"""FastAPI router for POST /exams/{exam_id}/students and GET /exams/{exam_id}/students."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from exam_api.api.dependencies import CurrentTeacher, require_teacher
from exam_api.api.invite_router import (
    get_exam_ownership_repository,
    verify_teacher_exam_ownership,
)
from exam_api.application.add_students import (
    AddStudentsCommand,
    AddStudentsUseCase,
    StudentInput,
)
from exam_api.application.list_exam_students import (
    ListExamStudentsCommand,
    ListExamStudentsUseCase,
)
from exam_api.domain.errors import (
    DuplicateStudentError,
    EnrollmentExamNotFoundError,
    EnrollmentExamOwnershipError,
    InvalidExamListCursorError,
    StudentBatchTooLargeError,
)
from exam_api.ports.exam_ownership_port import ExamOwnershipPort
from exam_api.ports.student_enrollment_repository_port import StudentEnrollmentRepositoryPort

router = APIRouter(prefix="/exams", tags=["students"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class StudentInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    student_id: str | None = None
    nom: str = Field(..., min_length=1)
    prenom: str = Field(..., min_length=1)
    classe: str = Field(..., min_length=1)
    email: EmailStr | None = None


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


# ---------------------------------------------------------------------------
# Dependency providers
# ---------------------------------------------------------------------------


def get_enrollment_repository(request: Request) -> StudentEnrollmentRepositoryPort:
    repository = getattr(request.app.state, "student_enrollment_repository", None)
    if not isinstance(repository, StudentEnrollmentRepositoryPort):
        raise RuntimeError(
            "Missing enrollment repository. Set app.state.student_enrollment_repository."
        )
    return repository


def provide_add_students_use_case(
    repository: Annotated[
        StudentEnrollmentRepositoryPort, Depends(get_enrollment_repository)
    ],
    exam_ownership: Annotated[
        ExamOwnershipPort, Depends(get_exam_ownership_repository)
    ],
) -> AddStudentsUseCase:
    return AddStudentsUseCase(
        enrollment_repository=repository,
        exam_ownership_port=exam_ownership,
    )


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
    body: Annotated[list[StudentInputSchema], Field(min_length=1, max_length=50)],
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
    except EnrollmentExamNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except EnrollmentExamOwnershipError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": str(err),
                "code": "exam_ownership",
            },
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
    response_model=ListStudentsResponse,
    status_code=status.HTTP_200_OK,
)
async def list_students(
    exam_id: str,
    current_teacher: Annotated[CurrentTeacher, Depends(require_teacher)],
    _: Annotated[None, Depends(verify_teacher_exam_ownership)],
    use_case: Annotated[ListExamStudentsUseCase, Depends(provide_list_students_use_case)],
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> ListStudentsResponse:
    try:
        page = await use_case.execute(
            ListExamStudentsCommand(
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

    return ListStudentsResponse(
        items=[
            EnrolledStudentSchema(
                student_id=s.student_id,
                nom=s.nom,
                prenom=s.prenom,
                classe=s.classe,
                email=s.email,
                submission_status=s.submission_status.value,
            )
            for s in page.items
        ],
        next_cursor=page.next_cursor,
    )
