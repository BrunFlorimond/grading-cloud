"""Unit tests for PostgresUserIdentityRepository."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from exam_api.domain.errors import InvalidUserIdentitySubjectError
from exam_api.domain.student import Student
from exam_api.domain.teacher import Teacher
from exam_api.infrastructure.postgres_user_identity_repository import (
    PostgresUserIdentityRepository,
)

COGNITO_SUB = "550e8400-e29b-41d4-a716-446655440000"


def _mock_execute_teacher(
    teacher_id: uuid.UUID, email: str, full_name: str
) -> AsyncMock:
    row = MagicMock()
    row.id = teacher_id
    row.email = email
    row.full_name = full_name
    result = MagicMock()
    result.one.return_value = row
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    return session


def _mock_execute_student(student_id: uuid.UUID, email: str) -> AsyncMock:
    row = MagicMock()
    row.id = student_id
    row.email = email
    result = MagicMock()
    result.one.return_value = row
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_upsert_teacher_returns_teacher_domain_model() -> None:
    session = _mock_execute_teacher(
        teacher_id=uuid.UUID(COGNITO_SUB),
        email="teacher@school.fr",
        full_name="Marie Curie",
    )
    repository = PostgresUserIdentityRepository(session)

    teacher = await repository.upsert_teacher(
        cognito_sub=COGNITO_SUB,
        email="teacher@school.fr",
        full_name="Marie Curie",
    )

    assert isinstance(teacher, Teacher)
    assert teacher.teacher_id == COGNITO_SUB
    assert str(teacher.email) == "teacher@school.fr"
    assert teacher.full_name == "Marie Curie"
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_student_returns_student_domain_model() -> None:
    session = _mock_execute_student(
        student_id=uuid.UUID(COGNITO_SUB),
        email="student@school.fr",
    )
    repository = PostgresUserIdentityRepository(session)

    student = await repository.upsert_student(
        cognito_sub=COGNITO_SUB,
        email="student@school.fr",
    )

    assert isinstance(student, Student)
    assert student.student_id == COGNITO_SUB
    assert str(student.email) == "student@school.fr"
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_teacher_raises_on_invalid_cognito_sub() -> None:
    session = AsyncMock()
    repository = PostgresUserIdentityRepository(session)

    with pytest.raises(InvalidUserIdentitySubjectError):
        await repository.upsert_teacher(
            cognito_sub="not-a-uuid",
            email="teacher@school.fr",
            full_name="Marie Curie",
        )

    session.execute.assert_not_called()

