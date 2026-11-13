#!/usr/bin/env bash
# Phase: keep Docker Compose and Kubernetes configuration consistent and valid.
#  * files duplicated into the kustomize tree (kustomize cannot read outside its root) are identical
#  * Prometheus jobs used by dashboards/alerts exist in both scrape configs
#  * docker compose config renders
#  * every kustomize overlay renders and (if docker is available) passes kubeconform schema checks
source "$(dirname "$0")/lib.sh"
cd "$ROOT"

log "compose <-> kubernetes config copies"
K=infrastructure/k8s/base/config
pairs=(
  "infrastructure/prometheus/alerts.yml:$K/alerts.yml"
  "infrastructure/mosquitto/mosquitto.conf:$K/mosquitto.conf"
  "infrastructure/mosquitto/acl:$K/acl"
  "infrastructure/mosquitto/entrypoint.sh:$K/entrypoint.sh"
  "infrastructure/grafana/provisioning/datasources/prometheus.yml:$K/grafana-datasource.yml"
)
for f in infrastructure/grafana/dashboards/*.json; do pairs+=("$f:$K/$(basename "$f")"); done
for p in "${pairs[@]}"; do
  a=${p%%:*}; b=${p#*:}
  diff -q <(tr -d '\r' <"$a") <(tr -d '\r' <"$b") >/dev/null || fail "$b differs from $a (copy it: cp $a $b)"
done
ok "${#pairs[@]} shared files identical"

log "prometheus jobs referenced by dashboards/alerts exist in both environments"
"$PY" - <<'EOF'
import re, sys, glob
need = {"coldguard-api", "coldguard-worker", "postgres", "redis"}
for f in ("infrastructure/prometheus/prometheus.yml", "infrastructure/k8s/base/config/prometheus.yml"):
    jobs = set(re.findall(r"job_name:\s*([\w-]+)", open(f, encoding="utf-8").read()))
    missing = need - jobs
    if missing:
        sys.exit(f"{f}: missing jobs {sorted(missing)}")
for f in glob.glob("infrastructure/grafana/dashboards/*.json"):
    import json
    json.load(open(f, encoding="utf-8"))  # valid JSON
print("ok")
EOF
ok "scrape jobs and dashboard JSON valid"

if command -v docker >/dev/null 2>&1; then
  log "docker compose config"
  tmp=$(mktemp)
  make_ephemeral_env "$tmp"
  docker compose --env-file "$tmp" -f docker-compose.yml config -q
  echo "PUBLIC_ORIGIN=https://coldguard.example.org" >>"$tmp"
  docker compose --env-file "$tmp" -f docker-compose.yml -f docker-compose.prod.yml config -q
  # every service that loads Settings must get an https origin in production (Settings refuses http)
  docker compose --env-file "$tmp" -f docker-compose.yml -f docker-compose.prod.yml config --format json | "$PY" -c "
import json, sys
svcs = json.load(sys.stdin)['services']
bad = [n for n, s in svcs.items() if (s.get('environment') or {}).get('ENVIRONMENT') == 'production'
       and any(not o.startswith('https://') for o in (s['environment'].get('BACKEND_CORS_ORIGINS') or 'https://').split(','))]
sys.exit(f'production services with non-https CORS origins: {bad}' if bad else 0)"
  ok "compose files render (dev + prod)"
fi

log "kustomize overlays render"
OUT="$ROOT/build/k8s-render"; rm -rf "$OUT"; mkdir -p "$OUT"
trap 'rm -rf "$OUT" "${tmp:-}"' EXIT        # the rendered local overlay contains secret values
for ov in infrastructure/k8s/overlays/*/; do
  name=$(basename "$ov")
  created=""
  if [ "$name" = local ] && [ ! -f "$ov/secrets.env" ]; then
    cp "$ov/secrets.env.example" "$ov/secrets.env"; created=1   # placeholder values, render only
  fi
  kubectl kustomize "$ov" >"$OUT/$name.yaml"
  [ -n "$created" ] && rm -f "$ov/secrets.env"
  ok "$name: $(grep -c '^kind:' "$OUT/$name.yaml") resources"
done

if command -v docker >/dev/null 2>&1 && [ "${SKIP_KUBECONFORM:-0}" != "1" ]; then
  log "kubeconform schema validation (Kubernetes ${KUBE_VERSION:-1.32.0})"
  host_out="$OUT"; command -v cygpath >/dev/null 2>&1 && host_out=$(cygpath -w "$OUT")   # Docker Desktop on Git Bash
  MSYS_NO_PATHCONV=1 docker run --rm -v "$host_out:/m:ro" ghcr.io/yannh/kubeconform:v0.6.7 \
    -strict -summary -kubernetes-version "${KUBE_VERSION:-1.32.0}" /m/local.yaml /m/production.yaml
fi
# rendered local overlay contains secret values from secrets.env — never keep it around
rm -rf "$OUT"
ok "configuration consistent"
