"""Multi-turn patient chat intake (issue #11).

`clinical-ai-assistant`'s own Implementation Plan never got past Phase 1
(conversation schema) and Phase 4 (RAG ingestion) — Phase 2 ("chat intake
flow with dynamic follow-up question logic") was never built there, so
there is no chat-loop code to literally port. What *is* reused is
everything that phase would have needed: `clinical_core`'s schema-validated
`PatientRecord` and `dag_extraction`'s extraction/persistence pipeline
(issues #8/#9) — this module drives `dag_extraction.pipeline.run_pipeline`
with accumulated patient text one turn at a time, rather than
re-implementing extraction.

Follow-up questions are a fixed, ordered list of the missing field groups
(one question per group), not an adaptive choice — see issue #12 for
dynamic follow-up logic. The loop still needs a deliberate termination rule
(knowledge-base "stateful agentic run lifecycle" pattern: combine a
semantic-completion check with a hard iteration cap rather than relying on
either alone): stop once every field group has something extracted, or
after MAX_TURNS, whichever comes first.
"""
from __future__ import annotations

from dataclasses import dataclass

from dag_extraction.extraction import extract_patient_record
from dag_extraction.models import ExtractionRecord
from dag_extraction.pipeline import run_pipeline

from .models import ChatSession, ChatTurn

MAX_TURNS = 6

FIELD_ORDER: tuple[str, ...] = ("vitals", "symptoms", "history")

QUESTIONS: dict[str, str] = {
    "vitals": (
        "Can you share your vitals? (e.g. temperature, heart rate, blood "
        "pressure, oxygen saturation)"
    ),
    "symptoms": "What symptoms are you experiencing, and for how long?",
    "history": "Do you have any relevant medical history?",
}

OPENING_QUESTION = QUESTIONS[FIELD_ORDER[0]]


@dataclass
class TurnResult:
    complete: bool
    missing_fields: tuple[str, ...]
    record: ExtractionRecord | None


def start_session(patient_id: str) -> ChatSession:
    return ChatSession.objects.create(patient_id=patient_id, status=ChatSession.Status.ACTIVE)


def _combined_text(session: ChatSession) -> str:
    return "\n".join(turn.patient_text for turn in session.turns.order_by("turn_index"))


def _next_question(missing_fields: tuple[str, ...]) -> str | None:
    for field in FIELD_ORDER:
        if field in missing_fields:
            return QUESTIONS[field]
    return None


def pending_question_for(session: ChatSession) -> str | None:
    """The question to show next, or None once the session is complete."""
    if session.status != ChatSession.Status.ACTIVE:
        return None
    if session.turns.count() == 0:
        return OPENING_QUESTION
    check = extract_patient_record(_combined_text(session), patient_id=session.patient_id)
    return _next_question(check.missing_fields)


def submit_turn(session: ChatSession, patient_text: str) -> TurnResult:
    if session.status != ChatSession.Status.ACTIVE:
        raise ValueError(f"Session {session.id} is not active (status={session.status!r}).")

    turn_index = session.turns.count()
    ChatTurn.objects.create(session=session, turn_index=turn_index, patient_text=patient_text)

    combined = _combined_text(session)
    check = extract_patient_record(combined, patient_id=session.patient_id)
    turns_used = turn_index + 1

    if check.missing_fields and turns_used < MAX_TURNS:
        return TurnResult(complete=False, missing_fields=check.missing_fields, record=None)

    record, result = run_pipeline(combined, patient_id=session.patient_id)
    session.status = ChatSession.Status.COMPLETE
    session.extraction_record = record
    session.save(update_fields=["status", "extraction_record"])

    return TurnResult(complete=True, missing_fields=result.missing_fields, record=record)
