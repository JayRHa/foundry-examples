"""10 - Lebenszyklus: Agents und Threads ueber Prozessgrenzen hinweg nutzen.

    python 03_agents/10_lifecycle.py list        # alle Agents im Projekt
    python 03_agents/10_lifecycle.py ensure      # anlegen ODER aktualisieren
    python 03_agents/10_lifecycle.py chat "..."  # in einem persistenten Thread
    python 03_agents/10_lifecycle.py history
    python 03_agents/10_lifecycle.py cleanup

Die anderen Beispiele legen bei jedem Lauf einen Agent an und loeschen ihn wieder.
Fuer eine echte Anwendung ist das falsch: der Agent ist Konfiguration, die zum
Deployment gehoert, nicht zum Request.

Muster hier:
  - Agent per stabilem Namen suchen -> anlegen oder aktualisieren (idempotent)
  - Thread-ID pro Nutzer/Konversation speichern (hier: Datei, real: DB)
  - Der Thread ist das Gedaechtnis. Er waechst; irgendwann braucht es eine
    Strategie (neuer Thread pro Sitzung, Zusammenfassung, Ablauf nach N Tagen).
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from azure.ai.agents.models import ListSortOrder

from common import answer, get_agents_client, header, info, settings, warn

AGENT_NAME = "foundry-demo-persistent"
STATE_FILE = pathlib.Path(__file__).parent / "outputs" / "thread_state.json"

INSTRUCTIONS = (
    "Du bist ein persoenlicher Notizassistent. Du merkst dir, was die Person dir "
    "erzaehlt, und beziehst dich in spaeteren Antworten darauf. Antworte auf Deutsch."
)


def find_agent(agents, name: str):
    for agent in agents.list_agents():
        if agent.name == name:
            return agent
    return None


def ensure_agent(agents):
    """Idempotent: existiert der Agent, wird er aktualisiert, sonst angelegt."""
    existing = find_agent(agents, AGENT_NAME)
    if existing:
        updated = agents.update_agent(
            agent_id=existing.id,
            model=settings.agent_model_deployment,
            instructions=INSTRUCTIONS,
        )
        info(f"Agent aktualisiert: {updated.id}")
        return updated

    created = agents.create_agent(
        model=settings.agent_model_deployment, name=AGENT_NAME, instructions=INSTRUCTIONS
    )
    info(f"Agent angelegt: {created.id}")
    return created


def load_thread_id() -> str | None:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text()).get("thread_id")
    return None


def save_thread_id(thread_id: str) -> None:
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps({"thread_id": thread_id}, indent=2))


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "list"
    agents = get_agents_client()

    if command == "list":
        header("Agents im Projekt")
        for agent in agents.list_agents():
            info(f"  {agent.id}  {agent.name:<32} {agent.model}")
        return

    if command == "ensure":
        header("Agent sicherstellen")
        ensure_agent(agents)
        return

    if command == "chat":
        header("Chat im persistenten Thread")
        agent = ensure_agent(agents)

        thread_id = load_thread_id()
        if thread_id:
            info(f"Bestehender Thread: {thread_id}")
        else:
            thread_id = agents.threads.create().id
            save_thread_id(thread_id)
            info(f"Neuer Thread: {thread_id}")

        text = " ".join(sys.argv[2:]) or "Woran arbeite ich gerade?"
        agents.messages.create(thread_id=thread_id, role="user", content=text)
        run = agents.runs.create_and_process(thread_id=thread_id, agent_id=agent.id)
        if run.status == "failed":
            warn(f"Run fehlgeschlagen: {run.last_error}")
            return

        message = agents.messages.get_last_message_by_role(thread_id=thread_id, role="assistant")
        answer(message.text_messages[-1].text.value)
        info("\nTipp: Skript nochmal mit einer Folgefrage aufrufen - der Kontext bleibt.")
        return

    if command == "history":
        header("Thread-Verlauf")
        thread_id = load_thread_id()
        if not thread_id:
            warn("Noch kein Thread. Erst 'chat' aufrufen.")
            return
        for message in agents.messages.list(thread_id=thread_id, order=ListSortOrder.ASCENDING):
            for part in message.text_messages:
                role = getattr(message.role, "value", str(message.role))
                info(f"{role:>9}: {part.text.value}")
        return

    if command == "cleanup":
        header("Aufraeumen")
        thread_id = load_thread_id()
        if thread_id:
            agents.threads.delete(thread_id)
            STATE_FILE.unlink(missing_ok=True)
            info("Thread geloescht.")
        agent = find_agent(agents, AGENT_NAME)
        if agent:
            agents.delete_agent(agent.id)
            info("Agent geloescht.")
        return

    warn(f"Unbekannter Befehl: {command}")


if __name__ == "__main__":
    main()
