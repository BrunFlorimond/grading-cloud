"""Use case: teacher views exam detail and pipeline status summary."""

from __future__ import annotations

from grading_shared.domain.models import StrictModel

from exam_api.ports.exam_detail_repository_port import ExamDetail, ExamDetailRepositoryPort


class GetExamDetailCommand(StrictModel):
    exam_id: str
    teacher_id: str


class GetExamDetailUseCase:
    """Ownership is enforced by ``verify_teacher_exam_ownership`` on the router."""

    def __init__(self, exam_detail_repository: ExamDetailRepositoryPort) -> None:
        self._exam_detail_repository = exam_detail_repository

    async def execute(self, command: GetExamDetailCommand) -> ExamDetail:
        # TODO(#16): call repository.get_exam_detail and return result
        # TODO(#16): map ExamNotFoundError → propagate (router converts to 404)
        raise NotImplementedError
