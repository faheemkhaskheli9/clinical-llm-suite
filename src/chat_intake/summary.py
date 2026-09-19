"""Doctor-facing intake summary generation (issue #15).

Generated once a Chat Intake session completes, from the record
`dag_extraction` already extracted from the conversation -- reuses
`dag_extraction.summarization.summarize_record` (issue #9's deterministic,
no-real-LLM template assembly) for the clinical-fact portion rather than a
second, divergent summarizer, and frames it with the patient id and turn
count a doctor needs to orient before reading further.

Generation is deliberately allowed to fail loudly (`SummaryGenerationError`)
on a session with nothing worth summarizing; `conversation.submit_turn` --
not this module -- is responsible for catching that and still saving the
intake record (acceptance criterion: a summary failure must never block the
record itself from being saved), the same division of responsibility
`dag_extraction.pipeline` already uses for `SummarizationError`.
"""
from __future__ import annotations

from dataclasses import dataclass

from clinical_core.schemas import PatientRecord
from dag_extraction.summarization import SummarizationError, summarize_record


class SummaryGenerationError(Exception):
    """Raised when a doctor-facing summary cannot be produced for a session."""


@dataclass(frozen=True)
class IntakeSummary:
    text: str
    turn_count: int


def generate_intake_summary(record: PatientRecord, *, turn_count: int) -> IntakeSummary:
    """Build a doctor-facing summary of `record` (already validated/extracted
    from a session's conversation) plus how many turns it took to gather it.

    Raises `SummaryGenerationError` if `record` has nothing to summarize
    (turn_count < 1, or `summarize_record` finds no vitals/symptoms/history)
    -- callers must catch this rather than let it propagate."""

    if turn_count < 1:
        raise SummaryGenerationError("Cannot summarize a session with no turns.")

    try:
        clinical = summarize_record(record)
    except SummarizationError as exc:
        raise SummaryGenerationError(str(exc)) from exc

    text = f"Intake for patient {record.patient_id} across {turn_count} turn(s). {clinical}"
    return IntakeSummary(text=text, turn_count=turn_count)
