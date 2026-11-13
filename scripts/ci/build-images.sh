#!/usr/bin/env bash
# Phase: build container images, tagged with the app version (used by compose + k8s base)
# and the git sha (traceability / registry push).
source "$(dirname "$0")/lib.sh"
cd "$ROOT"

build() {
  local name=$1 ctx=$2; shift 2
  log "docker build $name ($APP_VERSION, $IMAGE_TAG)"
  docker build "$@" -t "$name:$APP_VERSION" -t "$name:$IMAGE_TAG" "$ctx"
}
build coldguard-backend ./backend
build coldguard-frontend ./frontend --build-arg "VITE_SHOW_DEMO_LOGINS=${VITE_SHOW_DEMO_LOGINS:-true}"
build coldguard-simulator . -f simulator/Dockerfile
docker images --format '{{.Repository}}:{{.Tag}}  {{.Size}}' | grep -E '^coldguard-' | sort
ok "images built"
