"""Port for the student invitation service (Cognito + SES)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from grading_shared.domain.models import StrictModel


class InviteStudentResult(StrictModel):
    """Data returned by the invite service after provisioning the student account."""

    cognito_sub: str
    already_existed: bool


@runtime_checkable
class StudentInviteServicePort(Protocol):
    def invite_student(
        self,
        *,
        student_email: str,
        exam_id: str,
    ) -> InviteStudentResult:
        """Create (or retrieve) a Cognito student account and send invitation email via SES.

        - If the student already exists in Cognito: resend the email, do NOT recreate account.
        - Cognito user must be added to the `students` group.
        - Cognito custom attributes: `custom:role=student`, `custom:exam_id=<exam_id>`.
        - TODO(#10): decide on MessageAction=SUPPRESS + custom SES email vs. Cognito built-in.
        """
        ...
