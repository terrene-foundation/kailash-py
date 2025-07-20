# Production Environment Configuration

# Project settings
project_id   = "your-project-id-prod"
environment  = "prod"
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
  },
  {
    display_name = "CI/CD Pipeline"
    cidr_block   = "YOUR_CICD_IP/32"
  }
]

# GKE configuration
kubernetes_version = "1.28"
release_channel    = "STABLE"  # More stable for production
regional_cluster   = true      # Regional for HA

# Cluster autoscaling limits
min_cpu_cores = 12
max_cpu_cores = 200
min_memory_gb = 48
max_memory_gb = 800

# Node pools (production-grade)
node_pools = {
  system = {
    machine_type  = "n2-standard-4"
    min_count     = 3
    max_count     = 10
    initial_count = 3
    disk_size_gb  = 100
    disk_type     = "pd-ssd"
    auto_repair   = true
    auto_upgrade  = true
    preemptible   = false
    spot          = false
    taints = [{
      key    = "CriticalAddonsOnly"
      value  = "true"
      effect = "NoSchedule"
    }]
    labels = {
      workload = "system"
      env      = "prod"
    }
  }
  
  general = {
    machine_type  = "n2-standard-8"
    min_count     = 3
    max_count     = 50
    initial_count = 6
    disk_size_gb  = 200
    disk_type     = "pd-ssd"
    auto_repair   = true
    auto_upgrade  = true
    preemptible   = false
    spot          = false
    taints        = []
    labels = {
      workload = "general"
      env      = "prod"
    }
  }
  
  memory = {
    machine_type  = "n2-highmem-4"
    min_count     = 0
    max_count     = 10
    initial_count = 2
    disk_size_gb  = 200
    disk_type     = "pd-ssd"
    auto_repair   = true
    auto_upgrade  = true
    preemptible   = false
    spot          = false
    taints = [{
      key    = "workload"
      value  = "memory-intensive"
      effect = "NoSchedule"
    }]
    labels = {
      workload = "memory-intensive"
      env      = "prod"
    }
  }
  
  spot = {
    machine_type  = "n2-standard-4"
    min_count     = 0
    max_count     = 30
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
      env      = "prod"
    }
  }
}

# Database configuration (HA for production)
database_version           = "POSTGRES_15"
database_tier             = "db-n1-standard-4"
database_availability_type = "REGIONAL"  # High availability

database_flags = [
  {
    name  = "max_connections"
    value = "500"
  },
  {
    name  = "shared_buffers"
    value = "1GB"
  },
  {
    name  = "effective_cache_size"
    value = "4GB"
  },
  {
    name  = "work_mem"
    value = "16MB"
  },
  {
    name  = "maintenance_work_mem"
    value = "256MB"
  },
  {
    name  = "random_page_cost"
    value = "1.1"
  },
  {
    name  = "effective_io_concurrency"
    value = "200"
  },
  {
    name  = "wal_buffers"
    value = "16MB"
  },
  {
    name  = "default_statistics_target"
    value = "100"
  }
]

# Redis configuration (HA for production)
redis_tier              = "STANDARD_HA"
redis_memory_size_gb    = 5
redis_version          = "REDIS_7_0"
redis_replica_count    = 1
redis_read_replicas_mode = "READ_REPLICAS_ENABLED"

redis_configs = {
  maxmemory-policy = "allkeys-lru"
  notify-keyspace-events = "Ex"
  timeout = "300"
}

# Monitoring
create_monitoring_workspace = true

# Alert policies (comprehensive for production)
alert_policies = {
  high_cpu = {
    display_name = "High CPU Usage"
    conditions = [{
      display_name = "CPU usage above 80%"
      threshold_value = 0.8
      duration = "300s"
    }]
  }
  
  high_memory = {
    display_name = "High Memory Usage"
    conditions = [{
      display_name = "Memory usage above 85%"
      threshold_value = 0.85
      duration = "300s"
    }]
  }
  
  pod_crash_looping = {
    display_name = "Pod Crash Looping"
    conditions = [{
      display_name = "Pod restart rate high"
      threshold_value = 5
      duration = "600s"
    }]
  }
  
  disk_usage = {
    display_name = "High Disk Usage"
    conditions = [{
      display_name = "Disk usage above 90%"
      threshold_value = 0.9
      duration = "300s"
    }]
  }
  
  database_connections = {
    display_name = "High Database Connections"
    conditions = [{
      display_name = "Connection count above 80%"
      threshold_value = 400
      duration = "300s"
    }]
  }
}

# Uptime checks
uptime_checks = {
  main_app = {
    display_name = "Main Application"
    host         = "app.yourdomain.com"
    path         = "/health"
    port         = 443
    use_ssl      = true
    period       = "60s"
  }
  
  api = {
    display_name = "API Endpoint"
    host         = "api.yourdomain.com"
    path         = "/v1/health"
    port         = 443
    use_ssl      = true
    period       = "60s"
  }
}

# Storage classes
storage_classes = {
  fast = {
    is_default           = "false"
    disk_type           = "pd-ssd"
    reclaim_policy      = "Retain"
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
  fast-local = {
    is_default           = "false"
    disk_type           = "pd-ssd"
    reclaim_policy      = "Delete"
    volume_binding_mode = "WaitForFirstConsumer"
    replication_type    = "none"
  }
}