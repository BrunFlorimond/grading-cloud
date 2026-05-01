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
