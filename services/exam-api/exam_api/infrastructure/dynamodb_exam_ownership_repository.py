"""DynamoDB adapter for exam ownership checks (single-table design)."""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable, TypeVar

import aiobotocore.session

T = TypeVar("T")


class DynamoDbExamOwnershipRepository:
    """Checks teacher-to-exam ownership via the single-table DynamoDB design.

    PK = TEACHER#{teacher_id}
    SK = EXAM#{exam_id}
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
                "DynamoDbExamOwnershipRepository without an injected dynamodb client."
            )
        return region

    async def _use_client(
        self,
        fn: Callable[[Any], Awaitable[T]],
    ) -> T:
        if self._injected_client is not None:
            return await fn(self._injected_client)
        async with self._session.create_client(
            "dynamodb", region_name=self._region_name()
        ) as client:
            return await fn(client)

    async def teacher_owns_exam(self, *, teacher_id: str, exam_id: str) -> bool:
        pk = f"TEACHER#{teacher_id}"
        sk = f"EXAM#{exam_id}"

        async def _get_item(client: Any) -> bool:
            response = await client.get_item(
                TableName=self._table_name,
                Key={"PK": {"S": pk}, "SK": {"S": sk}},
                ConsistentRead=True,
            )
            return bool(response.get("Item"))

        return await self._use_client(_get_item)
