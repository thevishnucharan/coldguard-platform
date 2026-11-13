#!/usr/bin/env bash
# Phase: end-to-end checks against the local Kubernetes deployment (run after k8s-deploy.sh).
# Covers: ingress, service discovery, auth/RBAC, MQTT + REST ingestion, Prometheus targets,
# Grafana provisioning, HPA metrics, NetworkPolicy isolation, zero-downtime rolling update,
# pod self-healing and persistent data across a database pod restart.
source "$(dirname "$0")/lib.sh"
source "$(dirname "$0")/smoke-checks.sh"
cd "$ROOT"

CTX="${KUBE_CONTEXT:-kind-coldguard}"
guard_kube_context "$CTX"
K=(kubectl --context "$CTX" -n coldguard)
SECRETS=infrastructure/k8s/overlays/local/secrets.env
secret() { "${K[@]}" get secret coldguard-secrets -o "jsonpath={.data.$1}" | base64 -d; }

PIDS=()
cleanup() { for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT
forward() {  # forward <svc> <local> <remote>
  "${K[@]}" port-forward "svc/$1" "$2:$3" >/dev/null 2>&1 &
  PIDS+=($!)
}
forward backend 18001 8000
forward prometheus 19090 9090
forward grafana 13000 3000
sleep 4

INGRESS_HOST="${INGRESS_HOST:-coldguard.localhost}"
INGRESS_PORT="${INGRESS_PORT:-8088}"
CURL_EXTRA="--resolve $INGRESS_HOST:$INGRESS_PORT:127.0.0.1"
CURL=(curl -sS --max-time 20 $CURL_EXTRA)
UI_URL="http://$INGRESS_HOST:$INGRESS_PORT"
API_URL="http://localhost:18001"
PROM_URL="http://localhost:19090"
GRAFANA_URL="http://localhost:13000"
GRAFANA_PASSWORD=$(secret GRAFANA_ADMIN_PASSWORD)
INGEST_KEY=$(secret INGEST_API_KEY)
DEVICE_PW=$(secret MQTT_DEVICE_PASSWORD)
EXTRA_PROM_QUERIES='sum(kube_pod_container_status_ready{namespace="coldguard"}) count(container_memory_working_set_bytes{namespace="coldguard"})'
mqtt_publish() {
  "${K[@]}" exec deploy/mosquitto -- mosquitto_pub -h localhost -q 1 -u coldguard-device -P "$DEVICE_PW" -t "$1" -m "$2"
}

run_smoke_checks

log "HorizontalPodAutoscaler receives resource metrics"
retry 36 5 bash -c "[ -n \"\$(kubectl --context $CTX -n coldguard get hpa backend -o jsonpath='{.status.currentMetrics[0].resource.current.averageUtilization}')\" ]" \
  || fail "HPA backend has no CPU metrics (metrics-server?)"
"${K[@]}" get hpa
ok "HPAs report CPU utilisation"

log "NetworkPolicy isolation: an unlabeled pod cannot reach the data tier"
# probe pods must satisfy the namespace's "restricted" Pod Security Standard
probe() {  # probe <name> <labels-json> <shell command>
  local ov
  ov=$(printf '{"apiVersion":"v1","metadata":{"labels":%s},"spec":{"securityContext":{"runAsNonRoot":true,"runAsUser":65534,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"%s","image":"busybox:1.36","command":["sh","-c","%s"],"securityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]}}}]}}' "$2" "$1" "$3")
  "${K[@]}" run "$1" --image=busybox:1.36 --restart=Never --rm -i --quiet --overrides="$ov" >/dev/null 2>&1
}
if probe np-probe '{"np":"probe"}' 'nc -z -w 4 postgres 5432 || nc -z -w 4 redis 6379'; then
  fail "unlabeled pod reached postgres/redis — NetworkPolicies not enforced"
fi
probe np-probe-app '{"tier":"app"}' 'nc -z -w 4 redis 6379' || fail "app-tier pod could not reach redis"
ok "data tier reachable only from app/monitoring tiers"

log "Pod Security: the namespace enforces 'restricted' and every running pod complies"
[ "$("${K[@]}" get ns coldguard -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}')" = restricted ]   || fail "namespace does not enforce the restricted Pod Security Standard"
if kubectl --context "$CTX" label --dry-run=server --overwrite ns coldguard pod-security.kubernetes.io/enforce=restricted 2>&1 | grep -q violate; then
  fail "running pods violate the restricted Pod Security Standard"
fi
ok "restricted Pod Security Standard enforced; all pods compliant"

log "rolling update without dropped requests (backend + frontend through the ingress)"
errs=$(mktemp)
( end=$((SECONDS + 150)); while [ $SECONDS -lt $end ]; do
    c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 $CURL_EXTRA "$UI_URL/api/v1/health"); [ "$c" = 200 ] || echo "$c" >>"$errs"
    [ -f "$errs.stop" ] && break; sleep 0.3; done ) &
LOOP=$!
"${K[@]}" rollout restart deploy/backend deploy/frontend >/dev/null
"${K[@]}" rollout status deploy/backend --timeout=300s
"${K[@]}" rollout status deploy/frontend --timeout=300s
sleep 5; touch "$errs.stop"; wait $LOOP || true
nerr=$(wc -l <"$errs" | tr -d ' '); rm -f "$errs" "$errs.stop"
[ "$nerr" -eq 0 ] || fail "$nerr failed requests during rolling update"
ok "rolling update completed with 0 failed requests"

log "self-healing: deleted worker pod is replaced"
old=$("${K[@]}" get pod -l app.kubernetes.io/name=worker -o jsonpath='{.items[0].metadata.name}')
"${K[@]}" delete pod "$old" --wait=false >/dev/null
retry 40 5 bash -c "kubectl --context $CTX -n coldguard get pod -l app.kubernetes.io/name=worker -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[0].ready}{\"\\n\"}{end}' | grep -v '^$old ' | grep -q ' true$'" \
  || fail "worker pod not replaced"
ok "worker pod replaced and ready"

log "persistence: data survives a postgres pod restart"
# the rollout replaced the API pod, so re-establish the port-forward afterwards
count_users() { "${CURL[@]}" -f -H "Authorization: Bearer $(login admin@coldguard.local)" "$API_URL/api/v1/users?page_size=1" | json_get 'd.get("total", len(d) if isinstance(d, list) else 0)'; }
refwd() { cleanup; PIDS=(); forward backend 18001 8000; forward prometheus 19090 9090; forward grafana 13000 3000; sleep 4; }
refwd
before=$(count_users)
"${K[@]}" delete pod postgres-0 >/dev/null
"${K[@]}" wait --for=condition=ready pod/postgres-0 --timeout=300s
retry 30 5 bash -c "[ \"\$(curl -s -o /dev/null -w '%{http_code}' $CURL_EXTRA '$UI_URL/api/v1/health')\" = 200 ]"
refwd
retry 20 5 bash -c "[ \"\$(curl -s -o /dev/null -w '%{http_code}' '$API_URL/ready')\" = 200 ]" || fail "API not ready after postgres restart"
after=$(count_users)
[ "$before" = "$after" ] || fail "user count changed across postgres restart ($before -> $after)"
"${K[@]}" get pvc
ok "postgres PVC persisted data ($after users)"

ok "Kubernetes smoke test passed"
