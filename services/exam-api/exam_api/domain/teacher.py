"""Teacher domain entity."""

from __future__ import annotations

from grading_shared.domain.models import StrictModel


class Teacher(StrictModel):
    # TODO: implement Teacher domain entity
    # Fields: teacher_id (Cognito sub, UUID), email, full_name
    teacher_id: str
    email: str
    full_name: str
