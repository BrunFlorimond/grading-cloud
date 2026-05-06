"""PostgreSQL adapter for local user identity upserts."""

from __future__ import annotations

import uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from exam_api.domain.errors import InvalidUserIdentitySubjectError
from exam_api.domain.student import Student
from exam_api.domain.teacher import Teacher
from exam_api.infrastructure.orm import StudentORM, TeacherORM
from exam_api.ports.user_identity_repository_port import UserIdentityRepositoryPort


class PostgresUserIdentityRepository(UserIdentityRepositoryPort):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    @staticmethod
    def _to_uuid(subject: str) -> uuid.UUID:
        try:
            return uuid.UUID(subject)
        except ValueError as err:
            raise InvalidUserIdentitySubjectError(
                "Cognito subject is not a valid UUID."
            ) from err

    async def upsert_teacher(
        self, *, cognito_sub: str, email: str, full_name: str
    ) -> Teacher:
        stmt = (
            insert(TeacherORM)
            .values(id=self._to_uuid(cognito_sub), email=email, full_name=full_name)
            .on_conflict_do_update(
                index_elements=["id"],
                set_={"email": email, "full_name": full_name},
            )
            .returning(TeacherORM.id, TeacherORM.email, TeacherORM.full_name)
        )
        row = (await self._s.execute(stmt)).one()
        return Teacher(teacher_id=str(row.id), email=row.email, full_name=row.full_name)

    async def upsert_student(self, *, cognito_sub: str, email: str) -> Student:
        stmt = (
            insert(StudentORM)
            .values(id=self._to_uuid(cognito_sub), email=email)
            .on_conflict_do_update(
                index_elements=["id"],
                set_={"email": email},
            )
            .returning(StudentORM.id, StudentORM.email)
        )
        row = (await self._s.execute(stmt)).one()
        return Student(student_id=str(row.id), email=row.email)
