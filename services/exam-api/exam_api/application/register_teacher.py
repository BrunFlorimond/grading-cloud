"""Use case: register a new teacher."""

from __future__ import annotations

from grading_shared.domain.models import StrictModel
from pydantic import EmailStr, Field

from exam_api.domain.errors import DuplicateEmailError, WeakPasswordError
from exam_api.domain.teacher import Teacher
from exam_api.ports.auth_service_port import AuthServicePort


class RegisterTeacherCommand(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1)
    full_name: str = Field(min_length=1)


class RegisterTeacherResult(StrictModel):
    teacher: Teacher


class RegisterTeacherUseCase:
    def __init__(self, auth_service: AuthServicePort) -> None:
        self._auth = auth_service

    def execute(self, command: RegisterTeacherCommand) -> RegisterTeacherResult:
        try:
            teacher_id = self._auth.register_teacher(
                email=str(command.email),
                password=command.password,
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
