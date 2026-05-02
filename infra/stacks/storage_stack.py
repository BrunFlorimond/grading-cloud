from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_ssm as ssm
from constructs import Construct


class StorageStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: object) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.files_bucket = s3.Bucket(
            self,
            "FilesBucket",
            versioned=True,
            auto_delete_objects=False,
            removal_policy=RemovalPolicy.RETAIN,
            # TODO: add encryption=s3.BucketEncryption.S3_MANAGED for AES-256 at rest
            # TODO: add block_public_access=s3.BlockPublicAccess.BLOCK_ALL
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ExpireTemporaryFiles",
                    # TODO: update prefix to "exams/" and add object_size_greater_than
                    #       or use a TagFilter to target exams/*/tmp/ objects specifically.
                    #       CDK lifecycle rules do not support mid-path wildcards; evaluate
                    #       whether a dedicated "exams-tmp/" prefix convention is acceptable.
                    prefix="tmp/",
                    expiration=Duration.days(7),
                    noncurrent_version_expiration=Duration.days(7),
                )
            ],
        )

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
            # TODO: add point_in_time_recovery=True
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

        # TODO: export bucket name as SSM parameter
        #   ssm.StringParameter(self, "FilesBucketNameParam",
        #       parameter_name="/grading/storage/files-bucket-name",
        #       string_value=self.files_bucket.bucket_name)

        # TODO: export table name as SSM parameter
        #   ssm.StringParameter(self, "GradingTableNameParam",
        #       parameter_name="/grading/storage/grading-table-name",
        #       string_value=self.grading_table.table_name)
