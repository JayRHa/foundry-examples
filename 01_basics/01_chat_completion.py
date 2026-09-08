"""01 - Der einfachste Aufruf: eine Chat Completion.

    python 01_basics/01_chat_completion.py

Kernidee: Du redest nicht direkt mit einem Endpoint, sondern holst dir vom
Foundry-*Projekt* einen fertig konfigurierten OpenAI-Client. Endpoint, Auth und
API-Version haengen damit an der Projektkonfiguration, nicht am Code.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # Repo-Root fuer `common`

from common import answer, get_openai_client, header, info, settings


def main() -> None:
    header("Chat Completion")

    client = get_openai_client()

    response = client.chat.completions.create(
        model=settings.model_deployment,  # Deployment-Name, nicht Modellname
        messages=[
            {
                "role": "system",
                "content": (
                    "Du bist ein praeziser technischer Assistent. "
                    "Antworte auf Deutsch und in maximal drei Saetzen."
                ),
            },
            {
                "role": "user",
                "content": "Was ist der Unterschied zwischen einem Modell-Deployment "
                           "und einer Connection in Azure AI Foundry?",
            },
        ],
        # Kein `temperature`: die GPT-5-Familie akzeptiert nur den Default (1).
        # Und `max_tokens` heisst hier `max_completion_tokens` - es deckt auch die
        # unsichtbaren Reasoning-Tokens ab, siehe 01_basics/08.
        max_completion_tokens=2000,
    )

    answer(response.choices[0].message.content)

    # Token-Verbrauch steht in jeder Antwort - die Basis fuer jedes Kosten-Monitoring.
    usage = response.usage
    info(
        f"\nDeployment: {settings.model_deployment} | "
        f"Prompt: {usage.prompt_tokens} | Completion: {usage.completion_tokens} | "
        f"Gesamt: {usage.total_tokens}"
    )


if __name__ == "__main__":
    main()
