"""FastAPI router for /auth endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from exam_api.application.login_teacher import LoginTeacherCommand, LoginTeacherUseCase
from exam_api.application.register_teacher import (
    RegisterTeacherCommand,
    RegisterTeacherUseCase,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    # TODO: add email validator (pydantic EmailStr)
    email: str
    password: str
    full_name: str


class RegisterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    teacher_id: str
    email: str
    full_name: str


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    email: str
    password: str


class LoginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id_token: str
    refresh_token: str
    expires_in: int


def get_register_use_case() -> RegisterTeacherUseCase:
    # TODO: wire CognitoAuthAdapter with env-provided user_pool_id and client_id
    raise NotImplementedError


def get_login_use_case() -> LoginTeacherUseCase:
    # TODO: wire CognitoAuthAdapter with env-provided user_pool_id and client_id
    raise NotImplementedError


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    body: RegisterRequest,
    use_case: RegisterTeacherUseCase = Depends(get_register_use_case),
) -> RegisterResponse:
    # TODO: call use_case.execute(RegisterTeacherCommand(...))
    # TODO: map DuplicateEmailError → HTTP 409
    # TODO: map WeakPasswordError → HTTP 400 with message
    raise NotImplementedError


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
)
def login(
    body: LoginRequest,
    use_case: LoginTeacherUseCase = Depends(get_login_use_case),
) -> LoginResponse:
    # TODO: call use_case.execute(LoginTeacherCommand(...))
    # TODO: map InvalidCredentialsError → HTTP 401
    raise NotImplementedError
