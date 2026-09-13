"""Django-persisted review queue (issue #5), ported from
`clinical-ai-review-platform`'s `reviews.models.ReviewItem` — same shape
(`public_id`/status/source/summary/timestamps), extended with the fields
`clinical_core.review.ReviewItem` (the in-memory contract this app implements
against, per that module's docstring) already defines: `patient_id`,
`quality_rating`, `reviewer_comments`, `assigned_to`.

Every sibling status field here is bounded the same way `clinical_core`
bounds them (rule: a check applied to one field applies to its siblings) —
`quality_rating` gets the same 1-5 range as the in-memory model.
"""
import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ReviewItem(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=120, db_index=True)
    patient_id = models.CharField(max_length=120, db_index=True)
    summary = models.TextField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    quality_rating = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    reviewer_comments = models.TextField(null=True, blank=True)
    assigned_to = models.CharField(max_length=150, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.id} ({self.status})"
