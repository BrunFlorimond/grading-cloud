"""Use case: teacher adds a batch of students to an exam."""

from __future__ import annotations

from grading_shared.domain.models import StrictModel
from pydantic import EmailStr

from exam_api.domain.errors import (
    EnrollmentExamNotFoundError,
    EnrollmentExamOwnershipError,
    StudentBatchTooLargeError,
)
from exam_api.domain.student import EnrolledStudent, SubmissionStatus
from exam_api.ports.exam_ownership_port import ExamOwnershipPort
from exam_api.ports.student_enrollment_repository_port import StudentEnrollmentRepositoryPort

_MAX_BATCH_SIZE = 50


class StudentInput(StrictModel):
    """Single student payload within a batch-add request."""

    student_id: str | None = None
    nom: str
    prenom: str
    classe: str
    email: EmailStr | None = None


class AddStudentsCommand(StrictModel):
    exam_id: str
    teacher_id: str
    students: list[StudentInput]


class AddStudentsResult(StrictModel):
    created: list[EnrolledStudent]


class AddStudentsUseCase:
    def __init__(
        self,
        enrollment_repository: StudentEnrollmentRepositoryPort,
        exam_ownership_port: ExamOwnershipPort,
    ) -> None:
        self._enrollment_repository = enrollment_repository
        self._exam_ownership_port = exam_ownership_port

    async def execute(self, command: AddStudentsCommand) -> AddStudentsResult:
        # TODO(#15): implement — validate batch size, ownership check, build entities, persist
        raise NotImplementedError

    def _validate_batch(self, students: list[StudentInput]) -> None:
        # TODO(#15): raise StudentBatchTooLargeError when len > _MAX_BATCH_SIZE
        raise NotImplementedError

    async def _check_ownership(self, *, exam_id: str, teacher_id: str) -> None:
        # TODO(#15): raise EnrollmentExamNotFoundError / EnrollmentExamOwnershipError
        raise NotImplementedError

    def _build_entities(
        self, *, exam_id: str, students: list[StudentInput]
    ) -> list[EnrolledStudent]:
        # TODO(#15): generate UUID for student_id when absent; build EnrolledStudent list
        raise NotImplementedError
