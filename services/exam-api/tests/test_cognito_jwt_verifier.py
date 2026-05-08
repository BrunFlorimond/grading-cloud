"""Unit tests for CognitoJwtVerifier."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from jose import JWTError

from exam_api.infrastructure.cognito_jwt_verifier import CognitoJwtVerifier


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


@pytest.mark.asyncio
async def test_decode_and_verify_token_refreshes_jwks_for_unknown_kid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = CognitoJwtVerifier(
        issuer="https://issuer.example.com/pool",
        audience="app-client-id",
    )

    monkeypatch.setattr(
        "exam_api.infrastructure.cognito_jwt_verifier.jwt.get_unverified_header",
        lambda token: {"kid": "kid-1"},
    )
    decode_mock = Mock(
        return_value={
            "sub": "teacher-1",
            "cognito:groups": ["teachers"],
            "token_use": "access",
            "client_id": "app-client-id",
        }
    )
    monkeypatch.setattr(
        "exam_api.infrastructure.cognito_jwt_verifier.jwt.decode",
        decode_mock,
    )
    mock_response = _FakeResponse(
        {
            "keys": [
                {
                    "kid": "kid-1",
                    "kty": "RSA",
                    "alg": "RS256",
                    "use": "sig",
                    "n": "abc",
                    "e": "AQAB",
                }
            ]
        }
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_response)

    class _CM:
        async def __aenter__(self) -> AsyncMock:
            return mock_client

        async def __aexit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(
        "exam_api.infrastructure.cognito_jwt_verifier.httpx.AsyncClient",
        lambda **kwargs: _CM(),
    )

    claims = await verifier.decode_and_verify_token("header.payload.signature")

    assert claims["sub"] == "teacher-1"
    assert decode_mock.call_count == 1


@pytest.mark.asyncio
async def test_decode_and_verify_token_accepts_access_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = CognitoJwtVerifier(
        issuer="https://issuer.example.com/pool",
        audience="app-client-id",
    )
    monkeypatch.setattr(
        "exam_api.infrastructure.cognito_jwt_verifier.jwt.get_unverified_header",
        lambda token: {"kid": "kid-1"},
    )
    mock_response = _FakeResponse(
        {
            "keys": [
                {
                    "kid": "kid-1",
                    "kty": "RSA",
                    "alg": "RS256",
                    "use": "sig",
                    "n": "abc",
                    "e": "AQAB",
                }
            ]
        }
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_response)

    class _CM:
        async def __aenter__(self) -> AsyncMock:
            return mock_client

        async def __aexit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(
        "exam_api.infrastructure.cognito_jwt_verifier.httpx.AsyncClient",
        lambda **kwargs: _CM(),
    )
    monkeypatch.setattr(
        "exam_api.infrastructure.cognito_jwt_verifier.jwt.decode",
        lambda *args, **kwargs: {
            "token_use": "access",
            "client_id": "app-client-id",
            "sub": "teacher-1",
        },
    )

    claims = await verifier.decode_and_verify_token("header.payload.signature")
    assert claims["token_use"] == "access"


@pytest.mark.asyncio
async def test_decode_and_verify_token_rejects_id_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = CognitoJwtVerifier(
        issuer="https://issuer.example.com/pool",
        audience="app-client-id",
    )
    monkeypatch.setattr(
        "exam_api.infrastructure.cognito_jwt_verifier.jwt.get_unverified_header",
        lambda token: {"kid": "kid-1"},
    )
    mock_response = _FakeResponse(
        {
            "keys": [
                {
                    "kid": "kid-1",
                    "kty": "RSA",
                    "alg": "RS256",
                    "use": "sig",
                    "n": "abc",
                    "e": "AQAB",
                }
            ]
        }
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_response)

    class _CM:
        async def __aenter__(self) -> AsyncMock:
            return mock_client

        async def __aexit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(
        "exam_api.infrastructure.cognito_jwt_verifier.httpx.AsyncClient",
        lambda **kwargs: _CM(),
    )
    monkeypatch.setattr(
        "exam_api.infrastructure.cognito_jwt_verifier.jwt.decode",
        lambda *args, **kwargs: {
            "token_use": "id",
            "aud": "app-client-id",
            "sub": "teacher-1",
        },
    )

    with pytest.raises(JWTError, match="Expected Cognito access token"):
        await verifier.decode_and_verify_token("header.payload.signature")


@pytest.mark.asyncio
async def test_decode_and_verify_token_fails_when_kid_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = CognitoJwtVerifier(
        issuer="https://issuer.example.com/pool",
        audience="app-client-id",
    )
    monkeypatch.setattr(
        "exam_api.infrastructure.cognito_jwt_verifier.jwt.get_unverified_header",
        lambda token: {"kid": "kid-missing"},
    )
    mock_response = _FakeResponse({"keys": []})
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_response)

    class _CM:
        async def __aenter__(self) -> AsyncMock:
            return mock_client

        async def __aexit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(
        "exam_api.infrastructure.cognito_jwt_verifier.httpx.AsyncClient",
        lambda **kwargs: _CM(),
    )

    with pytest.raises(JWTError):
        await verifier.decode_and_verify_token("header.payload.signature")


@pytest.mark.asyncio
async def test_jwks_refresh_called_once_for_concurrent_unknown_kid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = CognitoJwtVerifier(
        issuer="https://issuer.example.com/pool",
        audience="app-client-id",
    )
    monkeypatch.setattr(
        "exam_api.infrastructure.cognito_jwt_verifier.jwt.get_unverified_header",
        lambda token: {"kid": "kid-new"},
    )
    decode_mock = Mock(
        return_value={
            "sub": "u",
            "token_use": "access",
            "client_id": "app-client-id",
        }
    )
    monkeypatch.setattr(
        "exam_api.infrastructure.cognito_jwt_verifier.jwt.decode",
        decode_mock,
    )

    mock_response = _FakeResponse(
        {
            "keys": [
                {
                    "kid": "kid-new",
                    "kty": "RSA",
                    "alg": "RS256",
                    "use": "sig",
                    "n": "abc",
                    "e": "AQAB",
                }
            ]
        }
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_response)

    class _CM:
        async def __aenter__(self) -> AsyncMock:
            return mock_client

        async def __aexit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(
        "exam_api.infrastructure.cognito_jwt_verifier.httpx.AsyncClient",
        lambda **kwargs: _CM(),
    )

    await asyncio.gather(
        verifier.decode_and_verify_token("t1"),
        verifier.decode_and_verify_token("t2"),
    )

    assert mock_client.get.await_count == 1
