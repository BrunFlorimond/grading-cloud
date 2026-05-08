"""Port for the authentication service (Cognito)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from grading_shared.domain.models import StrictModel


class AuthTokens(StrictModel):
    """Authentication token bundle returned by Cognito login."""

    access_token: str
    id_token: str
    refresh_token: str
    expires_in: int


class AuthChallenge(StrictModel):
    """Represents a Cognito authentication challenge that must be completed."""

    challenge_name: str
    session: str


@runtime_checkable
class AuthServicePort(Protocol):
    async def register_teacher(
        self, *, email: str, password: str, full_name: str
    ) -> str:
        """Create a Cognito user in the teachers group and return teacher_id (sub)."""
        ...

    async def login_teacher(self, *, email: str, password: str) -> AuthTokens:
        """Authenticate via USER_PASSWORD_AUTH and return JWT tokens."""
        ...

    async def login_student(
        self, *, email: str, password: str
    ) -> AuthTokens | AuthChallenge:
        """Authenticate a student; may return a NEW_PASSWORD_REQUIRED challenge."""
        ...

    async def respond_to_new_password_challenge(
        self, *, email: str, session: str, new_password: str
    ) -> AuthTokens:
        """Complete a NEW_PASSWORD_REQUIRED challenge and return JWT tokens."""
        ...
