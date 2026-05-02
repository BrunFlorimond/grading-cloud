from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_ssm as ssm
from constructs import Construct


class StorageStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: object) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Ephemeral uploads: use keys under exams/tmp/... (S3 lifecycle has no mid-path
        # wildcards; this prefix covers per-exam scratch under exams/tmp/{exam_id}/).
        self.files_bucket = s3.Bucket(
            self,
            "FilesBucket",
            versioned=True,
            enforce_ssl=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            auto_delete_objects=False,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ExpireTemporaryFiles",
                    prefix="exams/tmp/",
                    expiration=Duration.days(7),
                    noncurrent_version_expiration=Duration.days(7),
                )
            ],
        )

        # Fixed physical name for single-table lookups across stacks; override via CDK
        # context or separate stacks when multi-env tables are needed in one account.
        self.grading_table = dynamodb.Table(
            self,
            "GradingTable",
            table_name="grading-table",
            partition_key=dynamodb.Attribute(
                name="PK",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="SK",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True,
            ),
        )

        self.grading_table.add_global_secondary_index(
            index_name="BatchIndex",
            partition_key=dynamodb.Attribute(
                name="GSI1PK",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="GSI1SK",
                type=dynamodb.AttributeType.STRING,
            ),
        )

        # TeacherExams: application stores TEACHER#{id} in GSI2PK and timestamps / SK
        # values (e.g. ISO 8601 created_at) in GSI2SK — generic single-table names.
        self.grading_table.add_global_secondary_index(
            index_name="TeacherExams",
            partition_key=dynamodb.Attribute(
                name="GSI2PK",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="GSI2SK",
                type=dynamodb.AttributeType.STRING,
            ),
        )

        ssm.StringParameter(
            self,
            "FilesBucketNameParam",
            parameter_name="/grading/storage/files-bucket-name",
            string_value=self.files_bucket.bucket_name,
        )

        ssm.StringParameter(
            self,
            "GradingTableNameParam",
            parameter_name="/grading/storage/grading-table-name",
            string_value=self.grading_table.table_name,
        )
