"""Use case: verify that a teacher owns the requested exam."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from exam_api.domain.errors import ExamOwnershipError
from exam_api.ports.exam_ownership_port import ExamOwnershipPort


class VerifyExamOwnershipCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    teacher_id: str
    exam_id: str


class VerifyExamOwnershipUseCase:
    def __init__(self, exam_ownership_repository: ExamOwnershipPort) -> None:
        self._repo = exam_ownership_repository

    async def execute(self, command: VerifyExamOwnershipCommand) -> None:
        # TODO(#12): call self._repo.teacher_owns_exam and raise ExamOwnershipError when False
        raise NotImplementedError
