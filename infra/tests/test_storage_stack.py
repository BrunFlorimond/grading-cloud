"""
CDK unit tests for StorageStack.

Test cases to implement (use aws_cdk.assertions.Template):

- test_s3_bucket_versioning_enabled
    Assert the FilesBucket has VersioningConfiguration.Status == "Enabled".

- test_s3_bucket_encryption_aes256
    Assert the FilesBucket has BucketEncryption with
    ServerSideEncryptionConfiguration rule using SSEAlgorithm "AES256".

- test_s3_bucket_block_all_public_access
    Assert the FilesBucket has PublicAccessBlockConfiguration with all four
    block flags set to True.

- test_s3_lifecycle_rule_expires_tmp_after_7_days
    Assert a lifecycle rule with prefix covering exams/*/tmp/ objects and
    ExpirationInDays == 7 exists on the bucket.

- test_dynamodb_table_pk_sk_schema
    Assert the GradingTable has KeySchema [PK (HASH) + SK (RANGE)] and
    AttributeDefinitions for both PK and SK as type S.

- test_dynamodb_billing_mode_pay_per_request
    Assert BillingMode == "PAY_PER_REQUEST" on the GradingTable.

- test_dynamodb_point_in_time_recovery_enabled
    Assert PointInTimeRecoverySpecification.PointInTimeRecoveryEnabled == True.

- test_dynamodb_gsi_batch_index
    Assert a GlobalSecondaryIndex named "BatchIndex" exists with
    GSI1PK (HASH) + GSI1SK (RANGE) key schema.

- test_dynamodb_gsi_teacher_exams
    Assert a GlobalSecondaryIndex named "TeacherExams" exists with
    GSI2PK (HASH) + GSI2SK (RANGE) key schema.

- test_ssm_parameter_bucket_name_exported
    Assert an SSM StringParameter with Name "/grading/storage/files-bucket-name"
    exists and its Value resolves to the FilesBucket logical name.

- test_ssm_parameter_table_name_exported
    Assert an SSM StringParameter with Name "/grading/storage/grading-table-name"
    exists and its Value resolves to the GradingTable logical name.
"""

import pytest


# TODO: implement test cases listed above
