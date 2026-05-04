"""Unit tests for PostgresAssignmentRepository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from grading_shared.domain.exam import Exam, ExamStatus
from sqlalchemy.exc import IntegrityError

from exam_api.domain.errors import (
    ExamConfigWrongStatusError,
    ExamCreationConflictError,
    ExamNotFoundError,
    InvalidExamListCursorError,
)
from exam_api.infrastructure.orm import AssignmentORM, TeacherAssignmentORM
from exam_api.infrastructure.postgres_assignment_repository import (
    PostgresAssignmentRepository,
)

EXAM_ID = "550e8400-e29b-41d4-a716-446655440000"
TEACHER_ID = "660e8400-e29b-41d4-a716-446655440000"


def _mock_assignment(
    exam_id: str = EXAM_ID,
    teacher_id: str = TEACHER_ID,
    title: str = "Algebra",
    status: str = "created",
    created_at: datetime | None = None,
) -> MagicMock:
    row = MagicMock(spec=AssignmentORM)
    row.id = uuid.UUID(exam_id)
    row.created_by = uuid.UUID(teacher_id)
    row.title = title
    row.status = status
    row.description = None
    row.subject = None
    row.created_at = created_at
    return row


def _session_with_execute(rows: list) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    return session


# ── create_exam ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_exam_adds_assignment_and_teacher_assignment() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.add = MagicMock()

    repo = PostgresAssignmentRepository(session)
    exam = Exam(exam_id=EXAM_ID, teacher_id=TEACHER_ID, title="Algebra", status=ExamStatus.CREATED)

    await repo.create_exam(exam)

    assert session.add.call_count == 2
    first_arg = session.add.call_args_list[0].args[0]
    second_arg = session.add.call_args_list[1].args[0]
    assert isinstance(first_arg, AssignmentORM)
    assert isinstance(second_arg, TeacherAssignmentORM)


@pytest.mark.asyncio
async def test_create_exam_raises_conflict_when_exam_exists() -> None:
    row = _mock_assignment()
    session = AsyncMock()
    session.get = AsyncMock(return_value=row)

    repo = PostgresAssignmentRepository(session)
    exam = Exam(exam_id=EXAM_ID, teacher_id=TEACHER_ID, title="Algebra", status=ExamStatus.CREATED)

    with pytest.raises(ExamCreationConflictError):
        await repo.create_exam(exam)


@pytest.mark.asyncio
async def test_create_exam_stores_correct_teacher_and_title() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.add = MagicMock()

    repo = PostgresAssignmentRepository(session)
    exam = Exam(
        exam_id=EXAM_ID,
        teacher_id=TEACHER_ID,
        title="Midterm",
        status=ExamStatus.CREATED,
        description="Chapitre 1",
        subject="Math",
    )

    await repo.create_exam(exam)

    assignment: AssignmentORM = session.add.call_args_list[0].args[0]
    assert assignment.title == "Midterm"
    assert assignment.created_by == uuid.UUID(TEACHER_ID)
    assert assignment.description == "Chapitre 1"
    assert assignment.subject == "Math"


# ── list_teacher_exams ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_teacher_exams_returns_exam_domain_objects() -> None:
    row = _mock_assignment()
    session = _session_with_execute([row])

    repo = PostgresAssignmentRepository(session)
    page = await repo.list_teacher_exams(teacher_id=TEACHER_ID, limit=10, cursor=None)

    assert len(page.items) == 1
    assert page.items[0].exam_id == EXAM_ID
    assert page.items[0].title == "Algebra"


@pytest.mark.asyncio
async def test_list_teacher_exams_next_cursor_set_when_page_full() -> None:
    rows = [_mock_assignment(exam_id=str(uuid.uuid4())) for _ in range(5)]
    session = _session_with_execute(rows)

    repo = PostgresAssignmentRepository(session)
    page = await repo.list_teacher_exams(teacher_id=TEACHER_ID, limit=5, cursor=None)

    assert page.next_cursor == "5"


@pytest.mark.asyncio
async def test_list_teacher_exams_next_cursor_none_on_last_page() -> None:
    rows = [_mock_assignment(exam_id=str(uuid.uuid4())) for _ in range(3)]
    session = _session_with_execute(rows)

    repo = PostgresAssignmentRepository(session)
    page = await repo.list_teacher_exams(teacher_id=TEACHER_ID, limit=5, cursor=None)

    assert page.next_cursor is None


@pytest.mark.asyncio
async def test_list_teacher_exams_cursor_advances_offset() -> None:
    session = _session_with_execute([])

    repo = PostgresAssignmentRepository(session)
    await repo.list_teacher_exams(teacher_id=TEACHER_ID, limit=10, cursor="20")

    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_teacher_exams_invalid_cursor_raises() -> None:
    session = AsyncMock()

    repo = PostgresAssignmentRepository(session)

    with pytest.raises(InvalidExamListCursorError):
        await repo.list_teacher_exams(teacher_id=TEACHER_ID, limit=10, cursor="garbage")


# ── verify_teacher_owns_exam ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_teacher_owns_exam_succeeds_when_rls_returns_row() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=_mock_assignment())

    repo = PostgresAssignmentRepository(session)
    await repo.verify_teacher_owns_exam(teacher_id=TEACHER_ID, exam_id=EXAM_ID)


@pytest.mark.asyncio
async def test_verify_teacher_owns_exam_raises_not_found_when_rls_hides_row() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)

    repo = PostgresAssignmentRepository(session)

    with pytest.raises(ExamNotFoundError):
        await repo.verify_teacher_owns_exam(teacher_id=TEACHER_ID, exam_id=EXAM_ID)


# ── get_exam_for_config / save_exam_config ────────────────────────────────────


@pytest.mark.asyncio
async def test_get_exam_for_config_returns_exam_when_found() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=_mock_assignment(status="created"))

    repo = PostgresAssignmentRepository(session)
    result = await repo.get_exam_for_config(exam_id=EXAM_ID)

    assert result is not None
    assert result.exam_id == EXAM_ID


@pytest.mark.asyncio
async def test_get_exam_for_config_returns_none_when_not_found() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)

    repo = PostgresAssignmentRepository(session)
    result = await repo.get_exam_for_config(exam_id=EXAM_ID)

    assert result is None


@pytest.mark.asyncio
async def test_save_exam_config_updates_status_to_configured() -> None:
    row = _mock_assignment(status="created")
    session = AsyncMock()
    session.get = AsyncMock(return_value=row)

    repo = PostgresAssignmentRepository(session)
    await repo.save_exam_config(
        exam_id=EXAM_ID, teacher_id=TEACHER_ID, created_at="2026-05-01T00:00:00Z",
        config_s3_keys={},
    )

    assert row.status == ExamStatus.CONFIGURED.value


@pytest.mark.asyncio
async def test_save_exam_config_raises_wrong_status_when_exam_not_found() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)

    repo = PostgresAssignmentRepository(session)

    with pytest.raises(ExamConfigWrongStatusError):
        await repo.save_exam_config(
            exam_id=EXAM_ID, teacher_id=TEACHER_ID, created_at="2026-05-01T00:00:00Z",
            config_s3_keys={},
        )


@pytest.mark.asyncio
async def test_save_exam_config_raises_wrong_status_when_already_running() -> None:
    row = _mock_assignment(status="ingestion_running")
    session = AsyncMock()
    session.get = AsyncMock(return_value=row)

    repo = PostgresAssignmentRepository(session)

    with pytest.raises(ExamConfigWrongStatusError):
        await repo.save_exam_config(
            exam_id=EXAM_ID, teacher_id=TEACHER_ID, created_at="2026-05-01T00:00:00Z",
            config_s3_keys={},
        )
