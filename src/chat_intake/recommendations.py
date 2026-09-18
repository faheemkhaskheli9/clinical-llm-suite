"""RAG-backed recommendation step for chat intake (issue #14).

Runs once a patient record has been extracted: retrieves reference chunks
from the RAG ingest pipeline's vector store (`clinical_core.rag`) for a
query built from the record itself, then assembles a response grounded in
those chunks. No real LLM call is made -- the same deterministic
template-assembly stand-in `dag_extraction.summarization` already uses --
but the response always says which retrieved source(s), if any, it is
based on, and never cites a source it didn't actually retrieve.

A retrieval miss -- no chunk clears `MIN_SIMILARITY`, including the
"nothing to summarize" case where there is no query text to search with at
all -- returns a `Recommendation` with `grounded=False` and no `sources`:
a clearly-labeled generic response rather than a fabricated citation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from clinical_core.rag.embeddings import EmbeddingProvider
from clinical_core.rag.factory import default_embedder, default_store
from clinical_core.rag.vector_store import VectorStore
from clinical_core.schemas import PatientRecord
from dag_extraction.summarization import SummarizationError, summarize_record

#: Cosine-similarity floor a retrieved chunk must clear to count as
#: "relevant" rather than noise. `HashingEmbedder` is a bag-of-words
#: embedding, so an unrelated query can still share a few common words with
#: any chunk; this floor separates that from a chunk that shares
#: essentially nothing with the query (a genuine retrieval miss).
MIN_SIMILARITY = 0.05

GENERIC_FALLBACK_PREFIX = (
    "[General guidance -- no matching reference material was found in the "
    "knowledge base for this intake.] "
)


@dataclass(frozen=True)
class SourceRef:
    """One retrieved chunk's citation fields, carried through to the
    rendered recommendation so it never names a source it didn't use."""

    title: str
    source: str
    section: str
    url: str


@dataclass(frozen=True)
class Recommendation:
    text: str
    sources: tuple[SourceRef, ...] = field(default_factory=tuple)
    grounded: bool = False


def _generic_recommendation(query_text: str | None) -> Recommendation:
    if query_text:
        text = GENERIC_FALLBACK_PREFIX + f"Based on the intake record alone: {query_text}"
    else:
        text = GENERIC_FALLBACK_PREFIX + "No intake findings were available to base guidance on."
    return Recommendation(text=text, sources=(), grounded=False)


def recommend_for_record(
    record: PatientRecord,
    *,
    store: VectorStore | None = None,
    embedder: EmbeddingProvider | None = None,
    top_k: int = 3,
    min_similarity: float = MIN_SIMILARITY,
) -> Recommendation:
    """Retrieve reference chunks relevant to `record` and assemble a
    recommendation grounded in them, or a clearly-labeled generic fallback
    on a retrieval miss (see module docstring)."""

    store = store if store is not None else default_store()
    embedder = embedder if embedder is not None else default_embedder()

    try:
        query_text = summarize_record(record)
    except SummarizationError:
        return _generic_recommendation(None)

    [query_embedding] = embedder.embed([query_text])
    scored = store.query_with_scores(query_embedding, top_k=top_k)
    relevant = [(score, hit) for score, hit in scored if score >= min_similarity]

    if not relevant:
        return _generic_recommendation(query_text)

    sources = tuple(
        SourceRef(
            title=hit.metadata.get("title", ""),
            source=hit.metadata.get("source", ""),
            section=hit.metadata.get("section", ""),
            url=hit.metadata.get("url", ""),
        )
        for _, hit in relevant
    )
    excerpts = "\n".join(
        f"- ({ref.title or ref.source}) {hit.document.strip()[:280]}"
        for (_, hit), ref in zip(relevant, sources)
    )
    text = f"Based on retrieved reference material for: {query_text}\n{excerpts}"
    return Recommendation(text=text, sources=sources, grounded=True)
