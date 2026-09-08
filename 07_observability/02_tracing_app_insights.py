"""02 - Dieselben Traces nach Application Insights.

    python 07_observability/02_tracing_app_insights.py

Ein Foundry-Projekt kann mit einer Application-Insights-Ressource verbunden
sein. Dann holt man den Connection String aus dem Projekt statt ihn in die
Konfiguration zu kopieren - eine Konfigurationsquelle weniger.

Danach im Portal sichtbar unter Foundry -> Tracing bzw. in Azure Monitor.
Nuetzliche KQL-Abfragen stehen unten in diesem Modul.

Was man damit tatsaechlich beantwortet:
  - Welche Anfragen dauern am laengsten und warum (Modell oder Tool)?
  - Welcher Tool-Aufruf schlaegt am haeufigsten fehl?
  - Wie verteilen sich Tokens/Kosten ueber Use Cases (dank eigener Attribute)?
"""

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

os.environ.setdefault("AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED", "true")

from azure.core.settings import settings as azure_settings
from opentelemetry import trace

from common import get_agents_client, get_project_client, header, info, settings, warn

# Alle drei Abfragen sind gegen echte Daten aus diesem Beispiel geprueft.
# Zwei Fallen, die man erst beim Ausprobieren merkt:
#   - Das Attribut heisst gen_ai.usage.input_tokens / .output_tokens.
#     Ein "total_tokens" gibt es nicht.
#   - Eigene Attribute (app.use_case) sitzen auf DEINEM Span, die Token-Zahlen
#     auf den SDK-Kindspans. Ohne join ueber operation_Id bleibt die Auswertung leer.
KQL_EXAMPLES = """
// 1) Langsamste GenAI-Operationen - wo geht die Zeit hin?
dependencies
| where timestamp > ago(24h) and isnotempty(tostring(customDimensions["gen_ai.operation.name"]))
| extend op = tostring(customDimensions["gen_ai.operation.name"])
| summarize p50 = percentile(duration, 50), p95 = percentile(duration, 95), n = count() by op
| order by p95 desc

// 2) Run-Status-Verteilung - wie viele Runs scheitern?
dependencies
| where timestamp > ago(24h) and isnotempty(tostring(customDimensions["gen_ai.thread.run.status"]))
| summarize n = count() by status = tostring(customDimensions["gen_ai.thread.run.status"])

// 3) Token-Verbrauch pro Use Case - der join ist hier der Kern
dependencies
| where timestamp > ago(24h)
| extend inTok  = toint(customDimensions["gen_ai.usage.input_tokens"]),
         outTok = toint(customDimensions["gen_ai.usage.output_tokens"])
| where isnotnull(inTok)
| join kind=leftouter (
    dependencies
    | where isnotempty(tostring(customDimensions["app.use_case"]))
    | project operation_Id, use_case = tostring(customDimensions["app.use_case"])
  ) on operation_Id
| summarize input_tokens = sum(inTok), output_tokens = sum(outTok), calls = count()
        by use_case = coalesce(use_case, "(ohne Attribut)")
| order by input_tokens desc
"""


def connection_string() -> str | None:
    if settings.app_insights_connection_string:
        return settings.app_insights_connection_string

    # Aus dem Projekt holen - der Methodenname unterscheidet sich je SDK-Version.
    telemetry = get_project_client().telemetry
    for attribute in ("get_application_insights_connection_string", "get_connection_string"):
        getter = getattr(telemetry, attribute, None)
        if getter:
            try:
                return getter()
            except Exception as exc:
                warn(f"{attribute}() fehlgeschlagen: {exc}")
    return None


def main() -> None:
    header("Tracing nach Application Insights")

    conn = connection_string()
    if not conn:
        warn("Keine Application-Insights-Verbindung gefunden.")
        warn("Im Foundry-Portal unter 'Tracing' eine Ressource verbinden oder")
        warn("APPLICATIONINSIGHTS_CONNECTION_STRING in .env setzen.")
        info("\nKQL-Abfragen fuer spaeter:" + KQL_EXAMPLES)
        return

    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor(connection_string=conn)

    # Wie in 01: ohne die azure-core-Bruecke kommen nur die eigenen Spans an.
    azure_settings.tracing_implementation = "opentelemetry"

    try:
        from azure.ai.agents.telemetry import AIAgentsInstrumentor

        AIAgentsInstrumentor().instrument()
    except ImportError:
        warn("azure.ai.agents.telemetry fehlt - Agent-Spans werden nicht erfasst.")

    tracer = trace.get_tracer(__name__)
    agents = get_agents_client()

    with tracer.start_as_current_span("faq-anfrage") as span:
        # Eigene Attribute sind das, was die Traces spaeter auswertbar macht:
        # ohne sie hast du Spans, aber keine Dimensionen zum Gruppieren.
        span.set_attribute("app.use_case", "faq")
        span.set_attribute("app.tenant", "demo")

        agent = agents.create_agent(
            model=settings.agent_model_deployment,
            name="foundry-demo-appinsights",
            instructions="Antworte in einem Satz auf Deutsch.",
        )
        thread = agents.threads.create()
        try:
            agents.messages.create(
                thread_id=thread.id,
                role="user",
                content="Wozu dient Application Insights bei Agent-Anwendungen?",
            )
            run = agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
            info(f"Run: {run.status}")
        finally:
            agents.threads.delete(thread.id)
            agents.delete_agent(agent.id)

    info("Traces gesendet. Sichtbar im Portal nach 1-3 Minuten.")
    info("\nKQL-Abfragen:" + KQL_EXAMPLES)


if __name__ == "__main__":
    main()
