"""DynamoDB adapter for exam creation and paginated listing."""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable, TypeVar

import aiobotocore.session

from grading_shared.domain.exam import Exam

from exam_api.ports.exam_creation_repository_port import ExamCreationRepositoryPort, ExamPage

T = TypeVar("T")


class DynamoDbExamCreationRepository:
    """Implements ExamCreationRepositoryPort against the single grading DynamoDB table.

    Access patterns
    ---------------
    create_exam:
        transact_write two items (atomic):
          PK=EXAM#{exam_id}        SK=METADATA           title, teacher_id, status, created_at
          PK=TEACHER#{teacher_id}  SK=EXAM#{exam_id}     created_at (sort key for list query)

    list_teacher_exams:
        query  PK=TEACHER#{teacher_id}, SK begins_with "EXAM#"
               ScanIndexForward=False  (descending created_at)
               ExclusiveStartKey decoded from opaque base64 cursor
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
        # TODO(#13): build transact_write_items with two Put operations:
        #   - Item 1: PK=EXAM#{exam.exam_id} SK=METADATA, ConditionExpression=attribute_not_exists(PK)
        #   - Item 2: PK=TEACHER#{exam.teacher_id} SK=EXAM#{exam.exam_id}
        #   Both items must include created_at (UTC ISO-8601) for ordering.
        #   Map ClientError TransactionCanceledException → appropriate domain error if needed.
        raise NotImplementedError

    async def list_teacher_exams(
        self,
        *,
        teacher_id: str,
        limit: int,
        cursor: str | None,
    ) -> ExamPage:
        # TODO(#13): query PK=TEACHER#{teacher_id}, KeyConditionExpression SK begins_with "EXAM#"
        #   ScanIndexForward=False, Limit=limit
        #   Decode cursor from base64 JSON → ExclusiveStartKey if provided.
        #   Encode LastEvaluatedKey from response → base64 JSON next_cursor (None if no more pages).
        #   For each SK=EXAM#{exam_id} edge, either:
        #     (a) batch-get EXAM#{exam_id}/METADATA items, or
        #     (b) denormalize title+status into the edge item at write time (preferred).
        raise NotImplementedError
