"""Default vector-store / embedder wiring for RAG consumers (issue #14).

Any RAG-backed feature (chat_intake's recommendation step is the first)
resolves its `VectorStore`/`EmbeddingProvider` from here instead of
constructing `JSONVectorStore`/`HashingEmbedder` inline, so every consumer
reads from the same store the ingest pipeline (`clinical_core.rag.ingest`)
writes to, and a real deployment can swap either without touching a caller.

`RAG_VECTOR_STORE_PATH` follows the same "lenient with defaults, strict
with explicit input" rule `settings.py` uses for `DATABASE_URL`: unset ->
the built-in default local JSON path; set -> used as given. Either way
`JSONVectorStore` starts out empty if the file doesn't exist yet (its own
`_load`), so an un-ingested deployment degrades to "no matches" rather than
erroring.
"""

from __future__ import annotations

import os
from pathlib import Path

from .embeddings import EmbeddingProvider, HashingEmbedder
from .vector_store import JSONVectorStore, VectorStore

_DEFAULT_STORE_PATH = Path("data/rag/vector_store.json")
_DEFAULT_EMBEDDING_DIMENSIONS = 256


def default_store() -> VectorStore:
    """Resolve `RAG_VECTOR_STORE_PATH` (or the built-in default) into a
    `JSONVectorStore`. Never cached at import time (rule 12: import must be
    pure/cheap/total) -- resolved fresh on each call so a changed env var
    takes effect without a process restart."""

    raw_path = os.environ.get("RAG_VECTOR_STORE_PATH", "").strip()
    return JSONVectorStore(raw_path or _DEFAULT_STORE_PATH)


def default_embedder() -> EmbeddingProvider:
    """The same offline, CPU-only embedder `clinical_core.rag.ingest` uses
    by default -- a query embedded with any other provider/dimensions
    wouldn't be comparable to what's actually stored."""

    return HashingEmbedder(dimensions=_DEFAULT_EMBEDDING_DIMENSIONS)
