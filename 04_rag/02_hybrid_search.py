"""02 - Hybride Suche + Antwort mit Belegen.

    python 04_rag/02_hybrid_search.py "Deine Frage"

Der komplette RAG-Zyklus von Hand:
  Frage -> embedden -> hybrid suchen (BM25 + Vektor) -> semantisch reranken
        -> Top-K in den Prompt -> Antwort mit Quellenangabe.

Warum hybrid? Vektorsuche findet Bedeutung, verliert aber exakte Begriffe -
Produktnummern, Fehlercodes, Eigennamen. BM25 findet genau die. Die Kombination
ist robuster als beides einzeln, und der Semantic Ranker sortiert am Ende nach
tatsaechlicher Relevanz zur Frage.

Die harte Regel im System-Prompt ("nur aus dem Kontext") ist der Unterschied
zwischen einem RAG-System und einem Modell, das Quellen dekoriert.
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from azure.search.documents.models import QueryType, VectorizedQuery

from common import answer, get_openai_client, get_search_client, header, info, settings

TOP_K = 4

# Nummerierte Quellen statt Dateinamen: Modelle setzen [1] deutlich zuverlaessiger
# als [handbuch.md#handbuch-3]. Die Zuordnung Nummer -> Datei macht der Code danach.
SYSTEM_PROMPT = """Du beantwortest Fragen ausschliesslich anhand der nummerierten Quellen.

Regeln:
- Steht die Antwort nicht in den Quellen, antworte exakt: Das steht nicht in den Unterlagen.
- Setze hinter jeden Satz die Nummer der Quelle in eckigen Klammern, z.B. [2].
  Ohne diese Nummern ist die Antwort unbrauchbar.
- Erfinde nichts und kombiniere nicht ueber das hinaus, was dasteht.
- Antworte auf Deutsch und kompakt."""


def retrieve(question: str) -> list[dict]:
    openai_client = get_openai_client()
    search_client = get_search_client()

    embedding = (
        openai_client.embeddings.create(
            model=settings.embedding_deployment, input=[question], dimensions=1536
        )
        .data[0]
        .embedding
    )

    results = search_client.search(
        search_text=question,  # BM25-Anteil
        vector_queries=[
            VectorizedQuery(vector=embedding, k_nearest_neighbors=TOP_K * 3, fields="content_vector")
        ],
        query_type=QueryType.SEMANTIC,  # Reranking
        semantic_configuration_name="semantic-config",
        select=["id", "content", "source", "section"],
        top=TOP_K,
    )

    return [
        {
            "id": r["id"],
            "content": r["content"],
            "source": r["source"],
            "section": r["section"],
            "score": r.get("@search.reranker_score") or r["@search.score"],
        }
        for r in results
    ]


def main() -> None:
    header("Hybride Suche + RAG-Antwort")

    question = " ".join(sys.argv[1:]) or "Welche Freigaben braucht eine IAM-Aenderung?"
    info(f"Frage: {question}\n")

    hits = retrieve(question)
    if not hits:
        info("Keine Treffer - wurde 04_rag/01_build_index.py schon ausgefuehrt?")
        return

    for hit in hits:
        info(f"  [{hit['score']:.2f}] {hit['source']}#{hit['id']} - {hit['section']}")

    context = "\n\n".join(
        f"QUELLE [{number}] ({hit['source']} / {hit['section']})\n{hit['content']}"
        for number, hit in enumerate(hits, 1)
    )

    response = get_openai_client().chat.completions.create(
        model=settings.model_deployment,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"KONTEXT:\n{context}\n\nFRAGE: {question}"},
        ],
        max_completion_tokens=4000,
    )

    text = response.choices[0].message.content
    answer("\n" + text)

    # Zitatnummern zurueck auf Dateien abbilden - das ist der Teil, den die UI braucht.
    used = sorted({int(n) for n in re.findall(r"\[(\d+)\]", text)})
    if used:
        info("\nZitierte Quellen:")
        for number in used:
            hit = hits[number - 1]
            info(f"  [{number}] {hit['source']} / {hit['section']}")
    else:
        info("\n(Keine Zitate gesetzt - bei einer Nicht-Antwort ist das korrekt.)")


if __name__ == "__main__":
    main()
