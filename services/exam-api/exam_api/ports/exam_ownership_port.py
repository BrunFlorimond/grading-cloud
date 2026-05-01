"""Port for verifying that a teacher owns a given exam."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ExamOwnershipPort(Protocol):
    async def verify_teacher_owns_exam(self, *, teacher_id: str, exam_id: str) -> None:
        """Raise ExamNotFoundError if the exam does not exist, ExamOwnershipError if not owned."""
