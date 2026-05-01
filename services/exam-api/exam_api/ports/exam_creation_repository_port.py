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
        """Persist a newly created exam.

        Must write two items atomically:
          - PK=EXAM#{exam_id}           SK=METADATA          (exam data + created_at)
          - PK=TEACHER#{teacher_id}     SK=EXAM#{exam_id}    (ownership edge + created_at)

        TODO(#13): add description and subject once the shared Exam model is extended.
        """
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
