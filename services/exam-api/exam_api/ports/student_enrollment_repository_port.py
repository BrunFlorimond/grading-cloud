"""Port for persisting and querying enrolled students within an exam."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from grading_shared.domain.models import StrictModel

from exam_api.domain.student import EnrolledStudent


class EnrolledStudentPage(StrictModel):
    """One page of enrolled students returned by list_exam_students."""

    items: list[EnrolledStudent]
    next_cursor: str | None


@runtime_checkable
class StudentEnrollmentRepositoryPort(Protocol):
    async def add_students(
        self,
        *,
        exam_id: str,
        students: list[EnrolledStudent],
    ) -> list[EnrolledStudent]:
        """Persist a batch of enrolled students.

        Raises DuplicateStudentError when any student_id already exists in this exam.
        """
        ...

    async def list_exam_students(
        self,
        *,
        exam_id: str,
        limit: int,
        cursor: str | None,
    ) -> EnrolledStudentPage:
        """Return a paginated list of students enrolled in exam_id."""
        ...
