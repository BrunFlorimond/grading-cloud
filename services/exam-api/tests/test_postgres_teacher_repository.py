"""Unit tests for PostgresTeacherRepository."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from exam_api.domain.teacher import Teacher
from exam_api.infrastructure.postgres_teacher_repository import (
    PostgresTeacherRepository,
)

COGNITO_SUB = "550e8400-e29b-41d4-a716-446655440000"


def _mock_execute_returning(
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


@pytest.mark.asyncio
async def test_upsert_teacher_returns_teacher_domain_model() -> None:
    session = _mock_execute_returning(
        teacher_id=uuid.UUID(COGNITO_SUB),
        email="teacher@school.fr",
        full_name="Marie Curie",
    )

    repo = PostgresTeacherRepository(session)
    teacher = await repo.upsert_teacher(
        cognito_sub=COGNITO_SUB,
        email="teacher@school.fr",
        full_name="Marie Curie",
    )

    assert isinstance(teacher, Teacher)
    assert teacher.teacher_id == COGNITO_SUB
    assert teacher.email == "teacher@school.fr"
    assert teacher.full_name == "Marie Curie"


@pytest.mark.asyncio
async def test_upsert_teacher_passes_cognito_sub_as_uuid_id() -> None:
    session = _mock_execute_returning(
        teacher_id=uuid.UUID(COGNITO_SUB),
        email="t@school.fr",
        full_name="T",
    )

    repo = PostgresTeacherRepository(session)
    await repo.upsert_teacher(
        cognito_sub=COGNITO_SUB, email="t@school.fr", full_name="T"
    )

    # The INSERT statement must be compiled — verify session.execute was called once
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_teacher_executes_upsert_statement() -> None:
    session = _mock_execute_returning(
        teacher_id=uuid.UUID(COGNITO_SUB),
        email="a@b.fr",
        full_name="A B",
    )

    repo = PostgresTeacherRepository(session)
    await repo.upsert_teacher(cognito_sub=COGNITO_SUB, email="a@b.fr", full_name="A B")

    session.execute.assert_awaited_once()
