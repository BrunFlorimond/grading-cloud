"""Tests for issue #13 — teacher creates a new exam.

TODO(#13): implement the following test cases:

Use case unit tests (test_create_exam_use_case):
  - test_create_exam_returns_uuid_v4
      Verify exam_id in the result matches UUID v4 format.
  - test_create_exam_returns_status_created
      Verify result.status == "CREATED".
  - test_create_exam_persists_exam_with_repository
      Assert create_exam was called once with the built Exam aggregate.
  - test_create_exam_with_empty_title_raises_error
      ExamTitleRequiredError is raised when title is "".
  - test_create_exam_with_title_over_120_chars_raises_error
      ExamTitleTooLongError is raised when len(title) > 120.
  - test_create_exam_sets_teacher_id_from_command
      Exam.teacher_id equals command.teacher_id.

Use case unit tests (test_list_teacher_exams_use_case):
  - test_list_exams_delegates_to_repository
      Assert list_teacher_exams was called with correct teacher_id, limit, cursor.
  - test_list_exams_returns_page_from_repository
      Result page is forwarded as-is from the repository.

API integration tests (test_exam_router, using TestClient + AsyncMock repository):
  - test_post_exams_requires_auth
      POST /exams without Authorization returns 401.
  - test_post_exams_returns_201_with_exam_id_and_status
      POST /exams with valid body returns 201, exam_id is UUID, status=="CREATED".
  - test_post_exams_missing_title_returns_422
      POST /exams with missing title field returns 422.
  - test_post_exams_title_too_long_returns_422
      POST /exams with title > 120 chars returns 422.
  - test_get_exams_requires_auth
      GET /exams without Authorization returns 401.
  - test_get_exams_returns_paginated_list
      GET /exams returns 200 with items list and next_cursor.

DynamoDB adapter unit tests (test_dynamodb_exam_creation_repository, using moto or AsyncMock):
  - test_create_exam_writes_metadata_item
      PK=EXAM#{exam_id} SK=METADATA exists in the table after create_exam.
  - test_create_exam_writes_teacher_ownership_edge
      PK=TEACHER#{teacher_id} SK=EXAM#{exam_id} exists after create_exam.
  - test_list_teacher_exams_returns_only_own_exams
      Exams from another teacher are not returned.
  - test_list_teacher_exams_ordered_by_created_at_desc
      Items are returned newest first.
  - test_list_teacher_exams_cursor_pagination
      second page uses LastEvaluatedKey from first page.
"""
