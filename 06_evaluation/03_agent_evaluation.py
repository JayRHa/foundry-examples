"""03 - Agents bewerten: nicht nur die Antwort, sondern den Weg dorthin.

    python 06_evaluation/03_agent_evaluation.py

Bei einem Agent reicht "war die Antwort gut?" nicht. Die typischen Fehler
stecken dazwischen: falsches Tool, falsche Argumente, Abschweifen von der
Aufgabe. Dafuer gibt es eigene Evaluatoren:

  IntentResolution   Hat der Agent verstanden, was gewollt war?
  ToolCallAccuracy   Waren Tool-Auswahl und Argumente korrekt?
  TaskAdherence      Hat er sich an seine Instructions gehalten?

`AIAgentConverter` uebersetzt einen echten Thread in das Eingabeformat - man
bewertet also produktive Laeufe, nicht nachgebaute Beispiele.

Hinweis: Die Agent-Evaluatoren sind Teil der Preview-Oberflaeche von
azure-ai-evaluation und aendern sich schneller als der Rest. Deshalb hier mit
klarer Fehlermeldung statt hartem Absturz.

Beobachtet mit azure-ai-evaluation 1.18.5: TaskAdherenceEvaluator liefert fuer
diesen Fall reproduzierbar score=0.0, waehrend die mitgelieferte Begruendung das
Verhalten ausdruecklich als korrekt beschreibt. Der Eingabe-Payload ist
vollstaendig (Instructions stehen als system-Message in `query`), es ist also
ein Fehler im Evaluator, nicht im Aufruf.

Konsequenz fuer die Praxis: Bevor man einen Evaluator als Gate in eine Pipeline
haengt, prueft man ihn an Faellen mit bekanntem Ergebnis. Sonst blockiert eine
kaputte Metrik das Deployment - oder, schlimmer, winkt es durch.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from azure.ai.agents.models import FunctionTool, ToolSet

from common import get_agents_client, get_project_client, header, info, settings, warn


def get_weather(city: str) -> str:
    """Aktuelles Wetter fuer eine Stadt."""
    return f'{{"city": "{city}", "temp_c": 12, "condition": "Regen"}}'


def book_restaurant(city: str, people: int) -> str:
    """Reserviert einen Tisch. Nur nutzen, wenn ausdruecklich gewuenscht."""
    return f'{{"booking_id": "BK-1", "city": "{city}", "people": {people}}}'


class _AgentsAdapter:
    """Reicht einen AgentsClient unter dem Attribut `.agents` durch."""

    def __init__(self, agents_client) -> None:
        self.agents = agents_client


def model_config() -> dict:
    endpoint = settings.require_project_endpoint().split("/api/projects/")[0]
    config = {
        "azure_endpoint": endpoint,
        # Der Judge ist bewusst NICHT das Agent-Modell: bewerten soll ein
        # moeglichst starkes Modell, und der Judge laeuft ueber Chat Completions,
        # wo gpt-5.6-sol keine Einschraenkung hat.
        "azure_deployment": settings.model_deployment,
        "api_version": settings.openai_api_version,
    }
    if settings.api_key:
        config["api_key"] = settings.api_key
    return config


def main() -> None:
    header("Agent-Evaluation")

    try:
        from azure.ai.evaluation import (
            AIAgentConverter,
            IntentResolutionEvaluator,
            TaskAdherenceEvaluator,
            ToolCallAccuracyEvaluator,
        )
    except ImportError as exc:
        warn(f"Agent-Evaluatoren nicht verfuegbar: {exc}")
        warn("Abhilfe: pip install -U azure-ai-evaluation")
        return

    agents = get_agents_client()
    toolset = ToolSet()
    toolset.add(FunctionTool({get_weather, book_restaurant}))
    agents.enable_auto_function_calls(toolset)

    agent = agents.create_agent(
        model=settings.agent_model_deployment,
        name="foundry-demo-eval",
        instructions=(
            "Du hilfst bei Reiseplanung. Reserviere NUR, wenn ausdruecklich darum "
            "gebeten wird. Antworte auf Deutsch."
        ),
        toolset=toolset,
    )
    thread = agents.threads.create()

    try:
        agents.messages.create(
            thread_id=thread.id,
            role="user",
            content="Wie ist das Wetter morgen in Zuerich? Ich ueberlege, essen zu gehen.",
        )
        run = agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
        info(f"Run: {run.status}")

        # Echten Thread in Evaluations-Eingaben uebersetzen.
        #
        # Der Converter erwartet ein Objekt mit `.agents`, und `.agents` muss
        # der klassische AgentsClient sein (er ruft .runs / .messages /
        # .run_steps darauf auf). Beides passt nicht mehr zusammen:
        #   - AgentsClient direkt  -> 'AgentsClient' object has no attribute 'agents'
        #   - AIProjectClient 2.x  -> 'AgentsOperations' object has no attribute 'runs'
        # Ein Zwei-Zeilen-Adapter loest das, bis der Converter nachzieht.
        converter = AIAgentConverter(_AgentsAdapter(agents))
        evaluation_input = converter.convert(thread_id=thread.id, run_id=run.id)

        config = model_config()
        # is_reasoning_model=True ist bei der GPT-5-Familie als Judge Pflicht.
        evaluators = {
            "intent_resolution": IntentResolutionEvaluator(model_config=config, is_reasoning_model=True),
            "tool_call_accuracy": ToolCallAccuracyEvaluator(model_config=config, is_reasoning_model=True),
            "task_adherence": TaskAdherenceEvaluator(model_config=config, is_reasoning_model=True),
        }

        # Jeder Evaluator liefert mehrere Schluessel. Robust auslesen statt raten:
        #   <name>            numerischer Score
        #   <name>_result     "pass" / "fail"  <- das ist die Aussage, die zaehlt
        #   <name>_threshold  ab wann "pass"
        #   <name>_reason     Begruendung des Judge-Modells
        # Die Skalen unterscheiden sich je Evaluator und Version - deshalb nie
        # auf einen festen Bereich (1-5) hart verdrahten.
        for name, evaluator in evaluators.items():
            try:
                result = evaluator(**evaluation_input)
                verdict = result.get(f"{name}_result", "?")
                score = result.get(name, result.get(f"{name}_score"))
                threshold = result.get(f"{name}_threshold", "?")
                info(f"  {name:<20} {str(verdict):<5} score={score} (Schwelle {threshold})")
                info(f"    {str(result.get(f'{name}_reason', ''))[:160]}")
            except Exception as exc:
                warn(f"  {name:<20} nicht auswertbar: {type(exc).__name__}: {exc}")

        info(
            "\nErwartet: intent_resolution und tool_call_accuracy auf 'pass'. Der Agent "
            "soll das Wetter liefern und NICHT reservieren - niemand hat darum gebeten. "
            "Baut man 'book_restaurant' als Standardaktion in die Instructions ein, faellt "
            "tool_call_accuracy sofort durch, waehrend die Antwort weiter plausibel klingt."
        )
        info(
            "\ntask_adherence meldet mit azure-ai-evaluation 1.18.5 hier 'fail' bei "
            "score=0.0 - lies die Begruendung daneben: sie beschreibt das Verhalten als "
            "korrekt. Bekannte Schwaeche des Evaluators, siehe Modul-Docstring."
        )

    finally:
        agents.threads.delete(thread.id)
        agents.delete_agent(agent.id)


if __name__ == "__main__":
    main()
