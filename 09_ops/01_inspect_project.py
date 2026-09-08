"""01 - Projekt inspizieren: was ist ueberhaupt da?

    python 09_ops/01_inspect_project.py

Der erste Befehl, wenn ein Beispiel nicht laeuft. Beantwortet die drei haeufigsten
Ursachen auf einen Blick:

  - Heisst mein Deployment wirklich so wie in .env?
  - Ist die Search-/Bing-Connection verknuepft und wie heisst sie genau?
  - Habe ich Zugriff (Rolle "Azure AI User" auf dem Projekt)?

Gleichzeitig ein Beispiel fuer die Verwaltungsoperationen des AIProjectClient,
die man fuer Dashboards oder CI-Checks braucht.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import get_agents_client, get_project_client, header, info, settings, warn


def section(title: str) -> None:
    info(f"\n{title}\n{'-' * len(title)}")


def main() -> None:
    header("Projekt-Inventar")
    info(f"Endpoint: {settings.project_endpoint}")

    try:
        project = get_project_client()
    except Exception as exc:
        warn(f"Verbindung fehlgeschlagen: {exc}")
        warn("Pruefe AZURE_AI_PROJECT_ENDPOINT und ob 'az login' aktiv ist.")
        return

    section("Deployments (Modelle)")
    try:
        found = False
        for deployment in project.deployments.list():
            found = True
            marker = ""
            if deployment.name == settings.model_deployment:
                marker = "  <- MODEL_DEPLOYMENT_NAME"
            elif deployment.name == settings.agent_model_deployment:
                marker = "  <- AGENT_MODEL_DEPLOYMENT_NAME"
            elif deployment.name == settings.embedding_deployment:
                marker = "  <- EMBEDDING_DEPLOYMENT_NAME"
            info(
                f"  {deployment.name:<32} {getattr(deployment, 'model_name', '?'):<28} "
                f"{getattr(deployment, 'model_publisher', '')}{marker}"
            )
        if not found:
            warn("  Keine Deployments. Im Portal unter 'Models + endpoints' eines anlegen.")
    except Exception as exc:
        warn(f"  Nicht lesbar: {exc}")

    section("Connections (externe Ressourcen)")
    try:
        found = False
        for connection in project.connections.list():
            found = True
            info(f"  {connection.name:<32} {connection.type}")
        if not found:
            info("  Keine Connections verknuepft.")
    except Exception as exc:
        warn(f"  Nicht lesbar: {exc}")

    section("Agents")
    try:
        # Bewusst der eigenstaendige AgentsClient: `project.agents` bedeutet in
        # azure-ai-projects 2.x etwas anderes (siehe common/clients.py).
        agents = list(get_agents_client().list_agents())
        if not agents:
            info("  Keine Agents angelegt.")
        for agent in agents:
            info(f"  {agent.id:<32} {agent.name:<28} {agent.model}")
    except Exception as exc:
        warn(f"  Nicht lesbar: {exc}")

    section("Datasets / Indexes")
    for label, operations in (("Datasets", "datasets"), ("Indexes", "indexes")):
        client = getattr(project, operations, None)
        if not client:
            continue
        try:
            names = [getattr(item, "name", "?") for item in client.list()]
            info(f"  {label}: {', '.join(names) if names else '-'}")
        except Exception as exc:
            info(f"  {label}: nicht lesbar ({type(exc).__name__})")

    section("Erwartete Werte aus .env")
    info(f"  MODEL_DEPLOYMENT_NAME        = {settings.model_deployment}")
    info(f"  AGENT_MODEL_DEPLOYMENT_NAME  = {settings.agent_model_deployment}")
    info(f"  EMBEDDING_DEPLOYMENT_NAME    = {settings.embedding_deployment}")
    info(f"  REASONING_DEPLOYMENT_NAME    = {settings.reasoning_deployment}")
    info(f"  AZURE_SEARCH_CONNECTION_NAME = {settings.search_connection_name or '-'}")
    info(f"  BING_CONNECTION_NAME         = {settings.bing_connection_name or '-'}")


if __name__ == "__main__":
    main()
