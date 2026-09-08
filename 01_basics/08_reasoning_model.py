"""08 - Reasoning-Modelle: `reasoning_effort` als Kosten- und Latenzhebel.

    python 01_basics/08_reasoning_model.py

Die GPT-5-Familie denkt vor dem Antworten. Diese Denk-Tokens sind unsichtbar,
werden aber mitbezahlt und kosten Zeit. `reasoning_effort` steuert, wie viel
davon entsteht - der wichtigste Regler, den man an diesen Modellen hat.

Drei Fallstricke, die zuverlaessig Fehler produzieren:

  1. `max_tokens` existiert nicht mehr -> `max_completion_tokens`. Und das Budget
     deckt auch die unsichtbaren Reasoning-Tokens ab: zu knapp gesetzt, kommt
     eine LEERE Antwort mit finish_reason="length" zurueck. Man bezahlt dann
     fuers Nachdenken, ohne ein Ergebnis zu bekommen.
  2. `temperature` akzeptiert nur den Default (1), `top_p` gar nicht.
     Determinismus holt man sich ueber Structured Outputs und praezise Prompts,
     nicht mehr ueber Sampling-Parameter.
  3. Statt "system" ist "developer" der vorgesehene Rollenname (beides wird
     aktuell akzeptiert).

Das Skript laesst dieselbe Aufgabe mit mehreren Effort-Stufen laufen und zeigt
Zeit, Reasoning-Tokens und Ergebnis nebeneinander. Fuer diese kleine Logikaufgabe
liegen die Stufen dicht beieinander - der Punkt ist die Messmethode, nicht die
konkrete Zahl. Bei mehrstufigen Aufgaben geht die Schere weit auf.
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import answer, get_openai_client, header, info, settings, warn

PUZZLE = """
Drei Server A, B, C laufen hinter einem Loadbalancer.
- A faellt genau dann aus, wenn B laeuft.
- C laeuft nur, wenn mindestens einer von A und B laeuft.
- Es laufen nie alle drei gleichzeitig.
Welche Kombinationen sind moeglich? Antworte mit der Liste der Tripel (A,B,C)
als 1/0 und einem Satz Begruendung.
"""

EFFORTS = ["none", "low", "medium", "high"]


def main() -> None:
    header("Reasoning-Modell: reasoning_effort im Vergleich")

    client = get_openai_client()
    info(f"Deployment: {settings.reasoning_deployment}\n")

    for effort in EFFORTS:
        started = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=settings.reasoning_deployment,
                messages=[
                    {"role": "developer", "content": "Antworte knapp und auf Deutsch."},
                    {"role": "user", "content": PUZZLE},
                ],
                reasoning_effort=effort,
                # Grosszuegig: das Budget muss Reasoning UND Antwort abdecken.
                max_completion_tokens=8000,
            )
        except Exception as exc:
            warn(f"{effort:<7} fehlgeschlagen: {str(exc)[:160]}")
            continue

        elapsed = time.perf_counter() - started
        choice = response.choices[0]

        details = getattr(response.usage, "completion_tokens_details", None)
        reasoning_tokens = getattr(details, "reasoning_tokens", 0) or 0

        info(
            f"--- reasoning_effort={effort} --- "
            f"{elapsed:5.1f}s | {reasoning_tokens:5d} Reasoning-Tokens | "
            f"{response.usage.completion_tokens:5d} Completion-Tokens gesamt"
        )

        if choice.finish_reason == "length" and not choice.message.content:
            warn("  Leere Antwort: Budget ging komplett fuers Nachdenken drauf.")
            continue

        answer("  " + (choice.message.content or "").strip().replace("\n", "\n  "))
        print()

    info(
        "Faustregel: die niedrigste Stufe nehmen, die das Ergebnis noch trifft -\n"
        "und das an der eigenen Aufgabe messen, nicht schaetzen. Wie weit die\n"
        "Stufen auseinanderliegen, haengt komplett am Problem: Bei dieser kleinen\n"
        "Logikaufgabe liegen 'low' und 'high' nur wenige Dutzend Reasoning-Tokens\n"
        "auseinander. Bei mehrstufigen Aufgaben (Code, Beweise, lange Planung)\n"
        "koennen es Tausende sein - dort entscheidet der Regler ueber die Rechnung."
    )


if __name__ == "__main__":
    main()
