"""CDK unit tests for ComputeStack (aws_cdk.assertions.Template)."""

from __future__ import annotations

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from stacks.auth_stack import AuthStack
from stacks.compute_stack import ComputeStack
from stacks.database_stack import DatabaseStack
from stacks.storage_stack import StorageStack


@pytest.fixture
def compute_template() -> Template:
    app = cdk.App()
    storage = StorageStack(app, "TestStorageStack")
    auth = AuthStack(app, "TestAuthStack")
    database = DatabaseStack(app, "TestDatabaseStack")
    compute = ComputeStack(
        app,
        "TestComputeStack",
        files_bucket=storage.files_bucket,
        vpc=database.vpc,
        db_secret=database.db_secret,
        db_endpoint=database.db_instance.db_instance_endpoint_address,
        db_name="grading",
        user_pool_id=auth.user_pool.user_pool_id,
        app_client_id=auth.user_pool_client.user_pool_client_id,
        alb_sg=database.alb_sg,
        fargate_sg=database.fargate_sg,
    )
    return Template.from_stack(compute)


# ── Queues ──────────────────────────────────────────────────────────────────


def test_pipeline_events_queue_exists(compute_template: Template) -> None:
    compute_template.has_resource_properties(
        "AWS::SQS::Queue",
        {
            "QueueName": "grading-pipeline-events",
            "VisibilityTimeout": 300,
            "RedrivePolicy": Match.object_like(
                {"maxReceiveCount": 5}
            ),
        },
    )


def test_spreadsheet_conversion_queue_visibility_and_redrive(
    compute_template: Template,
) -> None:
    compute_template.has_resource_properties(
        "AWS::SQS::Queue",
        {
            "QueueName": "grading-spreadsheet-conversion",
            "VisibilityTimeout": 300,
            "RedrivePolicy": Match.object_like(
                {"maxReceiveCount": 3}
            ),
        },
    )


def test_pdf_generation_queue_visibility_and_redrive(
    compute_template: Template,
) -> None:
    compute_template.has_resource_properties(
        "AWS::SQS::Queue",
        {
            "QueueName": "grading-pdf-generation",
            "VisibilityTimeout": 300,
            "RedrivePolicy": Match.object_like(
                {"maxReceiveCount": 3}
            ),
        },
    )


def test_dlqs_have_14_day_retention(compute_template: Template) -> None:
    fourteen_days_seconds = 14 * 24 * 60 * 60
    for dlq_name in (
        "grading-pipeline-events-dlq",
        "grading-spreadsheet-conversion-dlq",
        "grading-pdf-generation-dlq",
    ):
        compute_template.has_resource_properties(
            "AWS::SQS::Queue",
            {
                "QueueName": dlq_name,
                "MessageRetentionPeriod": fourteen_days_seconds,
            },
        )


def test_six_queues_total(compute_template: Template) -> None:
    # 3 main + 3 DLQ
    compute_template.resource_count_is("AWS::SQS::Queue", 6)


# ── DLQ alarms ──────────────────────────────────────────────────────────────


def test_three_dlq_alarms(compute_template: Template) -> None:
    compute_template.resource_count_is("AWS::CloudWatch::Alarm", 3)


@pytest.mark.parametrize(
    "alarm_name",
    [
        "grading-pipeline-events-dlq-not-empty",
        "grading-spreadsheet-conversion-dlq-not-empty",
        "grading-pdf-generation-dlq-not-empty",
    ],
)
def test_dlq_alarm_fires_on_any_message(
    compute_template: Template, alarm_name: str
) -> None:
    compute_template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "AlarmName": alarm_name,
            "MetricName": "ApproximateNumberOfMessagesVisible",
            "Namespace": "AWS/SQS",
            "ComparisonOperator": "GreaterThanThreshold",
            "Threshold": 0,
            "EvaluationPeriods": 1,
        },
    )


# ── SSM parameters ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "param_name",
    [
        "/grading/messaging/pipeline-events-queue-url",
        "/grading/messaging/spreadsheet-conversion-queue-url",
        "/grading/messaging/pdf-generation-queue-url",
    ],
)
def test_queue_url_published_to_ssm(
    compute_template: Template, param_name: str
) -> None:
    compute_template.has_resource_properties(
        "AWS::SSM::Parameter",
        {"Name": param_name, "Type": "String"},
    )


# ── IAM least-privilege ─────────────────────────────────────────────────────


def test_pipeline_events_consumer_statement_targets_only_main_queue(
    compute_template: Template,
) -> None:
    """exam-api consumes pipeline-events; the statement must NOT reach DLQs
    (DLQs only receive traffic via redrive policy) or other queues."""
    compute_template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Sid": "SqsPipelineEventsConsumer",
                                    "Effect": "Allow",
                                    "Action": Match.array_with(
                                        [
                                            "sqs:ChangeMessageVisibility",
                                            "sqs:DeleteMessage",
                                            "sqs:ReceiveMessage",
                                            "sqs:SendMessage",
                                        ]
                                    ),
                                    "Resource": {
                                        "Fn::GetAtt": [
                                            Match.string_like_regexp(
                                                "PipelineEventsQueue"
                                            ),
                                            "Arn",
                                        ]
                                    },
                                }
                            )
                        ]
                    )
                }
            )
        },
    )


def test_producer_statement_only_send_message_on_lambda_queues(
    compute_template: Template,
) -> None:
    """Spreadsheet/PDF queues are consumed by Lambdas (Issue #5).
    Fargate is producer-only — no Receive/Delete/ChangeVisibility."""
    compute_template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Sid": "SqsProducer",
                                    "Effect": "Allow",
                                    "Action": "sqs:SendMessage",
                                    "Resource": [
                                        {
                                            "Fn::GetAtt": [
                                                Match.string_like_regexp(
                                                    "SpreadsheetConversionQueue"
                                                ),
                                                "Arn",
                                            ]
                                        },
                                        {
                                            "Fn::GetAtt": [
                                                Match.string_like_regexp(
                                                    "PdfGenerationQueue"
                                                ),
                                                "Arn",
                                            ]
                                        },
                                    ],
                                }
                            )
                        ]
                    )
                }
            )
        },
    )


def test_no_iam_action_on_dlqs(compute_template: Template) -> None:
    """DLQs must never appear in any IAM policy statement —
    they receive messages exclusively via SQS redrive."""
    policies = compute_template.find_resources("AWS::IAM::Policy")
    for logical_id, resource in policies.items():
        statements = resource["Properties"]["PolicyDocument"]["Statement"]
        for stmt in statements:
            resources = stmt.get("Resource", [])
            if not isinstance(resources, list):
                resources = [resources]
            for res in resources:
                if isinstance(res, dict) and "Fn::GetAtt" in res:
                    referenced_logical_id = res["Fn::GetAtt"][0]
                    assert "Dlq" not in referenced_logical_id, (
                        f"Policy {logical_id} statement {stmt.get('Sid')!r} "
                        f"references DLQ {referenced_logical_id} — DLQs must "
                        "only be reachable via redrive policy."
                    )


# ── Lambdas ─────────────────────────────────────────────────────────────────


def test_three_lambda_functions_total(compute_template: Template) -> None:
    # spreadsheet-converter + pdf-generator + batch-poller
    compute_template.resource_count_is("AWS::Lambda::Function", 3)


def test_spreadsheet_converter_lambda_config(compute_template: Template) -> None:
    compute_template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "FunctionName": "grading-spreadsheet-converter",
            "PackageType": "Image",
            "MemorySize": 512,
            "Timeout": 300,
        },
    )


def test_pdf_generator_lambda_config(compute_template: Template) -> None:
    compute_template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "FunctionName": "grading-pdf-generator",
            "PackageType": "Image",
            "MemorySize": 1024,
            "Timeout": 300,
        },
    )


def test_batch_poller_lambda_config(compute_template: Template) -> None:
    """batch-poller is a zip-deployed Python Lambda — NOT a container."""
    compute_template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "FunctionName": "grading-batch-poller",
            "Runtime": "python3.12",
            "Handler": "handler.handler",
            "MemorySize": 256,
            "Timeout": 60,
        },
    )


def test_batch_poller_lambda_is_not_a_container(compute_template: Template) -> None:
    """batch-poller must NOT have PackageType=Image (it's a zip Lambda)."""
    functions = compute_template.find_resources(
        "AWS::Lambda::Function",
        {
            "Properties": Match.object_like(
                {"FunctionName": "grading-batch-poller"}
            )
        },
    )
    assert len(functions) == 1, "Expected exactly one batch-poller Lambda"
    props = next(iter(functions.values()))["Properties"]
    assert props.get("PackageType") != "Image"


# ── SQS event sources ───────────────────────────────────────────────────────


def test_two_lambda_event_source_mappings(compute_template: Template) -> None:
    """Only the two container Lambdas are SQS-triggered. batch-poller is
    invoked by EventBridge Scheduler (no event-source mapping)."""
    compute_template.resource_count_is("AWS::Lambda::EventSourceMapping", 2)


@pytest.mark.parametrize(
    "queue_logical_prefix",
    ["SpreadsheetConversionQueue", "PdfGenerationQueue"],
)
def test_sqs_event_source_batch_size_one(
    compute_template: Template, queue_logical_prefix: str
) -> None:
    compute_template.has_resource_properties(
        "AWS::Lambda::EventSourceMapping",
        {
            "BatchSize": 1,
            "EventSourceArn": {
                "Fn::GetAtt": [
                    Match.string_like_regexp(queue_logical_prefix),
                    "Arn",
                ]
            },
        },
    )


# ── EventBridge Scheduler ───────────────────────────────────────────────────


def test_batch_pollers_schedule_group_exists(compute_template: Template) -> None:
    compute_template.has_resource_properties(
        "AWS::Scheduler::ScheduleGroup",
        {"Name": "grading-batch-pollers"},
    )


def test_no_individual_schedules_provisioned(compute_template: Template) -> None:
    """Per-batch schedules are created at runtime by exam-api, never via CDK."""
    compute_template.resource_count_is("AWS::Scheduler::Schedule", 0)


def test_scheduler_role_trusts_scheduler_service(compute_template: Template) -> None:
    """Trust policy must scope to scheduler.amazonaws.com AND constrain both
    aws:SourceAccount and aws:SourceArn (confused-deputy hardening). Without
    SourceArn, any schedule in any group could assume this role."""
    compute_template.has_resource_properties(
        "AWS::IAM::Role",
        {
            "RoleName": "grading-batch-poller-scheduler-role",
            "AssumeRolePolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Effect": "Allow",
                                    "Action": "sts:AssumeRole",
                                    "Principal": {
                                        "Service": "scheduler.amazonaws.com"
                                    },
                                    "Condition": Match.object_like(
                                        {
                                            "StringEquals": Match.object_like(
                                                {
                                                    "aws:SourceAccount": Match.any_value()
                                                }
                                            ),
                                            "ArnLike": Match.object_like(
                                                {"aws:SourceArn": Match.any_value()}
                                            ),
                                        }
                                    ),
                                }
                            )
                        ]
                    )
                }
            ),
        },
    )


def test_scheduler_role_source_arn_scoped_to_batch_pollers_group(
    compute_template: Template,
) -> None:
    """The aws:SourceArn condition must end with the batch-pollers group ARN
    suffix — nothing wider should be acceptable."""
    roles = compute_template.find_resources(
        "AWS::IAM::Role",
        {
            "Properties": Match.object_like(
                {"RoleName": "grading-batch-poller-scheduler-role"}
            )
        },
    )
    assert len(roles) == 1
    statements = next(iter(roles.values()))["Properties"][
        "AssumeRolePolicyDocument"
    ]["Statement"]
    arn_like = statements[0]["Condition"]["ArnLike"]["aws:SourceArn"]
    assert isinstance(arn_like, dict) and "Fn::Join" in arn_like
    joined = "".join(p for p in arn_like["Fn::Join"][1] if isinstance(p, str))
    assert joined.endswith(":schedule/grading-batch-pollers/*"), (
        f"Trust SourceArn not scoped to batch-pollers group: {joined}"
    )


def test_scheduler_role_can_invoke_only_batch_poller(
    compute_template: Template,
) -> None:
    """Scheduler role must invoke ONLY the batch-poller Lambda."""
    compute_template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Effect": "Allow",
                                    "Action": "lambda:InvokeFunction",
                                    "Resource": Match.array_with(
                                        [
                                            {
                                                "Fn::GetAtt": [
                                                    Match.string_like_regexp(
                                                        "BatchPollerLambda"
                                                    ),
                                                    "Arn",
                                                ]
                                            }
                                        ]
                                    ),
                                }
                            )
                        ]
                    )
                }
            ),
            "Roles": Match.array_with(
                [{"Ref": Match.string_like_regexp("BatchPollerSchedulerRole")}]
            ),
        },
    )


# ── exam-api task role: scheduler API + PassRole ────────────────────────────


def test_exam_api_can_manage_schedules_in_batch_pollers_group(
    compute_template: Template,
) -> None:
    compute_template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Sid": "SchedulerAccess",
                                    "Effect": "Allow",
                                    "Action": Match.array_with(
                                        [
                                            "scheduler:CreateSchedule",
                                            "scheduler:DeleteSchedule",
                                            "scheduler:GetSchedule",
                                            "scheduler:UpdateSchedule",
                                        ]
                                    ),
                                }
                            )
                        ]
                    )
                }
            )
        },
    )


def test_exam_api_scheduler_resource_scoped_to_batch_pollers_group(
    compute_template: Template,
) -> None:
    """The resource ARN is a Fn::Join over region/account; verify the static
    suffix narrows it to the batch-pollers group only."""
    policies = compute_template.find_resources("AWS::IAM::Policy")
    matched = False
    for resource in policies.values():
        for stmt in resource["Properties"]["PolicyDocument"]["Statement"]:
            if stmt.get("Sid") != "SchedulerAccess":
                continue
            res = stmt["Resource"]
            assert isinstance(res, dict) and "Fn::Join" in res, (
                "Expected Fn::Join ARN for scheduler resource"
            )
            joined = "".join(p for p in res["Fn::Join"][1] if isinstance(p, str))
            assert joined.endswith(":schedule/grading-batch-pollers/*"), (
                f"Resource not scoped to batch-pollers group: {joined}"
            )
            matched = True
    assert matched, "SchedulerAccess statement not found"


def test_exam_api_passrole_scoped_to_scheduler_service(
    compute_template: Template,
) -> None:
    """PassRole must target ONLY the batch-poller scheduler role and be
    conditioned on the scheduler service. Widening the resource to "*" or
    naming any other role must fail this test."""
    policies = compute_template.find_resources("AWS::IAM::Policy")
    matched = False
    for resource in policies.values():
        for stmt in resource["Properties"]["PolicyDocument"]["Statement"]:
            if stmt.get("Sid") != "SchedulerPassRole":
                continue
            assert stmt["Effect"] == "Allow"
            assert stmt["Action"] == "iam:PassRole"
            assert stmt["Condition"] == {
                "StringEquals": {"iam:PassedToService": "scheduler.amazonaws.com"}
            }
            res = stmt["Resource"]
            assert isinstance(res, dict) and "Fn::GetAtt" in res, (
                f"Resource must be a single GetAtt on the scheduler role, got {res!r}"
            )
            referenced_logical_id, attr = res["Fn::GetAtt"]
            assert "BatchPollerSchedulerRole" in referenced_logical_id, (
                f"Expected scheduler role, got {referenced_logical_id}"
            )
            assert attr == "Arn"
            matched = True
    assert matched, "SchedulerPassRole statement not found"


# ── SSM parameters for runtime wiring ───────────────────────────────────────


@pytest.mark.parametrize(
    "param_name",
    [
        "/grading/lambda/batch-poller-arn",
        "/grading/scheduler/batch-pollers-group-name",
        "/grading/scheduler/batch-poller-role-arn",
    ],
)
def test_runtime_wiring_published_to_ssm(
    compute_template: Template, param_name: str
) -> None:
    compute_template.has_resource_properties(
        "AWS::SSM::Parameter",
        {"Name": param_name, "Type": "String"},
    )


def test_batch_pollers_group_name_param_is_literal(
    compute_template: Template,
) -> None:
    """The group-name SSM parameter holds the plain string, not a CFN ref —
    exam-api reads it as a literal name."""
    compute_template.has_resource_properties(
        "AWS::SSM::Parameter",
        {
            "Name": "/grading/scheduler/batch-pollers-group-name",
            "Value": "grading-batch-pollers",
        },
    )
