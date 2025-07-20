# AWS EKS Enterprise Deployment - Main Configuration
# This configuration creates a production-ready EKS cluster with complete networking,
# security, and monitoring capabilities for the Kailash SDK Template

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.20"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.10"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.1"
    }
  }

  # Backend configuration for state management
  backend "s3" {
    # bucket = "your-terraform-state-bucket"
    # key    = "kailash/terraform.tfstate"
    # region = "us-west-2"
    # 
    # dynamodb_table = "terraform-locks"
    # encrypt        = true
  }
}

# Configure AWS Provider
provider "aws" {
  region = var.aws_region
  
  default_tags {
    tags = {
      Environment   = var.environment
      Project       = var.project_name
      ManagedBy     = "terraform"
      Application   = "kailash-sdk"
      Owner         = var.owner
      CostCenter    = var.cost_center
    }
  }
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_availability_zones" "available" {
  state = "available"
}

# Random suffix for unique resource names
resource "random_string" "suffix" {
  length  = 8
  special = false
  upper   = false
}

# Local values
locals {
  cluster_name = "${var.project_name}-${var.environment}-${random_string.suffix.result}"
  
  common_tags = {
    Environment = var.environment
    Project     = var.project_name
    Owner       = var.owner
    ManagedBy   = "terraform"
  }

  # VPC Configuration
  vpc_cidr = var.vpc_cidr
  azs      = slice(data.aws_availability_zones.available.names, 0, 3)
  
  private_subnets = [
    cidrsubnet(local.vpc_cidr, 8, 1),
    cidrsubnet(local.vpc_cidr, 8, 2),
    cidrsubnet(local.vpc_cidr, 8, 3)
  ]
  
  public_subnets = [
    cidrsubnet(local.vpc_cidr, 8, 101),
    cidrsubnet(local.vpc_cidr, 8, 102),
    cidrsubnet(local.vpc_cidr, 8, 103)
  ]
  
  database_subnets = [
    cidrsubnet(local.vpc_cidr, 8, 201),
    cidrsubnet(local.vpc_cidr, 8, 202),
    cidrsubnet(local.vpc_cidr, 8, 203)
  ]
}

# VPC Module
module "vpc" {
  source = "./modules/vpc"
  
  name = "${local.cluster_name}-vpc"
  cidr = local.vpc_cidr
  
  azs              = local.azs
  private_subnets  = local.private_subnets
  public_subnets   = local.public_subnets
  database_subnets = local.database_subnets
  
  enable_nat_gateway   = true
  enable_vpn_gateway   = false
  enable_dns_hostnames = true
  enable_dns_support   = true
  
  # VPC Flow Logs
  enable_flow_log                      = var.enable_vpc_flow_logs
  create_flow_log_cloudwatch_log_group = var.enable_vpc_flow_logs
  create_flow_log_cloudwatch_iam_role  = var.enable_vpc_flow_logs
  
  # VPC Endpoints
  enable_s3_endpoint       = var.enable_vpc_endpoints
  enable_ec2_endpoint      = var.enable_vpc_endpoints
  enable_ecr_api_endpoint  = var.enable_vpc_endpoints
  enable_ecr_dkr_endpoint  = var.enable_vpc_endpoints
  
  public_subnet_tags = {
    "kubernetes.io/role/elb" = "1"
    "kubernetes.io/cluster/${local.cluster_name}" = "owned"
  }
  
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = "1"
    "kubernetes.io/cluster/${local.cluster_name}" = "owned"
  }
  
  tags = local.common_tags
}

# Security Module
module "security" {
  source = "./modules/security"
  
  vpc_id               = module.vpc.vpc_id
  cluster_name         = local.cluster_name
  worker_node_subnets  = module.vpc.private_subnets
  
  # Enable AWS Config and CloudTrail
  enable_config     = var.enable_aws_config
  enable_cloudtrail = var.enable_cloudtrail
  
  tags = local.common_tags
}

# KMS Module for encryption
module "kms" {
  source = "./modules/kms"
  
  cluster_name = local.cluster_name
  environment  = var.environment
  
  enable_key_rotation = var.enable_kms_key_rotation
  
  tags = local.common_tags
}

# EKS Module
module "eks" {
  source = "./modules/eks"
  
  cluster_name    = local.cluster_name
  cluster_version = var.kubernetes_version
  
  vpc_id                   = module.vpc.vpc_id
  subnet_ids               = module.vpc.private_subnets
  control_plane_subnet_ids = module.vpc.public_subnets
  
  # Security
  cluster_security_group_id = module.security.cluster_security_group_id
  node_security_group_id    = module.security.node_security_group_id
  
  # Encryption
  cluster_encryption_config = [
    {
      provider_key_arn = module.kms.cluster_key_arn
      resources        = ["secrets"]
    }
  ]
  
  # Node Groups
  node_groups = var.node_groups
  
  # Add-ons
  cluster_addons = {
    coredns = {
      most_recent = true
    }
    kube-proxy = {
      most_recent = true
    }
    vpc-cni = {
      most_recent = true
    }
    aws-ebs-csi-driver = {
      most_recent = true
    }
  }
  
  # IRSA
  enable_irsa = var.enable_irsa
  
  # Cluster endpoint configuration
  cluster_endpoint_private_access = true
  cluster_endpoint_public_access  = var.cluster_endpoint_public_access
  cluster_endpoint_public_access_cidrs = var.cluster_endpoint_public_access_cidrs
  
  # Logging
  cluster_enabled_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
  
  tags = local.common_tags
}

# RDS Module
module "rds" {
  source = "./modules/rds"
  
  identifier = "${local.cluster_name}-postgres"
  
  engine         = "postgres"
  engine_version = var.postgres_version
  instance_class = var.db_instance_class
  
  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_encrypted     = true
  kms_key_id           = module.kms.rds_key_arn
  
  db_name  = var.db_name
  username = var.db_username
  port     = 5432
  
  vpc_security_group_ids = [module.security.rds_security_group_id]
  db_subnet_group_name   = module.vpc.database_subnet_group
  
  backup_retention_period = var.db_backup_retention_period
  backup_window          = var.db_backup_window
  maintenance_window     = var.db_maintenance_window
  
  # High Availability
  multi_az               = var.db_multi_az
  deletion_protection    = var.environment == "production" ? true : false
  
  # Monitoring
  monitoring_interval = 60
  monitoring_role_arn = module.security.rds_monitoring_role_arn
  
  # Performance Insights
  performance_insights_enabled = var.enable_performance_insights
  performance_insights_kms_key_id = module.kms.rds_key_arn
  
  tags = local.common_tags
}

# ElastiCache Module
module "elasticache" {
  source = "./modules/elasticache"
  
  cluster_id      = "${local.cluster_name}-redis"
  engine          = "redis"
  engine_version  = var.redis_version
  node_type       = var.redis_node_type
  num_cache_nodes = var.redis_num_cache_nodes
  port            = 6379
  
  subnet_group_name  = module.vpc.elasticache_subnet_group_name
  security_group_ids = [module.security.redis_security_group_id]
  
  # Encryption
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  kms_key_id                 = module.kms.elasticache_key_arn
  
  # Backup
  snapshot_retention_limit = var.redis_snapshot_retention_limit
  snapshot_window         = var.redis_snapshot_window
  
  # Maintenance
  maintenance_window = var.redis_maintenance_window
  
  tags = local.common_tags
}

# Monitoring Module
module "monitoring" {
  source = "./modules/monitoring"
  
  cluster_name = local.cluster_name
  environment  = var.environment
  
  # CloudWatch Container Insights
  enable_container_insights = var.enable_container_insights
  
  # Prometheus & Grafana
  enable_prometheus = var.enable_prometheus
  enable_grafana    = var.enable_grafana
  
  # Alerting
  sns_topic_arn = var.sns_topic_arn
  
  tags = local.common_tags
}

# DNS Module (Route53)
module "dns" {
  source = "./modules/dns"
  count  = var.domain_name != "" ? 1 : 0
  
  domain_name         = var.domain_name
  create_route53_zone = var.create_route53_zone
  
  # ALB for ingress
  alb_dns_name    = module.eks.cluster_primary_security_group_id # This will be replaced with actual ALB
  alb_zone_id     = "Z1D633PJN98FT9" # US West 2 ALB zone ID
  
  tags = local.common_tags
}

# Kubernetes provider configuration
provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
  
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", local.cluster_name]
  }
}

# Helm provider configuration
provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
    
    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", local.cluster_name]
    }
  }
}

# Essential Kubernetes resources
resource "kubernetes_namespace" "kailash_system" {
  metadata {
    name = "kailash-system"
    
    labels = {
      name = "kailash-system"
    }
  }
  
  depends_on = [module.eks]
}

resource "kubernetes_namespace" "monitoring" {
  metadata {
    name = "monitoring"
    
    labels = {
      name = "monitoring"
    }
  }
  
  depends_on = [module.eks]
}