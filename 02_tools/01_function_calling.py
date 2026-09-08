"""01 - Function Calling von Hand: der Tool-Loop, den jedes Agent-Framework kapselt.

    python 02_tools/01_function_calling.py

Ablauf:
  user -> Modell -> tool_calls -> du fuehrst aus -> Ergebnis als role="tool"
  zurueck -> Modell -> finale Antwort.

Einmal von Hand gebaut zu haben lohnt sich: danach ist klar, was das Agent
Service (03_agents/) einem tatsaechlich abnimmt und wo man debuggen muss.
"""

import json
import pathlib
import sys
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import answer, get_openai_client, header, info, settings

# --- 1. Die eigentlichen Funktionen ----------------------------------------

STOCK = {"laptop-14": 42, "laptop-16": 0, "dock-usbc": 7}


def get_inventory(sku: str) -> dict:
    return {"sku": sku, "available": STOCK.get(sku, 0), "checked_at": str(date.today())}


def create_restock_order(sku: str, quantity: int) -> dict:
    if quantity <= 0:
        return {"error": "quantity muss > 0 sein"}
    return {"order_id": f"RO-{date.today():%Y%m%d}-{sku}", "sku": sku, "quantity": quantity}


TOOL_IMPLEMENTATIONS = {
    "get_inventory": get_inventory,
    "create_restock_order": create_restock_order,
}

# --- 2. Die Schemas, die das Modell sieht ----------------------------------
# `strict: True` + `additionalProperties: False` erzwingen, dass die Argumente
# exakt dem Schema entsprechen. Ohne das darfst du jeden Aufruf selbst validieren.

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_inventory",
            "description": "Liefert den aktuellen Lagerbestand fuer eine SKU.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string", "description": "Artikelnummer, z.B. 'laptop-14'"}
                },
                "required": ["sku"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_restock_order",
            "description": "Legt eine Nachbestellung an. Nur nutzen, wenn der Bestand 0 ist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string"},
                    "quantity": {"type": "integer", "description": "Stueckzahl, > 0"},
                },
                "required": ["sku", "quantity"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
]


def main() -> None:
    header("Function Calling (manueller Loop)")

    client = get_openai_client()
    messages = [
        {"role": "system", "content": "Du verwaltest ein Lager. Nutze die Tools, rate nie Bestaende."},
        {"role": "user", "content": "Ist laptop-16 auf Lager? Falls nicht, bestelle 25 Stueck nach."},
    ]

    for turn in range(1, 6):  # harte Obergrenze gegen Endlosschleifen
        response = client.chat.completions.create(
            model=settings.model_deployment,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_completion_tokens=4000,
        )
        message = response.choices[0].message
        messages.append(message)

        if not message.tool_calls:
            answer(message.content)
            info(f"\nFertig nach {turn} Modellaufruf(en).")
            return

        for call in message.tool_calls:
            args = json.loads(call.function.arguments)
            info(f"  -> {call.function.name}({args})")

            fn = TOOL_IMPLEMENTATIONS.get(call.function.name)
            # Fehler NICHT werfen, sondern zurueckgeben: das Modell kann sich korrigieren.
            try:
                result = fn(**args) if fn else {"error": f"unbekanntes Tool {call.function.name}"}
            except Exception as exc:
                result = {"error": f"{type(exc).__name__}: {exc}"}

            info(f"  <- {result}")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,  # muss exakt zugeordnet werden
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    info("Maximale Anzahl an Runden erreicht.")


if __name__ == "__main__":
    main()
