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
  for f in secrets.env azure-params.env; do   # example values, render only
    if [ -f "$ov/$f.example" ] && [ ! -f "$ov/$f" ]; then cp "$ov/$f.example" "$ov/$f"; created="$created $ov/$f"; fi
  done
  kubectl kustomize "$ov" >"$OUT/$name.yaml"
  [ -n "$created" ] && rm -f $created
  if [ "$name" = azure ]; then
    grep -q 'placeholder' "$OUT/$name.yaml" && fail "azure overlay: unreplaced placeholder"
    grep -qE '^kind: (StatefulSet|Secret)$' "$OUT/$name.yaml" && fail "azure overlay must not contain the in-cluster database or literal Secrets"
  fi
  ok "$name: $(grep -c '^kind:' "$OUT/$name.yaml") resources"
done
kubectl kustomize infrastructure/k8s/azure-monitor >"$OUT/azure-monitor.yaml"
ok "azure-monitor: $(grep -c '^kind:' "$OUT/azure-monitor.yaml") resources"

if command -v docker >/dev/null 2>&1 && [ "${SKIP_KUBECONFORM:-0}" != "1" ]; then
  log "kubeconform schema validation (Kubernetes ${KUBE_VERSION:-1.32.0})"
  host_out="$OUT"; command -v cygpath >/dev/null 2>&1 && host_out=$(cygpath -w "$OUT")   # Docker Desktop on Git Bash
  MSYS_NO_PATHCONV=1 docker run --rm -v "$host_out:/m:ro" ghcr.io/yannh/kubeconform:v0.6.7 \
    -strict -summary -kubernetes-version "${KUBE_VERSION:-1.32.0}"     -schema-location default     -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'     /m/local.yaml /m/production.yaml /m/azure.yaml /m/azure-monitor.yaml
fi

log "terraform (Azure infrastructure): fmt + validate"
TF_DIR=infrastructure/azure/terraform
tf_ok=""
if command -v terraform >/dev/null 2>&1 && terraform version -json 2>/dev/null | "$PY" -c "import json,sys; v=json.load(sys.stdin)['terraform_version'].split('.'); sys.exit(0 if (int(v[0]),int(v[1]))>=(1,6) else 1)"; then
  terraform -chdir="$TF_DIR" fmt -check -recursive
  terraform -chdir="$TF_DIR" init -backend=false -input=false >/dev/null
  terraform -chdir="$TF_DIR" validate -no-color && tf_ok=1
elif command -v docker >/dev/null 2>&1 && [ "${SKIP_TERRAFORM:-0}" != "1" ]; then
  host_tf="$ROOT/$TF_DIR"; command -v cygpath >/dev/null 2>&1 && host_tf=$(cygpath -w "$host_tf")
  TF=(docker run --rm -v "$host_tf:/tf" -w /tf hashicorp/terraform:1.9.8)
  MSYS_NO_PATHCONV=1 "${TF[@]}" fmt -check -recursive
  MSYS_NO_PATHCONV=1 "${TF[@]}" init -backend=false -input=false >/dev/null
  MSYS_NO_PATHCONV=1 "${TF[@]}" validate -no-color && tf_ok=1
fi
[ -n "$tf_ok" ] && ok "terraform valid" || echo "terraform >= 1.6 / docker not available — skipped"
# rendered local overlay contains secret values from secrets.env — never keep it around
rm -rf "$OUT"
ok "configuration consistent"
