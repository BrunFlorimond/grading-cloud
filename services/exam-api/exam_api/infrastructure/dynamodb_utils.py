"""Shared DynamoDB attribute (de)serialization for exam-related adapters."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from grading_shared.domain.exam import Exam, ExamStatus

TS_PREFIX = "TS#"


def ddb_deserialize(attr: dict[str, Any]) -> Any:
    if len(attr) != 1:
        raise ValueError(f"Expected exactly one type key in AttributeValue, got {attr!r}")
    key, val = next(iter(attr.items()))
    if key == "S":
        return val
    if key == "N":
        return Decimal(val)
    if key == "BOOL":
        return bool(val)
    if key == "NULL":
        return None
    if key == "M":
        if not isinstance(val, dict):
            raise TypeError("Invalid DynamoDB M value")
        return {k: ddb_deserialize(v) for k, v in val.items()}
    if key == "L":
        if not isinstance(val, list):
            raise TypeError("Invalid DynamoDB L value")
        return [ddb_deserialize(v) for v in val]
    raise ValueError(f"Unsupported DynamoDB attribute type {key!r}")


def ddb_serialize(value: Any) -> dict[str, Any]:
    if value is None:
        return {"NULL": True}
    if isinstance(value, bool):
        return {"BOOL": value}
    if isinstance(value, str):
        return {"S": value}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"N": str(value)}
    if isinstance(value, Decimal):
        return {"N": format(value, "f")}
    if isinstance(value, float):
        return {"N": format(Decimal(str(value)), "f")}
    if isinstance(value, dict):
        return {"M": {k: ddb_serialize(v) for k, v in value.items()}}
    if isinstance(value, list):
        return {"L": [ddb_serialize(v) for v in value]}
    if isinstance(value, tuple):
        return {"L": [ddb_serialize(v) for v in value]}
    raise TypeError(f"Unsupported Python type for DynamoDB encoding: {type(value)!r}")


def deserialize_item(item: dict[str, Any]) -> dict[str, Any]:
    return {k: ddb_deserialize(v) for k, v in item.items()}


def exam_from_dynamodb_flat(flat: dict[str, Any]) -> Exam | None:
    """Build an ``Exam`` from denormalized DynamoDB attributes (sort edge or METADATA + exam_id)."""
    exam_id = flat.get("exam_id")
    teacher_id = flat.get("teacher_id")
    title = flat.get("title")
    if not isinstance(exam_id, str) or not exam_id:
        return None
    if not isinstance(teacher_id, str) or not teacher_id:
        return None
    if not isinstance(title, str) or not title:
        return None

    raw_status = flat.get("status", ExamStatus.DRAFT.value)
    if not isinstance(raw_status, str):
        raw_status = ExamStatus.DRAFT.value
    try:
        status = ExamStatus(raw_status)
    except ValueError:
        status = ExamStatus.DRAFT

    description = flat.get("description")
    if description is not None and not isinstance(description, str):
        description = None
    subject = flat.get("subject")
    if subject is not None and not isinstance(subject, str):
        subject = None
    created_at = flat.get("created_at")
    if created_at is not None and not isinstance(created_at, str):
        created_at = None

    return Exam(
        exam_id=exam_id,
        teacher_id=teacher_id,
        title=title,
        status=status,
        description=description,
        subject=subject,
        created_at=created_at,
    )
