"""DynamoDB repository for exam ownership and student invite scope."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from grading_shared.domain.exam import Exam, ExamStatus
from grading_shared.domain.models import NotationPayload
from grading_shared.ports import ExamRepositoryPort

from exam_api.domain.errors import StudentExamScopeConflictError
from exam_api.domain.student import Student
from exam_api.ports.student_scope_repository_port import StudentScopeRepositoryPort


class DynamoDbInviteRepository(ExamRepositoryPort, StudentScopeRepositoryPort):
    def __init__(self, *, table_name: str, dynamodb_resource: Any | None = None) -> None:
        resource = dynamodb_resource or boto3.resource("dynamodb")
        self._table_name = table_name
        self._table = resource.Table(table_name)
        self._dynamodb_client = resource.meta.client

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

    def upsert_student_scope(
        self, *, student: Student, teacher_id: str, external_student_id: str
    ) -> None:
        now_iso = datetime.now(UTC).isoformat()
        try:
            self._dynamodb_client.transact_write_items(
                TransactItems=[
                    {
                        "Update": {
                            "TableName": self._table_name,
                            "Key": {
                                "PK": {"S": f"EXAM#{student.exam_id}"},
                                "SK": {"S": f"STUDENT#{student.student_id}"},
                            },
                            "UpdateExpression": (
                                "SET teacher_id = :teacher_id, "
                                "student_id = :student_id, "
                                "external_student_id = :external_student_id, "
                                "email = :email, "
                                "updated_at = :updated_at, "
                                "invited_at = if_not_exists(invited_at, :invited_at)"
                            ),
                            "ExpressionAttributeValues": {
                                ":teacher_id": {"S": teacher_id},
                                ":student_id": {"S": student.student_id},
                                ":external_student_id": {"S": external_student_id},
                                ":email": {"S": str(student.email)},
                                ":updated_at": {"S": now_iso},
                                ":invited_at": {"S": now_iso},
                            },
                        }
                    },
                    {
                        "Update": {
                            "TableName": self._table_name,
                            "Key": {
                                "PK": {"S": f"STUDENT#{student.student_id}"},
                                "SK": {"S": "SCOPE"},
                            },
                            "UpdateExpression": (
                                "SET exam_id = :exam_id, "
                                "teacher_id = :teacher_id, "
                                "external_student_id = :external_student_id, "
                                "email = :email, "
                                "updated_at = :updated_at, "
                                "invited_at = if_not_exists(invited_at, :invited_at)"
                            ),
                            "ConditionExpression": (
                                "attribute_not_exists(exam_id) OR exam_id = :exam_id"
                            ),
                            "ExpressionAttributeValues": {
                                ":exam_id": {"S": student.exam_id},
                                ":teacher_id": {"S": teacher_id},
                                ":external_student_id": {"S": external_student_id},
                                ":email": {"S": str(student.email)},
                                ":updated_at": {"S": now_iso},
                                ":invited_at": {"S": now_iso},
                            },
                        }
                    },
                ]
            )
        except ClientError as err:
            if self._is_scope_conflict_error(err):
                raise StudentExamScopeConflictError(
                    "Student account is already scoped to another exam."
                ) from err
            raise

    def get_student_scope(self, *, exam_id: str, student_sub: str) -> Student | None:
        response = self._table.get_item(
            Key={
                "PK": f"EXAM#{exam_id}",
                "SK": f"STUDENT#{student_sub}",
            },
            ConsistentRead=True,
        )
        item = response.get("Item")
        if not isinstance(item, dict):
            return None
        email = item.get("email")
        if not isinstance(email, str) or not email:
            return None
        return Student(student_id=student_sub, exam_id=exam_id, email=email)

    def get_exam_id_for_student_sub(self, *, student_sub: str) -> str | None:
        response = self._table.get_item(
            Key={
                "PK": f"STUDENT#{student_sub}",
                "SK": "SCOPE",
            },
            ConsistentRead=True,
        )
        item = response.get("Item")
        if not isinstance(item, dict):
            return None
        exam_id = item.get("exam_id")
        if not isinstance(exam_id, str) or not exam_id:
            return None
        return exam_id

    @staticmethod
    def _is_scope_conflict_error(err: ClientError) -> bool:
        code = str(err.response.get("Error", {}).get("Code", ""))
        if code == "ConditionalCheckFailedException":
            return True
        if code != "TransactionCanceledException":
            return False
        reasons = err.response.get("CancellationReasons", [])
        if not isinstance(reasons, list):
            return False
        for reason in reasons:
            if not isinstance(reason, dict):
                continue
            if reason.get("Code") == "ConditionalCheckFailed":
                return True
        return False
