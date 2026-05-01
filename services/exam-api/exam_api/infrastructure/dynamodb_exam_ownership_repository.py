"""DynamoDB adapter for exam ownership checks (single-table design)."""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable, TypeVar

import aiobotocore.session

from exam_api.domain.errors import ExamNotFoundError, ExamOwnershipError

T = TypeVar("T")


class DynamoDbExamOwnershipRepository:
    """Checks teacher-to-exam ownership via the single-table DynamoDB design.

    Exam existence: PK = EXAM#{exam_id}, SK = METADATA.
    Ownership edge: PK = TEACHER#{teacher_id}, SK = EXAM#{exam_id}.

    Without ``dynamodb_client``, each call opens a short-lived DynamoDB client
    (fine for tests; production should inject the lifespan-scoped client).
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

    async def verify_teacher_owns_exam(self, *, teacher_id: str, exam_id: str) -> None:

        async def _verify(client: Any) -> None:
            exam_response = await client.get_item(
                TableName=self._table_name,
                Key={
                    "PK": {"S": f"EXAM#{exam_id}"},
                    "SK": {"S": "METADATA"},
                },
                ConsistentRead=True,
            )
            if not exam_response.get("Item"):
                raise ExamNotFoundError(f"Exam {exam_id} not found.")

            edge_response = await client.get_item(
                TableName=self._table_name,
                Key={
                    "PK": {"S": f"TEACHER#{teacher_id}"},
                    "SK": {"S": f"EXAM#{exam_id}"},
                },
                ConsistentRead=True,
            )
            if not edge_response.get("Item"):
                raise ExamOwnershipError(
                    f"Teacher {teacher_id} does not own exam {exam_id}."
                )

        await self._use_client(_verify)
