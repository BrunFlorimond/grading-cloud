"""DynamoDB adapter for student enrollment — PK=EXAM#{exam_id}, SK=STUDENT#{student_id}."""

from __future__ import annotations

import base64
import binascii
import json
import os
from typing import Any, Awaitable, Callable, TypeVar

import aiobotocore.session
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from exam_api.domain.errors import DuplicateStudentError, InvalidExamListCursorError
from exam_api.domain.student import EnrolledStudent, SubmissionStatus
from exam_api.infrastructure.dynamodb_utils import ddb_serialize, deserialize_item
from exam_api.ports.student_enrollment_repository_port import EnrolledStudentPage

T = TypeVar("T")

_TRANSACT_MAX_ITEMS = 25
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


class DynamoDbStudentEnrollmentRepository:
    """Implements StudentEnrollmentRepositoryPort against the single grading DynamoDB table.

    Items written on add (Put per student in chunks of 25, ConditionExpression prevents dupes):
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

    @staticmethod
    def _item_put(exam_id: str, student: EnrolledStudent) -> dict[str, Any]:
        pk = f"EXAM#{exam_id}"
        sk = f"{_SK_PREFIX}{student.student_id}"
        raw: dict[str, Any] = {
            "PK": pk,
            "SK": sk,
            "exam_id": exam_id,
            "student_id": student.student_id,
            "nom": student.nom,
            "prenom": student.prenom,
            "classe": student.classe,
            "submission_status": student.submission_status.value,
        }
        if student.email is not None:
            raw["email"] = str(student.email)
        return {k: ddb_serialize(v) for k, v in raw.items()}

    async def _compensate_delete(
        self, client: Any, exam_id: str, student_ids: list[str]
    ) -> None:
        for i in range(0, len(student_ids), _TRANSACT_MAX_ITEMS):
            chunk = student_ids[i : i + _TRANSACT_MAX_ITEMS]
            transact_items = [
                {
                    "Delete": {
                        "TableName": self._table_name,
                        "Key": {
                            "PK": {"S": f"EXAM#{exam_id}"},
                            "SK": {"S": f"{_SK_PREFIX}{sid}"},
                        },
                    }
                }
                for sid in chunk
            ]
            await client.transact_write_items(TransactItems=transact_items)

    async def add_students(
        self,
        *,
        exam_id: str,
        students: list[EnrolledStudent],
    ) -> list[EnrolledStudent]:
        if not students:
            return []

        committed_ids: list[str] = []

        async def _run(client: Any) -> None:
            nonlocal committed_ids
            for chunk_start in range(0, len(students), _TRANSACT_MAX_ITEMS):
                chunk = students[chunk_start : chunk_start + _TRANSACT_MAX_ITEMS]
                transact_items = [
                    {
                        "Put": {
                            "TableName": self._table_name,
                            "Item": self._item_put(exam_id, s),
                            "ConditionExpression": "attribute_not_exists(PK)",
                        }
                    }
                    for s in chunk
                ]
                try:
                    await client.transact_write_items(TransactItems=transact_items)
                except ClientError as err:
                    code = str(err.response.get("Error", {}).get("Code", ""))
                    if code == "TransactionCanceledException":
                        fail_sid = self._failure_student_id(chunk, err)
                        if chunk_start > 0 and committed_ids:
                            try:
                                await self._compensate_delete(
                                    client, exam_id, committed_ids
                                )
                            except ClientError:
                                pass
                            committed_ids = []
                        raise DuplicateStudentError(fail_sid, exam_id) from err
                    raise
                committed_ids.extend(s.student_id for s in chunk)

        await self._use_client(_run)
        return students

    @staticmethod
    def _failure_student_id(
        chunk: list[EnrolledStudent], err: ClientError
    ) -> str:
        reasons = err.response.get("CancellationReasons", [])
        if isinstance(reasons, list):
            for i, reason in enumerate(reasons):
                if isinstance(reason, dict) and reason.get("Code") == "ConditionalCheckFailed":
                    if i < len(chunk):
                        return chunk[i].student_id
        return chunk[0].student_id if chunk else "unknown"

    async def list_exam_students(
        self,
        *,
        exam_id: str,
        limit: int,
        cursor: str | None,
    ) -> EnrolledStudentPage:
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

        async def _query(client: Any) -> EnrolledStudentPage:
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

            items_out: list[EnrolledStudent] = []
            for item in response.get("Items", []):
                if not isinstance(item, dict):
                    continue
                flat = deserialize_item(item)
                student = DynamoDbStudentEnrollmentRepository._student_from_flat(
                    flat, exam_id
                )
                if student is not None:
                    items_out.append(student)

            next_cursor: str | None = None
            lek = response.get("LastEvaluatedKey")
            if isinstance(lek, dict) and lek:
                next_cursor = _encode_lek(lek)

            return EnrolledStudentPage(items=items_out, next_cursor=next_cursor)

        return await self._use_client(_query)

    @staticmethod
    def _student_from_flat(flat: dict[str, Any], exam_id: str) -> EnrolledStudent | None:
        sk = flat.get("SK")
        if not isinstance(sk, str) or not sk.startswith(_SK_PREFIX):
            return None
        student_id = sk[len(_SK_PREFIX) :]
        if not student_id:
            return None
        raw_sid = flat.get("student_id")
        if isinstance(raw_sid, str) and raw_sid:
            student_id = raw_sid

        nom = flat.get("nom")
        prenom = flat.get("prenom")
        classe = flat.get("classe")
        if not isinstance(nom, str) or not isinstance(prenom, str) or not isinstance(
            classe, str
        ):
            return None

        raw_status = flat.get("submission_status", SubmissionStatus.PENDING.value)
        if not isinstance(raw_status, str):
            raw_status = SubmissionStatus.PENDING.value
        try:
            submission_status = SubmissionStatus(raw_status)
        except ValueError:
            submission_status = SubmissionStatus.PENDING

        email_val = flat.get("email")
        email_out: str | None
        if email_val is None or email_val == "":
            email_out = None
        elif isinstance(email_val, str):
            email_out = email_val
        else:
            email_out = str(email_val)

        return EnrolledStudent(
            student_id=student_id,
            exam_id=exam_id,
            nom=nom,
            prenom=prenom,
            classe=classe,
            email=email_out,
            submission_status=submission_status,
        )
