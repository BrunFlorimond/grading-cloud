"""DynamoDB adapter for exam detail and per-student pipeline status queries."""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable, TypeVar

import aiobotocore.session

from exam_api.ports.exam_detail_repository_port import (
    ExamDetail,
    ExamDetailRepositoryPort,  # noqa: F401 — satisfies runtime_checkable check in main.py
    StatusCounts,
    StudentPipelinePage,
    StudentPipelineStatus,
)

T = TypeVar("T")


class DynamoDbExamDetailRepository:
    """Single-table DynamoDB adapter for exam detail and student pipeline status.

    All student rows live under PK=EXAM#{exam_id}; a single Query retrieves
    the METADATA item and all STUDENT#{student_id} items in one round-trip.

    Without ``dynamodb_client``, each call opens a short-lived client
    (suitable for tests; production injects the lifespan-scoped client).
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
                "DynamoDbExamDetailRepository without an injected dynamodb client."
            )
        return region

    async def _use_client(self, fn: Callable[[Any], Awaitable[T]]) -> T:
        if self._injected_client is not None:
            return await fn(self._injected_client)
        async with self._session.create_client(
            "dynamodb", region_name=self._region_name()
        ) as client:
            return await fn(client)

    async def get_exam_detail(self, *, exam_id: str) -> ExamDetail:
        # TODO(#16): Query PK=EXAM#{exam_id}, KeyConditionExpression SK begins_with nothing
        #            — use Query with no SK filter to fetch METADATA + all STUDENT# rows
        # TODO(#16): separate METADATA item from STUDENT# items in the result set
        # TODO(#16): compute StatusCounts by counting student items per submission_status
        # TODO(#16): map DynamoDB item attributes to ExamDetail fields
        # TODO(#16): raise ExamNotFoundError if METADATA item absent
        raise NotImplementedError

    async def list_exam_student_statuses(
        self,
        *,
        exam_id: str,
        limit: int,
        cursor: str | None,
    ) -> StudentPipelinePage:
        # TODO(#16): Query PK=EXAM#{exam_id}, SK begins_with "STUDENT#", limit+cursor
        # TODO(#16): decode cursor (base64 urlsafe JSON) — raise InvalidExamListCursorError on bad value
        # TODO(#16): for each item determine pdf_available (S3 flag or DynamoDB attribute)
        # TODO(#16): encode next_cursor from LastEvaluatedKey
        raise NotImplementedError
