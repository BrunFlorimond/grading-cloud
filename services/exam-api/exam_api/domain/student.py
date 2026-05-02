"""Student domain entities for the invitation and enrollment flows."""

from __future__ import annotations

from enum import StrEnum

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


class SubmissionStatus(StrEnum):
    """Lifecycle status of a student's submission within an exam."""

    PENDING = "PENDING"
    CONVERTED = "CONVERTED"
    CORRECTED = "CORRECTED"


class EnrolledStudent(StrictModel):
    """Student registered for an exam by a teacher (school-ID-based, pre-invite)."""

    # TODO(#15): confirm whether student_id must be unique globally or per-exam only
    student_id: str
    exam_id: str
    nom: str
    prenom: str
    classe: str
    email: EmailStr | None = None
    submission_status: SubmissionStatus = SubmissionStatus.PENDING
