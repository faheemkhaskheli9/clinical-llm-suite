from clinical_core.rag.vector_store import JSONVectorStore, VectorRecord


def _record(id_, embedding, text="passage", metadata=None):
    return VectorRecord(id=id_, embedding=embedding, document=text, metadata=metadata or {})


def test_upsert_by_id_does_not_duplicate(tmp_path):
    store = JSONVectorStore(tmp_path / "store.json")

    store.upsert([_record("a", [1.0, 0.0])])
    store.upsert([_record("a", [1.0, 0.0])])  # re-ingest same id

    assert len(store) == 1
    assert store.get_ids() == {"a"}


def test_upsert_replaces_existing_record_content(tmp_path):
    store = JSONVectorStore(tmp_path / "store.json")

    store.upsert([_record("a", [1.0, 0.0], text="old text")])
    store.upsert([_record("a", [1.0, 0.0], text="new text")])

    [record] = store.query([1.0, 0.0], top_k=1)
    assert record.document == "new text"


def test_persists_and_reloads_from_disk(tmp_path):
    path = tmp_path / "store.json"
    store = JSONVectorStore(path)
    store.upsert([_record("a", [1.0, 0.0], metadata={"source": "medlineplus"})])

    reloaded = JSONVectorStore(path)

    assert reloaded.get_ids() == {"a"}
    [record] = reloaded.query([1.0, 0.0], top_k=1)
    assert record.metadata == {"source": "medlineplus"}


def test_query_with_scores_ranks_by_cosine_similarity(tmp_path):
    store = JSONVectorStore(tmp_path / "store.json")
    store.upsert([
        _record("close", [1.0, 0.0]),
        _record("far", [0.0, 1.0]),
    ])

    ranked = store.query_with_scores([1.0, 0.0], top_k=2)

    assert [record.id for _, record in ranked] == ["close", "far"]
