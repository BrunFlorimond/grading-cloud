"""Student domain entities for the invitation and enrollment flows."""

from __future__ import annotations

from enum import StrEnum

# TODO(#10): decide whether InvitationStatus belongs here or as a StrEnum sibling
from grading_shared.domain.models import StrictModel
from pydantic import EmailStr


class Student(StrictModel):
    """Student aggregate created when a teacher invites a student to an assignment."""

    student_id: str
    email: EmailStr


class SubmissionStatus(StrEnum):
    PENDING = "PENDING"
    CONVERTED = "CONVERTED"
    CORRECTED = "CORRECTED"


class StudentAssignment(StrictModel):
    """Junction between a student and an assignment, carries submission lifecycle."""

    student_id: str
    assignment_id: str
    nom: str
    prenom: str
    classe: str
    email: EmailStr | None = None
    submission_status: SubmissionStatus = SubmissionStatus.PENDING


# Backward-compat alias — existing use cases and ports still reference EnrolledStudent.
# exam_id maps to assignment_id; kept until all call-sites are updated.
class EnrolledStudent(StrictModel):
    student_id: str
    exam_id: str
    nom: str
    prenom: str
    classe: str
    email: EmailStr | None = None
    submission_status: SubmissionStatus = SubmissionStatus.PENDING
