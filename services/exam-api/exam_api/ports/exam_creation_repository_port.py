"""Port for exam creation and paginated listing."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from grading_shared.domain.exam import Exam
from grading_shared.domain.models import StrictModel


class ExamPage(StrictModel):
    """One page of exam results returned by list_teacher_exams."""

    items: list[Exam]
    next_cursor: str | None


@runtime_checkable
class ExamCreationRepositoryPort(Protocol):
    async def create_exam(self, exam: Exam) -> None:
        """Persist a newly created exam (metadata, ownership edge, and time-sorted list edge)."""
        ...

    async def list_teacher_exams(
        self,
        *,
        teacher_id: str,
        limit: int,
        cursor: str | None,
    ) -> ExamPage:
        """Return a paginated page of exams owned by teacher_id, ordered by created_at desc."""
        ...
