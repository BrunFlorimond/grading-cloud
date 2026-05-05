"""JWT signature verifier for Cognito ID tokens."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from jose import JWTError, jwt


class CognitoJwtVerifier:
    """Verifies Cognito JWT tokens using async JWKS fetch (httpx.AsyncClient)."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        # Accept either issuer base URL or full JWKS URL from env/config.
        normalized_issuer = issuer.rstrip("/")
        jwks_suffix = "/.well-known/jwks.json"
        if normalized_issuer.endswith(jwks_suffix):
            normalized_issuer = normalized_issuer[: -len(jwks_suffix)]

        self._issuer = normalized_issuer
        self._audience = audience
        self._jwks_url = f"{self._issuer}/.well-known/jwks.json"
        self._keys_by_kid: dict[str, dict[str, str]] = {}
        self._refresh_lock = asyncio.Lock()
        self._http_client = http_client

    async def decode_and_verify_token(self, token: str) -> dict[str, Any]:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise JWTError("JWT header does not include a key identifier.")

        key = self._keys_by_kid.get(kid)
        if key is None:
            async with self._refresh_lock:
                key = self._keys_by_kid.get(kid)
                if key is None:
                    await self._refresh_jwks()
                    key = self._keys_by_kid.get(kid)
                    if key is None:
                        raise JWTError("Unknown key identifier in JWT header.")

        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=self._audience,
            issuer=self._issuer,
        )
        token_use = claims.get("token_use")
        if token_use != "id":
            raise JWTError("Expected Cognito ID token.")
        return claims

    async def _refresh_jwks(self) -> None:
        if self._http_client is not None:
            response = await self._http_client.get(self._jwks_url)
            self._apply_jwks_response(response)
            return
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(self._jwks_url)
            self._apply_jwks_response(response)

    def _apply_jwks_response(self, response: httpx.Response) -> None:
        response.raise_for_status()
        payload = response.json()
        keys = payload.get("keys")
        if not isinstance(keys, list):
            raise JWTError("Invalid JWKS payload.")
        refreshed: dict[str, dict[str, str]] = {}
        for item in keys:
            if not isinstance(item, dict):
                continue
            item_kid = item.get("kid")
            if not isinstance(item_kid, str) or not item_kid:
                continue
            refreshed[item_kid] = item
        if not refreshed:
            raise JWTError("JWKS does not include usable signing keys.")
        self._keys_by_kid = refreshed
