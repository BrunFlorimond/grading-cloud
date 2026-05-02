"""DynamoDB adapter for exam detail and per-student pipeline status queries."""

from __future__ import annotations

import base64
import binascii
import json
import os
from typing import Any, Awaitable, Callable, TypeVar

import aiobotocore.session
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from exam_api.domain.errors import ExamNotFoundError, InvalidExamListCursorError
from exam_api.domain.student import SubmissionStatus
from exam_api.infrastructure.dynamodb_utils import deserialize_item
from exam_api.ports.exam_detail_repository_port import (
    ExamDetail,
    ExamDetailRepositoryPort,  # noqa: F401 — satisfies runtime_checkable check in main.py
    StatusCounts,
    StudentPipelinePage,
    StudentPipelineStatus,
)

T = TypeVar("T")

_SK_PREFIX = "STUDENT#"


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

    async def _query_partition_items(
        self, client: Any, *, exam_id: str
    ) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        exclusive_start_key: dict[str, Any] | None = None
        while True:
            kwargs: dict[str, Any] = {
                "TableName": self._table_name,
                "KeyConditionExpression": "PK = :pk",
                "ExpressionAttributeValues": {":pk": {"S": f"EXAM#{exam_id}"}},
            }
            if exclusive_start_key is not None:
                kwargs["ExclusiveStartKey"] = exclusive_start_key
            response = await client.query(**kwargs)
            items = response.get("Items", [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        collected.append(item)
            lek = response.get("LastEvaluatedKey")
            if isinstance(lek, dict) and lek:
                exclusive_start_key = lek
            else:
                break
        return collected

    @staticmethod
    def _exam_detail_from_metadata(
        *,
        exam_id: str,
        flat: dict[str, Any],
    ) -> ExamDetail | None:
        teacher_id = flat.get("teacher_id")
        title = flat.get("title")
        raw_status = flat.get("status")
        if not isinstance(teacher_id, str) or not teacher_id:
            return None
        if not isinstance(title, str) or not title:
            return None
        if not isinstance(raw_status, str) or not raw_status:
            return None

        description = flat.get("description")
        if description is not None and not isinstance(description, str):
            description = None
        subject = flat.get("subject")
        if subject is not None and not isinstance(subject, str):
            subject = None
        created_at = flat.get("created_at")
        if created_at is not None and not isinstance(created_at, str):
            created_at = None
        pipeline_started_at = flat.get("pipeline_started_at")
        if pipeline_started_at is not None and not isinstance(pipeline_started_at, str):
            pipeline_started_at = None
        pipeline_completed_at = flat.get("pipeline_completed_at")
        if pipeline_completed_at is not None and not isinstance(
            pipeline_completed_at, str
        ):
            pipeline_completed_at = None

        return ExamDetail(
            exam_id=exam_id,
            teacher_id=teacher_id,
            title=title,
            status=raw_status,
            description=description,
            subject=subject,
            created_at=created_at,
            pipeline_started_at=pipeline_started_at,
            pipeline_completed_at=pipeline_completed_at,
            status_counts=StatusCounts(
                pending=0,
                converted=0,
                corrected=0,
                other=0,
            ),
        )

    @staticmethod
    def _status_counts_from_student_items(items: list[dict[str, Any]]) -> StatusCounts:
        pending = 0
        converted = 0
        corrected = 0
        other = 0
        for item in items:
            flat = deserialize_item(item)
            sk = flat.get("SK")
            if not isinstance(sk, str) or not sk.startswith(_SK_PREFIX):
                continue
            raw = flat.get("submission_status", SubmissionStatus.PENDING.value)
            if not isinstance(raw, str):
                raw = SubmissionStatus.PENDING.value
            if raw == SubmissionStatus.PENDING.value:
                pending += 1
            elif raw == SubmissionStatus.CONVERTED.value:
                converted += 1
            elif raw == SubmissionStatus.CORRECTED.value:
                corrected += 1
            else:
                other += 1
        return StatusCounts(
            pending=pending,
            converted=converted,
            corrected=corrected,
            other=other,
        )

    async def get_exam_detail(self, *, exam_id: str) -> ExamDetail:
        async def _run(client: Any) -> ExamDetail:
            raw_items = await self._query_partition_items(client, exam_id=exam_id)
            metadata_flat: dict[str, Any] | None = None
            for item in raw_items:
                flat = deserialize_item(item)
                sk = flat.get("SK")
                if sk == "METADATA":
                    metadata_flat = flat
                    break
            if metadata_flat is None:
                raise ExamNotFoundError(f"Exam {exam_id!r} not found.")

            detail = self._exam_detail_from_metadata(
                exam_id=exam_id, flat=metadata_flat
            )
            if detail is None:
                raise ExamNotFoundError(f"Exam {exam_id!r} not found.")

            counts = self._status_counts_from_student_items(raw_items)
            return detail.model_copy(update={"status_counts": counts})

        try:
            return await self._use_client(_run)
        except ClientError as err:
            code = err.response.get("Error", {}).get("Code", "")
            if code == "ResourceNotFoundException":
                raise ExamNotFoundError(f"Exam {exam_id!r} not found.") from err
            raise

    @staticmethod
    def _student_pipeline_from_flat(
        flat: dict[str, Any],
    ) -> StudentPipelineStatus | None:
        sk = flat.get("SK")
        if not isinstance(sk, str) or not sk.startswith(_SK_PREFIX):
            return None
        student_id = sk[len(_SK_PREFIX) :]
        raw_sid = flat.get("student_id")
        if isinstance(raw_sid, str) and raw_sid:
            student_id = raw_sid
        if not student_id:
            return None

        nom = flat.get("nom")
        prenom = flat.get("prenom")
        classe = flat.get("classe")
        if (
            not isinstance(nom, str)
            or not isinstance(prenom, str)
            or not isinstance(classe, str)
        ):
            return None

        raw_status = flat.get("submission_status", SubmissionStatus.PENDING.value)
        submission_status = (
            raw_status
            if isinstance(raw_status, str)
            else SubmissionStatus.PENDING.value
        )

        pdf_available = bool(flat.get("pdf_available"))

        return StudentPipelineStatus(
            student_id=student_id,
            nom=nom,
            prenom=prenom,
            classe=classe,
            submission_status=submission_status,
            pdf_available=pdf_available,
        )

    async def list_exam_student_statuses(
        self,
        *,
        exam_id: str,
        limit: int,
        cursor: str | None,
    ) -> StudentPipelinePage:
        exclusive_start_key: dict[str, Any] | None = None
        if cursor is not None:
            try:
                decoded = _decode_lek(cursor)
            except ValueError as err:
                raise InvalidExamListCursorError("Invalid pagination cursor.") from err
            if not _is_valid_exclusive_start_key(decoded):
                raise InvalidExamListCursorError("Invalid pagination cursor.")
            pk_expected = f"EXAM#{exam_id}"
            if decoded.get("PK", {}).get("S") != pk_expected:
                raise InvalidExamListCursorError("Invalid pagination cursor.")
            exclusive_start_key = decoded

        async def _query(client: Any) -> StudentPipelinePage:
            kwargs: dict[str, Any] = {
                "TableName": self._table_name,
                "KeyConditionExpression": "PK = :pk AND begins_with(SK, :skp)",
                "ExpressionAttributeValues": {
                    ":pk": {"S": f"EXAM#{exam_id}"},
                    ":skp": {"S": _SK_PREFIX},
                },
                "Limit": limit,
            }
            if exclusive_start_key is not None:
                kwargs["ExclusiveStartKey"] = exclusive_start_key

            try:
                response = await client.query(**kwargs)
            except ClientError as err:
                code = err.response.get("Error", {}).get("Code", "")
                if code == "ValidationException":
                    raise InvalidExamListCursorError(
                        "Invalid pagination cursor."
                    ) from err
                raise

            items_out: list[StudentPipelineStatus] = []
            for item in response.get("Items", []):
                if not isinstance(item, dict):
                    continue
                flat = deserialize_item(item)
                row = self._student_pipeline_from_flat(flat)
                if row is not None:
                    items_out.append(row)

            next_cursor: str | None = None
            lek = response.get("LastEvaluatedKey")
            if isinstance(lek, dict) and lek:
                next_cursor = _encode_lek(lek)

            return StudentPipelinePage(items=items_out, next_cursor=next_cursor)

        return await self._use_client(_query)
