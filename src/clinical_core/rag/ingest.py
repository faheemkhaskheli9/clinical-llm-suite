"""RAG ingest pipeline: fetch -> normalize -> chunk -> embed -> upsert.

Composes the MedlinePlus/openFDA/MedQuAD fetchers (each yielding a
normalized ``SourceDocument``) with the chunking-and-embedding-ingestion
knowledge-base pattern: chunk id = hash(source_document_id, chunk_index,
chunk_text), so re-ingesting the same document set is idempotent — upsert by
id never duplicates a chunk, while an edited chunk gets a new id instead of
silently overwriting old text under a stale key. Every stored chunk keeps
its source document's citation fields (source, title, url, section) in its
metadata so a retrieval result can always be attributed back to where it
came from.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Iterable, Iterator

from clinical_core.rag.chunking import chunk_text
from clinical_core.rag.embeddings import EmbeddingProvider
from clinical_core.rag.fetchers import medlineplus, medquad, openfda
from clinical_core.rag.schema import SourceDocument
from clinical_core.rag.storage import write_documents
from clinical_core.rag.vector_store import VectorRecord, VectorStore

logger = logging.getLogger(__name__)

FETCHERS: dict[str, Callable[..., Iterator[SourceDocument]]] = {
    "medlineplus": medlineplus.fetch,
    "openfda": openfda.fetch,
    "medquad": medquad.fetch,
}


def chunk_id(document_id: str, chunk_index: int, chunk: str) -> str:
    """Deterministic id derived from the source document id + chunk index +
    chunk content, so re-ingesting the same document set produces the same
    ids (idempotent upsert) but an edited chunk gets a new id rather than
    silently overwriting the old text under a stale key."""
    digest = hashlib.sha256(f"{document_id}::{chunk_index}::{chunk}".encode("utf-8")).hexdigest()
    return digest


def chunk_documents(
    documents: Iterable[SourceDocument], chunk_size: int = 800, chunk_overlap: int = 100
) -> Iterator[tuple[str, str, dict]]:
    """Yield ``(id, chunk_text, metadata)`` for every chunk of every document.

    ``metadata`` always carries the source document's citation fields
    (document_id, source, doc_type, title, section, url, chunk_index) so a
    retrieval hit can be attributed back to its origin.
    """
    for document in documents:
        chunks = chunk_text(document.text, chunk_size, chunk_overlap)
        for index, chunk in enumerate(chunks):
            metadata = {
                "document_id": document.id,
                "source": document.source,
                "doc_type": document.doc_type.value,
                "title": document.title,
                "section": document.section,
                "url": document.url,
                "chunk_index": index,
            }
            yield chunk_id(document.id, index, chunk), chunk, metadata


def ingest_documents(
    documents: Iterable[SourceDocument],
    embedder: EmbeddingProvider,
    store: VectorStore,
    *,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> int:
    """Chunk, embed, and upsert `documents` into `store`.

    Returns the number of chunks written. Safe to call more than once on the
    same documents — upsert by the (document, chunk_index, text)-derived id
    keeps re-ingestion idempotent rather than duplicating records.
    """
    ids: list[str] = []
    texts: list[str] = []
    metadatas: list[dict] = []
    for record_id, chunk, metadata in chunk_documents(documents, chunk_size, chunk_overlap):
        ids.append(record_id)
        texts.append(chunk)
        metadatas.append(metadata)

    if not texts:
        return 0

    embeddings = embedder.embed(texts)
    records = [
        VectorRecord(id=record_id, embedding=embedding.tolist(), document=chunk, metadata=metadata)
        for record_id, chunk, metadata, embedding in zip(ids, texts, metadatas, embeddings)
    ]
    store.upsert(records)
    n_documents = len({m["document_id"] for m in metadatas})
    logger.info("ingested %d chunks from %d document(s)", len(records), n_documents)
    return len(records)


def run(
    sources: list[str],
    config: dict,
    embedder: EmbeddingProvider,
    store: VectorStore,
    *,
    persist_normalized: bool = True,
) -> dict[str, int]:
    """Fetch each named source, optionally cache its normalized documents to
    ``data/processed/<source>.jsonl``, then chunk/embed/upsert every fetched
    document into `store`. Returns chunk counts written, keyed by source.
    """
    counts: dict[str, int] = {}
    for source in sources:
        fetch = FETCHERS.get(source)
        if fetch is None:
            logger.warning("unknown source %r (known: %s)", source, ", ".join(FETCHERS))
            continue

        kwargs = {k: v for k, v in (config.get(source) or {}).items() if v is not None}
        documents = list(fetch(**kwargs))
        if persist_normalized:
            write_documents(source, documents)
        counts[source] = ingest_documents(documents, embedder, store)
    return counts
