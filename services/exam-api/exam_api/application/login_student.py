"""Use case: authenticate a student and handle NEW_PASSWORD_REQUIRED challenge."""

from __future__ import annotations

from grading_shared.domain.models import StrictModel
from pydantic import EmailStr, SecretStr, field_validator

from exam_api.domain.errors import InvalidCredentialsError
from exam_api.ports.auth_service_port import AuthChallenge, AuthServicePort, AuthTokens


class LoginStudentCommand(StrictModel):
    email: EmailStr
    password: SecretStr

    @field_validator("password")
    @classmethod
    def _validate_password_not_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("Password must not be empty.")
        return value


class LoginStudentResult(StrictModel):
    # TODO(#11): exactly one of tokens or challenge will be set; consider
    #            replacing with a tagged union once the API contract is finalised.
    tokens: AuthTokens | None = None
    challenge: AuthChallenge | None = None


class LoginStudentUseCase:
    def __init__(self, auth_service: AuthServicePort) -> None:
        self._auth = auth_service

    async def execute(self, command: LoginStudentCommand) -> LoginStudentResult:
        # TODO(#11): call self._auth.login_student(), map result to LoginStudentResult
        raise NotImplementedError
