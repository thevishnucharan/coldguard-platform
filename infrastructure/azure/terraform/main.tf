# ColdGuard on Azure: AKS (workload identity, Key Vault CSI, Azure network policy, KEDA,
# app routing, Container Insights + managed Prometheus), ACR, Azure Database for PostgreSQL
# Flexible Server (private VNet access), Key Vault (RBAC) holding every application secret,
# one user-assigned identity for the pods with least-privilege role assignments.

data "azurerm_client_config" "current" {}

locals {
  name      = "${var.name_prefix}-${var.environment}"
  flat_name = "${var.name_prefix}${substr(var.environment, 0, 4)}" # for globally-unique, dash-free names
  namespace = "coldguard"
  app_sa    = "coldguard-app"
}

resource "random_string" "suffix" {
  length  = 5
  special = false
  upper   = false
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.name}"
  location = var.location
  tags     = var.tags
}

# ------------------------------------------------------------------ network
resource "azurerm_virtual_network" "main" {
  name                = "vnet-${local.name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  address_space       = [var.vnet_cidr]
  tags                = var.tags
}

resource "azurerm_subnet" "aks" {
  name                 = "snet-aks"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [var.aks_subnet_cidr]
}

resource "azurerm_subnet" "postgres" {
  name                 = "snet-postgres"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [var.postgres_subnet_cidr]
  service_endpoints    = ["Microsoft.Storage"]
  delegation {
    name = "postgres"
    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_private_dns_zone" "postgres" {
  name                = "${local.name}.private.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.main.name
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "postgres" {
  name                  = "postgres-vnet"
  private_dns_zone_name = azurerm_private_dns_zone.postgres.name
  resource_group_name   = azurerm_resource_group.main.name
  virtual_network_id    = azurerm_virtual_network.main.id
}

# ------------------------------------------------------------------ observability
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = var.tags
}

resource "azurerm_application_insights" "main" {
  name                = "appi-${local.name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
  tags                = var.tags
}

# Azure Monitor managed Prometheus (scrapes the same prometheus.io pod annotations)
resource "azurerm_monitor_workspace" "main" {
  name                = "amw-${local.name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = var.tags
}

resource "azurerm_monitor_data_collection_endpoint" "prometheus" {
  name                = "dce-prom-${local.name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  kind                = "Linux"
  tags                = var.tags
}

resource "azurerm_monitor_data_collection_rule" "prometheus" {
  name                        = "dcr-prom-${local.name}"
  location                    = azurerm_resource_group.main.location
  resource_group_name         = azurerm_resource_group.main.name
  data_collection_endpoint_id = azurerm_monitor_data_collection_endpoint.prometheus.id
  kind                        = "Linux"
  destinations {
    monitor_account {
      monitor_account_id = azurerm_monitor_workspace.main.id
      name               = "MonitoringAccount1"
    }
  }
  data_flow {
    streams      = ["Microsoft-PrometheusMetrics"]
    destinations = ["MonitoringAccount1"]
  }
  data_sources {
    prometheus_forwarder {
      streams = ["Microsoft-PrometheusMetrics"]
      name    = "PrometheusDataSource"
    }
  }
  tags = var.tags
}

resource "azurerm_monitor_data_collection_rule_association" "prometheus" {
  name                    = "dcra-prom-${local.name}"
  target_resource_id      = azurerm_kubernetes_cluster.main.id
  data_collection_rule_id = azurerm_monitor_data_collection_rule.prometheus.id
}

# ------------------------------------------------------------------ registry
resource "azurerm_container_registry" "main" {
  name                          = "acr${local.flat_name}${random_string.suffix.result}"
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  sku                           = "Standard"
  admin_enabled                 = false # pull via managed identity only
  public_network_access_enabled = true  # CI pushes from Jenkins; lock down with Premium + private endpoint if required
  tags                          = var.tags
}

# ------------------------------------------------------------------ AKS
resource "azurerm_kubernetes_cluster" "main" {
  name                      = "aks-${local.name}"
  location                  = azurerm_resource_group.main.location
  resource_group_name       = azurerm_resource_group.main.name
  dns_prefix                = local.name
  kubernetes_version        = var.kubernetes_version
  sku_tier                  = var.environment == "production" ? "Standard" : "Free"
  oidc_issuer_enabled       = true # workload identity federation
  workload_identity_enabled = true
  azure_policy_enabled      = true
  local_account_disabled    = length(var.admin_group_object_ids) > 0
  automatic_upgrade_channel = "patch"

  default_node_pool {
    name                         = "system"
    vm_size                      = var.node_vm_size
    node_count                   = var.system_node_count
    vnet_subnet_id               = azurerm_subnet.aks.id
    only_critical_addons_enabled = true
    zones                        = ["1", "2", "3"]
    upgrade_settings { max_surge = "33%" }
  }

  identity { type = "SystemAssigned" }

  dynamic "azure_active_directory_role_based_access_control" {
    for_each = length(var.admin_group_object_ids) > 0 ? [1] : []
    content {
      azure_rbac_enabled     = true
      admin_group_object_ids = var.admin_group_object_ids
    }
  }

  network_profile {
    network_plugin    = "azure"
    network_policy    = "azure" # enforces the ColdGuard NetworkPolicies
    load_balancer_sku = "standard"
    service_cidr      = "10.41.0.0/16"
    dns_service_ip    = "10.41.0.10"
  }

  key_vault_secrets_provider {
    secret_rotation_enabled  = true
    secret_rotation_interval = "2m"
  }

  oms_agent { # Container Insights (stdout JSON logs, node/pod health)
    log_analytics_workspace_id      = azurerm_log_analytics_workspace.main.id
    msi_auth_for_monitoring_enabled = true
  }

  monitor_metrics {} # managed Prometheus (ama-metrics)

  workload_autoscaler_profile {
    keda_enabled = true # backend scaled on CPU, memory and API request rate
  }

  web_app_routing {
    dns_zone_ids = []
  }

  tags = var.tags
}

resource "azurerm_kubernetes_cluster_node_pool" "apps" {
  name                  = "apps"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main.id
  vm_size               = var.node_vm_size
  vnet_subnet_id        = azurerm_subnet.aks.id
  auto_scaling_enabled  = true
  min_count             = var.user_node_min
  max_count             = var.user_node_max
  zones                 = ["1", "2", "3"]
  mode                  = "User"
  upgrade_settings { max_surge = "33%" }
  tags = var.tags
}

# kubelet pulls images from ACR — nothing else gets registry rights
resource "azurerm_role_assignment" "aks_acr_pull" {
  scope                            = azurerm_container_registry.main.id
  role_definition_name             = "AcrPull"
  principal_id                     = azurerm_kubernetes_cluster.main.kubelet_identity[0].object_id
  skip_service_principal_aad_check = true
}

# AKS needs to join the subnet for internal load balancers (MQTT)
resource "azurerm_role_assignment" "aks_network" {
  scope                = azurerm_subnet.aks.id
  role_definition_name = "Network Contributor"
  principal_id         = azurerm_kubernetes_cluster.main.identity[0].principal_id
}

# ------------------------------------------------------------------ workload identity (pods)
resource "azurerm_user_assigned_identity" "app" {
  name                = "id-${local.name}-app"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = var.tags
}

resource "azurerm_federated_identity_credential" "app" {
  name                = "coldguard-app-sa"
  resource_group_name = azurerm_resource_group.main.name
  parent_id           = azurerm_user_assigned_identity.app.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = azurerm_kubernetes_cluster.main.oidc_issuer_url
  subject             = "system:serviceaccount:${local.namespace}:${local.app_sa}"
}

# ------------------------------------------------------------------ Key Vault (RBAC)
resource "azurerm_key_vault" "main" {
  name                          = "kv-${local.flat_name}-${random_string.suffix.result}"
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  rbac_authorization_enabled    = true
  purge_protection_enabled      = var.environment == "production"
  soft_delete_retention_days    = 30
  public_network_access_enabled = true # CSI driver + Terraform; restrict with private endpoint/firewall if required
  tags                          = var.tags
}

# least privilege: the pods may READ secrets of this vault only
resource "azurerm_role_assignment" "app_kv_reader" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# whoever runs Terraform writes the generated secrets
resource "azurerm_role_assignment" "deployer_kv_officer" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "admins_kv_officer" {
  for_each             = toset(var.admin_group_object_ids)
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = each.value
}

# ------------------------------------------------------------------ PostgreSQL Flexible Server
resource "random_password" "postgres" {
  length  = 32
  special = false
}

resource "azurerm_postgresql_flexible_server" "main" {
  name                          = "psql-${local.name}-${random_string.suffix.result}"
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  version                       = "16"
  sku_name                      = var.postgres_sku
  storage_mb                    = var.postgres_storage_mb
  backup_retention_days         = var.environment == "production" ? 35 : 7
  geo_redundant_backup_enabled  = var.environment == "production"
  delegated_subnet_id           = azurerm_subnet.postgres.id
  private_dns_zone_id           = azurerm_private_dns_zone.postgres.id
  public_network_access_enabled = false
  administrator_login           = "coldguardadmin"
  administrator_password        = random_password.postgres.result
  zone                          = "1"

  dynamic "high_availability" {
    for_each = var.postgres_high_availability ? [1] : []
    content {
      mode                      = "ZoneRedundant"
      standby_availability_zone = "2"
    }
  }

  lifecycle {
    ignore_changes = [zone, high_availability[0].standby_availability_zone]
  }
  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgres]
  tags       = var.tags
}

resource "azurerm_postgresql_flexible_server_database" "coldguard" {
  name      = "coldguard"
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_postgresql_flexible_server_configuration" "require_tls" {
  name      = "require_secure_transport"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "on"
}

# ------------------------------------------------------------------ application secrets -> Key Vault
resource "random_password" "secret_key" {
  length  = 64
  special = false
}

resource "random_password" "ingest_key" {
  length  = 40
  special = false
}

resource "random_password" "mqtt_ingestor" {
  length  = 32
  special = false
}

resource "random_password" "mqtt_device" {
  length  = 32
  special = false
}

resource "random_password" "grafana" {
  length  = 24
  special = false
}

locals {
  pg_host = azurerm_postgresql_flexible_server.main.fqdn
  pg_user = azurerm_postgresql_flexible_server.main.administrator_login
  pg_pass = random_password.postgres.result
  # Key Vault secret names cannot contain "_": the SecretProviderClass maps them back to env names.
  app_secrets = {
    "database-url"                          = "postgresql://${local.pg_user}:${local.pg_pass}@${local.pg_host}:5432/coldguard?sslmode=require"
    "exporter-dsn"                          = "postgresql://${local.pg_user}:${local.pg_pass}@${local.pg_host}:5432/coldguard?sslmode=require"
    "postgres-user"                         = local.pg_user
    "postgres-password"                     = local.pg_pass
    "secret-key"                            = random_password.secret_key.result
    "ingest-api-key"                        = random_password.ingest_key.result
    "mqtt-password"                         = random_password.mqtt_ingestor.result
    "mqtt-ingestor-password"                = random_password.mqtt_ingestor.result
    "mqtt-device-password"                  = random_password.mqtt_device.result
    "grafana-admin-password"                = random_password.grafana.result
    "applicationinsights-connection-string" = azurerm_application_insights.main.connection_string
  }
}

resource "azurerm_key_vault_secret" "app" {
  for_each     = local.app_secrets
  name         = each.key
  value        = each.value
  key_vault_id = azurerm_key_vault.main.id
  content_type = "coldguard"
  depends_on   = [azurerm_role_assignment.deployer_kv_officer]
}
