"""Tests for issue #15 — teacher adds students to an exam."""

from __future__ import annotations

import base64
import json
import uuid
from unittest.mock import AsyncMock, Mock, create_autospec

import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from exam_api.api.http_error_handlers import register_http_error_handlers
from exam_api.api.student_router import router as student_router
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
    ExamNotFoundError,
    ExamOwnershipError,
    StudentBatchTooLargeError,
)
from exam_api.domain.student import EnrolledStudent, SubmissionStatus
from exam_api.infrastructure.dynamodb_student_enrollment_repository import (
    DynamoDbStudentEnrollmentRepository,
)
from exam_api.ports.exam_ownership_port import ExamOwnershipPort
from exam_api.ports.jwt_verifier_port import JwtVerifierPort
from exam_api.ports.student_enrollment_repository_port import (
    EnrolledStudentPage,
    StudentEnrollmentRepositoryPort,
)


def _uuid4_string(value: str) -> bool:
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return False
    return parsed.version == 4


# --- AddStudentsUseCase ---


@pytest.mark.asyncio
async def test_add_students_returns_created_list() -> None:
    enrollment = Mock(spec=StudentEnrollmentRepositoryPort)
    ownership = Mock(spec=ExamOwnershipPort)
    ownership.verify_teacher_owns_exam = AsyncMock()
    created = [
        EnrolledStudent(
            student_id="s1",
            exam_id="e1",
            nom="Doe",
            prenom="Jane",
            classe="A",
            submission_status=SubmissionStatus.PENDING,
        ),
        EnrolledStudent(
            student_id="s2",
            exam_id="e1",
            nom="Roe",
            prenom="John",
            classe="B",
            submission_status=SubmissionStatus.PENDING,
        ),
    ]
    enrollment.add_students = AsyncMock(return_value=created)

    use_case = AddStudentsUseCase(
        enrollment_repository=enrollment,
        exam_ownership_port=ownership,
    )
    result = await use_case.execute(
        AddStudentsCommand(
            exam_id="e1",
            teacher_id="t1",
            students=[
                StudentInput(
                    student_id="s1",
                    nom="Doe",
                    prenom="Jane",
                    classe="A",
                ),
                StudentInput(
                    student_id="s2",
                    nom="Roe",
                    prenom="John",
                    classe="B",
                ),
            ],
        )
    )

    assert len(result.created) == 2
    assert result.created[0].student_id == "s1"
    assert result.created[1].student_id == "s2"


@pytest.mark.asyncio
async def test_add_students_assigns_uuid_when_student_id_absent() -> None:
    enrollment = Mock(spec=StudentEnrollmentRepositoryPort)
    ownership = Mock(spec=ExamOwnershipPort)
    ownership.verify_teacher_owns_exam = AsyncMock()

    async def _capture(**kwargs: object) -> list[EnrolledStudent]:
        students = kwargs["students"]
        assert isinstance(students, list) and len(students) == 1
        return students

    enrollment.add_students = AsyncMock(side_effect=_capture)

    use_case = AddStudentsUseCase(
        enrollment_repository=enrollment,
        exam_ownership_port=ownership,
    )
    result = await use_case.execute(
        AddStudentsCommand(
            exam_id="e1",
            teacher_id="t1",
            students=[
                StudentInput(
                    nom="Doe",
                    prenom="Jane",
                    classe="A",
                )
            ],
        )
    )

    assert _uuid4_string(result.created[0].student_id)


@pytest.mark.asyncio
async def test_add_students_keeps_provided_student_id() -> None:
    enrollment = Mock(spec=StudentEnrollmentRepositoryPort)
    ownership = Mock(spec=ExamOwnershipPort)
    ownership.verify_teacher_owns_exam = AsyncMock()
    enrollment.add_students = AsyncMock(
        side_effect=lambda **kwargs: kwargs["students"]
    )

    use_case = AddStudentsUseCase(
        enrollment_repository=enrollment,
        exam_ownership_port=ownership,
    )
    result = await use_case.execute(
        AddStudentsCommand(
            exam_id="e1",
            teacher_id="t1",
            students=[
                StudentInput(
                    student_id="EL-001",
                    nom="Doe",
                    prenom="Jane",
                    classe="A",
                )
            ],
        )
    )

    assert result.created[0].student_id == "EL-001"


@pytest.mark.asyncio
async def test_add_students_sets_submission_status_pending() -> None:
    enrollment = Mock(spec=StudentEnrollmentRepositoryPort)
    ownership = Mock(spec=ExamOwnershipPort)
    ownership.verify_teacher_owns_exam = AsyncMock()
    enrollment.add_students = AsyncMock(
        side_effect=lambda **kwargs: kwargs["students"]
    )

    use_case = AddStudentsUseCase(
        enrollment_repository=enrollment,
        exam_ownership_port=ownership,
    )
    result = await use_case.execute(
        AddStudentsCommand(
            exam_id="e1",
            teacher_id="t1",
            students=[
                StudentInput(
                    student_id="s1",
                    nom="Doe",
                    prenom="Jane",
                    classe="A",
                )
            ],
        )
    )

    assert result.created[0].submission_status == SubmissionStatus.PENDING


@pytest.mark.asyncio
async def test_add_students_raises_when_batch_exceeds_50() -> None:
    enrollment = Mock(spec=StudentEnrollmentRepositoryPort)
    ownership = Mock(spec=ExamOwnershipPort)
    use_case = AddStudentsUseCase(
        enrollment_repository=enrollment,
        exam_ownership_port=ownership,
    )

    with pytest.raises(StudentBatchTooLargeError):
        await use_case.execute(
            AddStudentsCommand(
                exam_id="e1",
                teacher_id="t1",
                students=[
                    StudentInput(
                        student_id=f"id-{i}",
                        nom="N",
                        prenom="P",
                        classe="C",
                    )
                    for i in range(51)
                ],
            )
        )


@pytest.mark.asyncio
async def test_add_students_raises_on_duplicate_student_id_from_repository() -> None:
    enrollment = Mock(spec=StudentEnrollmentRepositoryPort)
    ownership = Mock(spec=ExamOwnershipPort)
    ownership.verify_teacher_owns_exam = AsyncMock()
    enrollment.add_students = AsyncMock(
        side_effect=DuplicateStudentError("s1", "e1"),
    )

    use_case = AddStudentsUseCase(
        enrollment_repository=enrollment,
        exam_ownership_port=ownership,
    )

    with pytest.raises(DuplicateStudentError):
        await use_case.execute(
            AddStudentsCommand(
                exam_id="e1",
                teacher_id="t1",
                students=[
                    StudentInput(
                        student_id="s1",
                        nom="Doe",
                        prenom="Jane",
                        classe="A",
                    )
                ],
            )
        )


@pytest.mark.asyncio
async def test_add_students_raises_on_duplicate_student_id_in_request() -> None:
    enrollment = Mock(spec=StudentEnrollmentRepositoryPort)
    ownership = Mock(spec=ExamOwnershipPort)
    ownership.verify_teacher_owns_exam = AsyncMock()

    use_case = AddStudentsUseCase(
        enrollment_repository=enrollment,
        exam_ownership_port=ownership,
    )

    with pytest.raises(DuplicateStudentError):
        await use_case.execute(
            AddStudentsCommand(
                exam_id="e1",
                teacher_id="t1",
                students=[
                    StudentInput(
                        student_id="dup",
                        nom="A",
                        prenom="B",
                        classe="C",
                    ),
                    StudentInput(
                        student_id="dup",
                        nom="X",
                        prenom="Y",
                        classe="Z",
                    ),
                ],
            )
        )


@pytest.mark.asyncio
async def test_add_students_raises_on_exam_not_found() -> None:
    enrollment = Mock(spec=StudentEnrollmentRepositoryPort)
    ownership = Mock(spec=ExamOwnershipPort)
    ownership.verify_teacher_owns_exam = AsyncMock(
        side_effect=ExamNotFoundError("missing"),
    )

    use_case = AddStudentsUseCase(
        enrollment_repository=enrollment,
        exam_ownership_port=ownership,
    )

    with pytest.raises(EnrollmentExamNotFoundError):
        await use_case.execute(
            AddStudentsCommand(
                exam_id="e1",
                teacher_id="t1",
                students=[
                    StudentInput(
                        student_id="s1",
                        nom="Doe",
                        prenom="Jane",
                        classe="A",
                    )
                ],
            )
        )


@pytest.mark.asyncio
async def test_add_students_raises_on_wrong_owner() -> None:
    enrollment = Mock(spec=StudentEnrollmentRepositoryPort)
    ownership = Mock(spec=ExamOwnershipPort)
    ownership.verify_teacher_owns_exam = AsyncMock(
        side_effect=ExamOwnershipError("no"),
    )

    use_case = AddStudentsUseCase(
        enrollment_repository=enrollment,
        exam_ownership_port=ownership,
    )

    with pytest.raises(EnrollmentExamOwnershipError):
        await use_case.execute(
            AddStudentsCommand(
                exam_id="e1",
                teacher_id="t1",
                students=[
                    StudentInput(
                        student_id="s1",
                        nom="Doe",
                        prenom="Jane",
                        classe="A",
                    )
                ],
            )
        )


# --- ListExamStudentsUseCase ---


@pytest.mark.asyncio
async def test_list_exam_students_delegates_to_repository() -> None:
    page = EnrolledStudentPage(items=[], next_cursor=None)
    enrollment = Mock(spec=StudentEnrollmentRepositoryPort)
    enrollment.list_exam_students = AsyncMock(return_value=page)

    use_case = ListExamStudentsUseCase(enrollment_repository=enrollment)
    await use_case.execute(
        ListExamStudentsCommand(
            exam_id="e1",
            teacher_id="t1",
            limit=20,
            cursor="cur",
        )
    )

    enrollment.list_exam_students.assert_awaited_once_with(
        exam_id="e1",
        limit=20,
        cursor="cur",
    )


@pytest.mark.asyncio
async def test_list_exam_students_returns_page_from_repository() -> None:
    page = EnrolledStudentPage(items=[], next_cursor="next")
    enrollment = Mock(spec=StudentEnrollmentRepositoryPort)
    enrollment.list_exam_students = AsyncMock(return_value=page)

    use_case = ListExamStudentsUseCase(enrollment_repository=enrollment)
    result = await use_case.execute(
        ListExamStudentsCommand(
            exam_id="e1",
            teacher_id="t1",
            limit=20,
            cursor=None,
        )
    )

    assert result is page


# --- student_router (TestClient) ---


@pytest.fixture
def students_api_client() -> TestClient:
    app = FastAPI()
    register_http_error_handlers(app)
    app.include_router(student_router)

    enrollment = Mock(spec=StudentEnrollmentRepositoryPort)
    enrollment.add_students = AsyncMock(
        side_effect=lambda **kwargs: kwargs["students"]
    )
    enrollment.list_exam_students = AsyncMock(
        return_value=EnrolledStudentPage(items=[], next_cursor=None)
    )
    app.state.student_enrollment_repository = enrollment

    ownership = Mock(spec=ExamOwnershipPort)
    ownership.verify_teacher_owns_exam = AsyncMock()
    app.state.exam_ownership_repository = ownership

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


def test_post_students_requires_auth() -> None:
    app = FastAPI()
    register_http_error_handlers(app)
    app.include_router(student_router)
    app.state.student_enrollment_repository = Mock(spec=StudentEnrollmentRepositoryPort)
    app.state.exam_ownership_repository = Mock(spec=ExamOwnershipPort)
    app.state.jwt_verifier = create_autospec(JwtVerifierPort, instance=True)
    client = TestClient(app)

    response = client.post("/exams/e1/students", json=[])

    assert response.status_code == 401


def test_post_students_returns_201_with_created_list(
    students_api_client: TestClient,
) -> None:
    response = students_api_client.post(
        "/exams/exam-99/students",
        json=[
            {
                "student_id": "s1",
                "nom": "Doe",
                "prenom": "Jane",
                "classe": "A",
                "email": None,
            },
            {
                "nom": "Roe",
                "prenom": "John",
                "classe": "B",
                "email": None,
            },
        ],
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 201
    data = response.json()["created"]
    assert len(data) == 2
    assert data[0]["student_id"] == "s1"
    assert data[0]["submission_status"] == "PENDING"
    assert _uuid4_string(data[1]["student_id"])


def test_post_students_empty_body_returns_422(students_api_client: TestClient) -> None:
    response = students_api_client.post(
        "/exams/exam-99/students",
        json=[],
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 422


def test_post_students_batch_over_50_returns_422(students_api_client: TestClient) -> None:
    body = [
        {
            "student_id": f"s{i}",
            "nom": "N",
            "prenom": "P",
            "classe": "C",
        }
        for i in range(51)
    ]
    response = students_api_client.post(
        "/exams/exam-99/students",
        json=body,
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 422


def test_post_students_duplicate_student_id_returns_409(
    students_api_client: TestClient,
) -> None:
    enrollment = students_api_client.app.state.student_enrollment_repository
    enrollment.add_students = AsyncMock(
        side_effect=DuplicateStudentError("s1", "exam-99"),
    )

    response = students_api_client.post(
        "/exams/exam-99/students",
        json=[
            {
                "student_id": "s1",
                "nom": "Doe",
                "prenom": "Jane",
                "classe": "A",
            }
        ],
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 409


def test_post_students_exam_not_found_returns_404(students_api_client: TestClient) -> None:
    ownership = students_api_client.app.state.exam_ownership_repository
    ownership.verify_teacher_owns_exam = AsyncMock(
        side_effect=ExamNotFoundError("Exam missing."),
    )

    response = students_api_client.post(
        "/exams/exam-99/students",
        json=[
            {
                "student_id": "s1",
                "nom": "Doe",
                "prenom": "Jane",
                "classe": "A",
            }
        ],
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 404


def test_get_students_requires_auth() -> None:
    app = FastAPI()
    register_http_error_handlers(app)
    app.include_router(student_router)
    app.state.student_enrollment_repository = Mock(spec=StudentEnrollmentRepositoryPort)
    app.state.exam_ownership_repository = Mock(spec=ExamOwnershipPort)
    app.state.jwt_verifier = create_autospec(JwtVerifierPort, instance=True)
    client = TestClient(app)

    response = client.get("/exams/e1/students")

    assert response.status_code == 401


def test_get_students_returns_paginated_list(students_api_client: TestClient) -> None:
    enrollment = students_api_client.app.state.student_enrollment_repository
    enrollment.list_exam_students = AsyncMock(
        return_value=EnrolledStudentPage(
            items=[
                EnrolledStudent(
                    student_id="s1",
                    exam_id="exam-99",
                    nom="D",
                    prenom="P",
                    classe="C",
                    submission_status=SubmissionStatus.PENDING,
                )
            ],
            next_cursor="next-page",
        )
    )

    response = students_api_client.get(
        "/exams/exam-99/students",
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["student_id"] == "s1"
    assert body["next_cursor"] == "next-page"


def test_get_students_passes_limit_and_cursor_to_use_case(
    students_api_client: TestClient,
) -> None:
    enrollment = students_api_client.app.state.student_enrollment_repository

    response = students_api_client.get(
        "/exams/exam-99/students?limit=5&cursor=abc",
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 200
    enrollment.list_exam_students.assert_awaited()
    kwargs = enrollment.list_exam_students.await_args.kwargs
    assert kwargs["limit"] == 5
    assert kwargs["cursor"] == "abc"


# --- DynamoDbStudentEnrollmentRepository ---


@pytest.mark.asyncio
async def test_add_students_writes_correct_pk_sk() -> None:
    client = AsyncMock()
    client.transact_write_items = AsyncMock()
    repo = DynamoDbStudentEnrollmentRepository(
        table_name="grading-table",
        dynamodb_client=client,
    )
    students = [
        EnrolledStudent(
            student_id="stu-1",
            exam_id="e1",
            nom="N",
            prenom="P",
            classe="C",
            submission_status=SubmissionStatus.PENDING,
        )
    ]

    await repo.add_students(exam_id="e1", students=students)

    items = client.transact_write_items.await_args.kwargs["TransactItems"]
    assert len(items) == 1
    item = items[0]["Put"]["Item"]
    assert item["PK"]["S"] == "EXAM#e1"
    assert item["SK"]["S"] == "STUDENT#stu-1"


@pytest.mark.asyncio
async def test_add_students_stores_all_fields() -> None:
    client = AsyncMock()
    client.transact_write_items = AsyncMock()
    repo = DynamoDbStudentEnrollmentRepository(
        table_name="grading-table",
        dynamodb_client=client,
    )
    students = [
        EnrolledStudent(
            student_id="stu-1",
            exam_id="e1",
            nom="Nom",
            prenom="Prenom",
            classe="Cl",
            email="a@b.co",
            submission_status=SubmissionStatus.PENDING,
        )
    ]

    await repo.add_students(exam_id="e1", students=students)

    item = client.transact_write_items.await_args.kwargs["TransactItems"][0]["Put"][
        "Item"
    ]
    assert item["nom"]["S"] == "Nom"
    assert item["prenom"]["S"] == "Prenom"
    assert item["classe"]["S"] == "Cl"
    assert item["email"]["S"] == "a@b.co"
    assert item["submission_status"]["S"] == "PENDING"


@pytest.mark.asyncio
async def test_add_students_conditional_failure_raises_duplicate_error() -> None:
    error_response = {
        "Error": {
            "Code": "TransactionCanceledException",
            "Message": "Transaction cancelled",
        },
        "CancellationReasons": [
            {
                "Code": "ConditionalCheckFailed",
                "Message": "The conditional request failed",
            }
        ],
    }
    err = ClientError(error_response, "TransactWriteItems")

    client = AsyncMock()
    client.transact_write_items = AsyncMock(side_effect=err)
    repo = DynamoDbStudentEnrollmentRepository(
        table_name="grading-table",
        dynamodb_client=client,
    )
    students = [
        EnrolledStudent(
            student_id="x",
            exam_id="e1",
            nom="N",
            prenom="P",
            classe="C",
            submission_status=SubmissionStatus.PENDING,
        )
    ]

    with pytest.raises(DuplicateStudentError):
        await repo.add_students(exam_id="e1", students=students)


@pytest.mark.asyncio
async def test_list_exam_students_queries_correct_pk_prefix() -> None:
    client = AsyncMock()
    client.query = AsyncMock(return_value={"Items": [], "LastEvaluatedKey": None})
    repo = DynamoDbStudentEnrollmentRepository(
        table_name="grading-table",
        dynamodb_client=client,
    )

    await repo.list_exam_students(exam_id="e1", limit=10, cursor=None)

    kwargs = client.query.await_args.kwargs
    assert kwargs["KeyConditionExpression"] == "PK = :pk AND begins_with(SK, :skp)"
    assert kwargs["ExpressionAttributeValues"][":pk"]["S"] == "EXAM#e1"
    assert kwargs["ExpressionAttributeValues"][":skp"]["S"] == "STUDENT#"


@pytest.mark.asyncio
async def test_list_exam_students_cursor_pagination() -> None:
    lek = {
        "PK": {"S": "EXAM#e1"},
        "SK": {"S": "STUDENT#s1"},
    }
    client = AsyncMock()
    client.query = AsyncMock(
        side_effect=[
            {"Items": [], "LastEvaluatedKey": lek},
            {"Items": [], "LastEvaluatedKey": None},
        ]
    )
    repo = DynamoDbStudentEnrollmentRepository(
        table_name="grading-table",
        dynamodb_client=client,
    )

    page1 = await repo.list_exam_students(exam_id="e1", limit=5, cursor=None)
    assert page1.next_cursor is not None
    raw = base64.urlsafe_b64decode(page1.next_cursor + "=" * (-len(page1.next_cursor) % 4))
    assert json.loads(raw.decode("utf-8")) == {
        "PK": {"S": "EXAM#e1"},
        "SK": {"S": "STUDENT#s1"},
    }

    await repo.list_exam_students(exam_id="e1", limit=5, cursor=page1.next_cursor)

    assert client.query.await_count == 2
    second_kwargs = client.query.await_args_list[1].kwargs
    assert second_kwargs["ExclusiveStartKey"] == lek
