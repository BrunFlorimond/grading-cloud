"""Tests for issue #14 — teacher uploads exam configuration files.

All test cases listed below are stubs to be implemented once the use cases,
adapters, and router are filled in.
"""

from __future__ import annotations

# --- GetExamConfigUploadUrlsUseCase ---

# TODO(#14): test_get_upload_urls_returns_presigned_urls_for_all_four_files
# TODO(#14): test_get_upload_urls_verifies_teacher_ownership_before_generating_urls
# TODO(#14): test_get_upload_urls_raises_exam_not_found_when_exam_missing
# TODO(#14): test_get_upload_urls_raises_ownership_error_when_wrong_teacher

# --- ConfirmExamConfigUseCase ---

# TODO(#14): test_confirm_config_returns_configured_status_when_all_files_present
# TODO(#14): test_confirm_config_raises_missing_files_error_when_devoir_absent
# TODO(#14): test_confirm_config_raises_missing_files_error_when_correction_absent
# TODO(#14): test_confirm_config_raises_missing_files_error_when_prompt_absent
# TODO(#14): test_confirm_config_raises_missing_files_error_when_grille_notation_absent
# TODO(#14): test_confirm_config_raises_invalid_json_error_for_malformed_devoir
# TODO(#14): test_confirm_config_raises_invalid_json_error_for_malformed_correction
# TODO(#14): test_confirm_config_raises_invalid_json_error_for_malformed_grille_notation
# TODO(#14): test_confirm_config_saves_config_s3_keys_to_repository
# TODO(#14): test_confirm_config_overwrites_previous_keys_on_re_upload

# --- S3ExamConfigStorage ---

# TODO(#14): test_generate_upload_urls_calls_presigned_url_for_each_of_four_config_files
# TODO(#14): test_generate_upload_urls_sets_expiry_to_900_seconds
# TODO(#14): test_generate_upload_urls_uses_correct_s3_prefix
# TODO(#14): test_all_files_exist_returns_true_for_each_present_file
# TODO(#14): test_all_files_exist_returns_false_for_absent_file
# TODO(#14): test_get_file_bytes_raises_missing_files_error_when_object_not_found

# --- DynamoDbExamConfigRepository ---

# TODO(#14): test_get_exam_for_config_returns_exam_when_metadata_item_exists
# TODO(#14): test_get_exam_for_config_returns_none_when_metadata_item_absent
# TODO(#14): test_save_exam_config_updates_dynamodb_metadata_with_s3_keys_and_configured_status
# TODO(#14): test_save_exam_config_uses_conditional_expression_to_prevent_phantom_writes

# --- config_router (TestClient) ---

# TODO(#14): test_post_upload_urls_requires_auth
# TODO(#14): test_post_upload_urls_returns_200_with_four_presigned_urls
# TODO(#14): test_post_upload_urls_returns_404_when_exam_not_found
# TODO(#14): test_post_upload_urls_returns_403_when_teacher_does_not_own_exam
# TODO(#14): test_post_confirm_requires_auth
# TODO(#14): test_post_confirm_returns_200_with_configured_status
# TODO(#14): test_post_confirm_returns_422_when_files_missing
# TODO(#14): test_post_confirm_returns_422_with_field_level_error_for_invalid_json
# TODO(#14): test_post_confirm_returns_200_on_re_upload_overwriting_previous_config
