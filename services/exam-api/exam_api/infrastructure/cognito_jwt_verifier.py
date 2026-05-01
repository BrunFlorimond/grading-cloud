"""JWT signature verifier for Cognito ID tokens."""

from __future__ import annotations

from typing import Any

import httpx
from jose import JWTError, jwt


class CognitoJwtVerifier:
    def __init__(self, *, issuer: str, audience: str) -> None:
        self._issuer = issuer.rstrip("/")
        self._audience = audience
        self._jwks_url = f"{self._issuer}/.well-known/jwks.json"
        self._keys_by_kid: dict[str, dict[str, str]] = {}

    def decode_and_verify_token(self, token: str) -> dict[str, Any]:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise JWTError("JWT header does not include a key identifier.")

        key = self._keys_by_kid.get(kid)
        if key is None:
            self._refresh_jwks()
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

    def _refresh_jwks(self) -> None:
        response = httpx.get(self._jwks_url, timeout=5.0)
        response.raise_for_status()
        payload = response.json()
        keys = payload.get("keys")
        if not isinstance(keys, list):
            raise JWTError("Invalid JWKS payload.")
        refreshed: dict[str, dict[str, str]] = {}
        for item in keys:
            if not isinstance(item, dict):
                continue
            kid = item.get("kid")
            if not isinstance(kid, str) or not kid:
                continue
            refreshed[kid] = item
        if not refreshed:
            raise JWTError("JWKS does not include usable signing keys.")
        self._keys_by_kid = refreshed
