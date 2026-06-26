#!/usr/bin/env bash
# Run table scripts listed in pipeline.steps.tables (or all configured tables).
#
# Usage:
#   ./run_tables.sh [config.yaml]

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

TABLES=$(python "${CLI}" list tables "${CONFIG}")

if [[ -z "${TABLES}" ]]; then
  echo "No tables listed in pipeline.steps.tables"
  exit 0
fi

for table in ${TABLES}; do
  script=$(python "${CLI}" script tables "${table}" "${CONFIG}")
  echo "=== table: ${table} ==="
  python "${TOP_DIR}/${script}" --config "${CONFIG}"
  echo
done
