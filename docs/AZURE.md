# ColdGuard on Azure (AKS)

The Azure deployment reuses the Kubernetes base unchanged: probes, PDBs, HPAs, NetworkPolicies,
the restricted Pod Security Standard and preStop drains. It adds Azure-native pieces around it:

```
infrastructure/azure/terraform/          AKS, ACR, PostgreSQL Flexible Server, Key Vault, identities,
                                         Log Analytics, Application Insights, managed Prometheus
infrastructure/k8s/overlays/azure/       Kubernetes overlay (see table below)
infrastructure/k8s/azure-monitor/        Azure Monitor agent settings (kube-system)
scripts/ci/azure-infra.sh                terraform init / validate / plan / apply
scripts/ci/azure-deploy.sh               ACR push + AKS deploy
```

| Recommendation | Implementation |
|---|---|
| **Kubernetes: `overlays/azure`** | Based on `../../base`. ACR images pinned per build, `managed-csi` disks for every PVC, AKS application-routing ingress (managed NGINX) with a Key Vault TLS certificate and forced HTTPS, production config, migration Job without demo seed |
| **Database: managed PostgreSQL** | Terraform: Azure Database for PostgreSQL Flexible Server 16, private VNet access only (delegated subnet + private DNS), TLS required, zone-redundant HA, 35-day backups with geo-redundancy in production. The overlay deletes the in-cluster StatefulSet/Service; `postgres-exporter` monitors the managed server |
| **Secrets: Azure Key Vault** | Terraform generates every secret (DB, JWT key, ingest key, MQTT, Grafana, App Insights) into a Key Vault using RBAC authorisation and purge protection. The Secrets Store CSI driver (AKS add-on, 2-minute rotation) syncs them into `coldguard-secrets`. No secret in Git, YAML, images or the pipeline |
| **MQTT: persistent storage and internal broker access** | Broker data on an Azure disk PVC. Devices connect through an **internal** load balancer (`mosquitto-devices`, `loadBalancerSourceRanges` = device network). The "from anywhere" NetworkPolicy is replaced by one allowing only the app tier and the device CIDR. In-cluster clients use the ClusterIP service |
| **CI/CD: Azure stages in Jenkins** | `Azure: Terraform` (plan, or approval-gated apply of the plan from the same run) and `Azure: Deploy to AKS` (approval → backend image with the App Insights exporter, ACR push, deploy, wait for migration and rollouts, verify the Key Vault sync) |
| **Scaling: CPU/memory HPA + custom metrics** | Base HPAs now use CPU **and** memory (scale-up damped). On AKS a KEDA `ScaledObject` scales the API on CPU, memory **and request rate** (`coldguard_http_requests_total` from the in-cluster Prometheus, 40 req/s per replica). Nodes autoscale 2–6 in the `apps` pool across 3 zones |
| **Security: workload identity, least privilege** | One user-assigned managed identity, federated with the `coldguard/coldguard-app` service account, holding only **Key Vault Secrets User** on this vault. Only the six workloads that read secrets use it (API, worker, migrate, mosquitto, grafana, postgres-exporter); frontend, Redis and the exporters get no identity. The kubelet holds only **AcrPull** (ACR admin user disabled). Azure network policy enforces the NetworkPolicies, Azure Policy is enabled, local accounts are disabled when Entra admin groups are configured, and the private DB has no public endpoint |
| **Monitoring: Azure Monitor alongside Prometheus/Grafana** | Container Insights (structured stdout logs to Log Analytics; environment variables are **not** collected). Managed Prometheus scrapes the same annotated pods as the in-cluster Prometheus, so Grafana and Azure Monitor see the same series. The backend sends requests, dependencies, exceptions and logs to Application Insights via OpenTelemetry (image built with `INSTALL_AZURE_MONITOR=true`, 25 % sampling, secrets masked). In-cluster Prometheus, Grafana and the alert rules stay unchanged |

Extra NetworkPolicies on AKS allow only `ama-metrics` (managed Prometheus) to scrape the metrics
ports, and only the KEDA operator to query Prometheus. The base default-deny stays in force.

## First deployment

Prerequisites:
* Terraform ≥ 1.6, Azure CLI, kubectl and kubelogin;
* a storage account for Terraform state;
* a service principal with Owner (or Contributor plus User Access Administrator) on the
  subscription, because Terraform creates role assignments.

```bash
cd infrastructure/azure/terraform
cp terraform.tfvars.example production.tfvars        # subscription, hostname, admin group, device CIDR
export ARM_CLIENT_ID=… ARM_CLIENT_SECRET=… ARM_TENANT_ID=… ARM_SUBSCRIPTION_ID=…
export TF_BACKEND_RESOURCE_GROUP=tfstate TF_BACKEND_STORAGE_ACCOUNT=…
AZURE_ENV=production TF_ACTION=apply bash ../../../scripts/ci/azure-infra.sh

# TLS: import the certificate for PUBLIC_HOSTNAME into the vault as "coldguard-tls"
az keyvault certificate import --vault-name <kv> -n coldguard-tls -f coldguard.pfx
az aks approuting update -g <rg> -n <aks> --enable-kv --attach-kv <kv-resource-id>

bash scripts/ci/build-images.sh
AZURE_ENV=production bash scripts/ci/azure-deploy.sh all   # ACR push + deploy + verification
```

Then point the DNS name at the app-routing ingress IP. The first administrator account is created
with `BOOTSTRAP_ADMIN_PASSWORD=… python scripts/seed.py --bootstrap-admin you@org`, run as a
one-off Job.

## What was validated here, and what was not

* **Validated locally:**
  * `terraform validate` and `fmt` pass (azurerm 4.x provider);
  * the Azure overlay renders 55 resources with every placeholder replaced and no in-cluster
    database or literal Secret;
  * kubeconform reports all 162 rendered objects (four renders) schema-valid, including the
    KEDA `ScaledObject` and `SecretProviderClass`;
  * the backend image builds with the Application Insights exporter;
  * the App Insights hook is unit-tested: off by default, degrades without the package, masks
    log messages.
* **Not validated:** an actual Azure deployment. No subscription or credentials were used. Run
  `azure-infra.sh` with `TF_ACTION=plan` first, and review quotas and SKU availability in your
  region (`Standard_D4s_v5`, `GP_Standard_D2ds_v5`, zone redundancy).

## Cost and size notes

The defaults are production-shaped: Standard AKS tier, 2 system + 2–6 app nodes across 3 zones,
and zone-redundant PostgreSQL. For staging, set `environment = "staging"` (Free tier, 7-day
backups, no geo-backup), `postgres_high_availability = false` and smaller node counts in the
tfvars.
