"""02 - Prompts als versionierte Dateien statt als String im Code.

    python 09_ops/02_prompt_templates.py

Ein Prompt ist Konfiguration mit Verhaltensauswirkung - er gehoert versioniert,
reviewt und getestet, nicht als f-String zwischen zwei Funktionen.

Das .prompty-Format (Front Matter + Rollenabschnitte) hat sich dafuer etabliert:
Metadaten, Modellparameter und der eigentliche Prompt in einer Datei, lesbar
auch fuer Leute, die kein Python schreiben.

Hier ein kompakter Loader ohne zusaetzliche Abhaengigkeit. Er zeigt, worauf es
ankommt:
  - Prompt und Parameter kommen aus derselben Datei
  - Platzhalter werden explizit geprueft (fehlende Variable = Fehler, nicht
    stillschweigend "{{x}}" im Prompt)
  - die Parameter sind eine Allowlist, keine Durchreiche: sonst setzt ein
    Prompt-Autor `top_p`, und mit der GPT-5-Familie scheitert jeder Request
  - die Version wandert ins Logging, damit ein Ergebnis zuordenbar bleibt
"""

import json
import pathlib
import re
import sys
from dataclasses import dataclass

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import answer, get_openai_client, header, info, settings

PROMPTS_DIR = pathlib.Path(__file__).parent / "prompts"
ROLE_PATTERN = re.compile(r"^(system|user|assistant):\s*$", re.MULTILINE)
PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")

TICKET = (
    "Seit heute 8 Uhr laufen unsere naechtlichen Exporte nicht mehr durch, "
    "die Fehlermeldung lautet 'connection reset'. Betrifft alle Mandanten."
)


@dataclass
class Prompt:
    name: str
    version: int
    parameters: dict
    sections: list[tuple[str, str]]

    def render(self, **variables) -> list[dict]:
        messages = []
        for role, template in self.sections:
            required = set(PLACEHOLDER_PATTERN.findall(template))
            missing = required - variables.keys()
            if missing:
                # Lieber hier lautstark scheitern als einen kaputten Prompt senden.
                raise KeyError(f"Fehlende Prompt-Variablen: {sorted(missing)}")
            text = PLACEHOLDER_PATTERN.sub(lambda m: str(variables[m.group(1)]), template)
            messages.append({"role": role, "content": text.strip()})
        return messages


def load_prompt(path: pathlib.Path) -> Prompt:
    raw = path.read_text(encoding="utf-8")
    _, front_matter, body = raw.split("---", 2)

    # Minimaler YAML-Ersatz - reicht fuer flaches Front Matter ohne PyYAML.
    meta: dict = {}
    for line in front_matter.splitlines():
        if ":" in line and not line.startswith((" ", "-")):
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()

    parts = ROLE_PATTERN.split(body)
    sections = [(parts[i], parts[i + 1]) for i in range(1, len(parts) - 1, 2)]

    # Modellparameter aus dem Front Matter. Bewusst als Allowlist: was nicht hier
    # steht, landet auch nicht im Request. Ein Prompt-Autor soll `top_p` nicht
    # versehentlich setzen koennen - die GPT-5-Familie lehnt es ab.
    parameters: dict = {}
    for key, cast in (("max_completion_tokens", int), ("max_tokens", int),
                      ("temperature", float), ("reasoning_effort", str)):
        match = re.search(rf"{key}:\s*([\w.]+)", raw)
        if match:
            parameters[key] = cast(match.group(1))

    return Prompt(
        name=meta.get("name", path.stem),
        version=int(meta.get("version", 1)),
        parameters=parameters,
        sections=sections,
    )


def main() -> None:
    header("Prompt-Templates")

    prompt = load_prompt(PROMPTS_DIR / "ticket_triage.prompty")
    info(f"Prompt: {prompt.name} v{prompt.version}  Parameter: {prompt.parameters}")

    messages = prompt.render(
        ticket_text=TICKET,
        known_categories="infrastruktur, abrechnung, zugang, datenqualitaet, sonstiges",
    )
    for message in messages:
        info(f"\n[{message['role']}]\n{message['content'][:220]}")

    response = get_openai_client().chat.completions.create(
        model=settings.model_deployment, messages=messages, **prompt.parameters
    )
    answer("\n" + response.choices[0].message.content)

    # Die Version gehoert in jedes Log: sonst ist spaeter nicht rekonstruierbar,
    # welcher Prompt zu welchem Ergebnis gefuehrt hat.
    info(
        "\nLog: "
        + json.dumps(
            {
                "prompt": prompt.name,
                "prompt_version": prompt.version,
                "deployment": settings.model_deployment,
                "tokens": response.usage.total_tokens,
            }
        )
    )


if __name__ == "__main__":
    main()
