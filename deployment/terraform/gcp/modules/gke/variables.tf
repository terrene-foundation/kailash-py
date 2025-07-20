# Variables for GKE Module

variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "cluster_name" {
  description = "Name of the GKE cluster"
  type        = string
}

variable "location" {
  description = "Location for the GKE cluster (region or zone)"
  type        = string
}

variable "regional" {
  description = "Whether this is a regional cluster"
  type        = bool
  default     = true
}

variable "zones" {
  description = "Zones for the cluster nodes (for regional clusters)"
  type        = list(string)
  default     = []
}

variable "network" {
  description = "VPC network name"
  type        = string
}

variable "subnetwork" {
  description = "VPC subnetwork name"
  type        = string
}

variable "pods_range" {
  description = "Secondary range name for pods"
  type        = string
}

variable "services_range" {
  description = "Secondary range name for services"
  type        = string
}

variable "master_ipv4_cidr_block" {
  description = "CIDR block for the master nodes"
  type        = string
}

variable "kubernetes_version" {
  description = "Kubernetes version"
  type        = string
  default     = ""
}

variable "release_channel" {
  description = "Release channel for GKE"
  type        = string
  default     = "REGULAR"
}

variable "enable_private_nodes" {
  description = "Enable private nodes"
  type        = bool
  default     = true
}

variable "enable_private_endpoint" {
  description = "Enable private endpoint"
  type        = bool
  default     = false
}

variable "master_authorized_networks" {
  description = "Networks authorized to access the master"
  type = list(object({
    display_name = string
    cidr_block   = string
  }))
  default = []
}

variable "enable_shielded_nodes" {
  description = "Enable shielded nodes"
  type        = bool
  default     = true
}

variable "enable_workload_identity" {
  description = "Enable workload identity"
  type        = bool
  default     = true
}

variable "enable_binary_authorization" {
  description = "Enable binary authorization"
  type        = bool
  default     = false
}

variable "enable_horizontal_pod_autoscaling" {
  description = "Enable horizontal pod autoscaling"
  type        = bool
  default     = true
}

variable "enable_vertical_pod_autoscaling" {
  description = "Enable vertical pod autoscaling"
  type        = bool
  default     = true
}

variable "enable_cluster_autoscaling" {
  description = "Enable cluster autoscaling"
  type        = bool
  default     = true
}

variable "cluster_autoscaling_config" {
  description = "Cluster autoscaling configuration"
  type = object({
    min_cpu_cores = number
    max_cpu_cores = number
    min_memory_gb = number
    max_memory_gb = number
  })
  default = {
    min_cpu_cores = 4
    max_cpu_cores = 100
    min_memory_gb = 16
    max_memory_gb = 400
  }
}

variable "node_pools" {
  description = "Node pool configurations"
  type = map(object({
    machine_type   = string
    min_count      = number
    max_count      = number
    initial_count  = number
    disk_size_gb   = number
    disk_type      = string
    auto_repair    = bool
    auto_upgrade   = bool
    preemptible    = bool
    spot           = bool
    max_surge      = optional(number)
    max_unavailable = optional(number)
    upgrade_strategy = optional(string)
    accelerators   = optional(list(object({
      type  = string
      count = number
    })))
    taints = list(object({
      key    = string
      value  = string
      effect = string
    }))
    labels = map(string)
  }))
}

variable "logging_config" {
  description = "Logging components to enable"
  type        = list(string)
  default     = ["SYSTEM_COMPONENTS", "WORKLOADS"]
}

variable "monitoring_config" {
  description = "Monitoring components to enable"
  type        = list(string)
  default     = ["SYSTEM_COMPONENTS"]
}

variable "maintenance_window" {
  description = "Maintenance window configuration"
  type = object({
    start_time = string
    end_time   = string
    recurrence = string
  })
}

variable "database_encryption_state" {
  description = "State of database encryption"
  type        = string
  default     = "DECRYPTED"
}

variable "database_encryption_key_name" {
  description = "KMS key for database encryption"
  type        = string
  default     = ""
}

variable "labels" {
  description = "Labels to apply to the cluster"
  type        = map(string)
  default     = {}
}

variable "enable_upgrade_notifications" {
  description = "Enable notifications for cluster upgrades"
  type        = bool
  default     = false
}

variable "upgrade_notification_topic" {
  description = "Pub/Sub topic for upgrade notifications"
  type        = string
  default     = ""
}

variable "enable_cost_management" {
  description = "Enable GKE cost allocation"
  type        = bool
  default     = true
}