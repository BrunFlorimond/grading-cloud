"""Cognito + SES adapter implementing StudentInviteServicePort."""

from __future__ import annotations

# TODO(#10): no AWS imports in domain/ or ports/ — adapter-only
from typing import Any

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from exam_api.ports.student_invite_port import InviteStudentResult, StudentInviteServicePort


class CognitoSesStudentInviteAdapter(StudentInviteServicePort):
    """Implements StudentInviteServicePort using Cognito AdminCreateUser + SES SendEmail."""

    def __init__(
        self,
        *,
        user_pool_id: str,
        ses_from_address: str,
        cognito_client: Any | None = None,
        ses_client: Any | None = None,
    ) -> None:
        self._user_pool_id = user_pool_id
        self._ses_from_address = ses_from_address
        self._cognito = cognito_client or boto3.client("cognito-idp")
        self._ses = ses_client or boto3.client("ses")

    def invite_student(
        self,
        *,
        student_email: str,
        exam_id: str,
    ) -> InviteStudentResult:
        # TODO(#10): call self._cognito.admin_create_user with MessageAction="SUPPRESS"
        # TODO(#10): set UserAttributes: email, custom:role=student, custom:exam_id=exam_id
        # TODO(#10): catch ClientError UsernameExistsException → set already_existed=True, fetch existing sub
        # TODO(#10): call self._cognito.admin_add_user_to_group(GroupName="students")
        # TODO(#10): call self._send_invitation_email(student_email, temporary_password, exam_id)
        # TODO(#10): return InviteStudentResult(cognito_sub=..., temporary_password=..., already_existed=...)
        raise NotImplementedError  # noqa: EM101

    def _send_invitation_email(
        self,
        *,
        to_address: str,
        temporary_password: str,
        exam_id: str,
    ) -> None:
        # TODO(#10): compose SES email body with login URL, temporary_password, exam_id
        # TODO(#10): call self._ses.send_email(Source=self._ses_from_address, ...)
        raise NotImplementedError  # noqa: EM101

    @staticmethod
    def _extract_error_code(err: ClientError) -> str:
        return str(err.response.get("Error", {}).get("Code", ""))
