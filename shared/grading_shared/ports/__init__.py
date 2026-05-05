"""Application ports for grading-cloud adapters."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from grading_shared.domain.events import PipelineEvent
from grading_shared.domain.exam import Exam
from grading_shared.domain.models import NotationPayload


@runtime_checkable
class FileStoragePort(Protocol):
    def put_json(self, *, key: str, payload: dict[str, Any]) -> None:
        """Store JSON-serializable data."""

    def get_json(self, *, key: str) -> dict[str, Any]:
        """Fetch JSON-serializable data."""

    def put_binary(self, *, key: str, content: bytes, content_type: str) -> None:
        """Store binary content."""


@runtime_checkable
class ExamRepositoryPort(Protocol):
    """Persist and load exam aggregates (async since issue #59).

    Only ``exam-api`` ships an implementation today. Other services must use
    matching ``async def`` methods before calling these APIs from async code.
    """

    async def save_exam(self, exam: Exam) -> None:
        """Persist an exam aggregate."""

    async def get_exam(self, *, exam_id: str) -> Exam | None:
        """Load an exam aggregate by its identifier."""

    async def save_notation_payload(
        self, *, exam_id: str, student_id: str, payload: NotationPayload
    ) -> None:
        """Persist a student's notation payload."""


@runtime_checkable
class AIBatchPort(Protocol):
    def create_batch(self, *, batch_name: str, requests: list[dict[str, Any]]) -> str:
        """Create an AI batch and return its provider identifier."""

    def get_batch_status(self, *, batch_id: str) -> str:
        """Return provider batch status."""

    def get_batch_results(self, *, batch_id: str) -> list[dict[str, Any]]:
        """Return provider batch results."""


@runtime_checkable
class MessagePublisherPort(Protocol):
    def publish_pipeline_event(self, event: PipelineEvent) -> None:
        """Publish a pipeline event."""


@runtime_checkable
class SchedulerPort(Protocol):
    def schedule_batch_polling(self, *, batch_id: str, interval_minutes: int) -> str:
        """Create a polling schedule and return schedule identifier."""

    def remove_schedule(self, *, schedule_id: str) -> None:
        """Delete a previously created schedule."""
