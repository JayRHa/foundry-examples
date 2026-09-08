"""01 - Agent Framework: Agent mit Tools, lokal definiert.

    pip install --pre -r requirements-agent-framework.txt
    python 08_agent_framework/01_basics.py

Unterschied zu 03_agents/: Der Agent ist ein Python-Objekt in deinem Prozess.
Kein Anlegen, kein Loeschen, keine Agent-IDs - dafuer haelst du den Zustand
selbst und Tools laufen immer lokal.

Das Modell kommt weiter aus dem Foundry-Projekt: die Trennung verlaeuft zwischen
Orchestrierung (lokal) und Inferenz (Foundry).

Zur Paketstruktur: `agent_framework` ist der Kern, die Foundry-Anbindung liegt in
`agent_framework_foundry`. Der `FoundryChatClient` spricht die Responses API des
Projekts; `FoundryAgent` waere fuer bereits IN Foundry angelegte Agents.
"""

import asyncio
import pathlib
import sys
from typing import Annotated

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pydantic import Field

from common import answer, header, info, settings, warn


def get_flight_status(
    flight_number: Annotated[str, Field(description="Flugnummer, z.B. LX318")],
) -> str:
    """Aktueller Status eines Flugs."""
    return f"{flight_number}: puenktlich, Gate A42, Boarding 14:35"


def get_gate_walk_time(
    gate: Annotated[str, Field(description="Gate-Bezeichnung, z.B. A42")],
) -> str:
    """Fussweg zum Gate ab Sicherheitskontrolle in Minuten."""
    return f"Gate {gate}: etwa 12 Minuten Fussweg"


async def main() -> None:
    header("Agent Framework - Grundlagen")

    try:
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

        # Tools sind einfach Python-Funktionen. Signatur, Docstring und die
        # Annotated-Beschreibungen werden zum Schema - kein separates JSON.
        agent = client.as_agent(
            name="reise-assistent",
            instructions="Du hilfst am Flughafen. Antworte auf Deutsch, kurz und konkret.",
            tools=[get_flight_status, get_gate_walk_time],
        )

        result = await agent.run("Ist LX318 puenktlich und wie lange laufe ich zum Gate?")
        answer(result.text)

        # Eine Session haelt den Verlauf - im Prozess, nicht im Dienst.
        session = agent.create_session()
        await agent.run("Ich fliege LX318.", session=session)
        followup = await agent.run("Wann muss ich an der Kontrolle sein?", session=session)
        answer("\n" + followup.text)

        info("\n--- gestreamt ---")
        async for update in agent.run(
            "Fasse deine Empfehlung in einem Satz zusammen.", session=session, stream=True
        ):
            if update.text:
                print(update.text, end="", flush=True)
        print()


if __name__ == "__main__":
    asyncio.run(main())
