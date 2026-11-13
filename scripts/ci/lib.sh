#!/usr/bin/env bash
# Shared helpers for the CI phase scripts. Sourced, not executed.
# The same scripts run in Jenkins (Linux agent) and locally (Linux/macOS/Git Bash on Windows).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPORTS="${REPORTS_DIR:-$ROOT/reports}"
mkdir -p "$REPORTS"

APP_VERSION="${APP_VERSION:-2.0.0}"          # image tag referenced by compose + k8s base
IMAGE_TAG="${IMAGE_TAG:-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo local)}"

c_info=$'\033[36m'; c_ok=$'\033[32m'; c_err=$'\033[31m'; c_off=$'\033[0m'
log()  { printf '%s==>%s %s\n' "$c_info" "$c_off" "$*"; }
ok()   { printf '%s ✔%s  %s\n' "$c_ok" "$c_off" "$*"; }
fail() { printf '%s ✘  %s%s\n' "$c_err" "$*" "$c_off" >&2; exit 1; }

# python used only for small JSON/YAML checks in the scripts (not the backend runtime)
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then PY="$c"; break; fi
  done
fi
[ -n "$PY" ] || fail "python >= 3.9 is required for the CI helper checks"

# json_get '<python expression on d>'  (reads JSON from stdin)
json_get() { "$PY" -c "import json,sys; d=json.load(sys.stdin); print($1)"; }

rand() { head -c 2048 /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9' | cut -c "1-${1:-40}"; }

# retry <attempts> <sleep-seconds> <command...>
retry() {
  local n=$1 s=$2; shift 2
  for i in $(seq 1 "$n"); do
    if "$@"; then return 0; fi
    [ "$i" -lt "$n" ] && sleep "$s"
  done
  return 1
}

# Write a throw-away env file with random secrets (never committed, deleted on exit by callers).
make_ephemeral_env() {
  local f=$1 pg; pg=$(rand 24)
  cat >"$f" <<EOF
ENVIRONMENT=development
DEMO_MODE=true
POSTGRES_USER=coldguard
POSTGRES_PASSWORD=$pg
POSTGRES_DB=coldguard
SECRET_KEY=$(rand 64)
INGEST_API_KEY=$(rand 32)
MQTT_INGESTOR_PASSWORD=$(rand 24)
MQTT_DEVICE_PASSWORD=$(rand 24)
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$(rand 24)
UI_PORT=${UI_PORT:-8080}
LOG_LEVEL=INFO
EOF
}

# Refuse to touch anything but a local cluster unless explicitly allowed.
guard_kube_context() {
  local ctx=$1
  case "$ctx" in
    kind-*|minikube|docker-desktop|rancher-desktop|k3d-*) return 0 ;;
  esac
  [ "${ALLOW_REMOTE_CONTEXT:-0}" = "1" ] || fail "Refusing to deploy to non-local kube context '$ctx' (set ALLOW_REMOTE_CONTEXT=1 to override)"
}
