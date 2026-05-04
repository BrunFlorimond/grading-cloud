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


