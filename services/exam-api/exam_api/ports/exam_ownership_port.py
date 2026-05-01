"""Port for verifying that a teacher owns a given exam."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


# TODO(#12): implement DynamoDB adapter that checks PK=TEACHER#{teacher_id} SK=EXAM#{exam_id}
@runtime_checkable
class ExamOwnershipPort(Protocol):
    async def teacher_owns_exam(self, *, teacher_id: str, exam_id: str) -> bool:
        """Return True iff the exam item exists under the teacher's partition key."""
