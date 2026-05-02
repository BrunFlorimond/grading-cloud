"""CDK assertions for AuthStack (issue #6).

All tests below are stubs — implement using aws_cdk.assertions.Template.
Run with: uv run pytest tests/test_auth_stack.py
"""

from __future__ import annotations

import pytest

# TODO(#6): uncomment once aws-cdk-lib[testing] / pytest are in pyproject.toml
# import aws_cdk as cdk
# from aws_cdk import assertions
# from stacks.auth_stack import AuthStack


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def template():
    # TODO(#6): synthesise AuthStack and return assertions.Template.from_stack(stack)
    pytest.skip("stub — not yet implemented")


# ---------------------------------------------------------------------------
# User Pool
# ---------------------------------------------------------------------------


def test_user_pool_email_sign_in(template):
    # TODO(#6): assert UsernameAttributes contains EMAIL
    pytest.skip("stub — not yet implemented")


def test_user_pool_self_signup_disabled(template):
    # TODO(#6): assert AdminCreateUserConfig.AllowAdminCreateUserOnly == True
    pytest.skip("stub — not yet implemented")


def test_user_pool_password_policy(template):
    # TODO(#6): assert PasswordPolicy min_length=8, require_uppercase, lowercase, digits
    pytest.skip("stub — not yet implemented")


def test_user_pool_custom_role_attribute(template):
    # TODO(#6): assert Schema contains custom:role StringAttributeConstraints
    pytest.skip("stub — not yet implemented")


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


def test_teachers_group_exists(template):
    # TODO(#6): assert CfnUserPoolGroup with GroupName=Teachers
    pytest.skip("stub — not yet implemented")


def test_students_group_exists(template):
    # TODO(#6): assert CfnUserPoolGroup with GroupName=Students
    pytest.skip("stub — not yet implemented")


# ---------------------------------------------------------------------------
# App Client
# ---------------------------------------------------------------------------


def test_app_client_no_secret(template):
    # TODO(#6): assert UserPoolClient GenerateSecret == False (or absent)
    pytest.skip("stub — not yet implemented")


def test_app_client_supports_user_password_auth(template):
    # TODO(#6): assert ExplicitAuthFlows contains ALLOW_USER_PASSWORD_AUTH
    pytest.skip("stub — not yet implemented")


# ---------------------------------------------------------------------------
# HTTP API + JWT Authorizer
# ---------------------------------------------------------------------------


def test_http_api_protocol_http(template):
    # TODO(#6): assert CfnApi ProtocolType == HTTP
    pytest.skip("stub — not yet implemented")


def test_jwt_authorizer_uses_cognito_issuer(template):
    # TODO(#6): assert CfnAuthorizer JwtConfiguration.Issuer matches user pool URL
    pytest.skip("stub — not yet implemented")


# ---------------------------------------------------------------------------
# SSM Parameter exports
# ---------------------------------------------------------------------------


def test_ssm_user_pool_id_parameter(template):
    # TODO(#6): assert StringParameter /grading/cognito/user-pool-id exists
    pytest.skip("stub — not yet implemented")


def test_ssm_app_client_id_parameter(template):
    # TODO(#6): assert StringParameter /grading/cognito/app-client-id exists
    pytest.skip("stub — not yet implemented")
