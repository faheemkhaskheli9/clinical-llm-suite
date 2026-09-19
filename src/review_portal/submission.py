"""Shared submission path into the review queue (issue #16).

Both `chat_intake` and `dag_extraction` call this once they have a completed
draft summary, instead of each hand-rolling its own validate-then-persist
logic (or duplicating what `api_views._create` already does for the HTTP
API) -- one place validates against `clinical_core.review.ReviewItem` (the
schema every feature app submits against) and persists into
`review_portal.models.ReviewItem`.
"""
from __future__ import annotations

from clinical_core.review import ReviewItem as ReviewItemSchema

from .models import ReviewItem


def submit_review_item(
    *,
    source: str,
    patient_id: str,
    summary: str,
    assigned_to: str | None = None,
) -> ReviewItem:
    """Validate `source`/`patient_id`/`summary` against the shared schema,
    then persist a `review_portal.models.ReviewItem` row.

    Raises `pydantic.ValidationError` if the fields don't satisfy
    `clinical_core.review.ReviewItem` (e.g. an empty summary) -- feature
    apps are expected to only call this once they have a genuinely
    completed draft, so this is a programming-error signal, not a normal
    control-flow branch.
    """
    validated = ReviewItemSchema(
        source=source,
        patient_id=patient_id,
        summary=summary,
        assigned_to=assigned_to,
    )
    return ReviewItem.objects.create(
        source=validated.source,
        patient_id=validated.patient_id,
        summary=validated.summary,
        assigned_to=validated.assigned_to,
    )
