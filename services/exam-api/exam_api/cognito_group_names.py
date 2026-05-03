"""Cognito user pool group names — must match infra/stacks/auth_stack.py CfnUserPoolGroup."""

# AWS group names are case-sensitive. Teachers/students use lowercase pool groups; Admin is title case.
COGNITO_TEACHER_GROUP = "teachers"
COGNITO_STUDENT_GROUP = "students"
COGNITO_ADMIN_GROUP = "admin"
