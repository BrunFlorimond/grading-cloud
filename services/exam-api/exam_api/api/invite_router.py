"""FastAPI router for POST /exams/{exam_id}/students/{student_id}/invite."""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr

from exam_api.application.invite_student import InviteStudentCommand, InviteStudentUseCase
from exam_api.domain.errors import ExamNotFoundError, ExamOwnershipError, StudentAlreadyInvitedError
from exam_api.infrastructure.student_invite_adapter import CognitoSesStudentInviteAdapter

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


def get_invite_use_case() -> InviteStudentUseCase:
    # TODO(#10): inject ExamRepositoryPort and StudentRepositoryPort once implemented
    return InviteStudentUseCase(invite_service=_build_invite_adapter())


@router.post(
    "/{exam_id}/students/{student_id}/invite",
    response_model=InviteStudentResponse,
    status_code=status.HTTP_200_OK,
)
def invite_student(
    exam_id: str,
    student_id: str,
    body: InviteStudentRequest,
    use_case: Annotated[InviteStudentUseCase, Depends(get_invite_use_case)],
) -> InviteStudentResponse:
    # TODO(#10): extract teacher_id from JWT claims (request.state.user or Cognito authorizer)
    teacher_id = "TODO_extract_from_jwt"

    try:
        result = use_case.execute(
            InviteStudentCommand(
                exam_id=exam_id,
                student_id=student_id,
                student_email=body.student_email,
                teacher_id=teacher_id,
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
    except StudentAlreadyInvitedError:
        # TODO(#10): re-invite path — use case should still return success with re_invited=True
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Re-invite path not yet implemented.",
        )

    return InviteStudentResponse(
        student_id=result.student.student_id,
        exam_id=result.student.exam_id,
        re_invited=result.re_invited,
    )


def _build_invite_adapter() -> CognitoSesStudentInviteAdapter:
    user_pool_id = os.getenv("COGNITO_USER_POOL_ID")
    ses_from_address = os.getenv("SES_FROM_ADDRESS")
    if not user_pool_id or not ses_from_address:
        raise RuntimeError(
            "Missing configuration: set COGNITO_USER_POOL_ID and SES_FROM_ADDRESS."
        )
    return CognitoSesStudentInviteAdapter(
        user_pool_id=user_pool_id,
        ses_from_address=ses_from_address,
    )
