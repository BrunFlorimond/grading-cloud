"""Use case: teacher creates a new exam."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from grading_shared.domain.exam import Exam, ExamStatus
from grading_shared.domain.models import StrictModel

from exam_api.domain.errors import ExamTitleRequiredError, ExamTitleTooLongError
from exam_api.ports.exam_creation_repository_port import ExamCreationRepositoryPort

_MAX_TITLE_LENGTH = 120


class CreateExamCommand(StrictModel):
    teacher_id: str
    title: str
    description: str | None = None
    subject: str | None = None


class CreateExamResult(StrictModel):
    exam_id: str
    status: str


class CreateExamUseCase:
    def __init__(self, exam_repository: ExamCreationRepositoryPort) -> None:
        self._exam_repository = exam_repository

    async def execute(self, command: CreateExamCommand) -> CreateExamResult:
        stripped = command.title.strip()
        if not stripped:
            raise ExamTitleRequiredError("Exam title is required.")
        if len(stripped) > _MAX_TITLE_LENGTH:
            raise ExamTitleTooLongError(
                f"Exam title must be at most {_MAX_TITLE_LENGTH} characters."
            )

        exam_id = str(uuid.uuid4())
        created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        exam = Exam(
            exam_id=exam_id,
            teacher_id=command.teacher_id,
            title=stripped,
            status=ExamStatus.DRAFT,
            description=command.description,
            subject=command.subject,
            created_at=created_at,
        )
        await self._exam_repository.create_exam(exam)
        return CreateExamResult(exam_id=exam_id, status="CREATED")
