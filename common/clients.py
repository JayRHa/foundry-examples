"""Client-Factories fuer Azure AI Foundry.

Ein Foundry-*Projekt* ist die Klammer um Deployments, Connections, Agents,
Dateien, Evaluations und Tracing:

    AIProjectClient
      |-- .get_openai_client()   -> OpenAI-kompatibler Client (Chat, Embeddings, Responses)
      |-- .connections           -> Search, Bing, App Insights, Storage, ...
      |-- .deployments           -> welche Modelle sind verfuegbar
      +-- .telemetry             -> App-Insights-Connection-String

    AgentsClient (Paket azure-ai-agents)
      +-- .threads / .messages / .runs / .run_steps / .files / .vector_stores

WICHTIG - SDK-Generationen:
`azure-ai-projects` 2.x ist ein Bruch gegenueber 1.x. Zwei Dinge aendern sich,
und beide erzeugen Fehler, die nicht nach ihrer Ursache aussehen:

  1. `project.agents` ist in 2.x NICHT mehr der klassische AgentsClient, sondern
     die neue, deklarative Agent-Version-API. Symptom:
       AttributeError: 'AgentsOperations' object has no attribute 'create_agent'
     Loesung: den AgentsClient direkt aus `azure-ai-agents` bauen (siehe unten).
     Das ist ohnehin die ehrlichere Variante - es ist ein eigenes Paket.

  2. `get_openai_client()` nimmt in 2.x kein `api_version` mehr. Der Client zeigt
     auf `{endpoint}/openai/v1` und ist damit versionslos. Symptom:
       TypeError: OpenAI.__init__() got an unexpected keyword argument 'api_version'

Beide Factories hier tragen deshalb 1.x und 2.x.

Auth: DefaultAzureCredential deckt lokal (`az login`), Managed Identity in Azure
und Service Principal in CI ab - ohne Codeaenderung. Keys nur als Notausgang.
"""

from __future__ import annotations

import functools

from azure.core.credentials import AzureKeyCredential, TokenCredential
from azure.identity import DefaultAzureCredential

from .config import settings

# Scope, unter dem Foundry-Datenebenen-Aufrufe autorisiert werden.
COGNITIVE_SERVICES_SCOPE = "https://ai.azure.com/.default"


@functools.lru_cache(maxsize=1)
def get_credential() -> TokenCredential:
    """Eine einzige Credential-Instanz teilen - sie cached Tokens intern."""
    return DefaultAzureCredential(
        # Interaktiven Browser-Login unterdruecken: schlaegt in CI sonst nur langsam fehl.
        exclude_interactive_browser_credential=True,
    )


@functools.lru_cache(maxsize=1)
def get_project_client():
    """Einstiegspunkt in das Foundry-Projekt."""
    from azure.ai.projects import AIProjectClient

    return AIProjectClient(
        endpoint=settings.require_project_endpoint(),
        credential=get_credential(),
    )


def get_openai_client(api_version: str | None = None):
    """OpenAI-kompatibler Client, konfiguriert aus dem Projekt.

    Vorteil gegenueber `AzureOpenAI(...)` von Hand: Endpoint und Token-Handling
    kommen aus dem Projekt, du hantierst nirgends mit Keys.

    `api_version` wird nur von azure-ai-projects 1.x ausgewertet. Unter 2.x zeigt
    der Client auf /openai/v1 und braucht keine Version - das Argument bleibt
    trotzdem erlaubt, damit die Beispiele auf beiden Generationen laufen.
    """
    project = get_project_client()
    version = api_version or settings.openai_api_version

    try:
        return project.get_openai_client(api_version=version)  # 1.x
    except AttributeError:
        return project.inference.get_azure_openai_client(api_version=version)  # 1.0.0bX
    except TypeError:
        pass  # 2.x: kein api_version mehr

    # 2.x: get_openai_client() zeigt per Default auf
    #   {endpoint}/api/projects/{projekt}/openai/v1
    # Dieser projektbezogene Pfad bedient Chat und Responses, aber NICHT
    # /embeddings - dort kommt ein nacktes 404 zurueck. Der Endpoint der
    # *Ressource* bedient beides, deshalb setzen wir base_url um.
    account_endpoint = settings.require_project_endpoint().split("/api/projects/")[0]
    return project.get_openai_client(base_url=f"{account_endpoint}/openai/v1")


@functools.lru_cache(maxsize=1)
def get_agents_client():
    """AgentsClient (Threads, Runs, Tools, Vector Stores).

    Direkt aus `azure-ai-agents` gebaut statt ueber `project.agents`: Unter
    azure-ai-projects 2.x zeigt `project.agents` auf eine andere API und der
    Zugriff schlaegt mit "'AgentsOperations' object has no attribute
    'create_agent'" fehl.
    """
    from azure.ai.agents import AgentsClient

    return AgentsClient(
        endpoint=settings.require_project_endpoint(),
        credential=get_credential(),
    )


def get_inference_client(model: str | None = None):
    """Client fuer den Model Catalog (Llama, Mistral, Phi, Cohere, DeepSeek, ...).

    Nutzt die einheitliche Azure-AI-Inference-API - derselbe Code funktioniert
    fuer jedes Modell im Katalog, nur der Deployment-Name aendert sich.
    """
    from azure.ai.inference import ChatCompletionsClient

    endpoint = settings.require_project_endpoint().split("/api/projects/")[0] + "/models"
    credential = (
        AzureKeyCredential(settings.api_key) if settings.api_key else get_credential()
    )
    kwargs = {} if settings.api_key else {"credential_scopes": [COGNITIVE_SERVICES_SCOPE]}
    return ChatCompletionsClient(
        endpoint=endpoint,
        credential=credential,
        model=model or settings.model_deployment,
        api_version="2024-05-01-preview",
        **kwargs,
    )


def get_search_client(index_name: str | None = None):
    """Azure-AI-Search-Client fuer die RAG-Beispiele."""
    from azure.search.documents import SearchClient

    credential = (
        AzureKeyCredential(settings.search_api_key)
        if settings.search_api_key
        else get_credential()
    )
    return SearchClient(
        endpoint=settings.require_search_endpoint(),
        index_name=index_name or settings.search_index,
        credential=credential,
    )


def resolve_connection_id(name: str) -> str:
    """Connection-Name -> ARM-Resource-ID, wie sie die Agent-Tools erwarten."""
    connection = get_project_client().connections.get(name=name)
    return connection.id
