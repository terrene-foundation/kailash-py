# Outputs for GKE Module

output "cluster_id" {
  description = "GKE cluster ID"
  value       = google_container_cluster.primary.id
}

output "cluster_name" {
  description = "GKE cluster name"
  value       = google_container_cluster.primary.name
}

output "location" {
  description = "GKE cluster location"
  value       = google_container_cluster.primary.location
}

output "endpoint" {
  description = "GKE cluster endpoint"
  value       = google_container_cluster.primary.endpoint
  sensitive   = true
}

output "ca_certificate" {
  description = "Cluster CA certificate (base64 encoded)"
  value       = google_container_cluster.primary.master_auth[0].cluster_ca_certificate
  sensitive   = true
}

output "master_version" {
  description = "Current master version"
  value       = google_container_cluster.primary.master_version
}

output "node_pools" {
  description = "Node pool names"
  value       = [for np in google_container_node_pool.node_pools : np.name]
}

output "node_service_account" {
  description = "Service account used by nodes"
  value       = google_service_account.nodes.email
}

output "workload_identity_pool" {
  description = "Workload identity pool"
  value       = "${var.project_id}.svc.id.goog"
}