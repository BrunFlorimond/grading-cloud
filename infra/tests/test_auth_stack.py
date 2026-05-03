"""CDK assertions for AuthStack (issue #6).

Run with: uv run pytest tests/test_auth_stack.py
(from the infra/ directory)
"""

from __future__ import annotations

import aws_cdk as cdk
import pytest
from aws_cdk import assertions
from exam_api.cognito_group_names import (
    COGNITO_ADMIN_GROUP,
    COGNITO_STUDENT_GROUP,
    COGNITO_TEACHER_GROUP,
)
from stacks.auth_stack import AuthStack


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def template() -> assertions.Template:
    app = cdk.App()
    stack = AuthStack(app, "TestAuthStack")
    return assertions.Template.from_stack(stack)


# ---------------------------------------------------------------------------
# User Pool
# ---------------------------------------------------------------------------


def test_user_pool_email_sign_in(template: assertions.Template) -> None:
    template.has_resource_properties(
        "AWS::Cognito::UserPool",
        {"UsernameAttributes": ["email"]},
    )


def test_user_pool_self_signup_disabled(template: assertions.Template) -> None:
    template.has_resource_properties(
        "AWS::Cognito::UserPool",
        {"AdminCreateUserConfig": {"AllowAdminCreateUserOnly": True}},
    )


def test_user_pool_password_policy(template: assertions.Template) -> None:
    template.has_resource_properties(
        "AWS::Cognito::UserPool",
        {
            "Policies": {
                "PasswordPolicy": {
                    "MinimumLength": 8,
                    "RequireUppercase": True,
                    "RequireLowercase": True,
                    "RequireNumbers": True,
                    "RequireSymbols": False,
                }
            }
        },
    )


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


def test_teachers_group_exists(template: assertions.Template) -> None:
    template.has_resource_properties(
        "AWS::Cognito::UserPoolGroup",
        {"GroupName": COGNITO_TEACHER_GROUP},
    )


def test_students_group_exists(template: assertions.Template) -> None:
    template.has_resource_properties(
        "AWS::Cognito::UserPoolGroup",
        {"GroupName": COGNITO_STUDENT_GROUP},
    )


def test_admin_group_exists(template: assertions.Template) -> None:
    template.has_resource_properties(
        "AWS::Cognito::UserPoolGroup",
        {"GroupName": COGNITO_ADMIN_GROUP},
    )


# ---------------------------------------------------------------------------
# App Client
# ---------------------------------------------------------------------------


def test_app_client_no_secret(template: assertions.Template) -> None:
    template.has_resource_properties(
        "AWS::Cognito::UserPoolClient",
        {"GenerateSecret": False},
    )


def test_app_client_supports_user_password_auth(template: assertions.Template) -> None:
    template.has_resource_properties(
        "AWS::Cognito::UserPoolClient",
        {
            "ExplicitAuthFlows": assertions.Match.array_with(
                ["ALLOW_USER_PASSWORD_AUTH"],
            )
        },
    )


# ---------------------------------------------------------------------------
# HTTP API + JWT Authorizer
# ---------------------------------------------------------------------------


def test_http_api_protocol_http(template: assertions.Template) -> None:
    template.has_resource_properties(
        "AWS::ApiGatewayV2::Api",
        {"ProtocolType": "HTTP"},
    )


def test_jwt_authorizer_uses_cognito_issuer(template: assertions.Template) -> None:
    template.has_resource_properties(
        "AWS::ApiGatewayV2::Authorizer",
        {
            "AuthorizerType": "JWT",
            "JwtConfiguration": assertions.Match.object_like(
                {
                    "Issuer": {"Fn::GetAtt": assertions.Match.any_value()},
                    "Audience": assertions.Match.any_value(),
                }
            ),
        },
    )


def test_jwt_authorizer_enforced_on_route(template: assertions.Template) -> None:
    template.has_resource_properties(
        "AWS::ApiGatewayV2::Route",
        {
            "AuthorizationType": "JWT",
            "RouteKey": "GET /auth-probe",
        },
    )


# ---------------------------------------------------------------------------
# SSM Parameter exports
# ---------------------------------------------------------------------------


def test_ssm_user_pool_id_parameter(template: assertions.Template) -> None:
    template.has_resource_properties(
        "AWS::SSM::Parameter",
        {"Name": "/grading/cognito/user-pool-id"},
    )


def test_ssm_app_client_id_parameter(template: assertions.Template) -> None:
    template.has_resource_properties(
        "AWS::SSM::Parameter",
        {"Name": "/grading/cognito/app-client-id"},
    )
