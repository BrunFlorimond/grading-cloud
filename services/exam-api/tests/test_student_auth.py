"""Tests for student login and password-change flows (issue #11).

All test cases below are stubs — implement them after the use cases and adapter
methods in TODO(#11) are filled in.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# LoginStudentUseCase
# ---------------------------------------------------------------------------

# TODO(#11): test — student login with valid temporary password returns
#            LoginStudentResult with challenge set to AuthChallenge(NEW_PASSWORD_REQUIRED)
#            and tokens=None.
@pytest.mark.asyncio
async def test_login_student_returns_new_password_required_challenge() -> None:
    pytest.skip("TODO(#11): implement")


# TODO(#11): test — student login with correct permanent password (after reset)
#            returns LoginStudentResult with tokens set and challenge=None.
@pytest.mark.asyncio
async def test_login_student_returns_tokens_on_normal_auth() -> None:
    pytest.skip("TODO(#11): implement")


# TODO(#11): test — student login with wrong password raises InvalidCredentialsError.
@pytest.mark.asyncio
async def test_login_student_invalid_credentials_raises_error() -> None:
    pytest.skip("TODO(#11): implement")


# ---------------------------------------------------------------------------
# ChangeStudentPasswordUseCase
# ---------------------------------------------------------------------------

# TODO(#11): test — change password with valid session and strong new_password
#            returns ChangeStudentPasswordResult with AuthTokens.
@pytest.mark.asyncio
async def test_change_student_password_returns_tokens() -> None:
    pytest.skip("TODO(#11): implement")


# TODO(#11): test — change password with expired/invalid session raises
#            InvalidCredentialsError.
@pytest.mark.asyncio
async def test_change_student_password_invalid_session_raises_error() -> None:
    pytest.skip("TODO(#11): implement")


# TODO(#11): test — change password with weak new_password raises WeakPasswordError.
@pytest.mark.asyncio
async def test_change_student_password_weak_password_raises_error() -> None:
    pytest.skip("TODO(#11): implement")


# ---------------------------------------------------------------------------
# CognitoAuthAdapter — login_student
# ---------------------------------------------------------------------------

# TODO(#11): test — adapter.login_student() calls initiate_auth with
#            USER_PASSWORD_AUTH; when Cognito returns ChallengeName=NEW_PASSWORD_REQUIRED
#            the adapter returns AuthChallenge with session token.
@pytest.mark.asyncio
async def test_cognito_adapter_login_student_returns_challenge() -> None:
    pytest.skip("TODO(#11): implement")


# TODO(#11): test — adapter.login_student() returns AuthTokens when Cognito
#            returns AuthenticationResult directly (no challenge).
@pytest.mark.asyncio
async def test_cognito_adapter_login_student_returns_tokens() -> None:
    pytest.skip("TODO(#11): implement")


# TODO(#11): test — adapter.login_student() maps NotAuthorizedException →
#            InvalidCredentialsError.
@pytest.mark.asyncio
async def test_cognito_adapter_login_student_maps_not_authorized() -> None:
    pytest.skip("TODO(#11): implement")


# ---------------------------------------------------------------------------
# CognitoAuthAdapter — respond_to_new_password_challenge
# ---------------------------------------------------------------------------

# TODO(#11): test — adapter.respond_to_new_password_challenge() calls
#            respond_to_auth_challenge with correct parameters and returns AuthTokens.
@pytest.mark.asyncio
async def test_cognito_adapter_respond_to_challenge_returns_tokens() -> None:
    pytest.skip("TODO(#11): implement")


# TODO(#11): test — adapter.respond_to_new_password_challenge() maps
#            InvalidPasswordException → WeakPasswordError.
@pytest.mark.asyncio
async def test_cognito_adapter_respond_to_challenge_maps_weak_password() -> None:
    pytest.skip("TODO(#11): implement")


# TODO(#11): test — adapter.respond_to_new_password_challenge() maps
#            NotAuthorizedException → InvalidCredentialsError (expired session).
@pytest.mark.asyncio
async def test_cognito_adapter_respond_to_challenge_maps_not_authorized() -> None:
    pytest.skip("TODO(#11): implement")


# ---------------------------------------------------------------------------
# API — POST /auth/student-login
# ---------------------------------------------------------------------------

# TODO(#11): test — POST /auth/student-login with temporary password returns
#            200 with {challenge_name: "NEW_PASSWORD_REQUIRED", session: "..."}.
def test_api_student_login_returns_challenge() -> None:
    pytest.skip("TODO(#11): implement")


# TODO(#11): test — POST /auth/student-login with correct permanent password
#            returns 200 with {id_token, refresh_token, expires_in}.
def test_api_student_login_returns_tokens() -> None:
    pytest.skip("TODO(#11): implement")


# TODO(#11): test — POST /auth/student-login with wrong credentials returns 401.
def test_api_student_login_invalid_credentials_returns_401() -> None:
    pytest.skip("TODO(#11): implement")


# ---------------------------------------------------------------------------
# API — POST /auth/change-password
# ---------------------------------------------------------------------------

# TODO(#11): test — POST /auth/change-password with valid session + strong password
#            returns 200 with {id_token, refresh_token, expires_in}.
def test_api_change_password_returns_tokens() -> None:
    pytest.skip("TODO(#11): implement")


# TODO(#11): test — POST /auth/change-password with invalid/expired session
#            returns 401.
def test_api_change_password_invalid_session_returns_401() -> None:
    pytest.skip("TODO(#11): implement")


# TODO(#11): test — POST /auth/change-password with weak new_password returns 400.
def test_api_change_password_weak_password_returns_400() -> None:
    pytest.skip("TODO(#11): implement")


# ---------------------------------------------------------------------------
# JWT claims validation
# ---------------------------------------------------------------------------

# TODO(#11): test — JWT returned after password change contains
#            custom:role=student, sub, email, custom:exam_id claims.
def test_student_jwt_contains_required_claims() -> None:
    pytest.skip("TODO(#11): implement")
