"""Unit tests for DynamoDbInviteRepository."""

from __future__ import annotations

from unittest.mock import Mock

from grading_shared.domain.exam import Exam, ExamStatus
from grading_shared.domain.models import MetaModel, NotationPayload, StudentModel, TotauxModel

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

    called_item = table.put_item.call_args.kwargs["Item"]
    assert called_item["PK"] == "EXAM#exam-1"
    assert called_item["SK"] == "STUDENT#student-sub-1"
    assert called_item["teacher_id"] == "teacher-1"
    assert called_item["external_student_id"] == "roster-17"
    assert called_item["email"] == "student@example.com"


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
