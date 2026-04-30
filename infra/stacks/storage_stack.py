from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_s3 as s3
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
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ExpireTemporaryFiles",
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
