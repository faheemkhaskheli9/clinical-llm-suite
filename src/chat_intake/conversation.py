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

Follow-up questions are mostly a fixed, ordered list of the missing field
groups (one question per group) — the loop still needs a deliberate
termination rule (knowledge-base "stateful agentic run lifecycle" pattern:
combine a semantic-completion check with a hard iteration cap rather than
relying on either alone): stop once every field group has something
extracted, or after MAX_TURNS, whichever comes first.

Symptoms are the one field group with a dynamic follow-up (issue #12): once
the patient has named a symptom but its duration/severity is still missing,
the next question targets that specific symptom (`_adaptive_symptom_followup`)
instead of the generic "what symptoms" question — the question depends on
what the patient already said, not a fixed script. A named symptom with no
matching follow-up rule falls back to the ordinary FIELD_ORDER question
rather than raising.

Issue #14: once a turn completes the session, a RAG-backed recommendation
(`recommendations.recommend_for_record`) is generated from the extracted
record and returned alongside it -- `None` only when extraction itself
found nothing valid to build a record from (there is no patient data to
recommend on), never omitted just because retrieval found no matching
reference chunks (that case still returns a clearly-labeled generic
`Recommendation`, per `recommendations.py`).

Issue #15: completion also generates a doctor-facing summary
(`summary.generate_intake_summary`) from the same extracted record. Unlike
the recommendation, summary generation is allowed to raise
(`SummaryGenerationError`) -- this module is what guarantees a summary
failure never blocks `extraction_record`/`status` from being saved: the
call is wrapped so any failure is logged and leaves `summary_text` `None`
rather than aborting the completing `save()`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from dag_extraction.extraction import extract_patient_record, extract_symptoms
from dag_extraction.models import ExtractionRecord
from dag_extraction.pipeline import run_pipeline

from .models import ChatSession, ChatTurn
from .recommendations import Recommendation, recommend_for_record
from .summary import IntakeSummary, SummaryGenerationError, generate_intake_summary

logger = logging.getLogger(__name__)

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

# One targeted follow-up per keyword `dag_extraction.extraction` knows how to
# spot (mirrors its `_SYMPTOM_KEYWORDS`). Keyed by symptom name so a symptom
# `extract_symptoms` finds but this dict has no rule for (there is no such
# keyword today, but a future extraction-side addition could outpace this
# list) falls back to the generic question rather than raising a KeyError.
_SYMPTOM_FOLLOWUPS: dict[str, str] = {
    "cough": "How long have you had that cough, and does it produce anything?",
    "fever": "How high has your fever gotten, and how long has it lasted?",
    "headache": "How severe is the headache -- mild, moderate, or severe?",
    "nausea": "How long has the nausea lasted?",
    "fatigue": "How long have you been feeling fatigued?",
    "vomiting": "How many times have you vomited, and over what period?",
    "dizziness": "How long have you felt dizzy, and does it come and go?",
    "chest pain": "How severe is the chest pain, and does it radiate anywhere?",
    "shortness of breath": (
        "Does the shortness of breath happen at rest or only with activity, "
        "and how long has it lasted?"
    ),
    "sore throat": "How long has your throat been sore?",
}


@dataclass
class TurnResult:
    complete: bool
    missing_fields: tuple[str, ...]
    record: ExtractionRecord | None
    recommendation: Recommendation | None = None
    summary: IntakeSummary | None = None


def start_session(patient_id: str) -> ChatSession:
    return ChatSession.objects.create(patient_id=patient_id, status=ChatSession.Status.ACTIVE)


def _combined_text(session: ChatSession) -> str:
    return "\n".join(turn.patient_text for turn in session.turns.order_by("turn_index"))


def _adaptive_symptom_followup(text: str) -> str | None:
    """A named symptom with neither `duration_days` nor `severity` yet gets
    a targeted follow-up instead of the generic "what symptoms" question —
    depends on what the patient already said, not a fixed script. Returns
    `None` (no matching rule, or every named symptom already has detail) so
    the caller falls back to the ordinary FIELD_ORDER question instead of
    raising."""
    for symptom in extract_symptoms(text):
        if symptom.get("duration_days") is None and symptom.get("severity") is None:
            return _SYMPTOM_FOLLOWUPS.get(symptom["name"])
    return None


def _next_question(text: str, missing_fields: tuple[str, ...]) -> str | None:
    if "symptoms" not in missing_fields:
        adaptive = _adaptive_symptom_followup(text)
        if adaptive is not None:
            return adaptive
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
    combined = _combined_text(session)
    check = extract_patient_record(combined, patient_id=session.patient_id)
    return _next_question(combined, check.missing_fields)


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
    recommendation = recommend_for_record(result.record) if result.record is not None else None

    summary: IntakeSummary | None = None
    if result.record is not None:
        try:
            summary = generate_intake_summary(result.record, turn_count=turns_used)
        except SummaryGenerationError:
            logger.exception(
                "Failed to generate doctor-facing summary for session %s; "
                "saving the intake record without one.",
                session.id,
            )

    session.status = ChatSession.Status.COMPLETE
    session.extraction_record = record
    if recommendation is not None:
        session.recommendation_text = recommendation.text
        session.recommendation_grounded = recommendation.grounded
        session.recommendation_sources = [vars(ref) for ref in recommendation.sources]
    if summary is not None:
        session.summary_text = summary.text
    session.save(
        update_fields=[
            "status",
            "extraction_record",
            "recommendation_text",
            "recommendation_grounded",
            "recommendation_sources",
            "summary_text",
        ]
    )

    return TurnResult(
        complete=True,
        missing_fields=result.missing_fields,
        record=record,
        recommendation=recommendation,
        summary=summary,
    )
