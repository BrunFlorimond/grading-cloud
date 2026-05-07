from aws_cdk import CfnOutput, CfnParameter, Duration, Stack
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_events as events
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_event_sources as lambda_event_sources
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_scheduler as scheduler
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_sqs as sqs
from aws_cdk import aws_ssm as ssm
from constructs import Construct

BATCH_POLLERS_SCHEDULE_GROUP_NAME = "grading-batch-pollers"

# Inline placeholder for the batch-poller Lambda. The real implementation ships
# as a zip via CI; this stub only exists so CDK can synth before the first
# deploy.
_BATCH_POLLER_PLACEHOLDER_CODE = (
    "def handler(event, context):\n"
    "    raise NotImplementedError("
    "'batch-poller code is uploaded by CI; replace via aws lambda update-function-code'"
    ")\n"
)


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

        # ── Lambdas ──────────────────────────────────────────────────────────
        # Explicit log groups (the deprecated `log_retention=` shim spawns a
        # custom-resource Lambda; pre-creating the group is the modern path).
        spreadsheet_converter_log_group = logs.LogGroup(
            self,
            "SpreadsheetConverterLogGroup",
            log_group_name="/aws/lambda/grading-spreadsheet-converter",
            retention=logs.RetentionDays.ONE_MONTH,
        )
        pdf_generator_log_group = logs.LogGroup(
            self,
            "PdfGeneratorLogGroup",
            log_group_name="/aws/lambda/grading-pdf-generator",
            retention=logs.RetentionDays.ONE_MONTH,
        )
        batch_poller_log_group = logs.LogGroup(
            self,
            "BatchPollerLogGroup",
            log_group_name="/aws/lambda/grading-batch-poller",
            retention=logs.RetentionDays.ONE_MONTH,
        )

        # Container image Lambda — consumes spreadsheet-conversion queue.
        spreadsheet_converter_lambda = lambda_.DockerImageFunction(
            self,
            "SpreadsheetConverterLambda",
            function_name="grading-spreadsheet-converter",
            code=lambda_.DockerImageCode.from_ecr(
                self.spreadsheet_converter_repository, tag_or_digest="latest"
            ),
            memory_size=512,
            timeout=Duration.seconds(300),
            environment={
                "FILES_BUCKET_NAME": files_bucket.bucket_name,
                "PIPELINE_EVENTS_QUEUE_URL": pipeline_events_queue.queue_url,
            },
            log_group=spreadsheet_converter_log_group,
        )
        spreadsheet_converter_lambda.add_event_source(
            lambda_event_sources.SqsEventSource(
                spreadsheet_conversion_queue, batch_size=1
            )
        )
        files_bucket.grant_read_write(spreadsheet_converter_lambda)
        pipeline_events_queue.grant_send_messages(spreadsheet_converter_lambda)

        # Container image Lambda — consumes pdf-generation queue.
        pdf_generator_lambda = lambda_.DockerImageFunction(
            self,
            "PdfGeneratorLambda",
            function_name="grading-pdf-generator",
            code=lambda_.DockerImageCode.from_ecr(
                self.pdf_generator_repository, tag_or_digest="latest"
            ),
            memory_size=1024,
            timeout=Duration.seconds(300),
            environment={
                "FILES_BUCKET_NAME": files_bucket.bucket_name,
                "PIPELINE_EVENTS_QUEUE_URL": pipeline_events_queue.queue_url,
            },
            log_group=pdf_generator_log_group,
        )
        pdf_generator_lambda.add_event_source(
            lambda_event_sources.SqsEventSource(pdf_generation_queue, batch_size=1)
        )
        files_bucket.grant_read_write(pdf_generator_lambda)
        pipeline_events_queue.grant_send_messages(pdf_generator_lambda)

        # Zip Lambda — invoked by EventBridge Scheduler (one rule per active batch).
        # Not subscribed to any queue.
        batch_poller_lambda = lambda_.Function(
            self,
            "BatchPollerLambda",
            function_name="grading-batch-poller",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_inline(_BATCH_POLLER_PLACEHOLDER_CODE),
            memory_size=256,
            timeout=Duration.seconds(60),
            environment={
                "FILES_BUCKET_NAME": files_bucket.bucket_name,
                "PIPELINE_EVENTS_QUEUE_URL": pipeline_events_queue.queue_url,
            },
            log_group=batch_poller_log_group,
        )
        files_bucket.grant_read_write(batch_poller_lambda)
        pipeline_events_queue.grant_send_messages(batch_poller_lambda)

        # ── EventBridge Scheduler ────────────────────────────────────────────
        # The schedule group is pre-created here; individual schedules (one per
        # active Anthropic batch) are created/deleted dynamically by exam-api.
        batch_pollers_schedule_group = scheduler.CfnScheduleGroup(
            self,
            "BatchPollersScheduleGroup",
            name=BATCH_POLLERS_SCHEDULE_GROUP_NAME,
        )

        # Role assumed by EventBridge Scheduler when invoking the batch-poller
        # Lambda. exam-api passes this ARN as the `RoleArn` on each schedule.
        batch_poller_scheduler_role = iam.Role(
            self,
            "BatchPollerSchedulerRole",
            role_name="grading-batch-poller-scheduler-role",
            assumed_by=iam.ServicePrincipal(
                "scheduler.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": self.account},
                },
            ),
            description=(
                "Assumed by EventBridge Scheduler to invoke the batch-poller Lambda."
            ),
        )
        batch_poller_lambda.grant_invoke(batch_poller_scheduler_role)

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
        # exam-api creates/deletes schedules dynamically (one per active batch),
        # scoped to the batch-pollers group only.
        task_role.add_to_principal_policy(
            iam.PolicyStatement(
                sid="SchedulerAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "scheduler:CreateSchedule",
                    "scheduler:DeleteSchedule",
                    "scheduler:GetSchedule",
                    "scheduler:UpdateSchedule",
                ],
                resources=[
                    f"arn:aws:scheduler:{self.region}:{self.account}"
                    f":schedule/{BATCH_POLLERS_SCHEDULE_GROUP_NAME}/*"
                ],
            )
        )
        # PassRole is required so exam-api can hand the scheduler role over to
        # EventBridge Scheduler when creating each schedule.
        task_role.add_to_principal_policy(
            iam.PolicyStatement(
                sid="SchedulerPassRole",
                effect=iam.Effect.ALLOW,
                actions=["iam:PassRole"],
                resources=[batch_poller_scheduler_role.role_arn],
                conditions={
                    "StringEquals": {
                        "iam:PassedToService": "scheduler.amazonaws.com"
                    }
                },
            )
        )

        # exam-api needs the batch-poller Lambda ARN to point new scheduler rules
        # at it, plus the schedule group name and the role Scheduler assumes.
        ssm.StringParameter(
            self,
            "BatchPollerLambdaArnParam",
            parameter_name="/grading/lambda/batch-poller-arn",
            string_value=batch_poller_lambda.function_arn,
        )
        ssm.StringParameter(
            self,
            "BatchPollersScheduleGroupNameParam",
            parameter_name="/grading/scheduler/batch-pollers-group-name",
            string_value=BATCH_POLLERS_SCHEDULE_GROUP_NAME,
        )
        ssm.StringParameter(
            self,
            "BatchPollerSchedulerRoleArnParam",
            parameter_name="/grading/scheduler/batch-poller-role-arn",
            string_value=batch_poller_scheduler_role.role_arn,
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
        CfnOutput(
            self,
            "BatchPollerLambdaArn",
            value=batch_poller_lambda.function_arn,
            export_name="GradingBatchPollerLambdaArn",
        )
        CfnOutput(
            self,
            "BatchPollersScheduleGroupName",
            value=batch_pollers_schedule_group.name or BATCH_POLLERS_SCHEDULE_GROUP_NAME,
            export_name="GradingBatchPollersScheduleGroupName",
        )
        CfnOutput(
            self,
            "BatchPollerSchedulerRoleArn",
            value=batch_poller_scheduler_role.role_arn,
            export_name="GradingBatchPollerSchedulerRoleArn",
        )
