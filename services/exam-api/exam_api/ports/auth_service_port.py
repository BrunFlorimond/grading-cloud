"""Port for the authentication service (Cognito)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from grading_shared.domain.models import StrictModel


class AuthTokens(StrictModel):
    """Authentication token bundle returned by Cognito login."""

    id_token: str
    refresh_token: str
    expires_in: int


@runtime_checkable
class AuthServicePort(Protocol):
    async def register_teacher(self, *, email: str, password: str, full_name: str) -> str:
        """Create a Cognito user in the teachers group and return teacher_id (sub)."""
        ...

    async def login_teacher(self, *, email: str, password: str) -> AuthTokens:
        """Authenticate via USER_PASSWORD_AUTH and return JWT tokens."""
        ...
