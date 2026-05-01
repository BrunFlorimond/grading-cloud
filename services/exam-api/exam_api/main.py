"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI

from exam_api.api.auth_router import router as auth_router
from exam_api.api.invite_router import router as invite_router

# TODO: add startup/shutdown lifespan to init AWS clients
app = FastAPI(title="exam-api", version="0.1.0")

app.include_router(auth_router)
app.include_router(invite_router)
