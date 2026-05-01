"""Teacher domain entity."""

from __future__ import annotations

from grading_shared.domain.models import StrictModel
from pydantic import EmailStr


class Teacher(StrictModel):
    """Teacher aggregate loaded from Cognito identity data."""

    teacher_id: str
    email: EmailStr
    full_name: str
