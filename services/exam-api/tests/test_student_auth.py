"""Tests for student login and password-change flows (issue #11)."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, Mock

import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from exam_api.api.auth_router import (
    get_change_password_use_case,
    get_login_student_use_case,
    router,
)
from exam_api.api.http_error_handlers import register_http_error_handlers
from exam_api.application.change_student_password import (
    ChangeStudentPasswordCommand,
    ChangeStudentPasswordResult,
    ChangeStudentPasswordUseCase,
)
from exam_api.application.login_student import (
    LoginStudentCommand,
    LoginStudentResult,
    LoginStudentUseCase,
)
from exam_api.domain.errors import InvalidCredentialsError, WeakPasswordError
from exam_api.infrastructure.cognito_auth_adapter import CognitoAuthAdapter
from exam_api.ports.auth_service_port import AuthChallenge, AuthTokens


def _make_client_error(code: str, message: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": message}},
        operation_name="CognitoAction",
    )


def _encode_segment(payload: dict[str, str]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _decode_jwt_payload(token: str) -> dict[str, str]:
    payload_segment = token.split(".")[1]
    missing_padding = len(payload_segment) % 4
    if missing_padding:
        payload_segment += "=" * (4 - missing_padding)
    decoded = base64.urlsafe_b64decode(payload_segment.encode("utf-8"))
    return json.loads(decoded.decode("utf-8"))


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_http_error_handlers(app)
    app.include_router(router)
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_login_student_returns_new_password_required_challenge() -> None:
    auth = Mock()
    auth.login_student = AsyncMock(
        return_value=AuthChallenge(
            challenge_name="NEW_PASSWORD_REQUIRED",
            session="cognito-session-token",
        )
    )
    use_case = LoginStudentUseCase(auth_service=auth)

    result = await use_case.execute(
        LoginStudentCommand(email="student@school.edu", password="TempPass123!")
    )

    assert result.tokens is None
    assert result.challenge is not None
    assert result.challenge.challenge_name == "NEW_PASSWORD_REQUIRED"
    assert result.challenge.session == "cognito-session-token"


@pytest.mark.asyncio
async def test_login_student_returns_tokens_on_normal_auth() -> None:
    auth = Mock()
    auth.login_student = AsyncMock(
        return_value=AuthTokens(
            id_token="id.jwt.token",
            refresh_token="refresh.token",
            expires_in=3600,
        )
    )
    use_case = LoginStudentUseCase(auth_service=auth)

    result = await use_case.execute(
        LoginStudentCommand(email="student@school.edu", password="StrongPassword123!")
    )

    assert result.challenge is None
    assert result.tokens is not None
    assert result.tokens.id_token == "id.jwt.token"


@pytest.mark.asyncio
async def test_login_student_invalid_credentials_raises_error() -> None:
    auth = Mock()
    auth.login_student = AsyncMock(side_effect=InvalidCredentialsError("invalid"))
    use_case = LoginStudentUseCase(auth_service=auth)

    with pytest.raises(InvalidCredentialsError):
        await use_case.execute(
            LoginStudentCommand(email="student@school.edu", password="wrong")
        )


@pytest.mark.asyncio
async def test_change_student_password_returns_tokens() -> None:
    auth = Mock()
    auth.respond_to_new_password_challenge = AsyncMock(
        return_value=AuthTokens(
            id_token="id.after.change",
            refresh_token="refresh.after",
            expires_in=3600,
        )
    )
    use_case = ChangeStudentPasswordUseCase(auth_service=auth)

    result = await use_case.execute(
        ChangeStudentPasswordCommand(
            email="student@school.edu",
            session="cognito-session-token",
            new_password="NewStrongPassword123!",
        )
    )

    assert result.tokens.id_token == "id.after.change"
    auth.respond_to_new_password_challenge.assert_awaited_once_with(
        email="student@school.edu",
        session="cognito-session-token",
        new_password="NewStrongPassword123!",
    )


@pytest.mark.asyncio
async def test_change_student_password_invalid_session_raises_error() -> None:
    auth = Mock()
    auth.respond_to_new_password_challenge = AsyncMock(
        side_effect=InvalidCredentialsError("invalid session")
    )
    use_case = ChangeStudentPasswordUseCase(auth_service=auth)

    with pytest.raises(InvalidCredentialsError):
        await use_case.execute(
            ChangeStudentPasswordCommand(
                email="student@school.edu",
                session="invalid-session",
                new_password="NewStrongPassword123!",
            )
        )


@pytest.mark.asyncio
async def test_change_student_password_weak_password_raises_error() -> None:
    auth = Mock()
    auth.respond_to_new_password_challenge = AsyncMock(
        side_effect=WeakPasswordError("too short")
    )
    use_case = ChangeStudentPasswordUseCase(auth_service=auth)

    with pytest.raises(WeakPasswordError):
        await use_case.execute(
            ChangeStudentPasswordCommand(
                email="student@school.edu",
                session="cognito-session-token",
                new_password="weak",
            )
        )


@pytest.mark.asyncio
async def test_cognito_adapter_login_student_returns_challenge() -> None:
    cognito = Mock()
    cognito.initiate_auth = AsyncMock(
        return_value={
            "ChallengeName": "NEW_PASSWORD_REQUIRED",
            "Session": "sess-abc",
        }
    )
    adapter = CognitoAuthAdapter(
        user_pool_id="pool-id",
        client_id="app-client-id",
        client=cognito,
    )

    outcome = await adapter.login_student(
        email="student@school.edu", password="TempPass123!"
    )

    assert outcome == AuthChallenge(
        challenge_name="NEW_PASSWORD_REQUIRED",
        session="sess-abc",
    )
    cognito.initiate_auth.assert_awaited_once_with(
        ClientId="app-client-id",
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={
            "USERNAME": "student@school.edu",
            "PASSWORD": "TempPass123!",
        },
    )


@pytest.mark.asyncio
async def test_cognito_adapter_login_student_returns_tokens() -> None:
    cognito = Mock()
    cognito.initiate_auth = AsyncMock(
        return_value={
            "AuthenticationResult": {
                "IdToken": "id.jwt.token",
                "RefreshToken": "refresh.token",
                "ExpiresIn": 3600,
            }
        }
    )
    adapter = CognitoAuthAdapter(
        user_pool_id="pool-id",
        client_id="app-client-id",
        client=cognito,
    )

    tokens = await adapter.login_student(
        email="student@school.edu", password="StrongPassword123!"
    )

    assert tokens == AuthTokens(
        id_token="id.jwt.token",
        refresh_token="refresh.token",
        expires_in=3600,
    )


@pytest.mark.asyncio
async def test_cognito_adapter_login_student_maps_user_not_found() -> None:
    cognito = Mock()
    cognito.initiate_auth = AsyncMock(
        side_effect=_make_client_error("UserNotFoundException", "User not found")
    )
    adapter = CognitoAuthAdapter(
        user_pool_id="pool-id",
        client_id="app-client-id",
        client=cognito,
    )

    with pytest.raises(InvalidCredentialsError):
        await adapter.login_student(email="unknown@school.edu", password="x")


@pytest.mark.asyncio
async def test_cognito_adapter_login_student_re_raises_unmapped_client_error() -> None:
    cognito = Mock()
    cognito.initiate_auth = AsyncMock(
        side_effect=_make_client_error("TooManyRequestsException", "Throttled")
    )
    adapter = CognitoAuthAdapter(
        user_pool_id="pool-id",
        client_id="app-client-id",
        client=cognito,
    )

    with pytest.raises(ClientError) as exc_info:
        await adapter.login_student(email="student@school.edu", password="x")

    assert exc_info.value.response["Error"]["Code"] == "TooManyRequestsException"


@pytest.mark.asyncio
async def test_cognito_adapter_login_student_maps_not_authorized() -> None:
    cognito = Mock()
    cognito.initiate_auth = AsyncMock(
        side_effect=_make_client_error(
            "NotAuthorizedException",
            "Incorrect username or password",
        )
    )
    adapter = CognitoAuthAdapter(
        user_pool_id="pool-id",
        client_id="app-client-id",
        client=cognito,
    )

    with pytest.raises(InvalidCredentialsError):
        await adapter.login_student(email="student@school.edu", password="wrong")


@pytest.mark.asyncio
async def test_cognito_adapter_respond_to_challenge_returns_tokens() -> None:
    cognito = Mock()
    cognito.respond_to_auth_challenge = AsyncMock(
        return_value={
            "AuthenticationResult": {
                "IdToken": "id.after",
                "RefreshToken": "refresh.after",
                "ExpiresIn": 3600,
            }
        }
    )
    adapter = CognitoAuthAdapter(
        user_pool_id="pool-id",
        client_id="app-client-id",
        client=cognito,
    )

    tokens = await adapter.respond_to_new_password_challenge(
        email="student@school.edu",
        session="sess-xyz",
        new_password="NewStrongPassword123!",
    )

    assert tokens == AuthTokens(
        id_token="id.after",
        refresh_token="refresh.after",
        expires_in=3600,
    )
    cognito.respond_to_auth_challenge.assert_awaited_once_with(
        ClientId="app-client-id",
        ChallengeName="NEW_PASSWORD_REQUIRED",
        Session="sess-xyz",
        ChallengeResponses={
            "USERNAME": "student@school.edu",
            "NEW_PASSWORD": "NewStrongPassword123!",
        },
    )


@pytest.mark.asyncio
async def test_cognito_adapter_respond_to_challenge_maps_weak_password() -> None:
    cognito = Mock()
    cognito.respond_to_auth_challenge = AsyncMock(
        side_effect=_make_client_error(
            "InvalidPasswordException",
            "Password should contain special characters",
        )
    )
    adapter = CognitoAuthAdapter(
        user_pool_id="pool-id",
        client_id="app-client-id",
        client=cognito,
    )

    with pytest.raises(WeakPasswordError, match="special characters"):
        await adapter.respond_to_new_password_challenge(
            email="student@school.edu",
            session="sess-xyz",
            new_password="weak",
        )


@pytest.mark.asyncio
async def test_cognito_adapter_respond_to_challenge_maps_not_authorized() -> None:
    cognito = Mock()
    cognito.respond_to_auth_challenge = AsyncMock(
        side_effect=_make_client_error(
            "NotAuthorizedException",
            "Session expired",
        )
    )
    adapter = CognitoAuthAdapter(
        user_pool_id="pool-id",
        client_id="app-client-id",
        client=cognito,
    )

    with pytest.raises(InvalidCredentialsError):
        await adapter.respond_to_new_password_challenge(
            email="student@school.edu",
            session="bad-session",
            new_password="NewStrongPassword123!",
        )


def test_api_student_login_returns_challenge(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock(
        return_value=LoginStudentResult(
            tokens=None,
            challenge=AuthChallenge(
                challenge_name="NEW_PASSWORD_REQUIRED",
                session="sess-abc",
            ),
        )
    )
    client.app.dependency_overrides[get_login_student_use_case] = lambda: mock_use_case

    response = client.post(
        "/auth/student-login",
        json={"email": "student@school.edu", "password": "TempPass123!"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id_token": None,
        "refresh_token": None,
        "expires_in": None,
        "challenge_name": "NEW_PASSWORD_REQUIRED",
        "session": "sess-abc",
    }


def test_api_student_login_returns_tokens(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock(
        return_value=LoginStudentResult(
            tokens=AuthTokens(
                id_token="id.jwt.token",
                refresh_token="refresh.token",
                expires_in=3600,
            ),
            challenge=None,
        )
    )
    client.app.dependency_overrides[get_login_student_use_case] = lambda: mock_use_case

    response = client.post(
        "/auth/student-login",
        json={"email": "student@school.edu", "password": "StrongPassword123!"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id_token": "id.jwt.token",
        "refresh_token": "refresh.token",
        "expires_in": 3600,
        "challenge_name": None,
        "session": None,
    }


def test_api_student_login_invalid_credentials_returns_401(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock(
        side_effect=InvalidCredentialsError("bad credentials")
    )
    client.app.dependency_overrides[get_login_student_use_case] = lambda: mock_use_case

    response = client.post(
        "/auth/student-login",
        json={"email": "student@school.edu", "password": "wrong"},
    )

    assert response.status_code == 401
    body = response.json()
    assert body["error"] == "bad credentials"
    assert body["code"] == "invalid_credentials"


def test_api_change_password_returns_tokens(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock(
        return_value=ChangeStudentPasswordResult(
            tokens=AuthTokens(
                id_token="id.after",
                refresh_token="refresh.after",
                expires_in=3600,
            )
        )
    )
    client.app.dependency_overrides[get_change_password_use_case] = lambda: (
        mock_use_case
    )

    response = client.post(
        "/auth/change-password",
        json={
            "email": "student@school.edu",
            "session": "sess-xyz",
            "new_password": "NewStrongPassword123!",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "id_token": "id.after",
        "refresh_token": "refresh.after",
        "expires_in": 3600,
    }


def test_api_change_password_invalid_session_returns_401(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock(
        side_effect=InvalidCredentialsError("session expired")
    )
    client.app.dependency_overrides[get_change_password_use_case] = lambda: (
        mock_use_case
    )

    response = client.post(
        "/auth/change-password",
        json={
            "email": "student@school.edu",
            "session": "bad",
            "new_password": "NewStrongPassword123!",
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"


def test_api_change_password_weak_password_returns_400(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock(side_effect=WeakPasswordError("too weak"))
    client.app.dependency_overrides[get_change_password_use_case] = lambda: (
        mock_use_case
    )

    response = client.post(
        "/auth/change-password",
        json={
            "email": "student@school.edu",
            "session": "sess-xyz",
            "new_password": "123",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "too weak"


@pytest.mark.asyncio
async def test_student_id_token_from_challenge_response_contains_claims() -> None:
    """Decode IdToken returned by the adapter (as Cognito would emit it)."""
    header = _encode_segment({"alg": "none", "typ": "JWT"})
    payload = _encode_segment(
        {
            "custom:role": "student",
            "sub": "student-sub-uuid",
            "email": "student@school.edu",
            "custom:exam_id": "exam-123",
        }
    )
    id_token = f"{header}.{payload}."

    cognito = Mock()
    cognito.respond_to_auth_challenge = AsyncMock(
        return_value={
            "AuthenticationResult": {
                "IdToken": id_token,
                "RefreshToken": "refresh.after",
                "ExpiresIn": 3600,
            }
        }
    )
    adapter = CognitoAuthAdapter(
        user_pool_id="pool-id",
        client_id="app-client-id",
        client=cognito,
    )

    tokens = await adapter.respond_to_new_password_challenge(
        email="student@school.edu",
        session="sess",
        new_password="NewStrongPassword123!",
    )

    claims = _decode_jwt_payload(tokens.id_token)

    assert claims["custom:role"] == "student"
    assert claims["sub"] == "student-sub-uuid"
    assert claims["email"] == "student@school.edu"
    assert claims["custom:exam_id"] == "exam-123"


@pytest.mark.asyncio
async def test_after_password_change_student_login_called_with_new_password() -> None:
    """Structural flow: challenge completion then login with final password (mocked Cognito)."""
    auth = Mock()
    auth.respond_to_new_password_challenge = AsyncMock(
        return_value=AuthTokens(
            id_token="id.after",
            refresh_token="refresh.after",
            expires_in=3600,
        )
    )
    auth.login_student = AsyncMock(
        return_value=AuthTokens(
            id_token="id.login",
            refresh_token="refresh.login",
            expires_in=3600,
        )
    )

    change_uc = ChangeStudentPasswordUseCase(auth_service=auth)
    await change_uc.execute(
        ChangeStudentPasswordCommand(
            email="student@school.edu",
            session="sess",
            new_password="FinalStrongPassword123!",
        )
    )

    login_uc = LoginStudentUseCase(auth_service=auth)
    await login_uc.execute(
        LoginStudentCommand(
            email="student@school.edu",
            password="FinalStrongPassword123!",
        )
    )

    auth.respond_to_new_password_challenge.assert_awaited_once()
    auth.login_student.assert_awaited_once_with(
        email="student@school.edu",
        password="FinalStrongPassword123!",
    )


def test_api_change_password_empty_session_returns_422(client: TestClient) -> None:
    mock_use_case = Mock()
    client.app.dependency_overrides[get_change_password_use_case] = lambda: (
        mock_use_case
    )

    response = client.post(
        "/auth/change-password",
        json={
            "email": "student@school.edu",
            "session": "   ",
            "new_password": "NewStrongPassword123!",
        },
    )

    assert response.status_code == 422
    mock_use_case.execute.assert_not_called()
