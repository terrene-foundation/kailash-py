# AWS EKS Enterprise Deployment - Outputs
# Output values for the Kailash SDK EKS deployment

# Cluster Information
output "cluster_name" {
  description = "Name of the EKS cluster"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "Endpoint for EKS control plane"
  value       = module.eks.cluster_endpoint
}

output "cluster_version" {
  description = "The Kubernetes version for the EKS cluster"
  value       = module.eks.cluster_version
}

output "cluster_platform_version" {
  description = "Platform version for the EKS cluster"
  value       = module.eks.cluster_platform_version
}

output "cluster_status" {
  description = "Status of the EKS cluster"
  value       = module.eks.cluster_status
}

output "cluster_primary_security_group_id" {
  description = "Cluster security group that was created by Amazon EKS for the cluster"
  value       = module.eks.cluster_primary_security_group_id
}

output "cluster_iam_role_arn" {
  description = "IAM role ARN of the EKS cluster"
  value       = module.eks.cluster_iam_role_arn
}

output "cluster_oidc_issuer_url" {
  description = "The URL on the EKS cluster for the OpenID Connect identity provider"
  value       = module.eks.cluster_oidc_issuer_url
}

output "cluster_certificate_authority_data" {
  description = "Base64 encoded certificate data required to communicate with the cluster"
  value       = module.eks.cluster_certificate_authority_data
  sensitive   = true
}

# Node Group Information
output "node_groups" {
  description = "EKS node groups"
  value       = module.eks.eks_managed_node_groups
}

output "node_security_group_id" {
  description = "ID of the node shared security group"
  value       = module.eks.node_security_group_id
}

# Network Information
output "vpc_id" {
  description = "ID of the VPC where the cluster and its nodes will be provisioned"
  value       = module.vpc.vpc_id
}

output "vpc_cidr_block" {
  description = "The CIDR block of the VPC"
  value       = module.vpc.vpc_cidr_block
}

output "private_subnets" {
  description = "List of IDs of private subnets"
  value       = module.vpc.private_subnets
}

output "public_subnets" {
  description = "List of IDs of public subnets"
  value       = module.vpc.public_subnets
}

output "database_subnets" {
  description = "List of IDs of database subnets"
  value       = module.vpc.database_subnets
}

output "nat_gateway_ids" {
  description = "List of IDs of the NAT Gateways"
  value       = module.vpc.natgw_ids
}

# Database Information
output "rds_endpoint" {
  description = "RDS instance endpoint"
  value       = module.rds.db_instance_endpoint
  sensitive   = true
}

output "rds_port" {
  description = "RDS instance port"
  value       = module.rds.db_instance_port
}

output "rds_instance_id" {
  description = "RDS instance ID"
  value       = module.rds.db_instance_id
}

output "rds_instance_arn" {
  description = "RDS instance ARN"
  value       = module.rds.db_instance_arn
}

output "database_name" {
  description = "Name of the database"
  value       = var.db_name
}

output "database_username" {
  description = "Database username"
  value       = var.db_username
  sensitive   = true
}

# Cache Information
output "redis_endpoint" {
  description = "Redis cache cluster endpoint"
  value       = module.elasticache.cache_cluster_address
  sensitive   = true
}

output "redis_port" {
  description = "Redis cache cluster port"
  value       = module.elasticache.cache_cluster_port
}

output "redis_cluster_id" {
  description = "Redis cache cluster ID"
  value       = module.elasticache.cache_cluster_id
}

# Security Information
output "kms_key_arn" {
  description = "The Amazon Resource Name (ARN) of the KMS key"
  value       = module.kms.cluster_key_arn
}

output "kms_key_id" {
  description = "The globally unique identifier for the KMS key"
  value       = module.kms.cluster_key_id
}

# DNS Information
output "route53_zone_id" {
  description = "Route53 zone ID"
  value       = length(module.dns) > 0 ? module.dns[0].zone_id : ""
}

output "route53_zone_name" {
  description = "Route53 zone name"
  value       = var.domain_name
}

# Monitoring Information
output "cloudwatch_log_group_name" {
  description = "Name of CloudWatch log group for EKS cluster logs"
  value       = "/aws/eks/${module.eks.cluster_name}/cluster"
}

# Application URLs
output "application_url" {
  description = "URL to access the application"
  value       = var.domain_name != "" ? "https://${var.domain_name}" : "Use kubectl port-forward to access the application"
}

output "grafana_url" {
  description = "URL to access Grafana dashboard"
  value       = var.domain_name != "" ? "https://grafana.${var.domain_name}" : "Use kubectl port-forward to access Grafana"
}

output "prometheus_url" {
  description = "URL to access Prometheus"
  value       = var.domain_name != "" ? "https://prometheus.${var.domain_name}" : "Use kubectl port-forward to access Prometheus"
}

# kubectl Configuration
output "kubectl_config_command" {
  description = "Command to configure kubectl"
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name}"
}

# Connection Information
output "database_connection_string" {
  description = "Database connection string template"
  value       = "postgresql://${var.db_username}:<password>@${module.rds.db_instance_endpoint}:${module.rds.db_instance_port}/${var.db_name}"
  sensitive   = true
}

output "redis_connection_string" {
  description = "Redis connection string template"
  value       = "redis://${module.elasticache.cache_cluster_address}:${module.elasticache.cache_cluster_port}"
  sensitive   = true
}

# Environment Information
output "environment" {
  description = "Environment name"
  value       = var.environment
}

output "region" {
  description = "AWS region"
  value       = var.aws_region
}

output "availability_zones" {
  description = "List of availability zones used"
  value       = local.azs
}

# Security Groups
output "cluster_security_group_id" {
  description = "Security group ID attached to the EKS cluster"
  value       = module.security.cluster_security_group_id
}

output "rds_security_group_id" {
  description = "Security group ID for RDS"
  value       = module.security.rds_security_group_id
}

output "redis_security_group_id" {
  description = "Security group ID for Redis"
  value       = module.security.redis_security_group_id
}

# Resource ARNs for IRSA
output "cluster_oidc_provider_arn" {
  description = "ARN of the OIDC Provider for IRSA"
  value       = module.eks.oidc_provider_arn
}

# Cost Information
output "estimated_monthly_cost" {
  description = "Estimated monthly cost (approximate)"
  value = {
    eks_cluster = "~$73/month"
    node_groups = "Depends on instance types and count"
    rds        = "Depends on instance class"
    elasticache = "Depends on node type"
    data_transfer = "Depends on usage"
    storage = "Depends on usage"
    load_balancers = "~$22/month per ALB"
    note = "Actual costs may vary based on usage, region, and AWS pricing changes"
  }
}

# Deployment Information
output "deployment_info" {
  description = "Important deployment information"
  value = {
    cluster_name = module.eks.cluster_name
    region      = var.aws_region
    environment = var.environment
    
    next_steps = [
      "1. Configure kubectl: ${local.kubectl_config_command}",
      "2. Verify cluster: kubectl get nodes",
      "3. Deploy application: kubectl apply -f k8s-manifests/",
      "4. Access application: ${local.application_url}",
      "5. Monitor cluster: ${local.grafana_url}"
    ]
    
    important_notes = [
      "Database password is stored in AWS Secrets Manager",
      "All data is encrypted at rest and in transit",
      "Cluster endpoint is ${var.cluster_endpoint_public_access ? "public" : "private"}",
      "Backup retention: ${var.db_backup_retention_period} days"
    ]
  }
}

# Locals for reuse
locals {
  kubectl_config_command = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name}"
  application_url = var.domain_name != "" ? "https://${var.domain_name}" : "Use kubectl port-forward to access the application"
  grafana_url = var.domain_name != "" ? "https://grafana.${var.domain_name}" : "Use kubectl port-forward to access Grafana"
}