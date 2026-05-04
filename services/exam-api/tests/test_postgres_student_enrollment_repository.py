"""Unit tests for PostgresStudentEnrollmentRepository."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from exam_api.domain.errors import (
    DuplicateStudentError,
    InvalidExamListCursorError,
    StudentExamScopeConflictError,
)
from exam_api.domain.student import EnrolledStudent, Student, SubmissionStatus
from exam_api.infrastructure.orm import StudentAssignmentORM
from exam_api.infrastructure.postgres_student_enrollment_repository import (
    PostgresStudentEnrollmentRepository,
)

EXAM_ID = "550e8400-e29b-41d4-a716-446655440000"
COGNITO_SUB = "660e8400-e29b-41d4-a716-446655440000"


def _enrolled(student_id: str = "EL-001", exam_id: str = EXAM_ID) -> EnrolledStudent:
    return EnrolledStudent(
        student_id=student_id,
        exam_id=exam_id,
        nom="Doe",
        prenom="Jane",
        classe="A",
        submission_status=SubmissionStatus.PENDING,
    )


def _mock_student_assignment_row(
    student_id: str = "EL-001",
    cognito_sub: str | None = None,
    assignment_id: str = EXAM_ID,
) -> MagicMock:
    row = MagicMock(spec=StudentAssignmentORM)
    row.student_id = student_id
    row.cognito_sub = cognito_sub
    row.assignment_id = uuid.UUID(assignment_id)
    row.nom = "Doe"
    row.prenom = "Jane"
    row.classe = "A"
    row.email = None
    row.submission_status = "PENDING"
    return row


# ── add_students ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_students_executes_insert_for_each_student() -> None:
    session = AsyncMock()
    session.execute = AsyncMock()
    session.rollback = AsyncMock()

    repo = PostgresStudentEnrollmentRepository(session)
    await repo.add_students(exam_id=EXAM_ID, students=[_enrolled("s1"), _enrolled("s2")])

    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_add_students_returns_empty_list_for_empty_input() -> None:
    session = AsyncMock()

    repo = PostgresStudentEnrollmentRepository(session)
    result = await repo.add_students(exam_id=EXAM_ID, students=[])

    assert result == []
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_students_raises_duplicate_error_on_integrity_error() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=IntegrityError(None, None, None))
    session.rollback = AsyncMock()

    repo = PostgresStudentEnrollmentRepository(session)

    with pytest.raises(DuplicateStudentError) as exc_info:
        await repo.add_students(exam_id=EXAM_ID, students=[_enrolled("dup")])

    assert exc_info.value.student_id == "dup"
    assert exc_info.value.exam_id == EXAM_ID
    session.rollback.assert_awaited_once()


# ── list_exam_students ────────────────────────────────────────────────────────


def _session_for_list(rows: list) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_list_exam_students_returns_page_of_enrolled_students() -> None:
    rows = [_mock_student_assignment_row("s1"), _mock_student_assignment_row("s2")]
    session = _session_for_list(rows)

    repo = PostgresStudentEnrollmentRepository(session)
    page = await repo.list_exam_students(exam_id=EXAM_ID, limit=10, cursor=None)

    assert len(page.items) == 2
    assert page.items[0].student_id == "s1"


@pytest.mark.asyncio
async def test_list_exam_students_next_cursor_set_when_page_full() -> None:
    rows = [_mock_student_assignment_row(f"s{i}") for i in range(5)]
    session = _session_for_list(rows)

    repo = PostgresStudentEnrollmentRepository(session)
    page = await repo.list_exam_students(exam_id=EXAM_ID, limit=5, cursor=None)

    assert page.next_cursor == "5"


@pytest.mark.asyncio
async def test_list_exam_students_next_cursor_none_on_last_page() -> None:
    rows = [_mock_student_assignment_row("s1")]
    session = _session_for_list(rows)

    repo = PostgresStudentEnrollmentRepository(session)
    page = await repo.list_exam_students(exam_id=EXAM_ID, limit=5, cursor=None)

    assert page.next_cursor is None


@pytest.mark.asyncio
async def test_list_exam_students_invalid_cursor_raises() -> None:
    session = AsyncMock()

    repo = PostgresStudentEnrollmentRepository(session)

    with pytest.raises(InvalidExamListCursorError):
        await repo.list_exam_students(exam_id=EXAM_ID, limit=10, cursor="bad!")


# ── upsert_student_scope ──────────────────────────────────────────────────────


def _session_for_upsert_scope(conflict_row: MagicMock | None) -> AsyncMock:
    session = AsyncMock()
    # First execute: conflict check (scalar_one_or_none)
    # Second execute: INSERT ... ON CONFLICT
    conflict_result = MagicMock()
    conflict_result.scalar_one_or_none.return_value = conflict_row
    insert_result = MagicMock()
    session.execute = AsyncMock(side_effect=[conflict_result, insert_result])
    return session


@pytest.mark.asyncio
async def test_upsert_student_scope_raises_conflict_when_sub_bound_to_other_exam() -> None:
    other_row = _mock_student_assignment_row(assignment_id=str(uuid.uuid4()))
    session = _session_for_upsert_scope(conflict_row=other_row)

    repo = PostgresStudentEnrollmentRepository(session)
    student = Student(student_id=COGNITO_SUB, email="s@school.fr")

    with pytest.raises(StudentExamScopeConflictError):
        await repo.upsert_student_scope(
            student=student, exam_id=EXAM_ID, teacher_id="t1", external_student_id="EL-001"
        )


@pytest.mark.asyncio
async def test_upsert_student_scope_executes_upsert_when_no_conflict() -> None:
    session = _session_for_upsert_scope(conflict_row=None)

    repo = PostgresStudentEnrollmentRepository(session)
    student = Student(student_id=COGNITO_SUB, email="s@school.fr")

    await repo.upsert_student_scope(
        student=student, exam_id=EXAM_ID, teacher_id="t1", external_student_id="EL-001"
    )

    assert session.execute.await_count == 2


# ── get_student_scope ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_student_scope_returns_student_when_found() -> None:
    row = _mock_student_assignment_row(cognito_sub=COGNITO_SUB)
    row.email = "s@school.fr"

    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    session.execute = AsyncMock(return_value=result)

    repo = PostgresStudentEnrollmentRepository(session)
    student = await repo.get_student_scope(exam_id=EXAM_ID, student_sub=COGNITO_SUB)

    assert student is not None
    assert student.student_id == COGNITO_SUB


@pytest.mark.asyncio
async def test_get_student_scope_returns_none_when_not_found() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)

    repo = PostgresStudentEnrollmentRepository(session)
    student = await repo.get_student_scope(exam_id=EXAM_ID, student_sub=COGNITO_SUB)

    assert student is None
