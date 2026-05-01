"""Centralised FastAPI dependency guards for role-based access control.

Provides:
    require_teacher  — rejects non-teacher JWTs with 403
    require_student  — rejects non-student JWTs with 403
    require_own_data — rejects students accessing another student's resource with 403

All 401/403 responses use the canonical JSON body: {"error": "...", "code": "..."}.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from httpx import HTTPError
from jose import JWTError
from pydantic import BaseModel, ConfigDict

from exam_api.ports.jwt_verifier_port import JwtVerifierPort

# ---------------------------------------------------------------------------
# Shared value objects returned by the dependency guards
# ---------------------------------------------------------------------------


class CurrentTeacher(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    teacher_id: str


class CurrentStudent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    student_id: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_jwt_verifier(request: Request) -> JwtVerifierPort:
    verifier = getattr(request.app.state, "jwt_verifier", None)
    if not isinstance(verifier, JwtVerifierPort) and not hasattr(
        verifier, "decode_and_verify_token"
    ):
        raise RuntimeError("Missing JWT verifier — set app.state.jwt_verifier in lifespan.")
    return verifier


def _bearer_token(authorization: str | None) -> str:
    """Extract the raw token from an 'Authorization: Bearer <token>' header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Missing Authorization header.", "code": "missing_token"},
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Authorization header must use Bearer scheme.", "code": "bad_scheme"},
        )
    return token


async def _decode_token(token: str, jwt_verifier: JwtVerifierPort) -> dict:
    # TODO(#12): replace bare except with targeted exception types after integration tests exist
    try:
        return await jwt_verifier.decode_and_verify_token(token)
    except (HTTPError, JWTError) as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid or expired JWT token.", "code": "invalid_token"},
        ) from err


# ---------------------------------------------------------------------------
# Public dependency guards
# ---------------------------------------------------------------------------


async def require_teacher(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentTeacher:
    """Dependency: bearer token must carry custom:role=teacher.

    Raises 401 when the token is absent/invalid, 403 when the role is wrong.
    """
    # TODO(#12): implement — extract token, decode, assert role == "teacher"
    raise NotImplementedError


async def require_student(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentStudent:
    """Dependency: bearer token must carry custom:role=student.

    Raises 401 when the token is absent/invalid, 403 when the role is wrong.
    """
    # TODO(#12): implement — extract token, decode, assert role == "student"
    raise NotImplementedError


def require_own_data(student_id_path_param: str):
    """Dependency factory: student JWT sub must match the URL path student_id.

    Usage::
        @router.get("/{student_id}/results")
        async def get_results(
            student_id: str,
            current_student: Annotated[CurrentStudent, Depends(require_student)],
            _: Annotated[None, Depends(require_own_data("student_id"))],
        ): ...

    Raises 403 when the authenticated student differs from the path parameter.
    """

    # TODO(#12): implement — compare current_student.student_id with the resolved path param
    async def _guard(
        request: Request,
        current_student: Annotated[CurrentStudent, Depends(require_student)],
    ) -> None:
        raise NotImplementedError

    return _guard
