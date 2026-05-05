"""Use case: complete NEW_PASSWORD_REQUIRED challenge and return JWT tokens."""

from __future__ import annotations

from grading_shared.domain.models import StrictModel
from pydantic import EmailStr, SecretStr, field_validator

from exam_api.ports.auth_service_port import AuthServicePort, AuthTokens


class ChangeStudentPasswordCommand(StrictModel):
    email: EmailStr
    session: str
    new_password: SecretStr

    @field_validator("new_password")
    @classmethod
    def _validate_password_not_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("New password must not be empty.")
        return value

    @field_validator("session")
    @classmethod
    def _validate_session_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Session token must not be empty.")
        return value


class ChangeStudentPasswordResult(StrictModel):
    tokens: AuthTokens


class ChangeStudentPasswordUseCase:
    def __init__(self, auth_service: AuthServicePort) -> None:
        self._auth = auth_service

    async def execute(
        self, command: ChangeStudentPasswordCommand
    ) -> ChangeStudentPasswordResult:
        tokens = await self._auth.respond_to_new_password_challenge(
            email=str(command.email),
            session=command.session,
            new_password=command.new_password.get_secret_value(),
        )
        return ChangeStudentPasswordResult(tokens=tokens)
