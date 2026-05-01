"""Port for verifying teacher JWT tokens."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class JwtVerifierPort(Protocol):
    def decode_teacher_token(self, token: str) -> dict[str, Any]:
        """Decode and verify a teacher JWT, returning claims."""
