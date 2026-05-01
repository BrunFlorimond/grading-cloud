"""DynamoDB adapter for exam ownership checks (single-table design)."""

from __future__ import annotations

# TODO(#12): implement ExamOwnershipPort using aiobotocore
#   Key pattern: PK=TEACHER#{teacher_id}  SK=EXAM#{exam_id}
#   Use GetItem and check for item existence — no scan.

import aiobotocore.session

from exam_api.ports.exam_ownership_port import ExamOwnershipPort


class DynamoDbExamOwnershipRepository:
    """Checks teacher-to-exam ownership via the single-table DynamoDB design.

    PK = TEACHER#{teacher_id}
    SK = EXAM#{exam_id}
    """

    def __init__(self, table_name: str, client=None) -> None:
        self._table_name = table_name
        self._client = client  # injected in tests; None triggers real aiobotocore client

    async def teacher_owns_exam(self, *, teacher_id: str, exam_id: str) -> bool:
        # TODO(#12): perform GetItem(Key={PK: TEACHER#{teacher_id}, SK: EXAM#{exam_id}})
        #   Return True iff item exists in the response.
        raise NotImplementedError


# Verify structural compatibility with the port at import time.
_: ExamOwnershipPort = DynamoDbExamOwnershipRepository.__new__(  # type: ignore[assignment]
    DynamoDbExamOwnershipRepository
)
