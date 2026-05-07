#!/usr/bin/env bash
set -euo pipefail

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-eu-west-1}}"
BUCKET_NAME="grading-cloud-local-exam-config"
FROM_EMAIL="no-reply@local.grading-cloud"
BATCH_POLLERS_GROUP_NAME="grading-batch-pollers"
BATCH_POLLER_FUNCTION_NAME="grading-batch-poller"
SCHEDULER_ROLE_NAME="grading-batch-poller-scheduler-role"
BATCH_POLLER_EXECUTION_ROLE_NAME="grading-batch-poller-execution-role"

awslocal s3 mb "s3://${BUCKET_NAME}" >/dev/null
awslocal ses verify-email-identity --email-address "${FROM_EMAIL}" >/dev/null

create_queue_with_dlq() {
  local main_name="$1"
  local dlq_name="$2"
  local visibility_timeout="$3"
  local max_receive_count="$4"

  local dlq_attrs_file="/tmp/${dlq_name}.attrs.json"
  printf '{"MessageRetentionPeriod":"1209600"}' >"${dlq_attrs_file}"
  awslocal sqs create-queue \
    --queue-name "${dlq_name}" \
    --attributes "file://${dlq_attrs_file}" \
    >/dev/null

  local dlq_url
  dlq_url=$(awslocal sqs get-queue-url --queue-name "${dlq_name}" --query 'QueueUrl' --output text)
  local dlq_arn
  dlq_arn=$(awslocal sqs get-queue-attributes \
    --queue-url "${dlq_url}" \
    --attribute-names QueueArn \
    --query 'Attributes.QueueArn' \
    --output text)

  # AWS CLI requires RedrivePolicy as a JSON-encoded string inside the attrs JSON.
  # Build the inner JSON, then embed it (escaped) as a string value.
  local redrive_json
  redrive_json=$(printf '{"deadLetterTargetArn":"%s","maxReceiveCount":"%s"}' \
    "${dlq_arn}" "${max_receive_count}")
  local redrive_escaped="${redrive_json//\"/\\\"}"

  local main_attrs_file="/tmp/${main_name}.attrs.json"
  printf '{"VisibilityTimeout":"%s","MessageRetentionPeriod":"345600","RedrivePolicy":"%s"}' \
    "${visibility_timeout}" "${redrive_escaped}" >"${main_attrs_file}"
  awslocal sqs create-queue \
    --queue-name "${main_name}" \
    --attributes "file://${main_attrs_file}" \
    >/dev/null
}

create_queue_with_dlq "grading-pipeline-events"        "grading-pipeline-events-dlq"        300 5
create_queue_with_dlq "grading-spreadsheet-conversion" "grading-spreadsheet-conversion-dlq" 300 3
create_queue_with_dlq "grading-pdf-generation"         "grading-pdf-generation-dlq"         300 3

PIPELINE_EVENTS_QUEUE_URL=$(awslocal sqs get-queue-url --queue-name "grading-pipeline-events" --query 'QueueUrl' --output text)
SPREADSHEET_CONVERSION_QUEUE_URL=$(awslocal sqs get-queue-url --queue-name "grading-spreadsheet-conversion" --query 'QueueUrl' --output text)
PDF_GENERATION_QUEUE_URL=$(awslocal sqs get-queue-url --queue-name "grading-pdf-generation" --query 'QueueUrl' --output text)

# ── EventBridge Scheduler group ─────────────────────────────────────────────
# CDK provisions this group; mirror it locally so exam-api can create/delete
# per-batch schedules against the same name in dev.
awslocal scheduler create-schedule-group \
  --name "${BATCH_POLLERS_GROUP_NAME}" \
  >/dev/null 2>&1 || true

# ── IAM role + placeholder batch-poller Lambda ──────────────────────────────
# Real ARNs (rather than fake strings) so SSM lookups + schedule creation work
# end-to-end against LocalStack. The handler is a no-op — the production zip is
# uploaded by CI in real environments.
SCHEDULER_TRUST_POLICY='{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "scheduler.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}'

awslocal iam create-role \
  --role-name "${SCHEDULER_ROLE_NAME}" \
  --assume-role-policy-document "${SCHEDULER_TRUST_POLICY}" \
  >/dev/null 2>&1 || true

SCHEDULER_ROLE_ARN=$(awslocal iam get-role \
  --role-name "${SCHEDULER_ROLE_NAME}" \
  --query 'Role.Arn' --output text)

# Lambda execution role — distinct from the scheduler role above. Trust must
# allow lambda.amazonaws.com (real AWS rejects mismatched principals; LocalStack
# is permissive but we keep parity with prod).
LAMBDA_TRUST_POLICY='{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "lambda.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}'

awslocal iam create-role \
  --role-name "${BATCH_POLLER_EXECUTION_ROLE_NAME}" \
  --assume-role-policy-document "${LAMBDA_TRUST_POLICY}" \
  >/dev/null 2>&1 || true

BATCH_POLLER_EXECUTION_ROLE_ARN=$(awslocal iam get-role \
  --role-name "${BATCH_POLLER_EXECUTION_ROLE_NAME}" \
  --query 'Role.Arn' --output text)

# Minimal handler.py packaged into a zip in /tmp.
mkdir -p /tmp/batch-poller-stub
cat >/tmp/batch-poller-stub/handler.py <<'PY'
def handler(event, context):
    return {"status": "noop", "received": event}
PY
(cd /tmp/batch-poller-stub && zip -q -r /tmp/batch-poller-stub.zip handler.py)

awslocal lambda create-function \
  --function-name "${BATCH_POLLER_FUNCTION_NAME}" \
  --runtime python3.12 \
  --handler handler.handler \
  --role "${BATCH_POLLER_EXECUTION_ROLE_ARN}" \
  --zip-file fileb:///tmp/batch-poller-stub.zip \
  --memory-size 256 \
  --timeout 60 \
  >/dev/null 2>&1 || true

BATCH_POLLER_LAMBDA_ARN=$(awslocal lambda get-function \
  --function-name "${BATCH_POLLER_FUNCTION_NAME}" \
  --query 'Configuration.FunctionArn' --output text)

# ── SSM parameters ─────────────────────────────────────────────────────────
# Mirror the parameters published by the CDK ComputeStack so exam-api can read
# them in dev exactly like in prod.
awslocal ssm put-parameter \
  --name "/grading/lambda/batch-poller-arn" \
  --value "${BATCH_POLLER_LAMBDA_ARN}" \
  --type String --overwrite >/dev/null
awslocal ssm put-parameter \
  --name "/grading/scheduler/batch-pollers-group-name" \
  --value "${BATCH_POLLERS_GROUP_NAME}" \
  --type String --overwrite >/dev/null
awslocal ssm put-parameter \
  --name "/grading/scheduler/batch-poller-role-arn" \
  --value "${SCHEDULER_ROLE_ARN}" \
  --type String --overwrite >/dev/null

cat >/tmp/localstack-exam-api.env <<EOF
AWS_REGION=${REGION}
AWS_S3_ENDPOINT_URL=http://localstack:4566
AWS_SES_ENDPOINT_URL=http://localstack:4566
AWS_SECRETSMANAGER_ENDPOINT_URL=http://localstack:4566
AWS_SQS_ENDPOINT_URL=http://localstack:4566
AWS_SSM_ENDPOINT_URL=http://localstack:4566
AWS_SCHEDULER_ENDPOINT_URL=http://localstack:4566
AWS_LAMBDA_ENDPOINT_URL=http://localstack:4566
DATABASE_URL=postgresql+asyncpg://grading_app:grading_pass@exam-api-postgres:5432/grading
COGNITO_USER_POOL_ID=replace-with-real-cognito-user-pool-id
COGNITO_APP_CLIENT_ID=replace-with-real-cognito-app-client-id
COGNITO_ISSUER_URL=replace-with-real-cognito-issuer-url
SES_FROM_ADDRESS=${FROM_EMAIL}
EXAM_CONFIG_BUCKET=${BUCKET_NAME}
PIPELINE_EVENTS_QUEUE_URL=${PIPELINE_EVENTS_QUEUE_URL}
SPREADSHEET_CONVERSION_QUEUE_URL=${SPREADSHEET_CONVERSION_QUEUE_URL}
PDF_GENERATION_QUEUE_URL=${PDF_GENERATION_QUEUE_URL}
BATCH_POLLER_LAMBDA_ARN=${BATCH_POLLER_LAMBDA_ARN}
BATCH_POLLERS_SCHEDULE_GROUP_NAME=${BATCH_POLLERS_GROUP_NAME}
BATCH_POLLER_SCHEDULER_ROLE_ARN=${SCHEDULER_ROLE_ARN}
EOF

cp /tmp/localstack-exam-api.env /var/lib/localstack/localstack-exam-api.env

echo "[localstack-init] wrote /var/lib/localstack/localstack-exam-api.env"
