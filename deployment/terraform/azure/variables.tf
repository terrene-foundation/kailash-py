# Variables for Azure Infrastructure

# General Configuration
variable "project_name" {
  description = "Name of the project (used for resource naming)"
  type        = string
  default     = "kailash"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "location" {
  description = "Azure region for resources"
  type        = string
  default     = "eastus2"
}

variable "team_name" {
  description = "Team name for resource tagging"
  type        = string
  default     = "platform"
}

variable "tags" {
  description = "Additional tags for resources"
  type        = map(string)
  default     = {}
}

# Network Configuration
variable "vnet_cidr" {
  description = "CIDR block for Virtual Network"
  type        = string
  default     = "10.0.0.0/16"
}

variable "aks_subnet_cidr" {
  description = "CIDR block for AKS subnet"
  type        = string
  default     = "10.0.1.0/20"
}

variable "internal_lb_subnet_cidr" {
  description = "CIDR block for internal load balancer subnet"
  type        = string
  default     = "10.0.16.0/24"
}

variable "appgw_subnet_cidr" {
  description = "CIDR block for Application Gateway subnet"
  type        = string
  default     = "10.0.17.0/24"
}

variable "postgresql_subnet_cidr" {
  description = "CIDR block for PostgreSQL subnet"
  type        = string
  default     = "10.0.18.0/24"
}

variable "service_cidr" {
  description = "CIDR block for Kubernetes services"
  type        = string
  default     = "10.1.0.0/16"
}

variable "dns_service_ip" {
  description = "IP address for Kubernetes DNS service"
  type        = string
  default     = "10.1.0.10"
}

variable "enable_ddos_protection" {
  description = "Enable DDoS protection plan"
  type        = bool
  default     = false
}

# AKS Configuration
variable "kubernetes_version" {
  description = "Kubernetes version for AKS"
  type        = string
  default     = "1.28"
}

variable "availability_zones" {
  description = "Availability zones for AKS nodes"
  type        = list(string)
  default     = ["1", "2", "3"]
}

variable "system_node_pool_vm_size" {
  description = "VM size for system node pool"
  type        = string
  default     = "Standard_D2s_v3"
}

variable "system_node_pool_count" {
  description = "Initial node count for system pool"
  type        = number
  default     = 3
}

variable "system_node_pool_min_count" {
  description = "Minimum node count for system pool"
  type        = number
  default     = 1
}

variable "system_node_pool_max_count" {
  description = "Maximum node count for system pool"
  type        = number
  default     = 5
}

variable "node_pools" {
  description = "Additional node pools configuration"
  type = map(object({
    vm_size             = string
    node_count         = number
    min_count          = number
    max_count          = number
    enable_auto_scaling = bool
    availability_zones  = list(string)
    node_labels        = map(string)
    node_taints        = list(string)
    max_pods           = number
    os_disk_size_gb    = number
    os_disk_type       = string
  }))
  default = {
    general = {
      vm_size             = "Standard_D4s_v3"
      node_count         = 3
      min_count          = 2
      max_count          = 10
      enable_auto_scaling = true
      availability_zones  = ["1", "2", "3"]
      node_labels = {
        workload = "general"
      }
      node_taints     = []
      max_pods        = 30
      os_disk_size_gb = 100
      os_disk_type    = "Managed"
    }
  }
}

variable "azure_ad_enabled" {
  description = "Enable Azure AD integration"
  type        = bool
  default     = true
}

variable "admin_group_ids" {
  description = "Azure AD group IDs for cluster admins"
  type        = list(string)
  default     = []
}

variable "private_cluster_enabled" {
  description = "Enable private AKS cluster"
  type        = bool
  default     = false
}

variable "authorized_ip_ranges" {
  description = "Authorized IP ranges for API server"
  type        = list(string)
  default     = []
}

variable "log_retention_days" {
  description = "Log Analytics workspace retention in days"
  type        = number
  default     = 30
}

variable "maintenance_window" {
  description = "Maintenance window configuration"
  type = object({
    allowed = list(object({
      day   = string
      hours = list(number)
    }))
    not_allowed = list(object({
      start = string
      end   = string
    }))
  })
  default = {
    allowed = [
      {
        day   = "Saturday"
        hours = [1, 2, 3, 4]
      }
    ]
    not_allowed = []
  }
}

# PostgreSQL Configuration
variable "postgresql_version" {
  description = "PostgreSQL version"
  type        = string
  default     = "15"
}

variable "postgresql_sku_name" {
  description = "SKU for PostgreSQL server"
  type        = string
  default     = "GP_Standard_D2s_v3"
}

variable "postgresql_storage_mb" {
  description = "Storage size in MB for PostgreSQL"
  type        = number
  default     = 131072  # 128 GB
}

variable "postgresql_zone_redundant" {
  description = "Enable zone redundancy for PostgreSQL"
  type        = bool
  default     = false
}

variable "postgresql_backup_retention_days" {
  description = "Backup retention in days"
  type        = number
  default     = 30
}

variable "postgresql_geo_redundant_backup" {
  description = "Enable geo-redundant backups"
  type        = bool
  default     = false
}

variable "postgresql_databases" {
  description = "List of databases to create"
  type        = list(string)
  default     = ["kailash"]
}

variable "postgresql_configurations" {
  description = "PostgreSQL server parameters"
  type        = map(string)
  default = {
    max_connections            = "200"
    shared_buffers            = "65536"  # 256MB in 8KB pages
    effective_cache_size      = "524288" # 4GB in 8KB pages
    maintenance_work_mem      = "262144" # 256MB in KB
    checkpoint_completion_target = "0.9"
    wal_buffers               = "2048"   # 16MB in 8KB pages
    default_statistics_target = "100"
    random_page_cost          = "1.1"
    effective_io_concurrency  = "200"
    work_mem                  = "16384"  # 16MB in KB
    huge_pages                = "try"
  }
}

# Redis Configuration
variable "redis_capacity" {
  description = "Redis cache capacity"
  type        = number
  default     = 1
}

variable "redis_family" {
  description = "Redis cache family (C or P)"
  type        = string
  default     = "C"
}

variable "redis_sku_name" {
  description = "Redis cache SKU"
  type        = string
  default     = "Standard"
}

variable "redis_configuration" {
  description = "Redis configuration"
  type        = map(string)
  default     = {}
}

variable "redis_patch_schedule" {
  description = "Redis patch schedule"
  type = list(object({
    day_of_week    = string
    start_hour_utc = number
  }))
  default = [
    {
      day_of_week    = "Sunday"
      start_hour_utc = 2
    }
  ]
}

# Storage Configuration
variable "storage_allowed_ips" {
  description = "Allowed IP addresses for storage account"
  type        = list(string)
  default     = []
}

# Key Vault Configuration
variable "keyvault_allowed_ips" {
  description = "Allowed IP addresses for Key Vault"
  type        = list(string)
  default     = []
}

# Container Registry Configuration
variable "acr_sku" {
  description = "SKU for Container Registry"
  type        = string
  default     = "Standard"
}

variable "acr_retention_days" {
  description = "Retention policy in days for untagged manifests"
  type        = number
  default     = 30
}

variable "acr_georeplications" {
  description = "Geo-replication configuration for ACR"
  type = list(object({
    location                = string
    zone_redundancy_enabled = bool
    tags                    = map(string)
  }))
  default = []
}

# Kubernetes Configuration
variable "kubernetes_namespaces" {
  description = "List of Kubernetes namespaces to create"
  type        = list(string)
  default = [
    "kailash-system",
    "vault-system",
    "monitoring",
    "ingress-nginx",
    "cert-manager"
  ]
}

variable "storage_classes" {
  description = "Storage classes to create"
  type = map(object({
    is_default           = string
    sku_name            = string
    reclaim_policy      = string
    volume_binding_mode = string
  }))
  default = {
    managed-premium = {
      is_default           = "false"
      sku_name            = "Premium_LRS"
      reclaim_policy      = "Delete"
      volume_binding_mode = "WaitForFirstConsumer"
    }
    managed-standard = {
      is_default           = "true"
      sku_name            = "Standard_LRS"
      reclaim_policy      = "Delete"
      volume_binding_mode = "WaitForFirstConsumer"
    }
    managed-premium-retain = {
      is_default           = "false"
      sku_name            = "Premium_LRS"
      reclaim_policy      = "Retain"
      volume_binding_mode = "WaitForFirstConsumer"
    }
  }
}

# Monitoring Configuration
variable "create_application_insights" {
  description = "Create Application Insights instance"
  type        = bool
  default     = true
}

variable "action_groups" {
  description = "Action groups for alerts"
  type        = any
  default     = {}
}

variable "metric_alerts" {
  description = "Metric alert rules"
  type        = any
  default     = {}
}

variable "log_alerts" {
  description = "Log alert rules"
  type        = any
  default     = {}
}