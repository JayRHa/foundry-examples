"""07 - Responses API: serverseitiger Gespraechszustand.

    python 01_basics/07_responses_api.py

Unterschied zu Chat Completions: Du schickst nicht bei jedem Turn die ganze
Historie mit, sondern verweist mit `previous_response_id` auf die letzte Antwort.
Der Verlauf liegt beim Dienst.

  + kein eigenes History-Management, kein Aufblaehen des Requests
  + eingebaute Tools (File Search, Code Interpreter, Web Search) im selben Call
  - Zustand liegt beim Dienst: fuer Datenhaltung/Loeschkonzepte relevant

Braucht eine aktuelle API-Version (>= 2025-03-01-preview) und ein Deployment,
das die Responses API unterstuetzt.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import answer, get_openai_client, header, info, settings


def main() -> None:
    header("Responses API")

    client = get_openai_client(api_version="2025-04-01-preview")

    first = client.responses.create(
        model=settings.model_deployment,
        instructions="Du bist ein knapper Reisefuehrer. Maximal drei Saetze pro Antwort.",
        input="Nenne mir eine gute Stadt fuer ein langes Wochenende im November in Europa.",
    )
    answer(first.output_text)
    info(f"[response id: {first.id}]\n")

    # Zweiter Turn: nur der Verweis, kein erneutes Mitschicken der Historie.
    second = client.responses.create(
        model=settings.model_deployment,
        previous_response_id=first.id,
        input="Und was mache ich dort an einem Regentag?",
    )
    answer(second.output_text)

    # Streaming funktioniert genauso, nur mit Event-Typen statt Deltas.
    info("\n--- gestreamter dritter Turn ---")
    with client.responses.stream(
        model=settings.model_deployment,
        previous_response_id=second.id,
        input="Fasse deine beiden Empfehlungen in einem Satz zusammen.",
    ) as stream:
        for event in stream:
            if event.type == "response.output_text.delta":
                print(event.delta, end="", flush=True)
    print()


if __name__ == "__main__":
    main()
