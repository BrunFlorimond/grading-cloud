"""Port for local SQL identity upserts linked to Cognito users."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from exam_api.domain.student import Student
from exam_api.domain.teacher import Teacher


@runtime_checkable
class UserIdentityRepositoryPort(Protocol):
    async def upsert_teacher(
        self, *, cognito_sub: str, email: str, full_name: str
    ) -> Teacher:
        """Create or update a teacher row identified by Cognito sub."""
        ...

    async def upsert_student(self, *, cognito_sub: str, email: str) -> Student:
        """Create or update a student row identified by Cognito sub."""
        ...
