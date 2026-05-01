"""Exam aggregate and status state machine."""

from __future__ import annotations

from enum import StrEnum

from .models import StrictModel


class ExamStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    INGESTION_RUNNING = "ingestion_running"
    CORRECTION_RUNNING = "correction_running"
    HARMONIZATION_RUNNING = "harmonization_running"
    PDF_GENERATION_RUNNING = "pdf_generation_running"
    COMPLETED = "completed"
    FAILED = "failed"


_ALLOWED_TRANSITIONS: dict[ExamStatus, set[ExamStatus]] = {
    ExamStatus.DRAFT: {ExamStatus.READY, ExamStatus.FAILED},
    ExamStatus.READY: {ExamStatus.INGESTION_RUNNING, ExamStatus.FAILED},
    ExamStatus.INGESTION_RUNNING: {ExamStatus.CORRECTION_RUNNING, ExamStatus.FAILED},
    ExamStatus.CORRECTION_RUNNING: {ExamStatus.HARMONIZATION_RUNNING, ExamStatus.FAILED},
    ExamStatus.HARMONIZATION_RUNNING: {ExamStatus.PDF_GENERATION_RUNNING, ExamStatus.FAILED},
    ExamStatus.PDF_GENERATION_RUNNING: {ExamStatus.COMPLETED, ExamStatus.FAILED},
    ExamStatus.COMPLETED: set(),
    ExamStatus.FAILED: set(),
}


class Exam(StrictModel):
    exam_id: str
    teacher_id: str
    title: str
    status: ExamStatus = ExamStatus.DRAFT
    description: str | None = None
    subject: str | None = None
    created_at: str | None = None

    def can_transition_to(self, target_status: ExamStatus) -> bool:
        return target_status in _ALLOWED_TRANSITIONS[self.status]

    def transition_to(self, target_status: ExamStatus) -> None:
        if not self.can_transition_to(target_status):
            raise ValueError(
                f"Invalid exam status transition from {self.status} to {target_status}."
            )
        self.status = target_status

