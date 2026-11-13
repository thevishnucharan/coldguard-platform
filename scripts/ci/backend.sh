#!/usr/bin/env bash
# Phase: backend lint + tests (JUnit + coverage into reports/).
#   PYTHON_BIN=backend/venv/Scripts/python.exe scripts/ci/backend.sh   # reuse an existing venv
source "$(dirname "$0")/lib.sh"
# resolve a relative PYTHON_BIN against the repo root before changing directory
if [ -n "${PYTHON_BIN:-}" ] && [ "${PYTHON_BIN#/}" = "$PYTHON_BIN" ] && [ -e "$ROOT/$PYTHON_BIN" ]; then PYTHON_BIN="$ROOT/$PYTHON_BIN"; fi
cd "$ROOT/backend"

if [ -n "${PYTHON_BIN:-}" ]; then
  BPY="$PYTHON_BIN"
else
  VENV="${VENV_DIR:-$ROOT/backend/.ci-venv}"
  if [ ! -x "$VENV/bin/python" ] && [ ! -x "$VENV/Scripts/python.exe" ]; then
    log "creating virtualenv $VENV"
    "$PY" -m venv "$VENV"
  fi
  BPY="$VENV/bin/python"; [ -x "$BPY" ] || BPY="$VENV/Scripts/python.exe"
  log "installing backend dependencies"
  "$BPY" -m pip install -q --upgrade pip
  "$BPY" -m pip install -q -r requirements-dev.txt pytest-cov ruff
fi

log "ruff (non-blocking: reported, not gating)"
if "$BPY" -m ruff --version >/dev/null 2>&1; then
  "$BPY" -m ruff check app/ --output-format=concise --exit-zero | tail -n 15
else
  echo "ruff not installed — skipped"
fi

log "pytest"
COV=()
"$BPY" -c "import pytest_cov" 2>/dev/null && COV=(--cov=app --cov-report=xml:"$REPORTS/backend-coverage.xml" --cov-report=term:skip-covered)
"$BPY" -m pytest tests -q -p no:cacheprovider --junitxml="$REPORTS/backend-tests.xml" "${COV[@]}"
ok "backend tests passed"
