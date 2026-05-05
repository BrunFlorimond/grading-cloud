"""Unit tests for PostgresExamDetailRepository."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from exam_api.domain.errors import ExamNotFoundError, InvalidExamListCursorError
from exam_api.infrastructure.orm import AssignmentORM, StudentAssignmentORM
from exam_api.infrastructure.postgres_exam_detail_repository import (
    PostgresExamDetailRepository,
)
from exam_api.ports.exam_detail_repository_port import ExamDetail

EXAM_ID = "550e8400-e29b-41d4-a716-446655440000"
TEACHER_ID = "660e8400-e29b-41d4-a716-446655440000"


def _mock_assignment_row(
    exam_id: str = EXAM_ID, teacher_id: str = TEACHER_ID
) -> MagicMock:
    row = MagicMock(spec=AssignmentORM)
    row.id = uuid.UUID(exam_id)
    row.created_by = uuid.UUID(teacher_id)
    row.title = "Algebra"
    row.status = "CREATED"
    row.description = None
    row.subject = None
    row.created_at = None
    row.pipeline_started_at = None
    row.pipeline_completed_at = None
    return row


def _mock_status_count_execute(counts: dict[str, int]) -> MagicMock:
    rows = []
    for status, cnt in counts.items():
        r = MagicMock()
        r.submission_status = status
        r.cnt = cnt
        rows.append(r)
    result = MagicMock()
    result.all.return_value = rows
    return result


def _session_for_exam_detail(
    assignment_row: MagicMock | None,
    status_counts: dict[str, int],
) -> AsyncMock:
    session = AsyncMock()
    session.get = AsyncMock(return_value=assignment_row)
    count_result = _mock_status_count_execute(status_counts)
    session.execute = AsyncMock(return_value=count_result)
    return session


# ── get_exam_detail ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_exam_detail_returns_exam_with_status_counts() -> None:
    session = _session_for_exam_detail(
        _mock_assignment_row(),
        {"PENDING": 3, "CONVERTED": 1},
    )

    repo = PostgresExamDetailRepository(session)
    detail = await repo.get_exam_detail(exam_id=EXAM_ID)

    assert isinstance(detail, ExamDetail)
    assert detail.exam_id == EXAM_ID
    assert detail.status_counts.pending == 3
    assert detail.status_counts.converted == 1
    assert detail.status_counts.corrected == 0


@pytest.mark.asyncio
async def test_get_exam_detail_raises_not_found_when_rls_hides_row() -> None:
    session = _session_for_exam_detail(None, {})

    repo = PostgresExamDetailRepository(session)

    with pytest.raises(ExamNotFoundError):
        await repo.get_exam_detail(exam_id=EXAM_ID)


@pytest.mark.asyncio
async def test_get_exam_detail_other_status_bucketed_correctly() -> None:
    session = _session_for_exam_detail(
        _mock_assignment_row(),
        {"PENDING": 1, "UNKNOWN_STATUS": 2},
    )

    repo = PostgresExamDetailRepository(session)
    detail = await repo.get_exam_detail(exam_id=EXAM_ID)

    assert detail.status_counts.other == 2


# ── list_exam_student_statuses ────────────────────────────────────────────────


def _mock_student_assignment_row(student_id: str = "EL-001") -> MagicMock:
    row = MagicMock(spec=StudentAssignmentORM)
    row.student_id = student_id
    row.nom = "Doe"
    row.prenom = "Jane"
    row.classe = "A"
    row.submission_status = "PENDING"
    row.pdf_available = False
    return row


def _session_for_pipeline_page(rows: list) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_list_exam_student_statuses_returns_page() -> None:
    rows = [_mock_student_assignment_row("s1"), _mock_student_assignment_row("s2")]
    session = _session_for_pipeline_page(rows)

    repo = PostgresExamDetailRepository(session)
    page = await repo.list_exam_student_statuses(exam_id=EXAM_ID, limit=10, cursor=None)

    assert len(page.items) == 2
    assert page.items[0].student_id == "s1"
    assert page.items[1].student_id == "s2"


@pytest.mark.asyncio
async def test_list_exam_student_statuses_next_cursor_set_when_page_full() -> None:
    rows = [_mock_student_assignment_row(f"s{i}") for i in range(5)]
    session = _session_for_pipeline_page(rows)

    repo = PostgresExamDetailRepository(session)
    page = await repo.list_exam_student_statuses(exam_id=EXAM_ID, limit=5, cursor=None)

    assert page.next_cursor == "5"


@pytest.mark.asyncio
async def test_list_exam_student_statuses_next_cursor_none_on_last_page() -> None:
    rows = [_mock_student_assignment_row("s1")]
    session = _session_for_pipeline_page(rows)

    repo = PostgresExamDetailRepository(session)
    page = await repo.list_exam_student_statuses(exam_id=EXAM_ID, limit=5, cursor=None)

    assert page.next_cursor is None


@pytest.mark.asyncio
async def test_list_exam_student_statuses_invalid_cursor_raises() -> None:
    session = AsyncMock()

    repo = PostgresExamDetailRepository(session)

    with pytest.raises(InvalidExamListCursorError):
        await repo.list_exam_student_statuses(exam_id=EXAM_ID, limit=5, cursor="bad!")
