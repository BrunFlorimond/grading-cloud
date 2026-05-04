"""Composition root: concrete adapters and request-scoped DB context for FastAPI.

RBAC guards live in ``exam_api.api.dependencies``.
RLS sessions and PostgreSQL repository wiring live in submodules below.
"""

from exam_api.composition.postgres_wiring import (
    get_exam_config_repository,
    get_exam_creation_repository,
    get_exam_detail_repository,
    get_exam_ownership_repository,
    get_enrollment_repository,
    get_invite_exam_repository,
    get_invite_scope_repository,
    get_student_scope_repository,
    get_verify_exam_ownership_use_case,
    verify_teacher_exam_ownership,
)

__all__ = [
    "get_exam_config_repository",
    "get_exam_creation_repository",
    "get_exam_detail_repository",
    "get_exam_ownership_repository",
    "get_enrollment_repository",
    "get_invite_exam_repository",
    "get_invite_scope_repository",
    "get_student_rls_session",
    "get_student_scope_repository",
    "get_teacher_rls_session",
    "get_verify_exam_ownership_use_case",
    "verify_teacher_exam_ownership",
]
