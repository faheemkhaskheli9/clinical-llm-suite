"""Tests for issue #14: RAG-backed recommendations for chat intake."""
from __future__ import annotations

from clinical_core.rag.embeddings import HashingEmbedder
from clinical_core.rag.schema import DocType, SourceDocument
from clinical_core.rag.vector_store import JSONVectorStore
from clinical_core.rag import ingest
from clinical_core.schemas import PatientRecordV1, Symptom, Vitals
from chat_intake.recommendations import recommend_for_record


def _record(**kwargs) -> PatientRecordV1:
    return PatientRecordV1(patient_id="p-1", **kwargs)


def _doc(doc_id: str, text: str, *, title="Asthma", url="https://medlineplus.gov/asthma.html") -> SourceDocument:
    return SourceDocument(
        id=doc_id,
        doc_type=DocType.DISEASE,
        source="medlineplus",
        title=title,
        section="overview",
        text=text,
        url=url,
    )


def test_recommend_for_record_is_grounded_when_a_relevant_chunk_is_retrieved(tmp_path):
    store = JSONVectorStore(tmp_path / "store.json")
    embedder = HashingEmbedder(dimensions=64)
    ingest.ingest_documents(
        [_doc("medlineplus:asthma", "asthma cough wheezing shortness of breath treatment")],
        embedder,
        store,
    )
    record = _record(symptoms=[Symptom(name="cough", duration_days=2, severity=4)])

    recommendation = recommend_for_record(record, store=store, embedder=embedder, min_similarity=0.01)

    assert recommendation.grounded is True
    assert recommendation.sources
    assert recommendation.sources[0].title == "Asthma"
    assert recommendation.sources[0].url == "https://medlineplus.gov/asthma.html"
    assert "cough" in recommendation.text.lower()


def test_recommend_for_record_falls_back_to_generic_when_store_is_empty(tmp_path):
    store = JSONVectorStore(tmp_path / "store.json")
    embedder = HashingEmbedder(dimensions=64)
    record = _record(symptoms=[Symptom(name="cough", duration_days=2, severity=4)])

    recommendation = recommend_for_record(record, store=store, embedder=embedder)

    assert recommendation.grounded is False
    assert recommendation.sources == ()
    assert "[General guidance" in recommendation.text
    assert "cough" in recommendation.text.lower()  # still references the intake findings, just not a citation


def test_recommend_for_record_falls_back_to_generic_when_no_chunk_clears_the_similarity_floor(tmp_path):
    store = JSONVectorStore(tmp_path / "store.json")
    embedder = HashingEmbedder(dimensions=64)
    ingest.ingest_documents(
        [_doc("medlineplus:unrelated", "completely unrelated passage about something else entirely")],
        embedder,
        store,
    )
    record = _record(symptoms=[Symptom(name="cough", duration_days=2, severity=4)])

    recommendation = recommend_for_record(
        record, store=store, embedder=embedder, min_similarity=0.999
    )

    assert recommendation.grounded is False
    assert recommendation.sources == ()


def test_recommend_for_record_falls_back_to_generic_with_no_query_text_when_record_is_empty(tmp_path):
    store = JSONVectorStore(tmp_path / "store.json")
    embedder = HashingEmbedder(dimensions=64)
    record = _record()  # no vitals/symptoms/history -> summarize_record raises SummarizationError

    recommendation = recommend_for_record(record, store=store, embedder=embedder)

    assert recommendation.grounded is False
    assert recommendation.sources == ()
    assert "No intake findings were available" in recommendation.text


def test_recommend_for_record_never_cites_a_source_below_the_similarity_floor(tmp_path):
    """A retrieval miss must never fabricate a citation -- sources stays
    empty even though the store has content, if nothing clears the floor."""
    store = JSONVectorStore(tmp_path / "store.json")
    embedder = HashingEmbedder(dimensions=64)
    ingest.ingest_documents([_doc("medlineplus:x", "zzz qqq unrelated tokens")], embedder, store)
    record = _record(history=[])
    record = _record(symptoms=[Symptom(name="fever", duration_days=1)])

    recommendation = recommend_for_record(record, store=store, embedder=embedder, min_similarity=1.0)

    assert recommendation.sources == ()
