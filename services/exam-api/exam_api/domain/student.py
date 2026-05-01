"""Student domain entity for the invitation flow."""

from __future__ import annotations

# TODO(#10): decide whether InvitationStatus belongs here or as a StrEnum sibling
from grading_shared.domain.models import StrictModel
from pydantic import EmailStr


class Student(StrictModel):
    """Student aggregate created when a teacher invites a student to an exam."""

    # TODO(#10): student_id == Cognito sub; confirm mapping with DynamoDB PK/SK design
    student_id: str
    exam_id: str
    email: EmailStr
    # TODO(#10): store temporary_password transiently (never persist); pass through invite flow only
