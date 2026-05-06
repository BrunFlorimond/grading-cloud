"""Async SQLAlchemy engine, session factory, and RLS context middleware."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncGenerator, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_database_url() -> str:
    """Resolve DATABASE_URL.

    Priority:
    1. ``DATABASE_URL`` env var (used in local dev / tunneled migrations).
    2. Components ``DB_HOST``, ``DB_PORT`` (default 5432), ``DB_NAME``,
       ``DB_USERNAME``, ``DB_PASSWORD`` — injected by ECS in production.
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    host = os.environ["DB_HOST"]
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ["DB_NAME"]
    user = os.environ["DB_USERNAME"]
    password = os.environ["DB_PASSWORD"]
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            _get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_factory


@dataclass(frozen=True)
class RLSContext:
    user_id: str
    user_type: Literal["teacher", "student"]


@asynccontextmanager
async def session_with_rls(rls: RLSContext) -> AsyncGenerator[AsyncSession, None]:
    """Open a transaction and inject RLS GUCs scoped to it via SET LOCAL."""
    async with _get_session_factory()() as session:
        async with session.begin():
            await session.execute(
                text(
                    """
                    SELECT
                        set_config('app.user_id', :uid, true),
                        set_config('app.user_type', :utype, true)
                    """
                ),
                {"uid": rls.user_id, "utype": rls.user_type},
            )
            yield session


@asynccontextmanager
async def raw_session() -> AsyncGenerator[AsyncSession, None]:
    """Transaction without RLS context — for bootstrap upserts (e.g. teacher on login)."""
    async with _get_session_factory()() as session:
        async with session.begin():
            yield session
