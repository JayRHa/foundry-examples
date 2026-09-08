"""Zentrale Konfiguration.

Kein Beispiel liest os.environ direkt - alles laeuft ueber `settings`.
So aendert sich bei einem Umzug auf ein anderes Projekt genau eine Stelle.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

# .env aus dem Repo-Root laden, ohne bereits gesetzte Umgebungsvariablen zu ueberschreiben
# (wichtig in CI/Container, wo die Werte von aussen kommen).
load_dotenv(REPO_ROOT / ".env", override=False)


class MissingSetting(RuntimeError):
    """Aussagekraeftiger Fehler statt eines kryptischen 401 weiter unten im Stack."""

    def __init__(self, key: str) -> None:
        super().__init__(
            f"Umgebungsvariable '{key}' fehlt. "
            f"Kopiere .env.example nach .env und trage den Wert ein."
        )


def _get(key: str, default: str | None = None) -> str | None:
    value = os.environ.get(key, default)
    return value.strip() if isinstance(value, str) else value


@dataclass(frozen=True)
class Settings:
    project_endpoint: str | None = field(default_factory=lambda: _get("AZURE_AI_PROJECT_ENDPOINT"))

    # Das Standardmodell fuer alles, was ueber Chat Completions / Responses laeuft.
    model_deployment: str = field(
        default_factory=lambda: _get("MODEL_DEPLOYMENT_NAME", "gpt-5.6-sol")
    )

    # Eigenes Modell fuer das klassische Agent Service. Zwei Gruende, warum dort
    # nicht dasselbe Modell wie oben steht:
    #
    #   1. Das Agent Service sendet bei jedem Run intern ein `top_p`. gpt-5.5 und
    #      gpt-5.6-* lehnen den Parameter ab -> der Run scheitert mit
    #      "Unsupported parameter: 'top_p' is not supported with this model",
    #      und es gibt keine Moeglichkeit, ihn zu unterdruecken.
    #   2. Auch aeltere GPT-5-Modelle (gpt-5.4, gpt-5-mini) laufen dort nur mit
    #      einem TEIL der Tools. gpt-5-mini sagt es deutlich:
    #      "This model only supports Responses API compatible tools."
    #      Code Interpreter, File Search und MCP funktionieren; OpenAPI,
    #      Bing Grounding, Connected Agents und Azure AI Search nicht.
    #      gpt-5.4 quittiert dieselben Faelle mit einem nichtssagenden
    #      "server_error: Sorry, something went wrong."
    #
    # gpt-4o ist damit das Modell, mit dem ALLE Agent-Beispiele durchlaufen.
    # Wer nur Code Interpreter / File Search / MCP nutzt, kann hier gpt-5.4
    # eintragen.
    agent_model_deployment: str = field(
        default_factory=lambda: _get("AGENT_MODEL_DEPLOYMENT_NAME", "gpt-4o")
    )
    embedding_deployment: str = field(
        default_factory=lambda: _get("EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-small")
    )
    # Fuer 01_basics/08. gpt-5.6-sol ist selbst ein Reasoning-Modell, deshalb ist
    # das per Default dasselbe Deployment.
    reasoning_deployment: str = field(
        default_factory=lambda: _get("REASONING_DEPLOYMENT_NAME", "gpt-5.6-sol")
    )
    openai_api_version: str = field(
        default_factory=lambda: _get("OPENAI_API_VERSION", "2024-10-21")
    )

    api_key: str | None = field(default_factory=lambda: _get("AZURE_AI_API_KEY"))
    azure_openai_endpoint: str | None = field(
        default_factory=lambda: _get("AZURE_OPENAI_ENDPOINT")
    )

    search_endpoint: str | None = field(default_factory=lambda: _get("AZURE_SEARCH_ENDPOINT"))
    search_index: str = field(
        default_factory=lambda: _get("AZURE_SEARCH_INDEX_NAME", "foundry-demo-index")
    )
    search_api_key: str | None = field(default_factory=lambda: _get("AZURE_SEARCH_API_KEY"))
    search_connection_name: str | None = field(
        default_factory=lambda: _get("AZURE_SEARCH_CONNECTION_NAME")
    )

    bing_connection_name: str | None = field(default_factory=lambda: _get("BING_CONNECTION_NAME"))
    app_insights_connection_string: str | None = field(
        default_factory=lambda: _get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    )

    def require_project_endpoint(self) -> str:
        if not self.project_endpoint:
            raise MissingSetting("AZURE_AI_PROJECT_ENDPOINT")
        return self.project_endpoint

    def require_search_endpoint(self) -> str:
        if not self.search_endpoint:
            raise MissingSetting("AZURE_SEARCH_ENDPOINT")
        return self.search_endpoint


settings = Settings()
