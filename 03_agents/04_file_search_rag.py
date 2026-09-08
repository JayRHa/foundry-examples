"""04 - File Search: RAG ohne eigene Pipeline.

    python 03_agents/04_file_search_rag.py

Ein Vector Store im Agent Service uebernimmt Chunking, Embedding, Index und
hybride Suche. Fuer "ein paar hundert Dokumente, Standardverhalten" ist das der
schnellste Weg zu belastbaren Antworten.

Wann stattdessen Azure AI Search (siehe 04_rag/)?
  - eigene Chunking-Strategie oder Metadaten-Filter (Mandant, Sprache, Gueltigkeit)
  - der Index wird auch ausserhalb der Agents genutzt
  - grosse oder haeufig aktualisierte Korpora

Die Zitate stehen in den Annotations - ohne sie ist eine RAG-Antwort nicht pruefbar.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from azure.ai.agents.models import FilePurpose, FileSearchTool

from common import answer, get_agents_client, header, info, settings, warn

HERE = pathlib.Path(__file__).parent
DOC = HERE / "data" / "handbuch.md"

QUESTIONS = [
    "Darf ich freitags produktiv deployen?",
    "Ab welcher Summe entscheidet das Architecture Board ueber Cloud-Kosten?",
    "Welches Modell darf ich fuer eine Kunden-App mit Personendaten nutzen?",
]


def main() -> None:
    header("File Search (RAG)")

    agents = get_agents_client()

    uploaded = agents.files.upload_and_poll(file_path=str(DOC), purpose=FilePurpose.AGENTS)
    vector_store = agents.vector_stores.create_and_poll(
        file_ids=[uploaded.id], name="foundry-demo-handbuch"
    )
    info(f"Vector Store: {vector_store.id} ({vector_store.file_counts.completed} Datei(en))")

    file_search = FileSearchTool(vector_store_ids=[vector_store.id])

    agent = agents.create_agent(
        model=settings.agent_model_deployment,
        name="foundry-demo-handbuch",
        instructions=(
            "Beantworte Fragen ausschliesslich aus den bereitgestellten Dokumenten. "
            "Wenn die Antwort nicht darin steht, sage das klar. Zitiere die Quelle."
        ),
        tools=file_search.definitions,
        tool_resources=file_search.resources,
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
            text = message.text_messages[-1].text.value
            answer(f"\nFRAGE  : {question}\nANTWORT: {text}")

            for annotation in message.url_citation_annotations:
                info(f"  Quelle: {annotation.url_citation.title}")
            for annotation in getattr(message, "file_citation_annotations", []):
                info(f"  Beleg: {annotation.text}")

    finally:
        agents.threads.delete(thread.id)
        agents.delete_agent(agent.id)
        agents.vector_stores.delete(vector_store.id)
        agents.files.delete(uploaded.id)


if __name__ == "__main__":
    main()
