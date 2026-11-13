#!/usr/bin/env bash
# Phase: deploy to a LOCAL Kubernetes cluster (kind by default) with kustomize.
#   KUBE_CONTEXT=kind-coldguard  OVERLAY=local  KIND_BIN=kind  scripts/ci/k8s-deploy.sh
# Creates the kind cluster (with ingress-nginx + metrics-server) when it does not exist, loads
# the locally built images, generates git-ignored secrets and waits for every rollout.
source "$(dirname "$0")/lib.sh"
cd "$ROOT"

CTX="${KUBE_CONTEXT:-kind-coldguard}"
OVERLAY="${OVERLAY:-local}"
KIND="${KIND_BIN:-kind}"
guard_kube_context "$CTX"
K=(kubectl --context "$CTX")
INGRESS_NGINX_VERSION=controller-v1.12.0
METRICS_SERVER_VERSION=v0.7.2
INGRESS_CONTROLLER="${INGRESS_CONTROLLER:-nginx}"   # nginx | traefik (kind fallback when registry.k8s.io is unreachable)

# Docker Desktop's containerd image store keeps multi-platform indexes whose other-platform
# blobs were never pulled; `kind load docker-image` then fails with "content digest not found".
# Saving a single platform to an archive avoids that and works with every Docker version.
kind_load() {
  local plat="linux/$(docker version -f '{{.Server.Arch}}')" dir; dir=$(mktemp -d)
  for img in "$@"; do
    local tar="$dir/img.tar"
    docker save --platform "$plat" -o "$tar" "$img" 2>/dev/null || docker save -o "$tar" "$img"
    local arg="$tar"; command -v cygpath >/dev/null 2>&1 && arg=$(cygpath -w "$tar")
    "$KIND" load image-archive --name "$CLUSTER" "$arg" >/dev/null
    printf '   loaded %s
' "$img"
    rm -f "$tar"
  done
  rm -rf "$dir"
}

if [[ "$CTX" == kind-* ]]; then
  CLUSTER=${CTX#kind-}
  if ! "$KIND" get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
    log "creating kind cluster $CLUSTER"
    "$KIND" create cluster --name "$CLUSTER" --config infrastructure/k8s/kind/kind-config.yaml --wait 180s
  fi
  log "loading images into kind"
  kind_load "coldguard-backend:$APP_VERSION" "coldguard-frontend:$APP_VERSION"
  # Third-party images are pulled once on the host (with retries) and side-loaded, so a slow or
  # flaky registry connection inside the kind node does not stall the rollout. PRELOAD_IMAGES=0 skips.
  if [ "${PRELOAD_IMAGES:-1}" = "1" ]; then
    EXTERNAL=(
      "registry.k8s.io/metrics-server/metrics-server:$METRICS_SERVER_VERSION"
      "registry.k8s.io/kube-state-metrics/kube-state-metrics:v2.14.0"
      postgres:16-alpine redis:7.4-alpine eclipse-mosquitto:2.0.20 prom/prometheus:v3.1.0 grafana/grafana:11.4.0
      quay.io/prometheuscommunity/postgres-exporter:v0.16.0 oliver006/redis_exporter:v1.66.0 busybox:1.36
    )
    if [ "$INGRESS_CONTROLLER" = nginx ]; then
      EXTERNAL+=("registry.k8s.io/ingress-nginx/controller:${INGRESS_NGINX_VERSION#controller-}"
                 "registry.k8s.io/ingress-nginx/kube-webhook-certgen:v1.5.0")
    else
      EXTERNAL+=(traefik:v3.3.4)
    fi
    for img in "${EXTERNAL[@]}"; do
      docker image inspect "$img" >/dev/null 2>&1 || retry 5 10 docker pull -q "$img" || fail "could not pull $img"
    done
    kind_load "${EXTERNAL[@]}"
  fi
fi

log "cluster add-ons: $INGRESS_CONTROLLER ingress, metrics-server"
if [ "$INGRESS_CONTROLLER" = traefik ]; then
  "${K[@]}" apply -f infrastructure/k8s/kind/traefik.yaml
  "${K[@]}" -n ingress-traefik rollout status deploy/traefik --timeout=300s
else
  if ! "${K[@]}" get ns ingress-nginx >/dev/null 2>&1; then
    "${K[@]}" apply -f "https://raw.githubusercontent.com/kubernetes/ingress-nginx/$INGRESS_NGINX_VERSION/deploy/static/provider/kind/deploy.yaml"
  fi
  if [[ "$CTX" == kind-* ]] && [ "${PRELOAD_IMAGES:-1}" = "1" ]; then
    # upstream pins images by digest; the side-loaded copies are matched by tag
    "${K[@]}" -n ingress-nginx set image deploy/ingress-nginx-controller       "controller=registry.k8s.io/ingress-nginx/controller:${INGRESS_NGINX_VERSION#controller-}" >/dev/null
    "${K[@]}" -n ingress-nginx patch deploy ingress-nginx-controller --type=json       -p '[{"op":"replace","path":"/spec/template/spec/containers/0/imagePullPolicy","value":"IfNotPresent"}]' >/dev/null
  fi
  "${K[@]}" -n ingress-nginx rollout status deploy/ingress-nginx-controller --timeout=300s
  "${K[@]}" -n ingress-nginx wait --for=condition=complete job --all --timeout=180s
fi
if ! "${K[@]}" -n kube-system get deploy metrics-server >/dev/null 2>&1; then
  "${K[@]}" apply -f "https://github.com/kubernetes-sigs/metrics-server/releases/download/$METRICS_SERVER_VERSION/components.yaml"
  # kind kubelets use self-signed serving certs
  "${K[@]}" -n kube-system patch deploy metrics-server --type=json \
    -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
fi
"${K[@]}" -n kube-system rollout status deploy/metrics-server --timeout=300s

if [ "$OVERLAY" = local ]; then bash scripts/k8s/gen-secrets.sh; fi

log "applying overlay $OVERLAY"
# Jobs are immutable: replace the migration job so a new image re-runs migrations
"${K[@]}" -n coldguard delete job coldguard-migrate --ignore-not-found >/dev/null 2>&1 || true
"${K[@]}" apply -k "infrastructure/k8s/overlays/$OVERLAY"
if [ "$INGRESS_CONTROLLER" != nginx ]; then
  "${K[@]}" -n coldguard patch ingress coldguard --type=merge -p "{\"spec\":{\"ingressClassName\":\"$INGRESS_CONTROLLER\"}}"
fi

log "waiting for data tier, migrations and rollouts"
"${K[@]}" -n coldguard rollout status statefulset/postgres --timeout=300s
for d in redis mosquitto; do "${K[@]}" -n coldguard rollout status "deploy/$d" --timeout=300s; done
"${K[@]}" -n coldguard wait --for=condition=complete job/coldguard-migrate --timeout=600s
for d in $("${K[@]}" -n coldguard get deploy -o name); do
  "${K[@]}" -n coldguard rollout status "$d" --timeout=420s
done
"${K[@]}" -n coldguard get pods,svc,pvc,hpa,ingress
ok "deployed overlay '$OVERLAY' to $CTX"
