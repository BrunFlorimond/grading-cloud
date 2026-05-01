"""Unit tests for the invite-student flow."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from grading_shared.domain.exam import Exam, ExamStatus
from jose import JWTError

from exam_api.api.invite_router import (
    CurrentTeacher,
    get_current_teacher,
    provide_invite_use_case,
    router,
)
from exam_api.application.invite_student import (
    InviteStudentCommand,
    InviteStudentResult,
    InviteStudentUseCase,
)
from exam_api.domain.errors import ExamNotFoundError, ExamOwnershipError
from exam_api.domain.student import Student
from exam_api.infrastructure.student_invite_adapter import CognitoSesStudentInviteAdapter
from exam_api.ports.student_invite_port import InviteStudentResult as PortInviteStudentResult


def _make_client_error(code: str, message: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": message}},
        operation_name="CognitoAction",
    )


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.state.student_invite_service = Mock(spec=["invite_student"])
    app.state.invite_repository = Mock(
        spec=["get_exam", "upsert_student_scope", "get_student_scope"]
    )
    app.state.jwt_verifier = Mock(spec=["decode_and_verify_token"])
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
) -> InviteStudentUseCase:
    return InviteStudentUseCase(
        invite_service=invite_service or Mock(),
        exam_repository=exam_repository or Mock(),
        student_scope_repository=student_scope_repository or Mock(),
    )


def test_use_case_returns_new_invite_result() -> None:
    invite_service = Mock()
    exam_repository = Mock()
    exam_repository.get_exam.return_value = Exam(
        exam_id="exam-1",
        teacher_id="teacher-1",
        title="Math Midterm",
        status=ExamStatus.DRAFT,
    )
    student_scope_repository = Mock()
    invite_service.invite_student.return_value = PortInviteStudentResult(
        cognito_sub="student-sub-123",
        already_existed=False,
    )
    use_case = _build_use_case(
        invite_service=invite_service,
        exam_repository=exam_repository,
        student_scope_repository=student_scope_repository,
    )

    result = use_case.execute(
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
            exam_id="exam-1",
            email="student@example.com",
        ),
        re_invited=False,
    )
    invite_service.invite_student.assert_called_once_with(
        student_email="student@example.com",
        exam_id="exam-1",
    )
    student_scope_repository.upsert_student_scope.assert_called_once()


def test_use_case_returns_reinvited_true_when_student_exists() -> None:
    invite_service = Mock()
    exam_repository = Mock()
    exam_repository.get_exam.return_value = Exam(
        exam_id="exam-1",
        teacher_id="teacher-1",
        title="Math Midterm",
        status=ExamStatus.DRAFT,
    )
    invite_service.invite_student.return_value = PortInviteStudentResult(
        cognito_sub="student-sub-existing",
        already_existed=True,
    )
    use_case = _build_use_case(invite_service=invite_service, exam_repository=exam_repository)

    result = use_case.execute(
        InviteStudentCommand(
            exam_id="exam-1",
            student_id="student-external-id",
            student_email="student@example.com",
            teacher_id="teacher-1",
        )
    )

    assert result.re_invited is True
    assert result.student.student_id == "student-sub-existing"


def test_use_case_raises_exam_not_found() -> None:
    exam_repository = Mock()
    exam_repository.get_exam.return_value = None
    use_case = _build_use_case(exam_repository=exam_repository)

    with pytest.raises(ExamNotFoundError):
        use_case.execute(
            InviteStudentCommand(
                exam_id="exam-missing",
                student_id="student-external-id",
                student_email="student@example.com",
                teacher_id="teacher-1",
            )
        )


def test_use_case_raises_exam_ownership_error() -> None:
    exam_repository = Mock()
    exam_repository.get_exam.return_value = Exam(
        exam_id="exam-1",
        teacher_id="teacher-owner",
        title="Math Midterm",
        status=ExamStatus.DRAFT,
    )
    use_case = _build_use_case(exam_repository=exam_repository)

    with pytest.raises(ExamOwnershipError):
        use_case.execute(
            InviteStudentCommand(
                exam_id="exam-1",
                student_id="student-external-id",
                student_email="student@example.com",
                teacher_id="teacher-other",
            )
        )


def test_adapter_creates_cognito_user_and_sends_email() -> None:
    cognito = Mock()
    ses = Mock()
    cognito.admin_create_user.return_value = {
        "User": {
            "Attributes": [
                {"Name": "sub", "Value": "student-sub-123"},
                {"Name": "email", "Value": "student@example.com"},
            ]
        }
    }
    adapter = CognitoSesStudentInviteAdapter(
        user_pool_id="pool-id",
        ses_from_address="noreply@example.com",
        cognito_client=cognito,
        ses_client=ses,
    )

    result = adapter.invite_student(student_email="student@example.com", exam_id="exam-1")

    assert result.cognito_sub == "student-sub-123"
    assert result.already_existed is False
    cognito.admin_create_user.assert_called_once()
    create_call = cognito.admin_create_user.call_args.kwargs
    assert create_call["MessageAction"] == "SUPPRESS"
    assert {"Name": "custom:role", "Value": "student"} in create_call["UserAttributes"]
    assert {"Name": "custom:exam_id", "Value": "exam-1"} in create_call["UserAttributes"]
    cognito.admin_add_user_to_group.assert_called_once_with(
        UserPoolId="pool-id",
        Username="student@example.com",
        GroupName="students",
    )
    ses.send_email.assert_called_once()


def test_adapter_handles_existing_user_without_duplicate_account() -> None:
    cognito = Mock()
    ses = Mock()
    cognito.admin_create_user.side_effect = _make_client_error(
        "UsernameExistsException",
        "Already exists",
    )
    cognito.admin_get_user.return_value = {
        "UserAttributes": [{"Name": "sub", "Value": "existing-sub"}]
    }
    adapter = CognitoSesStudentInviteAdapter(
        user_pool_id="pool-id",
        ses_from_address="noreply@example.com",
        cognito_client=cognito,
        ses_client=ses,
    )

    result = adapter.invite_student(student_email="student@example.com", exam_id="exam-1")

    assert result.cognito_sub == "existing-sub"
    assert result.already_existed is True
    cognito.admin_set_user_password.assert_called_once()
    cognito.admin_add_user_to_group.assert_called_once()
    ses.send_email.assert_called_once()


def test_api_returns_200_on_successful_invite(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute.return_value = InviteStudentResult(
        student=Student(
            student_id="student-sub-123",
            exam_id="exam-1",
            email="student@example.com",
        ),
        re_invited=False,
    )
    client.app.dependency_overrides[provide_invite_use_case] = lambda: mock_use_case
    client.app.dependency_overrides[get_current_teacher] = lambda: CurrentTeacher(
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
    mock_use_case.execute.return_value = InviteStudentResult(
        student=Student(
            student_id="student-sub-existing",
            exam_id="exam-1",
            email="student@example.com",
        ),
        re_invited=True,
    )
    client.app.dependency_overrides[provide_invite_use_case] = lambda: mock_use_case
    client.app.dependency_overrides[get_current_teacher] = lambda: CurrentTeacher(
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
    mock_use_case.execute.side_effect = ExamNotFoundError("exam not found")
    client.app.dependency_overrides[provide_invite_use_case] = lambda: mock_use_case
    client.app.dependency_overrides[get_current_teacher] = lambda: CurrentTeacher(
        teacher_id="teacher-1"
    )

    response = client.post(
        "/exams/exam-404/students/student-1/invite",
        json={"student_email": "student@example.com"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "exam not found"


def test_api_returns_403_when_teacher_does_not_own_exam(client: TestClient) -> None:
    mock_use_case = Mock()
    mock_use_case.execute.side_effect = ExamOwnershipError("forbidden")
    client.app.dependency_overrides[provide_invite_use_case] = lambda: mock_use_case
    client.app.dependency_overrides[get_current_teacher] = lambda: CurrentTeacher(
        teacher_id="teacher-1"
    )

    response = client.post(
        "/exams/exam-1/students/student-1/invite",
        json={"student_email": "student@example.com"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden"


def test_api_returns_401_when_token_invalid(client: TestClient) -> None:
    mock_use_case = Mock()
    client.app.state.jwt_verifier.decode_and_verify_token.side_effect = JWTError(
        "invalid token"
    )
    client.app.dependency_overrides[provide_invite_use_case] = lambda: mock_use_case

    response = client.post(
        "/exams/exam-1/students/student-1/invite",
        json={"student_email": "student@example.com"},
        headers={"Authorization": "Bearer invalid.token.value"},
    )

    assert response.status_code == 401
    mock_use_case.execute.assert_not_called()


def test_api_returns_403_for_non_teacher_claim(client: TestClient) -> None:
    mock_use_case = Mock()
    client.app.state.jwt_verifier.decode_and_verify_token.return_value = {
        "sub": "teacher-1",
        "custom:role": "student",
    }
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
    client.app.state.jwt_verifier.decode_and_verify_token.return_value = {
        "sub": "student-sub-123",
        "custom:role": "student",
        "custom:exam_id": "exam-1",
        "token_use": "id",
    }
    client.app.state.invite_repository.get_student_scope.return_value = Student(
        student_id="student-sub-123",
        exam_id="exam-1",
        email="student@example.com",
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
    client.app.state.jwt_verifier.decode_and_verify_token.return_value = {
        "sub": "student-sub-abc",
        "custom:role": "student",
        "custom:exam_id": "exam-1",
        "token_use": "id",
    }

    response = client.get(
        "/exams/exam-1/students/student-sub-xyz/scope",
        headers={"Authorization": "Bearer valid.token.value"},
    )

    assert response.status_code == 403


def test_student_scope_endpoint_returns_404_when_scope_is_missing(
    client: TestClient,
) -> None:
    client.app.state.jwt_verifier.decode_and_verify_token.return_value = {
        "sub": "student-sub-123",
        "custom:role": "student",
        "custom:exam_id": "exam-1",
        "token_use": "id",
    }
    client.app.state.invite_repository.get_student_scope.return_value = None

    response = client.get(
        "/exams/exam-1/students/student-sub-123/scope",
        headers={"Authorization": "Bearer valid.token.value"},
    )

    assert response.status_code == 404
