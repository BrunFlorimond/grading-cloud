"""Use case: authenticate a teacher and return JWT tokens."""

from __future__ import annotations

from grading_shared.domain.models import StrictModel
from pydantic import EmailStr, Field

from exam_api.domain.errors import InvalidCredentialsError
from exam_api.ports.auth_service_port import AuthServicePort, AuthTokens


class LoginTeacherCommand(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1)


class LoginTeacherResult(StrictModel):
    tokens: AuthTokens


class LoginTeacherUseCase:
    def __init__(self, auth_service: AuthServicePort) -> None:
        self._auth = auth_service

    def execute(self, command: LoginTeacherCommand) -> LoginTeacherResult:
        try:
            tokens = self._auth.login_teacher(
                email=str(command.email),
                password=command.password,
            )
        except InvalidCredentialsError:
            raise

        return LoginTeacherResult(tokens=tokens)
