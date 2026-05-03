from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    aws_dynamodb as dynamodb,
    aws_ec2 as ec2,
    aws_ecr as ecr,
    aws_ecs as ecs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_events as events,
    aws_iam as iam,
    aws_logs as logs,
    aws_s3 as s3,
    aws_sqs as sqs,
)
from constructs import Construct


class ComputeStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        files_bucket: s3.IBucket,
        grading_table: dynamodb.ITable,
        **kwargs: object,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.exam_api_repository = ecr.Repository(
            self,
            "ExamApiRepository",
            repository_name="exam-api",
            image_scan_on_push=True,
        )
        self.spreadsheet_converter_repository = ecr.Repository(
            self,
            "SpreadsheetConverterRepository",
            repository_name="spreadsheet-converter",
            image_scan_on_push=True,
        )
        self.batch_poller_repository = ecr.Repository(
            self,
            "BatchPollerRepository",
            repository_name="batch-poller",
            image_scan_on_push=True,
        )
        self.pdf_generator_repository = ecr.Repository(
            self,
            "PdfGeneratorRepository",
            repository_name="pdf-generator",
            image_scan_on_push=True,
        )

        pipeline_dlq = sqs.Queue(
            self,
            "PipelineEventsDlq",
            queue_name="grading-pipeline-events-dlq",
            retention_period=Duration.days(14),
            enforce_ssl=True,
        )
        pipeline_events_queue = sqs.Queue(
            self,
            "PipelineEventsQueue",
            queue_name="grading-pipeline-events",
            retention_period=Duration.days(4),
            visibility_timeout=Duration.minutes(5),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=5,
                queue=pipeline_dlq,
            ),
            enforce_ssl=True,
        )

        event_bus = events.EventBus(
            self,
            "GradingEventBus",
            event_bus_name="grading-event-bus",
        )

        vpc = ec2.Vpc(
            self,
            "GradingVpc",
            max_azs=2,
            nat_gateways=0,
        )
        cluster = ecs.Cluster(
            self,
            "GradingCluster",
            vpc=vpc,
            cluster_name="grading-cluster",
        )

        task_definition = ecs.FargateTaskDefinition(
            self,
            "ExamApiTaskDefinition",
            cpu=512,
            memory_limit_mib=1024,
        )
        task_definition.add_container(
            "ExamApiContainer",
            image=ecs.ContainerImage.from_ecr_repository(self.exam_api_repository, "latest"),
            container_name="exam-api",
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="exam-api",
                log_retention=logs.RetentionDays.ONE_MONTH,
            ),
            environment={
                "FILES_BUCKET_NAME": files_bucket.bucket_name,
                "GRADING_TABLE_NAME": grading_table.table_name,
                "PIPELINE_EVENTS_QUEUE_URL": pipeline_events_queue.queue_url,
                "EVENT_BUS_NAME": event_bus.event_bus_name,
            },
            port_mappings=[ecs.PortMapping(container_port=8000)],
        )

        service = ecs.FargateService(
            self,
            "ExamApiService",
            cluster=cluster,
            task_definition=task_definition,
            desired_count=0,
            assign_public_ip=True,
            service_name="exam-api",
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

        alb = elbv2.ApplicationLoadBalancer(
            self,
            "ExamApiAlb",
            vpc=vpc,
            internet_facing=True,
            load_balancer_name="grading-exam-api-alb",
        )
        listener = alb.add_listener("HttpListener", port=80, open=True)
        listener.add_targets(
            "ExamApiTargets",
            port=8000,
            targets=[service],
            health_check=elbv2.HealthCheck(
                path="/health",
                healthy_http_codes="200-399",
            ),
        )

        task_role = task_definition.task_role
        task_role.add_to_principal_policy(
            iam.PolicyStatement(
                sid="S3Access",
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                    "s3:ListBucket",
                ],
                resources=[
                    files_bucket.bucket_arn,
                    files_bucket.arn_for_objects("*"),
                ],
            )
        )
        task_role.add_to_principal_policy(
            iam.PolicyStatement(
                sid="DynamoDbAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:BatchGetItem",
                    "dynamodb:BatchWriteItem",
                    "dynamodb:ConditionCheckItem",
                    "dynamodb:DeleteItem",
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:Query",
                    "dynamodb:TransactGetItems",
                    "dynamodb:TransactWriteItems",
                    "dynamodb:UpdateItem",
                ],
                resources=[
                    grading_table.table_arn,
                    f"{grading_table.table_arn}/index/*",
                ],
            )
        )
        task_role.add_to_principal_policy(
            iam.PolicyStatement(
                sid="SqsAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "sqs:ChangeMessageVisibility",
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes",
                    "sqs:GetQueueUrl",
                    "sqs:ReceiveMessage",
                    "sqs:SendMessage",
                ],
                resources=[
                    pipeline_events_queue.queue_arn,
                    pipeline_dlq.queue_arn,
                ],
            )
        )
        task_role.add_to_principal_policy(
            iam.PolicyStatement(
                sid="SesAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "ses:SendEmail",
                    "ses:SendRawEmail",
                ],
                resources=[
                    f"arn:aws:ses:{self.region}:{self.account}:identity/*",
                ],
            )
        )
        task_role.add_to_principal_policy(
            iam.PolicyStatement(
                sid="EventBridgeAccess",
                effect=iam.Effect.ALLOW,
                actions=["events:PutEvents"],
                resources=[event_bus.event_bus_arn],
            )
        )

        CfnOutput(
            self,
            "ExamApiRepositoryUri",
            value=self.exam_api_repository.repository_uri,
            export_name="GradingExamApiRepositoryUri",
        )
        CfnOutput(
            self,
            "SpreadsheetConverterRepositoryUri",
            value=self.spreadsheet_converter_repository.repository_uri,
            export_name="GradingSpreadsheetConverterRepositoryUri",
        )
        CfnOutput(
            self,
            "BatchPollerRepositoryUri",
            value=self.batch_poller_repository.repository_uri,
            export_name="GradingBatchPollerRepositoryUri",
        )
        CfnOutput(
            self,
            "PdfGeneratorRepositoryUri",
            value=self.pdf_generator_repository.repository_uri,
            export_name="GradingPdfGeneratorRepositoryUri",
        )
        CfnOutput(
            self,
            "ExamApiAlbDnsName",
            value=alb.load_balancer_dns_name,
            export_name="GradingExamApiAlbDnsName",
        )
        CfnOutput(
            self,
            "ExamApiClusterName",
            value=cluster.cluster_name,
            export_name="GradingExamApiClusterName",
        )
        CfnOutput(
            self,
            "ExamApiServiceName",
            value=service.service_name,
            export_name="GradingExamApiServiceName",
        )
        CfnOutput(
            self,
            "PipelineEventsQueueUrl",
            value=pipeline_events_queue.queue_url,
            export_name="GradingPipelineEventsQueueUrl",
        )
        CfnOutput(
            self,
            "PipelineEventsQueueArn",
            value=pipeline_events_queue.queue_arn,
            export_name="GradingPipelineEventsQueueArn",
        )
        CfnOutput(
            self,
            "EventBusName",
            value=event_bus.event_bus_name,
            export_name="GradingEventBusName",
        )
