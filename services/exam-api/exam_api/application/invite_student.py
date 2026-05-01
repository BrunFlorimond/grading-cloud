"""Use case: teacher invites a student to an exam."""

from __future__ import annotations

# TODO(#10): import ExamRepositoryPort from grading_shared once StudentRepositoryPort is defined
from grading_shared.domain.models import StrictModel
from pydantic import EmailStr

from exam_api.domain.errors import (
    ExamNotFoundError,
    ExamOwnershipError,
    StudentAlreadyInvitedError,
)
from exam_api.domain.student import Student
from exam_api.ports.student_invite_port import StudentInviteServicePort


class InviteStudentCommand(StrictModel):
    exam_id: str
    student_id: str
    student_email: EmailStr
    # TODO(#10): teacher_id should come from the validated JWT claims, not the request body
    teacher_id: str


class InviteStudentResult(StrictModel):
    student: Student
    re_invited: bool


class InviteStudentUseCase:
    def __init__(
        self,
        invite_service: StudentInviteServicePort,
        # TODO(#10): inject ExamRepositoryPort to verify exam ownership
        # TODO(#10): inject StudentRepositoryPort to persist DynamoDB record (PK=EXAM#{exam_id}, SK=STUDENT#{student_id})
    ) -> None:
        self._invite_service = invite_service

    def execute(self, command: InviteStudentCommand) -> InviteStudentResult:
        # TODO(#10): load exam via ExamRepositoryPort; raise ExamNotFoundError if missing
        # TODO(#10): verify exam.teacher_id == command.teacher_id; raise ExamOwnershipError if not
        # TODO(#10): call self._invite_service.invite_student(...)
        # TODO(#10): persist Student record to DynamoDB (student_id = cognito_sub)
        # TODO(#10): if already_existed raise StudentAlreadyInvitedError to signal re-invite path
        raise NotImplementedError  # noqa: EM101
