"""05 - Embeddings und semantische Aehnlichkeit.

    python 01_basics/05_embeddings.py

Die Grundlage jedes RAG-Systems: Text -> Vektor, Aehnlichkeit -> Skalarprodukt.
Azure-OpenAI-Embeddings sind bereits L2-normalisiert, deshalb genuegt das
Skalarprodukt - keine Division durch die Normen noetig.

`dimensions` kuerzt den Vektor (Matryoshka). 1536 -> 512 spart Index-Speicher
und Suchzeit bei meist nur geringem Qualitaetsverlust: unbedingt messen.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import get_openai_client, header, info, settings

CORPUS = [
    "Ein Modell-Deployment macht ein Modell unter einem eigenen Namen aufrufbar.",
    "Der Onboarding-Prozess fuer neue Mitarbeitende dauert zwei Wochen.",
    "Connections verknuepfen externe Ressourcen wie Azure AI Search mit dem Projekt.",
    "Die Kantine hat montags bis freitags von 11:30 bis 14:00 geoeffnet.",
]
QUERY = "Wie binde ich meinen Suchindex an das Foundry-Projekt an?"


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def main() -> None:
    header("Embeddings")

    client = get_openai_client()

    # Batching: alle Texte in einem Request - deutlich schneller und guenstiger
    # als eine Schleife mit Einzelaufrufen.
    result = client.embeddings.create(
        model=settings.embedding_deployment,
        input=[QUERY, *CORPUS],
        dimensions=512,
    )
    vectors = [item.embedding for item in result.data]
    query_vec, corpus_vecs = vectors[0], vectors[1:]

    info(f"Dimensionen: {len(query_vec)} | Tokens: {result.usage.total_tokens}\n")
    info(f"Query: {QUERY}\n")

    ranked = sorted(
        ((dot(query_vec, vec), text) for vec, text in zip(corpus_vecs, CORPUS)),
        reverse=True,
    )
    for score, text in ranked:
        info(f"  {score:+.3f}  {text}")


if __name__ == "__main__":
    main()
