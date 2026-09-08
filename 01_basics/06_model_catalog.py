"""06 - Model Catalog: nicht-OpenAI-Modelle mit derselben API ansprechen.

    python 01_basics/06_model_catalog.py                  # Standardmodell
    python 01_basics/06_model_catalog.py llama-3.3-70b    # Katalogmodell

Foundry hostet neben OpenAI auch Llama, Mistral, Phi, Cohere, DeepSeek, Grok
und (via Serverless) Anthropic-Modelle. `azure-ai-inference` gibt allen davon
*eine* Schnittstelle: derselbe Code, nur ein anderer Deployment-Name.

Wann was:
  - openai-SDK            -> OpenAI-Modelle, volle Feature-Breite (Responses, Assistants)
  - azure-ai-inference    -> anbieteruebergreifend, ideal fuer A/B-Vergleiche

Wichtige Einschraenkung, die man beim Vergleichen sofort trifft: Die *Aufrufform*
ist einheitlich, die *unterstuetzten Parameter* sind es nicht.

  Llama, Mistral, ...  -> `max_tokens`, `temperature`
  GPT-5-Familie        -> `max_completion_tokens`, kein `temperature`, kein `top_p`

`azure-ai-inference` kennt `max_completion_tokens` nicht als benanntes Argument -
es muss ueber `model_extras` durchgereicht werden. Deshalb probiert das Beispiel
unten beide Formen. Genau diese Fallunterscheidung braucht man in jedem echten
Multi-Modell-Setup.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from azure.ai.inference.models import SystemMessage, UserMessage
from azure.core.exceptions import HttpResponseError

from common import answer, get_inference_client, header, info, settings


def main() -> None:
    header("Model Catalog Inference")

    deployment = sys.argv[1] if len(sys.argv) > 1 else settings.model_deployment
    info(f"Deployment: {deployment}")

    with get_inference_client(model=deployment) as client:
        # Modell-Metadaten - praktisch, um zu pruefen, was wirklich dahintersteckt.
        try:
            model_info = client.get_model_info()
            info(f"Modell: {model_info.model_name} ({model_info.model_provider_name})")
        except Exception as exc:  # nicht jedes Deployment liefert Metadaten
            # Nicht jeder Foundry-Endpoint stellt /info bereit - kein Fehlerfall.
            info(f"(Keine Modell-Metadaten verfuegbar: {type(exc).__name__})")

        messages = [
            SystemMessage("Antworte in genau zwei Saetzen."),
            UserMessage(
                "Warum ist eine einheitliche Inference-API ueber mehrere "
                "Modellanbieter nuetzlich?"
            ),
        ]
        try:
            # Klassische Modelle (Llama, Mistral, Phi, Cohere, ...)
            response = client.complete(messages=messages, temperature=0.3, max_tokens=300)
            info("Parameter: temperature + max_tokens")
        except HttpResponseError as exc:
            if "unsupported_parameter" not in str(exc):
                raise
            # GPT-5-Familie: kein temperature, und max_completion_tokens kennt das
            # SDK nur als Durchreiche-Feld.
            response = client.complete(
                messages=messages, model_extras={"max_completion_tokens": 3000}
            )
            info("Parameter: model_extras[max_completion_tokens] (GPT-5-Familie)")

    answer(response.choices[0].message.content)
    info(f"\nTokens: {response.usage.total_tokens}")


if __name__ == "__main__":
    main()
