"""Port for the authentication service (Cognito)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from grading_shared.domain.models import StrictModel


class AuthTokens(StrictModel):
    # TODO: implement AuthTokens value object
    # Fields: id_token (JWT), refresh_token, expires_in (seconds)
    id_token: str
    refresh_token: str
    expires_in: int


@runtime_checkable
class AuthServicePort(Protocol):
    def register_teacher(
        self, *, email: str, password: str, full_name: str
    ) -> str:
        """Create a Cognito user in the teachers group and return teacher_id (sub)."""
        # TODO: implement in CognitoAuthAdapter
        ...

    def login_teacher(self, *, email: str, password: str) -> AuthTokens:
        """Authenticate via USER_PASSWORD_AUTH and return JWT tokens."""
        # TODO: implement in CognitoAuthAdapter
        ...
