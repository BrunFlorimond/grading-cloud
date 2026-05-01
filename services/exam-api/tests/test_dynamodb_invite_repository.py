"""Unit tests for DynamoDbInviteRepository."""

from __future__ import annotations

from unittest.mock import Mock

from botocore.exceptions import ClientError
from grading_shared.domain.exam import Exam, ExamStatus
from grading_shared.domain.models import MetaModel, NotationPayload, StudentModel, TotauxModel
import pytest

from exam_api.domain.errors import StudentExamScopeConflictError
from exam_api.domain.student import Student
from exam_api.infrastructure.dynamodb_invite_repository import DynamoDbInviteRepository


def test_get_exam_returns_exam_when_metadata_exists() -> None:
    table = Mock()
    table.get_item.return_value = {
        "Item": {
            "PK": "EXAM#exam-1",
            "SK": "METADATA",
            "teacher_id": "teacher-1",
            "title": "Math Midterm",
            "status": "ready",
        }
    }
    dynamodb = Mock()
    dynamodb.Table.return_value = table
    repository = DynamoDbInviteRepository(
        table_name="grading-table",
        dynamodb_resource=dynamodb,
    )

    exam = repository.get_exam(exam_id="exam-1")

    assert exam == Exam(
        exam_id="exam-1",
        teacher_id="teacher-1",
        title="Math Midterm",
        status=ExamStatus.READY,
    )


def test_upsert_student_scope_writes_student_item() -> None:
    table = Mock()
    dynamodb = Mock()
    dynamodb.Table.return_value = table
    dynamodb.meta.client = Mock()
    repository = DynamoDbInviteRepository(
        table_name="grading-table",
        dynamodb_resource=dynamodb,
    )

    repository.upsert_student_scope(
        student=Student(
            student_id="student-sub-1",
            exam_id="exam-1",
            email="student@example.com",
        ),
        teacher_id="teacher-1",
        external_student_id="roster-17",
    )

    transact_kwargs = dynamodb.meta.client.transact_write_items.call_args.kwargs
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


def test_upsert_student_scope_raises_conflict_when_condition_fails() -> None:
    table = Mock()
    dynamodb = Mock()
    dynamodb.Table.return_value = table
    dynamodb.meta.client = Mock()
    dynamodb.meta.client.transact_write_items.side_effect = ClientError(
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
    repository = DynamoDbInviteRepository(
        table_name="grading-table",
        dynamodb_resource=dynamodb,
    )

    with pytest.raises(StudentExamScopeConflictError):
        repository.upsert_student_scope(
            student=Student(
                student_id="student-sub-1",
                exam_id="exam-2",
                email="student@example.com",
            ),
            teacher_id="teacher-1",
            external_student_id="roster-17",
        )


def test_get_student_scope_returns_student_record() -> None:
    table = Mock()
    table.get_item.return_value = {
        "Item": {
            "PK": "EXAM#exam-1",
            "SK": "STUDENT#student-sub-1",
            "email": "student@example.com",
        }
    }
    dynamodb = Mock()
    dynamodb.Table.return_value = table
    repository = DynamoDbInviteRepository(
        table_name="grading-table",
        dynamodb_resource=dynamodb,
    )

    student = repository.get_student_scope(exam_id="exam-1", student_sub="student-sub-1")

    assert student is not None
    assert student.student_id == "student-sub-1"
    assert student.exam_id == "exam-1"
    assert str(student.email) == "student@example.com"


def test_get_exam_id_for_student_sub_returns_exam_id() -> None:
    table = Mock()
    table.get_item.return_value = {
        "Item": {
            "PK": "STUDENT#student-sub-1",
            "SK": "SCOPE",
            "exam_id": "exam-1",
        }
    }
    dynamodb = Mock()
    dynamodb.Table.return_value = table
    repository = DynamoDbInviteRepository(
        table_name="grading-table",
        dynamodb_resource=dynamodb,
    )

    exam_id = repository.get_exam_id_for_student_sub(student_sub="student-sub-1")

    assert exam_id == "exam-1"


def test_save_notation_payload_persists_payload_under_student_key() -> None:
    table = Mock()
    dynamodb = Mock()
    dynamodb.Table.return_value = table
    repository = DynamoDbInviteRepository(
        table_name="grading-table",
        dynamodb_resource=dynamodb,
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

    repository.save_notation_payload(
        exam_id="exam-1",
        student_id="student-sub-1",
        payload=payload,
    )

    called_item = table.put_item.call_args.kwargs["Item"]
    assert called_item["PK"] == "EXAM#exam-1"
    assert called_item["SK"] == "NOTATION#student-sub-1"
    assert called_item["payload"]["exam_id"] == "exam-1"
