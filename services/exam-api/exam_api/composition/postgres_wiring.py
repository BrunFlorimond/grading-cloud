"""PostgreSQL adapter wiring for FastAPI Depends() — composition root for persistence.

Each repository is constructed from the request-scoped AsyncSession produced by
``get_teacher_rls_session`` / ``get_student_rls_session`` (RLS GUCs per transaction).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from grading_shared.ports import ExamRepositoryPort
from sqlalchemy.ext.asyncio import AsyncSession

from exam_api.api.dependencies import CurrentTeacher, require_teacher
from exam_api.composition.rls_sessions import (
    get_student_rls_session,
    get_teacher_rls_session,
)
from exam_api.application.verify_exam_ownership import (
    VerifyExamOwnershipCommand,
    VerifyExamOwnershipUseCase,
)
from exam_api.domain.errors import (
    EXAM_NOT_FOUND_FOR_CLIENT,
    ExamNotFoundError,
    ExamOwnershipError,
)
from exam_api.infrastructure.postgres_assignment_repository import (
    PostgresAssignmentRepository,
)
from exam_api.infrastructure.postgres_exam_detail_repository import (
    PostgresExamDetailRepository,
)
from exam_api.infrastructure.postgres_student_enrollment_repository import (
    PostgresStudentEnrollmentRepository,
)
from exam_api.ports.exam_config_repository_port import ExamConfigRepositoryPort
from exam_api.ports.exam_creation_repository_port import ExamCreationRepositoryPort
from exam_api.ports.exam_detail_repository_port import ExamDetailRepositoryPort
from exam_api.ports.exam_ownership_port import ExamOwnershipPort
from exam_api.ports.student_scope_repository_port import StudentScopeRepositoryPort
from exam_api.ports.student_enrollment_repository_port import (
    StudentEnrollmentRepositoryPort,
)


def get_exam_detail_repository(
    session: Annotated[AsyncSession, Depends(get_teacher_rls_session)],
) -> ExamDetailRepositoryPort:
    return PostgresExamDetailRepository(session)


def get_exam_creation_repository(
    session: Annotated[AsyncSession, Depends(get_teacher_rls_session)],
) -> ExamCreationRepositoryPort:
    return PostgresAssignmentRepository(session)


def get_enrollment_repository(
    session: Annotated[AsyncSession, Depends(get_teacher_rls_session)],
) -> StudentEnrollmentRepositoryPort:
    return PostgresStudentEnrollmentRepository(session)


def get_invite_exam_repository(
    session: Annotated[AsyncSession, Depends(get_teacher_rls_session)],
) -> ExamRepositoryPort:
    return PostgresAssignmentRepository(session)


def get_invite_scope_repository(
    session: Annotated[AsyncSession, Depends(get_teacher_rls_session)],
) -> StudentScopeRepositoryPort:
    return PostgresStudentEnrollmentRepository(session)


def get_student_scope_repository(
    session: Annotated[AsyncSession, Depends(get_student_rls_session)],
) -> StudentScopeRepositoryPort:
    return PostgresStudentEnrollmentRepository(session)


def get_exam_config_repository(
    session: Annotated[AsyncSession, Depends(get_teacher_rls_session)],
) -> ExamConfigRepositoryPort:
    return PostgresAssignmentRepository(session)


def get_exam_ownership_repository(
    session: Annotated[AsyncSession, Depends(get_teacher_rls_session)],
) -> ExamOwnershipPort:
    return PostgresAssignmentRepository(session)


def get_verify_exam_ownership_use_case(
    exam_ownership_repository: Annotated[
        ExamOwnershipPort,
        Depends(get_exam_ownership_repository),
    ],
) -> VerifyExamOwnershipUseCase:
    return VerifyExamOwnershipUseCase(exam_ownership_repository)


async def verify_teacher_exam_ownership(
    exam_id: str,
    current_teacher: Annotated[CurrentTeacher, Depends(require_teacher)],
    use_case: Annotated[
        VerifyExamOwnershipUseCase,
        Depends(get_verify_exam_ownership_use_case),
    ],
) -> None:
    """Ensure exam exists and the teacher owns it (RLS-scoped query)."""
    try:
        await use_case.execute(
            VerifyExamOwnershipCommand(
                teacher_id=current_teacher.teacher_id,
                exam_id=exam_id,
            )
        )
    except ExamNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ExamOwnershipError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=EXAM_NOT_FOUND_FOR_CLIENT,
        ) from err
