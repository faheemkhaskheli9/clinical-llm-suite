"""Summarization node (issue #9): condenses a validated `PatientRecord` into
a short clinical summary, running after field extraction in the DAG.

Deterministic template assembly, not an LLM call — the same CPU-only /
no-paid-API stand-in extraction.py uses; a production version would swap
`summarize_record` for an LLM-backed call behind the same signature.
"""
from __future__ import annotations

from clinical_core.schemas import PatientRecord


class SummarizationError(Exception):
    """Raised when there is nothing in the record worth summarizing.

    Callers must catch this and still persist the extracted record — a
    summarization failure must never block the underlying extraction from
    being saved (issue #9 acceptance criterion).
    """


def summarize_record(record: PatientRecord) -> str:
    pieces: list[str] = []

    v = record.vitals
    vital_bits = []
    if v.temperature_c is not None:
        vital_bits.append(f"temp {v.temperature_c}C")
    if v.heart_rate_bpm is not None:
        vital_bits.append(f"HR {v.heart_rate_bpm} bpm")
    if v.systolic_bp_mmhg is not None and v.diastolic_bp_mmhg is not None:
        vital_bits.append(f"BP {v.systolic_bp_mmhg}/{v.diastolic_bp_mmhg}")
    if v.spo2_pct is not None:
        vital_bits.append(f"SpO2 {v.spo2_pct}%")
    if vital_bits:
        pieces.append("Vitals: " + ", ".join(vital_bits) + ".")

    if record.symptoms:
        symptom_bits = []
        for s in record.symptoms:
            bit = s.name
            if s.duration_days is not None:
                bit += f" ({s.duration_days}d)"
            if s.severity is not None:
                bit += f", severity {s.severity}/10"
            symptom_bits.append(bit)
        pieces.append("Symptoms: " + "; ".join(symptom_bits) + ".")

    if record.history:
        history_bits = [
            h.condition + (f" ({h.diagnosed_year})" if h.diagnosed_year else "")
            for h in record.history
        ]
        pieces.append("History: " + ", ".join(history_bits) + ".")

    if not pieces:
        raise SummarizationError(
            "Nothing to summarize: no vitals, symptoms, or history were extracted."
        )

    return " ".join(pieces)
