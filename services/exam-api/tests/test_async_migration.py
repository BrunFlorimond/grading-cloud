"""Test stubs for async migration (issue #59).

TODO(#59): implement each test case below once the corresponding adapter/use case
has been migrated to aiobotocore / httpx.AsyncClient.

All tests must use async mocks (AsyncMock or pytest-asyncio) — no run_in_threadpool,
no asyncio.to_thread in the production paths under test.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# CognitoAuthAdapter (async — aiobotocore)
# ---------------------------------------------------------------------------
# TODO(#59): test_register_teacher_success
#   Given a mocked aiobotocore cognito-idp client,
#   when register_teacher is awaited,
#   then sign_up / admin_add_user_to_group / admin_update_user_attributes are called
#   and the returned teacher_id equals the mocked UserSub.

# TODO(#59): test_register_teacher_duplicate_email
#   Given an aiobotocore client that raises UsernameExistsException,
#   then register_teacher raises DuplicateEmailError.

# TODO(#59): test_register_teacher_weak_password
#   Given an aiobotocore client that raises InvalidPasswordException,
#   then register_teacher raises WeakPasswordError.

# TODO(#59): test_login_teacher_success
#   Given a mocked aiobotocore cognito-idp client returning AuthenticationResult,
#   when login_teacher is awaited,
#   then LoginTeacherResult contains the expected id_token, refresh_token, expires_in.

# TODO(#59): test_login_teacher_invalid_credentials
#   Given an aiobotocore client that raises NotAuthorizedException,
#   then login_teacher raises InvalidCredentialsError.

# ---------------------------------------------------------------------------
# CognitoJwtVerifier (async — httpx.AsyncClient)
# ---------------------------------------------------------------------------
# TODO(#59): test_decode_and_verify_token_success
#   Given a mocked httpx.AsyncClient that returns a valid JWKS payload,
#   when decode_and_verify_token is awaited with a valid RS256 JWT,
#   then the returned claims dict contains the expected sub and token_use="id".

# TODO(#59): test_decode_and_verify_token_unknown_kid
#   Given a JWKS that does not contain the key matching the JWT header kid,
#   then decode_and_verify_token raises JWTError("Unknown key identifier").

# TODO(#59): test_decode_and_verify_token_wrong_token_use
#   Given a JWT with token_use != "id",
#   then decode_and_verify_token raises JWTError("Expected Cognito ID token.").

# TODO(#59): test_jwks_refresh_called_once_per_unknown_kid
#   Given two concurrent awaits on decode_and_verify_token with the same unknown kid,
#   then _refresh_jwks is called exactly once (asyncio.Lock prevents double refresh).

# ---------------------------------------------------------------------------
# RegisterTeacherUseCase (async execute)
# ---------------------------------------------------------------------------
# TODO(#59): test_register_use_case_async_execute_success
#   Given an AsyncMock AuthServicePort.register_teacher returning a teacher_id,
#   when use_case.execute is awaited,
#   then RegisterTeacherResult.teacher.teacher_id equals the mocked id.

# TODO(#59): test_register_use_case_propagates_duplicate_email_error
#   Given an AsyncMock that raises DuplicateEmailError,
#   then execute re-raises DuplicateEmailError.

# ---------------------------------------------------------------------------
# LoginTeacherUseCase (async execute)
# ---------------------------------------------------------------------------
# TODO(#59): test_login_use_case_async_execute_success
#   Given an AsyncMock AuthServicePort.login_teacher returning AuthTokens,
#   when use_case.execute is awaited,
#   then LoginTeacherResult.tokens matches the mocked AuthTokens.

# TODO(#59): test_login_use_case_propagates_invalid_credentials_error
#   Given an AsyncMock that raises InvalidCredentialsError,
#   then execute re-raises InvalidCredentialsError.

# ---------------------------------------------------------------------------
# POST /auth/register endpoint (no run_in_threadpool)
# ---------------------------------------------------------------------------
# TODO(#59): test_register_endpoint_returns_201
#   Given an AsyncMock use case returning RegisterTeacherResult,
#   POST /auth/register with valid payload returns HTTP 201 and RegisterResponse JSON.

# TODO(#59): test_register_endpoint_returns_409_on_duplicate
#   Given an AsyncMock use case raising DuplicateEmailError,
#   POST /auth/register returns HTTP 409.

# TODO(#59): test_register_endpoint_returns_400_on_weak_password
#   Given an AsyncMock use case raising WeakPasswordError,
#   POST /auth/register returns HTTP 400.

# ---------------------------------------------------------------------------
# POST /auth/login endpoint (no run_in_threadpool)
# ---------------------------------------------------------------------------
# TODO(#59): test_login_endpoint_returns_200
#   Given an AsyncMock use case returning LoginTeacherResult,
#   POST /auth/login with valid payload returns HTTP 200 and LoginResponse JSON.

# TODO(#59): test_login_endpoint_returns_401_on_invalid_credentials
#   Given an AsyncMock use case raising InvalidCredentialsError,
#   POST /auth/login returns HTTP 401.

# ---------------------------------------------------------------------------
# CognitoSesStudentInviteAdapter (aiobotocore — remove asyncio.to_thread)
# ---------------------------------------------------------------------------
# TODO(#59): test_invite_student_new_account_no_thread_wrapping
#   Given mocked aiobotocore cognito and ses clients,
#   when invite_student is awaited,
#   then admin_create_user, admin_add_user_to_group, send_email are all awaited
#   directly (no asyncio.to_thread in call stack).

# TODO(#59): test_invite_student_existing_account
#   Given aiobotocore cognito that raises UsernameExistsException on admin_create_user,
#   then the adapter falls back to admin_get_user path and still returns
#   InviteStudentResult(already_existed=True).

# ---------------------------------------------------------------------------
# DynamoDbInviteRepository (aiobotocore — remove asyncio.to_thread)
# ---------------------------------------------------------------------------
# TODO(#59): test_get_exam_async_no_thread_wrapping
#   Given a mocked aiobotocore DynamoDB client,
#   when get_exam is awaited,
#   then get_item is awaited directly (no asyncio.to_thread).

# TODO(#59): test_upsert_student_scope_async_no_thread_wrapping
#   Given a mocked aiobotocore client,
#   when upsert_student_scope is awaited,
#   then transact_write_items is awaited directly.

# TODO(#59): test_upsert_student_scope_conflict_raises_error
#   Given aiobotocore raises TransactionCanceledException with ConditionalCheckFailed,
#   then upsert_student_scope raises StudentExamScopeConflictError.
