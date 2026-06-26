#!/usr/bin/env bash
# Run preprocessing steps enabled in pipeline.steps (attach_pi, culling).
#
# Usage:
#   ./run_preprocessing.sh [config.yaml]

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

read -r ATTACH_PI DO_CULL <<< "$(python "${CLI}" preprocessing-flags "${CONFIG}")"

if [[ "${ATTACH_PI}" == "0" && "${DO_CULL}" == "0" ]]; then
  echo "No preprocessing steps enabled (attach_pi, cull_pb, cull_roads)"
  exit 0
fi

if [[ "${ATTACH_PI}" == "1" ]]; then
  script=$(python "${CLI}" attach-pi-script "${CONFIG}")
  echo "=== preprocessing: attach_pi ==="
  python "${TOP_DIR}/${script}" --config "${CONFIG}"
  echo
fi

if [[ "${DO_CULL}" == "1" ]]; then
  echo "=== preprocessing: culling ==="
  bash "${SCRIPT_DIR}/run_ensemble_culling.sh" "${CONFIG}"
  echo
fi

echo "Preprocessing complete."
