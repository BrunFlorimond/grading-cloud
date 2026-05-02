"""Port for pre-signed S3 upload URL generation and config file access."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# Files required for exam configuration; order is not significant.
CONFIG_FILES = ("devoir.json", "correction.json", "prompt.txt", "grille_notation.json")


@runtime_checkable
class ExamConfigStoragePort(Protocol):
    def config_object_key(self, *, exam_id: str, filename: str) -> str:
        """S3 object key for a config file (``exams/{exam_id}/config/{filename}``)."""
        ...

    async def generate_upload_urls(
        self, *, exam_id: str
    ) -> dict[str, dict[str, Any]]:
        """Return a presigned POST bundle per file: ``{url, fields}`` (see S3 API).

        POST policy enforces a max object size; TTL 15 minutes; key prefix
        ``exams/{exam_id}/config/``.
        """
        ...

    async def get_file_bytes(self, *, exam_id: str, filename: str) -> bytes:
        """Fetch the raw bytes of a config file from S3.

        Raises ``ExamConfigMissingFilesError`` when the object is absent.
        """
        ...

    async def all_files_exist(self, *, exam_id: str) -> dict[str, bool]:
        """Return filename → bool indicating S3 presence for each of the 4 config files."""
        ...
