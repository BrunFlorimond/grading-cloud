"""DynamoDB adapter for exam creation and paginated listing."""

from __future__ import annotations

import base64
import binascii
import json
import os
from typing import Any, Awaitable, Callable, TypeVar

import aiobotocore.session
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from grading_shared.domain.exam import Exam

from exam_api.domain.errors import ExamCreationConflictError, InvalidExamListCursorError
from exam_api.infrastructure.dynamodb_utils import (
    TS_PREFIX,
    ddb_serialize,
    deserialize_item,
    exam_from_dynamodb_flat,
)
from exam_api.ports.exam_creation_repository_port import ExamPage

T = TypeVar("T")


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


def _is_valid_exclusive_start_key(key: dict[str, Any]) -> bool:
    pk = key.get("PK")
    sk = key.get("SK")
    return isinstance(pk, dict) and isinstance(sk, dict) and "S" in pk and "S" in sk


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

        sort_sk = f"{TS_PREFIX}{exam.created_at}#{exam.exam_id}"
        sort_raw = {
            "PK": f"TEACHER#{exam.teacher_id}",
            "SK": sort_sk,
            **edge_common,
        }

        metadata_item = {k: ddb_serialize(v) for k, v in metadata_raw.items()}
        ownership_item = {k: ddb_serialize(v) for k, v in ownership_raw.items()}
        sort_item = {k: ddb_serialize(v) for k, v in sort_raw.items()}

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
                    reasons = err.response.get("CancellationReasons", [])
                    if isinstance(reasons, list):
                        for reason in reasons:
                            if isinstance(reason, dict) and reason.get("Code") == "ConditionalCheckFailed":
                                raise ExamCreationConflictError(
                                    "Exam metadata already exists for this identifier."
                                ) from err
                    raise ExamCreationConflictError(
                        "Exam could not be created (transaction cancelled)."
                    ) from err
                raise

        await self._use_client(_tx)

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
                decoded = _decode_lek(cursor)
            except ValueError as err:
                raise InvalidExamListCursorError("Invalid pagination cursor.") from err
            if not _is_valid_exclusive_start_key(decoded):
                raise InvalidExamListCursorError("Invalid pagination cursor.")
            exclusive_start_key = decoded

        async def _query(client: Any) -> ExamPage:
            kwargs: dict[str, Any] = {
                "TableName": self._table_name,
                "KeyConditionExpression": "PK = :pk AND begins_with(SK, :skp)",
                "ExpressionAttributeValues": {
                    ":pk": {"S": f"TEACHER#{teacher_id}"},
                    ":skp": {"S": TS_PREFIX},
                },
                "ScanIndexForward": False,
                "Limit": limit,
            }
            if exclusive_start_key is not None:
                kwargs["ExclusiveStartKey"] = exclusive_start_key

            try:
                response = await client.query(**kwargs)
            except ClientError as err:
                raise InvalidExamListCursorError("Invalid pagination cursor.") from err
            items_out: list[Exam] = []
            for item in response.get("Items", []):
                if not isinstance(item, dict):
                    continue
                flat = deserialize_item(item)
                exam = exam_from_dynamodb_flat(flat)
                if exam is not None:
                    items_out.append(exam)

            next_cursor: str | None = None
            lek = response.get("LastEvaluatedKey")
            if isinstance(lek, dict) and lek:
                next_cursor = _encode_lek(lek)

            return ExamPage(items=items_out, next_cursor=next_cursor)

        return await self._use_client(_query)
