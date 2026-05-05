from aws_cdk import Duration, RemovalPolicy, Stack
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

        ssm.StringParameter(
            self,
            "FilesBucketNameParam",
            parameter_name="/grading/storage/files-bucket-name",
            string_value=self.files_bucket.bucket_name,
        )
