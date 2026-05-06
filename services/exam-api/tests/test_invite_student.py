"""Unit tests for the invite-student flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, create_autospec

import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from grading_shared.domain.exam import Exam, ExamStatus
from jose import JWTError

from exam_api.api.dependencies import CurrentTeacher, require_teacher
from exam_api.api.http_error_handlers import register_http_error_handlers
from exam_api.api.invite_router import provide_invite_use_case, router
from exam_api.composition import (
    get_invite_exam_repository,
    get_invite_scope_repository,
    get_student_scope_repository,
    get_verify_exam_ownership_use_case,
    verify_teacher_exam_ownership,
)
from exam_api.application.invite_student import (
    InviteStudentCommand,
    InviteStudentResult,
    InviteStudentUseCase,
)
from exam_api.domain.errors import (
    EXAM_NOT_FOUND_FOR_CLIENT,
    ExamNotFoundError,
    ExamOwnershipError,
    StudentExamScopeConflictError,
)
from exam_api.domain.student import Student
from exam_api.ports.jwt_verifier_port import JwtVerifierPort
from exam_api.infrastructure.student_invite_adapter import (
    CognitoSesStudentInviteAdapter,
)
from exam_api.ports.student_invite_port import (
    InviteStudentResult as PortInviteStudentResult,
)


def _make_client_error(code: str, message: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": message}},
        operation_name="CognitoAction",
    )


async def _noop_verify_teacher_exam_ownership() -> None:
    return None


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_http_error_handlers(app)
    app.include_router(router)
    app.state.student_invite_service = Mock(spec=["invite_student"])
    invite_repository = Mock()
    invite_repository.get_exam = AsyncMock()
    invite_repository.save_exam = AsyncMock()
    invite_repository.save_notation_payload = AsyncMock()
    invite_repository.upsert_student_scope = AsyncMock()
    invite_repository.get_student_scope = AsyncMock()
    app.dependency_overrides[get_invite_exam_repository] = lambda: invite_repository
    app.dependency_overrides[get_invite_scope_repository] = lambda: invite_repository
    app.dependency_overrides[get_student_scope_repository] = lambda: invite_repository
    app.state.invite_repository = invite_repository
    jwt_verifier = create_autospec(JwtVerifierPort, instance=True)
    jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={
            "sub": "teacher-1",
            "cognito:groups": ["teachers"],
            "token_use": "id",
        }
    )
    app.state.jwt_verifier = jwt_verifier
    app.dependency_overrides[verify_teacher_exam_ownership] = (
        _noop_verify_teacher_exam_ownership
    )
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def _build_use_case(
    *,
    invite_service: Mock | None = None,
    exam_repository: Mock | None = None,
    student_scope_repository: Mock | None = None,
    user_identity_repository: Mock | None = None,
) -> InviteStudentUseCase:
    invite_adapter = invite_service
    if invite_adapter is None:
        invite_adapter = Mock()
        invite_adapter.invite_student = AsyncMock()
    scope_repository = student_scope_repository
    if scope_repository is None:
        scope_repository = Mock()
        scope_repository.upsert_student_scope = AsyncMock()
    identity_repository = user_identity_repository
    if identity_repository is None:
        identity_repository = Mock()
        identity_repository.upsert_student = AsyncMock()
    return InviteStudentUseCase(
        invite_service=invite_adapter,
        exam_repository=exam_repository or Mock(),
        student_scope_repository=scope_repository,
        user_identity_repository=identity_repository,
    )


@pytest.mark.asyncio
async def test_use_case_returns_new_invite_result() -> None:
    invite_service = Mock()
    invite_service.invite_student = AsyncMock(
        return_value=PortInviteStudentResult(
            cognito_sub="student-sub-123",
            already_existed=False,
        )
    )
    exam_repository = Mock()
    exam_repository.get_exam = AsyncMock(
        return_value=Exam(
            exam_id="exam-1",
            teacher_id="teacher-1",
            title="Math Midterm",
            status=ExamStatus.DRAFT,
        )
    )
    student_scope_repository = Mock()
    student_scope_repository.upsert_student_scope = AsyncMock()
    user_identity_repository = Mock()
    user_identity_repository.upsert_student = AsyncMock()
    use_case = _build_use_case(
        invite_service=invite_service,
        exam_repository=exam_repository,
        student_scope_repository=student_scope_repository,
        user_identity_repository=user_identity_repository,
    )

    result = await use_case.execute(
        InviteStudentCommand(
            exam_id="exam-1",
            student_id="student-external-id",
            student_email="student@example.com",
            teacher_id="teacher-1",
        )
    )

    assert result == InviteStudentResult(
        student=Student(
            student_id="student-sub-123",
            email="student@example.com",
        ),
        re_invited=False,
    )
    invite_service.invite_student.assert_awaited_once_with(
        student_email="student@example.com",
        exam_id="exam-1",
    )
    student_scope_repository.upsert_student_scope.assert_awaited_once()
    user_identity_repository.upsert_student.assert_awaited_once()


@pytest.mark.asyncio
async def test_use_case_returns_reinvited_true_when_student_exists() -> None:
    invite_service = Mock()
    invite_service.invite_student = AsyncMock(
        return_value=PortInviteStudentResult(
            cognito_sub="student-sub-existing",
            already_existed=True,
        )
    )
    exam_repository = Mock()
    student_scope_repository = Mock()
    student_scope_repository.upsert_student_scope = AsyncMock()
    user_identity_repository = Mock()
    user_identity_repository.upsert_student = AsyncMock()
    exam_repository.get_exam = AsyncMock(
        return_value=Exam(
            exam_id="exam-1",
            teacher_id="teacher-1",
            title="Math Midterm",
            status=ExamStatus.DRAFT,
        )
    )
    use_case = _build_use_case(
        invite_service=invite_service,
        exam_repository=exam_repository,
        student_scope_repository=student_scope_repository,
        user_identity_repository=user_identity_repository,
    )

    result = await use_case.execute(
        InviteStudentCommand(
            exam_id="exam-1",
            student_id="student-external-id",
            student_email="student@example.com",
            teacher_id="teacher-1",
        )
    )

    assert result.re_invited is True
    assert result.student.student_id == "student-sub-existing"
    student_scope_repository.upsert_student_scope.assert_awaited_once()
    user_identity_repository.upsert_student.assert_awaited_once()


@pytest.mark.asyncio
async def test_use_case_raises_scope_conflict_from_dynamo_upsert() -> None:
    invite_service = Mock()
    invite_service.invite_student = AsyncMock(
        return_value=PortInviteStudentResult(
            cognito_sub="student-sub-existing",
            already_existed=True,
        )
    )
    exam_repository = Mock()
    student_scope_repository = Mock()
    exam_repository.get_exam = AsyncMock(
        return_value=Exam(
            exam_id="exam-1",
            teacher_id="teacher-1",
            title="Math Midterm",
            status=ExamStatus.DRAFT,
        )
    )
    student_scope_repository.upsert_student_scope = AsyncMock(
        side_effect=StudentExamScopeConflictError(
            "Student account is already scoped to another exam."
        )
    )
    user_identity_repository = Mock()
    user_identity_repository.upsert_student = AsyncMock()
    use_case = _build_use_case(
        invite_service=invite_service,
        exam_repository=exam_repository,
        student_scope_repository=student_scope_repository,
        user_identity_repository=user_identity_repository,
    )

    with pytest.raises(StudentExamScopeConflictError):
        await use_case.execute(
            InviteStudentCommand(
                exam_id="exam-1",
                student_id="student-external-id",
                student_email="student@example.com",
                teacher_id="teacher-1",
            )
        )

    invite_service.invite_student.assert_awaited_once()
    user_identity_repository.upsert_student.assert_awaited_once()
    student_scope_repository.upsert_student_scope.assert_awaited_once()


@pytest.mark.asyncio
async def test_use_case_raises_exam_not_found() -> None:
    exam_repository = Mock()
    exam_repository.get_exam = AsyncMock(return_value=None)
    use_case = _build_use_case(exam_repository=exam_repository)

    with pytest.raises(ExamNotFoundError):
        await use_case.execute(
            InviteStudentCommand(
                exam_id="exam-missing",
                student_id="student-external-id",
                student_email="student@example.com",
                teacher_id="teacher-1",
            )
        )


@pytest.mark.asyncio
async def test_use_case_raises_exam_ownership_error() -> None:
    exam_repository = Mock()
    exam_repository.get_exam = AsyncMock(
        return_value=Exam(
            exam_id="exam-1",
            teacher_id="teacher-owner",
            title="Math Midterm",
            status=ExamStatus.DRAFT,
        )
    )
    use_case = _build_use_case(exam_repository=exam_repository)

    with pytest.raises(ExamOwnershipError):
        await use_case.execute(
            InviteStudentCommand(
                exam_id="exam-1",
                student_id="student-external-id",
                student_email="student@example.com",
                teacher_id="teacher-other",
            )
        )


@pytest.mark.asyncio
async def test_adapter_creates_cognito_user_and_sends_email() -> None:
    cognito = Mock()
    ses = Mock()
    cognito.admin_create_user = AsyncMock(
        return_value={
            "User": {
                "Attributes": [
                    {"Name": "sub", "Value": "student-sub-123"},
                    {"Name": "email", "Value": "student@example.com"},
                ]
            }
        }
    )
    cognito.admin_add_user_to_group = AsyncMock()
    ses.send_email = AsyncMock()
    adapter = CognitoSesStudentInviteAdapter(
        user_pool_id="pool-id",
        ses_from_address="noreply@example.com",
        cognito_client=cognito,
        ses_client=ses,
    )

    result = await adapter.invite_student(
        student_email="student@example.com", exam_id="exam-1"
    )

    assert result.cognito_sub == "student-sub-123"
    assert result.already_existed is False
    cognito.admin_create_user.assert_awaited_once()
    create_call = cognito.admin_create_user.call_args.kwargs
    assert create_call["MessageAction"] == "SUPPRESS"
    assert {"Name": "email", "Value": "student@example.com"} in create_call[
        "UserAttributes"
    ]
    cognito.admin_add_user_to_group.assert_awaited_once_with(
        UserPoolId="pool-id",
        Username="student@example.com",
        GroupName="students",
    )
    ses.send_email.assert_awaited_once()


def test_adapter_rejects_partial_injected_clients() -> None:
    with pytest.raises(ValueError, match="both be injected or both omitted"):
        CognitoSesStudentInviteAdapter(
            user_pool_id="pool-id",
            ses_from_address="noreply@example.com",
            cognito_client=Mock(),
            ses_client=None,
        )


@pytest.mark.asyncio
async def test_adapter_handles_existing_user_without_duplicate_account() -> None:
    cognito = Mock()
    ses = Mock()
    cognito.admin_create_user = AsyncMock(
        side_effect=_make_client_error(
            "UsernameExistsException",
            "Already exists",
        )
    )
    cognito.admin_get_user = AsyncMock(
        return_value={
            "UserAttributes": [
                {"Name": "sub", "Value": "existing-sub"},
            ]
        }
    )
    cognito.admin_set_user_password = AsyncMock()
    cognito.admin_add_user_to_group = AsyncMock()
    ses.send_email = AsyncMock()
    adapter = CognitoSesStudentInviteAdapter(
        user_pool_id="pool-id",
        ses_from_address="noreply@example.com",
        cognito_client=cognito,
        ses_client=ses,
    )

    result = await adapter.invite_student(
        student_email="student@example.com", exam_id="exam-1"
    )

    assert result.cognito_sub == "existing-sub"
    assert result.already_existed is True
    cognito.admin_get_user.assert_awaited_once()
    cognito.admin_set_user_password.assert_awaited_once()
    cognito.admin_add_user_to_group.assert_awaited_once()
    ses.send_email.assert_awaited_once()


def test_api_returns_200_on_successful_invite(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock(
        return_value=InviteStudentResult(
            student=Student(
                student_id="student-sub-123",
                email="student@example.com",
            ),
            re_invited=False,
        )
    )
    client.app.dependency_overrides[provide_invite_use_case] = lambda: mock_use_case
    client.app.dependency_overrides[require_teacher] = lambda: CurrentTeacher(
        teacher_id="teacher-1"
    )

    response = client.post(
        "/exams/exam-1/students/student-1/invite",
        json={"student_email": "student@example.com"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "student_id": "student-sub-123",
        "exam_id": "exam-1",
        "re_invited": False,
    }
    called_command = mock_use_case.execute.call_args.args[0]
    assert called_command.teacher_id == "teacher-1"


def test_api_returns_reinvited_true_on_reinvite(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock(
        return_value=InviteStudentResult(
            student=Student(
                student_id="student-sub-existing",
                email="student@example.com",
            ),
            re_invited=True,
        )
    )
    client.app.dependency_overrides[provide_invite_use_case] = lambda: mock_use_case
    client.app.dependency_overrides[require_teacher] = lambda: CurrentTeacher(
        teacher_id="teacher-1"
    )

    response = client.post(
        "/exams/exam-1/students/student-1/invite",
        json={"student_email": "student@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["re_invited"] is True


def test_api_returns_404_when_exam_not_found(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock(side_effect=ExamNotFoundError("exam not found"))
    client.app.dependency_overrides[provide_invite_use_case] = lambda: mock_use_case
    client.app.dependency_overrides[require_teacher] = lambda: CurrentTeacher(
        teacher_id="teacher-1"
    )

    response = client.post(
        "/exams/exam-404/students/student-1/invite",
        json={"student_email": "student@example.com"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "exam not found"


def test_api_returns_404_when_exam_not_found_at_ownership_verify(
    client: TestClient,
) -> None:
    mock_verify_uc = Mock()
    mock_verify_uc.execute = AsyncMock(
        side_effect=ExamNotFoundError("Exam exam-missing not found.")
    )
    client.app.dependency_overrides[get_verify_exam_ownership_use_case] = lambda: (
        mock_verify_uc
    )
    client.app.dependency_overrides.pop(verify_teacher_exam_ownership, None)
    client.app.dependency_overrides[require_teacher] = lambda: CurrentTeacher(
        teacher_id="teacher-1"
    )
    mock_invite_uc = Mock()
    mock_invite_uc.execute = AsyncMock()
    client.app.dependency_overrides[provide_invite_use_case] = lambda: mock_invite_uc

    response = client.post(
        "/exams/exam-missing/students/student-1/invite",
        json={"student_email": "student@example.com"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Exam exam-missing not found."
    mock_invite_uc.execute.assert_not_called()


def test_api_returns_404_when_teacher_does_not_own_exam(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock(side_effect=ExamOwnershipError("forbidden"))
    client.app.dependency_overrides[provide_invite_use_case] = lambda: mock_use_case
    client.app.dependency_overrides[require_teacher] = lambda: CurrentTeacher(
        teacher_id="teacher-1"
    )

    response = client.post(
        "/exams/exam-1/students/student-1/invite",
        json={"student_email": "student@example.com"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == EXAM_NOT_FOUND_FOR_CLIENT


def test_api_returns_409_on_student_exam_scope_conflict(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock(
        side_effect=StudentExamScopeConflictError("scope conflict")
    )
    client.app.dependency_overrides[provide_invite_use_case] = lambda: mock_use_case
    client.app.dependency_overrides[require_teacher] = lambda: CurrentTeacher(
        teacher_id="teacher-1"
    )

    response = client.post(
        "/exams/exam-1/students/student-1/invite",
        json={"student_email": "student@example.com"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "scope conflict"


def test_api_returns_401_when_token_invalid(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock()
    client.app.state.jwt_verifier.decode_and_verify_token = AsyncMock(
        side_effect=JWTError("invalid token")
    )
    client.app.dependency_overrides[provide_invite_use_case] = lambda: mock_use_case

    response = client.post(
        "/exams/exam-1/students/student-1/invite",
        json={"student_email": "student@example.com"},
        headers={"Authorization": "Bearer invalid.token.value"},
    )

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["code"] == "invalid_token"
    mock_use_case.execute.assert_not_called()


def test_api_returns_403_for_non_teacher_claim(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute = AsyncMock()
    client.app.state.jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={
            "sub": "teacher-1",
            "cognito:groups": ["students"],
        }
    )
    client.app.dependency_overrides[provide_invite_use_case] = lambda: mock_use_case

    response = client.post(
        "/exams/exam-1/students/student-1/invite",
        json={"student_email": "student@example.com"},
        headers={"Authorization": "Bearer valid.token.value"},
    )

    assert response.status_code == 403
    mock_use_case.execute.assert_not_called()


def test_student_scope_endpoint_returns_200_for_matching_student_scope(
    client: TestClient,
) -> None:
    client.app.state.jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={
            "sub": "student-sub-123",
            "cognito:groups": ["students"],
            "token_use": "id",
        }
    )
    client.app.state.invite_repository.get_student_scope = AsyncMock(
        return_value=Student(
            student_id="student-sub-123",
            email="student@example.com",
        )
    )

    response = client.get(
        "/exams/exam-1/students/student-sub-123/scope",
        headers={"Authorization": "Bearer valid.token.value"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "student_id": "student-sub-123",
        "exam_id": "exam-1",
        "email": "student@example.com",
    }


def test_student_scope_endpoint_returns_403_on_sub_mismatch(client: TestClient) -> None:
    client.app.state.jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={
            "sub": "student-sub-abc",
            "cognito:groups": ["students"],
            "token_use": "id",
        }
    )

    response = client.get(
        "/exams/exam-1/students/student-sub-xyz/scope",
        headers={"Authorization": "Bearer valid.token.value"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "own_data_violation"


def test_student_scope_endpoint_ignores_custom_exam_id_claim(
    client: TestClient,
) -> None:
    client.app.state.jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={
            "sub": "student-sub-123",
            "cognito:groups": ["students"],
            "custom:exam_id": "exam-from-token",
            "token_use": "id",
        }
    )
    client.app.state.invite_repository.get_student_scope = AsyncMock(
        return_value=Student(
            student_id="student-sub-123",
            email="student@example.com",
        )
    )

    response = client.get(
        "/exams/exam-from-path/students/student-sub-123/scope",
        headers={"Authorization": "Bearer valid.token.value"},
    )

    assert response.status_code == 200
    assert response.json()["exam_id"] == "exam-from-path"


def test_student_scope_endpoint_returns_404_when_scope_is_missing(
    client: TestClient,
) -> None:
    client.app.state.jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={
            "sub": "student-sub-123",
            "cognito:groups": ["students"],
            "token_use": "id",
        }
    )
    client.app.state.invite_repository.get_student_scope = AsyncMock(return_value=None)

    response = client.get(
        "/exams/exam-1/students/student-sub-123/scope",
        headers={"Authorization": "Bearer valid.token.value"},
    )

    assert response.status_code == 404
