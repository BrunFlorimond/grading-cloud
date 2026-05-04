"""CDK unit tests for DatabaseStack (aws_cdk.assertions.Template)."""

from __future__ import annotations

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from stacks.database_stack import DatabaseStack


@pytest.fixture
def db_template() -> Template:
    app = cdk.App()
    stack = DatabaseStack(app, "TestDatabaseStack")
    return Template.from_stack(stack)


def test_rds_engine_postgres_16(db_template: Template) -> None:
    db_template.has_resource_properties(
        "AWS::RDS::DBInstance",
        {"Engine": "postgres", "EngineVersion": Match.string_like_regexp("^16")},
    )


def test_rds_instance_class_t3_micro(db_template: Template) -> None:
    db_template.has_resource_properties(
        "AWS::RDS::DBInstance",
        {"DBInstanceClass": "db.t3.micro"},
    )


def test_rds_allocated_storage_20_gb(db_template: Template) -> None:
    db_template.has_resource_properties(
        "AWS::RDS::DBInstance",
        {"AllocatedStorage": "20"},
    )


def test_rds_storage_encrypted(db_template: Template) -> None:
    db_template.has_resource_properties(
        "AWS::RDS::DBInstance",
        {"StorageEncrypted": True},
    )


def test_rds_not_publicly_accessible(db_template: Template) -> None:
    db_template.has_resource_properties(
        "AWS::RDS::DBInstance",
        {"PubliclyAccessible": False},
    )


def test_rds_single_az(db_template: Template) -> None:
    db_template.has_resource_properties(
        "AWS::RDS::DBInstance",
        {"MultiAZ": False},
    )


def test_rds_database_name(db_template: Template) -> None:
    db_template.has_resource_properties(
        "AWS::RDS::DBInstance",
        {"DBName": "grading"},
    )


def test_rds_master_username_from_secret(db_template: Template) -> None:
    db_template.has_resource_properties(
        "AWS::RDS::DBInstance",
        {
            "MasterUsername": Match.object_like({"Fn::Join": Match.any_value()}),
            "MasterUserPassword": Match.object_like({"Fn::Join": Match.any_value()}),
        },
    )


def test_rds_sg_allows_postgres_from_fargate(db_template: Template) -> None:
    db_template.has_resource_properties(
        "AWS::EC2::SecurityGroupIngress",
        {"IpProtocol": "tcp", "FromPort": 5432, "ToPort": 5432},
    )


def test_vpc_no_nat_gateways(db_template: Template) -> None:
    # nat_gateways=0 → no NAT Gateway resources provisioned
    db_template.resource_count_is("AWS::EC2::NatGateway", 0)


def test_secrets_manager_secret_created(db_template: Template) -> None:
    db_template.has_resource_properties(
        "AWS::SecretsManager::Secret",
        {
            "GenerateSecretString": Match.object_like(
                {"SecretStringTemplate": Match.string_like_regexp("grading_app")}
            )
        },
    )


def test_ssm_secret_arn_exported(db_template: Template) -> None:
    db_template.has_resource_properties(
        "AWS::SSM::Parameter",
        {"Name": "/grading/database/secret-arn", "Type": "String"},
    )


def test_ssm_endpoint_exported(db_template: Template) -> None:
    db_template.has_resource_properties(
        "AWS::SSM::Parameter",
        {"Name": "/grading/database/endpoint", "Type": "String"},
    )
