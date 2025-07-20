# Variables for VPC Module

variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The GCP region"
  type        = string
}

variable "network_name" {
  description = "Name of the VPC network"
  type        = string
}

variable "primary_cidr" {
  description = "Primary CIDR range for the subnet"
  type        = string
}

variable "pods_cidr" {
  description = "Secondary CIDR range for Kubernetes pods"
  type        = string
}

variable "services_cidr" {
  description = "Secondary CIDR range for Kubernetes services"
  type        = string
}

variable "enable_flow_logs" {
  description = "Enable VPC flow logs"
  type        = bool
  default     = true
}

variable "enable_private_google_access" {
  description = "Enable private Google access"
  type        = bool
  default     = true
}

variable "enable_cloud_nat" {
  description = "Enable Cloud NAT for outbound internet access"
  type        = bool
  default     = true
}

variable "create_private_dns_zone" {
  description = "Create a private DNS zone"
  type        = bool
  default     = false
}

variable "private_dns_domain" {
  description = "Domain for private DNS zone"
  type        = string
  default     = "internal.local."
}

variable "enable_network_policy" {
  description = "Enable network policy"
  type        = bool
  default     = false
}

variable "labels" {
  description = "Labels to apply to resources"
  type        = map(string)
  default     = {}
}