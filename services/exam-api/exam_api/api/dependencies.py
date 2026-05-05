"""Centralised FastAPI RBAC dependency guards (JWT + Cognito groups).

Per-request PostgreSQL sessions with RLS GUCs:
``exam_api.composition.rls_sessions``.

Repository adapters: ``exam_api.composition.postgres_wiring``.

All 401/403 responses use the canonical JSON body: {"error": "...", "code": "..."}.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Request, status
from httpx import HTTPError
from jose import JWTError
from pydantic import BaseModel, ConfigDict
from exam_api.cognito_group_names import (
    COGNITO_ADMIN_GROUP,
    COGNITO_STUDENT_GROUP,
    COGNITO_TEACHER_GROUP,
)
from exam_api.ports.jwt_verifier_port import JwtVerifierPort

# ---------------------------------------------------------------------------
# Shared value objects returned by the dependency guards
# ---------------------------------------------------------------------------


class CurrentAdmin(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    admin_id: str


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
    if not isinstance(verifier, JwtVerifierPort):
        raise RuntimeError(
            "Missing JWT verifier — set app.state.jwt_verifier in lifespan."
        )
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
            detail={
                "error": "Authorization header must use Bearer scheme.",
                "code": "bad_scheme",
            },
        )
    return token


async def _decode_token(token: str, jwt_verifier: JwtVerifierPort) -> dict[str, Any]:
    try:
        return await jwt_verifier.decode_and_verify_token(token)
    except (HTTPError, JWTError) as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid or expired JWT token.", "code": "invalid_token"},
        ) from err


def _cognito_groups_from_claims(claims: dict[str, Any]) -> list[str]:
    """Normalise cognito:groups to a list of strings (Cognito uses a list; some mocks may differ)."""
    raw = claims.get("cognito:groups")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [g for g in raw if isinstance(g, str)]
    return []


# ---------------------------------------------------------------------------
# Public dependency guards
# ---------------------------------------------------------------------------


async def require_teacher(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentTeacher:
    """Dependency: ID token must include cognito:groups containing the teachers pool group."""

    token = _bearer_token(authorization)
    jwt_verifier = _get_jwt_verifier(request)
    claims = await _decode_token(token, jwt_verifier)
    groups = _cognito_groups_from_claims(claims)
    if COGNITO_TEACHER_GROUP not in groups:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Teacher group membership required.",
                "code": "insufficient_role",
            },
        )
    teacher_id = claims.get("sub")
    if not isinstance(teacher_id, str) or not teacher_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "Missing teacher identifier in JWT claims.",
                "code": "missing_subject",
            },
        )
    return CurrentTeacher(teacher_id=teacher_id)


async def require_student(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentStudent:
    """Dependency: ID token must include cognito:groups containing the students pool group."""

    token = _bearer_token(authorization)
    jwt_verifier = _get_jwt_verifier(request)
    claims = await _decode_token(token, jwt_verifier)
    groups = _cognito_groups_from_claims(claims)
    if COGNITO_STUDENT_GROUP not in groups:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Student group membership required.",
                "code": "insufficient_role",
            },
        )
    student_id = claims.get("sub")
    if not isinstance(student_id, str) or not student_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "Missing student identifier in JWT claims.",
                "code": "missing_subject",
            },
        )
    return CurrentStudent(student_id=student_id)


async def require_admin(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentAdmin:
    """Dependency: ID token must include cognito:groups containing the `admin` pool group."""
    token = _bearer_token(authorization)
    jwt_verifier = _get_jwt_verifier(request)
    claims = await _decode_token(token, jwt_verifier)
    groups = _cognito_groups_from_claims(claims)
    if COGNITO_ADMIN_GROUP not in groups:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Administrator group membership required.",
                "code": "insufficient_role",
            },
        )
    admin_id = claims.get("sub")
    if not isinstance(admin_id, str) or not admin_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "Missing administrator identifier in JWT claims.",
                "code": "missing_subject",
            },
        )
    return CurrentAdmin(admin_id=admin_id)


def require_own_data(path_param_name: str):
    """Dependency factory: student JWT sub must match the named path parameter.

    Usage::

        @router.get("/{student_id}/scope")
        async def get_scope(
            exam_id: str,
            student_id: str,
            _: Annotated[None, Depends(require_own_data("student_id"))],
        ): ...

    Raises 403 when the authenticated student differs from the path parameter.
    """

    async def _guard(
        request: Request,
        current_student: Annotated[CurrentStudent, Depends(require_student)],
    ) -> None:
        path_val = request.path_params.get(path_param_name)
        if path_val is None:
            raise RuntimeError(
                f"require_own_data: path parameter {path_param_name!r} is not on this route."
            )
        if path_val != current_student.student_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "Cannot access another student's resource.",
                    "code": "own_data_violation",
                },
            )

    return _guard
