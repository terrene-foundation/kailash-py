# VPC Network Module - Enterprise networking for GCP

# VPC Network
resource "google_compute_network" "vpc" {
  name                            = var.network_name
  project                         = var.project_id
  auto_create_subnetworks         = false
  routing_mode                    = "REGIONAL"
  delete_default_routes_on_create = false
  
  description = "VPC network for ${var.network_name}"
}

# Primary subnet
resource "google_compute_subnetwork" "subnet" {
  name          = "${var.network_name}-subnet"
  project       = var.project_id
  region        = var.region
  network       = google_compute_network.vpc.self_link
  ip_cidr_range = var.primary_cidr

  # Secondary ranges for GKE
  secondary_ip_range {
    range_name    = "${var.network_name}-pods"
    ip_cidr_range = var.pods_cidr
  }

  secondary_ip_range {
    range_name    = "${var.network_name}-services"
    ip_cidr_range = var.services_cidr
  }

  # Enable VPC flow logs
  dynamic "log_config" {
    for_each = var.enable_flow_logs ? [1] : []
    content {
      aggregation_interval = "INTERVAL_5_SEC"
      flow_sampling        = 0.5
      metadata             = "INCLUDE_ALL_METADATA"
    }
  }

  # Enable private Google access
  private_ip_google_access = var.enable_private_google_access

  description = "Primary subnet for ${var.network_name}"
}

# Cloud Router for NAT
resource "google_compute_router" "router" {
  count = var.enable_cloud_nat ? 1 : 0

  name    = "${var.network_name}-router"
  project = var.project_id
  region  = var.region
  network = google_compute_network.vpc.self_link

  bgp {
    asn = 64514
  }
}

# Cloud NAT for outbound internet access
resource "google_compute_router_nat" "nat" {
  count = var.enable_cloud_nat ? 1 : 0

  name                               = "${var.network_name}-nat"
  project                            = var.project_id
  router                             = google_compute_router.router[0].name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

# Firewall rules
# Allow internal communication
resource "google_compute_firewall" "internal" {
  name    = "${var.network_name}-allow-internal"
  project = var.project_id
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "icmp"
  }

  source_ranges = [
    var.primary_cidr,
    var.pods_cidr,
    var.services_cidr
  ]

  priority = 1000
}

# Allow health checks
resource "google_compute_firewall" "health_checks" {
  name    = "${var.network_name}-allow-health-checks"
  project = var.project_id
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
  }

  source_ranges = [
    "35.191.0.0/16",  # Google health check IPs
    "130.211.0.0/22"  # Google health check IPs
  ]

  target_tags = ["allow-health-checks"]
  priority    = 1000
}

# Private Service Connection for managed services
resource "google_compute_global_address" "private_service_connection" {
  name          = "${var.network_name}-private-service-connection"
  project       = var.project_id
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.self_link
}

resource "google_service_networking_connection" "private_service_connection" {
  network                 = google_compute_network.vpc.self_link
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_service_connection.name]
}

# DNS configuration
resource "google_dns_managed_zone" "private" {
  count = var.create_private_dns_zone ? 1 : 0

  name        = "${var.network_name}-private-zone"
  project     = var.project_id
  dns_name    = var.private_dns_domain
  description = "Private DNS zone for ${var.network_name}"
  visibility  = "private"

  private_visibility_config {
    networks {
      network_url = google_compute_network.vpc.self_link
    }
  }
}

# Network policies
resource "google_compute_network_policy" "policy" {
  count = var.enable_network_policy ? 1 : 0

  name    = "${var.network_name}-policy"
  project = var.project_id
  network = google_compute_network.vpc.self_link

  description = "Network policy for ${var.network_name}"
}