"""DynamoDB adapter: read and update exam configuration in the single-table design."""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable, TypeVar

import aiobotocore.session
from grading_shared.domain.exam import Exam

T = TypeVar("T")


class DynamoDbExamConfigRepository:
    """Implements ExamConfigRepositoryPort.

    Reads from:  PK=EXAM#{exam_id}, SK=METADATA
    Updates to:  PK=EXAM#{exam_id}, SK=METADATA  (conditional update)
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
        # TODO(#14): client.get_item(TableName=..., Key={"PK": {"S": f"EXAM#{exam_id}"}, "SK": {"S": "METADATA"}})
        # TODO(#14): if no Item in response return None
        # TODO(#14): deserialize DynamoDB item → Exam aggregate using existing DDB type decoder pattern
        raise NotImplementedError

    async def save_exam_config(
        self,
        *,
        exam_id: str,
        config_s3_keys: dict[str, str],
    ) -> None:
        # TODO(#14): ExamStatus.CONFIGURED must be added to grading_shared before implementing
        # TODO(#14): client.update_item on PK=EXAM#{exam_id}, SK=METADATA
        # TODO(#14): SET config_s3_keys = :keys, #status = :configured
        # TODO(#14): ConditionExpression: attribute_exists(PK) to prevent phantom writes
        raise NotImplementedError
