# Outputs for GCP Infrastructure

# GKE Cluster Outputs
output "cluster_name" {
  description = "Name of the GKE cluster"
  value       = module.gke.cluster_name
}

output "cluster_endpoint" {
  description = "Endpoint for the GKE cluster"
  value       = module.gke.endpoint
  sensitive   = true
}

output "cluster_ca_certificate" {
  description = "Base64 encoded certificate for the cluster"
  value       = module.gke.ca_certificate
  sensitive   = true
}

output "cluster_location" {
  description = "Location of the GKE cluster"
  value       = module.gke.location
}

output "kubectl_config" {
  description = "kubectl config command"
  value       = "gcloud container clusters get-credentials ${module.gke.cluster_name} --location ${module.gke.location} --project ${local.project_id}"
}

# Network Outputs
output "vpc_network_name" {
  description = "Name of the VPC network"
  value       = module.vpc.network_name
}

output "vpc_subnet_name" {
  description = "Name of the VPC subnet"
  value       = module.vpc.subnet_name
}

output "vpc_network_id" {
  description = "ID of the VPC network"
  value       = module.vpc.network_id
}

# Database Outputs
output "cloud_sql_instance_name" {
  description = "Name of the Cloud SQL instance"
  value       = module.cloud_sql.instance_name
}

output "cloud_sql_connection_name" {
  description = "Connection name for the Cloud SQL instance"
  value       = module.cloud_sql.connection_name
}

output "cloud_sql_private_ip" {
  description = "Private IP address of the Cloud SQL instance"
  value       = module.cloud_sql.private_ip_address
}

output "cloud_sql_database_names" {
  description = "Names of the created databases"
  value       = module.cloud_sql.database_names
}

# Redis Outputs
output "redis_host" {
  description = "Hostname of the Redis instance"
  value       = module.memorystore.host
}

output "redis_port" {
  description = "Port of the Redis instance"
  value       = module.memorystore.port
}

output "redis_auth_string" {
  description = "Auth string for Redis connection"
  value       = module.memorystore.auth_string
  sensitive   = true
}

# Storage Outputs
output "gcs_bucket_names" {
  description = "Names of created GCS buckets"
  value       = module.gcs.bucket_names
}

output "gcs_bucket_urls" {
  description = "URLs of created GCS buckets"
  value       = module.gcs.bucket_urls
}

# IAM Outputs
output "workload_identity_service_accounts" {
  description = "Created Workload Identity service accounts"
  value       = module.iam.service_account_emails
}

output "workload_identity_bindings" {
  description = "Workload Identity bindings for Kubernetes service accounts"
  value       = module.iam.workload_identity_bindings
}

# Monitoring Outputs
output "monitoring_workspace_name" {
  description = "Name of the monitoring workspace"
  value       = module.monitoring.workspace_name
}

output "alert_policy_ids" {
  description = "IDs of created alert policies"
  value       = module.monitoring.alert_policy_ids
}

output "uptime_check_ids" {
  description = "IDs of created uptime checks"
  value       = module.monitoring.uptime_check_ids
}

# Kubernetes Resources
output "kubernetes_namespaces" {
  description = "Created Kubernetes namespaces"
  value       = [for ns in kubernetes_namespace.namespaces : ns.metadata[0].name]
}

output "storage_class_names" {
  description = "Created storage class names"
  value       = [for sc in kubernetes_storage_class.storage_classes : sc.metadata[0].name]
}

# Connection Information
output "connection_info" {
  description = "Connection information for various services"
  value = {
    gke_connect = "gcloud container clusters get-credentials ${module.gke.cluster_name} --location ${module.gke.location} --project ${local.project_id}"
    
    postgresql = {
      host     = module.cloud_sql.private_ip_address
      port     = 5432
      database = var.databases[0]
      connection_string = "postgresql://USER:PASSWORD@${module.cloud_sql.private_ip_address}:5432/${var.databases[0]}?sslmode=require"
    }
    
    redis = {
      host = module.memorystore.host
      port = module.memorystore.port
      connection_string = "redis://:AUTH_STRING@${module.memorystore.host}:${module.memorystore.port}"
    }
    
    monitoring = {
      workspace = module.monitoring.workspace_name
      dashboards_url = "https://console.cloud.google.com/monitoring/dashboards?project=${local.project_id}"
    }
  }
  sensitive = true
}

# Important URLs
output "important_urls" {
  description = "Important URLs for accessing resources"
  value = {
    gke_console        = "https://console.cloud.google.com/kubernetes/clusters/details/${module.gke.location}/${module.gke.cluster_name}?project=${local.project_id}"
    cloud_sql_console  = "https://console.cloud.google.com/sql/instances/${module.cloud_sql.instance_name}?project=${local.project_id}"
    redis_console      = "https://console.cloud.google.com/memorystore/redis/instances/${module.memorystore.instance_name}?project=${local.project_id}"
    monitoring_console = "https://console.cloud.google.com/monitoring?project=${local.project_id}"
    logs_console       = "https://console.cloud.google.com/logs?project=${local.project_id}"
    iam_console        = "https://console.cloud.google.com/iam-admin?project=${local.project_id}"
  }
}