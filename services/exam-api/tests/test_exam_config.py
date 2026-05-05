"""Tests for issue #14 — teacher uploads exam configuration files."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock, create_autospec

import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from grading_shared.domain.exam import Exam, ExamStatus

from exam_api.api.config_router import router as config_router
from exam_api.composition import (
    get_exam_config_repository,
    get_exam_ownership_repository,
)
from exam_api.api.http_error_handlers import register_http_error_handlers
from exam_api.application.confirm_exam_config import (
    ConfirmExamConfigCommand,
    ConfirmExamConfigUseCase,
)
from exam_api.application.get_exam_config_upload_urls import (
    GetExamConfigUploadUrlsCommand,
    GetExamConfigUploadUrlsUseCase,
    PresignedPostBundle,
)
from exam_api.domain.errors import (
    EXAM_NOT_FOUND_FOR_CLIENT,
    ExamConfigInvalidJsonError,
    ExamConfigMissingFilesError,
    ExamConfigWrongStatusError,
    ExamNotFoundError,
    ExamOwnershipError,
)
from exam_api.infrastructure.s3_exam_config_storage import S3ExamConfigStorage
from exam_api.ports.exam_config_storage_port import CONFIG_FILES
from exam_api.ports.jwt_verifier_port import JwtVerifierPort


def _mock_presigned_posts(exam_id: str = "e1") -> dict[str, dict[str, Any]]:
    return {
        name: {
            "url": f"https://bucket.example/post/{name}",
            "fields": {
                "key": f"exams/{exam_id}/config/{name}",
                "policy": "policy",
            },
        }
        for name in CONFIG_FILES
    }


def _config_object_key(*, exam_id: str, filename: str) -> str:
    return f"exams/{exam_id}/config/{filename}"


def _attach_confirm_storage_keys(storage: Mock) -> None:
    storage.config_object_key = _config_object_key


# --- GetExamConfigUploadUrlsUseCase ---


@pytest.mark.asyncio
async def test_get_upload_urls_returns_presigned_urls_for_all_four_files() -> None:
    raw = _mock_presigned_posts("e1")
    ownership = Mock()
    ownership.verify_teacher_owns_exam = AsyncMock()
    storage = Mock()
    storage.generate_upload_urls = AsyncMock(return_value=raw)

    use_case = GetExamConfigUploadUrlsUseCase(
        exam_ownership=ownership,
        config_storage=storage,
    )
    result = await use_case.execute(
        GetExamConfigUploadUrlsCommand(teacher_id="t1", exam_id="e1")
    )

    expected = {
        fname: PresignedPostBundle(
            url=data["url"],
            fields={str(k): str(v) for k, v in data["fields"].items()},
        )
        for fname, data in raw.items()
    }
    assert result.upload_urls == expected
    storage.generate_upload_urls.assert_awaited_once_with(exam_id="e1")


@pytest.mark.asyncio
async def test_get_upload_urls_verifies_teacher_ownership_before_generating_urls() -> (
    None
):
    ownership = Mock()
    ownership.verify_teacher_owns_exam = AsyncMock()
    storage = Mock()
    storage.generate_upload_urls = AsyncMock(return_value={})

    use_case = GetExamConfigUploadUrlsUseCase(
        exam_ownership=ownership,
        config_storage=storage,
    )
    await use_case.execute(
        GetExamConfigUploadUrlsCommand(teacher_id="t1", exam_id="e1")
    )

    ownership.verify_teacher_owns_exam.assert_awaited_once_with(
        teacher_id="t1",
        exam_id="e1",
    )
    storage.generate_upload_urls.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_upload_urls_raises_exam_not_found_when_exam_missing() -> None:
    ownership = Mock()
    ownership.verify_teacher_owns_exam = AsyncMock(
        side_effect=ExamNotFoundError("Exam e1 not found.")
    )
    storage = Mock()
    storage.generate_upload_urls = AsyncMock()

    use_case = GetExamConfigUploadUrlsUseCase(
        exam_ownership=ownership,
        config_storage=storage,
    )

    with pytest.raises(ExamNotFoundError):
        await use_case.execute(
            GetExamConfigUploadUrlsCommand(teacher_id="t1", exam_id="e1")
        )
    storage.generate_upload_urls.assert_not_called()


@pytest.mark.asyncio
async def test_get_upload_urls_raises_ownership_error_when_wrong_teacher() -> None:
    ownership = Mock()
    ownership.verify_teacher_owns_exam = AsyncMock(
        side_effect=ExamOwnershipError("Teacher t1 does not own exam e1.")
    )
    storage = Mock()
    storage.generate_upload_urls = AsyncMock()

    use_case = GetExamConfigUploadUrlsUseCase(
        exam_ownership=ownership,
        config_storage=storage,
    )

    with pytest.raises(ExamOwnershipError):
        await use_case.execute(
            GetExamConfigUploadUrlsCommand(teacher_id="t1", exam_id="e1")
        )


# --- ConfirmExamConfigUseCase ---


def _sample_exam(*, status: ExamStatus = ExamStatus.CREATED) -> Exam:
    return Exam(
        exam_id="e1",
        teacher_id="t1",
        title="Midterm",
        status=status,
        created_at="2026-05-01T12:00:00.000000Z",
    )


@pytest.mark.asyncio
async def test_confirm_config_returns_configured_status_when_all_files_present() -> (
    None
):
    ownership = Mock()
    ownership.verify_teacher_owns_exam = AsyncMock()
    storage = Mock()
    _attach_confirm_storage_keys(storage)
    storage.all_files_exist = AsyncMock(
        return_value={name: True for name in CONFIG_FILES}
    )
    storage.get_file_bytes = AsyncMock(
        side_effect=lambda *, exam_id, filename: (
            b"{}" if filename.endswith(".json") else b"x"
        )
    )
    repo = Mock()
    repo.get_exam_for_config = AsyncMock(return_value=_sample_exam())
    repo.save_exam_config = AsyncMock()

    use_case = ConfirmExamConfigUseCase(
        exam_ownership=ownership,
        config_storage=storage,
        config_repository=repo,
    )
    result = await use_case.execute(
        ConfirmExamConfigCommand(teacher_id="t1", exam_id="e1")
    )

    assert result.exam_id == "e1"
    assert result.status == "CONFIGURED"
    repo.save_exam_config.assert_awaited_once()


@pytest.mark.asyncio
async def test_confirm_config_raises_missing_files_error_when_devoir_absent() -> None:
    ownership = Mock()
    ownership.verify_teacher_owns_exam = AsyncMock()
    presence = {name: True for name in CONFIG_FILES}
    presence["devoir.json"] = False
    storage = Mock()
    storage.all_files_exist = AsyncMock(return_value=presence)
    repo = Mock()
    repo.get_exam_for_config = AsyncMock(return_value=_sample_exam())

    use_case = ConfirmExamConfigUseCase(
        exam_ownership=ownership,
        config_storage=storage,
        config_repository=repo,
    )

    with pytest.raises(ExamConfigMissingFilesError) as excinfo:
        await use_case.execute(ConfirmExamConfigCommand(teacher_id="t1", exam_id="e1"))
    assert "devoir.json" in excinfo.value.missing_filenames


@pytest.mark.asyncio
async def test_confirm_config_raises_missing_files_error_when_correction_absent() -> (
    None
):
    ownership = Mock()
    ownership.verify_teacher_owns_exam = AsyncMock()
    presence = {name: True for name in CONFIG_FILES}
    presence["correction.json"] = False
    storage = Mock()
    storage.all_files_exist = AsyncMock(return_value=presence)
    repo = Mock()
    repo.get_exam_for_config = AsyncMock(return_value=_sample_exam())

    use_case = ConfirmExamConfigUseCase(
        exam_ownership=ownership,
        config_storage=storage,
        config_repository=repo,
    )

    with pytest.raises(ExamConfigMissingFilesError):
        await use_case.execute(ConfirmExamConfigCommand(teacher_id="t1", exam_id="e1"))


@pytest.mark.asyncio
async def test_confirm_config_raises_missing_files_error_when_prompt_absent() -> None:
    ownership = Mock()
    ownership.verify_teacher_owns_exam = AsyncMock()
    presence = {name: True for name in CONFIG_FILES}
    presence["prompt.txt"] = False
    storage = Mock()
    storage.all_files_exist = AsyncMock(return_value=presence)
    repo = Mock()
    repo.get_exam_for_config = AsyncMock(return_value=_sample_exam())

    use_case = ConfirmExamConfigUseCase(
        exam_ownership=ownership,
        config_storage=storage,
        config_repository=repo,
    )

    with pytest.raises(ExamConfigMissingFilesError):
        await use_case.execute(ConfirmExamConfigCommand(teacher_id="t1", exam_id="e1"))


@pytest.mark.asyncio
async def test_confirm_config_raises_missing_files_error_when_grille_notation_absent() -> (
    None
):
    ownership = Mock()
    ownership.verify_teacher_owns_exam = AsyncMock()
    presence = {name: True for name in CONFIG_FILES}
    presence["grille_notation.json"] = False
    storage = Mock()
    storage.all_files_exist = AsyncMock(return_value=presence)
    repo = Mock()
    repo.get_exam_for_config = AsyncMock(return_value=_sample_exam())

    use_case = ConfirmExamConfigUseCase(
        exam_ownership=ownership,
        config_storage=storage,
        config_repository=repo,
    )

    with pytest.raises(ExamConfigMissingFilesError):
        await use_case.execute(ConfirmExamConfigCommand(teacher_id="t1", exam_id="e1"))


@pytest.mark.asyncio
async def test_confirm_config_raises_invalid_json_error_for_malformed_devoir() -> None:
    ownership = Mock()
    ownership.verify_teacher_owns_exam = AsyncMock()
    storage = Mock()
    _attach_confirm_storage_keys(storage)
    storage.all_files_exist = AsyncMock(
        return_value={name: True for name in CONFIG_FILES}
    )

    async def _bytes(*, exam_id: str, filename: str) -> bytes:
        if filename == "devoir.json":
            return b"{"
        if filename.endswith(".json"):
            return b"{}"
        return b"plain"

    storage.get_file_bytes = AsyncMock(side_effect=_bytes)
    repo = Mock()
    repo.get_exam_for_config = AsyncMock(return_value=_sample_exam())

    use_case = ConfirmExamConfigUseCase(
        exam_ownership=ownership,
        config_storage=storage,
        config_repository=repo,
    )

    with pytest.raises(ExamConfigInvalidJsonError) as excinfo:
        await use_case.execute(ConfirmExamConfigCommand(teacher_id="t1", exam_id="e1"))
    assert excinfo.value.filename == "devoir.json"


@pytest.mark.asyncio
async def test_confirm_config_raises_invalid_json_error_for_malformed_correction() -> (
    None
):
    ownership = Mock()
    ownership.verify_teacher_owns_exam = AsyncMock()
    storage = Mock()
    _attach_confirm_storage_keys(storage)
    storage.all_files_exist = AsyncMock(
        return_value={name: True for name in CONFIG_FILES}
    )

    async def _bytes(*, exam_id: str, filename: str) -> bytes:
        if filename == "correction.json":
            return b"{bad"
        if filename.endswith(".json"):
            return b"{}"
        return b"plain"

    storage.get_file_bytes = AsyncMock(side_effect=_bytes)
    repo = Mock()
    repo.get_exam_for_config = AsyncMock(return_value=_sample_exam())

    use_case = ConfirmExamConfigUseCase(
        exam_ownership=ownership,
        config_storage=storage,
        config_repository=repo,
    )

    with pytest.raises(ExamConfigInvalidJsonError) as excinfo:
        await use_case.execute(ConfirmExamConfigCommand(teacher_id="t1", exam_id="e1"))
    assert excinfo.value.filename == "correction.json"


@pytest.mark.asyncio
async def test_confirm_config_raises_invalid_json_error_for_malformed_grille_notation() -> (
    None
):
    ownership = Mock()
    ownership.verify_teacher_owns_exam = AsyncMock()
    storage = Mock()
    _attach_confirm_storage_keys(storage)
    storage.all_files_exist = AsyncMock(
        return_value={name: True for name in CONFIG_FILES}
    )

    async def _bytes(*, exam_id: str, filename: str) -> bytes:
        if filename == "grille_notation.json":
            return b"not-json"
        if filename.endswith(".json"):
            return b"{}"
        return b"plain"

    storage.get_file_bytes = AsyncMock(side_effect=_bytes)
    repo = Mock()
    repo.get_exam_for_config = AsyncMock(return_value=_sample_exam())

    use_case = ConfirmExamConfigUseCase(
        exam_ownership=ownership,
        config_storage=storage,
        config_repository=repo,
    )

    with pytest.raises(ExamConfigInvalidJsonError) as excinfo:
        await use_case.execute(ConfirmExamConfigCommand(teacher_id="t1", exam_id="e1"))
    assert excinfo.value.filename == "grille_notation.json"


@pytest.mark.asyncio
async def test_confirm_config_saves_config_s3_keys_to_repository() -> None:
    ownership = Mock()
    ownership.verify_teacher_owns_exam = AsyncMock()
    storage = Mock()
    _attach_confirm_storage_keys(storage)
    storage.all_files_exist = AsyncMock(
        return_value={name: True for name in CONFIG_FILES}
    )
    storage.get_file_bytes = AsyncMock(
        side_effect=lambda *, exam_id, filename: (
            b"{}" if filename.endswith(".json") else b"x"
        )
    )
    repo = Mock()
    repo.get_exam_for_config = AsyncMock(return_value=_sample_exam())
    repo.save_exam_config = AsyncMock()

    use_case = ConfirmExamConfigUseCase(
        exam_ownership=ownership,
        config_storage=storage,
        config_repository=repo,
    )
    await use_case.execute(ConfirmExamConfigCommand(teacher_id="t1", exam_id="e1"))

    kwargs = repo.save_exam_config.await_args.kwargs
    assert kwargs["teacher_id"] == "t1"
    assert kwargs["created_at"] == "2026-05-01T12:00:00.000000Z"
    assert kwargs["config_s3_keys"]["devoir.json"] == "exams/e1/config/devoir.json"


@pytest.mark.asyncio
async def test_confirm_config_overwrites_previous_keys_on_re_upload() -> None:
    ownership = Mock()
    ownership.verify_teacher_owns_exam = AsyncMock()
    storage = Mock()
    _attach_confirm_storage_keys(storage)
    storage.all_files_exist = AsyncMock(
        return_value={name: True for name in CONFIG_FILES}
    )
    storage.get_file_bytes = AsyncMock(
        side_effect=lambda *, exam_id, filename: (
            b"{}" if filename.endswith(".json") else b"x"
        )
    )
    repo = Mock()
    repo.get_exam_for_config = AsyncMock(
        return_value=_sample_exam(status=ExamStatus.CONFIGURED)
    )
    repo.save_exam_config = AsyncMock()

    use_case = ConfirmExamConfigUseCase(
        exam_ownership=ownership,
        config_storage=storage,
        config_repository=repo,
    )
    await use_case.execute(ConfirmExamConfigCommand(teacher_id="t1", exam_id="e1"))

    repo.save_exam_config.assert_awaited_once()


@pytest.mark.asyncio
async def test_confirm_config_raises_wrong_status_when_exam_ready() -> None:
    ownership = Mock()
    ownership.verify_teacher_owns_exam = AsyncMock()
    storage = Mock()
    repo = Mock()
    repo.get_exam_for_config = AsyncMock(
        return_value=_sample_exam(status=ExamStatus.READY)
    )

    use_case = ConfirmExamConfigUseCase(
        exam_ownership=ownership,
        config_storage=storage,
        config_repository=repo,
    )

    with pytest.raises(ExamConfigWrongStatusError):
        await use_case.execute(ConfirmExamConfigCommand(teacher_id="t1", exam_id="e1"))


# --- S3ExamConfigStorage ---


@pytest.mark.asyncio
async def test_generate_upload_urls_calls_presigned_post_for_each_of_four_config_files() -> (
    None
):
    client = AsyncMock()
    client.generate_presigned_post = AsyncMock(
        return_value={"url": "https://u", "fields": {"key": "k"}}
    )

    storage = S3ExamConfigStorage(
        bucket_name="cfg-bucket",
        s3_client=client,
    )
    await storage.generate_upload_urls(exam_id="ex1")

    assert client.generate_presigned_post.await_count == len(CONFIG_FILES)


@pytest.mark.asyncio
async def test_generate_upload_urls_sets_expiry_to_900_seconds() -> None:
    client = AsyncMock()
    client.generate_presigned_post = AsyncMock(
        return_value={"url": "https://u", "fields": {}}
    )

    storage = S3ExamConfigStorage(bucket_name="b", s3_client=client)
    await storage.generate_upload_urls(exam_id="ex1")

    assert client.generate_presigned_post.await_args.kwargs["ExpiresIn"] == 900


@pytest.mark.asyncio
async def test_generate_upload_urls_uses_correct_s3_prefix_and_size_policy() -> None:
    client = AsyncMock()
    client.generate_presigned_post = AsyncMock(
        return_value={"url": "https://u", "fields": {}}
    )

    storage = S3ExamConfigStorage(bucket_name="my-bucket", s3_client=client)
    await storage.generate_upload_urls(exam_id="ex-uuid")

    keys = [call.args[1] for call in client.generate_presigned_post.await_args_list]
    assert "exams/ex-uuid/config/devoir.json" in keys
    conds = client.generate_presigned_post.await_args.kwargs["Conditions"]
    assert ["content-length-range", 0, 10 * 1024 * 1024] in conds


@pytest.mark.asyncio
async def test_all_files_exist_returns_true_for_each_present_file() -> None:
    async def _head(**kwargs: object) -> dict[str, object]:
        return {}

    client = AsyncMock()
    client.head_object = AsyncMock(side_effect=_head)

    storage = S3ExamConfigStorage(bucket_name="b", s3_client=client)
    out = await storage.all_files_exist(exam_id="e1")

    assert all(out[name] for name in CONFIG_FILES)


@pytest.mark.asyncio
async def test_all_files_exist_returns_false_for_absent_file() -> None:
    calls = {"n": 0}

    async def _head(**kwargs: object) -> dict[str, object]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )
        return {}

    client = AsyncMock()
    client.head_object = AsyncMock(side_effect=_head)

    storage = S3ExamConfigStorage(bucket_name="b", s3_client=client)
    out = await storage.all_files_exist(exam_id="e1")

    assert out[CONFIG_FILES[0]] is False
    assert out[CONFIG_FILES[1]] is True


@pytest.mark.asyncio
async def test_get_file_bytes_raises_missing_files_error_when_object_not_found() -> (
    None
):
    client = AsyncMock()
    client.get_object = AsyncMock(
        side_effect=ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "no"}},
            "GetObject",
        )
    )

    storage = S3ExamConfigStorage(bucket_name="b", s3_client=client)

    with pytest.raises(ExamConfigMissingFilesError) as excinfo:
        await storage.get_file_bytes(exam_id="e1", filename="devoir.json")
    assert excinfo.value.missing_filenames == ["devoir.json"]


# --- config_router (TestClient) ---


@pytest.fixture
def config_client_bundle() -> tuple[TestClient, Mock, Mock, Mock]:
    app = FastAPI()
    register_http_error_handlers(app)
    app.include_router(config_router)

    ownership = Mock()
    ownership.verify_teacher_owns_exam = AsyncMock()

    storage = Mock()
    _attach_confirm_storage_keys(storage)
    storage.generate_upload_urls = AsyncMock(return_value=_mock_presigned_posts("e1"))
    storage.all_files_exist = AsyncMock(
        return_value={name: True for name in CONFIG_FILES}
    )
    storage.get_file_bytes = AsyncMock(
        side_effect=lambda *, exam_id, filename: (
            b"{}" if filename.endswith(".json") else b"x"
        )
    )

    repo = Mock()
    repo.get_exam_for_config = AsyncMock(
        return_value=_sample_exam(),
    )
    repo.save_exam_config = AsyncMock()

    jwt_verifier = create_autospec(JwtVerifierPort, instance=True)
    jwt_verifier.decode_and_verify_token = AsyncMock(
        return_value={
            "sub": "teacher-1",
            "cognito:groups": ["teachers"],
            "token_use": "id",
        }
    )

    app.dependency_overrides[get_exam_ownership_repository] = lambda: ownership
    app.dependency_overrides[get_exam_config_repository] = lambda: repo
    app.state.exam_config_storage = storage
    app.state.jwt_verifier = jwt_verifier

    client = TestClient(app)
    try:
        yield client, ownership, storage, repo
    finally:
        app.dependency_overrides.clear()


def test_post_upload_urls_requires_auth() -> None:
    app = FastAPI()
    register_http_error_handlers(app)
    app.include_router(config_router)
    app.state.jwt_verifier = create_autospec(JwtVerifierPort, instance=True)
    client = TestClient(app)

    response = client.post("/exams/e1/config/upload-urls")

    assert response.status_code == 401


def test_post_upload_urls_returns_200_with_four_presigned_urls(
    config_client_bundle: tuple[TestClient, Mock, Mock, Mock],
) -> None:
    client, _, storage, _ = config_client_bundle

    response = client.post(
        "/exams/e1/config/upload-urls",
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["upload_urls"]) == 4
    assert body["upload_urls"]["devoir.json"]["url"].startswith("http")
    assert "fields" in body["upload_urls"]["devoir.json"]
    storage.generate_upload_urls.assert_awaited_once()


def test_post_upload_urls_returns_404_when_exam_not_found(
    config_client_bundle: tuple[TestClient, Mock, Mock, Mock],
) -> None:
    client, ownership, _, _ = config_client_bundle
    ownership.verify_teacher_owns_exam = AsyncMock(
        side_effect=ExamNotFoundError("Exam e1 not found.")
    )

    response = client.post(
        "/exams/e1/config/upload-urls",
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 404


def test_post_upload_urls_returns_404_when_teacher_does_not_own_exam(
    config_client_bundle: tuple[TestClient, Mock, Mock, Mock],
) -> None:
    client, ownership, _, _ = config_client_bundle
    ownership.verify_teacher_owns_exam = AsyncMock(
        side_effect=ExamOwnershipError("no access")
    )

    response = client.post(
        "/exams/e1/config/upload-urls",
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == EXAM_NOT_FOUND_FOR_CLIENT


def test_post_confirm_requires_auth() -> None:
    app = FastAPI()
    register_http_error_handlers(app)
    app.include_router(config_router)
    app.state.jwt_verifier = create_autospec(JwtVerifierPort, instance=True)
    client = TestClient(app)

    response = client.post("/exams/e1/config/confirm")

    assert response.status_code == 401


def test_post_confirm_returns_200_with_configured_status(
    config_client_bundle: tuple[TestClient, Mock, Mock, Mock],
) -> None:
    client, _, _, repo = config_client_bundle

    response = client.post(
        "/exams/e1/config/confirm",
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 200
    assert response.json() == {"exam_id": "e1", "status": "CONFIGURED"}
    repo.save_exam_config.assert_awaited_once()


def test_post_confirm_returns_422_when_files_missing(
    config_client_bundle: tuple[TestClient, Mock, Mock, Mock],
) -> None:
    client, _, storage, _ = config_client_bundle
    storage.all_files_exist = AsyncMock(
        return_value={name: (name != "devoir.json") for name in CONFIG_FILES}
    )

    response = client.post(
        "/exams/e1/config/confirm",
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["missing"] == ["devoir.json"]


def test_post_confirm_returns_422_with_field_level_error_for_invalid_json(
    config_client_bundle: tuple[TestClient, Mock, Mock, Mock],
) -> None:
    client, _, storage, _ = config_client_bundle

    async def _bad_bytes(*, exam_id: str, filename: str) -> bytes:
        if filename == "devoir.json":
            return b"{"
        if filename.endswith(".json"):
            return b"{}"
        return b"t"

    storage.get_file_bytes = AsyncMock(side_effect=_bad_bytes)

    response = client.post(
        "/exams/e1/config/confirm",
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail[0]["loc"] == ["body", "devoir.json"]
    assert "msg" in detail[0]


def test_post_confirm_returns_200_on_re_upload_overwriting_previous_config(
    config_client_bundle: tuple[TestClient, Mock, Mock, Mock],
) -> None:
    client, _, _, repo = config_client_bundle
    repo.get_exam_for_config = AsyncMock(
        return_value=_sample_exam(status=ExamStatus.CONFIGURED)
    )

    response = client.post(
        "/exams/e1/config/confirm",
        headers={"Authorization": "Bearer fake"},
    )

    assert response.status_code == 200
    repo.save_exam_config.assert_awaited_once()
