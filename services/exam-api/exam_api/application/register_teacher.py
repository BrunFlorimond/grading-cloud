"""Use case: register a new teacher."""

from __future__ import annotations

from grading_shared.domain.models import StrictModel

from exam_api.domain.teacher import Teacher
from exam_api.ports.auth_service_port import AuthServicePort


class RegisterTeacherCommand(StrictModel):
    # TODO: validate email format and password strength at this boundary
    email: str
    password: str
    full_name: str


class RegisterTeacherResult(StrictModel):
    teacher: Teacher


class RegisterTeacherUseCase:
    def __init__(self, auth_service: AuthServicePort) -> None:
        self._auth = auth_service

    def execute(self, command: RegisterTeacherCommand) -> RegisterTeacherResult:
        # TODO: call auth_service.register_teacher → get teacher_id (Cognito sub)
        # TODO: build Teacher aggregate from teacher_id + command fields
        # TODO: raise DuplicateEmailError (409) if Cognito UsernameExistsException
        # TODO: raise WeakPasswordError (400) if Cognito InvalidPasswordException
        raise NotImplementedError
