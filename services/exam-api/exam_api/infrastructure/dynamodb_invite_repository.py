"""DynamoDB repository for exam ownership and student invite scope."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Awaitable, Callable, TypeVar

import aiobotocore.session
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from grading_shared.domain.exam import Exam, ExamStatus
from grading_shared.domain.models import NotationPayload
from grading_shared.ports import ExamRepositoryPort

from exam_api.domain.errors import StudentExamScopeConflictError
from exam_api.domain.student import Student
from exam_api.ports.student_scope_repository_port import StudentScopeRepositoryPort

T = TypeVar("T")


def _ddb_deserialize(attr: dict[str, Any]) -> Any:
    """Decode one DynamoDB AttributeValue dict (low-level wire format) to Python."""
    if len(attr) != 1:
        raise ValueError(f"Expected exactly one type key in AttributeValue, got {attr!r}")
    key, val = next(iter(attr.items()))
    if key == "S":
        return val
    if key == "N":
        return Decimal(val)
    if key == "BOOL":
        return bool(val)
    if key == "NULL":
        return None
    if key == "M":
        if not isinstance(val, dict):
            raise TypeError("Invalid DynamoDB M value")
        return {k: _ddb_deserialize(v) for k, v in val.items()}
    if key == "L":
        if not isinstance(val, list):
            raise TypeError("Invalid DynamoDB L value")
        return [_ddb_deserialize(v) for v in val]
    raise ValueError(f"Unsupported DynamoDB attribute type {key!r}")


def _ddb_serialize(value: Any) -> dict[str, Any]:
    """Encode a Python value to DynamoDB AttributeValue (subset used by this repo)."""
    if value is None:
        return {"NULL": True}
    if isinstance(value, bool):
        return {"BOOL": value}
    if isinstance(value, str):
        return {"S": value}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"N": str(value)}
    if isinstance(value, Decimal):
        return {"N": format(value, "f")}
    if isinstance(value, float):
        return {"N": format(Decimal(str(value)), "f")}
    if isinstance(value, dict):
        return {"M": {k: _ddb_serialize(v) for k, v in value.items()}}
    if isinstance(value, list):
        return {"L": [_ddb_serialize(v) for v in value]}
    if isinstance(value, tuple):
        return {"L": [_ddb_serialize(v) for v in value]}
    raise TypeError(f"Unsupported Python type for DynamoDB encoding: {type(value)!r}")


def _deserialize_item(item: dict[str, Any]) -> dict[str, Any]:
    return {k: _ddb_deserialize(v) for k, v in item.items()}


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
        region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
        if not region:
            raise EnvironmentError(
                "Set AWS_REGION or AWS_DEFAULT_REGION when using DynamoDbInviteRepository "
                "without an injected dynamodb client."
            )
        return region

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

            description = flat.get("description")
            if description is not None and not isinstance(description, str):
                description = None
            subject = flat.get("subject")
            if subject is not None and not isinstance(subject, str):
                subject = None
            created_at = flat.get("created_at")
            if created_at is not None and not isinstance(created_at, str):
                created_at = None

            return Exam(
                exam_id=exam_id,
                teacher_id=teacher_id,
                title=title,
                status=status,
                description=description,
                subject=subject,
                created_at=created_at,
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
        if exam.description is not None:
            raw["description"] = exam.description
        if exam.subject is not None:
            raw["subject"] = exam.subject
        if exam.created_at is not None:
            raw["created_at"] = exam.created_at
        item = {k: _ddb_serialize(v) for k, v in raw.items()}

        async def _put(client: Any) -> None:
            await client.put_item(TableName=self._table_name, Item=item)

        await self._use_client(_put)

    async def save_notation_payload(
        self, *, exam_id: str, student_id: str, payload: NotationPayload
    ) -> None:
        dumped = payload.model_dump(mode="json")
        raw = {
            "PK": f"EXAM#{exam_id}",
            "SK": f"NOTATION#{student_id}",
            "payload": dumped,
        }
        item = {k: _ddb_serialize(v) for k, v in raw.items()}

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
