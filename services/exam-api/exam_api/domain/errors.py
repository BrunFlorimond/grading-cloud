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
