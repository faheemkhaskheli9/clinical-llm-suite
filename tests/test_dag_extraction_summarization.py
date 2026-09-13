"""Tests for issue #9: Port summarization node."""
import pytest
from django.urls import reverse

from dag_extraction.models import ExtractionRecord
from dag_extraction.pipeline import run_pipeline
from dag_extraction.summarization import SummarizationError, summarize_record

pytestmark = pytest.mark.django_db

SAMPLE_TEXT = (
    "Patient reports a cough for 3 days, severity 4/10. Temperature is 38.2C, "
    "heart rate 92 bpm. History of asthma diagnosed 2015."
)


def test_summarization_runs_after_extraction_and_mentions_extracted_fields():
    record, result = run_pipeline(SAMPLE_TEXT, patient_id="p-1")

    assert record is not None
    assert not record.summarization_failed
    assert "cough" in record.summary
    assert "asthma" in record.summary
    assert "38.2" in record.summary


def test_summary_is_persisted_alongside_the_structured_record():
    record, result = run_pipeline(SAMPLE_TEXT, patient_id="p-2")

    stored = ExtractionRecord.objects.get(id=record.id)
    assert stored.summary == record.summary
    assert stored.extracted_record["patient_id"] == "p-2"
    assert stored.extracted_record["symptoms"][0]["name"] == "cough"


def test_summarization_failure_does_not_block_extraction_from_being_saved():
    """Nothing to summarize (no vitals/symptoms/history extracted at all)
    still leaves a valid, empty-but-schema-valid record to persist."""
    record, result = run_pipeline("Patient seems generally well today.", patient_id="p-3")

    assert record is not None
    assert record.summarization_failed is True
    assert record.summary is None
    assert ExtractionRecord.objects.filter(id=record.id).exists()


def test_summarize_record_raises_when_nothing_extracted():
    result = run_pipeline("Patient seems generally well today.", patient_id="p-4")[1]
    with pytest.raises(SummarizationError):
        summarize_record(result.record)


def test_extraction_validation_failure_persists_nothing():
    record, result = run_pipeline("Temperature is 99.0C.", patient_id="p-5")

    assert record is None
    assert result.record is None
    assert not ExtractionRecord.objects.filter(patient_id="p-5").exists()


def test_extract_page_shows_summary(client, django_user_model):
    user = django_user_model.objects.create_user(username="doc", password="pw12345")
    client.force_login(user)

    resp = client.post(reverse("dag-extraction"), {"patient_id": "p-1", "text": SAMPLE_TEXT})

    assert resp.status_code == 200
    assert b"cough" in resp.content
    assert b"Summary" in resp.content


def test_extract_page_shows_summarization_failed_note(client, django_user_model):
    user = django_user_model.objects.create_user(username="doc2", password="pw12345")
    client.force_login(user)

    resp = client.post(
        reverse("dag-extraction"),
        {"patient_id": "p-1", "text": "Patient seems generally well today."},
    )

    assert resp.status_code == 200
    assert b"Summarization failed" in resp.content
