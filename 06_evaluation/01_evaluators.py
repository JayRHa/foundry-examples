"""01 - Einzelne Antworten bewerten: eingebaute und eigene Evaluatoren.

    python 06_evaluation/01_evaluators.py

Ohne Messung ist jede Prompt-Aenderung Bauchgefuehl. azure-ai-evaluation bringt
LLM-as-a-judge-Evaluatoren mit, die auf einer 1-5-Skala bewerten:

  Groundedness  Deckt der Kontext die Antwort? -> das Halluzinations-Mass fuer RAG
  Relevance     Beantwortet die Antwort die Frage?
  Retrieval     Waren die abgerufenen Dokumente die richtigen?
  Fluency       Sprachliche Qualitaet

Dazu kommen eigene, regelbasierte Evaluatoren. Die sind billig, deterministisch
und pruefen genau das, was dein Fachbereich fordert - das hier gezeigte
"Zitiert die Antwort eine Quelle?" ist so ein Fall.
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from azure.ai.evaluation import (
    GroundednessEvaluator,
    RelevanceEvaluator,
    AzureOpenAIModelConfiguration,
)

from common import header, info, settings

CONTEXT = (
    "Ein Team darf pro Monat bis zu 5.000 EUR an Cloud-Kosten ohne Ruecksprache "
    "verursachen. Ab 5.000 EUR ist ein Antrag im Kostenportal noetig, ab 20.000 EUR "
    "entscheidet das Architecture Board."
)
QUERY = "Ab welchem Betrag entscheidet das Architecture Board?"

CANDIDATES = {
    "gut": "Ab 20.000 EUR monatlichen Cloud-Kosten entscheidet das Architecture Board [handbuch.md#2].",
    "halluziniert": "Ab 50.000 EUR entscheidet das Architecture Board, ausserdem der CFO.",
    "am Thema vorbei": "Cloud-Kosten sollten regelmaessig ueberprueft werden.",
}


def judge_model_config() -> AzureOpenAIModelConfiguration:
    """Das bewertende Modell. Bewusst getrennt vom bewerteten - sonst benotet
    sich ein Modell selbst. In der Praxis nimmt man hier ein starkes Modell."""
    endpoint = settings.require_project_endpoint().split("/api/projects/")[0]
    config: AzureOpenAIModelConfiguration = {
        "azure_endpoint": endpoint,
        "azure_deployment": settings.model_deployment,
        "api_version": settings.openai_api_version,
    }
    if settings.api_key:  # ohne Key wird DefaultAzureCredential verwendet
        config["api_key"] = settings.api_key
    return config


# --- Eigener Evaluator: einfach ein Callable, das ein Dict zurueckgibt --------
class CitationEvaluator:
    """Prueft, ob die Antwort mindestens eine Quelle im Format [datei#id] nennt."""

    PATTERN = re.compile(r"\[[^\]\s]+#[^\]\s]+\]")

    def __call__(self, *, response: str, **kwargs) -> dict:
        citations = self.PATTERN.findall(response or "")
        return {"citation_count": len(citations), "has_citation": float(bool(citations))}


def main() -> None:
    header("Einzel-Evaluation")

    config = judge_model_config()
    # is_reasoning_model=True ist bei der GPT-5-Familie PFLICHT. Ohne das Flag
    # schickt azure-ai-evaluation intern `max_tokens` und `temperature` mit, und
    # jeder Judge-Aufruf endet in:
    #   Unsupported parameter: 'max_tokens' is not supported with this model.
    groundedness = GroundednessEvaluator(model_config=config, is_reasoning_model=True)
    relevance = RelevanceEvaluator(model_config=config, is_reasoning_model=True)
    citations = CitationEvaluator()

    for label, response in CANDIDATES.items():
        g = groundedness(query=QUERY, response=response, context=CONTEXT)
        r = relevance(query=QUERY, response=response)
        c = citations(response=response)

        info(f"\n--- {label} ---")
        info(f"  {response}")
        info(f"  Groundedness: {g['groundedness']}/5  ({g.get('groundedness_reason', '')[:110]})")
        info(f"  Relevance   : {r['relevance']}/5")
        info(f"  Zitate      : {int(c['citation_count'])}")


if __name__ == "__main__":
    main()
