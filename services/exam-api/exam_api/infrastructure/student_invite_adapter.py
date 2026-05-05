"""Cognito + SES adapter implementing StudentInviteServicePort."""

from __future__ import annotations

import secrets
import string
from typing import Any

import aiobotocore.session
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from exam_api.cognito_group_names import COGNITO_STUDENT_GROUP
from exam_api.ports.student_invite_port import (
    InviteStudentResult,
    StudentInviteServicePort,
)


class CognitoSesStudentInviteAdapter(StudentInviteServicePort):
    """Implements StudentInviteServicePort using Cognito AdminCreateUser + SES SendEmail (aiobotocore)."""

    def __init__(
        self,
        *,
        user_pool_id: str,
        ses_from_address: str,
        session: aiobotocore.session.AioSession | None = None,
        cognito_client: Any | None = None,
        ses_client: Any | None = None,
    ) -> None:
        self._user_pool_id = user_pool_id
        self._ses_from_address = ses_from_address
        self._session = session or aiobotocore.session.get_session()
        if (cognito_client is None) != (ses_client is None):
            raise ValueError(
                "cognito_client and ses_client must both be injected or both omitted."
            )
        self._injected_cognito = cognito_client
        self._injected_ses = ses_client

    async def invite_student(
        self,
        *,
        student_email: str,
        exam_id: str,
    ) -> InviteStudentResult:
        if self._injected_cognito is not None and self._injected_ses is not None:
            return await self._invite_with_clients(
                self._injected_cognito,
                self._injected_ses,
                student_email=student_email,
                exam_id=exam_id,
            )
        async with self._session.create_client("cognito-idp") as cognito:
            async with self._session.create_client("ses") as ses:
                return await self._invite_with_clients(
                    cognito,
                    ses,
                    student_email=student_email,
                    exam_id=exam_id,
                )

    async def _invite_with_clients(
        self,
        cognito: Any,
        ses: Any,
        *,
        student_email: str,
        exam_id: str,
    ) -> InviteStudentResult:
        temporary_password = self._generate_temporary_password()
        already_existed = False
        try:
            response = await cognito.admin_create_user(
                UserPoolId=self._user_pool_id,
                Username=student_email,
                TemporaryPassword=temporary_password,
                MessageAction="SUPPRESS",
                UserAttributes=[
                    {"Name": "email", "Value": student_email},
                    {"Name": "email_verified", "Value": "true"},
                ],
            )
            cognito_sub = self._extract_user_sub(
                response.get("User", {}), student_email
            )
        except ClientError as err:
            if self._extract_error_code(err) != "UsernameExistsException":
                raise
            already_existed = True
            existing_user = await cognito.admin_get_user(
                UserPoolId=self._user_pool_id,
                Username=student_email,
            )
            await cognito.admin_set_user_password(
                UserPoolId=self._user_pool_id,
                Username=student_email,
                Password=temporary_password,
                Permanent=False,
            )
            cognito_sub = self._extract_user_sub(existing_user, student_email)

        await cognito.admin_add_user_to_group(
            UserPoolId=self._user_pool_id,
            Username=student_email,
            GroupName=COGNITO_STUDENT_GROUP,
        )
        await self._send_invitation_email(
            ses,
            to_address=student_email,
            temporary_password=temporary_password,
            exam_id=exam_id,
        )
        return InviteStudentResult(
            cognito_sub=cognito_sub,
            already_existed=already_existed,
        )

    async def _send_invitation_email(
        self,
        ses: Any,
        *,
        to_address: str,
        temporary_password: str,
        exam_id: str,
    ) -> None:
        text_body = (
            "Vous avez ete invite(e) a la plateforme de correction.\n\n"
            f"Exam ID: {exam_id}\n"
            f"Email: {to_address}\n"
            f"Mot de passe temporaire: {temporary_password}\n\n"
            "Connectez-vous puis modifiez votre mot de passe des la premiere connexion."
        )
        html_body = (
            "<p>Vous avez ete invite(e) a la plateforme de correction.</p>"
            f"<p><strong>Exam ID:</strong> {exam_id}<br>"
            f"<strong>Email:</strong> {to_address}<br>"
            f"<strong>Mot de passe temporaire:</strong> {temporary_password}</p>"
            "<p>Connectez-vous puis modifiez votre mot de passe des la premiere connexion.</p>"
        )
        await ses.send_email(
            Source=self._ses_from_address,
            Destination={"ToAddresses": [to_address]},
            Message={
                "Subject": {"Data": "Invitation etudiant grading-cloud"},
                "Body": {
                    "Text": {"Data": text_body},
                    "Html": {"Data": html_body},
                },
            },
        )

    @staticmethod
    def _extract_user_sub(user_payload: dict[str, Any], student_email: str) -> str:
        attributes = user_payload.get("UserAttributes") or user_payload.get(
            "Attributes", []
        )
        if not isinstance(attributes, list):
            raise RuntimeError(
                f"Cognito response for {student_email} does not contain valid attributes."
            )
        for attribute in attributes:
            if not isinstance(attribute, dict):
                continue
            if attribute.get("Name") != "sub":
                continue
            value = attribute.get("Value")
            if isinstance(value, str) and value:
                return value
        raise RuntimeError(f"Missing Cognito sub for invited student {student_email}.")

    @staticmethod
    def _generate_temporary_password(length: int = 20) -> str:
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        return f"Aa1!{password}"

    @staticmethod
    def _extract_error_code(err: ClientError) -> str:
        return str(err.response.get("Error", {}).get("Code", ""))
