"""
Test cases to implement for Issue #9 — Teacher authentication.

All tests should use unittest.mock or moto to mock Cognito — no real AWS calls.
"""

import pytest

# ---------------------------------------------------------------------------
# RegisterTeacherUseCase
# ---------------------------------------------------------------------------

# TODO: test_register_returns_teacher_with_cognito_sub
#   - mock AuthServicePort.register_teacher to return a UUID sub
#   - assert result.teacher.teacher_id == sub
#   - assert result.teacher.email and full_name match command

# TODO: test_register_raises_duplicate_email_error
#   - mock AuthServicePort.register_teacher to raise DuplicateEmailError
#   - assert use case re-raises DuplicateEmailError

# TODO: test_register_raises_weak_password_error
#   - mock AuthServicePort.register_teacher to raise WeakPasswordError
#   - assert use case re-raises WeakPasswordError

# ---------------------------------------------------------------------------
# LoginTeacherUseCase
# ---------------------------------------------------------------------------

# TODO: test_login_returns_auth_tokens
#   - mock AuthServicePort.login_teacher to return AuthTokens
#   - assert result.tokens.id_token, refresh_token, expires_in match

# TODO: test_login_raises_invalid_credentials_error
#   - mock AuthServicePort.login_teacher to raise InvalidCredentialsError
#   - assert use case re-raises InvalidCredentialsError

# ---------------------------------------------------------------------------
# CognitoAuthAdapter
# ---------------------------------------------------------------------------

# TODO: test_cognito_register_calls_sign_up_and_adds_to_group
#   - patch boto3 client with moto or Mock
#   - assert sign_up called with correct username (email) and password
#   - assert admin_add_user_to_group called with "teachers" group
#   - assert admin_update_user_attributes sets custom:role=teacher
#   - assert returned teacher_id == Cognito sub

# TODO: test_cognito_register_maps_username_exists_exception_to_duplicate_email_error
#   - mock boto3 sign_up to raise ClientError(UsernameExistsException)
#   - assert CognitoAuthAdapter.register_teacher raises DuplicateEmailError

# TODO: test_cognito_register_maps_invalid_password_to_weak_password_error
#   - mock boto3 sign_up to raise ClientError(InvalidPasswordException)
#   - assert CognitoAuthAdapter.register_teacher raises WeakPasswordError

# TODO: test_cognito_login_calls_initiate_auth_and_returns_tokens
#   - mock boto3 initiate_auth to return AuthenticationResult with IdToken etc.
#   - assert returned AuthTokens match

# TODO: test_cognito_login_maps_not_authorized_to_invalid_credentials_error
#   - mock boto3 initiate_auth to raise ClientError(NotAuthorizedException)
#   - assert CognitoAuthAdapter.login_teacher raises InvalidCredentialsError

# ---------------------------------------------------------------------------
# API layer (FastAPI TestClient)
# ---------------------------------------------------------------------------

# TODO: test_post_register_201_returns_teacher_id
#   - override get_register_use_case dependency with a mock use case
#   - POST /auth/register with valid payload
#   - assert HTTP 201 and response contains teacher_id, email, full_name

# TODO: test_post_register_409_duplicate_email
#   - override use case to raise DuplicateEmailError
#   - assert HTTP 409

# TODO: test_post_register_400_weak_password
#   - override use case to raise WeakPasswordError with message
#   - assert HTTP 400 and detail message present

# TODO: test_post_login_200_returns_tokens
#   - override get_login_use_case dependency with a mock use case
#   - POST /auth/login with valid payload
#   - assert HTTP 200 and response contains id_token, refresh_token, expires_in

# TODO: test_post_login_401_invalid_credentials
#   - override use case to raise InvalidCredentialsError
#   - assert HTTP 401

# TODO: test_jwt_contains_required_claims
#   - decode id_token (without verification in unit test)
#   - assert claims: custom:role == "teacher", sub present, email present
