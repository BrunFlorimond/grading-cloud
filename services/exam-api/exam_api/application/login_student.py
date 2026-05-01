"""Use case: authenticate a student and handle NEW_PASSWORD_REQUIRED challenge."""

from __future__ import annotations

from grading_shared.domain.models import StrictModel
from pydantic import EmailStr, SecretStr, field_validator, model_validator

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
    tokens: AuthTokens | None = None
    challenge: AuthChallenge | None = None

    @model_validator(mode="after")
    def _exactly_one_outcome(self) -> LoginStudentResult:
        has_tokens = self.tokens is not None
        has_challenge = self.challenge is not None
        if has_tokens == has_challenge:
            raise ValueError("Exactly one of tokens or challenge must be set.")
        return self


class LoginStudentUseCase:
    def __init__(self, auth_service: AuthServicePort) -> None:
        self._auth = auth_service

    async def execute(self, command: LoginStudentCommand) -> LoginStudentResult:
        outcome = await self._auth.login_student(
            email=str(command.email),
            password=command.password.get_secret_value(),
        )
        if isinstance(outcome, AuthChallenge):
            return LoginStudentResult(tokens=None, challenge=outcome)
        return LoginStudentResult(tokens=outcome, challenge=None)
