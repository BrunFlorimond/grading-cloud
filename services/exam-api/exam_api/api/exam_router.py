"""FastAPI router for POST /exams, GET /exams, and GET /exams/{exam_id}."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from grading_shared.domain.exam import ExamStatus
from pydantic import BaseModel, ConfigDict, Field

from exam_api.api.dependencies import CurrentTeacher, require_teacher, verify_teacher_exam_ownership
from exam_api.application.create_exam import CreateExamCommand, CreateExamUseCase
from exam_api.application.get_exam_detail import GetExamDetailCommand, GetExamDetailUseCase
from exam_api.application.list_teacher_exams import ListTeacherExamsCommand, ListTeacherExamsUseCase
from exam_api.domain.errors import (
    ExamCreationConflictError,
    ExamNotFoundError,
    ExamTitleRequiredError,
    InvalidExamListCursorError,
)
from exam_api.ports.exam_creation_repository_port import ExamCreationRepositoryPort
from exam_api.ports.exam_detail_repository_port import ExamDetailRepositoryPort

router = APIRouter(prefix="/exams", tags=["exams"])


def _api_exam_status(status: ExamStatus) -> str:
    """Stable API strings: uppercase labels for create/configure flows; enum values elsewhere."""
    if status == ExamStatus.CREATED:
        return "CREATED"
    if status == ExamStatus.CONFIGURED:
        return "CONFIGURED"
    return status.value


class CreateExamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    title: str = Field(..., min_length=1, max_length=120)
    description: str | None = None
    subject: str | None = None


class CreateExamResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    exam_id: str
    status: str


class ExamSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    exam_id: str
    title: str
    status: str


class ListExamsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[ExamSummary]
    next_cursor: str | None


class StatusCountsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    # TODO(#16): extend fields once SubmissionStatus enum is finalised
    pending: int


class ExamDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    exam_id: str
    title: str
    status: str
    description: str | None
    subject: str | None
    created_at: str | None
    # TODO(#16): confirm DynamoDB attribute names for pipeline timestamps
    pipeline_started_at: str | None
    pipeline_completed_at: str | None
    status_counts: StatusCountsResponse


def get_exam_detail_repository(request: Request) -> ExamDetailRepositoryPort:
    repository = getattr(request.app.state, "exam_detail_repository", None)
    if not isinstance(repository, ExamDetailRepositoryPort):
        raise RuntimeError(
            "Missing exam detail repository. Set app.state.exam_detail_repository."
        )
    return repository


def provide_get_exam_detail_use_case(
    repository: Annotated[ExamDetailRepositoryPort, Depends(get_exam_detail_repository)],
) -> GetExamDetailUseCase:
    return GetExamDetailUseCase(exam_detail_repository=repository)


def get_exam_creation_repository(request: Request) -> ExamCreationRepositoryPort:
    repository = getattr(request.app.state, "exam_creation_repository", None)
    if not isinstance(repository, ExamCreationRepositoryPort):
        raise RuntimeError(
            "Missing exam creation repository. Set app.state.exam_creation_repository."
        )
    return repository


def provide_create_exam_use_case(
    repository: Annotated[ExamCreationRepositoryPort, Depends(get_exam_creation_repository)],
) -> CreateExamUseCase:
    return CreateExamUseCase(exam_repository=repository)


def provide_list_teacher_exams_use_case(
    repository: Annotated[ExamCreationRepositoryPort, Depends(get_exam_creation_repository)],
) -> ListTeacherExamsUseCase:
    return ListTeacherExamsUseCase(exam_repository=repository)


@router.post("", response_model=CreateExamResponse, status_code=status.HTTP_201_CREATED)
async def create_exam(
    body: CreateExamRequest,
    current_teacher: Annotated[CurrentTeacher, Depends(require_teacher)],
    use_case: Annotated[CreateExamUseCase, Depends(provide_create_exam_use_case)],
) -> CreateExamResponse:
    try:
        result = await use_case.execute(
            CreateExamCommand(
                teacher_id=current_teacher.teacher_id,
                title=body.title,
                description=body.description,
                subject=body.subject,
            )
        )
    except ExamTitleRequiredError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        ) from err
    except ExamCreationConflictError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        ) from err
    return CreateExamResponse(exam_id=result.exam_id, status=result.status)


@router.get("", response_model=ListExamsResponse, status_code=status.HTTP_200_OK)
async def list_exams(
    current_teacher: Annotated[CurrentTeacher, Depends(require_teacher)],
    use_case: Annotated[ListTeacherExamsUseCase, Depends(provide_list_teacher_exams_use_case)],
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> ListExamsResponse:
    try:
        page = await use_case.execute(
            ListTeacherExamsCommand(
                teacher_id=current_teacher.teacher_id,
                limit=limit,
                cursor=cursor,
            )
        )
    except InvalidExamListCursorError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        ) from err
    return ListExamsResponse(
        items=[
            ExamSummary(
                exam_id=exam.exam_id,
                title=exam.title,
                status=_api_exam_status(exam.status),
            )
            for exam in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.get("/{exam_id}", response_model=ExamDetailResponse, status_code=status.HTTP_200_OK)
async def get_exam_detail(
    exam_id: str,
    current_teacher: Annotated[CurrentTeacher, Depends(require_teacher)],
    _: Annotated[None, Depends(verify_teacher_exam_ownership)],
    use_case: Annotated[GetExamDetailUseCase, Depends(provide_get_exam_detail_use_case)],
) -> ExamDetailResponse:
    # TODO(#16): implement response mapping from ExamDetail domain object
    try:
        detail = await use_case.execute(
            GetExamDetailCommand(
                exam_id=exam_id,
                teacher_id=current_teacher.teacher_id,
            )
        )
    except ExamNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    # TODO(#16): map detail.status_counts to StatusCountsResponse
    return ExamDetailResponse(
        exam_id=detail.exam_id,
        title=detail.title,
        status=detail.status,
        description=detail.description,
        subject=detail.subject,
        created_at=detail.created_at,
        pipeline_started_at=detail.pipeline_started_at,
        pipeline_completed_at=detail.pipeline_completed_at,
        status_counts=StatusCountsResponse(pending=detail.status_counts.pending),
    )
