"""02 - Wiederverwendbare Tool-Registry mit paralleler Ausfuehrung.

    python 02_tools/02_tool_registry.py

Das Schema aus Beispiel 01 von Hand zu pflegen skaliert nicht - es laeuft
zwangslaeufig aus der Signatur heraus. Hier erzeugt ein Decorator das
JSON-Schema aus Type Hints und Docstring, und mehrere tool_calls einer Runde
werden parallel ausgefuehrt (Modelle fordern oft 3-5 auf einmal an).

Das Muster deckt ~80% der Faelle ab, in denen man sonst zu einem Framework greift.
"""

import concurrent.futures
import inspect
import json
import pathlib
import sys
import time
from typing import Any, Callable, get_type_hints

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import answer, get_openai_client, header, info, settings

JSON_TYPES: dict[Any, str] = {str: "string", int: "integer", float: "number", bool: "boolean"}


class ToolRegistry:
    def __init__(self) -> None:
        self._fns: dict[str, Callable[..., Any]] = {}
        self._schemas: list[dict] = []

    def tool(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator: Funktion registrieren und Schema aus der Signatur ableiten."""
        hints = get_type_hints(fn)
        signature = inspect.signature(fn)

        properties, required = {}, []
        for name, param in signature.parameters.items():
            properties[name] = {"type": JSON_TYPES.get(hints.get(name, str), "string")}
            if param.default is inspect.Parameter.empty:
                required.append(name)

        self._fns[fn.__name__] = fn
        self._schemas.append(
            {
                "type": "function",
                "function": {
                    "name": fn.__name__,
                    # Der Docstring ist die Beschreibung, die das Modell liest -
                    # er ist damit Teil des Prompts, nicht nur Doku.
                    "description": inspect.getdoc(fn) or "",
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
            }
        )
        return fn

    @property
    def schemas(self) -> list[dict]:
        return self._schemas

    def invoke(self, name: str, arguments: str) -> str:
        try:
            result = self._fns[name](**json.loads(arguments))
        except KeyError:
            result = {"error": f"unbekanntes Tool: {name}"}
        except Exception as exc:
            result = {"error": f"{type(exc).__name__}: {exc}"}
        return json.dumps(result, ensure_ascii=False, default=str)


registry = ToolRegistry()


@registry.tool
def get_weather(city: str) -> dict:
    """Aktuelles Wetter fuer eine Stadt. city ist der deutsche Stadtname."""
    time.sleep(1.0)  # steht fuer einen echten HTTP-Call
    # Normalisieren: das Modell schickt "Zürich", die Tabelle kennt "zuerich".
    # Genau solche Kleinigkeiten kosten in echten Tools die meiste Zeit.
    key = city.strip().lower().translate(str.maketrans({"ü": "ue", "ö": "oe", "ä": "ae", "ß": "ss"}))
    fake = {"zuerich": 12, "berlin": 9, "wien": 14}
    return {"city": city, "temp_c": fake.get(key, 11), "condition": "bewoelkt"}


@registry.tool
def get_train_delay(station: str) -> dict:
    """Durchschnittliche Verspaetung an einem Bahnhof in Minuten."""
    time.sleep(1.0)
    return {"station": station, "avg_delay_min": 4}


def main() -> None:
    header("Tool-Registry mit parallelen Calls")

    client = get_openai_client()
    messages = [
        {"role": "system", "content": "Nutze Tools fuer Fakten. Fasse am Ende kompakt zusammen."},
        {
            "role": "user",
            "content": "Vergleiche Wetter in Zuerich, Berlin und Wien und nenne die "
                       "Verspaetung in Zuerich HB.",
        },
    ]

    for _ in range(5):
        response = client.chat.completions.create(
            model=settings.model_deployment,
            messages=messages,
            tools=registry.schemas,
            max_completion_tokens=4000,
        )
        message = response.choices[0].message
        messages.append(message)

        if not message.tool_calls:
            answer(message.content)
            return

        started = time.perf_counter()
        # Parallel statt sequenziell: bei 4 Calls a 1s spart das ~3 Sekunden.
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = {
                pool.submit(registry.invoke, c.function.name, c.function.arguments): c
                for c in message.tool_calls
            }
            for future in concurrent.futures.as_completed(futures):
                call = futures[future]
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": future.result()}
                )

        info(
            f"  {len(message.tool_calls)} Tool-Calls parallel in "
            f"{time.perf_counter() - started:.2f}s"
        )


if __name__ == "__main__":
    main()
