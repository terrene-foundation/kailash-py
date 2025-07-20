# Development Environment Configuration for Azure

# General settings
environment = "dev"
location    = "eastus2"

# Network configuration
vnet_cidr               = "10.0.0.0/16"
aks_subnet_cidr         = "10.0.1.0/20"
internal_lb_subnet_cidr = "10.0.16.0/24"
appgw_subnet_cidr       = "10.0.17.0/24"
postgresql_subnet_cidr  = "10.0.18.0/24"

# AKS configuration
kubernetes_version = "1.28"
availability_zones = ["1", "2"]

# System node pool (minimal for dev)
system_node_pool_vm_size       = "Standard_B2s"
system_node_pool_count         = 1
system_node_pool_min_count     = 1
system_node_pool_max_count     = 3

# Additional node pools (minimal for dev)
node_pools = {
  general = {
    vm_size             = "Standard_B4ms"
    node_count         = 1
    min_count          = 1
    max_count          = 3
    enable_auto_scaling = true
    availability_zones  = ["1", "2"]
    node_labels = {
      workload = "general"
      env      = "dev"
    }
    node_taints     = []
    max_pods        = 30
    os_disk_size_gb = 100
    os_disk_type    = "Managed"
  }
}

# Security settings (relaxed for dev)
private_cluster_enabled = false
authorized_ip_ranges    = ["YOUR_DEV_IP/32"]  # Add your development IPs

# PostgreSQL (minimal for dev)
postgresql_version         = "15"
postgresql_sku_name       = "B_Standard_B1ms"  # Burstable tier for dev
postgresql_storage_mb     = 32768  # 32 GB
postgresql_zone_redundant = false
postgresql_backup_retention_days = 7
postgresql_geo_redundant_backup = false

# Redis (minimal for dev)
redis_capacity = 0  # 250 MB for Basic
redis_family   = "C"
redis_sku_name = "Basic"

# Storage
storage_allowed_ips = ["YOUR_DEV_IP/32"]

# Key Vault
keyvault_allowed_ips = ["YOUR_DEV_IP/32"]

# Container Registry
acr_sku = "Basic"
acr_retention_days = 7

# Monitoring (basic for dev)
log_retention_days = 7
create_application_insights = true

# Alert configuration (minimal for dev)
action_groups = {
  dev_team = {
    short_name = "devteam"
    email_receivers = [
      {
        name          = "DevTeam"
        email_address = "dev-team@yourdomain.com"
      }
    ]
  }
}

metric_alerts = {
  high_cpu = {
    description = "Alert when CPU usage is high"
    severity    = 3
    frequency   = "PT5M"
    window_size = "PT5M"
    criteria = {
      metric_namespace = "Microsoft.ContainerService/managedClusters"
      metric_name      = "node_cpu_usage_percentage"
      aggregation      = "Average"
      operator         = "GreaterThan"
      threshold        = 80
    }
  }
}

# Tags
tags = {
  environment    = "dev"
  cost_center    = "engineering"
  managed_by     = "terraform"
  auto_shutdown  = "true"
}