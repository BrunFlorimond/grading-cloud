"""Cognito user pool group names.

Must match ``exam_api.cognito_group_names`` (exam-api) — duplicated here so infra
tests and CDK stacks do not depend on application code.
"""

COGNITO_TEACHER_GROUP = "teachers"
COGNITO_STUDENT_GROUP = "students"
COGNITO_ADMIN_GROUP = "admin"
