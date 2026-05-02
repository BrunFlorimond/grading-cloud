"""Use case: teacher adds a batch of students to an exam."""

from __future__ import annotations

import uuid

from grading_shared.domain.models import StrictModel
from pydantic import EmailStr

from exam_api.domain.errors import (
    DuplicateStudentError,
    EnrollmentExamNotFoundError,
    EnrollmentExamOwnershipError,
    ExamNotFoundError,
    ExamOwnershipError,
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
        self._validate_batch(command.students)
        await self._check_ownership(exam_id=command.exam_id, teacher_id=command.teacher_id)
        entities = self._build_entities(
            exam_id=command.exam_id, students=command.students
        )
        self._assert_no_duplicate_ids(entities)
        created = await self._enrollment_repository.add_students(
            exam_id=command.exam_id, students=entities
        )
        return AddStudentsResult(created=created)

    def _validate_batch(self, students: list[StudentInput]) -> None:
        if len(students) > _MAX_BATCH_SIZE:
            raise StudentBatchTooLargeError()

    async def _check_ownership(self, *, exam_id: str, teacher_id: str) -> None:
        try:
            await self._exam_ownership_port.verify_teacher_owns_exam(
                teacher_id=teacher_id, exam_id=exam_id
            )
        except ExamNotFoundError as err:
            raise EnrollmentExamNotFoundError(str(err)) from err
        except ExamOwnershipError as err:
            raise EnrollmentExamOwnershipError(str(err)) from err

    def _build_entities(
        self, *, exam_id: str, students: list[StudentInput]
    ) -> list[EnrolledStudent]:
        out: list[EnrolledStudent] = []
        for s in students:
            sid = s.student_id if s.student_id is not None else str(uuid.uuid4())
            out.append(
                EnrolledStudent(
                    student_id=sid,
                    exam_id=exam_id,
                    nom=s.nom,
                    prenom=s.prenom,
                    classe=s.classe,
                    email=s.email,
                    submission_status=SubmissionStatus.PENDING,
                )
            )
        return out

    @staticmethod
    def _assert_no_duplicate_ids(students: list[EnrolledStudent]) -> None:
        seen: set[str] = set()
        for s in students:
            if s.student_id in seen:
                raise DuplicateStudentError(s.student_id, s.exam_id)
            seen.add(s.student_id)
