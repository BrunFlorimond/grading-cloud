"""FastAPI router for POST /exams/{exam_id}/students/{student_id}/invite."""

from __future__ import annotations

import base64
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr

from exam_api.application.invite_student import InviteStudentCommand, InviteStudentUseCase
from exam_api.domain.errors import ExamNotFoundError, ExamOwnershipError
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


def get_current_teacher(
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
    claims = _decode_jwt_payload(token)
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


def _decode_jwt_payload(token: str) -> dict[str, str]:
    token_parts = token.split(".")
    if len(token_parts) != 3:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid JWT token format.",
        )
    payload_segment = token_parts[1]
    missing_padding = len(payload_segment) % 4
    if missing_padding:
        payload_segment += "=" * (4 - missing_padding)
    try:
        decoded = base64.urlsafe_b64decode(payload_segment.encode("utf-8"))
        raw_payload = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to decode JWT payload.",
        ) from err
    if not isinstance(raw_payload, dict):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid JWT payload.",
        )
    claims: dict[str, str] = {}
    for key, value in raw_payload.items():
        if isinstance(key, str) and isinstance(value, str):
            claims[key] = value
    return claims


def get_student_invite_service(request: Request) -> StudentInviteServicePort:
    service = getattr(request.app.state, "student_invite_service", None)
    if not isinstance(service, StudentInviteServicePort):
        raise RuntimeError(
            "Missing invite service configuration. Set app.state.student_invite_service."
        )
    return service


def get_invite_use_case() -> InviteStudentUseCase:
    raise RuntimeError("Invite use case dependency not configured.")


def provide_invite_use_case(
    invite_service: Annotated[StudentInviteServicePort, Depends(get_student_invite_service)],
) -> InviteStudentUseCase:
    return InviteStudentUseCase(invite_service=invite_service)


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
