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


class ExamValidationError(Exception):
    """Base class for exam creation validation errors."""


class ExamTitleRequiredError(ExamValidationError):
    """Raised when the exam title is missing or empty."""


class ExamTitleTooLongError(ExamValidationError):
    """Raised when the exam title exceeds the maximum allowed length (120 chars)."""


class ExamCreationConflictError(ExamValidationError):
    """Raised when persisting a new exam hits a conditional write conflict (e.g. duplicate PK)."""


class InvalidExamListCursorError(ExamValidationError):
    """Raised when the pagination cursor cannot be applied to DynamoDB."""


class ExamConfigError(Exception):
    """Base class for exam configuration errors."""


class ExamConfigMissingFilesError(ExamConfigError):
    """Raised when one or more required config files are absent from S3."""

    def __init__(self, missing_filenames: list[str]) -> None:
        self.missing_filenames = list(missing_filenames)
        joined = ", ".join(missing_filenames)
        super().__init__(f"Missing config files: {joined}")


class ExamConfigInvalidJsonError(ExamConfigError):
    """Raised when a .json config file cannot be parsed as valid JSON."""

    def __init__(self, filename: str, parse_error: str) -> None:
        self.filename = filename
        self.parse_error = parse_error
        super().__init__(f"Invalid JSON in {filename}: {parse_error}")


class ExamConfigWrongStatusError(ExamConfigError):
    """Raised when the exam status does not allow configuration uploads."""
