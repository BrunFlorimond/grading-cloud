"""Tests for issue #16 — teacher views exam detail and per-student pipeline status."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Use case: GetExamDetailUseCase
# ---------------------------------------------------------------------------

# TODO(#16): test_get_exam_detail_returns_metadata_and_status_counts
#   — mock repository returning ExamDetail with status_counts
#   — assert use case result matches repository return value

# TODO(#16): test_get_exam_detail_propagates_exam_not_found_error
#   — mock repository raising ExamNotFoundError
#   — assert use case re-raises ExamNotFoundError

# ---------------------------------------------------------------------------
# Use case: ListExamStudentStatusesUseCase
# ---------------------------------------------------------------------------

# TODO(#16): test_list_exam_student_statuses_returns_page
#   — mock repository returning StudentPipelinePage with pdf_available values
#   — assert result matches repository return

# TODO(#16): test_list_exam_student_statuses_propagates_invalid_cursor_error
#   — mock repository raising InvalidExamListCursorError
#   — assert use case re-raises

# ---------------------------------------------------------------------------
# Repository: DynamoDbExamDetailRepository.get_exam_detail
# ---------------------------------------------------------------------------

# TODO(#16): test_get_exam_detail_queries_correct_pk
#   — mock DynamoDB Query, assert PK = "EXAM#{exam_id}"
#   — assert METADATA item parsed into ExamDetail fields

# TODO(#16): test_get_exam_detail_computes_status_counts_from_student_items
#   — DynamoDB returns 3 STUDENT# items with mixed submission_status
#   — assert status_counts.pending == expected count

# TODO(#16): test_get_exam_detail_raises_exam_not_found_when_metadata_missing
#   — Query returns no METADATA item
#   — assert ExamNotFoundError raised

# TODO(#16): test_get_exam_detail_includes_pipeline_timestamps_when_present
#   — METADATA item includes pipeline_started_at attribute
#   — assert ExamDetail.pipeline_started_at is populated

# ---------------------------------------------------------------------------
# Repository: DynamoDbExamDetailRepository.list_exam_student_statuses
# ---------------------------------------------------------------------------

# TODO(#16): test_list_exam_student_statuses_queries_correct_pk_and_sk_prefix
#   — assert Query uses PK = "EXAM#{exam_id}" and SK begins_with "STUDENT#"

# TODO(#16): test_list_exam_student_statuses_decodes_cursor_correctly
#   — provide base64 encoded cursor, assert ExclusiveStartKey forwarded to DynamoDB

# TODO(#16): test_list_exam_student_statuses_raises_on_invalid_cursor
#   — provide malformed cursor string
#   — assert InvalidExamListCursorError raised

# TODO(#16): test_list_exam_student_statuses_encodes_next_cursor
#   — DynamoDB returns LastEvaluatedKey
#   — assert next_cursor is base64 urlsafe encoded JSON of that key

# TODO(#16): test_list_exam_student_statuses_pdf_available_flag
#   — student item has pdf_available attribute set to True
#   — assert StudentPipelineStatus.pdf_available == True

# ---------------------------------------------------------------------------
# Router: GET /exams/{exam_id}
# ---------------------------------------------------------------------------

# TODO(#16): test_get_exam_detail_endpoint_returns_200
#   — mock JWT verifier (teacher), mock ownership check, mock use case
#   — GET /exams/{exam_id} → 200 with ExamDetailResponse body

# TODO(#16): test_get_exam_detail_endpoint_returns_404_when_not_found
#   — use case raises ExamNotFoundError
#   — assert 404 response

# TODO(#16): test_get_exam_detail_endpoint_requires_teacher_auth
#   — no Authorization header → 401

# TODO(#16): test_get_exam_detail_endpoint_returns_403_when_not_owner
#   — ownership check raises ExamOwnershipError → 403

# ---------------------------------------------------------------------------
# Router: GET /exams/{exam_id}/students  (updated with pdf_available)
# ---------------------------------------------------------------------------

# TODO(#16): test_list_student_statuses_endpoint_returns_200_with_pdf_flag
#   — mock JWT verifier (teacher), mock ownership, mock use case
#   — GET /exams/{exam_id}/students → 200 with pdf_available per item

# TODO(#16): test_list_student_statuses_endpoint_requires_teacher_auth
#   — no Authorization header → 401

# TODO(#16): test_list_student_statuses_endpoint_bad_cursor_returns_422
#   — use case raises InvalidExamListCursorError → 422

# TODO(#16): test_list_student_statuses_endpoint_pagination_params_forwarded
#   — query params limit=5&cursor=abc forwarded to use case command
