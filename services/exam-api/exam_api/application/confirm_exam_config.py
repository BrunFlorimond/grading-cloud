"""Use case: teacher confirms uploaded config files are valid and transitions exam status."""

from __future__ import annotations

import asyncio
import json
from typing import Literal

from grading_shared.domain.exam import ExamStatus
from grading_shared.domain.models import StrictModel

from exam_api.domain.errors import (
    ExamConfigError,
    ExamConfigInvalidJsonError,
    ExamConfigMissingFilesError,
    ExamConfigWrongStatusError,
    ExamNotFoundError,
)
from exam_api.ports.exam_config_repository_port import ExamConfigRepositoryPort
from exam_api.ports.exam_config_storage_port import CONFIG_FILES, ExamConfigStoragePort
from exam_api.ports.exam_ownership_port import ExamOwnershipPort


class ConfirmExamConfigCommand(StrictModel):
    teacher_id: str
    exam_id: str


class ConfirmExamConfigResult(StrictModel):
    exam_id: str
    status: Literal["CONFIGURED"]


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

    async def execute(
        self, command: ConfirmExamConfigCommand
    ) -> ConfirmExamConfigResult:
        await self._exam_ownership.verify_teacher_owns_exam(
            teacher_id=command.teacher_id,
            exam_id=command.exam_id,
        )
        exam = await self._config_repository.get_exam_for_config(
            exam_id=command.exam_id
        )
        if exam is None:
            raise ExamNotFoundError(f"Exam {command.exam_id} not found.")
        if exam.status not in (ExamStatus.CREATED, ExamStatus.CONFIGURED):
            raise ExamConfigWrongStatusError(
                "Exam must be in created or configured status to confirm configuration; "
                f"current status is {exam.status.value}."
            )
        if exam.created_at is None:
            raise ExamConfigError(
                "Exam metadata is missing created_at; cannot save config."
            )

        presence = await self._config_storage.all_files_exist(exam_id=command.exam_id)
        missing = [name for name, ok in presence.items() if not ok]
        if missing:
            raise ExamConfigMissingFilesError(missing)

        json_names = [f for f in CONFIG_FILES if f.endswith(".json")]
        json_bodies = await asyncio.gather(
            *[
                self._config_storage.get_file_bytes(
                    exam_id=command.exam_id,
                    filename=fname,
                )
                for fname in json_names
            ]
        )
        for filename, raw in zip(json_names, json_bodies, strict=True):
            try:
                json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as err:
                raise ExamConfigInvalidJsonError(filename, err.msg) from err

        exam_id = command.exam_id
        config_s3_keys = {
            filename: self._config_storage.config_object_key(
                exam_id=exam_id,
                filename=filename,
            )
            for filename in CONFIG_FILES
        }
        await self._config_repository.save_exam_config(
            exam_id=exam_id,
            teacher_id=exam.teacher_id,
            created_at=exam.created_at,
            config_s3_keys=config_s3_keys,
        )
        return ConfirmExamConfigResult(exam_id=exam_id, status="CONFIGURED")
