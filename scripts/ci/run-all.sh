#!/usr/bin/env bash
# Run the same phases as the Jenkinsfile, locally, in order.
#   scripts/ci/run-all.sh                       # everything
#   PHASES="backend frontend config" scripts/ci/run-all.sh
#   PYTHON_BIN=backend/venv/Scripts/python.exe  # reuse an existing backend venv (Windows)
source "$(dirname "$0")/lib.sh"
PHASES="${PHASES:-backend frontend config security images compose k8s-deploy k8s-smoke}"
declare -A SCRIPT=([backend]=backend.sh [frontend]=frontend.sh [config]=config-check.sh [security]=security-scan.sh
                   [images]=build-images.sh [compose]=compose-smoke.sh [k8s-deploy]=k8s-deploy.sh [k8s-smoke]=k8s-smoke.sh)
summary=()
for p in $PHASES; do
  [ -n "${SCRIPT[$p]:-}" ] || fail "unknown phase $p"
  log "──────── phase: $p"
  start=$SECONDS
  bash "$ROOT/scripts/ci/${SCRIPT[$p]}"
  summary+=("$(printf '%-11s %4ss  passed' "$p" $((SECONDS - start)))")
done
log "summary"; printf '   %s\n' "${summary[@]}"
