"""Domain errors for teacher authentication flows."""

from __future__ import annotations


class AuthError(Exception):
    """Base class for authentication-related domain errors."""


class DuplicateEmailError(AuthError):
    """Raised when a teacher tries to register with an existing email."""


class WeakPasswordError(AuthError):
    """Raised when a teacher password does not match policy constraints."""


class InvalidCredentialsError(AuthError):
    """Raised when login credentials are invalid."""


# TODO(#10): review whether InviteError should extend a broader DomainError base
class InviteError(Exception):
    """Base class for student invitation errors."""


class ExamNotFoundError(InviteError):
    """Raised when the target exam does not exist."""


class ExamOwnershipError(InviteError):
    """Raised when the requesting teacher does not own the exam."""


class StudentAlreadyInvitedError(InviteError):
    """Raised when the student has already been invited; re-invite re-sends the email."""


class StudentExamScopeConflictError(InviteError):
    """Raised when an existing student account is bound to another exam scope."""


# TODO(#11): add StudentAuthError subtypes if needed (e.g. ChallengeExpiredError)
class StudentAuthError(Exception):
    """Base class for student authentication errors."""


class PasswordChallengeRequiredError(StudentAuthError):
    """Raised when Cognito requires a NEW_PASSWORD_REQUIRED challenge on login."""

    def __init__(self, session: str) -> None:
        super().__init__("Password change required.")
        # TODO(#11): decide whether to keep session here or in the result model
        self.session = session
