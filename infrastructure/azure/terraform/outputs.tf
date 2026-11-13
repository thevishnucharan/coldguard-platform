# Consumed by scripts/ci/azure-deploy.sh to write infrastructure/k8s/overlays/azure/azure-params.env
# (no secret values are output — the pods read them from Key Vault).

output "resource_group" {
  value = azurerm_resource_group.main.name
}

output "aks_name" {
  value = azurerm_kubernetes_cluster.main.name
}

output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "key_vault_name" {
  value = azurerm_key_vault.main.name
}

output "tenant_id" {
  value = data.azurerm_client_config.current.tenant_id
}

output "workload_identity_client_id" {
  value = azurerm_user_assigned_identity.app.client_id
}

output "public_hostname" {
  value = var.public_hostname
}

output "devices_cidr" {
  value = var.devices_cidr
}

output "postgres_fqdn" {
  value = azurerm_postgresql_flexible_server.main.fqdn
}

output "log_analytics_workspace_id" {
  value = azurerm_log_analytics_workspace.main.id
}

output "monitor_workspace_query_endpoint" {
  value = azurerm_monitor_workspace.main.query_endpoint
}
