# Outputs for VNet Module

output "vnet_id" {
  description = "ID of the Virtual Network"
  value       = azurerm_virtual_network.main.id
}

output "vnet_name" {
  description = "Name of the Virtual Network"
  value       = azurerm_virtual_network.main.name
}

output "vnet_address_space" {
  description = "Address space of the Virtual Network"
  value       = azurerm_virtual_network.main.address_space
}

output "subnet_ids" {
  description = "Map of subnet names to IDs"
  value       = {
    for k, v in azurerm_subnet.subnets : k => v.id
  }
}

output "subnet_address_prefixes" {
  description = "Map of subnet names to address prefixes"
  value       = {
    for k, v in azurerm_subnet.subnets : k => v.address_prefixes
  }
}

output "nsg_ids" {
  description = "Map of NSG names to IDs"
  value       = {
    for k, v in azurerm_network_security_group.nsg : k => v.id
  }
}

output "nat_gateway_id" {
  description = "ID of the NAT Gateway"
  value       = var.enable_nat_gateway ? azurerm_nat_gateway.main[0].id : null
}

output "nat_gateway_public_ip" {
  description = "Public IP address of the NAT Gateway"
  value       = var.enable_nat_gateway ? azurerm_public_ip.nat[0].ip_address : null
}