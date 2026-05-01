"""Use case: teacher creates a new exam."""

from __future__ import annotations

import uuid

from grading_shared.domain.exam import Exam, ExamStatus
from grading_shared.domain.models import StrictModel

from exam_api.domain.errors import ExamTitleRequiredError, ExamTitleTooLongError
from exam_api.ports.exam_creation_repository_port import ExamCreationRepositoryPort

_MAX_TITLE_LENGTH = 120


class CreateExamCommand(StrictModel):
    teacher_id: str
    title: str
    # TODO(#13): add description and subject to the shared Exam model via shared-package agent
    description: str | None = None
    subject: str | None = None


class CreateExamResult(StrictModel):
    exam_id: str
    # TODO(#13): reconcile API status "CREATED" with ExamStatus.DRAFT in grading_shared
    status: str


class CreateExamUseCase:
    def __init__(self, exam_repository: ExamCreationRepositoryPort) -> None:
        self._exam_repository = exam_repository

    async def execute(self, command: CreateExamCommand) -> CreateExamResult:
        # TODO(#13): validate title (required, max 120 chars) → raise ExamTitleRequiredError /
        #   ExamTitleTooLongError
        # TODO(#13): generate UUID v4 exam_id
        # TODO(#13): build Exam aggregate with ExamStatus.DRAFT and persist via create_exam
        # TODO(#13): return CreateExamResult with exam_id and status="CREATED"
        raise NotImplementedError
