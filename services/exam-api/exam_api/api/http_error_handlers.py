"""Centralised HTTP error formatting for consistent JSON on auth-related codes."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse


def register_http_error_handlers(app: FastAPI) -> None:
    """401/403 return flat `{"error": str, "code": str}`; other codes use FastAPI defaults."""

    @app.exception_handler(StarletteHTTPException)
    async def _flat_http_errors(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        if exc.status_code not in (401, 403):
            return await http_exception_handler(request, exc)
        detail = exc.detail
        if isinstance(detail, dict) and "error" in detail and "code" in detail:
            if exc.status_code == 401:
                return JSONResponse(
                    status_code=exc.status_code,
                    content=detail,
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return JSONResponse(status_code=exc.status_code, content=detail)
        if isinstance(detail, str):
            code = "unauthorized" if exc.status_code == 401 else "forbidden"
            if exc.status_code == 401:
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"error": detail, "code": code},
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": detail, "code": code},
            )
        fallback_code = "unauthorized" if exc.status_code == 401 else "forbidden"
        hdrs: dict[str, str] = {}
        if exc.status_code == 401:
            hdrs["WWW-Authenticate"] = "Bearer"
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "Unexpected authorization error payload.",
                "code": fallback_code,
            },
            headers=hdrs,
        )
