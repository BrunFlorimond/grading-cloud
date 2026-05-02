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
        config_s3_keys: dict[str, str],
    ) -> None:
        """Persist config S3 keys and advance exam status to CONFIGURED.

        # TODO(#14): ExamStatus.CONFIGURED must be added to grading_shared before implementing.
        # TODO(#14): Use a DynamoDB conditional update to prevent overwriting a non-existent exam.
        """
        ...
