"""02 - Batch-Evaluation als Regressionstest fuer Prompts.

    python 06_evaluation/02_batch_evaluate.py v1
    python 06_evaluation/02_batch_evaluate.py v2

`evaluate()` laesst eine Zieffunktion ueber ein Datenset laufen und bewertet
jede Zeile. Das Ergebnis landet lokal als JSON und - wenn `azure_ai_project`
gesetzt ist - im Foundry-Portal unter "Evaluation", wo sich Laeufe vergleichen
lassen.

So wird aus Prompt-Tuning ein Engineering-Prozess:
  1. Datenset mit erwarteten Antworten pflegen (data/eval_dataset.jsonl)
  2. Prompt aendern
  3. Evaluation laufen lassen, Scores vergleichen
  4. Erst dann deployen

Der interessanteste Testfall im Datenset ist der letzte: die Antwort steht
NICHT im Kontext. Ein gutes System sagt das - ein schlechtes erfindet etwas.

Hier stehen zwei Prompt-Versionen zur Wahl. v1 ist zu streng formuliert und
verweigert die Antwort auch dann, wenn sie nur indirekt im Kontext steht
("Darf ich freitags deployen?" -> Kontext nennt einen Deployment-Stopp).
v2 erlaubt das Ableiten explizit. Genau diesen Unterschied macht die Messung
sichtbar - im Chatfenster faellt er kaum auf.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from azure.ai.evaluation import (
    AzureOpenAIModelConfiguration,
    GroundednessEvaluator,
    RelevanceEvaluator,
    evaluate,
)

from common import get_openai_client, header, info, settings

HERE = pathlib.Path(__file__).parent
DATASET = HERE / "data" / "eval_dataset.jsonl"
OUTPUT = HERE / "outputs" / "eval_result.json"

PROMPTS = {
    "v1": """Beantworte die Frage ausschliesslich aus dem Kontext.
Steht die Antwort nicht im Kontext, antworte exakt: Das steht nicht in den Unterlagen.
Antworte in einem Satz auf Deutsch.""",
    "v2": """Beantworte die Frage ausschliesslich aus dem Kontext.

- Der Kontext muss die Antwort nicht woertlich enthalten: Wenn sie sich eindeutig
  daraus ergibt, antworte und nenne die Stelle, auf die du dich stuetzt.
- Nur wenn der Kontext gar nichts zur Frage hergibt, antworte exakt:
  Das steht nicht in den Unterlagen.
- Antworte in ein bis zwei Saetzen auf Deutsch.""",
}


VERSION = sys.argv[1] if len(sys.argv) > 1 else "v1"


def target(query: str, context: str, **kwargs) -> dict:
    """Das zu testende System. evaluate() ruft das pro Datensatz-Zeile auf.

    Die Rueckgabe wird der Zeile hinzugefuegt - deshalb heisst der Schluessel
    'response', so wie ihn die Evaluatoren erwarten.
    """
    completion = get_openai_client().chat.completions.create(
        model=settings.model_deployment,
        messages=[
            {"role": "system", "content": PROMPTS[VERSION]},
            {"role": "user", "content": f"KONTEXT:\n{context}\n\nFRAGE: {query}"},
        ],
        max_completion_tokens=4000,
    )
    return {"response": completion.choices[0].message.content}


def main() -> None:
    header(f"Batch-Evaluation ({VERSION})")
    if VERSION not in PROMPTS:
        info(f"Unbekannte Version. Verfuegbar: {', '.join(PROMPTS)}")
        return
    OUTPUT.parent.mkdir(exist_ok=True)

    endpoint = settings.require_project_endpoint()
    config: AzureOpenAIModelConfiguration = {
        "azure_endpoint": endpoint.split("/api/projects/")[0],
        "azure_deployment": settings.model_deployment,
        "api_version": settings.openai_api_version,
    }
    if settings.api_key:
        config["api_key"] = settings.api_key

    result = evaluate(
        evaluation_name=f"handbuch-rag-{VERSION}",
        data=str(DATASET),
        target=target,
        evaluators={
            # is_reasoning_model=True: sonst sendet der Judge intern `max_tokens`
            # und die GPT-5-Familie lehnt jeden Aufruf ab.
            "groundedness": GroundednessEvaluator(model_config=config, is_reasoning_model=True),
            "relevance": RelevanceEvaluator(model_config=config, is_reasoning_model=True),
        },
        # Spalten des Datensets auf die Parameter der Evaluatoren mappen.
        evaluator_config={
            "groundedness": {
                "column_mapping": {
                    "query": "${data.query}",
                    "context": "${data.context}",
                    "response": "${target.response}",
                }
            },
            "relevance": {
                "column_mapping": {
                    "query": "${data.query}",
                    "response": "${target.response}",
                }
            },
        },
        # Ergebnisse ins Foundry-Portal hochladen (weglassen fuer rein lokal).
        azure_ai_project=endpoint,
        output_path=str(OUTPUT).replace(".json", f"-{VERSION}.json"),
    )

    info("\nDurchschnittswerte:")
    for metric, value in result["metrics"].items():
        if metric.endswith(("_score", "binary_aggregate")):
            continue  # Duplikate der Hauptmetrik ausblenden
        info(f"  {metric:<45} {value:.2f}")

    info("\nSchwaechste Zeilen:")
    rows = sorted(result["rows"], key=lambda r: r.get("outputs.groundedness.groundedness", 5))
    for row in rows[:2]:
        info(f"  Q: {row.get('inputs.query')}")
        info(f"  A: {str(row.get('outputs.response'))[:120]}")
        info(f"  Groundedness: {row.get('outputs.groundedness.groundedness')}\n")

    if url := result.get("studio_url"):
        info(f"\nIm Portal ansehen: {url}")
    info(
        "\nJetzt die andere Version laufen lassen und die Werte vergleichen:\n"
        f"  python 06_evaluation/02_batch_evaluate.py {'v2' if VERSION == 'v1' else 'v1'}"
    )


if __name__ == "__main__":
    main()
