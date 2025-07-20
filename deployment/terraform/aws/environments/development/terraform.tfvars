# Development Environment Configuration
# Optimized for development workloads with cost efficiency

# General Configuration
aws_region   = "us-west-2"
environment  = "development"
project_name = "kailash-sdk"
owner        = "dev-team"
cost_center  = "engineering"

# Network Configuration
vpc_cidr                = "10.10.0.0/16"
enable_vpc_flow_logs    = false  # Disabled for cost savings
enable_vpc_endpoints    = false  # Disabled for cost savings

# EKS Configuration
kubernetes_version                   = "1.28"
cluster_endpoint_public_access       = true   # Allow public access for dev
cluster_endpoint_public_access_cidrs = ["0.0.0.0/0"]

# Node Groups - Single, smaller node group for dev
node_groups = {
  dev = {
    instance_types = ["t3.medium"]
    capacity_type  = "SPOT"  # Use spot for cost savings
    scaling_config = {
      desired_size = 1
      max_size     = 3
      min_size     = 1
    }
    disk_size = 30  # Smaller disk for dev
    labels = {
      role = "dev"
      tier = "development"
    }
  }
}

enable_irsa = true

# Database Configuration - Smaller for development
postgres_version             = "15.4"
db_instance_class           = "db.t3.micro"
db_allocated_storage        = 20
db_max_allocated_storage    = 100
db_name                     = "kailash_dev"
db_username                 = "kailash_dev_user"
db_backup_retention_period  = 1   # Minimal backup for dev
db_backup_window           = "03:00-04:00"
db_maintenance_window      = "sun:04:00-sun:05:00"
db_multi_az                = false # Single AZ for dev
enable_performance_insights = false # Disabled for cost savings

# ElastiCache Configuration - Single node for development
redis_version                   = "7.0"
redis_node_type                = "cache.t4g.micro"
redis_num_cache_nodes          = 1
redis_snapshot_retention_limit = 1
redis_snapshot_window          = "03:00-05:00"
redis_maintenance_window       = "sun:05:00-sun:09:00"

# Security Configuration - Relaxed for development
enable_aws_config         = false  # Disabled for cost savings
enable_cloudtrail         = false  # Disabled for cost savings
enable_kms_key_rotation    = false  # Disabled for dev
compliance_framework       = "NONE"
enable_encryption_in_transit = true
enable_encryption_at_rest    = true

# Monitoring Configuration - Basic monitoring
enable_container_insights = false  # Disabled for cost savings
enable_prometheus        = true
enable_grafana          = true

# DNS Configuration - No custom domain for dev
domain_name         = ""
create_route53_zone = false

# Add-ons Configuration - Essential only
enable_cluster_autoscaler          = true
enable_aws_load_balancer_controller = true
enable_external_dns               = false
enable_cert_manager               = false
enable_velero                     = false
enable_metrics_server             = true
enable_ingress_nginx              = true

# Cost Optimization - Max savings for dev
enable_spot_instances      = true
spot_allocation_strategy   = "lowest-price"

# Disaster Recovery - Minimal for dev
enable_cross_region_backup = false

# Application Configuration - Minimal resources for dev
application_config = {
  replicas = 1
  
  resources = {
    requests = {
      cpu    = "250m"
      memory = "512Mi"
    }
    limits = {
      cpu    = "1000m"
      memory = "2Gi"
    }
  }
  
  autoscaling = {
    enabled                          = false  # Disabled for dev
    min_replicas                    = 1
    max_replicas                    = 3
    target_cpu_utilization_percentage = 80
  }
}