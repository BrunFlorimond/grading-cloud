"""CDK unit tests for StorageStack (aws_cdk.assertions.Template)."""

from __future__ import annotations

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from stacks.storage_stack import StorageStack


@pytest.fixture
def storage_template() -> Template:
    app = cdk.App()
    stack = StorageStack(app, "TestStorageStack")
    return Template.from_stack(stack)


def test_s3_bucket_versioning_enabled(storage_template: Template) -> None:
    storage_template.has_resource_properties(
        "AWS::S3::Bucket",
        {"VersioningConfiguration": {"Status": "Enabled"}},
    )


def test_s3_bucket_encryption_aes256(storage_template: Template) -> None:
    storage_template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": [
                    {
                        "ServerSideEncryptionByDefault": {
                            "SSEAlgorithm": "AES256",
                        }
                    }
                ]
            }
        },
    )


def test_s3_bucket_block_all_public_access(storage_template: Template) -> None:
    storage_template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            }
        },
    )


def test_s3_lifecycle_rule_expires_tmp_after_7_days(
    storage_template: Template,
) -> None:
    storage_template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "LifecycleConfiguration": {
                "Rules": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "ExpirationInDays": 7,
                                "Prefix": "exams/tmp/",
                                "NoncurrentVersionExpiration": {
                                    "NoncurrentDays": 7,
                                },
                                "Status": "Enabled",
                            }
                        )
                    ]
                )
            }
        },
    )


def test_dynamodb_table_pk_sk_schema(storage_template: Template) -> None:
    storage_template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "KeySchema": [
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            "AttributeDefinitions": Match.array_with(
                [
                    {"AttributeName": "PK", "AttributeType": "S"},
                    {"AttributeName": "SK", "AttributeType": "S"},
                ]
            ),
        },
    )


def test_dynamodb_billing_mode_pay_per_request(
    storage_template: Template,
) -> None:
    storage_template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {"BillingMode": "PAY_PER_REQUEST"},
    )


def test_dynamodb_point_in_time_recovery_enabled(
    storage_template: Template,
) -> None:
    storage_template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "PointInTimeRecoverySpecification": {
                "PointInTimeRecoveryEnabled": True,
            }
        },
    )


def test_dynamodb_gsi_batch_index(storage_template: Template) -> None:
    storage_template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "GlobalSecondaryIndexes": Match.array_with(
                [
                    Match.object_like(
                        {
                            "IndexName": "BatchIndex",
                            "KeySchema": [
                                {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                                {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                            ],
                        }
                    )
                ]
            )
        },
    )


def test_dynamodb_gsi_teacher_exams(storage_template: Template) -> None:
    storage_template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "GlobalSecondaryIndexes": Match.array_with(
                [
                    Match.object_like(
                        {
                            "IndexName": "TeacherExams",
                            "KeySchema": [
                                {"AttributeName": "GSI2PK", "KeyType": "HASH"},
                                {"AttributeName": "GSI2SK", "KeyType": "RANGE"},
                            ],
                        }
                    )
                ]
            )
        },
    )


def test_ssm_parameter_bucket_name_exported(
    storage_template: Template,
) -> None:
    storage_template.has_resource_properties(
        "AWS::SSM::Parameter",
        {
            "Name": "/grading/storage/files-bucket-name",
            "Type": "String",
            "Value": {
                "Ref": Match.string_like_regexp("FilesBucket"),
            },
        },
    )


def test_ssm_parameter_table_name_exported(
    storage_template: Template,
) -> None:
    storage_template.has_resource_properties(
        "AWS::SSM::Parameter",
        {
            "Name": "/grading/storage/grading-table-name",
            "Type": "String",
            "Value": {
                "Ref": Match.string_like_regexp("GradingTable"),
            },
        },
    )
