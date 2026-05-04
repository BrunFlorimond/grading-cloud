"""Use case: teacher invites a student to an exam."""

from __future__ import annotations

from grading_shared.domain.exam import Exam
from grading_shared.ports import ExamRepositoryPort
from grading_shared.domain.models import StrictModel
from pydantic import EmailStr

from exam_api.domain.errors import (
    ExamNotFoundError,
    ExamOwnershipError,
)
from exam_api.domain.student import Student
from exam_api.ports.student_scope_repository_port import StudentScopeRepositoryPort
from exam_api.ports.student_invite_port import StudentInviteServicePort


class InviteStudentCommand(StrictModel):
    exam_id: str
    student_id: str
    student_email: EmailStr
    teacher_id: str


class InviteStudentResult(StrictModel):
    student: Student
    re_invited: bool


class InviteStudentUseCase:
    def __init__(
        self,
        invite_service: StudentInviteServicePort,
        exam_repository: ExamRepositoryPort,
        student_scope_repository: StudentScopeRepositoryPort,
    ) -> None:
        self._invite_service = invite_service
        self._exam_repository = exam_repository
        self._student_scope_repository = student_scope_repository

    async def execute(self, command: InviteStudentCommand) -> InviteStudentResult:
        exam = await self._load_owned_exam(
            exam_id=command.exam_id,
            teacher_id=command.teacher_id,
        )
        invite_result = await self._invite_service.invite_student(
            student_email=str(command.student_email),
            exam_id=exam.exam_id,
        )
        student = Student(
            student_id=invite_result.cognito_sub,
            email=command.student_email,
        )
        await self._student_scope_repository.upsert_student_scope(
            student=student,
            exam_id=exam.exam_id,
            teacher_id=command.teacher_id,
            external_student_id=command.student_id,
        )
        return InviteStudentResult(
            student=student,
            re_invited=invite_result.already_existed,
        )

    async def _load_owned_exam(self, *, exam_id: str, teacher_id: str) -> Exam:
        exam = await self._exam_repository.get_exam(exam_id=exam_id)
        if exam is None:
            raise ExamNotFoundError(f"Exam {exam_id} not found.")
        if exam.teacher_id != teacher_id:
            raise ExamOwnershipError(
                f"Teacher {teacher_id} does not own exam {exam_id}."
            )
        return exam
