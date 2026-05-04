"""FastAPI router for POST /exams/{exam_id}/students/{student_id}/invite."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from grading_shared.ports import ExamRepositoryPort
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from exam_api.api.dependencies import (
    CurrentTeacher,
    get_student_rls_session,
    get_teacher_rls_session,
    require_own_data,
    require_teacher,
    verify_teacher_exam_ownership,
)
from exam_api.application.invite_student import (
    InviteStudentCommand,
    InviteStudentUseCase,
)
from exam_api.domain.errors import (
    EXAM_NOT_FOUND_FOR_CLIENT,
    ExamNotFoundError,
    ExamOwnershipError,
    StudentExamScopeConflictError,
)
from exam_api.infrastructure.postgres_assignment_repository import PostgresAssignmentRepository
from exam_api.infrastructure.postgres_student_enrollment_repository import PostgresStudentEnrollmentRepository
from exam_api.ports.student_invite_port import StudentInviteServicePort
from exam_api.ports.student_scope_repository_port import StudentScopeRepositoryPort

router = APIRouter(prefix="/exams", tags=["invite"])


class InviteStudentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    student_email: EmailStr
    # TODO(#10): remove teacher_id from request body; extract from JWT Cognito claims instead


class InviteStudentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    student_id: str
    exam_id: str
    re_invited: bool


class StudentScopeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    student_id: str
    exam_id: str
    email: EmailStr


def get_student_invite_service(request: Request) -> StudentInviteServicePort:
    service = getattr(request.app.state, "student_invite_service", None)
    if not isinstance(service, StudentInviteServicePort):
        raise RuntimeError(
            "Missing invite service configuration. Set app.state.student_invite_service."
        )
    return service


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


def provide_invite_use_case(
    invite_service: Annotated[
        StudentInviteServicePort, Depends(get_student_invite_service)
    ],
    exam_repository: Annotated[ExamRepositoryPort, Depends(get_invite_exam_repository)],
    student_scope_repository: Annotated[
        StudentScopeRepositoryPort, Depends(get_invite_scope_repository)
    ],
) -> InviteStudentUseCase:
    return InviteStudentUseCase(
        invite_service=invite_service,
        exam_repository=exam_repository,
        student_scope_repository=student_scope_repository,
    )


@router.post(
    "/{exam_id}/students/{student_id}/invite",
    response_model=InviteStudentResponse,
    status_code=status.HTTP_200_OK,
)
async def invite_student(
    exam_id: str,
    student_id: str,
    body: InviteStudentRequest,
    current_teacher: Annotated[CurrentTeacher, Depends(require_teacher)],
    _: Annotated[None, Depends(verify_teacher_exam_ownership)],
    use_case: Annotated[InviteStudentUseCase, Depends(provide_invite_use_case)],
) -> InviteStudentResponse:
    try:
        result = await use_case.execute(
            InviteStudentCommand(
                exam_id=exam_id,
                student_id=student_id,
                student_email=body.student_email,
                teacher_id=current_teacher.teacher_id,
            ),
        )
    except ExamNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ExamOwnershipError as err:
        # Defense in depth: dependency checks TEACHER#/EXAM#; use case re-checks exam metadata.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=EXAM_NOT_FOUND_FOR_CLIENT,
        ) from err
    except StudentExamScopeConflictError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        ) from err
    return InviteStudentResponse(
        student_id=result.student.student_id,
        exam_id=exam_id,
        re_invited=result.re_invited,
    )


@router.get(
    "/{exam_id}/students/{student_id}/scope",
    response_model=StudentScopeResponse,
    status_code=status.HTTP_200_OK,
)
async def get_student_scope(
    exam_id: str,
    student_id: str,
    _: Annotated[None, Depends(require_own_data("student_id"))],
    student_scope_repository: Annotated[
        StudentScopeRepositoryPort, Depends(get_student_scope_repository)
    ],
) -> StudentScopeResponse:
    student_scope = await student_scope_repository.get_student_scope(
        exam_id=exam_id,
        student_sub=student_id,
    )
    if student_scope is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student scope not found.",
        )
    return StudentScopeResponse(
        student_id=student_scope.student_id,
        exam_id=exam_id,
        email=student_scope.email,
    )
