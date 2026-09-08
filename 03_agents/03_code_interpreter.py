"""03 - Code Interpreter: der Agent rechnet und plottet selbst.

    python 03_agents/03_code_interpreter.py

Das Modell schreibt Python, das in einer Sandbox in der Cloud ausgefuehrt wird.
Ideal fuer Datenanalysen, bei denen du das Ergebnis brauchst und nicht die
Halluzination einer Rechnung.

Zwei Dinge, die man leicht uebersieht:
  - Die hochgeladene Datei muss dem Agent (oder dem Thread) ueber `tool_resources`
    zugeordnet werden, sonst "sieht" der Code sie nicht.
  - Erzeugte Bilder kommen als image_file zurueck und muessen separat
    heruntergeladen werden.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from azure.ai.agents.models import CodeInterpreterTool, FilePurpose, ListSortOrder

from common import answer, get_agents_client, header, info, settings, warn

HERE = pathlib.Path(__file__).parent
DATA = HERE / "data" / "sales.csv"
OUT = HERE / "outputs"


def main() -> None:
    header("Code Interpreter")

    agents = get_agents_client()
    OUT.mkdir(exist_ok=True)

    uploaded = agents.files.upload_and_poll(file_path=str(DATA), purpose=FilePurpose.AGENTS)
    info(f"Datei hochgeladen: {uploaded.id}")

    code_tool = CodeInterpreterTool(file_ids=[uploaded.id])

    agent = agents.create_agent(
        model=settings.agent_model_deployment,
        name="foundry-demo-analyst",
        instructions=(
            "Du bist Datenanalyst. Rechne immer mit dem Code Interpreter, nie im Kopf. "
            "Antworte auf Deutsch und nenne konkrete Zahlen."
        ),
        tools=code_tool.definitions,
        tool_resources=code_tool.resources,
    )
    thread = agents.threads.create()

    try:
        agents.messages.create(
            thread_id=thread.id,
            role="user",
            content=(
                "Analysiere sales.csv: Umsatz pro Region und Monat, Wachstum Januar->Juni "
                "in Prozent, und erstelle ein Liniendiagramm des Monatsumsatzes je Region. "
                "Speichere das Diagramm als PNG."
            ),
        )

        run = agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
        if run.status == "failed":
            warn(f"Run fehlgeschlagen: {run.last_error}")
            return

        for message in agents.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING):
            for part in message.text_messages:
                answer(f"{message.role.upper()}: {part.text.value}\n")

            # Vom Code erzeugte Bilder herunterladen.
            for image in message.image_contents:
                file_id = image.image_file.file_id
                agents.files.save(file_id=file_id, file_name=f"{file_id}.png", target_dir=str(OUT))
                info(f"  Bild gespeichert: {OUT / (file_id + '.png')}")

            # Der Agent kann auch Dateien anhaengen (z.B. eine erzeugte CSV).
            for annotation in message.file_path_annotations:
                fid = annotation.file_path.file_id
                name = pathlib.Path(annotation.text).name
                agents.files.save(file_id=fid, file_name=name, target_dir=str(OUT))
                info(f"  Datei gespeichert: {OUT / name}")

    finally:
        agents.threads.delete(thread.id)
        agents.delete_agent(agent.id)
        agents.files.delete(uploaded.id)


if __name__ == "__main__":
    main()
