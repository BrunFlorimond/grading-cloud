"""Use case: teacher lists students enrolled in an exam."""

from __future__ import annotations

from grading_shared.domain.models import StrictModel

from exam_api.domain.errors import (
    EnrollmentExamNotFoundError,
    EnrollmentExamOwnershipError,
    ExamNotFoundError,
    ExamOwnershipError,
)
from exam_api.ports.exam_ownership_port import ExamOwnershipPort
from exam_api.ports.student_enrollment_repository_port import (
    EnrolledStudentPage,
    StudentEnrollmentRepositoryPort,
)


class ListExamStudentsCommand(StrictModel):
    exam_id: str
    teacher_id: str
    limit: int
    cursor: str | None


class ListExamStudentsUseCase:
    def __init__(
        self,
        enrollment_repository: StudentEnrollmentRepositoryPort,
        exam_ownership_port: ExamOwnershipPort,
    ) -> None:
        self._enrollment_repository = enrollment_repository
        self._exam_ownership_port = exam_ownership_port

    async def execute(self, command: ListExamStudentsCommand) -> EnrolledStudentPage:
        await self._check_ownership(
            exam_id=command.exam_id, teacher_id=command.teacher_id
        )
        return await self._enrollment_repository.list_exam_students(
            exam_id=command.exam_id,
            limit=command.limit,
            cursor=command.cursor,
        )

    async def _check_ownership(self, *, exam_id: str, teacher_id: str) -> None:
        try:
            await self._exam_ownership_port.verify_teacher_owns_exam(
                teacher_id=teacher_id, exam_id=exam_id
            )
        except ExamNotFoundError as err:
            raise EnrollmentExamNotFoundError(str(err)) from err
        except ExamOwnershipError as err:
            raise EnrollmentExamOwnershipError(str(err)) from err
