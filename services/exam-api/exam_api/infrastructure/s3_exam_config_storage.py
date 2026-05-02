"""S3 adapter: pre-signed upload URL generation and config file access."""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable, TypeVar

import aiobotocore.session

from exam_api.ports.exam_config_storage_port import CONFIG_FILES

_UPLOAD_URL_TTL_SECONDS = 900  # 15 minutes

T = TypeVar("T")


class S3ExamConfigStorage:
    """Implements ExamConfigStoragePort using AWS S3.

    S3 key pattern: exams/{exam_id}/config/{filename}
    """

    def __init__(
        self,
        bucket_name: str,
        *,
        session: aiobotocore.session.AioSession | None = None,
        s3_client: Any | None = None,
    ) -> None:
        self._bucket_name = bucket_name
        self._session = session or aiobotocore.session.get_session()
        self._injected_client = s3_client

    def _region_name(self) -> str:
        region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
        if not region:
            raise EnvironmentError("Set AWS_REGION or AWS_DEFAULT_REGION.")
        return region

    async def _use_client(self, fn: Callable[[Any], Awaitable[T]]) -> T:
        if self._injected_client is not None:
            return await fn(self._injected_client)
        async with self._session.create_client(
            "s3", region_name=self._region_name()
        ) as client:
            return await fn(client)

    def _s3_key(self, exam_id: str, filename: str) -> str:
        return f"exams/{exam_id}/config/{filename}"

    async def generate_upload_urls(self, *, exam_id: str) -> dict[str, str]:
        # TODO(#14): for each filename in CONFIG_FILES call client.generate_presigned_url("put_object", Params={Bucket, Key}, ExpiresIn=_UPLOAD_URL_TTL_SECONDS)
        # TODO(#14): return {filename: presigned_url, ...}
        raise NotImplementedError

    async def get_file_bytes(self, *, exam_id: str, filename: str) -> bytes:
        # TODO(#14): client.get_object(Bucket=self._bucket_name, Key=self._s3_key(exam_id, filename))
        # TODO(#14): read and return response["Body"].read()
        # TODO(#14): catch NoSuchKey ClientError → raise ExamConfigMissingFilesError
        raise NotImplementedError

    async def all_files_exist(self, *, exam_id: str) -> dict[str, bool]:
        # TODO(#14): for each filename in CONFIG_FILES, call client.head_object(Bucket=..., Key=...)
        # TODO(#14): success → True; ClientError with 404/NoSuchKey → False
        # TODO(#14): return {filename: bool, ...}
        raise NotImplementedError
