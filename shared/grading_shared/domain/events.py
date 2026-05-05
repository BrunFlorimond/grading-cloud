"""Domain events for the grading pipeline."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from .models import StrictModel


class EventType(StrEnum):
    SPREADSHEET_CONVERTED = "spreadsheet_converted"
    CORRECTION_BATCH_STARTED = "correction_batch_started"
    CORRECTION_BATCH_COMPLETED = "correction_batch_completed"
    HARMONIZATION_BATCH_STARTED = "harmonization_batch_started"
    HARMONIZATION_BATCH_COMPLETED = "harmonization_batch_completed"
    PDF_GENERATED = "pdf_generated"
    PIPELINE_COMPLETED = "pipeline_completed"
    PIPELINE_FAILED = "pipeline_failed"


class PipelineEvent(StrictModel):
    event_id: str
    event_type: EventType
    exam_id: str
    occurred_at: str
    student_id: str | None = None
    batch_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
