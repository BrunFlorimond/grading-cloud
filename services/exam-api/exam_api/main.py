"""FastAPI application entry point."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from exam_api.api.auth_router import router as auth_router
from exam_api.api.http_error_handlers import register_http_error_handlers
from exam_api.api.invite_router import router as invite_router
from exam_api.infrastructure.cognito_jwt_verifier import CognitoJwtVerifier
from exam_api.infrastructure.dynamodb_exam_ownership_repository import (
    DynamoDbExamOwnershipRepository,
)
from exam_api.infrastructure.dynamodb_invite_repository import DynamoDbInviteRepository
from exam_api.infrastructure.student_invite_adapter import (
    CognitoSesStudentInviteAdapter,
)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    app.state.student_invite_service = _build_student_invite_service()
    app.state.invite_repository = _build_invite_repository()
    app.state.exam_ownership_repository = _build_exam_ownership_repository()
    app.state.jwt_verifier = _build_jwt_verifier()
    yield


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


def _build_invite_repository() -> DynamoDbInviteRepository:
    table_name = os.getenv("GRADING_TABLE_NAME")
    if not table_name:
        raise RuntimeError("Missing GRADING_TABLE_NAME configuration.")
    return DynamoDbInviteRepository(table_name=table_name)


def _build_exam_ownership_repository() -> DynamoDbExamOwnershipRepository:
    table_name = os.getenv("GRADING_TABLE_NAME")
    if not table_name:
        raise RuntimeError("Missing GRADING_TABLE_NAME configuration.")
    return DynamoDbExamOwnershipRepository(table_name=table_name)


def _build_jwt_verifier() -> CognitoJwtVerifier:
    user_pool_id = os.getenv("COGNITO_USER_POOL_ID")
    app_client_id = os.getenv("COGNITO_APP_CLIENT_ID")
    aws_region = os.getenv("AWS_REGION")
    if not user_pool_id or not app_client_id or not aws_region:
        raise RuntimeError(
            "Missing Cognito JWT configuration: set COGNITO_USER_POOL_ID, "
            "COGNITO_APP_CLIENT_ID and AWS_REGION."
        )
    issuer = f"https://cognito-idp.{aws_region}.amazonaws.com/{user_pool_id}"
    return CognitoJwtVerifier(issuer=issuer, audience=app_client_id)


app = FastAPI(title="exam-api", version="0.1.0", lifespan=_lifespan)

register_http_error_handlers(app)

app.include_router(auth_router)
app.include_router(invite_router)
