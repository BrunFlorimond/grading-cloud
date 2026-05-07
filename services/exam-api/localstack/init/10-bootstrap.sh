#!/usr/bin/env bash
set -euo pipefail

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-eu-west-1}}"
BUCKET_NAME="grading-cloud-local-exam-config"
FROM_EMAIL="no-reply@local.grading-cloud"

awslocal s3 mb "s3://${BUCKET_NAME}" >/dev/null
awslocal ses verify-email-identity --email-address "${FROM_EMAIL}" >/dev/null

create_queue_with_dlq() {
  local main_name="$1"
  local dlq_name="$2"
  local visibility_timeout="$3"
  local max_receive_count="$4"

  awslocal sqs create-queue \
    --queue-name "${dlq_name}" \
    --attributes "MessageRetentionPeriod=1209600" \
    >/dev/null

  local dlq_url
  dlq_url=$(awslocal sqs get-queue-url --queue-name "${dlq_name}" --query 'QueueUrl' --output text)
  local dlq_arn
  dlq_arn=$(awslocal sqs get-queue-attributes \
    --queue-url "${dlq_url}" \
    --attribute-names QueueArn \
    --query 'Attributes.QueueArn' \
    --output text)

  local redrive
  redrive=$(printf '{"deadLetterTargetArn":"%s","maxReceiveCount":"%s"}' "${dlq_arn}" "${max_receive_count}")

  awslocal sqs create-queue \
    --queue-name "${main_name}" \
    --attributes "VisibilityTimeout=${visibility_timeout},MessageRetentionPeriod=345600,RedrivePolicy=${redrive}" \
    >/dev/null
}

create_queue_with_dlq "grading-pipeline-events"        "grading-pipeline-events-dlq"        300 5
create_queue_with_dlq "grading-spreadsheet-conversion" "grading-spreadsheet-conversion-dlq" 300 3
create_queue_with_dlq "grading-pdf-generation"         "grading-pdf-generation-dlq"         300 3

PIPELINE_EVENTS_QUEUE_URL=$(awslocal sqs get-queue-url --queue-name "grading-pipeline-events" --query 'QueueUrl' --output text)
SPREADSHEET_CONVERSION_QUEUE_URL=$(awslocal sqs get-queue-url --queue-name "grading-spreadsheet-conversion" --query 'QueueUrl' --output text)
PDF_GENERATION_QUEUE_URL=$(awslocal sqs get-queue-url --queue-name "grading-pdf-generation" --query 'QueueUrl' --output text)

cat >/tmp/localstack-exam-api.env <<EOF
AWS_REGION=${REGION}
AWS_S3_ENDPOINT_URL=http://localstack:4566
AWS_SES_ENDPOINT_URL=http://localstack:4566
AWS_SECRETSMANAGER_ENDPOINT_URL=http://localstack:4566
AWS_SQS_ENDPOINT_URL=http://localstack:4566
DATABASE_URL=postgresql+asyncpg://grading_app:grading_pass@exam-api-postgres:5432/grading
COGNITO_USER_POOL_ID=replace-with-real-cognito-user-pool-id
COGNITO_APP_CLIENT_ID=replace-with-real-cognito-app-client-id
COGNITO_ISSUER_URL=replace-with-real-cognito-issuer-url
SES_FROM_ADDRESS=${FROM_EMAIL}
EXAM_CONFIG_BUCKET=${BUCKET_NAME}
PIPELINE_EVENTS_QUEUE_URL=${PIPELINE_EVENTS_QUEUE_URL}
SPREADSHEET_CONVERSION_QUEUE_URL=${SPREADSHEET_CONVERSION_QUEUE_URL}
PDF_GENERATION_QUEUE_URL=${PDF_GENERATION_QUEUE_URL}
EOF

cp /tmp/localstack-exam-api.env /var/lib/localstack/localstack-exam-api.env

echo "[localstack-init] wrote /var/lib/localstack/localstack-exam-api.env"
