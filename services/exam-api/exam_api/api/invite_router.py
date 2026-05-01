"""FastAPI router for POST /exams/{exam_id}/students/{student_id}/invite."""

from __future__ import annotations

from typing import Annotated

from grading_shared.ports import ExamRepositoryPort
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from httpx import HTTPError
from jose import JWTError
from pydantic import BaseModel, ConfigDict, EmailStr

from exam_api.application.invite_student import (
    InviteStudentCommand,
    InviteStudentUseCase,
)
from exam_api.domain.errors import ExamNotFoundError, ExamOwnershipError
from exam_api.ports.jwt_verifier_port import JwtVerifierPort
from exam_api.ports.student_scope_repository_port import StudentScopeRepositoryPort
from exam_api.ports.student_invite_port import StudentInviteServicePort

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


class CurrentTeacher(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    teacher_id: str


class CurrentStudent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    student_id: str
    exam_id: str


class StudentScopeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    student_id: str
    exam_id: str
    email: EmailStr


def get_current_teacher(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentTeacher:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must use Bearer token.",
        )
    jwt_verifier = get_jwt_verifier(request)
    try:
        claims = jwt_verifier.decode_and_verify_token(token)
    except (HTTPError, JWTError) as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid JWT token.",
        ) from err
    role = claims.get("custom:role")
    teacher_id = claims.get("sub")
    if role != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers can invite students.",
        )
    if not isinstance(teacher_id, str) or not teacher_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing teacher identifier in JWT claims.",
        )
    return CurrentTeacher(teacher_id=teacher_id)


def get_current_student(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentStudent:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must use Bearer token.",
        )
    jwt_verifier = get_jwt_verifier(request)
    try:
        claims = jwt_verifier.decode_and_verify_token(token)
    except (HTTPError, JWTError) as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid JWT token.",
        ) from err
    if claims.get("custom:role") != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can access this route.",
        )
    student_id = claims.get("sub")
    exam_id = claims.get("custom:exam_id")
    if not isinstance(student_id, str) or not student_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing student identifier in JWT claims.",
        )
    if not isinstance(exam_id, str) or not exam_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing exam scope in JWT claims.",
        )
    return CurrentStudent(student_id=student_id, exam_id=exam_id)


def get_student_invite_service(request: Request) -> StudentInviteServicePort:
    service = getattr(request.app.state, "student_invite_service", None)
    if not isinstance(service, StudentInviteServicePort):
        raise RuntimeError(
            "Missing invite service configuration. Set app.state.student_invite_service."
        )
    return service


def get_invite_repository(request: Request) -> ExamRepositoryPort:
    repository = getattr(request.app.state, "invite_repository", None)
    if not isinstance(repository, ExamRepositoryPort) and not hasattr(
        repository, "get_exam"
    ):
        raise RuntimeError(
            "Missing invite repository configuration. Set app.state.invite_repository."
        )
    return repository


def get_student_scope_repository(request: Request) -> StudentScopeRepositoryPort:
    repository = get_invite_repository(request)
    if not isinstance(repository, StudentScopeRepositoryPort) and not (
        hasattr(repository, "upsert_student_scope")
        and hasattr(repository, "get_student_scope")
    ):
        raise RuntimeError(
            "Invite repository must implement student scope persistence methods."
        )
    return repository


def get_jwt_verifier(request: Request) -> JwtVerifierPort:
    verifier = getattr(request.app.state, "jwt_verifier", None)
    if not isinstance(verifier, JwtVerifierPort) and not hasattr(
        verifier, "decode_and_verify_token"
    ):
        raise RuntimeError("Missing JWT verifier configuration.")
    return verifier


def provide_invite_use_case(
    invite_service: Annotated[StudentInviteServicePort, Depends(get_student_invite_service)],
    exam_repository: Annotated[ExamRepositoryPort, Depends(get_invite_repository)],
    student_scope_repository: Annotated[
        StudentScopeRepositoryPort, Depends(get_student_scope_repository)
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
def invite_student(
    exam_id: str,
    student_id: str,
    body: InviteStudentRequest,
    current_teacher: Annotated[CurrentTeacher, Depends(get_current_teacher)],
    use_case: Annotated[InviteStudentUseCase, Depends(provide_invite_use_case)],
) -> InviteStudentResponse:
    try:
        result = use_case.execute(
            InviteStudentCommand(
                exam_id=exam_id,
                student_id=student_id,
                student_email=body.student_email,
                teacher_id=current_teacher.teacher_id,
            )
        )
    except ExamNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ExamOwnershipError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(err),
        ) from err
    return InviteStudentResponse(
        student_id=result.student.student_id,
        exam_id=result.student.exam_id,
        re_invited=result.re_invited,
    )


@router.get(
    "/{exam_id}/students/{student_id}/scope",
    response_model=StudentScopeResponse,
    status_code=status.HTTP_200_OK,
)
def get_student_scope(
    exam_id: str,
    student_id: str,
    current_student: Annotated[CurrentStudent, Depends(get_current_student)],
    student_scope_repository: Annotated[
        StudentScopeRepositoryPort, Depends(get_student_scope_repository)
    ],
) -> StudentScopeResponse:
    if current_student.exam_id != exam_id or current_student.student_id != student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student token does not match requested resource.",
        )
    student_scope = student_scope_repository.get_student_scope(
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
        exam_id=student_scope.exam_id,
        email=student_scope.email,
    )
