"""Use case: teacher adds a batch of students to an exam."""

from __future__ import annotations

import uuid

from grading_shared.domain.models import StrictModel
from pydantic import EmailStr, Field, field_validator

from exam_api.domain.errors import DuplicateStudentError, StudentBatchTooLargeError
from exam_api.domain.student import EnrolledStudent, SubmissionStatus
from exam_api.ports.student_enrollment_repository_port import StudentEnrollmentRepositoryPort

_MAX_BATCH_SIZE = 50


class StudentInput(StrictModel):
    """Single student payload within a batch-add request."""

    student_id: str | None = Field(default=None, min_length=1)
    nom: str
    prenom: str
    classe: str
    email: EmailStr | None = None

    @field_validator("student_id", mode="before")
    @classmethod
    def _normalize_student_id(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            stripped = v.strip()
            return stripped if stripped else None
        return v


class AddStudentsCommand(StrictModel):
    exam_id: str
    teacher_id: str
    students: list[StudentInput]


class AddStudentsResult(StrictModel):
    created: list[EnrolledStudent]


class AddStudentsUseCase:
    """Ownership is enforced by ``verify_teacher_exam_ownership`` on the router."""

    def __init__(
        self,
        enrollment_repository: StudentEnrollmentRepositoryPort,
    ) -> None:
        self._enrollment_repository = enrollment_repository

    async def execute(self, command: AddStudentsCommand) -> AddStudentsResult:
        self._validate_batch(command.students)
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

    def _build_entities(
        self, *, exam_id: str, students: list[StudentInput]
    ) -> list[EnrolledStudent]:
        out: list[EnrolledStudent] = []
        for s in students:
            raw_id = s.student_id
            if raw_id is None or not str(raw_id).strip():
                sid = str(uuid.uuid4())
            else:
                sid = str(raw_id).strip()
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
