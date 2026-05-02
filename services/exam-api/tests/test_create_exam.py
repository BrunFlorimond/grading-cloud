"""Tests for issue #13 — teacher creates and lists exams."""

from __future__ import annotations

import base64
import json
import uuid
from unittest.mock import AsyncMock, Mock, create_autospec

import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from grading_shared.domain.exam import Exam, ExamStatus

from exam_api.api.exam_router import router as exam_router
from exam_api.api.http_error_handlers import register_http_error_handlers
from exam_api.application.create_exam import CreateExamCommand, CreateExamUseCase
from exam_api.application.list_teacher_exams import (
    ListTeacherExamsCommand,
    ListTeacherExamsUseCase,
)
from exam_api.domain.errors import (
    ExamCreationConflictError,
    ExamTitleRequiredError,
    ExamTitleTooLongError,
    InvalidExamListCursorError,
)
from exam_api.infrastructure.dynamodb_exam_creation_repository import DynamoDbExamCreationRepository
from exam_api.ports.exam_creation_repository_port import ExamPage
from exam_api.ports.jwt_verifier_port import JwtVerifierPort


def _uuid4(value: str) -> bool:
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return False
    return parsed.version == 4


# --- CreateExamUseCase ---


@pytest.mark.asyncio
async def test_create_exam_returns_uuid_v4() -> None:
    repo = Mock()
    repo.create_exam = AsyncMock()
    use_case = CreateExamUseCase(exam_repository=repo)

    result = await use_case.execute(
        CreateExamCommand(teacher_id="t1", title="Algebra")
    )

    assert _uuid4(result.exam_id)


@pytest.mark.asyncio
async def test_create_exam_returns_status_created() -> None:
    repo = Mock()
    repo.create_exam = AsyncMock()
    use_case = CreateExamUseCase(exam_repository=repo)

    result = await use_case.execute(
        CreateExamCommand(teacher_id="t1", title="Algebra")
    )

    assert result.status == "CREATED"


@pytest.mark.asyncio
async def test_create_exam_persists_exam_with_repository() -> None:
    repo = Mock()
    repo.create_exam = AsyncMock()
    use_case = CreateExamUseCase(exam_repository=repo)

    await use_case.execute(
        CreateExamCommand(
            teacher_id="teacher-99",
            title="Midterm",
            description="Chapitre 1",
            subject="Math",
        )
    )

    repo.create_exam.assert_awaited_once()
    passed = repo.create_exam.await_args.args[0]
    assert isinstance(passed, Exam)
    assert passed.teacher_id == "teacher-99"
    assert passed.title == "Midterm"
    assert passed.description == "Chapitre 1"
    assert passed.subject == "Math"
    assert passed.status == ExamStatus.CREATED
    assert passed.created_at is not None


@pytest.mark.asyncio
async def test_create_exam_with_empty_title_raises_error() -> None:
    repo = Mock()
    repo.create_exam = AsyncMock()
    use_case = CreateExamUseCase(exam_repository=repo)

    with pytest.raises(ExamTitleRequiredError):
        await use_case.execute(CreateExamCommand(teacher_id="t1", title="   "))


@pytest.mark.asyncio
async def test_create_exam_with_title_over_120_chars_raises_error() -> None:
    repo = Mock()
    repo.create_exam = AsyncMock()
    use_case = CreateExamUseCase(exam_repository=repo)

    with pytest.raises(ExamTitleTooLongError):
        await use_case.execute(
            CreateExamCommand(teacher_id="t1", title="x" * 121)
        )


@pytest.mark.asyncio
async def test_create_exam_sets_teacher_id_from_command() -> None:
    repo = Mock()
    repo.create_exam = AsyncMock()
    use_case = CreateExamUseCase(exam_repository=repo)

    await use_case.execute(CreateExamCommand(teacher_id="tid-42", title="Exam"))

    exam = repo.create_exam.await_args.args[0]
    assert exam.teacher_id == "tid-42"


# --- ListTeacherExamsUseCase ---


@pytest.mark.asyncio
async def test_list_exams_delegates_to_repository() -> None:
    repo = Mock()
    repo.list_teacher_exams = AsyncMock(
        return_value=ExamPage(items=[], next_cursor=None)
    )
    use_case = ListTeacherExamsUseCase(exam_repository=repo)

    await use_case.execute(
        ListTeacherExamsCommand(teacher_id="t1", limit=10, cursor="abc")
    )

    repo.list_teacher_exams.assert_awaited_once_with(
        teacher_id="t1", limit=10, cursor="abc"
    )


@pytest.mark.asyncio
async def test_list_exams_returns_page_from_repository() -> None:
    page = ExamPage(
        items=[
            Exam(
                exam_id="e1",
                teacher_id="t1",
                title="A",
                status=ExamStatus.CREATED,
                created_at="2026-05-01T12:00:00.000000Z",
            )
        ],
        next_cursor="next",
    )
    repo = Mock()
    repo.list_teacher_exams = AsyncMock(return_value=page)
    use_case = ListTeacherExamsUseCase(exam_repository=repo)

    result = await use_case.execute(
        ListTeacherExamsCommand(teacher_id="t1", limit=20, cursor=None)
    )

    assert result is page


# --- exam_router (TestClient) ---


@pytest.fixture
def exam_api_client() -> TestClient:
    app = FastAPI()
    register_http_error_handlers(app)
    app.include_router(exam_router)
    repo = Mock()
    repo.create_exam = AsyncMock()
    repo.list_teacher_exams = AsyncMock(
        return_value=ExamPage(items=[], next_cursor=None)
    )
    app.state.exam_creation_repository = repo
    jwt_verifier = create_autospec(JwtVerifierPort, instance=True)
    jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={
            "sub": "teacher-1",
            "custom:role": "teacher",
            "token_use": "id",
        }
    )
    app.state.jwt_verifier = jwt_verifier
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def test_post_exams_requires_auth() -> None:
    app = FastAPI()
    register_http_error_handlers(app)
    app.include_router(exam_router)
    app.state.exam_creation_repository = Mock()
    app.state.jwt_verifier = create_autospec(JwtVerifierPort, instance=True)
    client = TestClient(app)

    response = client.post("/exams", json={"title": "Exam"})

    assert response.status_code == 401


def test_post_exams_returns_201_with_exam_id_and_status(exam_api_client: TestClient) -> None:
    response = exam_api_client.post(
        "/exams",
        json={"title": "Final", "description": None, "subject": "Physics"},
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 201
    data = response.json()
    assert _uuid4(data["exam_id"])
    assert data["status"] == "CREATED"


def test_post_exams_missing_title_returns_422(exam_api_client: TestClient) -> None:
    response = exam_api_client.post(
        "/exams",
        json={"description": "x"},
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 422


def test_post_exams_title_too_long_returns_422(exam_api_client: TestClient) -> None:
    response = exam_api_client.post(
        "/exams",
        json={"title": "x" * 121},
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 422


def test_post_exams_whitespace_only_title_returns_422(exam_api_client: TestClient) -> None:
    response = exam_api_client.post(
        "/exams",
        json={"title": "   "},
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 422


def test_get_exams_requires_auth() -> None:
    app = FastAPI()
    register_http_error_handlers(app)
    app.include_router(exam_router)
    app.state.exam_creation_repository = Mock()
    app.state.jwt_verifier = create_autospec(JwtVerifierPort, instance=True)
    client = TestClient(app)

    response = client.get("/exams")

    assert response.status_code == 401


def test_get_exams_returns_pipeline_status_as_enum_value_not_member_name(
    exam_api_client: TestClient,
) -> None:
    """Regression: list uses StrEnum .value (e.g. ready) except CREATED/CONFIGURED labels."""
    repo = exam_api_client.app.state.exam_creation_repository
    repo.list_teacher_exams = AsyncMock(
        return_value=ExamPage(
            items=[
                Exam(
                    exam_id="e-ready",
                    teacher_id="teacher-1",
                    title="R",
                    status=ExamStatus.READY,
                    created_at="2026-05-01T12:00:00.000000Z",
                ),
                Exam(
                    exam_id="e-draft",
                    teacher_id="teacher-1",
                    title="D",
                    status=ExamStatus.DRAFT,
                    created_at="2026-05-01T12:00:00.000000Z",
                ),
            ],
            next_cursor=None,
        )
    )

    response = exam_api_client.get("/exams", headers={"Authorization": "Bearer fake"})

    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["status"] == "ready"
    assert items[1]["status"] == "draft"


def test_get_exams_returns_paginated_list(exam_api_client: TestClient) -> None:
    repo = exam_api_client.app.state.exam_creation_repository
    repo.list_teacher_exams = AsyncMock(
        return_value=ExamPage(
            items=[
                Exam(
                    exam_id="e1",
                    teacher_id="teacher-1",
                    title="T",
                    status=ExamStatus.CREATED,
                    created_at="2026-05-01T12:00:00.000000Z",
                )
            ],
            next_cursor=None,
        )
    )

    response = exam_api_client.get("/exams", headers={"Authorization": "Bearer fake"})

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [
        {"exam_id": "e1", "title": "T", "status": "CREATED"}
    ]
    assert body["next_cursor"] is None


def test_get_exams_invalid_cursor_returns_422(exam_api_client: TestClient) -> None:
    repo = exam_api_client.app.state.exam_creation_repository
    repo.list_teacher_exams = AsyncMock(
        side_effect=InvalidExamListCursorError("Invalid pagination cursor.")
    )

    response = exam_api_client.get(
        "/exams?cursor=garbage",
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 422


# --- DynamoDbExamCreationRepository ---


@pytest.mark.asyncio
async def test_create_exam_writes_metadata_item() -> None:
    client = AsyncMock()
    client.transact_write_items = AsyncMock()
    repo = DynamoDbExamCreationRepository(
        table_name="grading-table",
        dynamodb_client=client,
    )
    exam = Exam(
        exam_id="550e8400-e29b-41d4-a716-446655440000",
        teacher_id="teacher-1",
        title="Midterm",
        status=ExamStatus.CREATED,
        created_at="2026-05-01T12:00:00.000000Z",
    )

    await repo.create_exam(exam)

    puts = client.transact_write_items.call_args.kwargs["TransactItems"]
    assert len(puts) == 3
    meta = puts[0]["Put"]["Item"]
    assert meta["PK"]["S"] == "EXAM#550e8400-e29b-41d4-a716-446655440000"
    assert meta["SK"]["S"] == "METADATA"


@pytest.mark.asyncio
async def test_create_exam_writes_teacher_ownership_edge() -> None:
    client = AsyncMock()
    client.transact_write_items = AsyncMock()
    repo = DynamoDbExamCreationRepository(
        table_name="grading-table",
        dynamodb_client=client,
    )
    exam = Exam(
        exam_id="550e8400-e29b-41d4-a716-446655440000",
        teacher_id="teacher-1",
        title="Midterm",
        status=ExamStatus.CREATED,
        created_at="2026-05-01T12:00:00.000000Z",
    )

    await repo.create_exam(exam)

    puts = client.transact_write_items.call_args.kwargs["TransactItems"]
    ownership = puts[1]["Put"]["Item"]
    assert ownership["PK"]["S"] == "TEACHER#teacher-1"
    assert ownership["SK"]["S"] == "EXAM#550e8400-e29b-41d4-a716-446655440000"


@pytest.mark.asyncio
async def test_list_teacher_exams_returns_only_own_exams() -> None:
    client = AsyncMock()

    async def _query(**kwargs: object) -> dict[str, object]:
        pk = kwargs["ExpressionAttributeValues"][":pk"]["S"]
        assert pk == "TEACHER#teacher-1"
        return {"Items": [], "LastEvaluatedKey": None}

    client.query = AsyncMock(side_effect=_query)
    repo = DynamoDbExamCreationRepository(
        table_name="grading-table",
        dynamodb_client=client,
    )

    await repo.list_teacher_exams(teacher_id="teacher-1", limit=5, cursor=None)

    client.query.assert_awaited()


@pytest.mark.asyncio
async def test_list_teacher_exams_ordered_by_created_at_desc() -> None:
    client = AsyncMock()
    client.query = AsyncMock(return_value={"Items": [], "LastEvaluatedKey": None})
    repo = DynamoDbExamCreationRepository(
        table_name="grading-table",
        dynamodb_client=client,
    )

    await repo.list_teacher_exams(teacher_id="teacher-1", limit=5, cursor=None)

    kwargs = client.query.await_args.kwargs
    assert kwargs["ScanIndexForward"] is False


@pytest.mark.asyncio
async def test_list_teacher_exams_cursor_pagination() -> None:
    lek = {
        "PK": {"S": "TEACHER#t1"},
        "SK": {"S": "TS#2026-05-01T12:00:00.000000Z#e1"},
    }

    client = AsyncMock()
    client.query = AsyncMock(
        side_effect=[
            {"Items": [], "LastEvaluatedKey": lek},
            {"Items": [], "LastEvaluatedKey": None},
        ]
    )
    repo = DynamoDbExamCreationRepository(
        table_name="grading-table",
        dynamodb_client=client,
    )

    page1 = await repo.list_teacher_exams(teacher_id="t1", limit=1, cursor=None)
    assert page1.next_cursor is not None

    await repo.list_teacher_exams(teacher_id="t1", limit=1, cursor=page1.next_cursor)

    second_call = client.query.await_args_list[1].kwargs
    assert second_call["ExclusiveStartKey"] == lek


@pytest.mark.asyncio
async def test_create_exam_transaction_conditional_failure_raises_conflict() -> None:
    client = AsyncMock()
    client.transact_write_items = AsyncMock(
        side_effect=ClientError(
            {
                "Error": {"Code": "TransactionCanceledException", "Message": "tx"},
                "CancellationReasons": [{"Code": "ConditionalCheckFailed"}],
            },
            "TransactWriteItems",
        )
    )
    repo = DynamoDbExamCreationRepository(
        table_name="grading-table",
        dynamodb_client=client,
    )
    exam = Exam(
        exam_id="550e8400-e29b-41d4-a716-446655440000",
        teacher_id="teacher-1",
        title="Midterm",
        status=ExamStatus.CREATED,
        created_at="2026-05-01T12:00:00.000000Z",
    )

    with pytest.raises(ExamCreationConflictError):
        await repo.create_exam(exam)


@pytest.mark.asyncio
async def test_list_teacher_exams_query_error_maps_to_invalid_cursor() -> None:
    client = AsyncMock()
    client.query = AsyncMock(
        side_effect=ClientError(
            {"Error": {"Code": "ValidationException", "Message": "bad key"}},
            "Query",
        )
    )
    repo = DynamoDbExamCreationRepository(
        table_name="grading-table",
        dynamodb_client=client,
    )

    with pytest.raises(InvalidExamListCursorError):
        await repo.list_teacher_exams(teacher_id="t1", limit=5, cursor=None)


@pytest.mark.asyncio
async def test_list_teacher_exams_invalid_cursor_shape_raises() -> None:
    repo = DynamoDbExamCreationRepository(
        table_name="grading-table",
        dynamodb_client=AsyncMock(),
    )
    raw = base64.urlsafe_b64encode(json.dumps({"PK": "not-a-map"}).encode()).decode(
        "ascii"
    ).rstrip("=")

    with pytest.raises(InvalidExamListCursorError):
        await repo.list_teacher_exams(teacher_id="t1", limit=5, cursor=raw)
