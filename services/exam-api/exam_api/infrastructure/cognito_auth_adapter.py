"""Cognito adapter implementing AuthServicePort."""

from __future__ import annotations

import boto3  # type: ignore[import-untyped]

from exam_api.ports.auth_service_port import AuthServicePort, AuthTokens


class CognitoAuthAdapter:
    """Implements AuthServicePort using AWS Cognito via boto3."""

    def __init__(self, *, user_pool_id: str, client_id: str) -> None:
        # TODO: inject boto3 client to allow mocking in tests
        self._user_pool_id = user_pool_id
        self._client_id = client_id
        self._client = boto3.client("cognito-idp")

    def register_teacher(
        self, *, email: str, password: str, full_name: str
    ) -> str:
        # TODO: call cognito sign_up with email + password
        # TODO: add user to "teachers" group via admin_add_user_to_group
        # TODO: set custom:role=teacher via admin_update_user_attributes
        # TODO: map UsernameExistsException → raise DuplicateEmailError
        # TODO: map InvalidPasswordException → raise WeakPasswordError
        # TODO: return Cognito sub (teacher_id)
        raise NotImplementedError

    def login_teacher(self, *, email: str, password: str) -> AuthTokens:
        # TODO: call initiate_auth with USER_PASSWORD_AUTH flow
        # TODO: extract IdToken + RefreshToken + ExpiresIn from AuthenticationResult
        # TODO: map NotAuthorizedException → raise InvalidCredentialsError
        # TODO: map UserNotFoundException → raise InvalidCredentialsError (no user enumeration)
        # TODO: return AuthTokens value object
        raise NotImplementedError


