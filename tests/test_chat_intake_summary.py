"""Tests for issue #15: doctor-facing intake summary generation."""
import pytest

from chat_intake.summary import SummaryGenerationError, generate_intake_summary
from clinical_core.schemas import PatientRecord, Symptom, Vitals


def _record(**overrides):
    fields = {
        "patient_id": "p-1",
        "vitals": Vitals(),
        "symptoms": [],
        "history": [],
    }
    fields.update(overrides)
    return PatientRecord(**fields)


def test_generate_intake_summary_includes_patient_id_and_turn_count():
    record = _record(vitals=Vitals(temperature_c=38.0), symptoms=[Symptom(name="cough")])

    summary = generate_intake_summary(record, turn_count=3)

    assert "p-1" in summary.text
    assert "3 turn" in summary.text
    assert summary.turn_count == 3


def test_generate_intake_summary_includes_the_clinical_facts():
    record = _record(symptoms=[Symptom(name="cough", duration_days=2, severity=4)])

    summary = generate_intake_summary(record, turn_count=1)

    assert "cough" in summary.text


def test_generate_intake_summary_raises_with_zero_turns():
    record = _record(vitals=Vitals(temperature_c=38.0))

    with pytest.raises(SummaryGenerationError, match="no turns"):
        generate_intake_summary(record, turn_count=0)


def test_generate_intake_summary_raises_when_record_has_nothing_to_summarize():
    record = _record()

    with pytest.raises(SummaryGenerationError):
        generate_intake_summary(record, turn_count=1)
