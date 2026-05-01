"""DynamoDB repository for exam ownership and student invite scope."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Awaitable, Callable, TypeVar

import aiobotocore.session
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from grading_shared.domain.exam import Exam, ExamStatus
from grading_shared.domain.models import NotationPayload
from grading_shared.ports import ExamRepositoryPort

from exam_api.domain.errors import StudentExamScopeConflictError
from exam_api.domain.student import Student
from exam_api.ports.student_scope_repository_port import StudentScopeRepositoryPort

_deserializer = TypeDeserializer()
_serializer = TypeSerializer()

T = TypeVar("T")


def _floats_to_decimal(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _floats_to_decimal(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_floats_to_decimal(v) for v in value]
    return value


def _deserialize_item(item: dict[str, Any]) -> dict[str, Any]:
    return {k: _deserializer.deserialize(v) for k, v in item.items()}


class DynamoDbInviteRepository(ExamRepositoryPort, StudentScopeRepositoryPort):
    def __init__(
        self,
        *,
        table_name: str,
        session: aiobotocore.session.AioSession | None = None,
        dynamodb_client: Any | None = None,
    ) -> None:
        self._table_name = table_name
        self._session = session or aiobotocore.session.get_session()
        self._injected_client = dynamodb_client

    def _region_name(self) -> str:
        return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"

    async def _use_client(
        self, fn: Callable[[Any], Awaitable[T]],
    ) -> T:
        if self._injected_client is not None:
            return await fn(self._injected_client)
        async with self._session.create_client(
            "dynamodb", region_name=self._region_name()
        ) as client:
            return await fn(client)

    async def get_exam(self, *, exam_id: str) -> Exam | None:

        async def _get(client: Any) -> Exam | None:
            response = await client.get_item(
                TableName=self._table_name,
                Key={
                    "PK": {"S": f"EXAM#{exam_id}"},
                    "SK": {"S": "METADATA"},
                },
                ConsistentRead=True,
            )
            item = response.get("Item")
            if not isinstance(item, dict):
                return None
            flat = _deserialize_item(item)

            teacher_id = flat.get("teacher_id")
            title = flat.get("title")
            if not isinstance(teacher_id, str) or not teacher_id:
                return None
            if not isinstance(title, str) or not title:
                return None

            raw_status = flat.get("status", ExamStatus.DRAFT.value)
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

        return await self._use_client(_get)

    async def save_exam(self, exam: Exam) -> None:
        raw = {
            "PK": f"EXAM#{exam.exam_id}",
            "SK": "METADATA",
            "teacher_id": exam.teacher_id,
            "title": exam.title,
            "status": exam.status.value,
        }
        item = {k: _serializer.serialize(v) for k, v in raw.items()}

        async def _put(client: Any) -> None:
            await client.put_item(TableName=self._table_name, Item=item)

        await self._use_client(_put)

    async def save_notation_payload(
        self, *, exam_id: str, student_id: str, payload: NotationPayload
    ) -> None:
        dumped = _floats_to_decimal(payload.model_dump(mode="json"))
        raw = {
            "PK": f"EXAM#{exam_id}",
            "SK": f"NOTATION#{student_id}",
            "payload": dumped,
        }
        item = {k: _serializer.serialize(v) for k, v in raw.items()}

        async def _put(client: Any) -> None:
            await client.put_item(TableName=self._table_name, Item=item)

        await self._use_client(_put)

    async def upsert_student_scope(
        self, *, student: Student, teacher_id: str, external_student_id: str
    ) -> None:
        now_iso = datetime.now(UTC).isoformat()

        async def _tx(client: Any) -> None:
            try:
                await client.transact_write_items(
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

        await self._use_client(_tx)

    async def get_student_scope(self, *, exam_id: str, student_sub: str) -> Student | None:

        async def _get(client: Any) -> Student | None:
            response = await client.get_item(
                TableName=self._table_name,
                Key={
                    "PK": {"S": f"EXAM#{exam_id}"},
                    "SK": {"S": f"STUDENT#{student_sub}"},
                },
                ConsistentRead=True,
            )
            item = response.get("Item")
            if not isinstance(item, dict):
                return None
            flat = _deserialize_item(item)
            email = flat.get("email")
            if not isinstance(email, str) or not email:
                return None
            return Student(student_id=student_sub, exam_id=exam_id, email=email)

        return await self._use_client(_get)

    @staticmethod
    def _is_scope_conflict_error(err: ClientError) -> bool:
        code = str(err.response.get("Error", {}).get("Code", ""))
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
