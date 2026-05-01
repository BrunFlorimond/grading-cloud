"""Use case: teacher lists their own exams (paginated)."""

from __future__ import annotations

from grading_shared.domain.models import StrictModel

from exam_api.ports.exam_creation_repository_port import ExamCreationRepositoryPort, ExamPage

_DEFAULT_PAGE_SIZE = 20


class ListTeacherExamsCommand(StrictModel):
    teacher_id: str
    limit: int = _DEFAULT_PAGE_SIZE
    cursor: str | None = None


class ListTeacherExamsUseCase:
    def __init__(self, exam_repository: ExamCreationRepositoryPort) -> None:
        self._exam_repository = exam_repository

    async def execute(self, command: ListTeacherExamsCommand) -> ExamPage:
        return await self._exam_repository.list_teacher_exams(
            teacher_id=command.teacher_id,
            limit=command.limit,
            cursor=command.cursor,
        )
