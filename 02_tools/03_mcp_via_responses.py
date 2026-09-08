"""03 - MCP-Server als Tool, ohne eigenen Client-Code.

    python 02_tools/03_mcp_via_responses.py

Model Context Protocol standardisiert, wie ein Modell an fremde Tools kommt.
Die Responses API kann einen MCP-Server direkt einbinden: Der Dienst holt sich
die Tool-Liste vom Server und ruft sie waehrend des Runs selbst auf. Du schreibst
weder Tool-Schemas noch einen Tool-Loop.

`require_approval` ist die entscheidende Stellschraube:
  "never"                      -> alles automatisch (nur fuer vertrauenswuerdige Server)
  {"never": {"tool_names": []}} -> Whitelist, Rest braucht Freigabe
  "always"                      -> jeder Aufruf muss bestaetigt werden

Achtung: Ein MCP-Server kann Tool-Beschreibungen liefern, die wie Anweisungen
gelesen werden (Prompt Injection). Nur Server einbinden, denen du vertraust,
und Schreibzugriffe hinter eine Freigabe legen.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import answer, get_openai_client, header, info, settings, warn

# Oeffentlicher Beispiel-Server (nur Lesen). Fuer eigene Server: server_url
# ersetzen und bei Bedarf `headers` mit einem Token ergaenzen.
MCP_SERVER = {
    "type": "mcp",
    "server_label": "microsoft_learn",
    "server_url": "https://learn.microsoft.com/api/mcp",
    "require_approval": "never",
    # "headers": {"Authorization": "Bearer ..."},
    # "allowed_tools": ["microsoft_docs_search"],   # Angriffsflaeche verkleinern
}


def main() -> None:
    header("MCP via Responses API")

    client = get_openai_client(api_version="2025-04-01-preview")

    try:
        response = client.responses.create(
            model=settings.model_deployment,
            tools=[MCP_SERVER],
            input="Welche Tool-Typen unterstuetzt das Azure AI Agent Service? "
                  "Nutze die Doku-Suche und nenne die Quelle.",
        )
    except Exception as exc:
        warn(f"Fehlgeschlagen: {exc}")
        warn("MCP-Tools brauchen eine aktuelle API-Version und ein unterstuetztes Deployment.")
        return

    # Der Output enthaelt neben der Antwort auch die MCP-Aufrufe - gut zum Debuggen.
    for item in response.output:
        kind = getattr(item, "type", "")
        if kind == "mcp_list_tools":
            names = [t.name for t in getattr(item, "tools", [])]
            info(f"  Server meldet Tools: {', '.join(names) or '-'}")
        elif kind == "mcp_call":
            info(f"  -> {item.name}({str(item.arguments)[:120]})")
        elif kind == "mcp_approval_request":
            warn(f"  Freigabe angefordert fuer {item.name} - require_approval pruefen.")

    answer("\n" + response.output_text)


if __name__ == "__main__":
    main()
