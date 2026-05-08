"""Unit tests for teacher registration and authentication."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, Mock, create_autospec

import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from exam_api.api.auth_router import (
    get_login_use_case,
    get_register_use_case,
    router,
)
from exam_api.api.http_error_handlers import register_http_error_handlers
from exam_api.application.login_teacher import (
    LoginTeacherCommand,
    LoginTeacherResult,
    LoginTeacherUseCase,
)
from exam_api.application.register_teacher import (
    RegisterTeacherCommand,
    RegisterTeacherResult,
    RegisterTeacherUseCase,
)
from exam_api.domain.errors import (
    DuplicateEmailError,
    InvalidCredentialsError,
    TeacherGroupAssignmentError,
    WeakPasswordError,
)
from exam_api.cognito_group_names import COGNITO_TEACHER_GROUP
from exam_api.domain.teacher import Teacher
from exam_api.infrastructure.cognito_auth_adapter import CognitoAuthAdapter
from exam_api.ports.auth_service_port import AuthTokens
from exam_api.ports.jwt_verifier_port import JwtVerifierPort
from exam_api.ports.user_identity_repository_port import UserIdentityRepositoryPort


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


_ADMIN_JWT_CLAIMS: dict[str, object] = {
    "sub": "admin-sub",
    "cognito:groups": ["admin"],
}


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_http_error_handlers(app)
    jwt_verifier = create_autospec(JwtVerifierPort, instance=True)
    jwt_verifier.decode_and_verify_token = AsyncMock(return_value=_ADMIN_JWT_CLAIMS)
    app.state.jwt_verifier = jwt_verifier
    app.include_router(router)
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_register_returns_teacher_with_cognito_sub() -> None:
    auth = Mock()
    auth.register_teacher = AsyncMock(
        return_value="a1fdb8a9-4f65-4f3d-9f99-984f2634af11"
    )
    user_identity_repository = create_autospec(
        UserIdentityRepositoryPort,
        instance=True,
    )
    user_identity_repository.upsert_teacher = AsyncMock(
        return_value=Teacher(
            teacher_id="a1fdb8a9-4f65-4f3d-9f99-984f2634af11",
            email="teacher@example.com",
            full_name="Ada Lovelace",
        )
    )
    use_case = RegisterTeacherUseCase(
        auth_service=auth,
        user_identity_repository=user_identity_repository,
    )

    result = await use_case.execute(
        RegisterTeacherCommand(
            email="teacher@example.com",
            password="StrongPassword123!",
            full_name="Ada Lovelace",
        )
    )

    assert result.teacher.teacher_id == "a1fdb8a9-4f65-4f3d-9f99-984f2634af11"
    assert str(result.teacher.email) == "teacher@example.com"
    assert result.teacher.full_name == "Ada Lovelace"


@pytest.mark.asyncio
async def test_register_raises_duplicate_email_error() -> None:
    auth = Mock()
    auth.register_teacher = AsyncMock(side_effect=DuplicateEmailError("duplicate"))
    user_identity_repository = create_autospec(
        UserIdentityRepositoryPort,
        instance=True,
    )
    user_identity_repository.upsert_teacher = AsyncMock()
    use_case = RegisterTeacherUseCase(
        auth_service=auth,
        user_identity_repository=user_identity_repository,
    )

    with pytest.raises(DuplicateEmailError):
        await use_case.execute(
            RegisterTeacherCommand(
                email="teacher@example.com",
                password="StrongPassword123!",
                full_name="Ada Lovelace",
            )
        )


@pytest.mark.asyncio
async def test_register_raises_weak_password_error() -> None:
    auth = Mock()
    auth.register_teacher = AsyncMock(side_effect=WeakPasswordError("weak password"))
    user_identity_repository = create_autospec(
        UserIdentityRepositoryPort,
        instance=True,
    )
    user_identity_repository.upsert_teacher = AsyncMock()
    use_case = RegisterTeacherUseCase(
        auth_service=auth,
        user_identity_repository=user_identity_repository,
    )

    with pytest.raises(WeakPasswordError):
        await use_case.execute(
            RegisterTeacherCommand(
                email="teacher@example.com",
                password="1234",
                full_name="Ada Lovelace",
            )
        )


@pytest.mark.asyncio
async def test_login_returns_auth_tokens() -> None:
    auth = Mock()
    auth.login_teacher = AsyncMock(
        return_value=AuthTokens(
            access_token="access.jwt.token",
            id_token="id.jwt.token",
            refresh_token="refresh.token",
            expires_in=3600,
        )
    )
    use_case = LoginTeacherUseCase(auth_service=auth)

    result = await use_case.execute(
        LoginTeacherCommand(email="teacher@example.com", password="StrongPassword123!")
    )

    assert result.tokens.id_token == "id.jwt.token"
    assert result.tokens.access_token == "access.jwt.token"
    assert result.tokens.refresh_token == "refresh.token"
    assert result.tokens.expires_in == 3600


@pytest.mark.asyncio
async def test_login_raises_invalid_credentials_error() -> None:
    auth = Mock()
    auth.login_teacher = AsyncMock(side_effect=InvalidCredentialsError("invalid"))
    use_case = LoginTeacherUseCase(auth_service=auth)

    with pytest.raises(InvalidCredentialsError):
        await use_case.execute(
            LoginTeacherCommand(email="teacher@example.com", password="wrong-password")
        )


@pytest.mark.asyncio
async def test_cognito_register_admin_creates_user_sets_password_adds_to_group() -> (
    None
):
    cognito = Mock()
    cognito.admin_create_user = AsyncMock(
        return_value={
            "User": {
                "Attributes": [
                    {"Name": "sub", "Value": "teacher-sub-uuid"},
                ],
            },
        }
    )
    cognito.admin_set_user_password = AsyncMock()
    cognito.admin_add_user_to_group = AsyncMock()
    cognito.admin_delete_user = AsyncMock()
    adapter = CognitoAuthAdapter(
        user_pool_id="pool-id",
        client_id="app-client-id",
        client=cognito,
    )

    teacher_id = await adapter.register_teacher(
        email="teacher@example.com",
        password="StrongPassword123!",
        full_name="Ada Lovelace",
    )

    assert teacher_id == "teacher-sub-uuid"
    create_call = cognito.admin_create_user.call_args.kwargs
    assert create_call["UserPoolId"] == "pool-id"
    assert create_call["Username"] == "teacher@example.com"
    assert create_call["MessageAction"] == "SUPPRESS"
    assert "TemporaryPassword" in create_call
    user_attrs = create_call["UserAttributes"]
    assert {"Name": "email", "Value": "teacher@example.com"} in user_attrs
    assert {"Name": "email_verified", "Value": "true"} in user_attrs
    assert {"Name": "name", "Value": "Ada Lovelace"} in user_attrs
    cognito.admin_set_user_password.assert_awaited_once_with(
        UserPoolId="pool-id",
        Username="teacher@example.com",
        Password="StrongPassword123!",
        Permanent=True,
    )
    cognito.admin_add_user_to_group.assert_awaited_once_with(
        UserPoolId="pool-id",
        Username="teacher@example.com",
        GroupName=COGNITO_TEACHER_GROUP,
    )


@pytest.mark.asyncio
async def test_cognito_register_maps_username_exists_to_duplicate_email() -> None:
    cognito = Mock()
    cognito.admin_create_user = AsyncMock(
        side_effect=_make_client_error(
            "UsernameExistsException",
            "User already exists",
        )
    )
    adapter = CognitoAuthAdapter(
        user_pool_id="pool-id",
        client_id="app-client-id",
        client=cognito,
    )

    with pytest.raises(DuplicateEmailError):
        await adapter.register_teacher(
            email="teacher@example.com",
            password="StrongPassword123!",
            full_name="Ada Lovelace",
        )


@pytest.mark.asyncio
async def test_cognito_register_maps_invalid_password_to_weak_password() -> None:
    cognito = Mock()
    cognito.admin_create_user = AsyncMock(
        return_value={
            "User": {
                "Attributes": [
                    {"Name": "sub", "Value": "sub"},
                ],
            },
        }
    )
    cognito.admin_set_user_password = AsyncMock(
        side_effect=_make_client_error(
            "InvalidPasswordException",
            "Password should contain special characters",
        )
    )
    cognito.admin_delete_user = AsyncMock()
    adapter = CognitoAuthAdapter(
        user_pool_id="pool-id",
        client_id="app-client-id",
        client=cognito,
    )

    with pytest.raises(WeakPasswordError, match="special characters"):
        await adapter.register_teacher(
            email="teacher@example.com",
            password="weak",
            full_name="Ada Lovelace",
        )

    cognito.admin_delete_user.assert_awaited_once_with(
        UserPoolId="pool-id",
        Username="teacher@example.com",
    )


@pytest.mark.asyncio
async def test_cognito_register_group_assignment_failure_deletes_user() -> None:
    cognito = Mock()
    cognito.admin_create_user = AsyncMock(
        return_value={
            "User": {
                "Attributes": [
                    {"Name": "sub", "Value": "teacher-sub-uuid"},
                ],
            },
        }
    )
    cognito.admin_set_user_password = AsyncMock()
    cognito.admin_add_user_to_group = AsyncMock(
        side_effect=_make_client_error(
            "LimitExceededException",
            "Too many requests",
        )
    )
    cognito.admin_delete_user = AsyncMock()
    adapter = CognitoAuthAdapter(
        user_pool_id="pool-id",
        client_id="app-client-id",
        client=cognito,
    )

    with pytest.raises(TeacherGroupAssignmentError):
        await adapter.register_teacher(
            email="teacher@example.com",
            password="StrongPassword123!",
            full_name="Ada Lovelace",
        )

    cognito.admin_delete_user.assert_awaited_once_with(
        UserPoolId="pool-id",
        Username="teacher@example.com",
    )


@pytest.mark.asyncio
async def test_cognito_register_missing_sub_deletes_user() -> None:
    """If Cognito omits sub in AdminCreateUser response, roll back and map to domain error."""
    cognito = Mock()
    cognito.admin_create_user = AsyncMock(
        return_value={
            "User": {
                "Attributes": [
                    {"Name": "email", "Value": "teacher@example.com"},
                ],
            },
        }
    )
    cognito.admin_set_user_password = AsyncMock()
    cognito.admin_add_user_to_group = AsyncMock()
    cognito.admin_delete_user = AsyncMock()
    adapter = CognitoAuthAdapter(
        user_pool_id="pool-id",
        client_id="app-client-id",
        client=cognito,
    )

    with pytest.raises(TeacherGroupAssignmentError, match="identifier"):
        await adapter.register_teacher(
            email="teacher@example.com",
            password="StrongPassword123!",
            full_name="Ada Lovelace",
        )

    cognito.admin_delete_user.assert_awaited_once_with(
        UserPoolId="pool-id",
        Username="teacher@example.com",
    )


def test_generate_internal_temporary_password_randomized_and_complex() -> None:
    seen: set[str] = set()
    for _ in range(30):
        pwd = CognitoAuthAdapter._generate_internal_temporary_password(24)
        assert len(pwd) == 24
        assert any(c.isupper() for c in pwd)
        assert any(c.islower() for c in pwd)
        assert any(c.isdigit() for c in pwd)
        assert any(c in "!@#$%^&*()-_=+" for c in pwd)
        seen.add(pwd)
    assert len(seen) > 1


@pytest.mark.asyncio
async def test_cognito_login_calls_initiate_auth_and_returns_tokens() -> None:
    cognito = Mock()
    cognito.initiate_auth = AsyncMock(
        return_value={
            "AuthenticationResult": {
                "AccessToken": "access.jwt.token",
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

    tokens = await adapter.login_teacher(
        email="teacher@example.com", password="StrongPassword123!"
    )

    assert tokens == AuthTokens(
        access_token="access.jwt.token",
        id_token="id.jwt.token",
        refresh_token="refresh.token",
        expires_in=3600,
    )
    cognito.initiate_auth.assert_awaited_once_with(
        ClientId="app-client-id",
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={
            "USERNAME": "teacher@example.com",
            "PASSWORD": "StrongPassword123!",
        },
    )


@pytest.mark.asyncio
async def test_cognito_login_maps_not_authorized_to_invalid_credentials() -> None:
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
        await adapter.login_teacher(email="teacher@example.com", password="wrong")


def test_post_register_201_returns_teacher_id(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock(
        return_value=RegisterTeacherResult(
            teacher=Teacher(
                teacher_id="teacher-sub-uuid",
                email="teacher@example.com",
                full_name="Ada Lovelace",
            )
        )
    )
    client.app.dependency_overrides[get_register_use_case] = lambda: mock_use_case

    response = client.post(
        "/auth/register",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "email": "teacher@example.com",
            "password": "StrongPassword123!",
            "full_name": "Ada Lovelace",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "teacher_id": "teacher-sub-uuid",
        "email": "teacher@example.com",
        "full_name": "Ada Lovelace",
    }


def test_post_register_409_duplicate_email(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock(side_effect=DuplicateEmailError("duplicate"))
    client.app.dependency_overrides[get_register_use_case] = lambda: mock_use_case

    response = client.post(
        "/auth/register",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "email": "teacher@example.com",
            "password": "StrongPassword123!",
            "full_name": "Ada Lovelace",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "duplicate"


def test_post_register_401_without_bearer(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock()
    client.app.dependency_overrides[get_register_use_case] = lambda: mock_use_case

    response = client.post(
        "/auth/register",
        json={
            "email": "teacher@example.com",
            "password": "StrongPassword123!",
            "full_name": "Ada Lovelace",
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == "missing_token"
    mock_use_case.execute.assert_not_called()


def test_post_register_403_without_admin_group(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock()
    client.app.dependency_overrides[get_register_use_case] = lambda: mock_use_case
    client.app.state.jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={
            "sub": "teacher-sub",
            "cognito:groups": ["teachers"],
        }
    )

    response = client.post(
        "/auth/register",
        headers={"Authorization": "Bearer id-token"},
        json={
            "email": "teacher@example.com",
            "password": "StrongPassword123!",
            "full_name": "Ada Lovelace",
        },
    )

    assert response.status_code == 403
    assert response.json()["code"] == "insufficient_role"
    mock_use_case.execute.assert_not_called()


def test_post_register_400_weak_password(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock(
        side_effect=WeakPasswordError("Password too weak")
    )
    client.app.dependency_overrides[get_register_use_case] = lambda: mock_use_case

    response = client.post(
        "/auth/register",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "email": "teacher@example.com",
            "password": "weak",
            "full_name": "Ada Lovelace",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Password too weak"


def test_post_register_503_teacher_group_assignment_failed(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock(
        side_effect=TeacherGroupAssignmentError(
            "Could not assign the new teacher to the teachers group."
        )
    )
    client.app.dependency_overrides[get_register_use_case] = lambda: mock_use_case

    response = client.post(
        "/auth/register",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "email": "teacher@example.com",
            "password": "StrongPassword123!",
            "full_name": "Ada Lovelace",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Could not assign the new teacher to the teachers group."
    )


def test_post_login_200_returns_tokens(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock(
        return_value=LoginTeacherResult(
            tokens=AuthTokens(
                access_token="access.jwt.token",
                id_token="id.jwt.token",
                refresh_token="refresh.token",
                expires_in=3600,
            )
        )
    )
    client.app.dependency_overrides[get_login_use_case] = lambda: mock_use_case

    response = client.post(
        "/auth/login",
        json={"email": "teacher@example.com", "password": "StrongPassword123!"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "access.jwt.token",
        "id_token": "id.jwt.token",
        "refresh_token": "refresh.token",
        "expires_in": 3600,
    }


def test_post_login_401_invalid_credentials(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock(
        side_effect=InvalidCredentialsError("invalid credentials")
    )
    client.app.dependency_overrides[get_login_use_case] = lambda: mock_use_case

    response = client.post(
        "/auth/login",
        json={"email": "teacher@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    body = response.json()
    assert body["error"] == "invalid credentials"
    assert body["code"] == "invalid_credentials"


def test_jwt_contains_required_claims() -> None:
    header = _encode_segment({"alg": "none", "typ": "JWT"})
    payload = _encode_segment(
        {
            "cognito:groups": ["teachers"],
            "sub": "a1fdb8a9-4f65-4f3d-9f99-984f2634af11",
            "email": "teacher@example.com",
        }
    )
    token = f"{header}.{payload}."

    claims = _decode_jwt_payload(token)

    assert claims["cognito:groups"] == ["teachers"]
    assert claims["sub"] == "a1fdb8a9-4f65-4f3d-9f99-984f2634af11"
    assert claims["email"] == "teacher@example.com"
