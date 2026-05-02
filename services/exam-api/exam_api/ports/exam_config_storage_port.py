"""Port for pre-signed S3 upload URL generation and config file access."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

# Files required for exam configuration; order is not significant.
CONFIG_FILES = ("devoir.json", "correction.json", "prompt.txt", "grille_notation.json")


@runtime_checkable
class ExamConfigStoragePort(Protocol):
    async def generate_upload_urls(self, *, exam_id: str) -> dict[str, str]:
        """Return pre-signed S3 PUT URLs keyed by filename for each config file.

        # TODO(#14): TTL must be 15 minutes; S3 prefix: exams/{exam_id}/config/
        """
        ...

    async def get_file_bytes(self, *, exam_id: str, filename: str) -> bytes:
        """Fetch the raw bytes of a config file from S3.

        # TODO(#14): raise ExamConfigMissingFilesError when the S3 object is absent.
        """
        ...

    async def all_files_exist(self, *, exam_id: str) -> dict[str, bool]:
        """Return filename → bool indicating S3 presence for each of the 4 config files."""
        ...
