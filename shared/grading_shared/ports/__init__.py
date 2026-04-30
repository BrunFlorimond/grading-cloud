"""Application ports for grading-cloud adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from grading_shared.domain.events import PipelineEvent
from grading_shared.domain.exam import Exam
from grading_shared.domain.models import NotationPayload


class FileStoragePort(ABC):
    @abstractmethod
    def put_json(self, *, key: str, payload: dict[str, Any]) -> None:
        """Store JSON-serializable data."""

    @abstractmethod
    def get_json(self, *, key: str) -> dict[str, Any]:
        """Fetch JSON-serializable data."""

    @abstractmethod
    def put_binary(self, *, key: str, content: bytes, content_type: str) -> None:
        """Store binary content."""


class ExamRepositoryPort(ABC):
    @abstractmethod
    def save_exam(self, exam: Exam) -> None:
        """Persist an exam aggregate."""

    @abstractmethod
    def get_exam(self, *, exam_id: str) -> Exam | None:
        """Load an exam aggregate by its identifier."""

    @abstractmethod
    def save_notation_payload(
        self, *, exam_id: str, student_id: str, payload: NotationPayload
    ) -> None:
        """Persist a student's notation payload."""


class AIBatchPort(ABC):
    @abstractmethod
    def create_batch(self, *, batch_name: str, requests: list[dict[str, Any]]) -> str:
        """Create an AI batch and return its provider identifier."""

    @abstractmethod
    def get_batch_status(self, *, batch_id: str) -> str:
        """Return provider batch status."""

    @abstractmethod
    def get_batch_results(self, *, batch_id: str) -> list[dict[str, Any]]:
        """Return provider batch results."""


class MessagePublisherPort(ABC):
    @abstractmethod
    def publish_pipeline_event(self, event: PipelineEvent) -> None:
        """Publish a pipeline event."""


class SchedulerPort(ABC):
    @abstractmethod
    def schedule_batch_polling(self, *, batch_id: str, interval_minutes: int) -> str:
        """Create a polling schedule and return schedule identifier."""

    @abstractmethod
    def remove_schedule(self, *, schedule_id: str) -> None:
        """Delete a previously created schedule."""

