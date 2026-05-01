"""Use case: register a new teacher."""

from __future__ import annotations

from grading_shared.domain.models import StrictModel
from pydantic import EmailStr, Field, SecretStr, field_validator

from exam_api.domain.errors import DuplicateEmailError, WeakPasswordError
from exam_api.domain.teacher import Teacher
from exam_api.ports.auth_service_port import AuthServicePort


class RegisterTeacherCommand(StrictModel):
    email: EmailStr
    password: SecretStr
    full_name: str = Field(min_length=1)

    @field_validator("password")
    @classmethod
    def _validate_password_not_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("Password must not be empty.")
        return value


class RegisterTeacherResult(StrictModel):
    teacher: Teacher


class RegisterTeacherUseCase:
    def __init__(self, auth_service: AuthServicePort) -> None:
        self._auth = auth_service

    # TODO(#59): remove run_in_threadpool call in auth_router once this is async
    async def execute(self, command: RegisterTeacherCommand) -> RegisterTeacherResult:
        try:
            # TODO(#59): await async CognitoAuthAdapter.register_teacher (aiobotocore)
            teacher_id = await self._auth.register_teacher(
                email=str(command.email),
                password=command.password.get_secret_value(),
                full_name=command.full_name,
            )
        except (DuplicateEmailError, WeakPasswordError):
            raise

        return RegisterTeacherResult(
            teacher=Teacher(
                teacher_id=teacher_id,
                email=command.email,
                full_name=command.full_name,
            )
        )
