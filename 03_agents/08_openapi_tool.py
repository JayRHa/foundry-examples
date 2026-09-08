"""08 - OpenAPI-Tool: eine bestehende REST-API ohne Glue-Code anbinden.

    python 03_agents/08_openapi_tool.py

Du uebergibst eine OpenAPI-3.0-Spec, und das Agent Service ruft die Endpunkte
selbst auf - serverseitig, ohne dass dein Prozess involviert ist. Das ist der
schnellste Weg, ein vorhandenes Backend agentenfaehig zu machen.

Wichtig fuer die Praxis:
  - `operationId` und `description` je Operation sind Pflicht-Qualitaet: danach
    waehlt das Modell aus.
  - Grosse Specs unbedingt auf die relevanten Pfade eindampfen. Jede Operation
    kostet Prompt-Tokens in *jedem* Turn.
  - Auth: Anonymous (hier), Connection (API-Key aus einer Foundry-Connection)
    oder Managed Identity.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from azure.ai.agents.models import OpenApiAnonymousAuthDetails, OpenApiTool

from common import answer, get_agents_client, header, info, settings, warn

# Kleine, oeffentliche API ohne Auth - bewusst minimal gehalten.
SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Open-Meteo Wetter", "version": "1.0.0"},
    "servers": [{"url": "https://api.open-meteo.com"}],
    "paths": {
        "/v1/forecast": {
            "get": {
                "operationId": "getForecast",
                "description": "Wettervorhersage fuer Koordinaten. Liefert Tageswerte.",
                "parameters": [
                    {
                        "name": "latitude",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "number"},
                        "description": "Breitengrad, z.B. 47.37 fuer Zuerich",
                    },
                    {
                        "name": "longitude",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "number"},
                        "description": "Laengengrad, z.B. 8.54 fuer Zuerich",
                    },
                    {
                        "name": "daily",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"},
                        "description": "Komma-Liste, z.B. 'temperature_2m_max,precipitation_sum'",
                    },
                    {
                        "name": "forecast_days",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "integer"},
                        "description": "Anzahl Tage, 1-16",
                    },
                    {
                        "name": "timezone",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string"},
                        "description": "z.B. 'Europe/Zurich'",
                    },
                ],
                "responses": {"200": {"description": "Vorhersage als JSON"}},
            }
        }
    },
}


def main() -> None:
    header("OpenAPI Tool")

    agents = get_agents_client()

    openapi = OpenApiTool(
        name="wetter",
        spec=SPEC,
        description="Wettervorhersage nach Koordinaten abrufen.",
        auth=OpenApiAnonymousAuthDetails(),
    )

    agent = agents.create_agent(
        model=settings.agent_model_deployment,
        name="foundry-demo-openapi",
        instructions=(
            "Du beantwortest Wetterfragen. Bestimme Koordinaten selbst und rufe die API auf. "
            "Antworte auf Deutsch mit konkreten Zahlen und Einheiten."
        ),
        tools=openapi.definitions,
    )
    thread = agents.threads.create()

    try:
        agents.messages.create(
            thread_id=thread.id,
            role="user",
            content="Wie wird das Wetter die naechsten drei Tage in Zuerich? "
                    "Nenne Maximaltemperatur und Niederschlag pro Tag.",
        )
        run = agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
        if run.status == "failed":
            warn(f"Run fehlgeschlagen: {run.last_error}")
            return

        for step in agents.run_steps.list(thread_id=thread.id, run_id=run.id):
            for call in step.get("step_details", {}).get("tool_calls", []):
                fn = call.get("function")
                if fn:
                    info(f"  -> {fn.get('name')}({json.dumps(fn.get('arguments'))[:160]})")

        message = agents.messages.get_last_message_by_role(thread_id=thread.id, role="assistant")
        answer("\n" + message.text_messages[-1].text.value)

    finally:
        agents.threads.delete(thread.id)
        agents.delete_agent(agent.id)


if __name__ == "__main__":
    main()
