"""DynamoDB adapter: read and update exam configuration in the single-table design."""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable, TypeVar

import aiobotocore.session
from grading_shared.domain.exam import Exam, ExamStatus

from exam_api.domain.errors import ExamConfigError
from exam_api.infrastructure.dynamodb_exam_creation_repository import (
    DynamoDbExamCreationRepository,
    _TS_PREFIX,
    _ddb_serialize,
    _deserialize_item,
)

T = TypeVar("T")

_EXAM_FLAT_PARSER = DynamoDbExamCreationRepository(
    table_name="_",
    dynamodb_client=None,
)


class DynamoDbExamConfigRepository:
    """Implements ExamConfigRepositoryPort.

    Reads from:  PK=EXAM#{exam_id}, SK=METADATA
    Updates to:  PK=EXAM#{exam_id}, SK=METADATA and matching teacher edges (same status).
    """

    def __init__(
        self,
        table_name: str,
        *,
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
                "DynamoDbExamConfigRepository without an injected dynamodb client."
            )
        return region

    async def _use_client(self, fn: Callable[[Any], Awaitable[T]]) -> T:
        if self._injected_client is not None:
            return await fn(self._injected_client)
        async with self._session.create_client(
            "dynamodb", region_name=self._region_name()
        ) as client:
            return await fn(client)

    async def get_exam_for_config(self, *, exam_id: str) -> Exam | None:
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
            if not item or not isinstance(item, dict):
                return None
            flat = _deserialize_item(item)
            # METADATA items omit ``exam_id``; teacher listing edges include it.
            merged = dict(flat)
            merged.setdefault("exam_id", exam_id)
            return _EXAM_FLAT_PARSER._exam_from_sort_item(merged)

        return await self._use_client(_get)

    async def save_exam_config(
        self,
        *,
        exam_id: str,
        config_s3_keys: dict[str, str],
    ) -> None:
        configured_value = ExamStatus.CONFIGURED.value
        keys_attr = _ddb_serialize(config_s3_keys)

        async def _save(client: Any) -> None:
            meta_response = await client.get_item(
                TableName=self._table_name,
                Key={
                    "PK": {"S": f"EXAM#{exam_id}"},
                    "SK": {"S": "METADATA"},
                },
                ConsistentRead=True,
            )
            meta_item = meta_response.get("Item")
            if not meta_item:
                raise ExamConfigError("Exam metadata not found for config save.")

            flat = _deserialize_item(meta_item)
            teacher_id = flat.get("teacher_id")
            created_at = flat.get("created_at")
            if not isinstance(teacher_id, str) or not isinstance(created_at, str):
                raise ValueError("Exam metadata is missing teacher_id or created_at.")

            ts_sk = f"{_TS_PREFIX}{created_at}#{exam_id}"

            transact_items: list[dict[str, Any]] = [
                {
                    "Update": {
                        "TableName": self._table_name,
                        "Key": {
                            "PK": {"S": f"EXAM#{exam_id}"},
                            "SK": {"S": "METADATA"},
                        },
                        "UpdateExpression": (
                            "SET config_s3_keys = :keys, #st = :configured"
                        ),
                        "ExpressionAttributeNames": {"#st": "status"},
                        "ExpressionAttributeValues": {
                            ":keys": keys_attr,
                            ":configured": {"S": configured_value},
                        },
                        "ConditionExpression": "attribute_exists(PK)",
                    }
                },
                {
                    "Update": {
                        "TableName": self._table_name,
                        "Key": {
                            "PK": {"S": f"TEACHER#{teacher_id}"},
                            "SK": {"S": f"EXAM#{exam_id}"},
                        },
                        "UpdateExpression": "SET #st = :configured",
                        "ExpressionAttributeNames": {"#st": "status"},
                        "ExpressionAttributeValues": {
                            ":configured": {"S": configured_value},
                        },
                        "ConditionExpression": "attribute_exists(PK)",
                    }
                },
                {
                    "Update": {
                        "TableName": self._table_name,
                        "Key": {
                            "PK": {"S": f"TEACHER#{teacher_id}"},
                            "SK": {"S": ts_sk},
                        },
                        "UpdateExpression": "SET #st = :configured",
                        "ExpressionAttributeNames": {"#st": "status"},
                        "ExpressionAttributeValues": {
                            ":configured": {"S": configured_value},
                        },
                        "ConditionExpression": "attribute_exists(PK)",
                    }
                },
            ]

            await client.transact_write_items(TransactItems=transact_items)

        await self._use_client(_save)
