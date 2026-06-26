#!/usr/bin/env bash
# Run figure scripts listed in pipeline.steps.figures.
#
# Usage:
#   ./run_figures.sh [config.yaml]
#   ./run_figures.sh [config.yaml] --ensembles districtPairsRA harvard recom1M
#
# --ensembles overrides the ensemble lists in config for every figure script.
# One ensemble → individual histogram for that ensemble only.
# Two or more → overlaid together on one histogram per figure type.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CLI="${SCRIPT_DIR}/config_cli.py"
CONFIG="${TOP_DIR}/config_UT.yaml"
ENSEMBLES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ensembles)
      shift
      while [[ $# -gt 0 && "$1" != --* ]]; do
        ENSEMBLES+=("$1")
        shift
      done
      ;;
    --help|-h)
      sed -n '2,10p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    -*)
      echo "Unknown option: $1"
      exit 1
      ;;
    *)
      CONFIG="$1"
      shift
      ;;
  esac
done

if [[ ! -f "${CONFIG}" ]]; then
  echo "Config not found: ${CONFIG}"
  exit 1
fi

# shellcheck source=/dev/null
source "${TOP_DIR}/.venv/bin/activate"
cd "${TOP_DIR}"

FIGURES=$(python "${CLI}" list figures "${CONFIG}")

if [[ -z "${FIGURES}" ]]; then
  echo "No figures listed in pipeline.steps.figures"
  exit 0
fi

ENSEMBLE_ARGS=()
if [[ ${#ENSEMBLES[@]} -gt 0 ]]; then
  ENSEMBLE_ARGS=(--ensembles "${ENSEMBLES[@]}")
  echo "Ensembles: ${ENSEMBLES[*]}"
  echo
fi

for fig in ${FIGURES}; do
  script=$(python "${CLI}" script figures "${fig}" "${CONFIG}")
  echo "=== figure: ${fig} ==="
  python "${TOP_DIR}/${script}" --config "${CONFIG}" "${ENSEMBLE_ARGS[@]}"
  echo
done
