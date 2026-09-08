"""02 - Eigene Python-Funktionen als Agent-Tools.

    python 03_agents/02_agent_function_tools.py

`FunctionTool` erzeugt die Schemas aus Signatur und Docstring, `ToolSet` buendelt
mehrere Tools, `enable_auto_function_calls` sorgt dafuer, dass das SDK die
Aufrufe waehrend `create_and_process` selbst ausfuehrt.

Wichtig: Die Funktionen laufen in *deinem* Prozess, nicht in der Cloud. Das
Modell liefert nur die Argumente - Validierung und Rechtepruefung bleiben deine
Aufgabe. Deshalb hier bewusst mit Guard im Code, nicht nur im Prompt.
"""

import json
import pathlib
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from azure.ai.agents.models import FunctionTool, ToolSet

from common import answer, get_agents_client, header, info, settings, warn

MAX_REFUND_EUR = 200.0


def get_order(order_id: str) -> str:
    """Liefert Bestelldetails. order_id hat die Form 'ORD-1234'."""
    orders = {
        "ORD-1001": {"total_eur": 149.0, "status": "delivered", "days_since_delivery": 5},
        "ORD-1002": {"total_eur": 899.0, "status": "delivered", "days_since_delivery": 40},
    }
    return json.dumps(orders.get(order_id, {"error": "unbekannte Bestellung"}))


def issue_refund(order_id: str, amount_eur: float, reason: str) -> str:
    """Erstattet einen Betrag fuer eine Bestellung. Nur nach Ruecksprache nutzen."""
    # Die Grenze gehoert in den Code, nicht in die Instructions: ein Prompt
    # laesst sich ueberreden, ein if nicht.
    if amount_eur > MAX_REFUND_EUR:
        return json.dumps(
            {"approved": False, "reason": f"Betraege ueber {MAX_REFUND_EUR} EUR brauchen Freigabe."}
        )
    return json.dumps(
        {
            "approved": True,
            "refund_id": f"RF-{order_id}",
            "amount_eur": amount_eur,
            "reason": reason,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )


def main() -> None:
    header("Agent mit Function Tools")

    agents = get_agents_client()

    toolset = ToolSet()
    toolset.add(FunctionTool({get_order, issue_refund}))
    # Ohne diese Zeile bleibt der Run bei "requires_action" stehen.
    agents.enable_auto_function_calls(toolset)

    agent = agents.create_agent(
        model=settings.agent_model_deployment,
        name="foundry-demo-support",
        instructions=(
            "Du bist im Kundenservice. Pruefe Bestellungen immer mit get_order, bevor du "
            "eine Erstattung veranlasst. Erstatte nie mehr als den Bestellwert. "
            "Erklaere dem Kunden das Ergebnis in einem Satz."
        ),
        toolset=toolset,
    )
    thread = agents.threads.create()

    try:
        for question in [
            "Bestellung ORD-1001 kam beschaedigt an. Bitte erstatten.",
            "Und fuer ORD-1002 haette ich auch gern eine volle Erstattung.",
        ]:
            agents.messages.create(thread_id=thread.id, role="user", content=question)
            run = agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
            if run.status == "failed":
                warn(f"Run fehlgeschlagen: {run.last_error}")
                continue

            # Run Steps zeigen, welche Tools mit welchen Argumenten liefen -
            # das ist der wichtigste Debug-Einstieg bei Agents.
            for step in agents.run_steps.list(thread_id=thread.id, run_id=run.id):
                details = step.get("step_details", {})
                for call in details.get("tool_calls", []):
                    fn = call.get("function", {})
                    if fn:
                        info(f"  -> {fn.get('name')}({fn.get('arguments')})")

            last = agents.messages.get_last_message_text_by_role(
                thread_id=thread.id, role="assistant"
            )
            answer(f"\nFRAGE : {question}\nANTWORT: {last.text.value}\n")

    finally:
        agents.threads.delete(thread.id)
        agents.delete_agent(agent.id)


if __name__ == "__main__":
    main()
