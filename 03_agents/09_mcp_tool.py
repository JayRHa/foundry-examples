"""09 - MCP-Server als Agent-Tool, inklusive Freigabe-Workflow.

    python 03_agents/09_mcp_tool.py

Anders als in 02_tools/03 laeuft das hier im Agent Service: der Dienst spricht
mit dem MCP-Server. Interessant ist der Approval-Pfad - der Run bleibt bei
`requires_action` stehen, bis du zustimmst. Genau dort haengt man in einer
echten Anwendung eine Rueckfrage an die Nutzerin.

Sicherheit: MCP-Server liefern Tool-Beschreibungen, die das Modell liest. Ein
boesartiger Server kann dort Anweisungen platzieren. Deshalb: nur vertrauens-
wuerdige Server, `allowed_tools` einschraenken, Schreibaktionen nur mit Freigabe.
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from azure.ai.agents.models import (
    McpTool,
    RequiredMcpToolCall,
    SubmitToolApprovalAction,
    ToolApproval,
)

from common import answer, get_agents_client, header, info, settings, warn

AUTO_APPROVE = False  # bewusst an: zeigt den Freigabe-Pfad


def main() -> None:
    header("MCP Tool im Agent Service")

    agents = get_agents_client()

    mcp = McpTool(
        server_label="microsoft_learn",
        server_url="https://learn.microsoft.com/api/mcp",
        allowed_tools=[],  # leer = alle; in Produktion explizit auflisten
    )
    mcp.set_approval_mode("never" if AUTO_APPROVE else "always")

    agent = agents.create_agent(
        model=settings.agent_model_deployment,
        name="foundry-demo-mcp",
        instructions="Nutze die Doku-Suche und antworte auf Deutsch mit Quellenangabe.",
        tools=mcp.definitions,
    )
    thread = agents.threads.create()

    try:
        agents.messages.create(
            thread_id=thread.id,
            role="user",
            content="Wie richte ich eine Managed Identity fuer eine Azure Function ein?",
        )

        # Nicht create_and_process: wir brauchen die Kontrolle ueber requires_action.
        run = agents.runs.create(
            thread_id=thread.id, agent_id=agent.id, tool_resources=mcp.resources
        )

        while run.status in ("queued", "in_progress", "requires_action"):
            time.sleep(1)
            run = agents.runs.get(thread_id=thread.id, run_id=run.id)

            if run.status != "requires_action":
                continue
            action = run.required_action
            if not isinstance(action, SubmitToolApprovalAction):
                warn(f"Unerwartete Aktion: {type(action).__name__}")
                break

            approvals = []
            for call in action.submit_tool_approval.tool_calls:
                if not isinstance(call, RequiredMcpToolCall):
                    continue
                # Hier wuerde in einer App die Rueckfrage an die Nutzerin stehen.
                info(f"  Freigabe angefragt: {call.name}")
                approvals.append(
                    ToolApproval(tool_call_id=call.id, approve=True, headers=mcp.headers)
                )

            if approvals:
                run = agents.runs.submit_tool_outputs(
                    thread_id=thread.id, run_id=run.id, tool_approvals=approvals
                )

        info(f"Run: {run.status}")
        if run.status == "failed":
            warn(f"Fehler: {run.last_error}")
            return

        message = agents.messages.get_last_message_by_role(thread_id=thread.id, role="assistant")
        answer("\n" + message.text_messages[-1].text.value)

    finally:
        agents.threads.delete(thread.id)
        agents.delete_agent(agent.id)


if __name__ == "__main__":
    main()
