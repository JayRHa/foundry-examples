"""03 - Was zwischen Prototyp und Produktion liegt.

    python 09_ops/03_production_hardening.py

Vier Dinge, die im Demo-Code fehlen und in Produktion zuverlaessig weh tun:

  1. 429 (Rate Limit)   -> Backoff, der `retry-after-ms` respektiert statt zu raten
  2. Content Filter     -> kein Serverfehler, sondern eine fachliche Antwort
  3. Timeouts           -> ohne Limit haengt ein Request bis zum Client-Default
  4. Kosten             -> Tokens pro Use Case zaehlen, bevor die Rechnung kommt

Nichts davon ist Foundry-spezifisch - aber alles davon fehlt in jedem Quickstart.
"""

import pathlib
import random
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import httpx
from openai import APIConnectionError, APITimeoutError, BadRequestError, RateLimitError

from common import answer, get_openai_client, header, info, settings, warn

# Preise pro 1 Mio. Tokens als (Input, Output), in USD.
#
# Diese Tabelle wird bewusst von Hand gepflegt und ist bewusst UNVOLLSTAENDIG:
# Fuer neue Modelle steht oft noch nichts in der oeffentlichen Preisliste (die
# Azure Retail Prices API liefert fuer gpt-5.6-sol aktuell keinen Eintrag).
#
# Der wichtige Teil ist unten in report(): Ein fehlender Preis wird ANGEZEIGT,
# nicht als 0 verrechnet. Eine Kostenauswertung, die stillschweigend 0,00 USD
# meldet, ist schlimmer als gar keine - man haelt sie fuer eine Aussage.
PRICE_PER_1M_TOKENS: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    # "gpt-5.6-sol": (?, ?),   <- aus der Azure-Preisliste eintragen
}


@dataclass
class UsageTracker:
    """Zaehlt Tokens und geschaetzte Kosten pro Use Case."""

    by_use_case: dict[str, dict] = field(default_factory=lambda: defaultdict(
        lambda: {"prompt": 0, "completion": 0, "calls": 0}
    ))

    def record(self, use_case: str, usage) -> None:
        entry = self.by_use_case[use_case]
        entry["prompt"] += usage.prompt_tokens
        entry["completion"] += usage.completion_tokens
        entry["calls"] += 1

    def report(self, deployment: str) -> None:
        prices = PRICE_PER_1M_TOKENS.get(deployment)

        info("\nVerbrauch:")
        for use_case, entry in self.by_use_case.items():
            tokens = entry["prompt"] + entry["completion"]
            line = (
                f"  {use_case:<16} {entry['calls']} Aufruf(e), "
                f"{tokens} Tokens ({entry['prompt']} in / {entry['completion']} out)"
            )
            if prices:
                cost = entry["prompt"] / 1e6 * prices[0] + entry["completion"] / 1e6 * prices[1]
                line += f", ~{cost:.4f} USD"
            info(line)

        if not prices:
            warn(
                f"Fuer '{deployment}' ist kein Preis hinterlegt - es werden nur Tokens "
                f"ausgewiesen, KEINE Kosten. Preise in PRICE_PER_1M_TOKENS eintragen."
            )


def chat_with_retry(client, *, max_attempts: int = 5, **kwargs):
    """Chat-Aufruf mit exponentiellem Backoff und Jitter.

    Wichtig: Bei 429 sagt der Dienst im Header, wie lange zu warten ist. Diesen
    Wert zu nutzen ist deutlich besser als eine feste Wartezeit - er beruecksichtigt
    das tatsaechliche Quota-Fenster.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return client.chat.completions.create(timeout=httpx.Timeout(30.0, connect=5.0), **kwargs)

        except RateLimitError as exc:
            if attempt == max_attempts:
                raise
            headers = getattr(exc.response, "headers", {}) or {}
            retry_after_ms = headers.get("retry-after-ms")
            retry_after = headers.get("retry-after")
            if retry_after_ms:
                delay = int(retry_after_ms) / 1000
            elif retry_after:
                delay = float(retry_after)
            else:
                delay = min(2**attempt, 30) + random.uniform(0, 1)  # Jitter gegen Thundering Herd
            warn(f"  429 - Versuch {attempt}, warte {delay:.1f}s")
            time.sleep(delay)

        except (APITimeoutError, APIConnectionError) as exc:
            if attempt == max_attempts:
                raise
            delay = min(2**attempt, 20)
            warn(f"  {type(exc).__name__} - Versuch {attempt}, warte {delay}s")
            time.sleep(delay)

        except BadRequestError as exc:
            # Content Filter: NICHT wiederholen - das Ergebnis bleibt gleich.
            # Das ist ein fachliches Ereignis, das die Anwendung behandeln muss.
            if getattr(exc, "code", "") == "content_filter" or "content_filter" in str(exc):
                raise ContentFiltered(exc) from exc
            raise

    raise RuntimeError("unerreichbar")


class ContentFiltered(Exception):
    """Der Inhaltsfilter hat Eingabe oder Ausgabe blockiert."""

    def __init__(self, original: BadRequestError) -> None:
        super().__init__("Vom Inhaltsfilter blockiert")
        self.categories = self._extract_categories(original)

    @staticmethod
    def _extract_categories(exc: BadRequestError) -> list[str]:
        try:
            details = exc.response.json()["error"]["innererror"]["content_filter_result"]
            return [name for name, value in details.items() if value.get("filtered")]
        except Exception:
            return []


def main() -> None:
    header("Produktionshaertung")

    client = get_openai_client()
    tracker = UsageTracker()

    requests = [
        ("faq", "Was ist ein Vector Store im Agent Service? Ein Satz."),
        ("faq", "Wozu dient ein Semantic Ranker? Ein Satz."),
        ("zusammenfassung", "Fasse in einem Satz zusammen, was Retry-Logik bewirkt."),
    ]

    for use_case, question in requests:
        try:
            response = chat_with_retry(
                client,
                model=settings.model_deployment,
                messages=[{"role": "user", "content": question}],
                max_completion_tokens=2000,
                # user-Feld hilft Azure beim Missbrauchsschutz und dir beim Debuggen.
                user=f"demo:{use_case}",
            )
        except ContentFiltered as exc:
            warn(f"  Blockiert ({', '.join(exc.categories) or 'unbekannt'}) - "
                 f"Nutzerin freundlich informieren, nicht 500 zurueckgeben.")
            continue
        except Exception as exc:
            warn(f"  Endgueltig fehlgeschlagen: {type(exc).__name__}: {exc}")
            continue

        tracker.record(use_case, response.usage)
        answer(f"[{use_case}] {response.choices[0].message.content}")

    tracker.report(settings.model_deployment)

    info(
        "\nWeitere Punkte fuer Produktion:\n"
        "  - Provisioned Throughput (PTU) statt Pay-as-you-go bei stabiler Last\n"
        "  - Mehrere Deployments/Regionen und Failover im Client\n"
        "  - Private Endpoints, damit kein Verkehr ueber das oeffentliche Internet laeuft\n"
        "  - Eigene Content-Filter-Policy pro Deployment statt Standardstufe\n"
        "  - Traces mit Nutzer-/Mandanten-Attribut (07_observability/)"
    )


if __name__ == "__main__":
    main()
