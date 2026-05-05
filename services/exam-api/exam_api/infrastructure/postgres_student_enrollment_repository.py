"""PostgreSQL adapters for student enrollment and scope."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from exam_api.domain.errors import (
    DuplicateStudentError,
    InvalidExamListCursorError,
    StudentExamScopeConflictError,
)
from exam_api.domain.student import Student, StudentAssignment, SubmissionStatus
from exam_api.infrastructure.orm import StudentAssignmentORM
from exam_api.ports.student_enrollment_repository_port import EnrolledStudentPage

logger = logging.getLogger(__name__)


def _to_enrolled(row: StudentAssignmentORM) -> StudentAssignment:
    return StudentAssignment(
        student_id=row.student_id,
        assignment_id=str(row.assignment_id),
        nom=row.nom,
        prenom=row.prenom,
        classe=row.classe,
        email=row.email,
        submission_status=SubmissionStatus(row.submission_status),
    )


class PostgresStudentEnrollmentRepository:
    """Implements StudentEnrollmentRepositoryPort + StudentScopeRepositoryPort."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ── StudentEnrollmentRepositoryPort ───────────────────────────────────

    async def add_students(
        self, *, exam_id: str, students: list[StudentAssignment]
    ) -> list[StudentAssignment]:
        if not students:
            return []
        assignment_uuid = uuid.UUID(exam_id)
        for student in students:
            stmt = insert(StudentAssignmentORM).values(
                id=uuid.uuid4(),
                assignment_id=assignment_uuid,
                student_id=student.student_id,
                nom=student.nom,
                prenom=student.prenom,
                classe=student.classe,
                email=str(student.email) if student.email else None,
                submission_status=student.submission_status.value,
            )
            try:
                await self._s.execute(stmt)
            except IntegrityError:
                await self._s.rollback()
                raise DuplicateStudentError(student.student_id, exam_id)
        return students

    async def list_exam_students(
        self, *, exam_id: str, limit: int, cursor: str | None
    ) -> EnrolledStudentPage:
        try:
            offset = int(cursor) if cursor is not None else 0
        except ValueError:
            raise InvalidExamListCursorError("Invalid pagination cursor.")

        stmt = (
            select(StudentAssignmentORM)
            .where(StudentAssignmentORM.assignment_id == uuid.UUID(exam_id))
            .order_by(StudentAssignmentORM.enrolled_at)
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        items = [_to_enrolled(r) for r in rows]
        next_cursor = str(offset + limit) if len(rows) == limit else None
        return EnrolledStudentPage(items=items, next_cursor=next_cursor)

    # ── StudentScopeRepositoryPort ────────────────────────────────────────

    async def upsert_student_scope(
        self,
        *,
        student: Student,
        exam_id: str,
        teacher_id: str,
        external_student_id: str,
    ) -> None:
        assignment_uuid = uuid.UUID(exam_id)

        # Check that no other assignment already owns this cognito_sub
        existing_stmt = select(StudentAssignmentORM).where(
            StudentAssignmentORM.cognito_sub == student.student_id,
            StudentAssignmentORM.assignment_id != assignment_uuid,
        )
        conflict = (await self._s.execute(existing_stmt)).scalar_one_or_none()
        if conflict is not None:
            raise StudentExamScopeConflictError(
                "Student account is already scoped to another exam."
            )

        # Link the enrollment row identified by external_student_id to this cognito_sub
        stmt = (
            insert(StudentAssignmentORM)
            .values(
                id=uuid.uuid4(),
                assignment_id=assignment_uuid,
                student_id=external_student_id,
                cognito_sub=student.student_id,
                nom="",
                prenom="",
                classe="",
                email=str(student.email),
            )
            .on_conflict_do_update(
                index_elements=["assignment_id", "student_id"],
                set_={"cognito_sub": student.student_id, "email": str(student.email)},
            )
        )
        await self._s.execute(stmt)

    async def get_student_scope(
        self, *, exam_id: str, student_sub: str
    ) -> Student | None:
        stmt = select(StudentAssignmentORM).where(
            StudentAssignmentORM.assignment_id == uuid.UUID(exam_id),
            StudentAssignmentORM.cognito_sub == student_sub,
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return Student(student_id=student_sub, email=row.email or "")
