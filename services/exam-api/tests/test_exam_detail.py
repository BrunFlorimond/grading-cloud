"""Tests for issue #16 — teacher views exam detail and per-student pipeline status."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, Mock, create_autospec

import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from exam_api.api.exam_router import router as exam_router
from exam_api.api.http_error_handlers import register_http_error_handlers
from exam_api.api.student_router import router as student_router
from exam_api.application.get_exam_detail import (
    GetExamDetailCommand,
    GetExamDetailUseCase,
)
from exam_api.application.list_exam_student_statuses import (
    ListExamStudentStatusesCommand,
    ListExamStudentStatusesUseCase,
)
from exam_api.domain.errors import (
    ExamNotFoundError,
    ExamOwnershipError,
    InvalidExamListCursorError,
)
from exam_api.infrastructure.dynamodb_exam_detail_repository import (
    DynamoDbExamDetailRepository,
)
from exam_api.ports.exam_creation_repository_port import ExamPage
from exam_api.ports.exam_detail_repository_port import (
    ExamDetail,
    ExamDetailRepositoryPort,
    StatusCounts,
    StudentPipelinePage,
    StudentPipelineStatus,
)
from exam_api.ports.exam_ownership_port import ExamOwnershipPort
from exam_api.ports.jwt_verifier_port import JwtVerifierPort


def _encode_lek_local(key: dict[str, object]) -> str:
    raw = json.dumps(key, sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


# --- GetExamDetailUseCase ---


@pytest.mark.asyncio
async def test_get_exam_detail_returns_metadata_and_status_counts() -> None:
    detail = ExamDetail(
        exam_id="e1",
        teacher_id="t1",
        title="Final",
        status="created",
        status_counts=StatusCounts(pending=3),
    )
    repo = Mock(spec=ExamDetailRepositoryPort)
    repo.get_exam_detail = AsyncMock(return_value=detail)

    use_case = GetExamDetailUseCase(exam_detail_repository=repo)
    result = await use_case.execute(
        GetExamDetailCommand(exam_id="e1", teacher_id="t1"),
    )

    assert result is detail
    repo.get_exam_detail.assert_awaited_once_with(exam_id="e1")


@pytest.mark.asyncio
async def test_get_exam_detail_propagates_exam_not_found_error() -> None:
    repo = Mock(spec=ExamDetailRepositoryPort)
    repo.get_exam_detail = AsyncMock(side_effect=ExamNotFoundError("missing"))

    use_case = GetExamDetailUseCase(exam_detail_repository=repo)

    with pytest.raises(ExamNotFoundError):
        await use_case.execute(GetExamDetailCommand(exam_id="e1", teacher_id="t1"))


# --- ListExamStudentStatusesUseCase ---


@pytest.mark.asyncio
async def test_list_exam_student_statuses_returns_page() -> None:
    page = StudentPipelinePage(
        items=[
            StudentPipelineStatus(
                student_id="s1",
                nom="D",
                prenom="P",
                classe="C",
                submission_status="PENDING",
                pdf_available=True,
            )
        ],
        next_cursor="n",
    )
    repo = Mock(spec=ExamDetailRepositoryPort)
    repo.list_exam_student_statuses = AsyncMock(return_value=page)

    use_case = ListExamStudentStatusesUseCase(exam_detail_repository=repo)
    result = await use_case.execute(
        ListExamStudentStatusesCommand(
            exam_id="e1",
            teacher_id="t1",
            limit=20,
            cursor=None,
        ),
    )

    assert result is page
    repo.list_exam_student_statuses.assert_awaited_once_with(
        exam_id="e1",
        limit=20,
        cursor=None,
    )


@pytest.mark.asyncio
async def test_list_exam_student_statuses_propagates_invalid_cursor_error() -> None:
    repo = Mock(spec=ExamDetailRepositoryPort)
    repo.list_exam_student_statuses = AsyncMock(
        side_effect=InvalidExamListCursorError("Invalid pagination cursor."),
    )

    use_case = ListExamStudentStatusesUseCase(exam_detail_repository=repo)

    with pytest.raises(InvalidExamListCursorError):
        await use_case.execute(
            ListExamStudentStatusesCommand(
                exam_id="e1",
                teacher_id="t1",
                limit=20,
                cursor="bad",
            ),
        )


# --- DynamoDbExamDetailRepository.get_exam_detail ---


@pytest.mark.asyncio
async def test_get_exam_detail_queries_correct_pk() -> None:
    client = AsyncMock()
    client.query = AsyncMock(
        return_value={
            "Items": [
                {
                    "PK": {"S": "EXAM#e1"},
                    "SK": {"S": "METADATA"},
                    "teacher_id": {"S": "t1"},
                    "title": {"S": "T"},
                    "status": {"S": "created"},
                }
            ],
            "LastEvaluatedKey": None,
        }
    )
    repo = DynamoDbExamDetailRepository(
        table_name="grading-table", dynamodb_client=client
    )

    detail = await repo.get_exam_detail(exam_id="e1")

    assert detail.exam_id == "e1"
    assert detail.teacher_id == "t1"
    assert detail.title == "T"
    assert detail.status == "created"
    kwargs = client.query.await_args.kwargs
    assert kwargs["KeyConditionExpression"] == "PK = :pk"
    assert kwargs["ExpressionAttributeValues"][":pk"]["S"] == "EXAM#e1"


@pytest.mark.asyncio
async def test_get_exam_detail_computes_status_counts_from_student_items() -> None:
    client = AsyncMock()
    client.query = AsyncMock(
        return_value={
            "Items": [
                {
                    "PK": {"S": "EXAM#e1"},
                    "SK": {"S": "METADATA"},
                    "teacher_id": {"S": "t1"},
                    "title": {"S": "T"},
                    "status": {"S": "created"},
                },
                {
                    "PK": {"S": "EXAM#e1"},
                    "SK": {"S": "STUDENT#a"},
                    "nom": {"S": "A"},
                    "prenom": {"S": "B"},
                    "classe": {"S": "C"},
                    "submission_status": {"S": "PENDING"},
                },
                {
                    "PK": {"S": "EXAM#e1"},
                    "SK": {"S": "STUDENT#b"},
                    "nom": {"S": "A"},
                    "prenom": {"S": "B"},
                    "classe": {"S": "C"},
                    "submission_status": {"S": "PENDING"},
                },
                {
                    "PK": {"S": "EXAM#e1"},
                    "SK": {"S": "STUDENT#c"},
                    "nom": {"S": "A"},
                    "prenom": {"S": "B"},
                    "classe": {"S": "C"},
                    "submission_status": {"S": "CONVERTED"},
                },
            ],
            "LastEvaluatedKey": None,
        }
    )
    repo = DynamoDbExamDetailRepository(
        table_name="grading-table", dynamodb_client=client
    )

    detail = await repo.get_exam_detail(exam_id="e1")

    assert detail.status_counts.pending == 2


@pytest.mark.asyncio
async def test_get_exam_detail_raises_exam_not_found_when_metadata_missing() -> None:
    client = AsyncMock()
    client.query = AsyncMock(
        return_value={
            "Items": [
                {
                    "PK": {"S": "EXAM#e1"},
                    "SK": {"S": "STUDENT#a"},
                    "nom": {"S": "A"},
                    "prenom": {"S": "B"},
                    "classe": {"S": "C"},
                    "submission_status": {"S": "PENDING"},
                },
            ],
            "LastEvaluatedKey": None,
        }
    )
    repo = DynamoDbExamDetailRepository(
        table_name="grading-table", dynamodb_client=client
    )

    with pytest.raises(ExamNotFoundError):
        await repo.get_exam_detail(exam_id="e1")


@pytest.mark.asyncio
async def test_get_exam_detail_includes_pipeline_timestamps_when_present() -> None:
    client = AsyncMock()
    client.query = AsyncMock(
        return_value={
            "Items": [
                {
                    "PK": {"S": "EXAM#e1"},
                    "SK": {"S": "METADATA"},
                    "teacher_id": {"S": "t1"},
                    "title": {"S": "T"},
                    "status": {"S": "created"},
                    "pipeline_started_at": {"S": "2026-05-01T12:00:00Z"},
                    "pipeline_completed_at": {"S": "2026-05-01T13:00:00Z"},
                }
            ],
            "LastEvaluatedKey": None,
        }
    )
    repo = DynamoDbExamDetailRepository(
        table_name="grading-table", dynamodb_client=client
    )

    detail = await repo.get_exam_detail(exam_id="e1")

    assert detail.pipeline_started_at == "2026-05-01T12:00:00Z"
    assert detail.pipeline_completed_at == "2026-05-01T13:00:00Z"


@pytest.mark.asyncio
async def test_get_exam_detail_maps_resource_not_found_to_exam_not_found() -> None:
    err = ClientError(
        {"Error": {"Code": "ResourceNotFoundException", "Message": "no table"}},
        "Query",
    )
    client = AsyncMock()
    client.query = AsyncMock(side_effect=err)
    repo = DynamoDbExamDetailRepository(
        table_name="grading-table", dynamodb_client=client
    )

    with pytest.raises(ExamNotFoundError):
        await repo.get_exam_detail(exam_id="e1")


# --- DynamoDbExamDetailRepository.list_exam_student_statuses ---


@pytest.mark.asyncio
async def test_list_exam_student_statuses_queries_correct_pk_and_sk_prefix() -> None:
    client = AsyncMock()
    client.query = AsyncMock(return_value={"Items": [], "LastEvaluatedKey": None})
    repo = DynamoDbExamDetailRepository(
        table_name="grading-table", dynamodb_client=client
    )

    await repo.list_exam_student_statuses(exam_id="e1", limit=10, cursor=None)

    kwargs = client.query.await_args.kwargs
    assert kwargs["KeyConditionExpression"] == "PK = :pk AND begins_with(SK, :skp)"
    assert kwargs["ExpressionAttributeValues"][":pk"]["S"] == "EXAM#e1"
    assert kwargs["ExpressionAttributeValues"][":skp"]["S"] == "STUDENT#"


@pytest.mark.asyncio
async def test_list_exam_student_statuses_decodes_cursor_correctly() -> None:
    lek = {
        "PK": {"S": "EXAM#e1"},
        "SK": {"S": "STUDENT#s1"},
    }
    cursor = _encode_lek_local(lek)
    client = AsyncMock()
    client.query = AsyncMock(return_value={"Items": [], "LastEvaluatedKey": None})
    repo = DynamoDbExamDetailRepository(
        table_name="grading-table", dynamodb_client=client
    )

    await repo.list_exam_student_statuses(exam_id="e1", limit=5, cursor=cursor)

    kwargs = client.query.await_args.kwargs
    assert kwargs["ExclusiveStartKey"] == lek


@pytest.mark.asyncio
async def test_list_exam_student_statuses_raises_on_invalid_cursor() -> None:
    client = AsyncMock()
    repo = DynamoDbExamDetailRepository(
        table_name="grading-table", dynamodb_client=client
    )

    with pytest.raises(InvalidExamListCursorError):
        await repo.list_exam_student_statuses(
            exam_id="e1",
            limit=5,
            cursor="@@@@",
        )

    client.query.assert_not_called()


@pytest.mark.asyncio
async def test_list_exam_student_statuses_encodes_next_cursor() -> None:
    lek = {
        "PK": {"S": "EXAM#e1"},
        "SK": {"S": "STUDENT#s1"},
    }
    client = AsyncMock()
    client.query = AsyncMock(return_value={"Items": [], "LastEvaluatedKey": lek})
    repo = DynamoDbExamDetailRepository(
        table_name="grading-table", dynamodb_client=client
    )

    page = await repo.list_exam_student_statuses(exam_id="e1", limit=5, cursor=None)

    assert page.next_cursor == _encode_lek_local(lek)


@pytest.mark.asyncio
async def test_list_exam_student_statuses_pdf_available_flag() -> None:
    client = AsyncMock()
    client.query = AsyncMock(
        return_value={
            "Items": [
                {
                    "PK": {"S": "EXAM#e1"},
                    "SK": {"S": "STUDENT#s1"},
                    "nom": {"S": "D"},
                    "prenom": {"S": "J"},
                    "classe": {"S": "A"},
                    "submission_status": {"S": "PENDING"},
                    "pdf_available": {"BOOL": True},
                }
            ],
            "LastEvaluatedKey": None,
        }
    )
    repo = DynamoDbExamDetailRepository(
        table_name="grading-table", dynamodb_client=client
    )

    page = await repo.list_exam_student_statuses(exam_id="e1", limit=5, cursor=None)

    assert len(page.items) == 1
    assert page.items[0].pdf_available is True


# --- exam_router GET /exams/{exam_id} ---


@pytest.fixture
def exam_detail_api_client() -> TestClient:
    app = FastAPI()
    register_http_error_handlers(app)
    app.include_router(exam_router)

    creation = Mock()
    creation.create_exam = AsyncMock()
    creation.list_teacher_exams = AsyncMock(
        return_value=ExamPage(items=[], next_cursor=None),
    )
    app.state.exam_creation_repository = creation

    detail_repo = Mock(spec=ExamDetailRepositoryPort)
    detail_repo.get_exam_detail = AsyncMock(
        return_value=ExamDetail(
            exam_id="exam-99",
            teacher_id="teacher-1",
            title="Physics",
            status="created",
            description=None,
            subject="Phy",
            created_at="2026-05-01T12:00:00Z",
            pipeline_started_at=None,
            pipeline_completed_at=None,
            status_counts=StatusCounts(pending=1),
        ),
    )
    app.state.exam_detail_repository = detail_repo

    ownership = Mock(spec=ExamOwnershipPort)
    ownership.verify_teacher_owns_exam = AsyncMock()
    app.state.exam_ownership_repository = ownership

    jwt_verifier = create_autospec(JwtVerifierPort, instance=True)
    jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={
            "sub": "teacher-1",
            "custom:role": "teacher",
            "token_use": "id",
        },
    )
    app.state.jwt_verifier = jwt_verifier

    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def test_get_exam_detail_endpoint_returns_200(
    exam_detail_api_client: TestClient,
) -> None:
    response = exam_detail_api_client.get(
        "/exams/exam-99",
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["exam_id"] == "exam-99"
    assert body["title"] == "Physics"
    assert body["status"] == "created"
    assert body["subject"] == "Phy"
    assert body["created_at"] == "2026-05-01T12:00:00Z"
    assert body["status_counts"]["pending"] == 1


def test_get_exam_detail_endpoint_returns_404_when_not_found(
    exam_detail_api_client: TestClient,
) -> None:
    repo = exam_detail_api_client.app.state.exam_detail_repository
    repo.get_exam_detail = AsyncMock(side_effect=ExamNotFoundError("gone"))

    response = exam_detail_api_client.get(
        "/exams/exam-99",
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 404


def test_get_exam_detail_endpoint_requires_teacher_auth() -> None:
    app = FastAPI()
    register_http_error_handlers(app)
    app.include_router(exam_router)
    app.state.exam_creation_repository = Mock()
    app.state.exam_detail_repository = Mock(spec=ExamDetailRepositoryPort)
    app.state.exam_ownership_repository = Mock(spec=ExamOwnershipPort)
    app.state.jwt_verifier = create_autospec(JwtVerifierPort, instance=True)
    client = TestClient(app)

    response = client.get("/exams/e1")

    assert response.status_code == 401


def test_get_exam_detail_endpoint_returns_403_when_not_owner(
    exam_detail_api_client: TestClient,
) -> None:
    ownership = exam_detail_api_client.app.state.exam_ownership_repository
    ownership.verify_teacher_owns_exam = AsyncMock(
        side_effect=ExamOwnershipError("not yours"),
    )

    response = exam_detail_api_client.get(
        "/exams/exam-99",
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "exam_ownership"


# --- student_router GET /exams/{exam_id}/students ---


@pytest.fixture
def student_statuses_api_client() -> TestClient:
    app = FastAPI()
    register_http_error_handlers(app)
    app.include_router(student_router)

    enrollment = Mock()
    enrollment.add_students = AsyncMock(side_effect=lambda **kwargs: kwargs["students"])
    app.state.student_enrollment_repository = enrollment

    detail_repo = Mock(spec=ExamDetailRepositoryPort)
    detail_repo.list_exam_student_statuses = AsyncMock(
        return_value=StudentPipelinePage(items=[], next_cursor=None),
    )
    app.state.exam_detail_repository = detail_repo

    ownership = Mock(spec=ExamOwnershipPort)
    ownership.verify_teacher_owns_exam = AsyncMock()
    app.state.exam_ownership_repository = ownership

    jwt_verifier = create_autospec(JwtVerifierPort, instance=True)
    jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={
            "sub": "teacher-1",
            "custom:role": "teacher",
            "token_use": "id",
        },
    )
    app.state.jwt_verifier = jwt_verifier

    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def test_list_student_statuses_endpoint_returns_200_with_pdf_flag(
    student_statuses_api_client: TestClient,
) -> None:
    repo = student_statuses_api_client.app.state.exam_detail_repository
    repo.list_exam_student_statuses = AsyncMock(
        return_value=StudentPipelinePage(
            items=[
                StudentPipelineStatus(
                    student_id="s1",
                    nom="D",
                    prenom="P",
                    classe="C",
                    submission_status="PENDING",
                    pdf_available=True,
                )
            ],
            next_cursor=None,
        ),
    )

    response = student_statuses_api_client.get(
        "/exams/exam-99/students",
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 200
    data = response.json()["items"][0]
    assert data["pdf_available"] is True
    assert data["student_id"] == "s1"


def test_list_student_statuses_endpoint_requires_teacher_auth() -> None:
    app = FastAPI()
    register_http_error_handlers(app)
    app.include_router(student_router)
    app.state.student_enrollment_repository = Mock()
    app.state.exam_detail_repository = Mock(spec=ExamDetailRepositoryPort)
    app.state.exam_ownership_repository = Mock(spec=ExamOwnershipPort)
    app.state.jwt_verifier = create_autospec(JwtVerifierPort, instance=True)
    client = TestClient(app)

    response = client.get("/exams/e1/students")

    assert response.status_code == 401


def test_list_student_statuses_endpoint_bad_cursor_returns_422(
    student_statuses_api_client: TestClient,
) -> None:
    repo = student_statuses_api_client.app.state.exam_detail_repository
    repo.list_exam_student_statuses = AsyncMock(
        side_effect=InvalidExamListCursorError("Invalid pagination cursor."),
    )

    response = student_statuses_api_client.get(
        "/exams/exam-99/students?cursor=x",
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 422


def test_list_student_statuses_endpoint_pagination_params_forwarded(
    student_statuses_api_client: TestClient,
) -> None:
    repo = student_statuses_api_client.app.state.exam_detail_repository

    response = student_statuses_api_client.get(
        "/exams/exam-99/students?limit=5&cursor=abc",
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 200
    repo.list_exam_student_statuses.assert_awaited_once()
    kwargs = repo.list_exam_student_statuses.await_args.kwargs
    assert kwargs["limit"] == 5
    assert kwargs["cursor"] == "abc"
