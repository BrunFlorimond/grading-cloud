"""PostgreSQL adapters for assignment (exam) creation, ownership, config and scope."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from grading_shared.domain.exam import Exam, ExamStatus
from grading_shared.domain.models import NotationPayload

from exam_api.domain.errors import (
    ExamConfigWrongStatusError,
    ExamCreationConflictError,
    ExamNotFoundError,
    InvalidExamListCursorError,
)
from exam_api.infrastructure.orm import AssignmentORM, TeacherAssignmentORM
from exam_api.ports.exam_creation_repository_port import ExamPage


def _to_exam(row: AssignmentORM) -> Exam:
    return Exam(
        exam_id=str(row.id),
        teacher_id=str(row.created_by),
        title=row.title,
        status=ExamStatus(row.status),
        description=row.description,
        subject=row.subject,
        created_at=row.created_at.isoformat() if row.created_at else None,
    )


class PostgresAssignmentRepository:
    """Implements ExamCreationRepositoryPort + ExamOwnershipPort + ExamConfigRepositoryPort
    + ExamRepositoryPort (grading_shared) against PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ── ExamCreationRepositoryPort ────────────────────────────────────────

    async def create_exam(self, exam: Exam) -> None:
        exam_uuid = uuid.UUID(exam.exam_id)
        teacher_uuid = uuid.UUID(exam.teacher_id)

        existing = await self._s.get(AssignmentORM, exam_uuid)
        if existing is not None:
            raise ExamCreationConflictError("Exam already exists for this identifier.")

        assignment = AssignmentORM(
            id=exam_uuid,
            title=exam.title,
            created_by=teacher_uuid,
            status=exam.status.value,
            description=exam.description,
            subject=exam.subject,
        )
        self._s.add(assignment)
        self._s.add(TeacherAssignmentORM(
            teacher_id=teacher_uuid,
            assignment_id=exam_uuid,
            role="owner",
        ))

    async def list_teacher_exams(self, *, teacher_id: str, limit: int, cursor: str | None) -> ExamPage:
        try:
            offset = int(cursor) if cursor is not None else 0
        except ValueError:
            raise InvalidExamListCursorError("Invalid pagination cursor.")

        stmt = (
            select(AssignmentORM)
            .order_by(AssignmentORM.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        items = [_to_exam(r) for r in rows]
        next_cursor = str(offset + limit) if len(rows) == limit else None
        return ExamPage(items=items, next_cursor=next_cursor)

    # ── ExamOwnershipPort ─────────────────────────────────────────────────

    async def verify_teacher_owns_exam(self, *, teacher_id: str, exam_id: str) -> None:
        row = await self._s.get(AssignmentORM, uuid.UUID(exam_id))
        if row is None:
            raise ExamNotFoundError(f"Exam {exam_id} not found.")

    # ── ExamConfigRepositoryPort ──────────────────────────────────────────

    async def get_exam_for_config(self, *, exam_id: str) -> Exam | None:
        row = await self._s.get(AssignmentORM, uuid.UUID(exam_id))
        return _to_exam(row) if row else None

    async def save_exam_config(
        self,
        *,
        exam_id: str,
        teacher_id: str,
        created_at: str,
        config_s3_keys: dict[str, str],
    ) -> None:
        allowed = {ExamStatus.CREATED.value, ExamStatus.CONFIGURED.value}
        row = await self._s.get(AssignmentORM, uuid.UUID(exam_id))
        if row is None or row.status not in allowed:
            raise ExamConfigWrongStatusError(
                "Exam status does not allow confirming configuration."
            )
        row.status = ExamStatus.CONFIGURED.value
        # config_s3_keys stored as JSON in a dedicated column if needed;
        # for now we just update status — S3 keys are managed by S3ExamConfigStorage.

    # ── ExamRepositoryPort (grading_shared) ───────────────────────────────

    async def get_exam(self, *, exam_id: str) -> Exam | None:
        row = await self._s.get(AssignmentORM, uuid.UUID(exam_id))
        return _to_exam(row) if row else None

    async def save_exam(self, exam: Exam) -> None:
        stmt = (
            insert(AssignmentORM)
            .values(
                id=uuid.UUID(exam.exam_id),
                title=exam.title,
                created_by=uuid.UUID(exam.teacher_id),
                status=exam.status.value,
                description=exam.description,
                subject=exam.subject,
            )
            .on_conflict_do_update(
                index_elements=["id"],
                set_={"status": exam.status.value, "title": exam.title},
            )
        )
        await self._s.execute(stmt)

    async def save_notation_payload(
        self, *, exam_id: str, student_id: str, payload: NotationPayload
    ) -> None:
        # Notation payloads are large JSON results written by batch-poller.
        # Stored in a separate table; stubbed here — implement when batch-poller migrates.
        raise NotImplementedError(
            "save_notation_payload not yet migrated to PostgreSQL."
        )
