"""Common aiobotocore client configuration for AWS and LocalStack."""

from __future__ import annotations

import os


def _service_env_prefix(service_name: str) -> str:
    return service_name.replace("-", "_").upper()


def build_client_kwargs(service_name: str) -> dict[str, object]:
    """Build kwargs for aiobotocore session.create_client.

    Supports LocalStack by honoring either:
    - ``AWS_<SERVICE>_ENDPOINT_URL`` (service-specific), or
    - ``AWS_ENDPOINT_URL`` (global fallback).
    """
    kwargs: dict[str, object] = {}

    service_prefix = _service_env_prefix(service_name)
    endpoint_url = os.getenv(f"AWS_{service_prefix}_ENDPOINT_URL") or os.getenv(
        "AWS_ENDPOINT_URL"
    )

    region_name = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")

    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
        kwargs["region_name"] = region_name or "us-east-1"
        kwargs["aws_access_key_id"] = os.getenv("AWS_ACCESS_KEY_ID", "test")
        kwargs["aws_secret_access_key"] = os.getenv("AWS_SECRET_ACCESS_KEY", "test")
        return kwargs

    if region_name:
        kwargs["region_name"] = region_name

    return kwargs
