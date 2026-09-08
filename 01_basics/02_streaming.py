"""02 - Streaming: Tokens ausgeben, sobald sie da sind.

    python 01_basics/02_streaming.py

Fuer alles mit UI ist das der Default. Wichtig: `stream_options` anfordern,
sonst kommt am Ende kein Usage-Objekt und du fliegst im Kosten-Reporting blind.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import get_openai_client, header, info, settings, stream_token


def main() -> None:
    header("Streaming Chat Completion")

    client = get_openai_client()

    stream = client.chat.completions.create(
        model=settings.model_deployment,
        messages=[
            {"role": "system", "content": "Du erklaerst knapp und mit konkreten Beispielen."},
            {"role": "user", "content": "Erklaere in 5 Punkten, wofuer man das Agent Service in Azure AI Foundry nutzt."},
        ],
        stream=True,
        stream_options={"include_usage": True},
    )

    usage = None
    for chunk in stream:
        # Das letzte Usage-Chunk hat eine leere choices-Liste.
        if chunk.usage is not None:
            usage = chunk.usage
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and delta.content:
            stream_token(delta.content)

    print()
    if usage:
        info(f"\nTokens gesamt: {usage.total_tokens}")


if __name__ == "__main__":
    main()
