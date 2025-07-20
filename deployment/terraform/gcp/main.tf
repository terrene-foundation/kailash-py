# Google Cloud Platform - Enterprise GKE Infrastructure
# Production-ready Kubernetes deployment with complete security and monitoring

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
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

  backend "gcs" {
    # Configuration provided via backend config file or CLI flags
    # bucket = "your-terraform-state-bucket"
    # prefix = "terraform/state/kailash"
  }
}

# Data sources
data "google_client_config" "default" {}

# Local variables
locals {
  project_id   = var.project_id
  region       = var.region
  cluster_name = "${var.project_name}-${var.environment}"
  
  common_labels = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
    team        = var.team_name
  }
}

# VPC Network
module "vpc" {
  source = "./modules/vpc"

  project_id   = local.project_id
  region       = local.region
  network_name = "${local.cluster_name}-vpc"
  
  # CIDR ranges for different environments
  primary_cidr     = var.vpc_cidr
  pods_cidr        = var.pods_cidr
  services_cidr    = var.services_cidr
  master_cidr      = var.master_cidr
  
  # Enable required APIs
  enable_flow_logs        = true
  enable_private_google_access = true
  enable_cloud_nat        = true
  
  labels = local.common_labels
}

# GKE Cluster
module "gke" {
  source = "./modules/gke"

  project_id     = local.project_id
  location       = var.regional_cluster ? local.region : var.zones[0]
  cluster_name   = local.cluster_name
  
  # Network configuration
  network         = module.vpc.network_name
  subnetwork      = module.vpc.subnet_name
  pods_range      = module.vpc.pods_range_name
  services_range  = module.vpc.services_range_name
  master_ipv4_cidr_block = var.master_cidr
  
  # Cluster configuration
  kubernetes_version      = var.kubernetes_version
  release_channel        = var.release_channel
  regional               = var.regional_cluster
  zones                  = var.zones
  
  # Security settings
  enable_private_nodes      = true
  enable_private_endpoint   = false # Set to true for fully private cluster
  master_authorized_networks = var.master_authorized_networks
  enable_shielded_nodes     = true
  enable_workload_identity  = true
  enable_binary_authorization = true
  
  # Features
  enable_horizontal_pod_autoscaling = true
  enable_vertical_pod_autoscaling   = true
  enable_cluster_autoscaling        = true
  cluster_autoscaling_config = {
    min_cpu_cores = var.min_cpu_cores
    max_cpu_cores = var.max_cpu_cores
    min_memory_gb = var.min_memory_gb
    max_memory_gb = var.max_memory_gb
  }
  
  # Node pools configuration
  node_pools = var.node_pools
  
  # Monitoring and logging
  enable_stackdriver_kubernetes_engine_monitoring = true
  logging_config = ["SYSTEM_COMPONENTS", "WORKLOADS", "API_SERVER"]
  monitoring_config = ["SYSTEM_COMPONENTS", "WORKLOADS", "API_SERVER"]
  
  # Maintenance window
  maintenance_window = {
    start_time = var.maintenance_window_start
    end_time   = var.maintenance_window_end
    recurrence = var.maintenance_window_recurrence
  }
  
  labels = local.common_labels
  
  depends_on = [module.vpc]
}

# Cloud SQL (PostgreSQL)
module "cloud_sql" {
  source = "./modules/cloud-sql"

  project_id   = local.project_id
  region       = local.region
  name         = "${local.cluster_name}-db"
  
  # Database configuration
  database_version = var.database_version
  tier            = var.database_tier
  
  # High availability
  availability_type = var.database_availability_type
  
  # Backup configuration
  backup_configuration = {
    enabled                        = true
    start_time                     = "03:00"
    location                       = local.region
    point_in_time_recovery_enabled = true
    transaction_log_retention_days = 7
    retained_backups              = 30
    retention_unit                = "COUNT"
  }
  
  # Network configuration
  network = module.vpc.network_self_link
  private_ip_enabled = true
  require_ssl = true
  
  # Database flags for security and performance
  database_flags = var.database_flags
  
  # Users and databases
  databases = var.databases
  users     = var.database_users
  
  labels = local.common_labels
  
  depends_on = [module.vpc]
}

# Memorystore (Redis)
module "memorystore" {
  source = "./modules/memorystore"

  project_id = local.project_id
  region     = local.region
  name       = "${local.cluster_name}-redis"
  
  # Redis configuration
  tier           = var.redis_tier
  memory_size_gb = var.redis_memory_size_gb
  redis_version  = var.redis_version
  
  # Network configuration
  network = module.vpc.network_self_link
  
  # High availability
  replica_count = var.redis_tier == "STANDARD_HA" ? var.redis_replica_count : 0
  read_replicas_mode = var.redis_read_replicas_mode
  
  # Redis configuration parameters
  redis_configs = var.redis_configs
  
  # Maintenance window
  maintenance_window = {
    day_of_week = var.redis_maintenance_window_day
    start_time  = var.redis_maintenance_window_time
  }
  
  labels = local.common_labels
  
  depends_on = [module.vpc]
}

# Cloud Storage Buckets
module "gcs" {
  source = "./modules/gcs"

  project_id = local.project_id
  location   = local.region
  
  # Bucket configurations
  buckets = {
    # Application data bucket
    "${local.cluster_name}-data" = {
      storage_class = "STANDARD"
      lifecycle_rules = [{
        action = {
          type = "SetStorageClass"
          storage_class = "NEARLINE"
        }
        condition = {
          age = 30
        }
      }]
      versioning = true
      encryption_key = var.kms_key_name
    }
    
    # Backup bucket
    "${local.cluster_name}-backups" = {
      storage_class = "NEARLINE"
      lifecycle_rules = [{
        action = {
          type = "Delete"
        }
        condition = {
          age = 90
        }
      }]
      versioning = true
      encryption_key = var.kms_key_name
    }
    
    # Logs bucket
    "${local.cluster_name}-logs" = {
      storage_class = "STANDARD"
      lifecycle_rules = [{
        action = {
          type = "SetStorageClass"
          storage_class = "COLDLINE"
        }
        condition = {
          age = 60
        }
      }]
      versioning = false
      encryption_key = var.kms_key_name
    }
  }
  
  # Uniform bucket-level access
  uniform_bucket_level_access = true
  
  labels = local.common_labels
}

# IAM and Workload Identity
module "iam" {
  source = "./modules/iam"

  project_id   = local.project_id
  cluster_name = module.gke.cluster_name
  
  # Workload Identity configuration
  workload_identity_namespace = local.project_id
  
  # Service accounts for different workloads
  service_accounts = {
    # Application service account
    "kailash-app" = {
      display_name = "Kailash Application"
      roles = [
        "roles/cloudsql.client",
        "roles/redis.editor",
        "roles/storage.objectUser",
        "roles/secretmanager.secretAccessor",
        "roles/monitoring.metricWriter",
        "roles/cloudtrace.agent"
      ]
      k8s_namespaces = ["default", "kailash-system"]
    }
    
    # Vault service account
    "vault" = {
      display_name = "HashiCorp Vault"
      roles = [
        "roles/secretmanager.admin",
        "roles/cloudkms.cryptoKeyEncrypterDecrypter",
        "roles/storage.objectAdmin" # For GCS backend
      ]
      k8s_namespaces = ["vault-system"]
    }
    
    # External Secrets Operator
    "external-secrets" = {
      display_name = "External Secrets Operator"
      roles = [
        "roles/secretmanager.secretAccessor"
      ]
      k8s_namespaces = ["external-secrets-system"]
    }
    
    # Monitoring service account
    "monitoring" = {
      display_name = "Monitoring Stack"
      roles = [
        "roles/monitoring.viewer",
        "roles/monitoring.metricWriter",
        "roles/logging.viewer"
      ]
      k8s_namespaces = ["monitoring"]
    }
  }
  
  depends_on = [module.gke]
}

# Monitoring Stack
module "monitoring" {
  source = "./modules/monitoring"

  project_id   = local.project_id
  cluster_name = module.gke.cluster_name
  
  # Monitoring workspace
  create_workspace = var.create_monitoring_workspace
  workspace_name   = "${local.cluster_name}-monitoring"
  
  # Alert policies
  alert_policies = var.alert_policies
  
  # Uptime checks
  uptime_checks = var.uptime_checks
  
  # Custom dashboards
  dashboards = var.monitoring_dashboards
  
  # Notification channels
  notification_channels = var.notification_channels
  
  labels = local.common_labels
  
  depends_on = [module.gke]
}

# Kubernetes provider configuration
provider "kubernetes" {
  host                   = "https://${module.gke.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(module.gke.ca_certificate)
}

# Helm provider configuration
provider "helm" {
  kubernetes {
    host                   = "https://${module.gke.endpoint}"
    token                  = data.google_client_config.default.access_token
    cluster_ca_certificate = base64decode(module.gke.ca_certificate)
  }
}

# Deploy base Kubernetes resources
resource "kubernetes_namespace" "namespaces" {
  for_each = toset(var.kubernetes_namespaces)

  metadata {
    name = each.value
    labels = merge(local.common_labels, {
      name = each.value
    })
  }
  
  depends_on = [module.gke]
}

# Deploy network policies
resource "kubernetes_network_policy" "default_deny" {
  for_each = kubernetes_namespace.namespaces

  metadata {
    name      = "default-deny-all"
    namespace = each.value.metadata[0].name
  }

  spec {
    pod_selector {}
    policy_types = ["Ingress", "Egress"]
  }
}

# Storage classes for different performance tiers
resource "kubernetes_storage_class" "storage_classes" {
  for_each = var.storage_classes

  metadata {
    name = each.key
    annotations = {
      "storageclass.kubernetes.io/is-default-class" = each.value.is_default
    }
  }

  storage_provisioner    = "kubernetes.io/gce-pd"
  reclaim_policy        = each.value.reclaim_policy
  allow_volume_expansion = true
  volume_binding_mode   = each.value.volume_binding_mode

  parameters = {
    type             = each.value.disk_type
    replication-type = each.value.replication_type
    fstype          = "ext4"
  }
}

# Priority classes for workload scheduling
resource "kubernetes_priority_class" "priority_classes" {
  for_each = var.priority_classes

  metadata {
    name = each.key
  }

  value          = each.value.value
  global_default = each.value.global_default
  description    = each.value.description
}