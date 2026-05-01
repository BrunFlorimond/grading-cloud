"""Port for persisting student authorization scope."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from exam_api.domain.student import Student


@runtime_checkable
class StudentScopeRepositoryPort(Protocol):
    def upsert_student_scope(
        self, *, student: Student, teacher_id: str, external_student_id: str
    ) -> None:
        """Persist student ownership scope for downstream authorization checks."""

    def get_student_scope(self, *, exam_id: str, student_sub: str) -> Student | None:
        """Load a student scope record by exam and Cognito subject."""

    def get_exam_id_for_student_sub(self, *, student_sub: str) -> str | None:
        """Load the exam scope currently bound to a Cognito student subject."""
