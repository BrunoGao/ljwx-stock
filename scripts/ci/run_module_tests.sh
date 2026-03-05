#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

run_module_tests() {
  local requirements_file="$1"
  local test_path="$2"

  echo "[test] requirements=${requirements_file} tests=${test_path}"
  uv run --with-requirements "${requirements_file}" python -m pytest -q "${test_path}"
}

run_module_tests "agent/requirements.txt" "agent/tests"
run_module_tests "qlib_bootstrap/requirements.txt" "qlib_bootstrap/tests"
run_module_tests "qlib_predict/requirements.txt" "qlib_predict/tests"
