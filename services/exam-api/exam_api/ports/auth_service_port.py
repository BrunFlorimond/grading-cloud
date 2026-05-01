"""Port for the authentication service (Cognito)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from grading_shared.domain.models import StrictModel


class AuthTokens(StrictModel):
    """Authentication token bundle returned by Cognito login."""

    id_token: str
    refresh_token: str
    expires_in: int


# TODO(#11): consider a discriminated union (AuthTokens | AuthChallenge) as a
#            single return type for login_student once response shape is agreed.
class AuthChallenge(StrictModel):
    """Represents a Cognito authentication challenge that must be completed."""

    challenge_name: str
    session: str


@runtime_checkable
class AuthServicePort(Protocol):
    async def register_teacher(self, *, email: str, password: str, full_name: str) -> str:
        """Create a Cognito user in the teachers group and return teacher_id (sub)."""
        ...

    async def login_teacher(self, *, email: str, password: str) -> AuthTokens:
        """Authenticate via USER_PASSWORD_AUTH and return JWT tokens."""
        ...

    # TODO(#11): implement — initiate_auth with USER_PASSWORD_AUTH;
    #            if ChallengeName == NEW_PASSWORD_REQUIRED return AuthChallenge,
    #            otherwise return AuthTokens.
    async def login_student(self, *, email: str, password: str) -> AuthTokens | AuthChallenge:
        """Authenticate a student; may return a NEW_PASSWORD_REQUIRED challenge."""
        ...

    # TODO(#11): implement — RespondToAuthChallenge with NEW_PASSWORD_REQUIRED,
    #            return AuthTokens on success.
    async def respond_to_new_password_challenge(
        self, *, email: str, session: str, new_password: str
    ) -> AuthTokens:
        """Complete a NEW_PASSWORD_REQUIRED challenge and return JWT tokens."""
        ...
