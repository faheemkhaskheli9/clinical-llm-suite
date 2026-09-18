import pytest

from clinical_core.rag import storage
from clinical_core.rag.schema import DocType, SourceDocument


def _doc(doc_id: str, text: str = "some passage text") -> SourceDocument:
    return SourceDocument(
        id=doc_id,
        doc_type=DocType.DISEASE,
        source="medlineplus",
        title="Example",
        text=text,
    )


def test_write_then_read_documents_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "PROCESSED_DIR", tmp_path)

    written = storage.write_documents("medlineplus", [_doc("medlineplus:a"), _doc("medlineplus:b")])
    read_back = list(storage.read_documents("medlineplus"))

    assert written == 2
    assert [doc.id for doc in read_back] == ["medlineplus:a", "medlineplus:b"]


def test_write_documents_overwrites_previous_run(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "PROCESSED_DIR", tmp_path)

    storage.write_documents("medlineplus", [_doc("medlineplus:a"), _doc("medlineplus:b")])
    storage.write_documents("medlineplus", [_doc("medlineplus:c")])

    read_back = list(storage.read_documents("medlineplus"))
    assert [doc.id for doc in read_back] == ["medlineplus:c"]


def test_read_documents_returns_empty_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "PROCESSED_DIR", tmp_path)

    assert list(storage.read_documents("never-ingested")) == []


def test_write_documents_keeps_previous_file_when_generator_raises_midway(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "PROCESSED_DIR", tmp_path)
    storage.write_documents("medlineplus", [_doc("medlineplus:good-1"), _doc("medlineplus:good-2")])

    def exploding_source():
        yield _doc("medlineplus:new-1")
        raise ConnectionError("source API died after 1 of N records")

    with pytest.raises(ConnectionError):
        storage.write_documents("medlineplus", exploding_source())

    # The prior good run must survive untouched — no truncated/partial file.
    read_back = list(storage.read_documents("medlineplus"))
    assert [doc.id for doc in read_back] == ["medlineplus:good-1", "medlineplus:good-2"]
    # And no stray temp files left behind.
    assert not list(tmp_path.glob(".*.tmp"))
