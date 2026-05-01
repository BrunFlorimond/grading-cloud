"""Use case: teacher invites a student to an exam."""

from __future__ import annotations

from grading_shared.domain.models import StrictModel
from pydantic import EmailStr

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
        invite_result = self._invite_service.invite_student(
            student_email=str(command.student_email),
            exam_id=command.exam_id,
        )
        return InviteStudentResult(
            student=Student(
                student_id=invite_result.cognito_sub,
                exam_id=command.exam_id,
                email=command.student_email,
            ),
            re_invited=invite_result.already_existed,
        )
