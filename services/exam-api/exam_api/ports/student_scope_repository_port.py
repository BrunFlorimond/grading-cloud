"""Port for persisting student authorization scope."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from exam_api.domain.student import Student


@runtime_checkable
class StudentScopeRepositoryPort(Protocol):
    async def upsert_student_scope(
        self, *, student: Student, teacher_id: str, external_student_id: str
    ) -> None:
        """Persist student ownership scope for downstream authorization checks."""

    async def get_student_scope(self, *, exam_id: str, student_sub: str) -> Student | None:
        """Load a student scope record by exam and Cognito subject."""
