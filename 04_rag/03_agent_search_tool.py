"""03 - Denselben Index als Agent-Tool einbinden.

    python 04_rag/03_agent_search_tool.py

Statt Retrieval selbst zu orchestrieren (02_hybrid_search.py), gibt man dem
Agent den Index als Tool. Er entscheidet dann selbst, ob und wonach er sucht -
und kann bei einer mehrteiligen Frage mehrfach suchen.

Voraussetzung: Der Suchdienst ist im Foundry-Projekt als Connection verknuepft,
Name in .env unter AZURE_SEARCH_CONNECTION_NAME.

Abwaegung:
  Eigenes Retrieval  -> volle Kontrolle, deterministisch, gut messbar
  Agent-Tool         -> weniger Code, mehrstufige Fragen von selbst, dafuer
                        weniger vorhersagbar (nicht jede Frage loest eine Suche aus)
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from azure.ai.agents.models import AzureAISearchQueryType, AzureAISearchTool

from common import answer, get_agents_client, header, info, settings, warn
from common.clients import resolve_connection_id

QUESTIONS = [
    "Welche Freigaben braucht eine IAM-Aenderung und wer entscheidet ab 20.000 EUR?",
    "Wie schnell muss ein Sev-1 gemeldet werden?",
]


def main() -> None:
    header("Azure AI Search als Agent-Tool")

    if not settings.search_connection_name:
        warn("AZURE_SEARCH_CONNECTION_NAME nicht gesetzt - Beispiel uebersprungen.")
        return

    agents = get_agents_client()
    connection_id = resolve_connection_id(settings.search_connection_name)

    search_tool = AzureAISearchTool(
        index_connection_id=connection_id,
        index_name=settings.search_index,
        query_type=AzureAISearchQueryType.VECTOR_SEMANTIC_HYBRID,
        top_k=4,
        # filter="source eq 'handbuch.md'",   # Metadatenfilter, z.B. pro Mandant
    )

    agent = agents.create_agent(
        model=settings.agent_model_deployment,
        name="foundry-demo-search",
        instructions=(
            "Beantworte Fragen ausschliesslich mit dem Suchindex. Fehlt die Information, "
            "sage das. Nenne immer die Quelle. Antworte auf Deutsch."
        ),
        tools=search_tool.definitions,
        tool_resources=search_tool.resources,
    )
    thread = agents.threads.create()

    try:
        for question in QUESTIONS:
            agents.messages.create(thread_id=thread.id, role="user", content=question)
            run = agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
            if run.status == "failed":
                warn(f"Run fehlgeschlagen: {run.last_error}")
                continue

            message = agents.messages.get_last_message_by_role(
                thread_id=thread.id, role="assistant"
            )
            answer(f"\nFRAGE  : {question}\nANTWORT: {message.text_messages[-1].text.value}")
            for annotation in message.url_citation_annotations:
                info(f"  Quelle: {annotation.url_citation.title}")

    finally:
        agents.threads.delete(thread.id)
        agents.delete_agent(agent.id)


if __name__ == "__main__":
    main()
