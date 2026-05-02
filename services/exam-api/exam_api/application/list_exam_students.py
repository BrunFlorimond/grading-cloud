"""Use case: teacher lists students enrolled in an exam."""

from __future__ import annotations

from grading_shared.domain.models import StrictModel

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
    ) -> None:
        self._enrollment_repository = enrollment_repository

    async def execute(self, command: ListExamStudentsCommand) -> EnrolledStudentPage:
        # TODO(#15): implement — ownership check then delegate to repository
        raise NotImplementedError
