"""Use case: teacher confirms uploaded config files are valid and transitions exam status."""

from __future__ import annotations

from grading_shared.domain.models import StrictModel

from exam_api.ports.exam_config_repository_port import ExamConfigRepositoryPort
from exam_api.ports.exam_config_storage_port import ExamConfigStoragePort
from exam_api.ports.exam_ownership_port import ExamOwnershipPort


class ConfirmExamConfigCommand(StrictModel):
    teacher_id: str
    exam_id: str


class ConfirmExamConfigResult(StrictModel):
    exam_id: str
    status: str  # "CONFIGURED"


class ConfirmExamConfigUseCase:
    def __init__(
        self,
        exam_ownership: ExamOwnershipPort,
        config_storage: ExamConfigStoragePort,
        config_repository: ExamConfigRepositoryPort,
    ) -> None:
        self._exam_ownership = exam_ownership
        self._config_storage = config_storage
        self._config_repository = config_repository

    async def execute(self, command: ConfirmExamConfigCommand) -> ConfirmExamConfigResult:
        # TODO(#14): verify ownership via self._exam_ownership.verify_teacher_owns_exam
        # TODO(#14): call self._config_storage.all_files_exist; raise ExamConfigMissingFilesError listing absent files
        # TODO(#14): for each .json file, fetch bytes via self._config_storage.get_file_bytes and json.loads; raise ExamConfigInvalidJsonError with filename + parse error on failure
        # TODO(#14): build config_s3_keys = {filename: f"exams/{exam_id}/config/{filename}" for each file}
        # TODO(#14): call self._config_repository.save_exam_config(exam_id=..., config_s3_keys=...)
        # TODO(#14): return ConfirmExamConfigResult(exam_id=command.exam_id, status="CONFIGURED")
        raise NotImplementedError
