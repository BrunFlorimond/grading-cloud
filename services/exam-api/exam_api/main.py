"""FastAPI application entry point."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from exam_api.api.auth_router import router as auth_router
from exam_api.api.invite_router import router as invite_router
from exam_api.infrastructure.student_invite_adapter import CognitoSesStudentInviteAdapter


@asynccontextmanager
async def _lifespan(app: FastAPI):
    app.state.student_invite_service = _build_student_invite_service()
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


app = FastAPI(title="exam-api", version="0.1.0", lifespan=_lifespan)

app.include_router(auth_router)
app.include_router(invite_router)
