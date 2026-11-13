# ColdGuard Azure Deployment Guide

This guide describes how to deploy the ColdGuard application to Azure using the provided Kubernetes manifests.

## Prerequisites

- Azure CLI installed and authenticated (`az login`)
- `kubectl` installed
- Provisioned Azure infrastructure:
  - Azure Kubernetes Service (AKS)
  - Azure Container Registry (ACR)
  - Azure Database for PostgreSQL
  - Azure Event Hubs
  - Azure Blob Storage
  - Azure OpenAI Service
  - Azure Key Vault
  - Application Insights

## 1. Prepare Configuration and Secrets

Before deploying to AKS, you must populate the secrets template with the actual values from your Azure resources.

1. Copy the secrets template:
   ```bash
   cp infrastructure/kubernetes/secrets-template.yaml infrastructure/kubernetes/secrets.yaml
   ```

2. Edit `infrastructure/kubernetes/secrets.yaml` and replace all placeholders (`<...>`) with your real Azure credentials.

*(Note: In a production environment, you should use Azure Key Vault integration with the Secrets Store CSI Driver or a GitOps tool like ArgoCD with Sealed Secrets, rather than manually applying secrets via YAML.)*

## 2. Deploy to Azure Kubernetes Service (AKS)

Connect your `kubectl` to your AKS cluster:

```bash
az aks get-credentials --resource-group <RESOURCE_GROUP_NAME> --name <AKS_CLUSTER_NAME>
```

Apply the Kubernetes manifests in the following order:

```bash
# 1. Create the namespace
kubectl apply -f infrastructure/kubernetes/namespace.yaml

# 2. Apply ConfigMap and Secrets
kubectl apply -f infrastructure/kubernetes/configmap.yaml
kubectl apply -f infrastructure/kubernetes/secrets.yaml

# 3. Deploy the Backend
kubectl apply -f infrastructure/kubernetes/backend-deployment.yaml
kubectl apply -f infrastructure/kubernetes/backend-service.yaml

# 4. Deploy the Frontend
kubectl apply -f infrastructure/kubernetes/frontend-deployment.yaml
kubectl apply -f infrastructure/kubernetes/frontend-service.yaml

# 5. Configure Ingress (Ensure an Ingress Controller is installed on AKS)
kubectl apply -f infrastructure/kubernetes/ingress.yaml
```

## 3. Environment Specific Configuration

To apply environment specific variables (Staging vs Production), you should update the `infrastructure/kubernetes/configmap.yaml` values to match the variables defined in:

- `infrastructure/azure/staging.env`
- `infrastructure/azure/production.env`

## 4. Database Migrations and Seeding

The database migrations are configured to run automatically when the backend container starts (via `docker-entrypoint.sh`). Ensure your Azure PostgreSQL firewall rules allow connections from your AKS cluster.

## 5. Verify Deployment

Check the status of your pods and services:

```bash
kubectl get pods -n coldguard
kubectl get svc -n coldguard
kubectl get ingress -n coldguard
```

Once the Ingress acquires an external IP, you can access the ColdGuard application via the configured hostname.
