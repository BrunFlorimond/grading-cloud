#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.localstack.yml"
ENV_FILE="${ROOT_DIR}/.env.localstack"
LOCALSTACK_CONTAINER="exam-api-localstack"
LOCALSTACK_ENV_PATH="/var/lib/localstack/localstack-exam-api.env"

get_env_value() {
  local key="$1"
  local file="$2"
  awk -F= -v k="${key}" '$1 == k {print substr($0, index($0, "=") + 1); exit}' "${file}"
}

echo "[1/4] Starting postgres + recreating localstack..."
docker compose -f "${COMPOSE_FILE}" up -d exam-api-postgres
docker compose -f "${COMPOSE_FILE}" up -d --force-recreate localstack

echo "[2/4] Waiting for LocalStack bootstrap env..."
for _ in $(seq 1 60); do
  if docker exec "${LOCALSTACK_CONTAINER}" test -f "${LOCALSTACK_ENV_PATH}" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! docker exec "${LOCALSTACK_CONTAINER}" test -f "${LOCALSTACK_ENV_PATH}" >/dev/null 2>&1; then
  echo "LocalStack bootstrap did not produce ${LOCALSTACK_ENV_PATH} in time."
  echo "Hint: check LocalStack logs. Cognito often requires LocalStack Pro."
  docker logs "${LOCALSTACK_CONTAINER}" --tail 80 || true
  exit 1
fi

echo "[3/4] Syncing .env.localstack from LocalStack..."
TMP_ENV_FILE="$(mktemp)"
PREVIOUS_ENV_FILE=""
if [[ -f "${ENV_FILE}" ]]; then
  PREVIOUS_ENV_FILE="$(mktemp)"
  cp "${ENV_FILE}" "${PREVIOUS_ENV_FILE}"
fi

docker cp "${LOCALSTACK_CONTAINER}:${LOCALSTACK_ENV_PATH}" "${TMP_ENV_FILE}"

if [[ -n "${PREVIOUS_ENV_FILE}" ]]; then
  for key in AWS_REGION COGNITO_USER_POOL_ID COGNITO_APP_CLIENT_ID COGNITO_ISSUER_URL; do
    previous_value="$(get_env_value "${key}" "${PREVIOUS_ENV_FILE}")"
    if [[ -z "${previous_value}" ]]; then
      continue
    fi

    if [[ "${key}" == "AWS_REGION" ]]; then
      current_value="$(get_env_value "${key}" "${TMP_ENV_FILE}")"
      if [[ -n "${current_value}" ]] && [[ "${current_value}" != "${previous_value}" ]]; then
        sed -i "s|^${key}=.*|${key}=${previous_value}|" "${TMP_ENV_FILE}"
      fi
      continue
    fi

    if grep -q "replace-with-real-cognito" "${TMP_ENV_FILE}" && [[ "${previous_value}" != *"replace-with-real-cognito"* ]]; then
      if grep -q "^${key}=" "${TMP_ENV_FILE}"; then
        sed -i "s|^${key}=.*|${key}=${previous_value}|" "${TMP_ENV_FILE}"
      else
        echo "${key}=${previous_value}" >> "${TMP_ENV_FILE}"
      fi
    fi
  done
fi

mv "${TMP_ENV_FILE}" "${ENV_FILE}"
if [[ -n "${PREVIOUS_ENV_FILE}" ]]; then
  rm -f "${PREVIOUS_ENV_FILE}"
fi

if grep -q "replace-with-real-cognito" "${ENV_FILE}"; then
  echo "Update Cognito values in ${ENV_FILE} before starting exam-api:"
  echo "- COGNITO_USER_POOL_ID"
  echo "- COGNITO_APP_CLIENT_ID"
  echo "- COGNITO_ISSUER_URL"
  exit 1
fi

echo "[4/4] Running migrations then starting exam-api..."
docker compose -f "${COMPOSE_FILE}" --profile migrations run --build --rm exam-api-migrations
#docker compose -f "${COMPOSE_FILE}" up -d exam-api

echo "LocalStack stack is ready."
echo "- API: http://localhost:8000"
echo "- Env file: ${ENV_FILE}"
