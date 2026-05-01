"""DynamoDB adapter for exam creation and paginated listing."""

from __future__ import annotations

import base64
import binascii
import json
import os
from decimal import Decimal
from typing import Any, Awaitable, Callable, TypeVar

import aiobotocore.session
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from grading_shared.domain.exam import Exam, ExamStatus

from exam_api.ports.exam_creation_repository_port import ExamCreationRepositoryPort, ExamPage

T = TypeVar("T")

_TS_PREFIX = "TS#"


def _ddb_deserialize(attr: dict[str, Any]) -> Any:
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


def _encode_lek(key: dict[str, Any]) -> str:
    raw = json.dumps(key, sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_lek(cursor: str) -> dict[str, Any]:
    pad = "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(cursor + pad)
    except binascii.Error as err:
        raise ValueError("Invalid pagination cursor.") from err
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as err:
        raise ValueError("Invalid pagination cursor.") from err
    if not isinstance(decoded, dict):
        raise ValueError("Invalid pagination cursor.")
    return decoded


class DynamoDbExamCreationRepository:
    """Implements ExamCreationRepositoryPort against the single grading DynamoDB table.

    Items written on create (single transact):
      - PK=EXAM#{exam_id}, SK=METADATA — exam aggregate fields.
      - PK=TEACHER#{teacher_id}, SK=EXAM#{exam_id} — ownership edge (O(1) ownership checks).
      - PK=TEACHER#{teacher_id}, SK=TS#{created_at}#{exam_id} — time-ordered listing edge.

    ``TS#`` rows sort lexicographically by ``created_at`` (UTC, fixed-width ISO-8601).
    """

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
                "Set AWS_REGION or AWS_DEFAULT_REGION when using "
                "DynamoDbExamCreationRepository without an injected dynamodb client."
            )
        return region

    async def _use_client(self, fn: Callable[[Any], Awaitable[T]]) -> T:
        if self._injected_client is not None:
            return await fn(self._injected_client)
        async with self._session.create_client(
            "dynamodb", region_name=self._region_name()
        ) as client:
            return await fn(client)

    async def create_exam(self, exam: Exam) -> None:
        if exam.created_at is None:
            raise ValueError("Exam.created_at must be set before persisting.")

        metadata_raw = {
            "PK": f"EXAM#{exam.exam_id}",
            "SK": "METADATA",
            "teacher_id": exam.teacher_id,
            "title": exam.title,
            "status": exam.status.value,
            "created_at": exam.created_at,
        }
        if exam.description is not None:
            metadata_raw["description"] = exam.description
        if exam.subject is not None:
            metadata_raw["subject"] = exam.subject

        edge_common = {
            "teacher_id": exam.teacher_id,
            "exam_id": exam.exam_id,
            "title": exam.title,
            "status": exam.status.value,
            "created_at": exam.created_at,
        }
        if exam.description is not None:
            edge_common["description"] = exam.description
        if exam.subject is not None:
            edge_common["subject"] = exam.subject

        ownership_raw = {
            "PK": f"TEACHER#{exam.teacher_id}",
            "SK": f"EXAM#{exam.exam_id}",
            **edge_common,
        }

        sort_sk = f"{_TS_PREFIX}{exam.created_at}#{exam.exam_id}"
        sort_raw = {
            "PK": f"TEACHER#{exam.teacher_id}",
            "SK": sort_sk,
            **edge_common,
        }

        metadata_item = {k: _ddb_serialize(v) for k, v in metadata_raw.items()}
        ownership_item = {k: _ddb_serialize(v) for k, v in ownership_raw.items()}
        sort_item = {k: _ddb_serialize(v) for k, v in sort_raw.items()}

        async def _tx(client: Any) -> None:
            try:
                await client.transact_write_items(
                    TransactItems=[
                        {
                            "Put": {
                                "TableName": self._table_name,
                                "Item": metadata_item,
                                "ConditionExpression": "attribute_not_exists(PK)",
                            }
                        },
                        {"Put": {"TableName": self._table_name, "Item": ownership_item}},
                        {"Put": {"TableName": self._table_name, "Item": sort_item}},
                    ]
                )
            except ClientError as err:
                code = str(err.response.get("Error", {}).get("Code", ""))
                if code == "TransactionCanceledException":
                    raise RuntimeError("Exam could not be created (transaction cancelled).") from err
                raise

        await self._use_client(_tx)

    def _exam_from_sort_item(self, flat: dict[str, Any]) -> Exam | None:
        exam_id = flat.get("exam_id")
        teacher_id = flat.get("teacher_id")
        title = flat.get("title")
        if not isinstance(exam_id, str) or not exam_id:
            return None
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

    async def list_teacher_exams(
        self,
        *,
        teacher_id: str,
        limit: int,
        cursor: str | None,
    ) -> ExamPage:
        exclusive_start_key: dict[str, Any] | None = None
        if cursor is not None:
            try:
                exclusive_start_key = _decode_lek(cursor)
            except ValueError:
                return ExamPage(items=[], next_cursor=None)

        async def _query(client: Any) -> ExamPage:
            kwargs: dict[str, Any] = {
                "TableName": self._table_name,
                "KeyConditionExpression": "PK = :pk AND begins_with(SK, :skp)",
                "ExpressionAttributeValues": {
                    ":pk": {"S": f"TEACHER#{teacher_id}"},
                    ":skp": {"S": _TS_PREFIX},
                },
                "ScanIndexForward": False,
                "Limit": limit,
            }
            if exclusive_start_key is not None:
                kwargs["ExclusiveStartKey"] = exclusive_start_key

            response = await client.query(**kwargs)
            items_out: list[Exam] = []
            for item in response.get("Items", []):
                if not isinstance(item, dict):
                    continue
                flat = _deserialize_item(item)
                exam = self._exam_from_sort_item(flat)
                if exam is not None:
                    items_out.append(exam)

            next_cursor: str | None = None
            lek = response.get("LastEvaluatedKey")
            if isinstance(lek, dict) and lek:
                next_cursor = _encode_lek(lek)

            return ExamPage(items=items_out, next_cursor=next_cursor)

        return await self._use_client(_query)
