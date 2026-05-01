"""JWT signature verifier for Cognito ID tokens."""

from __future__ import annotations

import threading
from typing import Any

# TODO(#59): replace httpx.get (blocking) with httpx.AsyncClient in _refresh_jwks
import httpx
from jose import JWTError, jwt


class CognitoJwtVerifier:
    """Verifies Cognito JWT tokens.

    TODO(#59): migrate to fully async:
    - Replace threading.Lock with asyncio.Lock
    - Replace httpx.get with await httpx.AsyncClient().get in _refresh_jwks
    - Update FastAPI dependencies (get_current_teacher, get_current_student) to async def
    """

    def __init__(self, *, issuer: str, audience: str) -> None:
        self._issuer = issuer.rstrip("/")
        self._audience = audience
        self._jwks_url = f"{self._issuer}/.well-known/jwks.json"
        self._keys_by_kid: dict[str, dict[str, str]] = {}
        # TODO(#59): replace threading.Lock with asyncio.Lock once method is async
        self._refresh_lock = threading.Lock()

    # TODO(#59): convert to async def — update all FastAPI dependencies that call this method
    async def decode_and_verify_token(self, token: str) -> dict[str, Any]:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise JWTError("JWT header does not include a key identifier.")

        key = self._keys_by_kid.get(kid)
        if key is None:
            # TODO(#59): replace with asyncio.Lock and await self._refresh_jwks()
            with self._refresh_lock:
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

    # TODO(#59): convert to async def _refresh_jwks using httpx.AsyncClient
    def _refresh_jwks(self) -> None:
        # TODO(#59): replace with:
        #   async with httpx.AsyncClient() as client:
        #       response = await client.get(self._jwks_url, timeout=5.0)
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
