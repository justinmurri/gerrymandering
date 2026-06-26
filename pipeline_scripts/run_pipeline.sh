#!/usr/bin/env bash
# Run the full analysis pipeline for a state config.
#
# Executes enabled steps from pipeline.steps in order:
#   1. preprocessing  (attach_pi, cull_pb, cull_roads)
#   2. metrics
#   3. tables
#   4. figures
#
# Usage:
#   ./run_pipeline.sh [config.yaml]
#   ./run_pipeline.sh [config.yaml] --only preprocessing|metrics|tables|figures
#   ./run_pipeline.sh [config.yaml] --skip preprocessing|metrics|tables|figures
#
# Examples:
#   ./run_pipeline.sh config_UT.yaml
#   ./run_pipeline.sh config_UT.yaml --only metrics
#   ./run_pipeline.sh config_UT.yaml --skip preprocessing

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CLI="${SCRIPT_DIR}/config_cli.py"
CONFIG="${TOP_DIR}/config_UT.yaml"
ONLY=""
SKIP=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --only)
      ONLY="${2:-}"
      shift 2
      ;;
    --skip)
      SKIP="${2:-}"
      shift 2
      ;;
    --help|-h)
      sed -n '2,18p' "$0" | sed 's/^# \?//'
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

should_run() {
  local step="$1"
  if [[ -n "${ONLY}" && "${ONLY}" != "${step}" ]]; then
    return 1
  fi
  if [[ -n "${SKIP}" && "${SKIP}" == "${step}" ]]; then
    return 1
  fi
  return 0
}

read -r DO_PREPROCESS DO_METRICS DO_TABLES DO_FIGURES <<< "$(python "${CLI}" pipeline-flags "${CONFIG}")"

echo "============================================================"
echo "Pipeline: $(basename "${CONFIG}")"
echo "Config:   ${CONFIG}"
echo "============================================================"
echo

if should_run preprocessing && [[ "${DO_PREPROCESS}" == "1" ]]; then
  bash "${SCRIPT_DIR}/run_preprocessing.sh" "${CONFIG}"
elif should_run preprocessing; then
  echo "=== preprocessing: skipped (nothing enabled) ==="
  echo
fi

if should_run metrics; then
  if [[ "${DO_METRICS}" == "1" ]]; then
    bash "${SCRIPT_DIR}/run_metrics.sh" "${CONFIG}"
  else
    echo "=== metrics: skipped (pipeline.steps.metrics is empty) ==="
    echo
  fi
fi

if should_run tables; then
  if [[ "${DO_TABLES}" == "1" ]]; then
    bash "${SCRIPT_DIR}/run_tables.sh" "${CONFIG}"
  else
    echo "=== tables: skipped (pipeline.steps.tables is empty) ==="
    echo
  fi
fi

if should_run figures; then
  if [[ "${DO_FIGURES}" == "1" ]]; then
    bash "${SCRIPT_DIR}/run_figures.sh" "${CONFIG}"
  else
    echo "=== figures: skipped (pipeline.steps.figures is empty) ==="
    echo
  fi
fi

echo "============================================================"
echo "Pipeline complete."
echo "============================================================"
