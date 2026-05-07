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
