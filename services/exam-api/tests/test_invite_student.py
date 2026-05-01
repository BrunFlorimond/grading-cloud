"""Tests for the invite-student flow (issue #10).

Cases to implement
------------------
Use case — InviteStudentUseCase
  TODO: test_execute_raises_exam_not_found_when_exam_missing
  TODO: test_execute_raises_exam_ownership_error_when_teacher_does_not_own_exam
  TODO: test_execute_calls_invite_service_with_correct_args
  TODO: test_execute_persists_student_record_to_dynamodb
  TODO: test_execute_returns_re_invited_false_on_first_invite
  TODO: test_execute_returns_re_invited_true_on_reinvite

Adapter — CognitoSesStudentInviteAdapter
  TODO: test_invite_student_creates_cognito_user_with_suppress_message_action
  TODO: test_invite_student_adds_user_to_students_group
  TODO: test_invite_student_sets_custom_role_and_exam_id_attributes
  TODO: test_invite_student_sends_ses_email_with_temporary_password
  TODO: test_invite_student_returns_already_existed_true_when_username_exists
  TODO: test_invite_student_does_not_duplicate_account_on_reinvite

API — POST /exams/{exam_id}/students/{student_id}/invite
  TODO: test_api_returns_200_on_successful_invite
  TODO: test_api_returns_200_with_re_invited_true_on_reinvite
  TODO: test_api_returns_404_when_exam_not_found
  TODO: test_api_returns_403_when_teacher_does_not_own_exam
  TODO: test_api_returns_422_on_invalid_email
  TODO: test_api_extracts_teacher_id_from_jwt_claims
"""
