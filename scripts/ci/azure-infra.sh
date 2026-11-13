#!/usr/bin/env bash
# Phase (Azure): provision / update infrastructure with Terraform.
#   AZURE_ENV=production TF_ACTION=plan|apply scripts/ci/azure-infra.sh
# Auth: ARM_CLIENT_ID / ARM_CLIENT_SECRET (or ARM_USE_OIDC) / ARM_TENANT_ID / ARM_SUBSCRIPTION_ID
# from Jenkins credentials. Remote state: TF_BACKEND_* (see versions.tf). Variables come from
# infrastructure/azure/terraform/$AZURE_ENV.tfvars (git-ignored; copy terraform.tfvars.example).
# `apply` only ever applies the plan file produced in the same run.
source "$(dirname "$0")/lib.sh"
TF_DIR="$ROOT/infrastructure/azure/terraform"
ENV_NAME="${AZURE_ENV:-production}"
ACTION="${TF_ACTION:-plan}"
VARS="$TF_DIR/$ENV_NAME.tfvars"
command -v terraform >/dev/null || fail "terraform >= 1.6 is required"
[ -f "$VARS" ] || fail "missing $VARS (copy terraform.tfvars.example)"
: "${TF_BACKEND_RESOURCE_GROUP:?remote state resource group}"
: "${TF_BACKEND_STORAGE_ACCOUNT:?remote state storage account}"

cd "$TF_DIR"
log "terraform init ($ENV_NAME)"
terraform init -input=false -reconfigure \
  -backend-config="resource_group_name=$TF_BACKEND_RESOURCE_GROUP" \
  -backend-config="storage_account_name=$TF_BACKEND_STORAGE_ACCOUNT" \
  -backend-config="container_name=${TF_BACKEND_CONTAINER:-tfstate}" \
  -backend-config="key=coldguard-$ENV_NAME.tfstate"
terraform fmt -check -recursive
terraform validate
log "terraform plan"
terraform plan -input=false -var-file="$VARS" -out="$ENV_NAME.tfplan"
if [ "$ACTION" = apply ]; then
  log "terraform apply (plan from this run)"
  terraform apply -input=false "$ENV_NAME.tfplan"
fi
rm -f "$ENV_NAME.tfplan"
ok "terraform $ACTION complete ($ENV_NAME)"
