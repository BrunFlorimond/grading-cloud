"""Port for reading and updating exam configuration status in DynamoDB."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from grading_shared.domain.exam import Exam


@runtime_checkable
class ExamConfigRepositoryPort(Protocol):
    async def get_exam_for_config(self, *, exam_id: str) -> Exam | None:
        """Load exam aggregate from PK=EXAM#{exam_id}, SK=METADATA; None if absent."""
        ...

    async def save_exam_config(
        self,
        *,
        exam_id: str,
        teacher_id: str,
        created_at: str,
        config_s3_keys: dict[str, str],
    ) -> None:
        """Persist config S3 keys and set exam status to CONFIGURED.

        ``teacher_id`` and ``created_at`` must match the exam loaded by the caller (avoids a
        redundant DynamoDB read). Uses conditional updates so phantom writes and stale-status
        races fail cleanly.
        """
        ...
