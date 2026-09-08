"""07 - Multi-Agent: ein Orchestrator delegiert an Spezialisten.

    python 03_agents/07_connected_agents.py

`ConnectedAgentTool` macht einen Agent fuer einen anderen zu einem Tool. Der
Orchestrator entscheidet selbst, wen er fragt - keine feste Ablaufsteuerung.

Wann lohnt sich das?
  + klar getrennte Zustaendigkeiten, jeweils eigene Tools/Instructions
  + Spezialisten sind unabhaengig testbar und wiederverwendbar
  - jeder Hop kostet Latenz und Tokens: bei 2-3 Tools im selben Agent lohnt es nicht

Die `description` ist entscheidend - danach waehlt der Orchestrator aus. Sie ist
Teil des Prompts, nicht Dokumentation.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from azure.ai.agents.models import ConnectedAgentTool

from common import answer, get_agents_client, header, info, settings, warn

POLICY = """
Reisekostenrichtlinie (Auszug):
- Bahn 1. Klasse ab 3 Stunden Fahrtzeit erstattungsfaehig.
- Hotel bis 180 EUR/Nacht in DACH, bis 250 EUR in Skandinavien.
- Verpflegungspauschale Inland 28 EUR/Tag, Ausland 40 EUR/Tag.
- Fluege innerhalb DACH nur mit schriftlicher Begruendung.
"""


def main() -> None:
    header("Connected Agents (Multi-Agent)")

    agents = get_agents_client()
    created: list[str] = []
    thread = None

    try:
        # --- Spezialist 1: kennt die Richtlinie ---------------------------
        policy_agent = agents.create_agent(
            model=settings.agent_model_deployment,
            name="foundry-demo-policy",
            instructions=(
                "Du beantwortest ausschliesslich Fragen zur folgenden Richtlinie. "
                "Antworte in ein bis zwei Saetzen.\n" + POLICY
            ),
        )
        created.append(policy_agent.id)

        # --- Spezialist 2: rechnet -----------------------------------------
        calc_agent = agents.create_agent(
            model=settings.agent_model_deployment,
            name="foundry-demo-calc",
            instructions=(
                "Du rechnest Reisekosten aus. Zeige den Rechenweg als kurze Liste "
                "und nenne die Summe in EUR."
            ),
        )
        created.append(calc_agent.id)

        # --- Orchestrator ---------------------------------------------------
        tools = [
            *ConnectedAgentTool(
                id=policy_agent.id,
                name="richtlinie",
                description="Fragen zur Reisekostenrichtlinie: Grenzen, Pauschalen, Erstattung.",
            ).definitions,
            *ConnectedAgentTool(
                id=calc_agent.id,
                name="rechner",
                description="Berechnet Summen und Erstattungsbetraege aus gegebenen Zahlen.",
            ).definitions,
        ]

        orchestrator = agents.create_agent(
            model=settings.agent_model_deployment,
            name="foundry-demo-travel",
            instructions=(
                "Du bearbeitest Reisekostenanfragen. Klaere Regeln immer ueber 'richtlinie' "
                "und lasse Betraege von 'rechner' ausrechnen. Fasse das Ergebnis fuer die "
                "Mitarbeitenden verstaendlich zusammen. Verwende KEINE Quellen-Marker."
            ),
            tools=tools,
        )
        created.append(orchestrator.id)

        thread = agents.threads.create()
        agents.messages.create(
            thread_id=thread.id,
            role="user",
            content=(
                "Dienstreise Zuerich -> Stockholm, 3 Naechte Hotel a 230 EUR, 4 Tage "
                "Verpflegung, Hinflug statt Bahn. Was wird erstattet?"
            ),
        )

        run = agents.runs.create_and_process(thread_id=thread.id, agent_id=orchestrator.id)
        if run.status == "failed":
            warn(f"Run fehlgeschlagen: {run.last_error}")
            return

        # Sichtbar machen, an wen delegiert wurde - sonst ist Multi-Agent nicht debugbar.
        for step in agents.run_steps.list(thread_id=thread.id, run_id=run.id):
            for call in step.get("step_details", {}).get("tool_calls", []):
                if "connected_agent" in call:
                    info(f"  -> delegiert an '{call['connected_agent'].get('name')}'")

        message = agents.messages.get_last_message_by_role(thread_id=thread.id, role="assistant")
        answer("\n" + message.text_messages[-1].text.value)

    finally:
        if thread:
            agents.threads.delete(thread.id)
        for agent_id in reversed(created):
            agents.delete_agent(agent_id)


if __name__ == "__main__":
    main()
