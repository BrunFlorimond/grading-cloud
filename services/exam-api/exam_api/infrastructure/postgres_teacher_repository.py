"""PostgreSQL adapter: upsert teacher on Cognito login."""

from __future__ import annotations

import uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from exam_api.domain.teacher import Teacher
from exam_api.infrastructure.orm import TeacherORM


class PostgresTeacherRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def upsert_teacher(
        self, *, cognito_sub: str, email: str, full_name: str
    ) -> Teacher:
        stmt = (
            insert(TeacherORM)
            .values(id=uuid.UUID(cognito_sub), email=email, full_name=full_name)
            .on_conflict_do_update(
                index_elements=["id"],
                set_={"email": email, "full_name": full_name},
            )
            .returning(TeacherORM.id, TeacherORM.email, TeacherORM.full_name)
        )
        row = (await self._s.execute(stmt)).one()
        return Teacher(teacher_id=str(row.id), email=row.email, full_name=row.full_name)
