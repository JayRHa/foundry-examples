"""05 - Streaming mit Event-Handler: sehen, was der Agent gerade tut.

    python 03_agents/05_streaming_events.py

`create_and_process` ist bequem, aber eine Blackbox: du wartest, bis alles fertig
ist. Fuer eine UI willst du den Zwischenstand - "sucht in Dokumenten", "fuehrt
Code aus", dann die Tokens.

Der EventHandler ist genau die Schicht, die man spaeter an WebSocket oder SSE
haengt (siehe 05_apps/fastapi_chat_api.py).
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from azure.ai.agents.models import (
    AgentEventHandler,
    MessageDeltaChunk,
    RunStep,
    ThreadMessage,
    ThreadRun,
)

from common import get_agents_client, header, info, settings, stream_token, warn


class ConsoleHandler(AgentEventHandler):
    """Uebersetzt den Event-Strom in etwas, das ein Mensch lesen kann."""

    def on_message_delta(self, delta: MessageDeltaChunk) -> None:
        # Der eigentliche Text, Token fuer Token.
        if delta.text:
            stream_token(delta.text)

    def on_thread_run(self, run: ThreadRun) -> None:
        if run.status == "failed":
            warn(f"\n[run failed] {run.last_error}")
        else:
            info(f"\n[run {run.status}]")

    def on_run_step(self, step: RunStep) -> None:
        # Hier sieht man Tool-Nutzung, bevor die Antwort kommt.
        if step.type == "tool_calls" and step.status == "in_progress":
            info("[Agent nutzt ein Tool ...]")

    def on_thread_message(self, message: ThreadMessage) -> None:
        if message.status == "completed" and message.role == "assistant":
            print()  # Zeilenumbruch nach der fertigen Antwort

    def on_error(self, data: str) -> None:
        warn(f"[stream error] {data}")

    def on_unhandled_event(self, event_type: str, event_data) -> None:
        pass  # bewusst still - sonst rauscht die Konsole zu


def main() -> None:
    header("Streaming Agent Run")

    agents = get_agents_client()
    agent = agents.create_agent(
        model=settings.agent_model_deployment,
        name="foundry-demo-stream",
        instructions="Antworte auf Deutsch, strukturiert, mit kurzen Absaetzen.",
    )
    thread = agents.threads.create()

    try:
        agents.messages.create(
            thread_id=thread.id,
            role="user",
            content="Erklaere den Unterschied zwischen Thread, Run und Run Step im Agent Service.",
        )

        with agents.runs.stream(
            thread_id=thread.id, agent_id=agent.id, event_handler=ConsoleHandler()
        ) as stream:
            stream.until_done()

    finally:
        agents.threads.delete(thread.id)
        agents.delete_agent(agent.id)


if __name__ == "__main__":
    main()
