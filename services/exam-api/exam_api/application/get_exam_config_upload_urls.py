"""Use case: teacher requests pre-signed S3 URLs to upload exam config files."""

from __future__ import annotations

from grading_shared.domain.models import StrictModel

from exam_api.ports.exam_config_storage_port import ExamConfigStoragePort
from exam_api.ports.exam_ownership_port import ExamOwnershipPort


class GetExamConfigUploadUrlsCommand(StrictModel):
    teacher_id: str
    exam_id: str


class GetExamConfigUploadUrlsResult(StrictModel):
    upload_urls: dict[str, str]  # filename → presigned PUT URL


class GetExamConfigUploadUrlsUseCase:
    def __init__(
        self,
        exam_ownership: ExamOwnershipPort,
        config_storage: ExamConfigStoragePort,
    ) -> None:
        self._exam_ownership = exam_ownership
        self._config_storage = config_storage

    async def execute(
        self, command: GetExamConfigUploadUrlsCommand
    ) -> GetExamConfigUploadUrlsResult:
        await self._exam_ownership.verify_teacher_owns_exam(
            teacher_id=command.teacher_id,
            exam_id=command.exam_id,
        )
        upload_urls = await self._config_storage.generate_upload_urls(
            exam_id=command.exam_id
        )
        return GetExamConfigUploadUrlsResult(upload_urls=upload_urls)
