#!/usr/bin/env bash
# Phase: bring up the FULL Docker Compose stack with throw-away secrets and run end-to-end checks.
#   KEEP_STACK=1  leave it running afterwards     NO_BUILD=1  use already-built images
#   SMOKE_PROJECT  compose project name (default cg-smoke)
source "$(dirname "$0")/lib.sh"
source "$(dirname "$0")/smoke-checks.sh"
cd "$ROOT"

P="${SMOKE_PROJECT:-cg-smoke}"
ENVF=$(mktemp)
make_ephemeral_env "$ENVF"
DC=(docker compose -p "$P" --env-file "$ENVF" -f docker-compose.yml)

cleanup() {
  local rc=$?
  if [ $rc -ne 0 ]; then
    log "failure diagnostics"
    "${DC[@]}" ps -a || true
    "${DC[@]}" logs --tail 60 backend worker migrate 2>/dev/null | tail -n 150 || true
  fi
  if [ "${KEEP_STACK:-0}" != "1" ]; then
    log "tearing down $P"; "${DC[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  else
    log "stack $P left running (secrets in $ENVF)"
  fi
  [ "${KEEP_STACK:-0}" = "1" ] || rm -f "$ENVF"
  exit $rc
}
trap cleanup EXIT

log "docker compose up ($P)"
BUILD=(--build); [ "${NO_BUILD:-0}" = "1" ] && BUILD=(--no-build)
"${DC[@]}" up -d "${BUILD[@]}" --remove-orphans

set -a; source "$ENVF"; set +a
UI_URL="http://localhost:${UI_PORT:-8080}"
API_URL="http://localhost:8001"
PROM_URL="http://localhost:9090"
GRAFANA_URL="http://localhost:3000"
GRAFANA_PASSWORD="$GRAFANA_ADMIN_PASSWORD"
INGEST_KEY="$INGEST_API_KEY"
EXTRA_PROM_QUERIES='count(container_last_seen{container_label_com_docker_compose_service="backend"}) sum(container_health_status{container_label_com_docker_compose_service="backend",status="healthy"}) sum(container_memory_working_set_bytes{container_label_com_docker_compose_service="postgres"})'
mqtt_publish() {
  "${DC[@]}" exec -T mosquitto mosquitto_pub -h localhost -q 1 -u coldguard-device -P "$MQTT_DEVICE_PASSWORD" -t "$1" -m "$2"
}

retry 60 5 bash -c "[ \"\$(docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' ${P}-migrate-1 2>/dev/null)\" = 'exited 0' ]" \
  || fail "migration job did not complete"
ok "migrations + demo seed completed"

run_smoke_checks

log "restart handling: the API process dies, the restart policy brings it back"
# `docker kill` counts as a manual stop (no restart); a crash is the main process exiting on its own
rc0=$(docker inspect -f '{{.RestartCount}}' "${P}-backend-1")
docker exec "${P}-backend-1" sh -c 'kill -TERM 1' || true
retry 40 3 bash -c "[ \"\$(docker inspect -f '{{.RestartCount}} {{.State.Health.Status}}' ${P}-backend-1)\" = '$((rc0 + 1)) healthy' ]"   || fail "backend not restarted to healthy (restarts: $(docker inspect -f '{{.RestartCount}} {{.State.Status}}' "${P}-backend-1"))"
expect_code 200 "$API_URL/ready"
ok "backend restarted by restart policy and healthy again"

log "persistence: data survives a postgres restart"
before=$("${CURL[@]}" -f -H "Authorization: Bearer $ADMIN" "$API_URL/api/v1/users?page_size=1" | json_get 'd.get("total", len(d) if isinstance(d, list) else 0)')
"${DC[@]}" restart postgres >/dev/null
retry 30 3 bash -c "[ \"\$(curl -s -o /dev/null -w '%{http_code}' '$API_URL/ready')\" = 200 ]" || fail "API not ready after postgres restart"
after=$("${CURL[@]}" -f -H "Authorization: Bearer $(login admin@coldguard.local)" "$API_URL/api/v1/users?page_size=1" | json_get 'd.get("total", len(d) if isinstance(d, list) else 0)')
[ "$before" = "$after" ] || fail "user count changed across postgres restart ($before -> $after)"
ok "postgres volume persisted ($after users)"

ok "Docker Compose smoke test passed"
