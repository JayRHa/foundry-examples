"""01 - Der erste Agent: Agent, Thread, Run.

    python 03_agents/01_hello_agent.py

Das Agent Service kennt drei langlebige Objekte:

  Agent   Konfiguration: Modell, Instructions, Tools. Existiert unabhaengig
          vom Gespraech und wird wiederverwendet (siehe 10_lifecycle.py).
  Thread  Ein Gespraech. Haelt die Historie serverseitig - du musst sie nie
          selbst mitschleppen oder kuerzen.
  Run     Die Ausfuehrung eines Agents auf einem Thread.

`create_and_process` pollt bis zum Ende und fuehrt registrierte Funktions-Tools
automatisch aus - das ist der Loop aus 02_tools/, nur serverseitig.

Warum hier `settings.agent_model_deployment` statt `settings.model_deployment`?

Das klassische Agent Service ist die Bremse, nicht das Modell. Es sendet bei
jedem Run intern ein `top_p`, das gpt-5.5 und gpt-5.6-* ablehnen. Und selbst
aeltere GPT-5-Modelle laufen dort nur mit einem Teil der Tools - gpt-5-mini sagt
es unmissverstaendlich:

    The model 'gpt-5-mini' cannot be used with the following tools: openapi.
    This model only supports Responses API compatible tools.

Deshalb nutzen die Beispiele in diesem Ordner ein Modell, mit dem das Agent
Service vollstaendig funktioniert. Ueberall sonst (01_basics/, 02_tools/,
04_rag/02, 06_evaluation/, 08_agent_framework/) laeuft gpt-5.6-sol.

Merke: Wer heute neu baut, sollte fuer neue Modelle die Responses API bzw. das
Agent Framework (08_agent_framework/) waehlen - dort ist gpt-5.6-sol kein Problem.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from azure.ai.agents.models import ListSortOrder, MessageRole

from common import answer, get_agents_client, header, info, settings, warn


def main() -> None:
    header("Hello Agent")

    agents = get_agents_client()

    agent = agents.create_agent(
        model=settings.agent_model_deployment,
        name="foundry-demo-hello",
        instructions=(
            "Du bist ein Assistent fuer Cloud-Architektur. "
            "Antworte auf Deutsch, konkret und ohne Marketingsprache."
        ),
    )
    info(f"Agent: {agent.id}")

    thread = agents.threads.create()
    info(f"Thread: {thread.id}")

    try:
        agents.messages.create(
            thread_id=thread.id,
            role=MessageRole.USER,
            content="Wann lohnt sich ein Agent gegenueber einem einfachen Prompt?",
        )

        run = agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
        info(f"Run {run.id}: {run.status}")
        if run.status == "failed":
            warn(f"Fehler: {run.last_error}")
            return

        # Zweiter Turn: kein History-Handling noetig, der Thread haelt den Kontext.
        agents.messages.create(
            thread_id=thread.id, role=MessageRole.USER, content="Und wann eher nicht?"
        )
        agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)

        for message in agents.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING):
            for part in message.text_messages:
                prefix = "USER >" if message.role == MessageRole.USER else "AGENT>"
                answer(f"{prefix} {part.text.value}\n")

        if run.usage:
            info(f"Tokens: {run.usage.total_tokens}")

    finally:
        # In der Demo aufraeumen. In Produktion bleibt der Agent stehen und wird
        # ueber seine ID wiederverwendet - siehe 10_lifecycle.py.
        agents.threads.delete(thread.id)
        agents.delete_agent(agent.id)
        info("Agent und Thread geloescht.")


if __name__ == "__main__":
    main()
