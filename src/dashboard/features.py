"""The 3 feature-picker entries shown on the dashboard.

A plain list for now — Phase 1 only needs a shell. Once chat_intake,
dag_extraction, and review_portal land as real feature apps (Phases 2-4),
this becomes the seed for the registry pattern docs/architecture.md
describes (mirroring medical-imaging-suite's BaseImagingTask/@register_task)
rather than a shape that needs reworking.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Feature:
    slug: str
    title: str
    description: str
    url_name: str | None = None
    """Name of the real feature app's own URL to redirect to once it exists
    (Phases 2-4). None means it isn't built yet, so the dashboard link falls
    back to `feature_stub`'s placeholder page."""


FEATURES: tuple[Feature, ...] = (
    Feature(
        slug="chat-intake",
        title="Chat Intake",
        description=(
            "Conversational patient intake with dynamic follow-up questions, "
            "structured extraction, and RAG-backed recommendations."
        ),
    ),
    Feature(
        slug="dag-extraction",
        title="DAG Extraction",
        description=(
            "Schema-validated field extraction (vitals, symptoms, history) "
            "from a raw conversation via a PromptFlow-style DAG."
        ),
        url_name="dag-extraction",
    ),
    Feature(
        slug="review-portal",
        title="Review Portal",
        description=(
            "Human-in-the-loop review queue for AI-generated clinical "
            "summaries: accept/reject, quality rating, reviewer comments."
        ),
        url_name="review-queue",
    ),
)

FEATURES_BY_SLUG: dict[str, Feature] = {f.slug: f for f in FEATURES}
