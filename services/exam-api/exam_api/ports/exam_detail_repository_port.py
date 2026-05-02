"""Port for querying exam detail and per-student pipeline status."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from grading_shared.domain.models import StrictModel


class StatusCounts(StrictModel):
    """Counts of students grouped by submission_status."""

    pending: int


class ExamDetail(StrictModel):
    """Exam metadata enriched with pipeline timestamps and per-status student counts."""

    exam_id: str
    teacher_id: str
    title: str
    status: str
    description: str | None = None
    subject: str | None = None
    created_at: str | None = None
    pipeline_started_at: str | None = None
    pipeline_completed_at: str | None = None
    status_counts: StatusCounts


class StudentPipelineStatus(StrictModel):
    """Per-student pipeline view returned by GET /exams/{exam_id}/students."""

    student_id: str
    nom: str
    prenom: str
    classe: str
    submission_status: str
    pdf_available: bool


class StudentPipelinePage(StrictModel):
    """One page of per-student pipeline statuses."""

    items: list[StudentPipelineStatus]
    next_cursor: str | None


@runtime_checkable
class ExamDetailRepositoryPort(Protocol):
    async def get_exam_detail(
        self,
        *,
        exam_id: str,
    ) -> ExamDetail:
        """Return exam metadata + pipeline timestamps + per-status student counts.

        Raises ExamNotFoundError when exam_id does not exist.
        """
        ...

    async def list_exam_student_statuses(
        self,
        *,
        exam_id: str,
        limit: int,
        cursor: str | None,
    ) -> StudentPipelinePage:
        """Return a paginated list of students with pipeline status and PDF availability."""
        ...
