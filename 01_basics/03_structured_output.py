"""03 - Structured Output: garantiert valides JSON gegen ein Pydantic-Schema.

    python 01_basics/03_structured_output.py

Das ist der wichtigste Baustein, wenn ein Modell in eine Pipeline schreibt statt
in einen Chat. `parse()` erzwingt das Schema serverseitig (Structured Outputs),
statt nur darum zu bitten - Retry-Schleifen fuer kaputtes JSON entfallen.

Voraussetzung: ein Modell, das Structured Outputs unterstuetzt - die gesamte
GPT-5-Familie tut das, ebenso gpt-4.1 und gpt-4o. Bei azure-ai-projects 1.x
zusaetzlich API-Version >= 2024-08-01-preview; unter 2.x ist der Client
versionslos.
"""

import pathlib
import sys
from enum import Enum

from pydantic import BaseModel, Field

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import get_openai_client, header, info, settings

TICKET = """
Betreff: Rechnung 2024-8871 - Betrag stimmt nicht
Hallo, auf der Rechnung vom 12.03. stehen 3 Lizenzen, wir nutzen aber seit Februar
nur noch 2. Wir haben die Kuendigung damals per Mail bestaetigt bekommen.
Bitte um Korrektur, sonst muessen wir die Zahlung zurueckhalten.
Viele Gruesse, M. Keller, Northwind AG
"""


class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Ticket(BaseModel):
    """Das Schema ist die API-Definition - Docstrings und Field-Beschreibungen
    landen im JSON-Schema und steuern das Modell mit."""

    summary: str = Field(description="Ein Satz, worum es geht.")
    category: str = Field(description="z.B. billing, technical, account, other")
    priority: Priority
    customer_name: str | None
    company: str | None
    mentioned_amounts: list[str] = Field(description="Alle genannten Betraege/Belegnummern.")
    requires_human: bool = Field(description="True, wenn eine Person pruefen muss.")


def main() -> None:
    header("Structured Output")

    client = get_openai_client(api_version="2024-10-21")

    completion = client.beta.chat.completions.parse(
        model=settings.model_deployment,
        messages=[
            {"role": "system", "content": "Extrahiere die Ticketdaten. Rate nichts dazu."},
            {"role": "user", "content": TICKET},
        ],
        response_format=Ticket,
        # Frueher haette hier temperature=0 gestanden. Die GPT-5-Familie laesst das
        # nicht mehr zu - Reproduzierbarkeit kommt jetzt aus dem erzwungenen Schema
        # und einem praezisen Prompt, nicht aus dem Sampling-Parameter.
        max_completion_tokens=4000,
    )

    ticket = completion.choices[0].message.parsed  # bereits ein Ticket-Objekt
    info(ticket.model_dump_json(indent=2))

    # Ab hier ist es normaler Python-Code - kein String-Parsing mehr.
    if ticket.requires_human and ticket.priority is Priority.high:
        info("\n-> Eskalation an das Billing-Team")


if __name__ == "__main__":
    main()
