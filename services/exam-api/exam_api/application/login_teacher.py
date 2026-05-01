"""Use case: authenticate a teacher and return JWT tokens."""

from __future__ import annotations

from grading_shared.domain.models import StrictModel
from pydantic import EmailStr, SecretStr, field_validator

from exam_api.domain.errors import InvalidCredentialsError
from exam_api.ports.auth_service_port import AuthServicePort, AuthTokens


class LoginTeacherCommand(StrictModel):
    email: EmailStr
    password: SecretStr

    @field_validator("password")
    @classmethod
    def _validate_password_not_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("Password must not be empty.")
        return value


class LoginTeacherResult(StrictModel):
    tokens: AuthTokens


class LoginTeacherUseCase:
    def __init__(self, auth_service: AuthServicePort) -> None:
        self._auth = auth_service

    async def execute(self, command: LoginTeacherCommand) -> LoginTeacherResult:
        try:
            tokens = await self._auth.login_teacher(
                email=str(command.email),
                password=command.password.get_secret_value(),
            )
        except InvalidCredentialsError:
            raise

        return LoginTeacherResult(tokens=tokens)
