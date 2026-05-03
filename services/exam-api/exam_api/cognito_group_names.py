"""Cognito user pool group names — must match infra/stacks/auth_stack.py CfnUserPoolGroup."""

# All pool group names are lowercase (AWS Cognito group names are case-sensitive).
COGNITO_TEACHER_GROUP = "teachers"
COGNITO_STUDENT_GROUP = "students"
COGNITO_ADMIN_GROUP = "admin"
