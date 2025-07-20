# Production Environment Configuration for Azure

# General settings
environment = "prod"
location    = "eastus2"

# Network configuration
vnet_cidr               = "10.0.0.0/16"
aks_subnet_cidr         = "10.0.1.0/20"
internal_lb_subnet_cidr = "10.0.16.0/24"
appgw_subnet_cidr       = "10.0.17.0/24"
postgresql_subnet_cidr  = "10.0.18.0/24"

# Enable DDoS protection for production
enable_ddos_protection = true

# AKS configuration
kubernetes_version = "1.28"
availability_zones = ["1", "2", "3"]

# System node pool (dedicated for production)
system_node_pool_vm_size       = "Standard_D4s_v3"
system_node_pool_count         = 3
system_node_pool_min_count     = 3
system_node_pool_max_count     = 5

# Additional node pools (production-grade)
node_pools = {
  general = {
    vm_size             = "Standard_D8s_v3"
    node_count         = 6
    min_count          = 3
    max_count          = 20
    enable_auto_scaling = true
    availability_zones  = ["1", "2", "3"]
    node_labels = {
      workload = "general"
      env      = "prod"
    }
    node_taints     = []
    max_pods        = 30
    os_disk_size_gb = 200
    os_disk_type    = "Managed"
  }
  
  memory = {
    vm_size             = "Standard_E8s_v3"
    node_count         = 3
    min_count          = 2
    max_count          = 10
    enable_auto_scaling = true
    availability_zones  = ["1", "2", "3"]
    node_labels = {
      workload = "memory-intensive"
      env      = "prod"
    }
    node_taints = ["workload=memory-intensive:NoSchedule"]
    max_pods        = 30
    os_disk_size_gb = 200
    os_disk_type    = "Managed"
  }
  
  spot = {
    vm_size             = "Standard_D4s_v3"
    node_count         = 0
    min_count          = 0
    max_count          = 20
    enable_auto_scaling = true
    availability_zones  = ["1", "2", "3"]
    node_labels = {
      workload = "spot"
      env      = "prod"
      "kubernetes.azure.com/scalesetpriority" = "spot"
    }
    node_taints = [
      "kubernetes.azure.com/scalesetpriority=spot:NoSchedule"
    ]
    max_pods        = 30
    os_disk_size_gb = 100
    os_disk_type    = "Managed"
  }
}

# Security settings (hardened for production)
private_cluster_enabled = true
authorized_ip_ranges    = [
  "YOUR_OFFICE_CIDR/24",     # Office network
  "YOUR_VPN_CIDR/24",        # VPN network
  "YOUR_CICD_IP/32"          # CI/CD pipeline
]

# Azure AD integration
azure_ad_enabled = true
admin_group_ids  = ["YOUR-ADMIN-GROUP-ID"]  # Azure AD group for admins

# PostgreSQL (HA for production)
postgresql_version         = "15"
postgresql_sku_name       = "GP_Standard_D4s_v3"
postgresql_storage_mb     = 524288  # 512 GB
postgresql_zone_redundant = true
postgresql_backup_retention_days = 35
postgresql_geo_redundant_backup = true

postgresql_configurations = {
  max_connections              = "500"
  shared_buffers              = "131072"  # 1GB in 8KB pages
  effective_cache_size        = "1048576" # 8GB in 8KB pages
  maintenance_work_mem        = "524288"  # 512MB in KB
  checkpoint_completion_target = "0.9"
  wal_buffers                 = "4096"    # 32MB in 8KB pages
  default_statistics_target   = "100"
  random_page_cost            = "1.1"
  effective_io_concurrency    = "200"
  work_mem                    = "32768"   # 32MB in KB
  huge_pages                  = "try"
  max_wal_size                = "8GB"
  min_wal_size                = "2GB"
}

# Redis (Premium for production)
redis_capacity = 2  # 13 GB for P2
redis_family   = "P"
redis_sku_name = "Premium"

redis_configuration = {
  maxmemory_policy = "allkeys-lru"
  notify_keyspace_events = "Ex"
  maxclients = "10000"
  maxmemory_reserved = "2048"
  maxfragmentationmemory_reserved = "2048"
  maxmemory_delta = "2048"
}

# Storage
storage_allowed_ips = [
  "YOUR_OFFICE_CIDR/24",
  "YOUR_VPN_CIDR/24"
]

# Key Vault
keyvault_allowed_ips = [
  "YOUR_OFFICE_CIDR/24",
  "YOUR_VPN_CIDR/24"
]

# Container Registry (Premium for production)
acr_sku = "Premium"
acr_retention_days = 90

# Geo-replication for ACR
acr_georeplications = [
  {
    location                = "westus2"
    zone_redundancy_enabled = true
    tags                    = {}
  }
]

# Monitoring (comprehensive for production)
log_retention_days = 90
create_application_insights = true

# Alert configuration
action_groups = {
  critical_alerts = {
    short_name = "critical"
    email_receivers = [
      {
        name          = "OpsTeam"
        email_address = "ops-team@yourdomain.com"
      }
    ]
    sms_receivers = [
      {
        name         = "OnCall"
        country_code = "1"
        phone_number = "5551234567"
      }
    ]
    webhook_receivers = [
      {
        name        = "PagerDuty"
        service_uri = "https://events.pagerduty.com/integration/YOUR_KEY/enqueue"
      }
    ]
  }
  
  warning_alerts = {
    short_name = "warning"
    email_receivers = [
      {
        name          = "DevTeam"
        email_address = "dev-team@yourdomain.com"
      }
    ]
  }
}

metric_alerts = {
  node_cpu_critical = {
    description = "Node CPU usage critical"
    severity    = 1
    frequency   = "PT1M"
    window_size = "PT5M"
    action_group_name = "critical_alerts"
    criteria = {
      metric_namespace = "Microsoft.ContainerService/managedClusters"
      metric_name      = "node_cpu_usage_percentage"
      aggregation      = "Average"
      operator         = "GreaterThan"
      threshold        = 90
    }
  }
  
  node_memory_critical = {
    description = "Node memory usage critical"
    severity    = 1
    frequency   = "PT1M"
    window_size = "PT5M"
    action_group_name = "critical_alerts"
    criteria = {
      metric_namespace = "Microsoft.ContainerService/managedClusters"
      metric_name      = "node_memory_working_set_percentage"
      aggregation      = "Average"
      operator         = "GreaterThan"
      threshold        = 85
    }
  }
  
  pod_failed = {
    description = "Pods in failed state"
    severity    = 2
    frequency   = "PT5M"
    window_size = "PT5M"
    action_group_name = "warning_alerts"
    criteria = {
      metric_namespace = "Microsoft.ContainerService/managedClusters"
      metric_name      = "kube_pod_status_phase"
      dimension_name   = "phase"
      dimension_value  = "Failed"
      aggregation      = "Average"
      operator         = "GreaterThan"
      threshold        = 0
    }
  }
  
  disk_usage_high = {
    description = "Disk usage high"
    severity    = 2
    frequency   = "PT5M"
    window_size = "PT15M"
    action_group_name = "warning_alerts"
    criteria = {
      metric_namespace = "Microsoft.ContainerService/managedClusters"
      metric_name      = "node_disk_usage_percentage"
      aggregation      = "Average"
      operator         = "GreaterThan"
      threshold        = 80
    }
  }
}

# Maintenance window (weekend nights)
maintenance_window = {
  allowed = [
    {
      day   = "Saturday"
      hours = [2, 3, 4, 5]
    },
    {
      day   = "Sunday"
      hours = [2, 3, 4, 5]
    }
  ]
  not_allowed = []
}

# Tags
tags = {
  environment         = "prod"
  cost_center         = "operations"
  compliance          = "required"
  data_classification = "confidential"
  backup              = "required"
  disaster_recovery   = "required"
  sla                 = "99.9"
}