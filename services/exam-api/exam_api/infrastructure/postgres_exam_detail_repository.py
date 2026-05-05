"""PostgreSQL adapter for exam detail and per-student pipeline status."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from exam_api.domain.errors import ExamNotFoundError, InvalidExamListCursorError
from exam_api.infrastructure.orm import AssignmentORM, StudentAssignmentORM
from exam_api.ports.exam_detail_repository_port import (
    ExamDetail,
    StatusCounts,
    StudentPipelinePage,
    StudentPipelineStatus,
)


class PostgresExamDetailRepository:
    """Implements ExamDetailRepositoryPort against PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_exam_detail(self, *, exam_id: str) -> ExamDetail:
        assignment_uuid = uuid.UUID(exam_id)
        row = await self._s.get(AssignmentORM, assignment_uuid)
        if row is None:
            raise ExamNotFoundError(f"Exam {exam_id!r} not found.")

        counts = await self._status_counts(assignment_uuid)
        return ExamDetail(
            exam_id=str(row.id),
            teacher_id=str(row.created_by),
            title=row.title,
            status=row.status,
            description=row.description,
            subject=row.subject,
            created_at=row.created_at.isoformat() if row.created_at else None,
            pipeline_started_at=row.pipeline_started_at.isoformat()
            if row.pipeline_started_at
            else None,
            pipeline_completed_at=row.pipeline_completed_at.isoformat()
            if row.pipeline_completed_at
            else None,
            status_counts=counts,
        )

    async def _status_counts(self, assignment_uuid: uuid.UUID) -> StatusCounts:
        stmt = (
            select(
                StudentAssignmentORM.submission_status,
                func.count().label("cnt"),
            )
            .where(StudentAssignmentORM.assignment_id == assignment_uuid)
            .group_by(StudentAssignmentORM.submission_status)
        )
        rows = (await self._s.execute(stmt)).all()
        counts = {r.submission_status: r.cnt for r in rows}
        return StatusCounts(
            pending=counts.get("PENDING", 0),
            converted=counts.get("CONVERTED", 0),
            corrected=counts.get("CORRECTED", 0),
            other=sum(
                v
                for k, v in counts.items()
                if k not in {"PENDING", "CONVERTED", "CORRECTED"}
            ),
        )

    async def list_exam_student_statuses(
        self, *, exam_id: str, limit: int, cursor: str | None
    ) -> StudentPipelinePage:
        assignment_uuid = uuid.UUID(exam_id)
        try:
            offset = int(cursor) if cursor is not None else 0
        except ValueError:
            raise InvalidExamListCursorError("Invalid pagination cursor.")

        stmt = (
            select(StudentAssignmentORM)
            .where(StudentAssignmentORM.assignment_id == assignment_uuid)
            .order_by(StudentAssignmentORM.enrolled_at)
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        items = [
            StudentPipelineStatus(
                student_id=r.student_id,
                nom=r.nom,
                prenom=r.prenom,
                classe=r.classe,
                submission_status=r.submission_status,
                pdf_available=r.pdf_available,
            )
            for r in rows
        ]
        next_cursor = str(offset + limit) if len(rows) == limit else None
        return StudentPipelinePage(items=items, next_cursor=next_cursor)
