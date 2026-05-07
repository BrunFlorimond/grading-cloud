from aws_cdk import CfnOutput, CfnParameter, Duration, Stack
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_events as events
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_sqs as sqs
from aws_cdk import aws_ssm as ssm
from constructs import Construct


class ComputeStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        files_bucket: s3.IBucket,
        vpc: ec2.IVpc,
        db_secret: secretsmanager.ISecret,
        db_endpoint: str,
        db_name: str,
        user_pool_id: str,
        app_client_id: str,
        alb_sg: ec2.ISecurityGroup,
        fargate_sg: ec2.ISecurityGroup,
        **kwargs: object,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # All SGs are pre-wired in DatabaseStack — no new rules created here.

        ses_from_address = CfnParameter(
            self,
            "SesFromAddress",
            type="String",
            description="Verified SES sender email used for student invitations.",
        ).value_as_string

        # ── ECR repositories ─────────────────────────────────────────────────
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

        # ── SQS ──────────────────────────────────────────────────────────────
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
                max_receive_count=5, queue=pipeline_dlq
            ),
            enforce_ssl=True,
        )

        spreadsheet_conversion_dlq = sqs.Queue(
            self,
            "SpreadsheetConversionDlq",
            queue_name="grading-spreadsheet-conversion-dlq",
            retention_period=Duration.days(14),
            enforce_ssl=True,
        )
        spreadsheet_conversion_queue = sqs.Queue(
            self,
            "SpreadsheetConversionQueue",
            queue_name="grading-spreadsheet-conversion",
            retention_period=Duration.days(4),
            visibility_timeout=Duration.seconds(300),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3, queue=spreadsheet_conversion_dlq
            ),
            enforce_ssl=True,
        )

        pdf_generation_dlq = sqs.Queue(
            self,
            "PdfGenerationDlq",
            queue_name="grading-pdf-generation-dlq",
            retention_period=Duration.days(14),
            enforce_ssl=True,
        )
        pdf_generation_queue = sqs.Queue(
            self,
            "PdfGenerationQueue",
            queue_name="grading-pdf-generation",
            retention_period=Duration.days(4),
            visibility_timeout=Duration.seconds(300),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3, queue=pdf_generation_dlq
            ),
            enforce_ssl=True,
        )

        # CloudWatch alarms — fire when any message lands in a DLQ
        for alarm_id, alarm_name, dlq in (
            (
                "PipelineEventsDlqAlarm",
                "grading-pipeline-events-dlq-not-empty",
                pipeline_dlq,
            ),
            (
                "SpreadsheetConversionDlqAlarm",
                "grading-spreadsheet-conversion-dlq-not-empty",
                spreadsheet_conversion_dlq,
            ),
            (
                "PdfGenerationDlqAlarm",
                "grading-pdf-generation-dlq-not-empty",
                pdf_generation_dlq,
            ),
        ):
            cloudwatch.Alarm(
                self,
                alarm_id,
                alarm_name=alarm_name,
                metric=dlq.metric_approximate_number_of_messages_visible(),
                evaluation_periods=1,
                threshold=0,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
                alarm_description=f"A message has landed in {dlq.queue_name}.",
            )

        # SSM parameters — queue URLs for downstream services
        ssm.StringParameter(
            self,
            "PipelineEventsQueueUrlParam",
            parameter_name="/grading/messaging/pipeline-events-queue-url",
            string_value=pipeline_events_queue.queue_url,
        )
        ssm.StringParameter(
            self,
            "SpreadsheetConversionQueueUrlParam",
            parameter_name="/grading/messaging/spreadsheet-conversion-queue-url",
            string_value=spreadsheet_conversion_queue.queue_url,
        )
        ssm.StringParameter(
            self,
            "PdfGenerationQueueUrlParam",
            parameter_name="/grading/messaging/pdf-generation-queue-url",
            string_value=pdf_generation_queue.queue_url,
        )

        # ── EventBridge ──────────────────────────────────────────────────────
        event_bus = events.EventBus(
            self, "GradingEventBus", event_bus_name="grading-event-bus"
        )

        # ── ECS ──────────────────────────────────────────────────────────────
        cluster = ecs.Cluster(
            self, "GradingCluster", vpc=vpc, cluster_name="grading-cluster"
        )

        # Shared env + secrets used by both the long-running service and the
        # one-shot migration task — defined once, applied to both containers.
        container_environment = {
            "FILES_BUCKET_NAME": files_bucket.bucket_name,
            "EXAM_CONFIG_BUCKET": files_bucket.bucket_name,
            "PIPELINE_EVENTS_QUEUE_URL": pipeline_events_queue.queue_url,
            "EVENT_BUS_NAME": event_bus.event_bus_name,
            "DB_HOST": db_endpoint,
            "DB_PORT": "5432",
            "DB_NAME": db_name,
            "COGNITO_USER_POOL_ID": user_pool_id,
            "COGNITO_APP_CLIENT_ID": app_client_id,
            "AWS_REGION": self.region,
            "SES_FROM_ADDRESS": ses_from_address,
        }
        container_secrets = {
            "DB_USERNAME": ecs.Secret.from_secrets_manager(db_secret, "username"),
            "DB_PASSWORD": ecs.Secret.from_secrets_manager(db_secret, "password"),
        }

        task_definition = ecs.FargateTaskDefinition(
            self, "ExamApiTaskDefinition", cpu=512, memory_limit_mib=1024
        )

        task_definition.add_container(
            "ExamApiContainer",
            image=ecs.ContainerImage.from_ecr_repository(
                self.exam_api_repository, "latest"
            ),
            container_name="exam-api",
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="exam-api",
                log_retention=logs.RetentionDays.ONE_MONTH,
            ),
            environment=container_environment,
            secrets=container_secrets,
            port_mappings=[ecs.PortMapping(container_port=8000)],
        )

        service = ecs.FargateService(
            self,
            "ExamApiService",
            cluster=cluster,
            task_definition=task_definition,
            desired_count=0,
            # assign_public_ip required in public subnet without NAT gateway (ECR pulls)
            assign_public_ip=True,
            service_name="exam-api",
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_groups=[fargate_sg],
        )

        # ── One-shot migration task (Alembic) ────────────────────────────────
        # Same image, same env/secrets, same SG — only the command differs.
        # Trigger with: aws ecs run-task --cluster <cluster> --task-definition exam-api-migrations
        #               --launch-type FARGATE --network-configuration ... (see CfnOutputs).
        migration_task_definition = ecs.FargateTaskDefinition(
            self,
            "ExamApiMigrationTaskDefinition",
            family="exam-api-migrations",
            cpu=256,
            memory_limit_mib=512,
        )
        migration_task_definition.add_container(
            "MigrationsContainer",
            image=ecs.ContainerImage.from_ecr_repository(
                self.exam_api_repository, "latest"
            ),
            container_name="migrations",
            command=["alembic", "upgrade", "head"],
            essential=True,
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="exam-api-migrations",
                log_retention=logs.RetentionDays.ONE_MONTH,
            ),
            environment=container_environment,
            secrets=container_secrets,
        )

        # ── ALB (explicit construction — avoids ecs_patterns SG auto-wiring) ─
        alb = elbv2.ApplicationLoadBalancer(
            self,
            "ExamApiAlb",
            vpc=vpc,
            internet_facing=True,
            security_group=alb_sg,  # pre-wired in DatabaseStack
            load_balancer_name="grading-exam-api-alb",
        )
        listener = alb.add_listener("HttpListener", port=80, open=False)
        listener.add_targets(
            "ExamApiTargets",
            port=8000,
            targets=[service],
            health_check=elbv2.HealthCheck(
                path="/health", healthy_http_codes="200-399"
            ),
        )

        # ── IAM ──────────────────────────────────────────────────────────────
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
                resources=[files_bucket.bucket_arn, files_bucket.arn_for_objects("*")],
            )
        )
        # Scoped grant — no wildcard; adds GetSecretValue + DescribeSecret on this ARN
        db_secret.grant_read(task_role)
        # exam-api is BOTH producer and consumer of pipeline-events.
        task_role.add_to_principal_policy(
            iam.PolicyStatement(
                sid="SqsPipelineEventsConsumer",
                effect=iam.Effect.ALLOW,
                actions=[
                    "sqs:ChangeMessageVisibility",
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes",
                    "sqs:GetQueueUrl",
                    "sqs:ReceiveMessage",
                    "sqs:SendMessage",
                ],
                resources=[pipeline_events_queue.queue_arn],
            )
        )
        # Spreadsheet/PDF queues are consumed by Lambdas (Issue #5);
        # exam-api only publishes work onto them.
        task_role.add_to_principal_policy(
            iam.PolicyStatement(
                sid="SqsProducer",
                effect=iam.Effect.ALLOW,
                actions=["sqs:SendMessage"],
                resources=[
                    spreadsheet_conversion_queue.queue_arn,
                    pdf_generation_queue.queue_arn,
                ],
            )
        )
        task_role.add_to_principal_policy(
            iam.PolicyStatement(
                sid="SesAccess",
                effect=iam.Effect.ALLOW,
                actions=["ses:SendEmail", "ses:SendRawEmail"],
                resources=[f"arn:aws:ses:{self.region}:{self.account}:identity/*"],
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

        # ── Outputs ───────────────────────────────────────────────────────────
        CfnOutput(
            self,
            "ExamApiRepositoryUri",
            value=self.exam_api_repository.repository_uri,
            export_name="GradingExamApiRepositoryUri",
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
            "EventBusName",
            value=event_bus.event_bus_name,
            export_name="GradingEventBusName",
        )
        CfnOutput(
            self,
            "MigrationTaskDefinitionArn",
            value=migration_task_definition.task_definition_arn,
            export_name="GradingMigrationTaskDefinitionArn",
        )
        CfnOutput(
            self,
            "FargateSecurityGroupId",
            value=fargate_sg.security_group_id,
            export_name="GradingFargateSecurityGroupId",
        )
        CfnOutput(
            self,
            "PublicSubnetIds",
            value=",".join([s.subnet_id for s in vpc.public_subnets]),
            export_name="GradingPublicSubnetIds",
        )
