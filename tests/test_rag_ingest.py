import importlib.util
from pathlib import Path

import pytest

from clinical_core.rag import ingest, storage
from clinical_core.rag.embeddings import HashingEmbedder
from clinical_core.rag.schema import DocType, SourceDocument
from clinical_core.rag.vector_store import JSONVectorStore

_INGEST_CLI_PATH = Path(__file__).resolve().parent.parent / "scripts" / "ingest.py"
_spec = importlib.util.spec_from_file_location("ingest_cli", _INGEST_CLI_PATH)
ingest_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ingest_cli)


def _doc(doc_id: str, text: str, *, source="medlineplus", section="overview", url="https://example.org/x") -> SourceDocument:
    return SourceDocument(
        id=doc_id,
        doc_type=DocType.DISEASE,
        source=source,
        title="Example condition",
        section=section,
        text=text,
        url=url,
    )


def test_chunk_documents_carries_citation_metadata():
    doc = _doc("medlineplus:diabetes", "some passage text about diabetes", url="https://medlineplus.gov/diabetes.html")

    [(record_id, chunk, metadata)] = list(ingest.chunk_documents([doc], chunk_size=800, chunk_overlap=100))

    assert chunk == doc.text
    assert metadata == {
        "document_id": "medlineplus:diabetes",
        "source": "medlineplus",
        "doc_type": "disease",
        "title": "Example condition",
        "section": "overview",
        "url": "https://medlineplus.gov/diabetes.html",
        "chunk_index": 0,
    }
    assert isinstance(record_id, str) and record_id


def test_chunk_id_is_deterministic_and_content_sensitive():
    id_a = ingest.chunk_id("doc-1", 0, "some text")
    id_b = ingest.chunk_id("doc-1", 0, "some text")
    id_c = ingest.chunk_id("doc-1", 0, "different text")

    assert id_a == id_b
    assert id_a != id_c


def test_ingest_documents_is_idempotent_on_reingestion(tmp_path):
    """Core acceptance criterion: re-running ingestion on the same documents
    must not duplicate chunks (chunking-and-embedding-ingestion KB pattern)."""
    store = JSONVectorStore(tmp_path / "store.json")
    embedder = HashingEmbedder(dimensions=32)
    docs = [_doc("medlineplus:diabetes", "diabetes causes high blood glucose over time")]

    first = ingest.ingest_documents(docs, embedder, store)
    second = ingest.ingest_documents(docs, embedder, store)

    assert first == second  # same chunk count both times
    assert len(store) == first  # no duplicates accumulated in the store


def test_ingest_documents_gives_an_edited_chunk_a_new_id_not_a_silent_overwrite(tmp_path):
    store = JSONVectorStore(tmp_path / "store.json")
    embedder = HashingEmbedder(dimensions=32)

    ingest.ingest_documents([_doc("medlineplus:diabetes", "original passage text")], embedder, store)
    ids_before = store.get_ids()
    ingest.ingest_documents([_doc("medlineplus:diabetes", "edited passage text")], embedder, store)

    # both the old and new chunk are present -- an edit doesn't silently clobber under a stale key.
    assert ids_before <= store.get_ids()
    assert len(store) == 2


def test_ingest_documents_upserts_records_with_source_and_citation_url(tmp_path):
    store = JSONVectorStore(tmp_path / "store.json")
    embedder = HashingEmbedder(dimensions=32)
    docs = [_doc("openfda:abc:warnings", "may cause drowsiness", source="openfda", section="warnings", url="https://dailymed.nlm.nih.gov/x")]

    ingest.ingest_documents(docs, embedder, store)

    [record] = store.query([0.0] * 32, top_k=1)
    assert record.metadata["source"] == "openfda"
    assert record.metadata["url"] == "https://dailymed.nlm.nih.gov/x"
    assert record.metadata["document_id"] == "openfda:abc:warnings"


def test_ingest_documents_returns_zero_for_no_documents(tmp_path):
    store = JSONVectorStore(tmp_path / "store.json")
    assert ingest.ingest_documents([], HashingEmbedder(dimensions=32), store) == 0


def test_run_fetches_normalizes_and_ingests_each_configured_source(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "PROCESSED_DIR", tmp_path / "processed")

    def fake_medlineplus_fetch(**kwargs):
        yield _doc("medlineplus:a", "passage a")
        yield _doc("medlineplus:b", "passage b")

    monkeypatch.setitem(ingest.FETCHERS, "medlineplus", fake_medlineplus_fetch)
    store = JSONVectorStore(tmp_path / "store.json")

    counts = ingest.run(["medlineplus"], {}, HashingEmbedder(dimensions=32), store)

    assert counts == {"medlineplus": 2}
    assert len(store) == 2
    # normalized documents were also cached to data/processed/medlineplus.jsonl
    cached = list(storage.read_documents("medlineplus"))
    assert [d.id for d in cached] == ["medlineplus:a", "medlineplus:b"]


def test_run_skips_unknown_source(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "PROCESSED_DIR", tmp_path / "processed")
    store = JSONVectorStore(tmp_path / "store.json")

    counts = ingest.run(["not-a-real-source"], {}, HashingEmbedder(dimensions=32), store)

    assert counts == {}


def test_load_config_returns_empty_when_default_path_absent(tmp_path):
    missing = tmp_path / "rag_ingest.yaml"
    assert ingest_cli.load_config(missing, required=False) == {}


def test_load_config_raises_when_explicit_path_absent(tmp_path):
    missing = tmp_path / "typo.yaml"
    with pytest.raises(SystemExit):
        ingest_cli.load_config(missing, required=True)


def test_load_config_parses_existing_file(tmp_path):
    cfg = tmp_path / "rag_ingest.yaml"
    cfg.write_text("openfda:\n  limit: 5\n", encoding="utf-8")
    assert ingest_cli.load_config(cfg, required=True) == {"openfda": {"limit": 5}}
