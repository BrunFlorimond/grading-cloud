"""FastAPI application entry point."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import aiobotocore.session
from fastapi import FastAPI

from exam_api.api.auth_router import router as auth_router
from exam_api.api.config_router import router as config_router
from exam_api.api.exam_router import router as exam_router
from exam_api.api.http_error_handlers import register_http_error_handlers
from exam_api.api.invite_router import router as invite_router
from exam_api.api.student_router import router as student_router
from exam_api.infrastructure.cognito_jwt_verifier import CognitoJwtVerifier
from exam_api.infrastructure.dynamodb_exam_creation_repository import (
    DynamoDbExamCreationRepository,
)
from exam_api.infrastructure.dynamodb_exam_ownership_repository import (
    DynamoDbExamOwnershipRepository,
)
from exam_api.infrastructure.dynamodb_invite_repository import DynamoDbInviteRepository
from exam_api.infrastructure.dynamodb_exam_config_repository import (
    DynamoDbExamConfigRepository,
)
from exam_api.infrastructure.dynamodb_exam_detail_repository import (
    DynamoDbExamDetailRepository,
)
from exam_api.infrastructure.dynamodb_student_enrollment_repository import (
    DynamoDbStudentEnrollmentRepository,
)
from exam_api.infrastructure.s3_exam_config_storage import S3ExamConfigStorage
from exam_api.infrastructure.student_invite_adapter import (
    CognitoSesStudentInviteAdapter,
)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    table_name = os.getenv("GRADING_TABLE_NAME")
    if not table_name:
        raise RuntimeError("Missing GRADING_TABLE_NAME configuration.")
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if not region:
        raise RuntimeError(
            "Missing AWS_REGION or AWS_DEFAULT_REGION for DynamoDB client."
        )
    session = aiobotocore.session.get_session()
    exam_config_bucket = os.getenv("EXAM_CONFIG_BUCKET")
    if not exam_config_bucket:
        raise RuntimeError("Missing EXAM_CONFIG_BUCKET configuration.")
    async with session.create_client("dynamodb", region_name=region) as dynamodb_client:
        async with session.create_client("s3", region_name=region) as s3_client:
            app.state.student_invite_service = _build_student_invite_service()
            app.state.invite_repository = _build_invite_repository()
            app.state.exam_ownership_repository = _build_exam_ownership_repository(
                table_name, dynamodb_client
            )
            app.state.exam_creation_repository = DynamoDbExamCreationRepository(
                table_name=table_name,
                dynamodb_client=dynamodb_client,
            )
            app.state.jwt_verifier = _build_jwt_verifier()
            app.state.exam_config_storage = S3ExamConfigStorage(
                bucket_name=exam_config_bucket,
                s3_client=s3_client,
            )
            app.state.exam_config_repository = DynamoDbExamConfigRepository(
                table_name=table_name,
                dynamodb_client=dynamodb_client,
            )
            app.state.student_enrollment_repository = (
                DynamoDbStudentEnrollmentRepository(
                    table_name=table_name,
                    dynamodb_client=dynamodb_client,
                )
            )
            app.state.exam_detail_repository = DynamoDbExamDetailRepository(
                table_name=table_name,
                dynamodb_client=dynamodb_client,
            )
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


def _build_exam_ownership_repository(
    table_name: str, dynamodb_client: Any
) -> DynamoDbExamOwnershipRepository:
    return DynamoDbExamOwnershipRepository(
        table_name=table_name,
        dynamodb_client=dynamodb_client,
    )


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
app.include_router(exam_router)
app.include_router(config_router)
app.include_router(student_router)
