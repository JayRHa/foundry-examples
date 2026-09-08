"""06 - Grounding with Bing Search: aktuelle Fakten statt Trainingsstand.

    python 03_agents/06_bing_grounding.py

Voraussetzung: eine "Grounding with Bing Search"-Ressource in Azure, die im
Foundry-Projekt als Connection verknuepft ist. Den Namen traegst du als
BING_CONNECTION_NAME in .env ein.

Zwei Punkte, die in der Praxis zaehlen:
  - Die Nutzungsbedingungen verlangen, dass du die Bing-Quellen mit Link anzeigst.
    Die Annotations liefern genau das - nicht wegwerfen.
  - Grounding kostet pro Suche extra und macht Antworten langsamer. Nur
    aktivieren, wenn Aktualitaet wirklich gebraucht wird.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from azure.ai.agents.models import BingGroundingTool

from common import answer, get_agents_client, header, info, settings, warn
from common.clients import resolve_connection_id


def main() -> None:
    header("Bing Grounding")

    if not settings.bing_connection_name:
        warn("BING_CONNECTION_NAME ist nicht gesetzt - Beispiel uebersprungen.")
        return

    agents = get_agents_client()
    connection_id = resolve_connection_id(settings.bing_connection_name)
    info(f"Connection: {connection_id}")

    bing = BingGroundingTool(connection_id=connection_id, market="de-DE", count=5)

    agent = agents.create_agent(
        model=settings.agent_model_deployment,
        name="foundry-demo-research",
        instructions=(
            "Recherchiere mit der Websuche und antworte auf Deutsch. "
            "Nenne fuer jede Aussage die Quelle. Wenn du nichts findest, sag es."
        ),
        tools=bing.definitions,
    )
    thread = agents.threads.create()

    try:
        agents.messages.create(
            thread_id=thread.id,
            role="user",
            content="Welche Modellfamilien sind aktuell im Azure-AI-Foundry-Katalog verfuegbar?",
        )
        run = agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
        if run.status == "failed":
            warn(f"Run fehlgeschlagen: {run.last_error}")
            return

        # Die tatsaechlich abgesetzte Bing-Query steht in den Run Steps.
        for step in agents.run_steps.list(thread_id=thread.id, run_id=run.id):
            for call in step.get("step_details", {}).get("tool_calls", []):
                query = call.get("bing_grounding", {}).get("requesturl")
                if query:
                    info(f"  Suchanfrage: {query}")

        message = agents.messages.get_last_message_by_role(thread_id=thread.id, role="assistant")
        answer(message.text_messages[-1].text.value)

        info("\nQuellen:")
        for annotation in message.url_citation_annotations:
            info(f"  - {annotation.url_citation.title}: {annotation.url_citation.url}")

    finally:
        agents.threads.delete(thread.id)
        agents.delete_agent(agent.id)


if __name__ == "__main__":
    main()
