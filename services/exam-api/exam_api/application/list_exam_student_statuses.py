"""Use case: teacher lists per-student pipeline status for an exam."""

from __future__ import annotations

from grading_shared.domain.models import StrictModel

from exam_api.ports.exam_detail_repository_port import (
    ExamDetailRepositoryPort,
    StudentPipelinePage,
)


class ListExamStudentStatusesCommand(StrictModel):
    exam_id: str
    teacher_id: str
    limit: int
    cursor: str | None


class ListExamStudentStatusesUseCase:
    """Ownership is enforced by ``verify_teacher_exam_ownership`` on the router."""

    def __init__(self, exam_detail_repository: ExamDetailRepositoryPort) -> None:
        self._exam_detail_repository = exam_detail_repository

    async def execute(self, command: ListExamStudentStatusesCommand) -> StudentPipelinePage:
        # TODO(#16): call repository.list_exam_student_statuses with pagination args
        # TODO(#16): propagate InvalidExamListCursorError on bad cursor
        raise NotImplementedError
