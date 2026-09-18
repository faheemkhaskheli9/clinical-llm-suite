"""Chat intake session/turn models (issue #11)."""
import uuid

from django.db import models

from dag_extraction.models import ExtractionRecord


class ChatSession(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETE = "complete", "Complete"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient_id = models.CharField(max_length=120, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    extraction_record = models.ForeignKey(
        ExtractionRecord,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="chat_sessions",
    )
    # Issue #14: the RAG-backed recommendation generated once the session
    # completes, persisted so it still renders on a later page load (not
    # just in the response to the completing POST). `recommendation_text`
    # null means no recommendation was generated at all (extraction found
    # nothing valid to recommend on) -- distinct from a *generic* fallback
    # recommendation, which is still non-null text with `grounded=False`.
    recommendation_text = models.TextField(null=True, blank=True)
    recommendation_grounded = models.BooleanField(default=False)
    recommendation_sources = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.id} ({self.patient_id}, {self.status})"


class ChatTurn(models.Model):
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="turns")
    turn_index = models.PositiveIntegerField()
    patient_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["turn_index"]
        constraints = [
            models.UniqueConstraint(fields=["session", "turn_index"], name="unique_turn_index_per_session")
        ]

    def __str__(self) -> str:
        return f"{self.session_id} turn {self.turn_index}"
