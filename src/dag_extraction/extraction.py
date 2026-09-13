"""Rule-based field extraction for the DAG Extraction feature app (issue #8).

`clinical-summary-promptflow` never actually had extraction logic to port —
its `VitalsSchema`/`SymptomSchema` (`src/clinical_summary/schemas.py`) are
field shapes, and its CLI (`src/clinical_summary/cli.py`) only validates an
*already-structured* JSON blob. This module is the real "raw conversation
text in, structured fields out" step those field shapes were waiting for.

Extraction is deterministic regex/keyword matching, not an LLM call — this
project's CPU-only / no-paid-APIs rule means the "PromptFlow-style DAG"'s
extraction node is mocked here rather than calling out to a real LLM; a
production version would swap `_extract_vitals`/`_extract_symptoms`/
`_extract_history` for an LLM-backed extraction call behind the same
`extract_patient_record` signature.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from clinical_core.schemas import (
    PatientRecord,
    PatientRecordValidationError,
    validate_patient_record,
)

FIELD_GROUPS = ("vitals", "symptoms", "history")

# Rule 10 candidate for expansion later: every symptom keyword is searched
# for and windowed the same way, so adding one is a one-line change here.
_SYMPTOM_KEYWORDS = (
    "cough",
    "fever",
    "headache",
    "nausea",
    "fatigue",
    "vomiting",
    "dizziness",
    "chest pain",
    "shortness of breath",
    "sore throat",
)

_SEVERITY_WORDS = {"mild": 3, "moderate": 5, "severe": 8}

_DURATION_UNIT_TO_DAYS = {
    "hour": 1 / 24,
    "hours": 1 / 24,
    "day": 1.0,
    "days": 1.0,
    "week": 7.0,
    "weeks": 7.0,
}

_HISTORY_PATTERN = re.compile(
    r"history of ([a-z][a-z \-]{2,40}?)(?:,? diagnosed(?:\s+in)?\s+(\d{4}))?(?=[.,;]|$)",
    re.IGNORECASE,
)


@dataclass
class ExtractionResult:
    """The extraction node's output.

    `missing_fields` names every field group (vitals/symptoms/history) that
    had nothing found in the text — an explicit flag, not a silently empty
    default the caller has to infer by checking `len(...) == 0` itself.
    `record` is the schema-validated `PatientRecord`, or `None` if the
    assembled fields failed `clinical_core` validation (`validation_errors`
    then carries why) — extraction output is never handed back as "valid"
    without having actually passed validation.
    """

    record: PatientRecord | None
    missing_fields: tuple[str, ...]
    validation_errors: tuple[str, ...] = ()


def _nearby_window(text: str, index: int, radius: int = 40) -> str:
    return text[max(0, index - radius) : index + radius]


def _extract_vitals(text: str) -> dict:
    vitals: dict = {}

    m = re.search(r"temp(?:erature)?\s*(?:of|is|:)?\s*(\d{2}(?:\.\d)?)\s*(?:c\b|celsius|°c)?", text, re.I)
    if m:
        vitals["temperature_c"] = float(m.group(1))

    m = re.search(r"(?:heart rate|hr|pulse)\s*(?:of|is|:)?\s*(\d{2,3})\s*(?:bpm)?\b", text, re.I)
    if m:
        vitals["heart_rate_bpm"] = int(m.group(1))

    m = re.search(r"(?:respiratory rate|rr)\s*(?:of|is|:)?\s*(\d{1,2})\s*(?:bpm|breaths)?", text, re.I)
    if m:
        vitals["respiratory_rate_bpm"] = int(m.group(1))

    m = re.search(r"(?:bp|blood pressure)\s*(?:of|is|:)?\s*(\d{2,3})\s*/\s*(\d{2,3})", text, re.I)
    if m:
        vitals["systolic_bp_mmhg"] = int(m.group(1))
        vitals["diastolic_bp_mmhg"] = int(m.group(2))

    m = re.search(r"(?:spo2|oxygen saturation|sat)\s*(?:of|is|:)?\s*(\d{2,3})\s*%?", text, re.I)
    if m:
        vitals["spo2_pct"] = float(m.group(1))

    return vitals


def _extract_symptoms(text: str) -> list[dict]:
    lower = text.lower()
    symptoms: list[dict] = []
    for keyword in _SYMPTOM_KEYWORDS:
        idx = lower.find(keyword)
        if idx == -1:
            continue
        window = _nearby_window(lower, idx)
        symptom: dict = {"name": keyword}

        duration_match = re.search(r"(\d+(?:\.\d+)?)\s*(hour|hours|day|days|week|weeks)", window)
        if duration_match:
            value = float(duration_match.group(1))
            unit = duration_match.group(2)
            symptom["duration_days"] = round(value * _DURATION_UNIT_TO_DAYS[unit], 2)

        severity_match = re.search(r"severity\D{0,5}(\d{1,2})", window)
        if severity_match:
            symptom["severity"] = min(10, int(severity_match.group(1)))
        else:
            for word, score in _SEVERITY_WORDS.items():
                if word in window:
                    symptom["severity"] = score
                    break

        symptoms.append(symptom)
    return symptoms


def _extract_history(text: str) -> list[dict]:
    history = []
    for match in _HISTORY_PATTERN.finditer(text):
        item: dict = {"condition": match.group(1).strip()}
        if match.group(2):
            item["diagnosed_year"] = int(match.group(2))
        history.append(item)
    return history


def extract_patient_record(text: str, *, patient_id: str) -> ExtractionResult:
    """Extract vitals/symptoms/history from `text` and validate the result
    against `clinical_core.schemas.validate_patient_record` before handing
    it back — acceptance criterion "Extraction output passes clinical_core
    schema validation before being persisted"."""
    vitals = _extract_vitals(text)
    symptoms = _extract_symptoms(text)
    history = _extract_history(text)

    missing = tuple(
        group
        for group, found in (("vitals", vitals), ("symptoms", symptoms), ("history", history))
        if not found
    )

    payload = {
        "patient_id": patient_id,
        "vitals": vitals,
        "symptoms": symptoms,
        "history": history,
    }
    try:
        record = validate_patient_record(payload)
    except PatientRecordValidationError as exc:
        return ExtractionResult(
            record=None,
            missing_fields=missing,
            validation_errors=tuple(f"{e.field}: {e.message}" for e in exc.errors),
        )
    return ExtractionResult(record=record, missing_fields=missing)
