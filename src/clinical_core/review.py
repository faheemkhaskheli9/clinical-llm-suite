"""
Review-item model and in-memory queue, shared by every feature app that
submits a draft clinical summary for human review (`review_portal` will wrap
this in a Django app in Phase 2 per docs/architecture.md).

Pure Pydantic + stdlib — no Django import — so `chat_intake` and
`dag_extraction` can submit into the same queue in Phase 4/5 without either
depending on the other's stack, and so the model is usable in tests and
scripts before a database exists at all (README.md Section 2 pipeline:
"Review Queue (accept/reject/rate/comment)").
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

ReviewStatus = Literal["pending", "accepted", "rejected"]

REVIEW_STATUSES: tuple[ReviewStatus, ...] = ("pending", "accepted", "rejected")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReviewItem(BaseModel):
    """One draft clinical summary awaiting (or having received) human review.

    `source` records which feature app produced it (e.g. "chat_intake",
    "dag_extraction") so the queue stays usable independent of which one
    created a given item — nothing here reads or depends on either app.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    source: str = Field(min_length=1)
    patient_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    status: ReviewStatus = "pending"
    quality_rating: int | None = Field(default=None, ge=1, le=5)
    reviewer_comments: str | None = None
    assigned_to: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class ReviewItemNotFoundError(KeyError):
    """Raised when a queue operation targets an id that isn't in the queue."""

    def __init__(self, item_id: uuid.UUID):
        self.item_id = item_id
        super().__init__(f"No review item with id {item_id}")


class ReviewQueue:
    """In-memory review queue: submit items, filter by status/assignment,
    and record a reviewer's decision (rule 6: `id` comes from `uuid.uuid4`,
    never a value that can collide across feature apps).

    Phase 2 wraps this shape in Django models/views backed by a real
    database (README.md Section 12's `POST/GET /api/review-items/`); this
    class defines the schema and filtering contract those views implement
    against, and is usable standalone by tests and any feature app today.
    """

    def __init__(self) -> None:
        self._items: dict[uuid.UUID, ReviewItem] = {}

    def submit(
        self,
        *,
        source: str,
        patient_id: str,
        summary: str,
        assigned_to: str | None = None,
    ) -> ReviewItem:
        item = ReviewItem(
            source=source,
            patient_id=patient_id,
            summary=summary,
            assigned_to=assigned_to,
        )
        self._items[item.id] = item
        return item

    def get(self, item_id: uuid.UUID) -> ReviewItem:
        try:
            return self._items[item_id]
        except KeyError:
            raise ReviewItemNotFoundError(item_id) from None

    def list(
        self,
        *,
        status: ReviewStatus | None = None,
        assigned_to: str | None = None,
    ) -> list[ReviewItem]:
        """Filter by status and/or assignment (acceptance criterion: "Queue
        schema supports filtering by status and assignment"). Newest first,
        matching the review-queue UI's expected ordering."""
        items = self._items.values()
        if status is not None:
            items = (i for i in items if i.status == status)
        if assigned_to is not None:
            items = (i for i in items if i.assigned_to == assigned_to)
        return sorted(items, key=lambda i: i.created_at, reverse=True)

    def assign(self, item_id: uuid.UUID, reviewer: str) -> ReviewItem:
        item = self.get(item_id)
        updated = item.model_copy(
            update={"assigned_to": reviewer, "updated_at": _utcnow()}
        )
        self._items[item_id] = updated
        return updated

    def decide(
        self,
        item_id: uuid.UUID,
        *,
        status: Literal["accepted", "rejected"],
        quality_rating: int | None = None,
        reviewer_comments: str | None = None,
    ) -> ReviewItem:
        """Record a reviewer's accept/reject decision, optional 1-5 quality
        rating, and optional comments. Validated the same way regardless of
        which feature app's summary this item wraps."""
        item = self.get(item_id)
        update = {"status": status, "updated_at": _utcnow()}
        if quality_rating is not None:
            update["quality_rating"] = quality_rating
        if reviewer_comments is not None:
            update["reviewer_comments"] = reviewer_comments
        updated = item.model_validate({**item.model_dump(), **update})
        self._items[item_id] = updated
        return updated
