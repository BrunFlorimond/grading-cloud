"""S3 adapter: pre-signed upload URL generation and config file access."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Awaitable, Callable, TypeVar

import aiobotocore.session
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from exam_api.domain.errors import ExamConfigMissingFilesError
from exam_api.infrastructure.aws_client_config import build_client_kwargs
from exam_api.ports.exam_config_storage_port import CONFIG_FILES

_UPLOAD_URL_TTL_SECONDS = 900  # 15 minutes
# Per-file cap for config uploads (DoS / cost control) via presigned POST policy.
_MAX_CONFIG_FILE_BYTES = 10 * 1024 * 1024

T = TypeVar("T")


def _is_not_found(err: ClientError) -> bool:
    code = str(err.response.get("Error", {}).get("Code", ""))
    return code in {"404", "NoSuchKey", "NotFound"}


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
        kwargs = build_client_kwargs("s3")
        if "region_name" not in kwargs:
            kwargs["region_name"] = self._region_name()
        async with self._session.create_client("s3", **kwargs) as client:
            return await fn(client)

    def config_object_key(self, *, exam_id: str, filename: str) -> str:
        return f"exams/{exam_id}/config/{filename}"

    async def generate_upload_urls(self, *, exam_id: str) -> dict[str, dict[str, Any]]:
        async def _post_one(client: Any, filename: str) -> tuple[str, dict[str, Any]]:
            key = self.config_object_key(exam_id=exam_id, filename=filename)
            post = await client.generate_presigned_post(
                self._bucket_name,
                key,
                Fields={"key": key},
                Conditions=[
                    ["eq", "$key", key],
                    ["content-length-range", 0, _MAX_CONFIG_FILE_BYTES],
                ],
                ExpiresIn=_UPLOAD_URL_TTL_SECONDS,
            )
            return filename, post

        async def _run(client: Any) -> dict[str, dict[str, Any]]:
            pairs = await asyncio.gather(
                *[_post_one(client, fn) for fn in CONFIG_FILES]
            )
            return dict(pairs)

        return await self._use_client(_run)

    async def get_file_bytes(self, *, exam_id: str, filename: str) -> bytes:
        key = self.config_object_key(exam_id=exam_id, filename=filename)

        async def _get(client: Any) -> bytes:
            try:
                response = await client.get_object(
                    Bucket=self._bucket_name,
                    Key=key,
                )
            except ClientError as err:
                if _is_not_found(err):
                    raise ExamConfigMissingFilesError([filename]) from err
                raise
            body = response["Body"]
            return await body.read()

        return await self._use_client(_get)

    async def all_files_exist(self, *, exam_id: str) -> dict[str, bool]:
        async def _head_one(client: Any, filename: str) -> tuple[str, bool]:
            key = self.config_object_key(exam_id=exam_id, filename=filename)
            try:
                await client.head_object(Bucket=self._bucket_name, Key=key)
                return filename, True
            except ClientError as err:
                if _is_not_found(err):
                    return filename, False
                raise

        async def _head_all(client: Any) -> dict[str, bool]:
            pairs = await asyncio.gather(
                *[_head_one(client, fn) for fn in CONFIG_FILES]
            )
            return dict(pairs)

        return await self._use_client(_head_all)
