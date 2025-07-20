# Outputs for VPC Module

output "network_name" {
  description = "Name of the VPC network"
  value       = google_compute_network.vpc.name
}

output "network_id" {
  description = "ID of the VPC network"
  value       = google_compute_network.vpc.id
}

output "network_self_link" {
  description = "Self link of the VPC network"
  value       = google_compute_network.vpc.self_link
}

output "subnet_name" {
  description = "Name of the subnet"
  value       = google_compute_subnetwork.subnet.name
}

output "subnet_id" {
  description = "ID of the subnet"
  value       = google_compute_subnetwork.subnet.id
}

output "subnet_self_link" {
  description = "Self link of the subnet"
  value       = google_compute_subnetwork.subnet.self_link
}

output "subnet_cidr" {
  description = "CIDR range of the subnet"
  value       = google_compute_subnetwork.subnet.ip_cidr_range
}

output "pods_range_name" {
  description = "Name of the pods secondary range"
  value       = google_compute_subnetwork.subnet.secondary_ip_range[0].range_name
}

output "services_range_name" {
  description = "Name of the services secondary range"
  value       = google_compute_subnetwork.subnet.secondary_ip_range[1].range_name
}

output "router_name" {
  description = "Name of the Cloud Router"
  value       = var.enable_cloud_nat ? google_compute_router.router[0].name : null
}

output "nat_name" {
  description = "Name of the Cloud NAT"
  value       = var.enable_cloud_nat ? google_compute_router_nat.nat[0].name : null
}

output "private_service_connection_ip" {
  description = "IP address for private service connection"
  value       = google_compute_global_address.private_service_connection.address
}