# Variables for GCP Infrastructure

# Project Configuration
variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

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

variable "region" {
  description = "The GCP region for resources"
  type        = string
  default     = "us-central1"
}

variable "zones" {
  description = "The GCP zones for GKE nodes"
  type        = list(string)
  default     = ["us-central1-a", "us-central1-b", "us-central1-c"]
}

variable "team_name" {
  description = "Team name for resource labeling"
  type        = string
  default     = "platform"
}

# Network Configuration
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "pods_cidr" {
  description = "CIDR block for Kubernetes pods"
  type        = string
  default     = "10.1.0.0/16"
}

variable "services_cidr" {
  description = "CIDR block for Kubernetes services"
  type        = string
  default     = "10.2.0.0/16"
}

variable "master_cidr" {
  description = "CIDR block for GKE master nodes"
  type        = string
  default     = "172.16.0.0/28"
}

variable "master_authorized_networks" {
  description = "List of networks authorized to access GKE master"
  type = list(object({
    display_name = string
    cidr_block   = string
  }))
  default = []
}

# GKE Configuration
variable "kubernetes_version" {
  description = "Kubernetes version for GKE"
  type        = string
  default     = "1.28"
}

variable "release_channel" {
  description = "GKE release channel"
  type        = string
  default     = "REGULAR"
}

variable "regional_cluster" {
  description = "Whether to create a regional cluster (vs zonal)"
  type        = bool
  default     = true
}

variable "min_cpu_cores" {
  description = "Minimum CPU cores for cluster autoscaling"
  type        = number
  default     = 4
}

variable "max_cpu_cores" {
  description = "Maximum CPU cores for cluster autoscaling"
  type        = number
  default     = 100
}

variable "min_memory_gb" {
  description = "Minimum memory in GB for cluster autoscaling"
  type        = number
  default     = 16
}

variable "max_memory_gb" {
  description = "Maximum memory in GB for cluster autoscaling"
  type        = number
  default     = 400
}

variable "node_pools" {
  description = "Configuration for GKE node pools"
  type = map(object({
    machine_type       = string
    min_count         = number
    max_count         = number
    initial_count     = number
    disk_size_gb      = number
    disk_type         = string
    auto_repair       = bool
    auto_upgrade      = bool
    preemptible       = bool
    spot              = bool
    taints = list(object({
      key    = string
      value  = string
      effect = string
    }))
    labels = map(string)
  }))
  default = {
    general = {
      machine_type  = "n2-standard-4"
      min_count     = 1
      max_count     = 10
      initial_count = 3
      disk_size_gb  = 100
      disk_type     = "pd-standard"
      auto_repair   = true
      auto_upgrade  = true
      preemptible   = false
      spot          = false
      taints        = []
      labels = {
        workload = "general"
      }
    }
    spot = {
      machine_type  = "n2-standard-4"
      min_count     = 0
      max_count     = 20
      initial_count = 0
      disk_size_gb  = 100
      disk_type     = "pd-standard"
      auto_repair   = true
      auto_upgrade  = true
      preemptible   = false
      spot          = true
      taints = [{
        key    = "workload"
        value  = "spot"
        effect = "NoSchedule"
      }]
      labels = {
        workload = "spot"
      }
    }
  }
}

# Maintenance Window
variable "maintenance_window_start" {
  description = "Start time for maintenance window (RFC3339 format)"
  type        = string
  default     = "2023-01-01T09:00:00Z"
}

variable "maintenance_window_end" {
  description = "End time for maintenance window (RFC3339 format)"
  type        = string
  default     = "2023-01-01T17:00:00Z"
}

variable "maintenance_window_recurrence" {
  description = "Recurrence for maintenance window (RFC5545 format)"
  type        = string
  default     = "FREQ=WEEKLY;BYDAY=SA"
}

# Database Configuration
variable "database_version" {
  description = "PostgreSQL version for Cloud SQL"
  type        = string
  default     = "POSTGRES_15"
}

variable "database_tier" {
  description = "Machine type for Cloud SQL instance"
  type        = string
  default     = "db-g1-small"
}

variable "database_availability_type" {
  description = "Availability type for Cloud SQL (ZONAL or REGIONAL)"
  type        = string
  default     = "ZONAL"
}

variable "database_flags" {
  description = "Database flags for Cloud SQL"
  type = list(object({
    name  = string
    value = string
  }))
  default = [
    {
      name  = "max_connections"
      value = "200"
    },
    {
      name  = "shared_buffers"
      value = "256MB"
    }
  ]
}

variable "databases" {
  description = "List of databases to create"
  type        = list(string)
  default     = ["kailash"]
}

variable "database_users" {
  description = "List of database users to create"
  type = list(object({
    name     = string
    password = string
  }))
  default = []
  sensitive = true
}

# Redis Configuration
variable "redis_tier" {
  description = "Service tier for Redis (BASIC or STANDARD_HA)"
  type        = string
  default     = "BASIC"
}

variable "redis_memory_size_gb" {
  description = "Memory size in GB for Redis instance"
  type        = number
  default     = 1
}

variable "redis_version" {
  description = "Redis version"
  type        = string
  default     = "REDIS_7_0"
}

variable "redis_replica_count" {
  description = "Number of Redis replicas (for STANDARD_HA tier)"
  type        = number
  default     = 1
}

variable "redis_read_replicas_mode" {
  description = "Read replicas mode for Redis"
  type        = string
  default     = "READ_REPLICAS_DISABLED"
}

variable "redis_configs" {
  description = "Redis configuration parameters"
  type        = map(string)
  default = {
    maxmemory-policy = "allkeys-lru"
  }
}

variable "redis_maintenance_window_day" {
  description = "Day of week for Redis maintenance (1-7, 1=Monday)"
  type        = number
  default     = 7
}

variable "redis_maintenance_window_time" {
  description = "Hour of day for Redis maintenance (0-23)"
  type        = object({
    hours   = number
    minutes = number
    seconds = number
    nanos   = number
  })
  default = {
    hours   = 3
    minutes = 0
    seconds = 0
    nanos   = 0
  }
}

# KMS Configuration
variable "kms_key_name" {
  description = "Name of the Cloud KMS key for encryption"
  type        = string
  default     = ""
}

# Kubernetes Configuration
variable "kubernetes_namespaces" {
  description = "List of Kubernetes namespaces to create"
  type        = list(string)
  default = [
    "kailash-system",
    "vault-system",
    "external-secrets-system",
    "monitoring",
    "ingress-nginx",
    "cert-manager"
  ]
}

variable "storage_classes" {
  description = "Storage classes to create"
  type = map(object({
    is_default           = string
    disk_type           = string
    reclaim_policy      = string
    volume_binding_mode = string
    replication_type    = string
  }))
  default = {
    fast = {
      is_default           = "false"
      disk_type           = "pd-ssd"
      reclaim_policy      = "Delete"
      volume_binding_mode = "WaitForFirstConsumer"
      replication_type    = "regional-pd"
    }
    standard = {
      is_default           = "true"
      disk_type           = "pd-standard"
      reclaim_policy      = "Delete"
      volume_binding_mode = "WaitForFirstConsumer"
      replication_type    = "regional-pd"
    }
  }
}

variable "priority_classes" {
  description = "Priority classes for workload scheduling"
  type = map(object({
    value          = number
    global_default = bool
    description    = string
  }))
  default = {
    critical = {
      value          = 1000
      global_default = false
      description    = "Critical system components"
    }
    high = {
      value          = 900
      global_default = false
      description    = "High priority workloads"
    }
    default = {
      value          = 500
      global_default = true
      description    = "Default priority"
    }
    low = {
      value          = 100
      global_default = false
      description    = "Low priority workloads"
    }
  }
}

# Monitoring Configuration
variable "create_monitoring_workspace" {
  description = "Whether to create a new monitoring workspace"
  type        = bool
  default     = true
}

variable "alert_policies" {
  description = "Alert policies configuration"
  type        = any
  default     = {}
}

variable "uptime_checks" {
  description = "Uptime check configurations"
  type        = any
  default     = {}
}

variable "monitoring_dashboards" {
  description = "Custom monitoring dashboards"
  type        = any
  default     = {}
}

variable "notification_channels" {
  description = "Notification channels for alerts"
  type        = any
  default     = {}
}