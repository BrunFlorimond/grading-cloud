"""FastAPI router for /auth endpoints."""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, SecretStr, field_validator

from exam_api.application.login_teacher import LoginTeacherCommand, LoginTeacherUseCase
from exam_api.application.register_teacher import (
    RegisterTeacherCommand,
    RegisterTeacherUseCase,
)
from exam_api.domain.errors import (
    DuplicateEmailError,
    InvalidCredentialsError,
    WeakPasswordError,
)
from exam_api.infrastructure.cognito_auth_adapter import CognitoAuthAdapter

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


def get_register_use_case() -> RegisterTeacherUseCase:
    return RegisterTeacherUseCase(auth_service=_build_auth_adapter())


def get_login_use_case() -> LoginTeacherUseCase:
    return LoginTeacherUseCase(auth_service=_build_auth_adapter())


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    body: RegisterRequest,
    use_case: Annotated[RegisterTeacherUseCase, Depends(get_register_use_case)],
) -> RegisterResponse:
    try:
        result = use_case.execute(
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
def login(
    body: LoginRequest,
    use_case: Annotated[LoginTeacherUseCase, Depends(get_login_use_case)],
) -> LoginResponse:
    try:
        result = use_case.execute(
            LoginTeacherCommand(email=body.email, password=body.password)
        )
    except InvalidCredentialsError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err) or "Invalid email or password.",
        ) from err

    return LoginResponse(
        id_token=result.tokens.id_token,
        refresh_token=result.tokens.refresh_token,
        expires_in=result.tokens.expires_in,
    )


def _build_auth_adapter() -> CognitoAuthAdapter:
    user_pool_id = os.getenv("COGNITO_USER_POOL_ID")
    client_id = os.getenv("COGNITO_APP_CLIENT_ID")
    if not user_pool_id or not client_id:
        raise RuntimeError(
            "Missing Cognito configuration: set COGNITO_USER_POOL_ID and COGNITO_APP_CLIENT_ID."
        )
    return CognitoAuthAdapter(user_pool_id=user_pool_id, client_id=client_id)
