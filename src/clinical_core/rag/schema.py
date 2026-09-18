"""Common normalized document schema for the medical reference knowledge base.

Ported from clinical-ai-assistant's src/rag/schema.py (issue #13). Every
fetcher (MedlinePlus, openFDA, MedQuAD, ...) maps its source-specific format
into this shape before anything is chunked/embedded, so downstream RAG code
never needs to know which source a passage came from.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocType(str, Enum):
    """What kind of medical concept a document describes."""

    DISEASE = "disease"
    MEDICATION = "medication"
    QA = "qa"


class SourceDocument(BaseModel):
    """One retrievable unit of medical reference content, prior to chunking.

    ``id`` must be stable and globally unique (fetchers namespace it with
    their source, e.g. ``"medlineplus:diabetes"``) so re-ingestion overwrites
    rather than duplicates a record once this is chunked into a vector store.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, description="Stable id, unique across all sources")
    doc_type: DocType = Field(..., description="disease | medication | qa")
    source: Literal["medlineplus", "openfda", "medquad"] = Field(
        ..., description="Which fetcher produced this document"
    )
    title: str = Field(..., min_length=1, description="Condition/drug/question title")
    section: str = Field(
        default="overview",
        description="Sub-section within the source record, e.g. 'dosage', 'qa_pair'",
    )
    text: str = Field(..., min_length=1, description="The retrievable passage text")
    url: str = Field(default="", description="Citation URL back to the source record")
    metadata: dict[str, str] = Field(
        default_factory=dict, description="Source-specific extras (query term, focus area, ...)"
    )
