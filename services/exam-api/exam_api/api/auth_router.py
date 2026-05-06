"""FastAPI router for /auth endpoints."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, SecretStr, field_validator

from exam_api.application.change_student_password import (
    ChangeStudentPasswordCommand,
    ChangeStudentPasswordUseCase,
)
from exam_api.application.login_student import LoginStudentCommand, LoginStudentUseCase
from exam_api.application.login_teacher import LoginTeacherCommand, LoginTeacherUseCase
from exam_api.application.register_teacher import (
    RegisterTeacherCommand,
    RegisterTeacherUseCase,
)
from exam_api.api.dependencies import CurrentAdmin, require_admin
from exam_api.domain.errors import (
    DuplicateEmailError,
    InvalidCredentialsError,
    TeacherGroupAssignmentError,
    WeakPasswordError,
)
from exam_api.infrastructure.cognito_auth_adapter import CognitoAuthAdapter
from exam_api.infrastructure.db import raw_session
from exam_api.infrastructure.postgres_user_identity_repository import (
    PostgresUserIdentityRepository,
)
from exam_api.ports.user_identity_repository_port import UserIdentityRepositoryPort

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    email: EmailStr
    password: SecretStr
    full_name: str

    @field_validator("password")
    @classmethod
    def _validate_password_not_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("Password must not be empty.")
        return value


class RegisterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    teacher_id: str
    email: str
    full_name: str


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    email: EmailStr
    password: SecretStr

    @field_validator("password")
    @classmethod
    def _validate_password_not_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("Password must not be empty.")
        return value


class LoginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id_token: str
    refresh_token: str
    expires_in: int


async def get_user_identity_repository() -> AsyncGenerator[UserIdentityRepositoryPort, None]:
    async with raw_session() as session:
        yield PostgresUserIdentityRepository(session)


def get_register_use_case(
    user_identity_repository: Annotated[
        UserIdentityRepositoryPort, Depends(get_user_identity_repository)
    ],
) -> RegisterTeacherUseCase:
    return RegisterTeacherUseCase(
        auth_service=_build_auth_adapter(),
        user_identity_repository=user_identity_repository,
    )


def get_login_use_case() -> LoginTeacherUseCase:
    return LoginTeacherUseCase(auth_service=_build_auth_adapter())


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    body: RegisterRequest,
    _: Annotated[CurrentAdmin, Depends(require_admin)],
    use_case: Annotated[RegisterTeacherUseCase, Depends(get_register_use_case)],
) -> RegisterResponse:
    try:
        result = await use_case.execute(
            RegisterTeacherCommand(
                email=body.email,
                password=body.password,
                full_name=body.full_name,
            )
        )
    except DuplicateEmailError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err) or "A teacher account already exists for this email.",
        ) from err
    except WeakPasswordError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err) or "Password does not meet the required policy.",
        ) from err
    except TeacherGroupAssignmentError as err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(err) or "Teacher registration could not be completed.",
        ) from err

    return RegisterResponse(
        teacher_id=result.teacher.teacher_id,
        email=str(result.teacher.email),
        full_name=result.teacher.full_name,
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
)
async def login(
    body: LoginRequest,
    use_case: Annotated[LoginTeacherUseCase, Depends(get_login_use_case)],
) -> LoginResponse:
    try:
        result = await use_case.execute(
            LoginTeacherCommand(email=body.email, password=body.password)
        )
    except InvalidCredentialsError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": str(err) or "Invalid email or password.",
                "code": "invalid_credentials",
            },
        ) from err

    return LoginResponse(
        id_token=result.tokens.id_token,
        refresh_token=result.tokens.refresh_token,
        expires_in=result.tokens.expires_in,
    )


# ---------------------------------------------------------------------------
# Student login (may return NEW_PASSWORD_REQUIRED challenge)
# ---------------------------------------------------------------------------


class StudentLoginResponse(BaseModel):
    """Response for POST /auth/student-login (tokens or NEW_PASSWORD_REQUIRED challenge)."""

    model_config = ConfigDict(extra="forbid", strict=True)
    id_token: str | None = None
    refresh_token: str | None = None
    expires_in: int | None = None
    challenge_name: str | None = None
    session: str | None = None


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    email: EmailStr
    session: str
    new_password: SecretStr

    @field_validator("session")
    @classmethod
    def _validate_session_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Session token must not be empty.")
        return value

    @field_validator("new_password")
    @classmethod
    def _validate_password_not_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("New password must not be empty.")
        return value


class ChangePasswordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id_token: str
    refresh_token: str
    expires_in: int


def get_login_student_use_case() -> LoginStudentUseCase:
    return LoginStudentUseCase(auth_service=_build_auth_adapter())


def get_change_password_use_case() -> ChangeStudentPasswordUseCase:
    return ChangeStudentPasswordUseCase(auth_service=_build_auth_adapter())


@router.post(
    "/student-login",
    response_model=StudentLoginResponse,
    status_code=status.HTTP_200_OK,
)
async def student_login(
    body: LoginRequest,
    use_case: Annotated[LoginStudentUseCase, Depends(get_login_student_use_case)],
) -> StudentLoginResponse:
    try:
        result = await use_case.execute(
            LoginStudentCommand(email=body.email, password=body.password)
        )
    except InvalidCredentialsError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": str(err) or "Invalid email or password.",
                "code": "invalid_credentials",
            },
        ) from err

    if result.challenge is not None:
        return StudentLoginResponse(
            challenge_name=result.challenge.challenge_name,
            session=result.challenge.session,
        )

    tokens = result.tokens
    if tokens is None:
        raise RuntimeError("Login outcome missing tokens despite absent challenge.")
    return StudentLoginResponse(
        id_token=tokens.id_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post(
    "/change-password",
    response_model=ChangePasswordResponse,
    status_code=status.HTTP_200_OK,
)
async def change_password(
    body: ChangePasswordRequest,
    use_case: Annotated[
        ChangeStudentPasswordUseCase, Depends(get_change_password_use_case)
    ],
) -> ChangePasswordResponse:
    try:
        result = await use_case.execute(
            ChangeStudentPasswordCommand(
                email=body.email,
                session=body.session,
                new_password=body.new_password,
            )
        )
    except InvalidCredentialsError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": str(err) or "Invalid email or session.",
                "code": "invalid_credentials",
            },
        ) from err
    except WeakPasswordError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err) or "Password does not meet the required policy.",
        ) from err

    return ChangePasswordResponse(
        id_token=result.tokens.id_token,
        refresh_token=result.tokens.refresh_token,
        expires_in=result.tokens.expires_in,
    )


@lru_cache(maxsize=1)
def _cached_cognito_adapter(user_pool_id: str, client_id: str) -> CognitoAuthAdapter:
    return CognitoAuthAdapter(user_pool_id=user_pool_id, client_id=client_id)


def _build_auth_adapter() -> CognitoAuthAdapter:
    user_pool_id = os.getenv("COGNITO_USER_POOL_ID")
    client_id = os.getenv("COGNITO_APP_CLIENT_ID")
    if not user_pool_id or not client_id:
        raise RuntimeError(
            "Missing Cognito configuration: set COGNITO_USER_POOL_ID and COGNITO_APP_CLIENT_ID."
        )
    return _cached_cognito_adapter(user_pool_id, client_id)
