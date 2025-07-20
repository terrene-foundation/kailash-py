# GKE Cluster Module - Enterprise-grade Kubernetes on Google Cloud

locals {
  cluster_type = var.regional ? "regional" : "zonal"
}

# GKE Cluster
resource "google_container_cluster" "primary" {
  name     = var.cluster_name
  location = var.location
  project  = var.project_id

  # Network configuration
  network    = var.network
  subnetwork = var.subnetwork

  # We can't create a cluster with no node pool defined, but we want to only use
  # separately managed node pools. So we create the smallest possible default
  # node pool and immediately delete it.
  remove_default_node_pool = true
  initial_node_count       = 1

  # Cluster configuration
  min_master_version = var.kubernetes_version
  release_channel {
    channel = var.release_channel
  }

  # Network security
  private_cluster_config {
    enable_private_nodes    = var.enable_private_nodes
    enable_private_endpoint = var.enable_private_endpoint
    master_ipv4_cidr_block  = var.master_ipv4_cidr_block
  }

  dynamic "master_authorized_networks_config" {
    for_each = length(var.master_authorized_networks) > 0 ? [1] : []
    content {
      dynamic "cidr_blocks" {
        for_each = var.master_authorized_networks
        content {
          display_name = cidr_blocks.value.display_name
          cidr_block   = cidr_blocks.value.cidr_block
        }
      }
    }
  }

  # IP allocation policy for VPC-native cluster
  ip_allocation_policy {
    cluster_secondary_range_name  = var.pods_range
    services_secondary_range_name = var.services_range
  }

  # Security features
  enable_shielded_nodes = var.enable_shielded_nodes
  
  dynamic "binary_authorization" {
    for_each = var.enable_binary_authorization ? [1] : []
    content {
      evaluation_mode = "PROJECT_SINGLETON_POLICY_ENFORCE"
    }
  }

  # Workload Identity
  workload_identity_config {
    workload_pool = var.enable_workload_identity ? "${var.project_id}.svc.id.goog" : null
  }

  # Cluster autoscaling
  dynamic "cluster_autoscaling" {
    for_each = var.enable_cluster_autoscaling ? [var.cluster_autoscaling_config] : []
    content {
      enabled = true
      resource_limits {
        resource_type = "cpu"
        minimum       = cluster_autoscaling.value.min_cpu_cores
        maximum       = cluster_autoscaling.value.max_cpu_cores
      }
      resource_limits {
        resource_type = "memory"
        minimum       = cluster_autoscaling.value.min_memory_gb
        maximum       = cluster_autoscaling.value.max_memory_gb
      }
      auto_provisioning_defaults {
        disk_size = 100
        disk_type = "pd-standard"
        oauth_scopes = [
          "https://www.googleapis.com/auth/compute",
          "https://www.googleapis.com/auth/devstorage.read_only",
          "https://www.googleapis.com/auth/logging.write",
          "https://www.googleapis.com/auth/monitoring",
          "https://www.googleapis.com/auth/servicecontrol",
          "https://www.googleapis.com/auth/service.management.readonly",
          "https://www.googleapis.com/auth/trace.append",
        ]
        service_account = google_service_account.nodes.email
        
        shielded_instance_config {
          enable_secure_boot          = true
          enable_integrity_monitoring = true
        }
      }
    }
  }

  # Addons configuration
  addons_config {
    horizontal_pod_autoscaling {
      disabled = !var.enable_horizontal_pod_autoscaling
    }
    
    vertical_pod_autoscaling {
      enabled = var.enable_vertical_pod_autoscaling
    }
    
    http_load_balancing {
      disabled = false
    }
    
    network_policy_config {
      disabled = false
    }
    
    dns_cache_config {
      enabled = true
    }
    
    gce_persistent_disk_csi_driver_config {
      enabled = true
    }
    
    gcp_filestore_csi_driver_config {
      enabled = true
    }
  }

  # Monitoring and logging
  monitoring_config {
    enable_components = var.monitoring_config
    
    managed_prometheus {
      enabled = true
    }
  }
  
  logging_config {
    enable_components = var.logging_config
  }

  # Maintenance window
  maintenance_policy {
    recurring_window {
      start_time = var.maintenance_window.start_time
      end_time   = var.maintenance_window.end_time
      recurrence = var.maintenance_window.recurrence
    }
  }

  # Database encryption
  database_encryption {
    state    = var.database_encryption_state
    key_name = var.database_encryption_key_name
  }

  # Resource labels
  resource_labels = var.labels

  # Notification config for cluster upgrades
  notification_config {
    pubsub {
      enabled = var.enable_upgrade_notifications
      topic   = var.upgrade_notification_topic
    }
  }

  # Cost management
  cost_management_config {
    enabled = var.enable_cost_management
  }

  lifecycle {
    ignore_changes = [
      # Ignore changes to node count (managed by autoscaler)
      initial_node_count,
    ]
  }
}

# Service account for nodes
resource "google_service_account" "nodes" {
  account_id   = "${var.cluster_name}-nodes"
  display_name = "GKE nodes service account for ${var.cluster_name}"
  project      = var.project_id
}

# IAM roles for node service account
resource "google_project_iam_member" "node_service_account_roles" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/monitoring.viewer",
    "roles/stackdriver.resourceMetadata.writer",
    "roles/artifactregistry.reader",
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.nodes.email}"
}

# Node pools
resource "google_container_node_pool" "node_pools" {
  for_each = var.node_pools

  name     = each.key
  location = var.regional ? var.location : var.zones[0]
  cluster  = google_container_cluster.primary.name
  project  = var.project_id

  # Node count and autoscaling
  initial_node_count = each.value.initial_count
  
  autoscaling {
    min_node_count = each.value.min_count
    max_node_count = each.value.max_count
  }

  # Node configuration
  node_config {
    machine_type = each.value.machine_type
    disk_size_gb = each.value.disk_size_gb
    disk_type    = each.value.disk_type
    
    # Use spot instances if specified
    dynamic "spot" {
      for_each = each.value.spot ? [1] : []
      content {
      }
    }
    
    preemptible = each.value.preemptible

    # Service account
    service_account = google_service_account.nodes.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    # Security
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    # Workload identity
    workload_metadata_config {
      mode = var.enable_workload_identity ? "GKE_METADATA" : "MODE_UNSPECIFIED"
    }

    # Labels
    labels = merge(var.labels, each.value.labels, {
      node_pool = each.key
    })

    # Taints
    dynamic "taint" {
      for_each = each.value.taints
      content {
        key    = taint.value.key
        value  = taint.value.value
        effect = taint.value.effect
      }
    }

    # Metadata
    metadata = {
      disable-legacy-endpoints = "true"
    }

    # Linux node config
    linux_node_config {
      sysctls = {
        "net.ipv4.tcp_keepalive_time"    = "120"
        "net.ipv4.tcp_keepalive_intvl"   = "30"
        "net.ipv4.tcp_keepalive_probes"  = "8"
        "net.core.netdev_max_backlog"    = "5000"
        "net.ipv4.tcp_congestion_control" = "bbr"
      }
    }

    # Guest accelerators (GPUs)
    dynamic "guest_accelerator" {
      for_each = lookup(each.value, "accelerators", [])
      content {
        type  = guest_accelerator.value.type
        count = guest_accelerator.value.count
      }
    }
  }

  # Management
  management {
    auto_repair  = each.value.auto_repair
    auto_upgrade = each.value.auto_upgrade
  }

  # Upgrade settings
  upgrade_settings {
    max_surge       = lookup(each.value, "max_surge", 1)
    max_unavailable = lookup(each.value, "max_unavailable", 0)
    strategy        = lookup(each.value, "upgrade_strategy", "SURGE")
  }

  # Node locations (for regional clusters)
  dynamic "node_locations" {
    for_each = var.regional ? [1] : []
    content {
      locations = var.zones
    }
  }

  lifecycle {
    create_before_destroy = true
    ignore_changes        = [initial_node_count]
  }
}