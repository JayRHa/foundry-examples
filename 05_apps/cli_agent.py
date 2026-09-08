"""Interaktiver CLI-Agent mit sichtbarer Tool-Nutzung.

    python 05_apps/cli_agent.py

Ein Terminal-Assistent, der lokal Dateien lesen und durchsuchen darf. Zeigt das
Muster, auf dem Coding- und Ops-Assistenten aufbauen: das Modell entscheidet,
*welche* Datei es braucht, dein Code entscheidet, *ob* es sie sehen darf.

Der Guard in `_safe_path` ist der wichtigste Teil der Datei. Ohne ihn liest der
Agent bei passendem Prompt ~/.ssh/id_rsa - "greife nicht auf Geheimnisse zu"
in den Instructions ist keine Sicherheitsmassnahme.

Befehle: /reset (neuer Thread), /exit
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from azure.ai.agents.models import FunctionTool, ToolSet

from common import get_agents_client, header, info, settings, warn

# Der Agent darf ausschliesslich unterhalb dieses Verzeichnisses arbeiten.
ROOT = pathlib.Path(__file__).resolve().parents[1]
MAX_BYTES = 20_000


def _safe_path(relative: str) -> pathlib.Path:
    """Verhindert Ausbruch aus ROOT (../.., Symlinks, absolute Pfade)."""
    candidate = (ROOT / relative).resolve()
    if not candidate.is_relative_to(ROOT):
        raise PermissionError(f"Pfad ausserhalb des erlaubten Bereichs: {relative}")
    return candidate


def list_files(subdirectory: str = ".") -> str:
    """Listet Dateien in einem Unterverzeichnis des Projekts auf."""
    base = _safe_path(subdirectory)
    entries = [
        str(p.relative_to(ROOT))
        for p in sorted(base.rglob("*"))
        if p.is_file() and not any(part.startswith((".", "__")) for part in p.parts)
    ]
    return json.dumps(entries[:200])


def read_file(path: str) -> str:
    """Liest eine Textdatei aus dem Projekt. path ist relativ zum Projektwurzelverzeichnis."""
    target = _safe_path(path)
    if not target.is_file():
        return json.dumps({"error": "Datei nicht gefunden"})
    return json.dumps({"path": path, "content": target.read_text(encoding="utf-8")[:MAX_BYTES]})


def search_text(pattern: str) -> str:
    """Sucht eine Zeichenkette in allen .py- und .md-Dateien des Projekts."""
    hits = []
    for path in ROOT.rglob("*"):
        if path.suffix not in {".py", ".md"} or not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if pattern.lower() in line.lower():
                hits.append({"file": str(path.relative_to(ROOT)), "line": number, "text": line.strip()[:160]})
        if len(hits) > 60:
            break
    return json.dumps(hits[:60])


def main() -> None:
    header("CLI-Agent (Projektassistent)")
    info(f"Arbeitsverzeichnis: {ROOT}\nBefehle: /reset, /exit\n")

    agents = get_agents_client()
    toolset = ToolSet()
    toolset.add(FunctionTool({list_files, read_file, search_text}))
    agents.enable_auto_function_calls(toolset)

    agent = agents.create_agent(
        model=settings.agent_model_deployment,
        name="foundry-demo-cli",
        instructions=(
            "Du bist ein Assistent fuer dieses Code-Projekt. Nutze die Tools, um "
            "Dateien zu finden und zu lesen, bevor du antwortest. Rate nie den Inhalt "
            "einer Datei. Antworte auf Deutsch und nenne Dateipfade."
        ),
        toolset=toolset,
    )
    thread = agents.threads.create()

    try:
        while True:
            try:
                prompt = input("\nDu > ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not prompt:
                continue
            if prompt == "/exit":
                break
            if prompt == "/reset":
                agents.threads.delete(thread.id)
                thread = agents.threads.create()
                info("Neuer Thread.")
                continue

            agents.messages.create(thread_id=thread.id, role="user", content=prompt)

            with agents.runs.stream(thread_id=thread.id, agent_id=agent.id) as stream:
                print("Agent > ", end="", flush=True)
                for event_type, event_data, _ in stream:
                    if event_type == "thread.message.delta":
                        for part in event_data.delta.content or []:
                            if getattr(part, "text", None):
                                print(part.text.value, end="", flush=True)
                    elif event_type == "thread.run.step.created":
                        if getattr(event_data, "type", "") == "tool_calls":
                            info("[nutzt Tools ...]")
                    elif event_type == "thread.run.failed":
                        warn(f"\n{event_data.last_error}")
                print()

    finally:
        agents.threads.delete(thread.id)
        agents.delete_agent(agent.id)
        info("\nAufgeraeumt.")


if __name__ == "__main__":
    main()
