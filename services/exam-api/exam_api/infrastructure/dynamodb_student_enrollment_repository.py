"""DynamoDB adapter for student enrollment — PK=EXAM#{exam_id}, SK=STUDENT#{student_id}."""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable, TypeVar

import aiobotocore.session

from exam_api.domain.student import EnrolledStudent
from exam_api.infrastructure.dynamodb_utils import ddb_serialize, deserialize_item
from exam_api.ports.student_enrollment_repository_port import (
    EnrolledStudentPage,
    StudentEnrollmentRepositoryPort,
)

T = TypeVar("T")

# TODO(#15): decide on pagination strategy (cursor encoding matches existing pattern)


class DynamoDbStudentEnrollmentRepository:
    """Implements StudentEnrollmentRepositoryPort against the single grading DynamoDB table.

    Items written on add (one Put per student, ConditionExpression prevents duplicates):
      - PK=EXAM#{exam_id}, SK=STUDENT#{student_id}
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
                "DynamoDbStudentEnrollmentRepository without an injected dynamodb client."
            )
        return region

    async def _use_client(self, fn: Callable[[Any], Awaitable[T]]) -> T:
        if self._injected_client is not None:
            return await fn(self._injected_client)
        async with self._session.create_client(
            "dynamodb", region_name=self._region_name()
        ) as client:
            return await fn(client)

    async def add_students(
        self,
        *,
        exam_id: str,
        students: list[EnrolledStudent],
    ) -> list[EnrolledStudent]:
        # TODO(#15): implement — transact_write_items with attribute_not_exists(PK) condition
        # TODO(#15): map TransactionCanceledException / ConditionalCheckFailed → DuplicateStudentError
        raise NotImplementedError

    async def list_exam_students(
        self,
        *,
        exam_id: str,
        limit: int,
        cursor: str | None,
    ) -> EnrolledStudentPage:
        # TODO(#15): implement — query PK=EXAM#{exam_id}, begins_with(SK, "STUDENT#")
        # TODO(#15): decode/encode cursor the same way as DynamoDbExamCreationRepository
        raise NotImplementedError

    @staticmethod
    def _student_from_flat(flat: dict[str, Any], exam_id: str) -> EnrolledStudent | None:
        # TODO(#15): implement deserialization from DynamoDB flat item to EnrolledStudent
        raise NotImplementedError
