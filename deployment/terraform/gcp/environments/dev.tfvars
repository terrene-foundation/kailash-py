# Development Environment Configuration

# Project settings
project_id   = "your-project-id-dev"
environment  = "dev"
region       = "us-central1"
zones        = ["us-central1-a", "us-central1-b", "us-central1-c"]

# Network configuration
vpc_cidr      = "10.0.0.0/16"
pods_cidr     = "10.1.0.0/16"
services_cidr = "10.2.0.0/16"
master_cidr   = "172.16.0.0/28"

# Authorized networks for GKE master access
master_authorized_networks = [
  {
    display_name = "Office Network"
    cidr_block   = "YOUR_OFFICE_IP/32"
  },
  {
    display_name = "VPN Network"
    cidr_block   = "YOUR_VPN_CIDR/24"
  }
]

# GKE configuration
kubernetes_version = "1.28"
release_channel    = "REGULAR"
regional_cluster   = false  # Zonal cluster for dev

# Cluster autoscaling limits (smaller for dev)
min_cpu_cores = 2
max_cpu_cores = 20
min_memory_gb = 8
max_memory_gb = 80

# Node pools (smaller for dev)
node_pools = {
  general = {
    machine_type  = "e2-standard-2"
    min_count     = 1
    max_count     = 3
    initial_count = 1
    disk_size_gb  = 50
    disk_type     = "pd-standard"
    auto_repair   = true
    auto_upgrade  = true
    preemptible   = true  # Use preemptible for cost savings
    spot          = false
    taints        = []
    labels = {
      workload = "general"
      env      = "dev"
    }
  }
}

# Database configuration (minimal for dev)
database_version           = "POSTGRES_15"
database_tier             = "db-f1-micro"
database_availability_type = "ZONAL"

# Redis configuration (minimal for dev)
redis_tier           = "BASIC"
redis_memory_size_gb = 1
redis_version        = "REDIS_7_0"

# Monitoring
create_monitoring_workspace = true

# Alert policies (basic for dev)
alert_policies = {
  high_cpu = {
    display_name = "High CPU Usage"
    conditions = [{
      display_name = "CPU usage above 80%"
      threshold_value = 0.8
      duration = "60s"
    }]
  }
}

# Storage classes
storage_classes = {
  standard = {
    is_default           = "true"
    disk_type           = "pd-standard"
    reclaim_policy      = "Delete"
    volume_binding_mode = "Immediate"
    replication_type    = "none"
  }
}