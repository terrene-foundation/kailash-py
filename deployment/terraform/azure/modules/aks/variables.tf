# Variables for AKS Module

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "cluster_name" {
  description = "Name of the AKS cluster"
  type        = string
}

variable "kubernetes_version" {
  description = "Kubernetes version"
  type        = string
}

variable "vnet_subnet_id" {
  description = "Subnet ID for AKS nodes"
  type        = string
}

variable "network_plugin" {
  description = "Network plugin to use (azure or kubenet)"
  type        = string
  default     = "azure"
}

variable "network_policy" {
  description = "Network policy to use (calico or azure)"
  type        = string
  default     = "calico"
}

variable "service_cidr" {
  description = "CIDR for Kubernetes services"
  type        = string
}

variable "dns_service_ip" {
  description = "IP address for Kubernetes DNS service"
  type        = string
}

variable "default_node_pool" {
  description = "Default node pool configuration"
  type = object({
    name                = string
    vm_size            = string
    node_count         = number
    min_count          = number
    max_count          = number
    enable_auto_scaling = bool
    availability_zones  = list(string)
    node_labels        = map(string)
    node_taints        = list(string)
  })
}

variable "node_pools" {
  description = "Additional node pools"
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
  default = {}
}

variable "identity_type" {
  description = "Type of managed identity"
  type        = string
  default     = "SystemAssigned"
}

variable "rbac_enabled" {
  description = "Enable RBAC"
  type        = bool
  default     = true
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

variable "enable_http_application_routing" {
  description = "Enable HTTP application routing"
  type        = bool
  default     = false
}

variable "enable_azure_policy" {
  description = "Enable Azure Policy"
  type        = bool
  default     = true
}

variable "enable_oms_agent" {
  description = "Enable OMS agent"
  type        = bool
  default     = true
}

variable "log_analytics_workspace_id" {
  description = "Log Analytics workspace ID"
  type        = string
}

variable "enable_key_vault_secrets_provider" {
  description = "Enable Key Vault secrets provider"
  type        = bool
  default     = true
}

variable "enable_host_encryption" {
  description = "Enable host encryption"
  type        = bool
  default     = true
}

variable "private_cluster_enabled" {
  description = "Enable private cluster"
  type        = bool
  default     = false
}

variable "authorized_ip_ranges" {
  description = "Authorized IP ranges for API server"
  type        = list(string)
  default     = []
}

variable "fips_enabled" {
  description = "Enable FIPS"
  type        = bool
  default     = false
}

variable "admin_username" {
  description = "Admin username for Linux nodes"
  type        = string
  default     = null
}

variable "ssh_key" {
  description = "SSH public key for Linux nodes"
  type        = string
  default     = null
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
  default = null
}

variable "auto_scaler_profile" {
  description = "Auto-scaler profile configuration"
  type = object({
    balance_similar_node_groups      = bool
    expander                        = string
    max_graceful_termination_sec    = number
    max_node_provisioning_time      = string
    max_unready_nodes               = number
    max_unready_percentage          = number
    new_pod_scale_up_delay          = string
    scale_down_delay_after_add      = string
    scale_down_delay_after_delete   = string
    scale_down_delay_after_failure  = string
    scan_interval                   = string
    scale_down_unneeded             = string
    scale_down_unready              = string
    scale_down_utilization_threshold = number
  })
  default = {
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
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}