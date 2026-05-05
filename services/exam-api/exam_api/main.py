"""FastAPI application entry point."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from exam_api.api.auth_router import router as auth_router
from exam_api.api.config_router import router as config_router
from exam_api.api.exam_router import router as exam_router
from exam_api.api.http_error_handlers import register_http_error_handlers
from exam_api.api.invite_router import router as invite_router
from exam_api.api.student_router import router as student_router
from exam_api.infrastructure.cognito_jwt_verifier import CognitoJwtVerifier
from exam_api.infrastructure.db import _get_engine, get_database_url
from exam_api.infrastructure.s3_exam_config_storage import S3ExamConfigStorage
from exam_api.infrastructure.student_invite_adapter import (
    CognitoSesStudentInviteAdapter,
)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Fail fast if DB config is incomplete (DATABASE_URL or DB_HOST/USER/PASSWORD/NAME).
    get_database_url()

    app.state.jwt_verifier = _build_jwt_verifier()
    app.state.student_invite_service = _build_student_invite_service()

    exam_config_bucket = os.getenv("EXAM_CONFIG_BUCKET")
    if exam_config_bucket:
        app.state.exam_config_storage = S3ExamConfigStorage(
            bucket_name=exam_config_bucket
        )

    engine = _get_engine()
    yield
    await engine.dispose()


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _build_student_invite_service() -> CognitoSesStudentInviteAdapter:
    user_pool_id = os.getenv("COGNITO_USER_POOL_ID")
    ses_from_address = os.getenv("SES_FROM_ADDRESS")
    if not user_pool_id or not ses_from_address:
        raise RuntimeError(
            "Missing configuration: set COGNITO_USER_POOL_ID and SES_FROM_ADDRESS."
        )
    return CognitoSesStudentInviteAdapter(
        user_pool_id=user_pool_id,
        ses_from_address=ses_from_address,
    )


def _build_jwt_verifier() -> CognitoJwtVerifier:
    user_pool_id = os.getenv("COGNITO_USER_POOL_ID")
    app_client_id = os.getenv("COGNITO_APP_CLIENT_ID")
    aws_region = os.getenv("AWS_REGION")
    issuer_override = os.getenv("COGNITO_ISSUER_URL")
    if not user_pool_id or not app_client_id:
        raise RuntimeError(
            "Missing Cognito JWT configuration: set COGNITO_USER_POOL_ID and "
            "COGNITO_APP_CLIENT_ID."
        )
    if issuer_override:
        issuer = issuer_override
    else:
        if not aws_region:
            raise RuntimeError(
                "Missing Cognito JWT configuration: set AWS_REGION or "
                "COGNITO_ISSUER_URL."
            )
        issuer = f"https://cognito-idp.{aws_region}.amazonaws.com/{user_pool_id}"
    return CognitoJwtVerifier(issuer=issuer, audience=app_client_id)


app = FastAPI(title="exam-api", version="0.1.0", lifespan=_lifespan)

register_http_error_handlers(app)

app.include_router(auth_router)
app.include_router(invite_router)
app.include_router(exam_router)
app.include_router(config_router)
app.include_router(student_router)
