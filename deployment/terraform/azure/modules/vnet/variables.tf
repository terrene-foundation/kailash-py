# Variables for VNet Module

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "vnet_name" {
  description = "Name of the Virtual Network"
  type        = string
}

variable "address_space" {
  description = "Address space for the VNet"
  type        = list(string)
}

variable "subnets" {
  description = "Map of subnet configurations"
  type = map(object({
    address_prefixes  = list(string)
    service_endpoints = list(string)
    delegation = optional(object({
      name = string
      service_delegation = object({
        name    = string
        actions = list(string)
      })
    }))
  }))
}

variable "enable_ddos_protection" {
  description = "Enable DDoS protection plan"
  type        = bool
  default     = false
}

variable "enable_network_security_groups" {
  description = "Enable NSGs for subnets"
  type        = bool
  default     = true
}

variable "enable_nat_gateway" {
  description = "Enable NAT Gateway for outbound connectivity"
  type        = bool
  default     = false
}

variable "nat_gateway_subnet_names" {
  description = "Subnet names to associate with NAT Gateway"
  type        = list(string)
  default     = []
}

variable "vnet_peerings" {
  description = "VNet peering configurations"
  type = map(object({
    remote_vnet_id               = string
    allow_virtual_network_access = bool
    allow_forwarded_traffic      = bool
    allow_gateway_transit        = bool
    use_remote_gateways          = bool
  }))
  default = {}
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}