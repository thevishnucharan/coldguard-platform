variable "subscription_id" {
  type        = string
  description = "Azure subscription to deploy into."
}

variable "environment" {
  type        = string
  description = "staging | production"
  default     = "production"
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production."
  }
}

variable "location" {
  type    = string
  default = "centralindia"
}

variable "name_prefix" {
  type        = string
  description = "Short lowercase prefix for resource names (letters/digits, max 10)."
  default     = "coldguard"
  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,9}$", var.name_prefix))
    error_message = "name_prefix must be 3-10 lowercase letters/digits."
  }
}

variable "public_hostname" {
  type        = string
  description = "Public DNS name of the UI (used for CORS and the ingress), e.g. coldguard.example.org"
}

variable "vnet_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "aks_subnet_cidr" {
  type    = string
  default = "10.40.0.0/20"
}

variable "postgres_subnet_cidr" {
  type    = string
  default = "10.40.16.0/24"
}

variable "devices_cidr" {
  type        = string
  description = "Address range MQTT devices/gateways connect from (VPN / ExpressRoute). Used by the internal load balancer and NetworkPolicy."
  default     = "10.40.0.0/16"
}

variable "kubernetes_version" {
  type    = string
  default = null # latest supported by AKS
}

variable "system_node_count" {
  type    = number
  default = 2
}

variable "user_node_min" {
  type    = number
  default = 2
}

variable "user_node_max" {
  type    = number
  default = 6
}

variable "node_vm_size" {
  type    = string
  default = "Standard_D4s_v5"
}

variable "postgres_sku" {
  type    = string
  default = "GP_Standard_D2ds_v5"
}

variable "postgres_storage_mb" {
  type    = number
  default = 65536
}

variable "postgres_high_availability" {
  type        = bool
  description = "Zone-redundant standby (recommended for production)."
  default     = true
}

variable "admin_group_object_ids" {
  type        = list(string)
  description = "Entra ID groups that administer the cluster and Key Vault."
  default     = []
}

variable "tags" {
  type    = map(string)
  default = { application = "coldguard", managed_by = "terraform" }
}
