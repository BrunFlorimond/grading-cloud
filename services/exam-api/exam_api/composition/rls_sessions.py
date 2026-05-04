"""FastAPI-callable providers for PostgreSQL sessions scoped by RLS GUCs.

Pairs JWT-derived identity (from ``exam_api.api.dependencies``) with
``session_with_rls`` — belongs in composition alongside concrete persistence wiring.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from exam_api.api.dependencies import (
    CurrentStudent,
    CurrentTeacher,
    require_student,
    require_teacher,
)
from exam_api.infrastructure.db import RLSContext, session_with_rls


async def get_teacher_rls_session(
    current_teacher: Annotated[CurrentTeacher, Depends(require_teacher)],
) -> AsyncGenerator[AsyncSession, None]:
    """Open a transaction with teacher RLS context. Deduplicated per-request by FastAPI."""
    async with session_with_rls(
        RLSContext(user_id=current_teacher.teacher_id, user_type="teacher")
    ) as session:
        yield session


async def get_student_rls_session(
    current_student: Annotated[CurrentStudent, Depends(require_student)],
) -> AsyncGenerator[AsyncSession, None]:
    """Open a transaction with student RLS context. Deduplicated per-request by FastAPI."""
    async with session_with_rls(
        RLSContext(user_id=current_student.student_id, user_type="student")
    ) as session:
        yield session
