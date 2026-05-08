"""Regression coverage for issue #59 — async adapters (aiobotocore + httpx.AsyncClient).

Detailed adapter behaviour is covered in test_auth.py, test_cognito_jwt_verifier.py,
test_dynamodb_invite_repository.py, and test_invite_student.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, create_autospec

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from exam_api.api.auth_router import get_login_use_case, get_register_use_case, router
from exam_api.application.login_teacher import LoginTeacherResult
from exam_api.application.register_teacher import RegisterTeacherResult
from exam_api.domain.teacher import Teacher
from exam_api.ports.auth_service_port import AuthTokens
from exam_api.ports.jwt_verifier_port import JwtVerifierPort


@pytest.fixture
def auth_client() -> TestClient:
    app = FastAPI()
    jwt_verifier = create_autospec(JwtVerifierPort, instance=True)
    jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={"sub": "admin", "cognito:groups": ["admin"]}
    )
    app.state.jwt_verifier = jwt_verifier
    app.include_router(router)
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def test_register_endpoint_uses_async_execute(auth_client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock(
        return_value=RegisterTeacherResult(
            teacher=Teacher(
                teacher_id="tid",
                email="t@example.com",
                full_name="T",
            )
        )
    )
    auth_client.app.dependency_overrides[get_register_use_case] = lambda: mock_use_case

    response = auth_client.post(
        "/auth/register",
        headers={"Authorization": "Bearer x"},
        json={
            "email": "t@example.com",
            "password": "StrongPassword123!",
            "full_name": "T",
        },
    )

    assert response.status_code == 201
    mock_use_case.execute.assert_awaited_once()


def test_login_endpoint_uses_async_execute(auth_client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock(
        return_value=LoginTeacherResult(
            tokens=AuthTokens(
                access_token="access",
                id_token="id",
                refresh_token="ref",
                expires_in=3600,
            )
        )
    )
    auth_client.app.dependency_overrides[get_login_use_case] = lambda: mock_use_case

    response = auth_client.post(
        "/auth/login",
        json={"email": "t@example.com", "password": "StrongPassword123!"},
    )

    assert response.status_code == 200
    mock_use_case.execute.assert_awaited_once()
