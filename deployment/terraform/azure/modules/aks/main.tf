# AKS Cluster Module - Enterprise-grade Kubernetes on Azure

# AKS Cluster
resource "azurerm_kubernetes_cluster" "main" {
  name                = var.cluster_name
  location            = var.location
  resource_group_name = var.resource_group_name
  dns_prefix          = var.cluster_name
  kubernetes_version  = var.kubernetes_version

  # Default node pool (system)
  default_node_pool {
    name                = var.default_node_pool.name
    vm_size             = var.default_node_pool.vm_size
    node_count          = var.default_node_pool.enable_auto_scaling ? null : var.default_node_pool.node_count
    enable_auto_scaling = var.default_node_pool.enable_auto_scaling
    min_count           = var.default_node_pool.enable_auto_scaling ? var.default_node_pool.min_count : null
    max_count           = var.default_node_pool.enable_auto_scaling ? var.default_node_pool.max_count : null
    
    # Availability zones
    availability_zones = var.default_node_pool.availability_zones
    
    # Node configuration
    node_labels = var.default_node_pool.node_labels
    node_taints = var.default_node_pool.node_taints
    
    # Network configuration
    vnet_subnet_id = var.vnet_subnet_id
    
    # Host encryption
    enable_host_encryption = var.enable_host_encryption
    
    # Pod configuration
    max_pods = 30
    
    # OS configuration
    os_disk_size_gb = 100
    os_disk_type    = "Managed"
    
    # Update configuration
    upgrade_settings {
      max_surge = "33%"
    }
    
    # Enable FIPS
    fips_enabled = var.fips_enabled
  }

  # Identity
  identity {
    type = var.identity_type
  }

  # Network profile
  network_profile {
    network_plugin    = var.network_plugin
    network_policy    = var.network_policy
    service_cidr      = var.service_cidr
    dns_service_ip    = var.dns_service_ip
    outbound_type     = "loadBalancer"
    load_balancer_sku = "standard"
  }

  # API server access profile
  api_server_access_profile {
    authorized_ip_ranges = var.private_cluster_enabled ? [] : var.authorized_ip_ranges
  }

  # Private cluster
  private_cluster_enabled = var.private_cluster_enabled
  private_dns_zone_id     = var.private_cluster_enabled ? "System" : null

  # Azure AD integration
  dynamic "azure_active_directory_role_based_access_control" {
    for_each = var.azure_ad_enabled ? [1] : []
    content {
      managed                = true
      admin_group_object_ids = var.admin_group_ids
      azure_rbac_enabled     = true
    }
  }

  # Add-ons
  addon_profile {
    # HTTP application routing (disabled for production)
    http_application_routing {
      enabled = var.enable_http_application_routing
    }
    
    # Azure Policy
    azure_policy {
      enabled = var.enable_azure_policy
    }
    
    # Monitoring
    oms_agent {
      enabled                    = var.enable_oms_agent
      log_analytics_workspace_id = var.log_analytics_workspace_id
    }
    
    # Key Vault Secrets Provider
    azure_keyvault_secrets_provider {
      enabled                  = var.enable_key_vault_secrets_provider
      secret_rotation_enabled  = true
      secret_rotation_interval = "2m"
    }
  }

  # Auto-scaler profile
  auto_scaler_profile {
    balance_similar_node_groups      = var.auto_scaler_profile.balance_similar_node_groups
    expander                        = var.auto_scaler_profile.expander
    max_graceful_termination_sec    = var.auto_scaler_profile.max_graceful_termination_sec
    max_node_provisioning_time      = var.auto_scaler_profile.max_node_provisioning_time
    max_unready_nodes               = var.auto_scaler_profile.max_unready_nodes
    max_unready_percentage          = var.auto_scaler_profile.max_unready_percentage
    new_pod_scale_up_delay          = var.auto_scaler_profile.new_pod_scale_up_delay
    scale_down_delay_after_add      = var.auto_scaler_profile.scale_down_delay_after_add
    scale_down_delay_after_delete   = var.auto_scaler_profile.scale_down_delay_after_delete
    scale_down_delay_after_failure  = var.auto_scaler_profile.scale_down_delay_after_failure
    scan_interval                   = var.auto_scaler_profile.scan_interval
    scale_down_unneeded             = var.auto_scaler_profile.scale_down_unneeded
    scale_down_unready              = var.auto_scaler_profile.scale_down_unready
    scale_down_utilization_threshold = var.auto_scaler_profile.scale_down_utilization_threshold
  }

  # Maintenance window
  dynamic "maintenance_window" {
    for_each = var.maintenance_window != null ? [var.maintenance_window] : []
    content {
      dynamic "allowed" {
        for_each = maintenance_window.value.allowed
        content {
          day   = allowed.value.day
          hours = allowed.value.hours
        }
      }
      
      dynamic "not_allowed" {
        for_each = maintenance_window.value.not_allowed
        content {
          start = not_allowed.value.start
          end   = not_allowed.value.end
        }
      }
    }
  }

  # Enable RBAC
  role_based_access_control {
    enabled = var.rbac_enabled
  }

  # Linux profile (for SSH access)
  dynamic "linux_profile" {
    for_each = var.admin_username != null ? [1] : []
    content {
      admin_username = var.admin_username
      
      ssh_key {
        key_data = var.ssh_key
      }
    }
  }

  tags = var.tags
}

# Additional Node Pools
resource "azurerm_kubernetes_cluster_node_pool" "additional" {
  for_each = var.node_pools

  name                  = each.key
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main.id
  vm_size              = each.value.vm_size
  node_count           = each.value.enable_auto_scaling ? null : each.value.node_count
  
  # Auto-scaling
  enable_auto_scaling = each.value.enable_auto_scaling
  min_count          = each.value.enable_auto_scaling ? each.value.min_count : null
  max_count          = each.value.enable_auto_scaling ? each.value.max_count : null
  
  # Availability zones
  availability_zones = each.value.availability_zones
  
  # Node configuration
  node_labels = each.value.node_labels
  node_taints = each.value.node_taints
  
  # Network
  vnet_subnet_id = var.vnet_subnet_id
  
  # Pod configuration
  max_pods = each.value.max_pods
  
  # OS disk
  os_disk_size_gb = each.value.os_disk_size_gb
  os_disk_type    = each.value.os_disk_type
  
  # Host encryption
  enable_host_encryption = var.enable_host_encryption
  
  # FIPS
  fips_enabled = var.fips_enabled
  
  # Update configuration
  upgrade_settings {
    max_surge = "33%"
  }
  
  tags = var.tags
}

# Diagnostic Settings
resource "azurerm_monitor_diagnostic_setting" "aks" {
  name                       = "${var.cluster_name}-diagnostics"
  target_resource_id         = azurerm_kubernetes_cluster.main.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  log {
    category = "kube-apiserver"
    enabled  = true

    retention_policy {
      enabled = true
      days    = 30
    }
  }

  log {
    category = "kube-audit"
    enabled  = true

    retention_policy {
      enabled = true
      days    = 30
    }
  }

  log {
    category = "kube-controller-manager"
    enabled  = true

    retention_policy {
      enabled = true
      days    = 30
    }
  }

  log {
    category = "kube-scheduler"
    enabled  = true

    retention_policy {
      enabled = true
      days    = 30
    }
  }

  log {
    category = "cluster-autoscaler"
    enabled  = true

    retention_policy {
      enabled = true
      days    = 30
    }
  }

  metric {
    category = "AllMetrics"
    enabled  = true

    retention_policy {
      enabled = true
      days    = 30
    }
  }
}