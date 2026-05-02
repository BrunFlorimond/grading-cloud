"""Tests for issue #15 — teacher adds students to an exam.

All test cases are stubs (pytest.mark.skip) to be implemented after the use cases
and infrastructure adapter are filled in.

Cases to implement
------------------

AddStudentsUseCase
  - test_add_students_returns_created_list
      Command with 2 students → result.created has 2 EnrolledStudent items.
  - test_add_students_assigns_uuid_when_student_id_absent
      StudentInput(student_id=None) → EnrolledStudent.student_id is a valid UUID v4.
  - test_add_students_keeps_provided_student_id
      StudentInput(student_id="EL-001") → EnrolledStudent.student_id == "EL-001".
  - test_add_students_sets_submission_status_pending
      All created students have submission_status == SubmissionStatus.PENDING.
  - test_add_students_raises_when_batch_exceeds_50
      Command with 51 StudentInput items → StudentBatchTooLargeError.
  - test_add_students_raises_on_duplicate_student_id
      Repository raises DuplicateStudentError → use case propagates it.
  - test_add_students_raises_on_exam_not_found
      Ownership check raises EnrollmentExamNotFoundError → propagated.
  - test_add_students_raises_on_wrong_owner
      Ownership check raises EnrollmentExamOwnershipError → propagated.

ListExamStudentsUseCase
  - test_list_exam_students_delegates_to_repository
      execute() calls enrollment_repository.list_exam_students with correct args.
  - test_list_exam_students_returns_page_from_repository
      Repository returns a page → use case returns it unchanged.

student_router (TestClient)
  - test_post_students_requires_auth
      No Authorization header → 401.
  - test_post_students_returns_201_with_created_list
      Valid batch of 2 students → 201, body.created has 2 items.
  - test_post_students_empty_body_returns_422
      body = [] → 422 (or configurable behaviour — check AC).
  - test_post_students_batch_over_50_returns_422
      51 students in body → 422.
  - test_post_students_duplicate_student_id_returns_409
      Use case raises DuplicateStudentError → 409.
  - test_post_students_exam_not_found_returns_404
      Ownership guard raises → 404.
  - test_get_students_requires_auth
      No Authorization header → 401.
  - test_get_students_returns_paginated_list
      Repository returns page with next_cursor → 200, body matches.
  - test_get_students_passes_limit_and_cursor_to_use_case
      Query params limit=5&cursor=abc forwarded to use case.

DynamoDbStudentEnrollmentRepository
  - test_add_students_writes_correct_pk_sk
      PK == EXAM#{exam_id}, SK == STUDENT#{student_id}.
  - test_add_students_stores_all_fields
      nom, prenom, classe, email, submission_status persisted.
  - test_add_students_conditional_failure_raises_duplicate_error
      TransactionCanceledException / ConditionalCheckFailed → DuplicateStudentError.
  - test_list_exam_students_queries_correct_pk_prefix
      query PK == EXAM#{exam_id}, begins_with(SK, "STUDENT#").
  - test_list_exam_students_cursor_pagination
      LastEvaluatedKey encoded as next_cursor, decoded on next call.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Placeholder — remove this marker once a test is implemented
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="TODO(#15): implement after use cases are filled in")
def test_placeholder() -> None:
    pass
