"""Use case: authenticate a teacher and return JWT tokens."""

from __future__ import annotations

from grading_shared.domain.models import StrictModel

from exam_api.ports.auth_service_port import AuthServicePort, AuthTokens


class LoginTeacherCommand(StrictModel):
    email: str
    password: str


class LoginTeacherResult(StrictModel):
    tokens: AuthTokens


class LoginTeacherUseCase:
    def __init__(self, auth_service: AuthServicePort) -> None:
        self._auth = auth_service

    def execute(self, command: LoginTeacherCommand) -> LoginTeacherResult:
        # TODO: call auth_service.login_teacher → get AuthTokens
        # TODO: raise InvalidCredentialsError (401) if Cognito NotAuthorizedException
        # TODO: raise UserNotFoundError (404) if Cognito UserNotFoundException
        raise NotImplementedError
