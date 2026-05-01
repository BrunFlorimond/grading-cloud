"""Unit tests for DynamoDbInviteRepository."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from botocore.exceptions import ClientError
from grading_shared.domain.exam import Exam, ExamStatus
from grading_shared.domain.models import MetaModel, NotationPayload, StudentModel, TotauxModel

from exam_api.domain.errors import StudentExamScopeConflictError
from exam_api.domain.student import Student
from exam_api.infrastructure.dynamodb_invite_repository import DynamoDbInviteRepository


@pytest.mark.asyncio
async def test_save_exam_put_item_with_expected_keys() -> None:
    client = AsyncMock()
    client.put_item = AsyncMock()
    repository = DynamoDbInviteRepository(
        table_name="grading-table",
        dynamodb_client=client,
    )
    exam = Exam(
        exam_id="exam-1",
        teacher_id="teacher-1",
        title="Midterm",
        status=ExamStatus.DRAFT,
    )

    await repository.save_exam(exam)

    item = client.put_item.call_args.kwargs["Item"]
    assert item["PK"]["S"] == "EXAM#exam-1"
    assert item["SK"]["S"] == "METADATA"
    assert item["teacher_id"]["S"] == "teacher-1"
    assert item["title"]["S"] == "Midterm"
    assert item["status"]["S"] == ExamStatus.DRAFT.value
    client.put_item.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_exam_returns_exam_when_metadata_exists() -> None:
    client = AsyncMock()
    client.get_item = AsyncMock(
        return_value={
            "Item": {
                "PK": {"S": "EXAM#exam-1"},
                "SK": {"S": "METADATA"},
                "teacher_id": {"S": "teacher-1"},
                "title": {"S": "Math Midterm"},
                "status": {"S": "ready"},
            }
        }
    )
    repository = DynamoDbInviteRepository(
        table_name="grading-table",
        dynamodb_client=client,
    )

    exam = await repository.get_exam(exam_id="exam-1")

    assert exam == Exam(
        exam_id="exam-1",
        teacher_id="teacher-1",
        title="Math Midterm",
        status=ExamStatus.READY,
    )
    client.get_item.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_student_scope_writes_student_item() -> None:
    client = AsyncMock()
    client.transact_write_items = AsyncMock()
    repository = DynamoDbInviteRepository(
        table_name="grading-table",
        dynamodb_client=client,
    )

    await repository.upsert_student_scope(
        student=Student(
            student_id="student-sub-1",
            exam_id="exam-1",
            email="student@example.com",
        ),
        teacher_id="teacher-1",
        external_student_id="roster-17",
    )

    transact_kwargs = client.transact_write_items.call_args.kwargs
    assert len(transact_kwargs["TransactItems"]) == 2
    exam_scope_write = transact_kwargs["TransactItems"][0]["Update"]
    reverse_scope_write = transact_kwargs["TransactItems"][1]["Update"]

    assert exam_scope_write["Key"]["PK"]["S"] == "EXAM#exam-1"
    assert exam_scope_write["Key"]["SK"]["S"] == "STUDENT#student-sub-1"
    assert "if_not_exists(invited_at, :invited_at)" in exam_scope_write["UpdateExpression"]
    assert exam_scope_write["ExpressionAttributeValues"][":teacher_id"]["S"] == "teacher-1"
    assert (
        exam_scope_write["ExpressionAttributeValues"][":external_student_id"]["S"]
        == "roster-17"
    )
    assert exam_scope_write["ExpressionAttributeValues"][":email"]["S"] == "student@example.com"

    assert reverse_scope_write["Key"]["PK"]["S"] == "STUDENT#student-sub-1"
    assert reverse_scope_write["Key"]["SK"]["S"] == "SCOPE"
    assert reverse_scope_write["ExpressionAttributeValues"][":exam_id"]["S"] == "exam-1"
    assert (
        reverse_scope_write["ConditionExpression"]
        == "attribute_not_exists(exam_id) OR exam_id = :exam_id"
    )


@pytest.mark.asyncio
async def test_upsert_student_scope_raises_conflict_when_condition_fails() -> None:
    client = AsyncMock()
    client.transact_write_items = AsyncMock(
        side_effect=ClientError(
            {
                "Error": {
                    "Code": "TransactionCanceledException",
                    "Message": "Transaction cancelled",
                },
                "CancellationReasons": [
                    {"Code": "None"},
                    {"Code": "ConditionalCheckFailed"},
                ],
            },
            operation_name="TransactWriteItems",
        )
    )
    repository = DynamoDbInviteRepository(
        table_name="grading-table",
        dynamodb_client=client,
    )

    with pytest.raises(StudentExamScopeConflictError):
        await repository.upsert_student_scope(
            student=Student(
                student_id="student-sub-1",
                exam_id="exam-2",
                email="student@example.com",
            ),
            teacher_id="teacher-1",
            external_student_id="roster-17",
        )


@pytest.mark.asyncio
async def test_get_student_scope_returns_student_record() -> None:
    client = AsyncMock()
    client.get_item = AsyncMock(
        return_value={
            "Item": {
                "PK": {"S": "EXAM#exam-1"},
                "SK": {"S": "STUDENT#student-sub-1"},
                "email": {"S": "student@example.com"},
            }
        }
    )
    repository = DynamoDbInviteRepository(
        table_name="grading-table",
        dynamodb_client=client,
    )

    student = await repository.get_student_scope(exam_id="exam-1", student_sub="student-sub-1")

    assert student is not None
    assert student.student_id == "student-sub-1"
    assert student.exam_id == "exam-1"
    assert str(student.email) == "student@example.com"


@pytest.mark.asyncio
async def test_save_notation_payload_persists_payload_under_student_key() -> None:
    client = AsyncMock()
    client.put_item = AsyncMock()
    repository = DynamoDbInviteRepository(
        table_name="grading-table",
        dynamodb_client=client,
    )
    payload = NotationPayload(
        exam_id="exam-1",
        student=StudentModel(
            student_id="student-sub-1",
            first_name="Ada",
            last_name="Lovelace",
        ),
        criteres_niveau1=[],
        totaux=TotauxModel(
            total_max_points=20,
            total_points_awarded=18,
            percentage=90,
            grade=18,
        ),
        meta=MetaModel(
            corrected_at="2026-05-01T00:00:00Z",
            correction_model="claude-4.6",
            rubric_version="v1",
            language="fr",
        ),
    )

    await repository.save_notation_payload(
        exam_id="exam-1",
        student_id="student-sub-1",
        payload=payload,
    )

    called_item = client.put_item.call_args.kwargs["Item"]
    assert called_item["PK"]["S"] == "EXAM#exam-1"
    assert called_item["SK"]["S"] == "NOTATION#student-sub-1"
    assert "payload" in called_item
    client.put_item.assert_awaited_once()
