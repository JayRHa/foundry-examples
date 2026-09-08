"""01 - Tracing auf der Konsole: sehen, was der Agent wirklich getan hat.

    python 07_observability/01_tracing_console.py

Ein Agent-Run ist eine Kette von Modellaufrufen und Tool-Ausfuehrungen. Wenn
etwas schiefgeht, ist die Frage nie "war die Antwort falsch", sondern "an welcher
Stelle". Genau dafuer sind Traces da.

Foundry setzt auf OpenTelemetry mit den GenAI-Semantic-Conventions - dieselben
Spans landen spaeter unveraendert in Application Insights (siehe 02).

AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED=true nimmt auch Prompts und
Antworten in die Spans auf. Sehr nuetzlich beim Entwickeln - in Produktion eine
Datenschutzentscheidung, keine Detailfrage.
"""

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# Muss VOR dem Instrumentieren gesetzt sein.
os.environ.setdefault("AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED", "true")

from azure.core.settings import settings as azure_settings
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

from common import get_agents_client, header, info, settings, warn


def setup_console_tracing() -> None:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)

    # DIE haeufigste Stolperstelle: Ohne diese Zeile instrumentiert man zwar
    # erfolgreich, sieht aber nur die eigenen Spans. Die Azure-SDKs erzeugen ihre
    # Spans ueber azure-core, und azure-core braucht die OpenTelemetry-Bruecke
    # explizit (Paket: azure-core-tracing-opentelemetry).
    azure_settings.tracing_implementation = "opentelemetry"

    try:
        from azure.ai.agents.telemetry import AIAgentsInstrumentor

        AIAgentsInstrumentor().instrument()
        info("Agent-Instrumentierung aktiv.")
    except ImportError:
        warn("azure.ai.agents.telemetry nicht verfuegbar - nur eigene Spans werden ausgegeben.")


def main() -> None:
    header("Tracing (Konsole)")
    setup_console_tracing()

    tracer = trace.get_tracer(__name__)
    agents = get_agents_client()

    # Eigene Spans um den SDK-Spans herum: so sieht man auch die Zeit, die in
    # deinem Code steckt - nicht nur die im Modell.
    with tracer.start_as_current_span("beispiel-anfrage") as span:
        span.set_attribute("app.use_case", "faq")
        span.set_attribute("app.user_tier", "internal")

        agent = agents.create_agent(
            model=settings.agent_model_deployment,
            name="foundry-demo-tracing",
            instructions="Antworte in einem Satz auf Deutsch.",
        )
        thread = agents.threads.create()
        try:
            agents.messages.create(
                thread_id=thread.id, role="user", content="Was ist ein Run Step?"
            )
            run = agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
            span.set_attribute("app.run_status", str(run.status))
        finally:
            agents.threads.delete(thread.id)
            agents.delete_agent(agent.id)

    info("\nOben stehen die Spans als JSON: Namen, Dauer, gen_ai.*-Attribute.")


if __name__ == "__main__":
    main()
