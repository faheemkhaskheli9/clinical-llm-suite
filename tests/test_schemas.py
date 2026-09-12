from pathlib import Path

import pytest
import yaml

from clinical_core.schemas import (
    LATEST_SCHEMA_VERSION,
    OLDER_SUPPORTED_VERSIONS,
    SCHEMA_REGISTRY,
    PatientRecordValidationError,
    schema_compatibility,
    validate_patient_record,
)

CONFIGS_SCHEMA_YAML = Path(__file__).resolve().parent.parent / "configs" / "schema.yaml"


def _valid_record(**overrides):
    record = {
        "patient_id": "p-1",
        "vitals": {"temperature_c": 37.0, "heart_rate_bpm": 72, "spo2_pct": 98.0},
        "symptoms": [{"name": "cough", "duration_days": 3, "severity": 4}],
        "history": [{"condition": "asthma", "diagnosed_year": 2015}],
    }
    record.update(overrides)
    return record


def test_valid_record_round_trips():
    record = validate_patient_record(_valid_record())
    assert record.schema_version == LATEST_SCHEMA_VERSION
    assert record.patient_id == "p-1"
    assert record.vitals.heart_rate_bpm == 72
    assert record.symptoms[0].name == "cough"
    assert record.history[0].condition == "asthma"


def test_defaults_apply_when_optional_sections_missing():
    record = validate_patient_record({"patient_id": "p-2"})
    assert record.vitals.temperature_c is None
    assert record.symptoms == []
    assert record.history == []


@pytest.mark.parametrize(
    "overrides,bad_field",
    [
        ({"patient_id": ""}, "patient_id"),
        ({"vitals": {"temperature_c": 200}}, "vitals.temperature_c"),
        ({"vitals": {"heart_rate_bpm": -1}}, "vitals.heart_rate_bpm"),
        ({"vitals": {"spo2_pct": 150}}, "vitals.spo2_pct"),
        ({"symptoms": [{"name": "", "severity": 5}]}, "symptoms.0.name"),
        ({"symptoms": [{"name": "cough", "severity": 11}]}, "symptoms.0.severity"),
        ({"history": [{"condition": "x", "diagnosed_year": 1800}]}, "history.0.diagnosed_year"),
    ],
)
def test_invalid_record_raises_field_level_error(overrides, bad_field):
    with pytest.raises(PatientRecordValidationError) as exc_info:
        validate_patient_record(_valid_record(**overrides))

    fields = [e.field for e in exc_info.value.errors]
    assert bad_field in fields, f"expected an error on {bad_field!r}, got {fields}"


def test_missing_required_field_is_a_field_level_error_not_generic():
    with pytest.raises(PatientRecordValidationError) as exc_info:
        validate_patient_record({})

    assert exc_info.value.errors
    assert exc_info.value.errors[0].field == "patient_id"


def test_unknown_schema_version_is_rejected():
    with pytest.raises(PatientRecordValidationError) as exc_info:
        validate_patient_record(_valid_record(schema_version="99.0"))

    assert exc_info.value.errors[0].field == "schema_version"


def test_schema_compatibility_classification():
    assert schema_compatibility(LATEST_SCHEMA_VERSION) == "current"
    assert schema_compatibility("99.0") == "unknown"
    for older in OLDER_SUPPORTED_VERSIONS:
        assert schema_compatibility(older) == "older_supported"


def test_registry_matches_configs_schema_yaml():
    """Duplicated data (the version list, here) needs a test asserting the
    copies match, not just a comment."""
    with open(CONFIGS_SCHEMA_YAML, encoding="utf-8") as f:
        policy = yaml.safe_load(f)

    assert policy["latest_version"] == LATEST_SCHEMA_VERSION
    assert set(policy["older_supported_versions"]) == set(OLDER_SUPPORTED_VERSIONS)
    assert set(policy["versions"].keys()) == set(SCHEMA_REGISTRY.keys())
