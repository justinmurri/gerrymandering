#!/usr/bin/env bash
# Convert raw chain file(s) to canonical JSONL, then PB / road culling per config.
#
# Usage:
#   ./run_ensemble_culling.sh [config.yaml]
#   ./run_ensemble_culling.sh [config.yaml] -- <chain.jsonl> <ensemble_name> [...]
#
# With no manual pairs, culls every ensemble in pipeline.steps.cull_ensembles
# (default: all entries in ensembles). PB and road steps follow pipeline.steps.cull_pb
# and pipeline.steps.cull_roads.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TOOLS="${SCRIPT_DIR}/graph_and_chain_tools"
CLI="${SCRIPT_DIR}/config_cli.py"
CONFIG="${1:-${TOP_DIR}/config_UT.yaml}"
VENV="${TOP_DIR}/.venv/bin/activate"

if [[ ! -f "${CONFIG}" ]]; then
  echo "Config not found: ${CONFIG}"
  exit 1
fi

shift || true

MANUAL=0
if [[ "${1:-}" == "--" ]]; then
  MANUAL=1
  shift
  if [[ $# -lt 2 || $(( $# % 2 )) -ne 0 ]]; then
    echo "Usage: $0 [config.yaml] -- <chain.jsonl> <ensemble_name> [...]"
    exit 1
  fi
fi

# shellcheck source=/dev/null
source "${VENV}"
cd "${TOP_DIR}"

read -r DO_PB DO_ROADS ROAD_TYPES <<< "$(python "${CLI}" cull-settings "${CONFIG}")"

if [[ "${DO_PB}" == "0" && "${DO_ROADS}" == "0" ]]; then
  echo "Both cull_pb and cull_roads are disabled; nothing to cull."
  exit 0
fi

CULL_ARGS=(--config "${CONFIG}")
if [[ "${DO_PB}" == "1" ]]; then
  CULL_ARGS+=(--pb)
else
  CULL_ARGS+=(--no-pb)
fi
if [[ "${DO_ROADS}" == "1" ]]; then
  # shellcheck disable=SC2206
  CULL_ARGS+=(--roads ${ROAD_TYPES})
else
  CULL_ARGS+=(--roads)
fi

process_pair() {
  local raw="$1"
  local name="$2"
  local canonical="${TOP_DIR}/$(python "${CLI}" canonical-path "${CONFIG}" "${name}")"

  if [[ ! -f "${raw}" ]]; then
    echo "Missing file: ${raw}"
    return 1
  fi

  echo "=== ${name}: convert ==="
  python "${TOOLS}/convert_chain_jsonl.py" "${raw}" "${canonical}"

  echo "=== ${name}: cull ==="
  python "${TOOLS}/cull_ensemble.py" \
    "${CULL_ARGS[@]}" \
    --input "${canonical}" \
    --name "${name}"
  echo
}

if [[ "${MANUAL}" == "1" ]]; then
  while [[ $# -ge 2 ]]; do
    process_pair "$1" "$2"
    shift 2
  done
else
  while IFS=$'\t' read -r raw name; do
    if [[ ! -f "${raw}" ]]; then
      echo "Skipping ${name}: raw chain not found at ${raw}"
      continue
    fi
    process_pair "${raw}" "${name}"
  done < <(python "${CLI}" cull-pairs "${CONFIG}" "${TOP_DIR}")
fi

echo "Culling complete."
