#!/usr/bin/env bash
# Run metric scripts listed in pipeline.steps.metrics.
#
# Usage:
#   ./run_metrics.sh [config.yaml]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CLI="${SCRIPT_DIR}/config_cli.py"
CONFIG="${1:-${TOP_DIR}/config_UT.yaml}"
VENV="${TOP_DIR}/.venv/bin/activate"

if [[ ! -f "${CONFIG}" ]]; then
  echo "Config not found: ${CONFIG}"
  exit 1
fi

# shellcheck source=/dev/null
source "${VENV}"
cd "${TOP_DIR}"

METRICS=$(python "${CLI}" list metrics "${CONFIG}")

if [[ -z "${METRICS}" ]]; then
  echo "No metrics listed in pipeline.steps.metrics"
  exit 1
fi

for metric in ${METRICS}; do
  script=$(python "${CLI}" script metrics "${metric}" "${CONFIG}")
  echo "=== metric: ${metric} ==="
  python "${TOP_DIR}/${script}" --config "${CONFIG}"
  echo
done
