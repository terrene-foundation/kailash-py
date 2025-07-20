# AWS EKS Enterprise Deployment - Variables
# Input variables for configuring the Kailash SDK EKS deployment

# General Configuration
variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-west-2"
}

variable "environment" {
  description = "Environment name (development, staging, production)"
  type        = string
  
  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Environment must be one of: development, staging, production."
  }
}

variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "kailash-sdk"
}

variable "owner" {
  description = "Owner of the infrastructure"
  type        = string
  default     = "platform-team"
}

variable "cost_center" {
  description = "Cost center for billing"
  type        = string
  default     = "engineering"
}

# Network Configuration
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
  
  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "VPC CIDR must be a valid IPv4 CIDR block."
  }
}

variable "enable_vpc_flow_logs" {
  description = "Enable VPC flow logs"
  type        = bool
  default     = true
}

variable "enable_vpc_endpoints" {
  description = "Enable VPC endpoints for AWS services"
  type        = bool
  default     = true
}

# EKS Configuration
variable "kubernetes_version" {
  description = "Kubernetes version for EKS cluster"
  type        = string
  default     = "1.28"
}

variable "cluster_endpoint_public_access" {
  description = "Enable public access to cluster endpoint"
  type        = bool
  default     = false
}

variable "cluster_endpoint_public_access_cidrs" {
  description = "List of CIDR blocks that can access the public cluster endpoint"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "node_groups" {
  description = "EKS node group configurations"
  type = map(object({
    instance_types = list(string)
    capacity_type  = optional(string, "ON_DEMAND")
    scaling_config = object({
      desired_size = number
      max_size     = number
      min_size     = number
    })
    update_config = optional(object({
      max_unavailable_percentage = number
    }), {
      max_unavailable_percentage = 25
    })
    disk_size    = optional(number, 50)
    ami_type     = optional(string, "AL2_x86_64")
    labels       = optional(map(string), {})
    taints       = optional(list(object({
      key    = string
      value  = string
      effect = string
    })), [])
  }))
  
  default = {
    general = {
      instance_types = ["m6i.large"]
      scaling_config = {
        desired_size = 3
        max_size     = 10
        min_size     = 1
      }
      disk_size = 50
      labels = {
        role = "general"
      }
    }
  }
}

variable "enable_irsa" {
  description = "Enable IAM Roles for Service Accounts"
  type        = bool
  default     = true
}

# Database Configuration
variable "postgres_version" {
  description = "PostgreSQL version"
  type        = string
  default     = "15.4"
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.r6g.large"
}

variable "db_allocated_storage" {
  description = "Initial allocated storage for RDS instance (GB)"
  type        = number
  default     = 100
  
  validation {
    condition     = var.db_allocated_storage >= 20
    error_message = "Allocated storage must be at least 20 GB."
  }
}

variable "db_max_allocated_storage" {
  description = "Maximum allocated storage for RDS instance (GB)"
  type        = number
  default     = 1000
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "kailash"
}

variable "db_username" {
  description = "Database username"
  type        = string
  default     = "kailash_user"
}

variable "db_backup_retention_period" {
  description = "Backup retention period in days"
  type        = number
  default     = 7
  
  validation {
    condition     = var.db_backup_retention_period >= 0 && var.db_backup_retention_period <= 35
    error_message = "Backup retention period must be between 0 and 35 days."
  }
}

variable "db_backup_window" {
  description = "Preferred backup window"
  type        = string
  default     = "03:00-04:00"
}

variable "db_maintenance_window" {
  description = "Preferred maintenance window"
  type        = string
  default     = "sun:04:00-sun:05:00"
}

variable "db_multi_az" {
  description = "Enable Multi-AZ deployment for RDS"
  type        = bool
  default     = true
}

variable "enable_performance_insights" {
  description = "Enable Performance Insights for RDS"
  type        = bool
  default     = true
}

# ElastiCache Configuration
variable "redis_version" {
  description = "Redis engine version"
  type        = string
  default     = "7.0"
}

variable "redis_node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.r6g.large"
}

variable "redis_num_cache_nodes" {
  description = "Number of cache nodes"
  type        = number
  default     = 3
  
  validation {
    condition     = var.redis_num_cache_nodes >= 1
    error_message = "Number of cache nodes must be at least 1."
  }
}

variable "redis_snapshot_retention_limit" {
  description = "Number of days for which ElastiCache retains automatic snapshots"
  type        = number
  default     = 5
}

variable "redis_snapshot_window" {
  description = "Daily time range during which automated backups are created"
  type        = string
  default     = "03:00-05:00"
}

variable "redis_maintenance_window" {
  description = "Weekly time range for system maintenance"
  type        = string
  default     = "sun:05:00-sun:09:00"
}

# Security Configuration
variable "enable_aws_config" {
  description = "Enable AWS Config for compliance monitoring"
  type        = bool
  default     = true
}

variable "enable_cloudtrail" {
  description = "Enable CloudTrail for audit logging"
  type        = bool
  default     = true
}

variable "enable_kms_key_rotation" {
  description = "Enable automatic KMS key rotation"
  type        = bool
  default     = true
}

# Monitoring Configuration
variable "enable_container_insights" {
  description = "Enable CloudWatch Container Insights"
  type        = bool
  default     = true
}

variable "enable_prometheus" {
  description = "Enable Prometheus monitoring"
  type        = bool
  default     = true
}

variable "enable_grafana" {
  description = "Enable Grafana dashboards"
  type        = bool
  default     = true
}

variable "sns_topic_arn" {
  description = "SNS topic ARN for alerts"
  type        = string
  default     = ""
}

# DNS Configuration
variable "domain_name" {
  description = "Domain name for the application"
  type        = string
  default     = ""
}

variable "create_route53_zone" {
  description = "Create Route53 hosted zone"
  type        = bool
  default     = false
}

# Add-ons Configuration
variable "enable_cluster_autoscaler" {
  description = "Enable Cluster Autoscaler"
  type        = bool
  default     = true
}

variable "enable_aws_load_balancer_controller" {
  description = "Enable AWS Load Balancer Controller"
  type        = bool
  default     = true
}

variable "enable_external_dns" {
  description = "Enable External DNS"
  type        = bool
  default     = false
}

variable "enable_cert_manager" {
  description = "Enable cert-manager for TLS certificates"
  type        = bool
  default     = true
}

variable "enable_velero" {
  description = "Enable Velero for backup and disaster recovery"
  type        = bool
  default     = true
}

variable "enable_metrics_server" {
  description = "Enable Metrics Server"
  type        = bool
  default     = true
}

variable "enable_ingress_nginx" {
  description = "Enable NGINX Ingress Controller"
  type        = bool
  default     = true
}

# Cost Optimization
variable "enable_spot_instances" {
  description = "Enable spot instances for cost optimization"
  type        = bool
  default     = false
}

variable "spot_allocation_strategy" {
  description = "Strategy for spot instance allocation"
  type        = string
  default     = "diversified"
  
  validation {
    condition     = contains(["lowest-price", "diversified"], var.spot_allocation_strategy)
    error_message = "Spot allocation strategy must be either 'lowest-price' or 'diversified'."
  }
}

# Disaster Recovery
variable "enable_cross_region_backup" {
  description = "Enable cross-region backup"
  type        = bool
  default     = false
}

variable "backup_region" {
  description = "Region for cross-region backup"
  type        = string
  default     = "us-east-1"
}

# Compliance
variable "compliance_framework" {
  description = "Compliance framework to implement (SOC2, HIPAA, PCI-DSS)"
  type        = string
  default     = "SOC2"
  
  validation {
    condition     = contains(["SOC2", "HIPAA", "PCI-DSS", "NONE"], var.compliance_framework)
    error_message = "Compliance framework must be one of: SOC2, HIPAA, PCI-DSS, NONE."
  }
}

variable "enable_encryption_in_transit" {
  description = "Enable encryption in transit for all services"
  type        = bool
  default     = true
}

variable "enable_encryption_at_rest" {
  description = "Enable encryption at rest for all services"
  type        = bool
  default     = true
}

# Application Configuration
variable "application_config" {
  description = "Application-specific configuration"
  type = object({
    replicas = optional(number, 3)
    resources = optional(object({
      requests = object({
        cpu    = string
        memory = string
      })
      limits = object({
        cpu    = string
        memory = string
      })
    }), {
      requests = {
        cpu    = "500m"
        memory = "1Gi"
      }
      limits = {
        cpu    = "2000m"
        memory = "4Gi"
      }
    })
    autoscaling = optional(object({
      enabled                        = bool
      min_replicas                  = number
      max_replicas                  = number
      target_cpu_utilization_percentage = number
    }), {
      enabled                        = true
      min_replicas                  = 3
      max_replicas                  = 20
      target_cpu_utilization_percentage = 70
    })
  })
  
  default = {}
}