"""01 - RAG-Index in Azure AI Search bauen: chunken, embedden, hochladen.

    python 04_rag/01_build_index.py

Wenn File Search (03_agents/04) nicht reicht, baut man den Index selbst. Dieses
Skript zeigt die drei Entscheidungen, die die Qualitaet bestimmen:

  1. Chunking      - hier absatzweise mit Ueberlappung. Zu grosse Chunks
                     verwaessern das Embedding, zu kleine verlieren Kontext.
  2. Felder        - Metadaten (source, section) sind kein Beiwerk: sie
                     ermoeglichen Filter (Mandant, Sprache, Gueltigkeit) und
                     saubere Zitate.
  3. Suchprofil    - HNSW fuer Vektoren + Semantic Ranker fuer das Reranking.
                     Hybrid (Text + Vektor) schlaegt in der Praxis fast immer
                     reine Vektorsuche.
  4. Vectorizer    - der Suchdienst embedded Suchanfragen selbst. Ohne ihn muss
                     jeder Aufrufer die Query vorher embedden, und das
                     AzureAISearchTool des Agents (04_rag/03) lehnt den Index
                     mit "requires a vector field with integrated vectorizer" ab.

Das Skript ist idempotent: der Index wird bei jedem Lauf neu erstellt.
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

from common import get_credential, get_openai_client, get_search_client, header, info, settings

DOCS_DIR = pathlib.Path(__file__).parent.parent / "03_agents" / "data"
EMBED_DIMS = 1536
CHUNK_CHARS = 700
OVERLAP_CHARS = 120


def chunk(text: str, size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[tuple[str, str]]:
    """Schneidet an Markdown-Ueberschriften und gibt (Abschnitt, Text) zurueck.

    Warum nicht stur nach Zeichen? Ein Schnitt mitten im Satz zerstoert genau die
    Bedeutung, die das Embedding einfangen soll - und der Abschnittstitel, der
    spaeter im Zitat steht, wird unbrauchbar ("R an Cloud-Kosten ohne ...").

    An Ueberschriften zu schneiden ist die billigste Verbesserung mit dem
    groessten Effekt. Erst wenn ein Abschnitt zu gross wird, greift der
    Zeichen-Split - und der respektiert Satzgrenzen und ueberlappt am Wortende.
    """
    sections: list[tuple[str, list[str]]] = []
    current_heading = "Einleitung"
    buffer: list[str] = []

    for line in text.splitlines():
        if line.startswith("#"):
            if buffer:
                sections.append((current_heading, buffer))
            current_heading = line.lstrip("#").strip()
            buffer = []
        else:
            buffer.append(line)
    if buffer:
        sections.append((current_heading, buffer))

    chunks: list[tuple[str, str]] = []
    for heading, lines in sections:
        body = "\n".join(lines).strip()
        if not body:
            continue
        if len(body) <= size:
            chunks.append((heading, f"{heading}\n\n{body}"))
            continue

        # Zu grosser Abschnitt: an Satzgrenzen splitten, am Wortende ueberlappen.
        sentences = re.split(r"(?<=[.!?])\s+", body)
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) + 1 <= size:
                current = f"{current} {sentence}".strip()
            else:
                if current:
                    chunks.append((heading, f"{heading}\n\n{current}"))
                tail = current[-overlap:]
                tail = tail[tail.find(" ") + 1 :] if " " in tail else ""
                current = f"{tail} {sentence}".strip()
        if current:
            chunks.append((heading, f"{heading}\n\n{current}"))

    return chunks


def build_index() -> None:
    client = SearchIndexClient(endpoint=settings.require_search_endpoint(), credential=get_credential())

    index = SearchIndex(
        name=settings.search_index,
        fields=[
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="de.microsoft"),
            SimpleField(name="source", type=SearchFieldDataType.String, filterable=True, facetable=True),
            SearchableField(name="section", type=SearchFieldDataType.String),
            SearchField(
                name="content_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=EMBED_DIMS,
                vector_search_profile_name="hnsw-profile",
            ),
        ],
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
            profiles=[
                VectorSearchProfile(
                    name="hnsw-profile",
                    algorithm_configuration_name="hnsw-config",
                    vectorizer_name="openai-vectorizer",
                )
            ],
            # Der Suchdienst ruft das Embedding-Deployment selbst auf - per
            # Managed Identity, deshalb steht hier kein Key.
            vectorizers=[
                AzureOpenAIVectorizer(
                    vectorizer_name="openai-vectorizer",
                    parameters=AzureOpenAIVectorizerParameters(
                        resource_url=settings.require_project_endpoint().split("/api/projects/")[0],
                        deployment_name=settings.embedding_deployment,
                        model_name="text-embedding-3-small",
                    ),
                )
            ],
        ),
        semantic_search=SemanticSearch(
            configurations=[
                SemanticConfiguration(
                    name="semantic-config",
                    prioritized_fields=SemanticPrioritizedFields(
                        title_field=SemanticField(field_name="section"),
                        content_fields=[SemanticField(field_name="content")],
                    ),
                )
            ]
        ),
    )

    client.create_or_update_index(index)
    info(f"Index '{settings.search_index}' angelegt/aktualisiert.")


def ingest() -> None:
    openai_client = get_openai_client()
    search_client = get_search_client()

    documents = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        pieces = chunk(path.read_text(encoding="utf-8"))
        info(f"{path.name}: {len(pieces)} Chunk(s)")
        for heading, _ in pieces:
            info(f"    - {heading}")

        # Embeddings gebatcht - ein Request statt einem pro Chunk.
        response = openai_client.embeddings.create(
            model=settings.embedding_deployment,
            input=[text for _, text in pieces],
            dimensions=EMBED_DIMS,
        )
        for i, ((heading, text), item) in enumerate(zip(pieces, response.data)):
            documents.append(
                {
                    "id": f"{path.stem}-{i}",
                    "content": text,
                    "source": path.name,
                    "section": heading,
                    "content_vector": item.embedding,
                }
            )

    result = search_client.upload_documents(documents=documents)
    info(f"{sum(1 for r in result if r.succeeded)}/{len(documents)} Dokumente indiziert.")


def main() -> None:
    header("RAG-Index bauen")
    build_index()
    ingest()
    info("\nWeiter mit: python 04_rag/02_hybrid_search.py")


if __name__ == "__main__":
    main()
