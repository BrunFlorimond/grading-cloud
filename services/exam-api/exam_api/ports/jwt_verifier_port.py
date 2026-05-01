"""Port for verifying teacher JWT tokens."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class JwtVerifierPort(Protocol):
    async def decode_and_verify_token(self, token: str) -> dict[str, Any]:
        """Decode and verify a Cognito JWT, returning claims."""
