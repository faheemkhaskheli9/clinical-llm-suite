"""Tests for issue #8: Port schema-validated field extraction."""
import pytest
from django.urls import reverse

from dag_extraction.extraction import extract_patient_record

pytestmark = pytest.mark.django_db


SAMPLE_TEXT = (
    "Patient reports a cough for 3 days, severity 4/10. Temperature is 38.2C, "
    "heart rate 92 bpm, BP 118/76, SpO2 96%. History of asthma diagnosed 2015."
)


def test_extraction_produces_fields_matching_clinical_core_schema():
    result = extract_patient_record(SAMPLE_TEXT, patient_id="p-1")

    assert result.record is not None
    assert result.record.patient_id == "p-1"
    assert result.record.vitals.temperature_c == 38.2
    assert result.record.vitals.heart_rate_bpm == 92
    assert result.record.vitals.systolic_bp_mmhg == 118
    assert result.record.vitals.diastolic_bp_mmhg == 76
    assert result.record.vitals.spo2_pct == 96
    assert result.record.symptoms[0].name == "cough"
    assert result.record.symptoms[0].duration_days == 3
    assert result.record.symptoms[0].severity == 4
    assert result.record.history[0].condition == "asthma"
    assert result.record.history[0].diagnosed_year == 2015


def test_missing_field_groups_are_flagged_not_silently_defaulted():
    result = extract_patient_record("Patient seems generally well today.", patient_id="p-2")

    assert result.missing_fields == ("vitals", "symptoms", "history")
    # Still a valid record: an empty group is a legitimate (flagged) outcome,
    # not a validation failure.
    assert result.record is not None
    assert result.record.vitals.temperature_c is None
    assert result.record.symptoms == []
    assert result.record.history == []


def test_partial_extraction_flags_only_the_groups_with_nothing_found():
    result = extract_patient_record("Temperature is 37.0C.", patient_id="p-3")

    assert result.missing_fields == ("symptoms", "history")
    assert result.record.vitals.temperature_c == 37.0


def test_extraction_output_is_validated_before_being_handed_back():
    """An out-of-range value the regex could in principle produce (e.g. a
    temperature typo) must not silently pass through as a "valid" record."""
    result = extract_patient_record("Temperature is 99.0C.", patient_id="p-4")

    assert result.record is None
    assert result.missing_fields == ("symptoms", "history")
    assert any("temperature_c" in msg for msg in result.validation_errors)


def test_severity_word_used_when_no_explicit_numeric_severity_given():
    result = extract_patient_record("Patient reports a severe headache for 2 hours.", patient_id="p-5")

    headache = next(s for s in result.record.symptoms if s.name == "headache")
    assert headache.severity == 8
    assert headache.duration_days == round(2 / 24, 2)


def test_unauthenticated_extract_page_redirects_to_login(client):
    resp = client.get(reverse("dag-extraction"))
    assert resp.status_code == 302
    assert resp.url.startswith(reverse("login"))


def test_extract_page_missing_patient_id_reprompts_without_extracting(client, django_user_model):
    user = django_user_model.objects.create_user(username="doc", password="pw12345")
    client.force_login(user)

    resp = client.post(reverse("dag-extraction"), {"patient_id": "", "text": SAMPLE_TEXT})

    assert resp.status_code == 200
    assert b"Patient ID is required." in resp.content


def test_extract_page_renders_extracted_fields(client, django_user_model):
    user = django_user_model.objects.create_user(username="doc2", password="pw12345")
    client.force_login(user)

    resp = client.post(reverse("dag-extraction"), {"patient_id": "p-1", "text": SAMPLE_TEXT})

    assert resp.status_code == 200
    assert b"asthma" in resp.content
    assert b"Passed clinical_core schema validation." in resp.content


def test_dashboard_dag_extraction_link_redirects_to_real_feature(client, django_user_model):
    user = django_user_model.objects.create_user(username="doc3", password="pw12345")
    client.force_login(user)

    resp = client.get(reverse("feature", kwargs={"slug": "dag-extraction"}))

    assert resp.status_code == 302
    assert resp.url == reverse("dag-extraction")
