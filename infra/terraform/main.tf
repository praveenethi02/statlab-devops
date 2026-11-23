terraform {
  required_version = ">= 1.6, < 2.0"
  backend "azurerm" {}
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}
}

variable "prefix" {
  type        = string
  description = "Globally unique lowercase resource prefix, 3 to 16 characters."
  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,15}$", var.prefix))
    error_message = "Use 3 to 16 lowercase letters and digits, starting with a letter."
  }
}

variable "location" { type = string }
variable "registry_name" { type = string }
variable "registry_resource_group" { type = string }
variable "image_tag" { type = string }
variable "database_password" {
  type      = string
  sensitive = true
}
variable "app_secret" {
  type      = string
  sensitive = true
}

data "azurerm_container_registry" "images" {
  name                = var.registry_name
  resource_group_name = var.registry_resource_group
}

resource "azurerm_resource_group" "app" {
  name     = "${var.prefix}-rg"
  location = var.location
}

resource "azurerm_virtual_network" "app" {
  name                = "${var.prefix}-vnet"
  resource_group_name = azurerm_resource_group.app.name
  location            = var.location
  address_space       = ["10.56.0.0/16"]
}

resource "azurerm_subnet" "apps" {
  name                 = "apps"
  resource_group_name  = azurerm_resource_group.app.name
  virtual_network_name = azurerm_virtual_network.app.name
  address_prefixes     = ["10.56.0.0/23"]
  delegation {
    name = "container-apps"
    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "database" {
  name                 = "database"
  resource_group_name  = azurerm_resource_group.app.name
  virtual_network_name = azurerm_virtual_network.app.name
  address_prefixes     = ["10.56.2.0/27"]
  delegation {
    name = "postgres"
    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_private_dns_zone" "database" {
  name                = "${var.prefix}.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.app.name
}

resource "azurerm_private_dns_zone_virtual_network_link" "database" {
  name                  = "statlab"
  resource_group_name   = azurerm_resource_group.app.name
  private_dns_zone_name = azurerm_private_dns_zone.database.name
  virtual_network_id    = azurerm_virtual_network.app.id
}

resource "azurerm_postgresql_flexible_server" "database" {
  name                          = "${var.prefix}-pg"
  location                      = var.location
  resource_group_name           = azurerm_resource_group.app.name
  version                       = "16"
  sku_name                      = "B_Standard_B1ms"
  storage_mb                    = 32768
  backup_retention_days         = 7
  administrator_login           = "statlabowner"
  administrator_password        = var.database_password
  delegated_subnet_id           = azurerm_subnet.database.id
  private_dns_zone_id           = azurerm_private_dns_zone.database.id
  public_network_access_enabled = false
  depends_on                    = [azurerm_private_dns_zone_virtual_network_link.database]
  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_postgresql_flexible_server_database" "statlab" {
  name      = "statlab"
  server_id = azurerm_postgresql_flexible_server.database.id
  collation = "en_US.utf8"
  charset   = "UTF8"
  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_container_app_environment" "app" {
  name                     = "${var.prefix}-env"
  location                 = var.location
  resource_group_name      = azurerm_resource_group.app.name
  infrastructure_subnet_id = azurerm_subnet.apps.id
  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }
}

resource "azurerm_user_assigned_identity" "pull" {
  name                = "${var.prefix}-image-pull"
  location            = var.location
  resource_group_name = azurerm_resource_group.app.name
}

resource "azurerm_role_assignment" "pull" {
  scope                            = data.azurerm_container_registry.images.id
  role_definition_name             = "AcrPull"
  principal_id                     = azurerm_user_assigned_identity.pull.principal_id
  skip_service_principal_aad_check = true
}

locals {
  domain   = azurerm_container_app_environment.app.default_domain
  frontend = "frontend.${local.domain}"
  backend  = "backend.internal.${local.domain}"
  backend_vars = {
    DATABASE_URL  = "postgresql:///${azurerm_postgresql_flexible_server_database.statlab.name}"
    PGHOST        = azurerm_postgresql_flexible_server.database.fqdn
    PGUSER        = azurerm_postgresql_flexible_server.database.administrator_login
    PGSSLMODE     = "verify-full"
    PGSSLROOTCERT = "/etc/ssl/certs/ca-certificates.crt"
    ALLOWED_HOSTS = "${local.backend},localhost,127.0.0.1"
    PUBLIC_ORIGIN = "https://${local.frontend}"
    COOKIE_SECURE = "true"
  }
}

resource "azurerm_container_app" "tier" {
  for_each                     = toset(["frontend", "backend"])
  name                         = each.key
  resource_group_name          = azurerm_resource_group.app.name
  container_app_environment_id = azurerm_container_app_environment.app.id
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  depends_on                   = [azurerm_role_assignment.pull]

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.pull.id]
  }
  registry {
    server   = data.azurerm_container_registry.images.login_server
    identity = azurerm_user_assigned_identity.pull.id
  }
  dynamic "secret" {
    for_each = each.key == "backend" ? toset(["database-password", "app-secret"]) : toset([])
    content {
      name  = secret.key
      value = secret.key == "database-password" ? var.database_password : var.app_secret
    }
  }
  ingress {
    external_enabled = each.key == "frontend"
    target_port      = each.key == "frontend" ? 80 : 8000
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
  template {
    min_replicas = 1
    max_replicas = 2
    container {
      name   = each.key
      image  = "${data.azurerm_container_registry.images.login_server}/statlab-${each.key}:${var.image_tag}"
      cpu    = 0.5
      memory = "1Gi"

      dynamic "env" {
        for_each = each.key == "backend" ? local.backend_vars : tomap({
          BACKEND_URL         = "https://${local.backend}"
          BACKEND_HOST_HEADER = local.backend
        })
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = each.key == "backend" ? { PGPASSWORD = "database-password", APP_SECRET = "app-secret" } : {}
        content {
          name        = env.key
          secret_name = env.value
        }
      }
      readiness_probe {
        transport = "HTTP"
        port      = each.key == "frontend" ? 80 : 8000
        path      = each.key == "frontend" ? "/" : "/api/health"
        header {
          name  = "Host"
          value = "localhost"
        }
      }
    }
  }
  lifecycle {
    # Terraform bootstraps the app. Ansible owns subsequent image revisions.
    ignore_changes = [template[0].container[0].image]
  }
}

output "resource_group" { value = azurerm_resource_group.app.name }
output "frontend_url" { value = "https://${local.frontend}" }
