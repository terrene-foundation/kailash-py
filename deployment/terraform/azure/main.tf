# Azure - Enterprise AKS Infrastructure
# Production-ready Kubernetes deployment with complete security and monitoring

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.85"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 2.46"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.11"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }

  backend "azurerm" {
    # Configuration provided via backend config file or CLI flags
    # resource_group_name  = "terraform-state-rg"
    # storage_account_name = "tfstatekailash"
    # container_name       = "tfstate"
    # key                  = "kailash.terraform.tfstate"
  }
}

# Configure Azure Provider
provider "azurerm" {
  features {
    resource_group {
      prevent_deletion_if_contains_resources = true
    }
    key_vault {
      purge_soft_delete_on_destroy = false
      recover_soft_deleted_key_vaults = true
    }
  }
}

# Data sources
data "azurerm_client_config" "current" {}
data "azuread_client_config" "current" {}

# Local variables
locals {
  resource_group_name = "${var.project_name}-${var.environment}-rg"
  cluster_name        = "${var.project_name}-${var.environment}-aks"
  location            = var.location
  
  common_tags = merge(var.tags, {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
    team        = var.team_name
  })
}

# Resource Group
resource "azurerm_resource_group" "main" {
  name     = local.resource_group_name
  location = local.location
  tags     = local.common_tags
}

# Virtual Network
module "vnet" {
  source = "./modules/vnet"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  vnet_name           = "${local.cluster_name}-vnet"
  
  # Address spaces
  address_space = [var.vnet_cidr]
  
  # Subnets
  subnets = {
    aks-nodes = {
      address_prefixes = [var.aks_subnet_cidr]
      service_endpoints = [
        "Microsoft.Storage",
        "Microsoft.Sql",
        "Microsoft.KeyVault",
        "Microsoft.ContainerRegistry"
      ]
      delegation = null
    }
    aks-internal-lb = {
      address_prefixes = [var.internal_lb_subnet_cidr]
      service_endpoints = []
      delegation = null
    }
    application-gateway = {
      address_prefixes = [var.appgw_subnet_cidr]
      service_endpoints = []
      delegation = null
    }
    postgresql = {
      address_prefixes = [var.postgresql_subnet_cidr]
      service_endpoints = ["Microsoft.Storage"]
      delegation = {
        name = "postgresql-delegation"
        service_delegation = {
          name = "Microsoft.DBforPostgreSQL/flexibleServers"
          actions = [
            "Microsoft.Network/virtualNetworks/subnets/join/action",
          ]
        }
      }
    }
  }
  
  # Network Security Groups
  enable_network_security_groups = true
  
  # DDoS Protection
  enable_ddos_protection = var.enable_ddos_protection
  
  tags = local.common_tags
}

# AKS Cluster
module "aks" {
  source = "./modules/aks"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  cluster_name        = local.cluster_name
  
  # Kubernetes version
  kubernetes_version = var.kubernetes_version
  
  # Network configuration
  vnet_subnet_id = module.vnet.subnet_ids["aks-nodes"]
  network_plugin = "azure"
  network_policy = "calico"
  
  # Service CIDR (internal Kubernetes services)
  service_cidr   = var.service_cidr
  dns_service_ip = var.dns_service_ip
  
  # Default node pool
  default_node_pool = {
    name                = "system"
    vm_size            = var.system_node_pool_vm_size
    node_count         = var.system_node_pool_count
    min_count          = var.system_node_pool_min_count
    max_count          = var.system_node_pool_max_count
    enable_auto_scaling = true
    availability_zones  = var.availability_zones
    node_labels = {
      "nodepool" = "system"
      "workload" = "system"
    }
    node_taints = ["CriticalAddonsOnly=true:NoSchedule"]
  }
  
  # Additional node pools
  node_pools = var.node_pools
  
  # Identity and RBAC
  identity_type = "SystemAssigned"
  rbac_enabled  = true
  
  # Azure AD integration
  azure_ad_enabled = var.azure_ad_enabled
  admin_group_ids  = var.admin_group_ids
  
  # Add-ons
  enable_http_application_routing = false
  enable_azure_policy            = true
  enable_oms_agent               = true
  log_analytics_workspace_id     = azurerm_log_analytics_workspace.main.id
  
  # Security
  enable_host_encryption = true
  private_cluster_enabled = var.private_cluster_enabled
  authorized_ip_ranges    = var.authorized_ip_ranges
  
  # Maintenance window
  maintenance_window = var.maintenance_window
  
  # Auto-scaler profile
  auto_scaler_profile = {
    balance_similar_node_groups      = true
    expander                        = "random"
    max_graceful_termination_sec    = 600
    max_node_provisioning_time      = "15m"
    max_unready_nodes               = 3
    max_unready_percentage          = 45
    new_pod_scale_up_delay          = "0s"
    scale_down_delay_after_add      = "10m"
    scale_down_delay_after_delete   = "10s"
    scale_down_delay_after_failure  = "3m"
    scan_interval                   = "10s"
    scale_down_unneeded             = "10m"
    scale_down_unready              = "20m"
    scale_down_utilization_threshold = 0.5
  }
  
  tags = local.common_tags
  
  depends_on = [module.vnet]
}

# Log Analytics Workspace
resource "azurerm_log_analytics_workspace" "main" {
  name                = "${local.cluster_name}-logs"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = var.log_retention_days
  
  tags = local.common_tags
}

# Azure Database for PostgreSQL
module "postgresql" {
  source = "./modules/postgresql"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  server_name         = "${local.cluster_name}-postgresql"
  
  # PostgreSQL configuration
  postgresql_version = var.postgresql_version
  sku_name          = var.postgresql_sku_name
  storage_mb        = var.postgresql_storage_mb
  
  # High availability
  zone_redundant = var.postgresql_zone_redundant
  
  # Backup configuration
  backup_retention_days        = var.postgresql_backup_retention_days
  geo_redundant_backup_enabled = var.postgresql_geo_redundant_backup
  
  # Network configuration
  delegated_subnet_id = module.vnet.subnet_ids["postgresql"]
  private_dns_zone_id = azurerm_private_dns_zone.postgresql.id
  
  # Databases and users
  databases = var.postgresql_databases
  
  # Server parameters
  postgresql_configurations = var.postgresql_configurations
  
  # Security
  ssl_enforcement_enabled       = true
  ssl_minimal_tls_version      = "TLS1_2"
  
  tags = local.common_tags
  
  depends_on = [module.vnet]
}

# Azure Cache for Redis
module "redis" {
  source = "./modules/redis"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  redis_name          = "${local.cluster_name}-redis"
  
  # Redis configuration
  capacity       = var.redis_capacity
  family         = var.redis_family
  sku_name       = var.redis_sku_name
  
  # Network configuration
  subnet_id = module.vnet.subnet_ids["aks-nodes"]
  
  # Redis configuration
  enable_non_ssl_port = false
  minimum_tls_version = "1.2"
  
  redis_configuration = merge(
    {
      maxmemory_policy       = "allkeys-lru"
      notify_keyspace_events = ""
      maxfragmentationmemory_reserved = 50
      maxmemory_reserved     = 50
      maxmemory_delta        = 50
    },
    var.redis_configuration
  )
  
  # Zones for redundancy
  zones = var.redis_sku_name == "Premium" ? var.availability_zones : []
  
  # Patch schedule
  patch_schedule = var.redis_patch_schedule
  
  tags = local.common_tags
  
  depends_on = [module.vnet]
}

# Storage Account
module "storage" {
  source = "./modules/storage"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  
  storage_accounts = {
    "${replace(local.cluster_name, "-", "")}data" = {
      account_tier             = "Standard"
      account_replication_type = "GRS"
      account_kind            = "StorageV2"
      enable_https_traffic_only = true
      min_tls_version         = "TLS1_2"
      
      containers = [
        {
          name                  = "backups"
          container_access_type = "private"
        },
        {
          name                  = "data"
          container_access_type = "private"
        }
      ]
      
      lifecycle_rules = [
        {
          name    = "archiveoldbackups"
          enabled = true
          prefix_match = ["backups/"]
          
          blob_types = ["blockBlob"]
          
          tier_to_cool_after_days    = 30
          tier_to_archive_after_days = 90
          delete_after_days          = 365
        }
      ]
    }
  }
  
  # Network rules
  network_rules = {
    default_action = "Deny"
    bypass         = ["AzureServices"]
    ip_rules       = var.storage_allowed_ips
    subnet_ids     = [module.vnet.subnet_ids["aks-nodes"]]
  }
  
  tags = local.common_tags
}

# Key Vault
resource "azurerm_key_vault" "main" {
  name                = "${replace(local.cluster_name, "-", "")}kv"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"
  
  enabled_for_deployment          = true
  enabled_for_disk_encryption     = true
  enabled_for_template_deployment = true
  enable_rbac_authorization       = true
  purge_protection_enabled        = true
  soft_delete_retention_days      = 90
  
  network_acls {
    default_action = "Deny"
    bypass         = "AzureServices"
    ip_rules       = var.keyvault_allowed_ips
    virtual_network_subnet_ids = [module.vnet.subnet_ids["aks-nodes"]]
  }
  
  tags = local.common_tags
}

# Container Registry
resource "azurerm_container_registry" "main" {
  name                = "${replace(local.cluster_name, "-", "")}acr"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = var.acr_sku
  admin_enabled       = false
  
  georeplications = var.acr_sku == "Premium" ? var.acr_georeplications : []
  
  retention_policy {
    days    = var.acr_retention_days
    enabled = true
  }
  
  trust_policy {
    enabled = var.acr_sku == "Premium" ? true : false
  }
  
  tags = local.common_tags
}

# Private DNS Zones
resource "azurerm_private_dns_zone" "postgresql" {
  name                = "privatelink.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "postgresql" {
  name                  = "${local.cluster_name}-postgresql-link"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.postgresql.name
  virtual_network_id    = module.vnet.vnet_id
  registration_enabled  = false
}

# Monitoring and Diagnostics
module "monitoring" {
  source = "./modules/monitoring"

  resource_group_name    = azurerm_resource_group.main.name
  location              = azurerm_resource_group.main.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  
  # Application Insights
  create_application_insights = var.create_application_insights
  application_insights_name   = "${local.cluster_name}-insights"
  
  # Action Groups
  action_groups = var.action_groups
  
  # Metric Alerts
  metric_alerts = var.metric_alerts
  
  # Log Alerts
  log_alerts = var.log_alerts
  
  tags = local.common_tags
}

# Configure Kubernetes Provider
provider "kubernetes" {
  host                   = module.aks.kube_config.0.host
  client_certificate     = base64decode(module.aks.kube_config.0.client_certificate)
  client_key             = base64decode(module.aks.kube_config.0.client_key)
  cluster_ca_certificate = base64decode(module.aks.kube_config.0.cluster_ca_certificate)
}

# Configure Helm Provider
provider "helm" {
  kubernetes {
    host                   = module.aks.kube_config.0.host
    client_certificate     = base64decode(module.aks.kube_config.0.client_certificate)
    client_key             = base64decode(module.aks.kube_config.0.client_key)
    cluster_ca_certificate = base64decode(module.aks.kube_config.0.cluster_ca_certificate)
  }
}

# Kubernetes Namespaces
resource "kubernetes_namespace" "namespaces" {
  for_each = toset(var.kubernetes_namespaces)

  metadata {
    name = each.value
    labels = merge(local.common_tags, {
      name = each.value
    })
  }
  
  depends_on = [module.aks]
}

# Storage Classes
resource "kubernetes_storage_class" "storage_classes" {
  for_each = var.storage_classes

  metadata {
    name = each.key
    annotations = {
      "storageclass.kubernetes.io/is-default-class" = each.value.is_default
    }
  }

  storage_provisioner    = "disk.csi.azure.com"
  reclaim_policy        = each.value.reclaim_policy
  allow_volume_expansion = true
  volume_binding_mode   = each.value.volume_binding_mode

  parameters = {
    skuName = each.value.sku_name
    kind    = "Managed"
  }
}

# Role Assignment for AKS to ACR
resource "azurerm_role_assignment" "aks_to_acr" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = module.aks.kubelet_identity_object_id
}