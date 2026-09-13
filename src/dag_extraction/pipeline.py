"""Extraction -> summarization DAG (issue #9): runs the summarization node
after field extraction and persists both together. A summarization failure
is caught and recorded (`summarization_failed=True`, `summary=None`) rather
than raised through -- it must never block the extraction itself from being
saved.
"""
from __future__ import annotations

from .extraction import ExtractionResult, extract_patient_record
from .models import ExtractionRecord
from .summarization import SummarizationError, summarize_record


def run_pipeline(text: str, *, patient_id: str) -> tuple[ExtractionRecord | None, ExtractionResult]:
    """Extract structured fields, then summarize, persisting the result.

    Returns `(None, result)` when extraction itself failed schema
    validation (nothing valid to persist yet), or `(record, result)` once
    the extracted record has been saved -- summarization succeeding or not.
    """
    result = extract_patient_record(text, patient_id=patient_id)
    if result.record is None:
        return None, result

    summary: str | None = None
    summarization_failed = False
    try:
        summary = summarize_record(result.record)
    except SummarizationError:
        summarization_failed = True

    record = ExtractionRecord.objects.create(
        patient_id=patient_id,
        source_text=text,
        extracted_record=result.record.model_dump(mode="json"),
        missing_fields=list(result.missing_fields),
        summary=summary,
        summarization_failed=summarization_failed,
    )
    return record, result
