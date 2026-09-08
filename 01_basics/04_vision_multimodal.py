"""04 - Multimodal: Bilder mit in den Prompt geben.

    python 01_basics/04_vision_multimodal.py [pfad/zum/bild.png]

Zwei Wege, ein Bild zu uebergeben:
  1. data:-URL (base64)    -> funktioniert immer, auch fuer lokale/private Dateien
  2. oeffentliche URL      -> spart Tokens im Request, aber der *Dienst* muss die
                              URL erreichen koennen. Viele Hosts (u.a. Wikimedia)
                              blocken die Azure-Egress-IPs, dann kommt
                              "Failed to download image" zurueck. Deshalb ist
                              base64 hier der Standardweg.

`detail` steuert Kosten: "low" rendert das Bild auf 512x512 herunter und kostet
einen festen, kleinen Tokenbetrag - fuer Klassifikation oft voellig ausreichend.
"""

import base64
import mimetypes
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import answer, get_openai_client, header, info, settings

DEMO_IMAGE = pathlib.Path(__file__).parent / "data" / "demo_chart.png"


def as_data_url(path: pathlib.Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{encoded}"


def main() -> None:
    header("Vision / Multimodal")

    source = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEMO_IMAGE
    image_url = as_data_url(source)
    info(f"Bild: {source.name} ({source.stat().st_size} Bytes als data:-URL)")

    client = get_openai_client()
    response = client.chat.completions.create(
        model=settings.model_deployment,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Beschreibe das Bild in drei Stichpunkten. "
                                "Falls es ein Diagramm ist: welcher Typ, wie viele "
                                "Datenreihen, was faellt auf?",
                    },
                    {"type": "image_url", "image_url": {"url": image_url, "detail": "low"}},
                ],
            }
        ],
        max_completion_tokens=3000,
    )

    answer(response.choices[0].message.content)


if __name__ == "__main__":
    main()
