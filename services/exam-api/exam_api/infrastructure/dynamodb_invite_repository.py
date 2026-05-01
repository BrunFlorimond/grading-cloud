"""DynamoDB repository for exam ownership and student invite scope."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import boto3  # type: ignore[import-untyped]

from grading_shared.domain.exam import Exam, ExamStatus
from grading_shared.domain.models import NotationPayload
from grading_shared.ports import ExamRepositoryPort

from exam_api.application.invite_student import StudentScopeRepositoryPort
from exam_api.domain.student import Student


class DynamoDbInviteRepository(ExamRepositoryPort, StudentScopeRepositoryPort):
    def __init__(self, *, table_name: str, dynamodb_resource: Any | None = None) -> None:
        resource = dynamodb_resource or boto3.resource("dynamodb")
        self._table = resource.Table(table_name)

    def get_exam(self, *, exam_id: str) -> Exam | None:
        response = self._table.get_item(
            Key={"PK": f"EXAM#{exam_id}", "SK": "METADATA"},
            ConsistentRead=True,
        )
        item = response.get("Item")
        if not isinstance(item, dict):
            return None

        teacher_id = item.get("teacher_id")
        title = item.get("title")
        if not isinstance(teacher_id, str) or not teacher_id:
            return None
        if not isinstance(title, str) or not title:
            return None

        raw_status = item.get("status", ExamStatus.DRAFT.value)
        if not isinstance(raw_status, str):
            raw_status = ExamStatus.DRAFT.value
        try:
            status = ExamStatus(raw_status)
        except ValueError:
            status = ExamStatus.DRAFT

        return Exam(
            exam_id=exam_id,
            teacher_id=teacher_id,
            title=title,
            status=status,
        )

    def save_exam(self, exam: Exam) -> None:
        self._table.put_item(
            Item={
                "PK": f"EXAM#{exam.exam_id}",
                "SK": "METADATA",
                "teacher_id": exam.teacher_id,
                "title": exam.title,
                "status": exam.status.value,
            }
        )

    def save_notation_payload(
        self, *, exam_id: str, student_id: str, payload: NotationPayload
    ) -> None:
        self._table.put_item(
            Item={
                "PK": f"EXAM#{exam_id}",
                "SK": f"NOTATION#{student_id}",
                "payload": payload.model_dump(mode="json"),
            }
        )

    def upsert_student_scope(self, *, student: Student, teacher_id: str) -> None:
        now_iso = datetime.now(UTC).isoformat()
        self._table.put_item(
            Item={
                "PK": f"EXAM#{student.exam_id}",
                "SK": f"STUDENT#{student.student_id}",
                "teacher_id": teacher_id,
                "student_id": student.student_id,
                "email": str(student.email),
                "invited_at": now_iso,
                "updated_at": now_iso,
            }
        )
