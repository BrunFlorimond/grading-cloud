"""Tests for centralised RBAC FastAPI dependency guards (issue #12)."""

from __future__ import annotations

from typing import Annotated
from unittest.mock import AsyncMock, Mock, create_autospec

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from httpx import HTTPError
from jose import JWTError

from exam_api.api.dependencies import (
    CurrentAdmin,
    CurrentStudent,
    CurrentTeacher,
    require_admin,
    require_own_data,
    require_student,
    require_teacher,
)
from exam_api.api.http_error_handlers import register_http_error_handlers
from exam_api.application.verify_exam_ownership import (
    VerifyExamOwnershipCommand,
    VerifyExamOwnershipUseCase,
)
from exam_api.domain.errors import ExamNotFoundError, ExamOwnershipError
from exam_api.infrastructure.dynamodb_exam_ownership_repository import (
    DynamoDbExamOwnershipRepository,
)
from exam_api.ports.exam_ownership_port import ExamOwnershipPort
from exam_api.ports.jwt_verifier_port import JwtVerifierPort


@pytest.fixture
def rbac_app() -> FastAPI:
    app = FastAPI()
    register_http_error_handlers(app)
    jwt_verifier = create_autospec(JwtVerifierPort, instance=True)
    app.state.jwt_verifier = jwt_verifier

    @app.get("/teacher-only")
    async def teacher_route(
        _: Annotated[CurrentTeacher, Depends(require_teacher)],
    ) -> dict[str, str]:
        return {"role": "teacher"}

    @app.get("/student-only")
    async def student_route(
        _: Annotated[CurrentStudent, Depends(require_student)],
    ) -> dict[str, str]:
        return {"role": "student"}

    @app.get("/admin-only")
    async def admin_route(
        _: Annotated[CurrentAdmin, Depends(require_admin)],
    ) -> dict[str, str]:
        return {"role": "admin"}

    @app.get("/exams/{exam_id}/students/{student_id}/mine")
    async def own_route(
        _: Annotated[None, Depends(require_own_data("student_id"))],
    ) -> dict[str, str]:
        return {"ok": "true"}

    return app


@pytest.fixture
def rbac_client(rbac_app: FastAPI) -> TestClient:
    return TestClient(rbac_app)


def test_require_teacher_returns_current_teacher(
    rbac_app: FastAPI, rbac_client: TestClient
) -> None:
    rbac_app.state.jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={"sub": "t1", "custom:role": "teacher"}
    )
    response = rbac_client.get("/teacher-only", headers={"Authorization": "Bearer x"})
    assert response.status_code == 200
    assert response.json() == {"role": "teacher"}


def test_require_teacher_401_missing_auth(rbac_client: TestClient) -> None:
    response = rbac_client.get("/teacher-only")
    assert response.status_code == 401
    body = response.json()
    assert "error" in body and "code" in body


def test_require_teacher_401_bad_scheme(rbac_client: TestClient) -> None:
    response = rbac_client.get("/teacher-only", headers={"Authorization": "Basic x"})
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "bad_scheme"


def test_require_teacher_401_invalid_jwt(
    rbac_app: FastAPI, rbac_client: TestClient
) -> None:
    rbac_app.state.jwt_verifier.decode_and_verify_token = AsyncMock(
        side_effect=JWTError("bad")
    )
    response = rbac_client.get("/teacher-only", headers={"Authorization": "Bearer bad"})
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


def test_require_teacher_403_student_role(
    rbac_app: FastAPI, rbac_client: TestClient
) -> None:
    rbac_app.state.jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={"sub": "x", "custom:role": "student"}
    )
    response = rbac_client.get("/teacher-only", headers={"Authorization": "Bearer x"})
    assert response.status_code == 403
    assert response.json()["code"] == "insufficient_role"


def test_require_teacher_403_missing_role(
    rbac_app: FastAPI, rbac_client: TestClient
) -> None:
    rbac_app.state.jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={"sub": "x"}
    )
    response = rbac_client.get("/teacher-only", headers={"Authorization": "Bearer x"})
    assert response.status_code == 403
    assert response.json()["code"] == "insufficient_role"


def test_require_admin_returns_when_group_present(
    rbac_app: FastAPI, rbac_client: TestClient
) -> None:
    rbac_app.state.jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={"sub": "a1", "cognito:groups": ["Admin"]}
    )
    response = rbac_client.get("/admin-only", headers={"Authorization": "Bearer x"})
    assert response.status_code == 200
    assert response.json() == {"role": "admin"}


def test_require_admin_403_without_admin_group(
    rbac_app: FastAPI, rbac_client: TestClient
) -> None:
    rbac_app.state.jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={"sub": "t", "cognito:groups": ["teachers"]}
    )
    response = rbac_client.get("/admin-only", headers={"Authorization": "Bearer x"})
    assert response.status_code == 403
    assert response.json()["code"] == "insufficient_role"


def test_require_student_returns_current_student(
    rbac_app: FastAPI, rbac_client: TestClient
) -> None:
    rbac_app.state.jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={"sub": "s1", "custom:role": "student"}
    )
    response = rbac_client.get("/student-only", headers={"Authorization": "Bearer x"})
    assert response.status_code == 200
    assert response.json() == {"role": "student"}


def test_require_student_401_missing_auth(rbac_client: TestClient) -> None:
    response = rbac_client.get("/student-only")
    assert response.status_code == 401
    body = response.json()
    assert "error" in body and "code" in body


def test_require_student_401_bad_scheme(rbac_client: TestClient) -> None:
    response = rbac_client.get("/student-only", headers={"Authorization": "Basic x"})
    assert response.status_code == 401


def test_require_student_401_invalid_jwt(
    rbac_app: FastAPI, rbac_client: TestClient
) -> None:
    rbac_app.state.jwt_verifier.decode_and_verify_token = AsyncMock(
        side_effect=HTTPError("x")
    )
    response = rbac_client.get("/student-only", headers={"Authorization": "Bearer bad"})
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


def test_require_student_403_teacher_role(
    rbac_app: FastAPI, rbac_client: TestClient
) -> None:
    rbac_app.state.jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={"sub": "t", "custom:role": "teacher"}
    )
    response = rbac_client.get("/student-only", headers={"Authorization": "Bearer x"})
    assert response.status_code == 403


def test_require_student_403_missing_role(
    rbac_app: FastAPI, rbac_client: TestClient
) -> None:
    rbac_app.state.jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={"sub": "s"}
    )
    response = rbac_client.get("/student-only", headers={"Authorization": "Bearer x"})
    assert response.status_code == 403


def test_require_own_data_passes(rbac_app: FastAPI, rbac_client: TestClient) -> None:
    rbac_app.state.jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={"sub": "student-a", "custom:role": "student"}
    )
    response = rbac_client.get(
        "/exams/e1/students/student-a/mine",
        headers={"Authorization": "Bearer x"},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": "true"}


def test_require_own_data_403_mismatch(
    rbac_app: FastAPI, rbac_client: TestClient
) -> None:
    rbac_app.state.jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={"sub": "student-a", "custom:role": "student"}
    )
    response = rbac_client.get(
        "/exams/e1/students/other/mine",
        headers={"Authorization": "Bearer x"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "own_data_violation"


@pytest.mark.asyncio
async def test_verify_exam_ownership_calls_port() -> None:
    port = Mock(spec=ExamOwnershipPort)
    port.verify_teacher_owns_exam = AsyncMock(return_value=None)
    uc = VerifyExamOwnershipUseCase(port)
    await uc.execute(VerifyExamOwnershipCommand(teacher_id="t1", exam_id="e1"))
    port.verify_teacher_owns_exam.assert_awaited_once_with(teacher_id="t1", exam_id="e1")


@pytest.mark.asyncio
async def test_verify_exam_ownership_propagates_ownership_error() -> None:
    port = Mock(spec=ExamOwnershipPort)
    port.verify_teacher_owns_exam = AsyncMock(
        side_effect=ExamOwnershipError("no access"),
    )
    uc = VerifyExamOwnershipUseCase(port)
    with pytest.raises(ExamOwnershipError):
        await uc.execute(VerifyExamOwnershipCommand(teacher_id="t1", exam_id="e1"))


@pytest.mark.asyncio
async def test_verify_exam_ownership_propagates_not_found() -> None:
    port = Mock(spec=ExamOwnershipPort)
    port.verify_teacher_owns_exam = AsyncMock(side_effect=ExamNotFoundError("missing"))
    uc = VerifyExamOwnershipUseCase(port)
    with pytest.raises(ExamNotFoundError):
        await uc.execute(VerifyExamOwnershipCommand(teacher_id="t1", exam_id="e1"))


@pytest.mark.asyncio
async def test_dynamodb_verify_success_when_metadata_and_edge_exist() -> None:
    client = Mock()
    client.get_item = AsyncMock(
        side_effect=[
            {"Item": {"PK": {"S": "EXAM#e"}}},
            {"Item": {"PK": {"S": "TEACHER#t"}}},
        ]
    )
    repo = DynamoDbExamOwnershipRepository(table_name="tbl", dynamodb_client=client)
    await repo.verify_teacher_owns_exam(teacher_id="t", exam_id="e")
    assert client.get_item.await_count == 2


@pytest.mark.asyncio
async def test_dynamodb_verify_raises_not_found_when_no_metadata() -> None:
    client = Mock()
    client.get_item = AsyncMock(return_value={})
    repo = DynamoDbExamOwnershipRepository(table_name="tbl", dynamodb_client=client)
    with pytest.raises(ExamNotFoundError):
        await repo.verify_teacher_owns_exam(teacher_id="t", exam_id="e")
    client.get_item.assert_awaited_once()


@pytest.mark.asyncio
async def test_dynamodb_verify_raises_ownership_when_no_edge() -> None:
    client = Mock()
    client.get_item = AsyncMock(
        side_effect=[
            {"Item": {"PK": {"S": "EXAM#e"}}},
            {},
        ]
    )
    repo = DynamoDbExamOwnershipRepository(table_name="tbl", dynamodb_client=client)
    with pytest.raises(ExamOwnershipError):
        await repo.verify_teacher_owns_exam(teacher_id="t", exam_id="e")
