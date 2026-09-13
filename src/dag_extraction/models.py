"""Persisted extraction + summary (issue #9): one row per extraction run,
holding the schema-validated structured record alongside the summarization
node's output so a reviewer can read the short summary without re-running
extraction.
"""
import uuid

from django.db import models


class ExtractionRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient_id = models.CharField(max_length=120, db_index=True)
    source_text = models.TextField()
    extracted_record = models.JSONField()
    missing_fields = models.JSONField(default=list)
    summary = models.TextField(null=True, blank=True)
    summarization_failed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.id} ({self.patient_id})"
