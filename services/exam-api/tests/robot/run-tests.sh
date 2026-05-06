#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXAM_API_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${EXAM_API_DIR}/docker/robot/.env.robot.localstack"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing env file: ${ENV_FILE}"
  exit 1
fi

set -a
source "${ENV_FILE}"
set +a

cd "${SCRIPT_DIR}"
uv run robot ./exam_api_ci.robot
