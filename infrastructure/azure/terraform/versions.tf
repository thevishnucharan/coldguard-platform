terraform {
  required_version = ">= 1.6"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.14" }
    random  = { source = "hashicorp/random", version = "~> 3.6" }
  }
  # Remote state (recommended): configure with -backend-config in CI, e.g.
  #   terraform init -backend-config="resource_group_name=tfstate" -backend-config="storage_account_name=..." \
  #                  -backend-config="container_name=tfstate" -backend-config="key=coldguard-<env>.tfstate"
  backend "azurerm" {}
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = false # never hard-delete secrets by accident
    }
  }
  subscription_id = var.subscription_id
}
