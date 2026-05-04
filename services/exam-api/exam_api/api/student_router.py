"""FastAPI router for POST /exams/{exam_id}/students and GET /exams/{exam_id}/students."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from exam_api.api.dependencies import (
    CurrentTeacher,
    get_teacher_rls_session,
    require_teacher,
    verify_teacher_exam_ownership,
)
from exam_api.application.add_students import (
    AddStudentsCommand,
    AddStudentsUseCase,
    StudentInput,
)
from exam_api.application.list_exam_student_statuses import (
    ListExamStudentStatusesCommand,
    ListExamStudentStatusesUseCase,
)
from exam_api.application.list_exam_students import ListExamStudentsUseCase
from exam_api.domain.errors import (
    DuplicateStudentError,
    InvalidExamListCursorError,
    StudentBatchTooLargeError,
)
from exam_api.infrastructure.postgres_exam_detail_repository import PostgresExamDetailRepository
from exam_api.infrastructure.postgres_student_enrollment_repository import PostgresStudentEnrollmentRepository
from exam_api.ports.exam_detail_repository_port import ExamDetailRepositoryPort
from exam_api.ports.student_enrollment_repository_port import (
    StudentEnrollmentRepositoryPort,
)

router = APIRouter(prefix="/exams", tags=["students"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class StudentInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    student_id: str | None = Field(default=None, min_length=1)
    nom: str = Field(..., min_length=1)
    prenom: str = Field(..., min_length=1)
    classe: str = Field(..., min_length=1)
    email: EmailStr | None = None

    @field_validator("student_id", mode="before")
    @classmethod
    def _normalize_student_id(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            stripped = v.strip()
            return stripped if stripped else None
        return v


class EnrolledStudentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    student_id: str
    nom: str
    prenom: str
    classe: str
    email: EmailStr | None
    submission_status: str


class AddStudentsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    created: list[EnrolledStudentSchema]


class ListStudentsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[EnrolledStudentSchema]
    next_cursor: str | None


class StudentPipelineStatusSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    student_id: str
    nom: str
    prenom: str
    classe: str
    submission_status: str
    pdf_available: bool


class ListStudentStatusesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[StudentPipelineStatusSchema]
    next_cursor: str | None


# ---------------------------------------------------------------------------
# Dependency providers
# ---------------------------------------------------------------------------


def get_exam_detail_repository(
    session: Annotated[AsyncSession, Depends(get_teacher_rls_session)],
) -> ExamDetailRepositoryPort:
    return PostgresExamDetailRepository(session)


def provide_list_student_statuses_use_case(
    repository: Annotated[
        ExamDetailRepositoryPort, Depends(get_exam_detail_repository)
    ],
) -> ListExamStudentStatusesUseCase:
    return ListExamStudentStatusesUseCase(exam_detail_repository=repository)


def get_enrollment_repository(
    session: Annotated[AsyncSession, Depends(get_teacher_rls_session)],
) -> StudentEnrollmentRepositoryPort:
    return PostgresStudentEnrollmentRepository(session)


def provide_add_students_use_case(
    repository: Annotated[
        StudentEnrollmentRepositoryPort, Depends(get_enrollment_repository)
    ],
) -> AddStudentsUseCase:
    return AddStudentsUseCase(enrollment_repository=repository)


def provide_list_students_use_case(
    repository: Annotated[
        StudentEnrollmentRepositoryPort, Depends(get_enrollment_repository)
    ],
) -> ListExamStudentsUseCase:
    return ListExamStudentsUseCase(enrollment_repository=repository)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{exam_id}/students",
    response_model=AddStudentsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_students(
    exam_id: str,
    current_teacher: Annotated[CurrentTeacher, Depends(require_teacher)],
    _: Annotated[None, Depends(verify_teacher_exam_ownership)],
    body: Annotated[list[StudentInputSchema], Body(min_length=1, max_length=50)],
    use_case: Annotated[AddStudentsUseCase, Depends(provide_add_students_use_case)],
) -> AddStudentsResponse:
    try:
        result = await use_case.execute(
            AddStudentsCommand(
                exam_id=exam_id,
                teacher_id=current_teacher.teacher_id,
                students=[
                    StudentInput(
                        student_id=s.student_id,
                        nom=s.nom,
                        prenom=s.prenom,
                        classe=s.classe,
                        email=s.email,
                    )
                    for s in body
                ],
            )
        )
    except StudentBatchTooLargeError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        ) from err
    except DuplicateStudentError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        ) from err

    return AddStudentsResponse(
        created=[
            EnrolledStudentSchema(
                student_id=s.student_id,
                nom=s.nom,
                prenom=s.prenom,
                classe=s.classe,
                email=s.email,
                submission_status=s.submission_status.value,
            )
            for s in result.created
        ]
    )


@router.get(
    "/{exam_id}/students",
    response_model=ListStudentStatusesResponse,
    status_code=status.HTTP_200_OK,
)
async def list_students(
    exam_id: str,
    current_teacher: Annotated[CurrentTeacher, Depends(require_teacher)],
    _: Annotated[None, Depends(verify_teacher_exam_ownership)],
    use_case: Annotated[
        ListExamStudentStatusesUseCase, Depends(provide_list_student_statuses_use_case)
    ],
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> ListStudentStatusesResponse:
    try:
        page = await use_case.execute(
            ListExamStudentStatusesCommand(
                exam_id=exam_id,
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

    return ListStudentStatusesResponse(
        items=[
            StudentPipelineStatusSchema(
                student_id=s.student_id,
                nom=s.nom,
                prenom=s.prenom,
                classe=s.classe,
                submission_status=s.submission_status,
                pdf_available=s.pdf_available,
            )
            for s in page.items
        ],
        next_cursor=page.next_cursor,
    )
