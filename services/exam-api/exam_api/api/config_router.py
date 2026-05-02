"""FastAPI router for POST /exams/{exam_id}/config/upload-urls and /confirm."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from exam_api.api.dependencies import CurrentTeacher, require_teacher
from exam_api.api.dependencies import get_exam_ownership_repository
from exam_api.application.confirm_exam_config import (
    ConfirmExamConfigCommand,
    ConfirmExamConfigUseCase,
)
from exam_api.application.get_exam_config_upload_urls import (
    GetExamConfigUploadUrlsCommand,
    GetExamConfigUploadUrlsUseCase,
    PresignedPostBundle,
)
from exam_api.domain.errors import (
    EXAM_NOT_FOUND_FOR_CLIENT,
    ExamConfigError,
    ExamConfigInvalidJsonError,
    ExamConfigMissingFilesError,
    ExamConfigWrongStatusError,
    ExamNotFoundError,
    ExamOwnershipError,
)
from exam_api.ports.exam_config_repository_port import ExamConfigRepositoryPort
from exam_api.ports.exam_config_storage_port import ExamConfigStoragePort
from exam_api.ports.exam_ownership_port import ExamOwnershipPort

router = APIRouter(prefix="/exams", tags=["config"])


class UploadUrlsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    upload_urls: dict[str, PresignedPostBundle]


class ConfirmConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    exam_id: str
    status: Literal["CONFIGURED"]


def get_exam_config_storage(request: Request) -> ExamConfigStoragePort:
    storage = getattr(request.app.state, "exam_config_storage", None)
    if not isinstance(storage, ExamConfigStoragePort):
        raise RuntimeError(
            "Missing exam config storage. Set app.state.exam_config_storage."
        )
    return storage


def get_exam_config_repository(request: Request) -> ExamConfigRepositoryPort:
    repository = getattr(request.app.state, "exam_config_repository", None)
    if not isinstance(repository, ExamConfigRepositoryPort):
        raise RuntimeError(
            "Missing exam config repository. Set app.state.exam_config_repository."
        )
    return repository


def provide_get_upload_urls_use_case(
    exam_ownership: Annotated[ExamOwnershipPort, Depends(get_exam_ownership_repository)],
    config_storage: Annotated[ExamConfigStoragePort, Depends(get_exam_config_storage)],
) -> GetExamConfigUploadUrlsUseCase:
    return GetExamConfigUploadUrlsUseCase(
        exam_ownership=exam_ownership,
        config_storage=config_storage,
    )


def provide_confirm_config_use_case(
    exam_ownership: Annotated[ExamOwnershipPort, Depends(get_exam_ownership_repository)],
    config_storage: Annotated[ExamConfigStoragePort, Depends(get_exam_config_storage)],
    config_repository: Annotated[ExamConfigRepositoryPort, Depends(get_exam_config_repository)],
) -> ConfirmExamConfigUseCase:
    return ConfirmExamConfigUseCase(
        exam_ownership=exam_ownership,
        config_storage=config_storage,
        config_repository=config_repository,
    )


@router.post(
    "/{exam_id}/config/upload-urls",
    response_model=UploadUrlsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_config_upload_urls(
    exam_id: str,
    current_teacher: Annotated[CurrentTeacher, Depends(require_teacher)],
    use_case: Annotated[
        GetExamConfigUploadUrlsUseCase, Depends(provide_get_upload_urls_use_case)
    ],
) -> UploadUrlsResponse:
    try:
        result = await use_case.execute(
            GetExamConfigUploadUrlsCommand(
                teacher_id=current_teacher.teacher_id,
                exam_id=exam_id,
            )
        )
    except ExamNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ExamOwnershipError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=EXAM_NOT_FOUND_FOR_CLIENT,
        ) from err
    return UploadUrlsResponse(upload_urls=result.upload_urls)


@router.post(
    "/{exam_id}/config/confirm",
    response_model=ConfirmConfigResponse,
    status_code=status.HTTP_200_OK,
)
async def confirm_config(
    exam_id: str,
    current_teacher: Annotated[CurrentTeacher, Depends(require_teacher)],
    use_case: Annotated[ConfirmExamConfigUseCase, Depends(provide_confirm_config_use_case)],
) -> ConfirmConfigResponse:
    try:
        result = await use_case.execute(
            ConfirmExamConfigCommand(
                teacher_id=current_teacher.teacher_id,
                exam_id=exam_id,
            )
        )
    except ExamNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ExamOwnershipError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=EXAM_NOT_FOUND_FOR_CLIENT,
        ) from err
    except ExamConfigMissingFilesError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {
                    "type": "missing_config_files",
                    "loc": ["body", "files"],
                    "msg": "One or more required config files are absent from storage.",
                    "missing": err.missing_filenames,
                }
            ],
        ) from err
    except ExamConfigInvalidJsonError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {
                    "type": "json_invalid",
                    "loc": ["body", err.filename],
                    "msg": err.parse_error,
                }
            ],
        ) from err
    except ExamConfigWrongStatusError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {
                    "type": "wrong_exam_status",
                    "loc": ["body", "exam"],
                    "msg": str(err),
                }
            ],
        ) from err
    except ExamConfigError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        ) from err
    return ConfirmConfigResponse(exam_id=result.exam_id, status=result.status)
