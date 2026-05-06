"""Use case: register a new teacher."""

from __future__ import annotations

from grading_shared.domain.models import StrictModel
from pydantic import EmailStr, Field, SecretStr, field_validator

from exam_api.domain.errors import DuplicateEmailError, WeakPasswordError
from exam_api.domain.teacher import Teacher
from exam_api.ports.auth_service_port import AuthServicePort
from exam_api.ports.user_identity_repository_port import UserIdentityRepositoryPort


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
    def __init__(
        self,
        auth_service: AuthServicePort,
        user_identity_repository: UserIdentityRepositoryPort,
    ) -> None:
        self._auth = auth_service
        self._user_identity_repository = user_identity_repository

    async def execute(self, command: RegisterTeacherCommand) -> RegisterTeacherResult:
        try:
            teacher_id = await self._auth.register_teacher(
                email=str(command.email),
                password=command.password.get_secret_value(),
                full_name=command.full_name,
            )
        except (DuplicateEmailError, WeakPasswordError):
            raise

        teacher = await self._user_identity_repository.upsert_teacher(
            cognito_sub=teacher_id,
            email=str(command.email),
            full_name=command.full_name,
        )
        return RegisterTeacherResult(teacher=teacher)
