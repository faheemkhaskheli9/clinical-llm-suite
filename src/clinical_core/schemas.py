"""
Versioned patient-record schema contract, shared by every intake feature app
(chat intake, DAG extraction) and the review portal.

Pure Pydantic + stdlib — no Django or other framework import — so any
feature app can call `validate_patient_record` regardless of its own stack
(README.md Section 2/3). Pydantic v2 is not itself a web framework; it is the
schema layer this project already commits to per README.md Section 3.

Versioning
----------
Each stored/submitted record carries its own `schema_version`. Adding a field
in a new version means adding a new model class + registry entry, not editing
the old one in place, so records written under an older version keep
validating exactly as they always did — see `SCHEMA_REGISTRY` and
`LATEST_SCHEMA_VERSION`. `upgrade_to_latest` is the extension point later
versions hook into to migrate an old-version record forward.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

# Every record produced by this suite is a pipeline demo over synthetic/public
# data, never a clinical-decision tool — see README.md's Disclosure section.
Compatibility = Literal["current", "older_supported", "unknown"]

CURRENT_YEAR = datetime.now(timezone.utc).year


class FieldError(BaseModel):
    """One field-level validation failure."""

    field: str
    message: str


class PatientRecordValidationError(ValueError):
    """Raised when a patient record fails schema validation.

    Carries `errors` (field-level, from Pydantic) instead of only a generic
    message, so a caller (chat intake, DAG extraction, review portal) can
    show the reviewer/patient exactly which field was wrong.
    """

    def __init__(self, errors: list[FieldError]):
        self.errors = errors
        message = "; ".join(f"{e.field}: {e.message}" for e in errors)
        super().__init__(message or "Invalid patient record.")

    @classmethod
    def from_pydantic(cls, exc: ValidationError) -> "PatientRecordValidationError":
        errors = [
            FieldError(
                field=".".join(str(p) for p in err["loc"]) or "(root)",
                message=err["msg"],
            )
            for err in exc.errors()
        ]
        return cls(errors)


# --- Shared sub-models -----------------------------------------------------


class Vitals(BaseModel):
    """All vital-sign fields are bounded the same way (rule: a check applied
    to one vital applies to every sibling vital) — every field non-negative,
    with a generous but real physiological upper bound so a unit-mixup
    (e.g. temperature in Fahrenheit) is rejected rather than stored."""

    temperature_c: float | None = Field(default=None, ge=25.0, le=45.0)
    heart_rate_bpm: int | None = Field(default=None, ge=0, le=300)
    respiratory_rate_bpm: int | None = Field(default=None, ge=0, le=100)
    systolic_bp_mmhg: int | None = Field(default=None, ge=0, le=300)
    diastolic_bp_mmhg: int | None = Field(default=None, ge=0, le=200)
    spo2_pct: float | None = Field(default=None, ge=0.0, le=100.0)


class Symptom(BaseModel):
    name: str = Field(min_length=1)
    duration_days: float | None = Field(default=None, ge=0)
    severity: int | None = Field(default=None, ge=1, le=10)


class HistoryItem(BaseModel):
    condition: str = Field(min_length=1)
    diagnosed_year: int | None = Field(default=None, ge=1900, le=CURRENT_YEAR)
    notes: str | None = None


# --- Versioned patient record ----------------------------------------------


class PatientRecordV1(BaseModel):
    """Schema version "1.0" of the patient record."""

    schema_version: Literal["1.0"] = "1.0"
    patient_id: str = Field(min_length=1)
    vitals: Vitals = Field(default_factory=Vitals)
    symptoms: list[Symptom] = Field(default_factory=list)
    history: list[HistoryItem] = Field(default_factory=list)


LATEST_SCHEMA_VERSION = "1.0"

# Keyed by version string, not one hardcoded field per version, so adding
# "1.1" is a new class + one registry entry rather than an edit to this one.
SCHEMA_REGISTRY: dict[str, type[BaseModel]] = {
    "1.0": PatientRecordV1,
}

# Versions this suite still accepts (and upgrades on read) but no longer
# writes new records under. Empty until a "1.1" ships and "1.0" moves here.
OLDER_SUPPORTED_VERSIONS: frozenset[str] = frozenset()

PatientRecord = PatientRecordV1  # alias to the current version's model


def schema_compatibility(version: str) -> Compatibility:
    """Classify a `schema_version` string per the versioning policy: the
    latest version, an older one this suite still accepts, or one it has
    never heard of."""
    if version == LATEST_SCHEMA_VERSION:
        return "current"
    if version in OLDER_SUPPORTED_VERSIONS:
        return "older_supported"
    return "unknown"


def upgrade_to_latest(data: dict) -> dict:
    """Migrate a record dict from an older `schema_version` forward.

    A no-op today (only "1.0" exists); a future "1.1" adds a branch here
    that fills in its new field(s) with a default before validation, so
    records written under "1.0" keep loading unchanged.
    """
    return data


def validate_patient_record(data: dict, *, upgrade: bool = True) -> PatientRecord:
    """Validate a raw dict against its declared (or latest) schema version.

    Raises `PatientRecordValidationError` with field-level errors on invalid
    input — never a bare/generic exception — so callers can surface exactly
    what was wrong.
    """
    version = data.get("schema_version", LATEST_SCHEMA_VERSION)
    if schema_compatibility(version) == "unknown":
        raise PatientRecordValidationError(
            [
                FieldError(
                    field="schema_version",
                    message=(
                        f"Unknown schema_version '{version}'. "
                        f"Known versions: {', '.join(sorted(SCHEMA_REGISTRY))}."
                    ),
                )
            ]
        )
    model_cls = SCHEMA_REGISTRY[version]

    if upgrade and version != LATEST_SCHEMA_VERSION:
        data = upgrade_to_latest(dict(data))
        model_cls = SCHEMA_REGISTRY[LATEST_SCHEMA_VERSION]

    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        raise PatientRecordValidationError.from_pydantic(exc) from exc
