#!/usr/bin/env bash
# Phase (Azure): push images to ACR and deploy the AKS overlay.
#   AZURE_ENV=production scripts/ci/azure-deploy.sh [push|deploy|all]
# Requires: az CLI, kubectl, docker, terraform (to read outputs) — or the outputs as env vars:
#   RESOURCE_GROUP AKS_NAME ACR_LOGIN_SERVER KEY_VAULT_NAME TENANT_ID WORKLOAD_IDENTITY_CLIENT_ID
#   PUBLIC_HOSTNAME DEVICES_CIDR [TLS_CERT_KEYVAULT_URI]
# Auth: `az login --service-principal` with AZURE_CLIENT_ID/AZURE_CLIENT_SECRET/AZURE_TENANT_ID
# (Jenkins credentials) or an existing az session. No secret is read or written by this script:
# the pods fetch them from Key Vault through workload identity.
source "$(dirname "$0")/lib.sh"
cd "$ROOT"
what=${1:-all}
ENV_NAME="${AZURE_ENV:-production}"
command -v az >/dev/null || fail "Azure CLI (az) is required"

if [ -n "${AZURE_CLIENT_ID:-}" ] && [ -n "${AZURE_CLIENT_SECRET:-}" ]; then
  log "az login (service principal)"
  az login --service-principal -u "$AZURE_CLIENT_ID" -p "$AZURE_CLIENT_SECRET" --tenant "$AZURE_TENANT_ID" >/dev/null
fi
[ -n "${AZURE_SUBSCRIPTION_ID:-}" ] && az account set --subscription "$AZURE_SUBSCRIPTION_ID"

# ------------------------------------------------------------------ infrastructure outputs
tf_out() { terraform -chdir="$ROOT/infrastructure/azure/terraform" output -raw "$1"; }
if [ -z "${AKS_NAME:-}" ]; then
  log "reading terraform outputs"
  RESOURCE_GROUP=$(tf_out resource_group); AKS_NAME=$(tf_out aks_name); ACR_LOGIN_SERVER=$(tf_out acr_login_server)
  KEY_VAULT_NAME=$(tf_out key_vault_name); TENANT_ID=$(tf_out tenant_id)
  WORKLOAD_IDENTITY_CLIENT_ID=$(tf_out workload_identity_client_id); PUBLIC_HOSTNAME=$(tf_out public_hostname)
  DEVICES_CIDR=$(tf_out devices_cidr)
fi
TLS_CERT_KEYVAULT_URI="${TLS_CERT_KEYVAULT_URI:-https://$KEY_VAULT_NAME.vault.azure.net/certificates/coldguard-tls}"

# ------------------------------------------------------------------ images -> ACR
if [ "$what" = push ] || [ "$what" = all ]; then
  log "pushing images to $ACR_LOGIN_SERVER"
  az acr login --name "${ACR_LOGIN_SERVER%%.*}"
  # the Azure backend image includes the Application Insights exporter
  docker build -t "coldguard-backend:$IMAGE_TAG-azure" --build-arg INSTALL_AZURE_MONITOR=true ./backend
  docker tag "coldguard-backend:$IMAGE_TAG-azure" "$ACR_LOGIN_SERVER/coldguard-backend:$IMAGE_TAG"
  docker tag "coldguard-frontend:$IMAGE_TAG" "$ACR_LOGIN_SERVER/coldguard-frontend:$IMAGE_TAG"
  docker push "$ACR_LOGIN_SERVER/coldguard-backend:$IMAGE_TAG"
  docker push "$ACR_LOGIN_SERVER/coldguard-frontend:$IMAGE_TAG"
  ok "images pushed ($IMAGE_TAG)"
fi

# ------------------------------------------------------------------ AKS
if [ "$what" = deploy ] || [ "$what" = all ]; then
  log "AKS credentials ($AKS_NAME)"
  az aks get-credentials --resource-group "$RESOURCE_GROUP" --name "$AKS_NAME" --overwrite-existing
  command -v kubelogin >/dev/null && kubelogin convert-kubeconfig -l azurecli
  CTX="$AKS_NAME"
  ALLOW_REMOTE_CONTEXT=1 guard_kube_context "$CTX"   # explicit: this stage targets Azure on purpose
  K=(kubectl --context "$CTX")

  OV="$ROOT/infrastructure/k8s/overlays/azure"
  umask 077
  cat >"$OV/azure-params.env" <<EOF
AZURE_CLIENT_ID=$WORKLOAD_IDENTITY_CLIENT_ID
AZURE_TENANT_ID=$TENANT_ID
KEY_VAULT_NAME=$KEY_VAULT_NAME
PUBLIC_HOSTNAME=$PUBLIC_HOSTNAME
BACKEND_CORS_ORIGINS=https://$PUBLIC_HOSTNAME
TLS_CERT_KEYVAULT_URI=$TLS_CERT_KEYVAULT_URI
DEVICES_CIDR=$DEVICES_CIDR
EOF
  REL="$ROOT/build/k8s-azure"; rm -rf "$REL"; mkdir -p "$REL"
  cat >"$REL/kustomization.yaml" <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources: [../../infrastructure/k8s/overlays/azure]
images:
  - { name: coldguard-backend, newName: $ACR_LOGIN_SERVER/coldguard-backend, newTag: "$IMAGE_TAG" }
  - { name: coldguard-frontend, newName: $ACR_LOGIN_SERVER/coldguard-frontend, newTag: "$IMAGE_TAG" }
EOF
  log "Azure Monitor agent settings (kube-system)"
  "${K[@]}" apply -k "$ROOT/infrastructure/k8s/azure-monitor"
  log "applying ColdGuard (overlay azure, $IMAGE_TAG)"
  "${K[@]}" -n coldguard delete job coldguard-migrate --ignore-not-found
  "${K[@]}" apply -k "$REL"
  "${K[@]}" -n coldguard wait --for=condition=complete job/coldguard-migrate --timeout=900s
  for d in $("${K[@]}" -n coldguard get deploy -o name); do "${K[@]}" -n coldguard rollout status "$d" --timeout=600s; done
  "${K[@]}" -n coldguard get secret coldguard-secrets >/dev/null || fail "Key Vault secrets were not synced"
  "${K[@]}" -n coldguard get pods,svc,ingress,scaledobject
  rm -f "$OV/azure-params.env"
  ok "deployed $IMAGE_TAG to $AKS_NAME"
fi
