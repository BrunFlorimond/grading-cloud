"""DynamoDB adapter: read and update exam configuration in the single-table design."""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable, TypeVar

import aiobotocore.session
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from grading_shared.domain.exam import Exam, ExamStatus

from exam_api.domain.errors import ExamConfigError, ExamConfigWrongStatusError
from exam_api.infrastructure.dynamodb_utils import (
    TS_PREFIX,
    ddb_serialize,
    deserialize_item,
    exam_from_dynamodb_flat,
)

T = TypeVar("T")


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
            flat = deserialize_item(item)
            # METADATA items omit ``exam_id``; teacher listing edges include it.
            merged = dict(flat)
            merged.setdefault("exam_id", exam_id)
            return exam_from_dynamodb_flat(merged)

        return await self._use_client(_get)

    async def save_exam_config(
        self,
        *,
        exam_id: str,
        config_s3_keys: dict[str, str],
    ) -> None:
        configured_value = ExamStatus.CONFIGURED.value
        created_value = ExamStatus.CREATED.value
        keys_attr = ddb_serialize(config_s3_keys)

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

            flat = deserialize_item(meta_item)
            teacher_id = flat.get("teacher_id")
            created_at = flat.get("created_at")
            if not isinstance(teacher_id, str) or not isinstance(created_at, str):
                raise ValueError("Exam metadata is missing teacher_id or created_at.")

            ts_sk = f"{TS_PREFIX}{created_at}#{exam_id}"

            common_values: dict[str, Any] = {
                ":keys": keys_attr,
                ":new_status": {"S": configured_value},
                ":st_created": {"S": created_value},
                ":st_configured": {"S": configured_value},
            }

            status_condition = (
                "attribute_exists(PK) AND #st IN (:st_created, :st_configured)"
            )

            transact_items: list[dict[str, Any]] = [
                {
                    "Update": {
                        "TableName": self._table_name,
                        "Key": {
                            "PK": {"S": f"EXAM#{exam_id}"},
                            "SK": {"S": "METADATA"},
                        },
                        "UpdateExpression": (
                            "SET config_s3_keys = :keys, #st = :new_status"
                        ),
                        "ExpressionAttributeNames": {"#st": "status"},
                        "ExpressionAttributeValues": common_values,
                        "ConditionExpression": status_condition,
                    }
                },
                {
                    "Update": {
                        "TableName": self._table_name,
                        "Key": {
                            "PK": {"S": f"TEACHER#{teacher_id}"},
                            "SK": {"S": f"EXAM#{exam_id}"},
                        },
                        "UpdateExpression": "SET #st = :new_status",
                        "ExpressionAttributeNames": {"#st": "status"},
                        "ExpressionAttributeValues": {
                            ":new_status": {"S": configured_value},
                            ":st_created": {"S": created_value},
                            ":st_configured": {"S": configured_value},
                        },
                        "ConditionExpression": status_condition,
                    }
                },
                {
                    "Update": {
                        "TableName": self._table_name,
                        "Key": {
                            "PK": {"S": f"TEACHER#{teacher_id}"},
                            "SK": {"S": ts_sk},
                        },
                        "UpdateExpression": "SET #st = :new_status",
                        "ExpressionAttributeNames": {"#st": "status"},
                        "ExpressionAttributeValues": {
                            ":new_status": {"S": configured_value},
                            ":st_created": {"S": created_value},
                            ":st_configured": {"S": configured_value},
                        },
                        "ConditionExpression": status_condition,
                    }
                },
            ]

            try:
                await client.transact_write_items(TransactItems=transact_items)
            except ClientError as err:
                code = str(err.response.get("Error", {}).get("Code", ""))
                if code == "TransactionCanceledException":
                    reasons = err.response.get("CancellationReasons", [])
                    if isinstance(reasons, list):
                        for reason in reasons:
                            if isinstance(reason, dict) and reason.get(
                                "Code"
                            ) == "ConditionalCheckFailed":
                                raise ExamConfigWrongStatusError(
                                    "Exam status changed or no longer allows confirming "
                                    "configuration (expected created or configured)."
                                ) from err
                raise

        await self._use_client(_save)
