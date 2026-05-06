#!/usr/bin/env bash
set -euo pipefail

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-eu-west-1}}"
BUCKET_NAME="grading-cloud-local-exam-config"
FROM_EMAIL="no-reply@local.grading-cloud"

awslocal s3 mb "s3://${BUCKET_NAME}" >/dev/null
awslocal ses verify-email-identity --email-address "${FROM_EMAIL}" >/dev/null

cat >/tmp/localstack-exam-api.env <<EOF
AWS_REGION=${REGION}
AWS_S3_ENDPOINT_URL=http://localstack:4566
AWS_SES_ENDPOINT_URL=http://localstack:4566
AWS_SECRETSMANAGER_ENDPOINT_URL=http://localstack:4566
DATABASE_URL=postgresql+asyncpg://grading_app:grading_pass@exam-api-postgres:5432/grading
COGNITO_USER_POOL_ID=replace-with-real-cognito-user-pool-id
COGNITO_APP_CLIENT_ID=replace-with-real-cognito-app-client-id
COGNITO_ISSUER_URL=replace-with-real-cognito-issuer-url
SES_FROM_ADDRESS=${FROM_EMAIL}
EXAM_CONFIG_BUCKET=${BUCKET_NAME}
EOF

cp /tmp/localstack-exam-api.env /var/lib/localstack/localstack-exam-api.env

echo "[localstack-init] wrote /var/lib/localstack/localstack-exam-api.env"
