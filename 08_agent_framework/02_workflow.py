"""02 - Workflow: mehrere Agents in einem festen Ablauf.

    python 08_agent_framework/02_workflow.py

Connected Agents (03_agents/07) lassen den Orchestrator frei entscheiden.
Manchmal willst du genau das nicht, sondern einen festgelegten Ablauf:

    Planer -> Autor -> Lektorat

Das ist der Unterschied zwischen einem Agenten und einem Prozess mit Agenten.
Fuer alles Auditierbare - Freigaben, Abrechnung, regulierte Vorgaenge - ist der
Graph die richtige Wahl: gleicher Input, gleicher Pfad, kein Modell entscheidet
ueber die Route.

`add_chain` ist die Kurzform fuer eine lineare Kette. Fuer Verzweigungen gibt es
add_edge, add_switch_case_edge_group, add_fan_out_edges und add_fan_in_edges.

Zum Event-Modell: `workflow.run(..., stream=True)` liefert EINE Event-Klasse
(WorkflowEvent) mit einem `type`-Feld - nicht je Ereignis eine eigene Klasse.
Relevante Typen: "superstep_started"/"superstep_completed" (eine Runde des
Graphen), "executor_completed" (ein Knoten fertig), "output" (Text-Deltas des
Endknotens) und "status".
"""

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import answer, header, info, settings, warn

BRIEF = (
    "Schreibe eine interne Kurzmitteilung (max. 150 Woerter) an alle Entwickelnden: "
    "ab naechstem Monat laufen alle KI-Prototypen ueber unser Foundry-Projekt statt "
    "ueber private API-Keys. Ton: sachlich, kein Marketing."
)


async def main() -> None:
    header("Agent Framework - Workflow")

    try:
        from agent_framework import WorkflowBuilder
        from agent_framework_foundry import FoundryChatClient
        from azure.identity.aio import DefaultAzureCredential
    except ImportError as exc:
        warn(f"Agent Framework nicht installiert: {exc}")
        warn("pip install --pre -r requirements-agent-framework.txt")
        return

    async with DefaultAzureCredential(exclude_interactive_browser_credential=True) as credential:
        client = FoundryChatClient(
            project_endpoint=settings.require_project_endpoint(),
            model=settings.model_deployment,
            credential=credential,
        )

        planner = client.as_agent(
            name="planer",
            instructions=(
                "Du gliederst Kommunikationsaufgaben. Gib NUR eine Stichpunktliste "
                "mit den Kernbotschaften aus, keinen Fliesstext."
            ),
        )
        writer = client.as_agent(
            name="autor",
            instructions=(
                "Du schreibst aus einer Stichpunktliste eine interne Mitteilung. "
                "Maximal 150 Woerter, sachlicher Ton, kein Marketing."
            ),
        )
        editor = client.as_agent(
            name="lektorat",
            instructions=(
                "Du kuerzt und schaerfst den erhaltenen Text. Entferne Fuellwoerter "
                "und Floskeln. Gib NUR den finalen Text aus, ohne Kommentar."
            ),
        )

        # Jede Kante ist ein fester Uebergang - kein Modell entscheidet ueber den Weg.
        workflow = (
            WorkflowBuilder(start_executor=planner, name="mitteilung")
            .add_chain([planner, writer, editor])
            .build()
        )

        info("Ablauf: planer -> autor -> lektorat\n")

        # Achtung: "output"-Events kommen von JEDEM Knoten, nicht nur vom letzten.
        # Ohne Trennung nach executor_id klebt am Ende die Stichpunktliste des
        # Planers vor dem fertigen Text - deshalb pro Knoten sammeln.
        stages: dict[str, list[str]] = {}
        async for event in workflow.run(BRIEF, stream=True):
            kind = getattr(event, "type", "")

            if kind == "executor_completed":
                info(f"  [fertig] {event.executor_id}")

            elif kind == "output":
                text = getattr(event.data, "text", None)
                if text:
                    stages.setdefault(event.executor_id, []).append(text)

            elif kind == "status":
                info(f"  [status] {getattr(event, 'state', '')}")

        for executor_id, parts in stages.items():
            if executor_id == "lektorat":
                continue
            info(f"\n--- Zwischenstand: {executor_id} ---")
            info("".join(parts).strip()[:400])

        answer("\n--- Endergebnis ---\n" + "".join(stages.get("lektorat", [])).strip())


if __name__ == "__main__":
    asyncio.run(main())
