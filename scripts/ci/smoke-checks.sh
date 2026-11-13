#!/usr/bin/env bash
# End-to-end checks shared by the Compose and Kubernetes smoke phases. Sourced by
# compose-smoke.sh / k8s-smoke.sh, which set:
#   UI_URL API_URL PROM_URL GRAFANA_URL GRAFANA_PASSWORD INGEST_KEY  and  mqtt_publish()
# Demo accounts exist only with DEMO_MODE=true (documented demo password).
DEMO_PASSWORD="${SMOKE_DEMO_PASSWORD:-ColdGuard#2026}"
CURL=(curl -sS --max-time 20 ${CURL_EXTRA:-})

http_code() { "${CURL[@]}" -o /dev/null -w '%{http_code}' "$@"; }
expect_code() {
  local want=$1; shift
  local got; got=$(http_code "$@")
  [ "$got" = "$want" ] || fail "expected HTTP $want, got $got: $*"
}
login() {
  "${CURL[@]}" -f -X POST "$API_URL/api/v1/auth/login" -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode "username=$1" --data-urlencode "password=$DEMO_PASSWORD" | json_get 'd["access_token"]'
}
prom_query() {  # prints the first sample value or empty
  "${CURL[@]}" -fG "$PROM_URL/api/v1/query" --data-urlencode "query=$1" \
    | json_get '(d["data"]["result"][0]["value"][1] if d["data"]["result"] else "")'
}
prom_positive() { local v; v=$(prom_query "$1"); [ -n "$v" ] && "$PY" -c "import sys; sys.exit(0 if float('$v') > 0 else 1)"; }

run_smoke_checks() {
  log "probes"
  retry 60 5 bash -c "[ \"\$(curl -s -o /dev/null -w '%{http_code}' ${CURL_EXTRA:-} '$API_URL/ready')\" = 200 ]" || fail "API not ready at $API_URL/ready"
  expect_code 200 "$API_URL/health"
  expect_code 200 "$UI_URL/healthz"
  "${CURL[@]}" -f "$UI_URL/" | grep -q '<div id="root"' || fail "UI index not served"
  expect_code 200 "$UI_URL/api/v1/health"        # nginx -> backend service discovery
  ok "API, UI and UI->API proxy healthy"

  log "authentication and authorization"
  expect_code 401 "$API_URL/api/v1/users"
  expect_code 401 -H "Authorization: Bearer forged.token.value" "$API_URL/api/v1/auth/me"
  ADMIN=$(login admin@coldguard.local)
  OPER=$(login operator.blr@coldguard.local)
  [ "$("${CURL[@]}" -f -H "Authorization: Bearer $ADMIN" "$API_URL/api/v1/auth/me" | json_get 'd["role"]')" = ADMIN ] || fail "admin /me"
  expect_code 403 -H "Authorization: Bearer $OPER" "$API_URL/api/v1/users"
  expect_code 403 -H "Authorization: Bearer $OPER" -X POST -H 'Content-Type: application/json' \
    -d '{"storage_unit_id":"00000000-0000-0000-0000-000000000000"}' "$API_URL/api/v1/logistics/route-plans"
  ok "JWT login, forged-token rejection, RBAC denials"

  log "application features"
  "${CURL[@]}" -f -H "Authorization: Bearer $ADMIN" "$API_URL/api/v1/logistics/model" | json_get 'd["available"]' | grep -q True \
    || fail "route ETA model not loaded in the container"
  expect_code 200 -H "Authorization: Bearer $ADMIN" "$API_URL/api/v1/logistics/excursions"
  expect_code 200 -H "Authorization: Bearer $ADMIN" "$API_URL/api/v1/dashboards/admin"
  # seeded supply-chain scenario: a vehicle in transit whose data logger failed half-way
  n=$("${CURL[@]}" -f -H "Authorization: Bearer $OPER" "$API_URL/api/v1/logistics/transit-alerts" | json_get 'len(d)')
  [ "$n" -ge 1 ] || fail "expected the seeded in-transit sensor-failure alert"
  "${CURL[@]}" -f -H "Authorization: Bearer $OPER" "$API_URL/api/v1/logistics/transit-alerts" \
    | json_get 'd[0]["nearby"][0]["facility_name"]' >/dev/null || fail "transit alert has no nearby cold-chain store"
  ok "dashboards, ML routing and in-transit alerting respond ($n active transit alert(s))"

  log "telemetry ingestion (REST gateway + MQTT)"
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  expect_code 202 -X POST -H "X-Ingest-Key: $INGEST_KEY" -H 'Content-Type: application/json' \
    -d "{\"sensor_code\":\"S-BLR-JAY-ILR-1\",\"temperature\":5.1,\"timestamp\":\"$now\",\"message_id\":\"smoke-rest-$RANDOM$RANDOM\"}" \
    "$API_URL/api/v1/temperature/readings"
  expect_code 401 -X POST -H 'X-Ingest-Key: wrong' -H 'Content-Type: application/json' -d '{}' "$API_URL/api/v1/temperature/readings"
  mqtt_publish "coldguard/telemetry/BLR-HEB/S-BLR-HEB-ILR-1" \
    "{\"sensor_code\":\"S-BLR-HEB-ILR-1\",\"temperature\":4.8,\"timestamp\":\"$now\",\"message_id\":\"smoke-mqtt-$RANDOM$RANDOM\"}"
  "${CURL[@]}" -f -X POST -H "Authorization: Bearer $ADMIN" -H 'Content-Type: application/json' \
    -d '{"interval_seconds": 5}' "$API_URL/api/v1/demo/simulation/start" >/dev/null
  ok "REST + MQTT readings submitted, simulation started"

  log "Prometheus targets and signals"
  retry 36 5 bash -c "curl -sf ${CURL_EXTRA:-} '$PROM_URL/api/v1/targets?state=active' | $PY -c \"import json,sys; t=json.load(sys.stdin)['data']['activeTargets']; bad=[x['labels']['job'] for x in t if x['health']!='up']; print('down:', bad or 'none'); sys.exit(1 if bad or not t else 0)\"" \
    || fail "some Prometheus targets are down"
  for q in 'max(up{job="coldguard-api"})' 'max(up{job="coldguard-worker"})' 'max(pg_up)' 'max(redis_up)' \
           'max(coldguard_mqtt_connected)' 'sum(coldguard_http_requests_total)' \
           'time() - max(coldguard_worker_last_heartbeat_timestamp) < 180' ${EXTRA_PROM_QUERIES:-}; do
    retry 24 5 prom_positive "$q" || fail "Prometheus signal missing/zero: $q"
    printf '   %s  %s\n' "✔" "$q"
  done
  # sensor ingestion counter (REST/MQTT/simulator all feed it)
  retry 30 5 prom_positive 'sum(coldguard_telemetry_accepted_total)' || fail "no telemetry accepted"
  ok "ingestion, MQTT, worker, database, cache and API metrics present"

  log "Grafana provisioning"
  n=$("${CURL[@]}" -f -u "admin:$GRAFANA_PASSWORD" "$GRAFANA_URL/api/search?type=dash-db" | json_get 'len([x for x in d if x["uid"].startswith("cg-")])')
  [ "$n" -ge 4 ] || fail "expected 4 ColdGuard dashboards in Grafana, found $n"
  "${CURL[@]}" -f -u "admin:$GRAFANA_PASSWORD" "$GRAFANA_URL/api/datasources" | json_get '[x["type"] for x in d]' | grep -q prometheus \
    || fail "Prometheus datasource not provisioned"
  expect_code 401 "$GRAFANA_URL/api/search"
  ok "$n dashboards + Prometheus datasource provisioned; anonymous access denied"
}
