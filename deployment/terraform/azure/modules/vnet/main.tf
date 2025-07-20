# Virtual Network Module - Enterprise networking for Azure

# Virtual Network
resource "azurerm_virtual_network" "main" {
  name                = var.vnet_name
  location            = var.location
  resource_group_name = var.resource_group_name
  address_space       = var.address_space
  
  # DDoS Protection
  dynamic "ddos_protection_plan" {
    for_each = var.enable_ddos_protection ? [1] : []
    content {
      id     = azurerm_network_ddos_protection_plan.main[0].id
      enable = true
    }
  }
  
  tags = var.tags
}

# DDoS Protection Plan
resource "azurerm_network_ddos_protection_plan" "main" {
  count = var.enable_ddos_protection ? 1 : 0
  
  name                = "${var.vnet_name}-ddos"
  location            = var.location
  resource_group_name = var.resource_group_name
  
  tags = var.tags
}

# Subnets
resource "azurerm_subnet" "subnets" {
  for_each = var.subnets
  
  name                 = each.key
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = each.value.address_prefixes
  
  # Service endpoints
  service_endpoints = each.value.service_endpoints
  
  # Delegation
  dynamic "delegation" {
    for_each = each.value.delegation != null ? [each.value.delegation] : []
    content {
      name = delegation.value.name
      
      service_delegation {
        name    = delegation.value.service_delegation.name
        actions = delegation.value.service_delegation.actions
      }
    }
  }
}

# Network Security Groups
resource "azurerm_network_security_group" "nsg" {
  for_each = var.enable_network_security_groups ? var.subnets : {}
  
  name                = "${each.key}-nsg"
  location            = var.location
  resource_group_name = var.resource_group_name
  
  tags = var.tags
}

# Default NSG rules
locals {
  default_nsg_rules = {
    AllowVnetInBound = {
      priority                   = 65000
      direction                  = "Inbound"
      access                     = "Allow"
      protocol                   = "*"
      source_port_range          = "*"
      destination_port_range     = "*"
      source_address_prefix      = "VirtualNetwork"
      destination_address_prefix = "VirtualNetwork"
    }
    AllowAzureLoadBalancerInBound = {
      priority                   = 65001
      direction                  = "Inbound"
      access                     = "Allow"
      protocol                   = "*"
      source_port_range          = "*"
      destination_port_range     = "*"
      source_address_prefix      = "AzureLoadBalancer"
      destination_address_prefix = "*"
    }
    DenyAllInBound = {
      priority                   = 65500
      direction                  = "Inbound"
      access                     = "Deny"
      protocol                   = "*"
      source_port_range          = "*"
      destination_port_range     = "*"
      source_address_prefix      = "*"
      destination_address_prefix = "*"
    }
    AllowVnetOutBound = {
      priority                   = 65000
      direction                  = "Outbound"
      access                     = "Allow"
      protocol                   = "*"
      source_port_range          = "*"
      destination_port_range     = "*"
      source_address_prefix      = "VirtualNetwork"
      destination_address_prefix = "VirtualNetwork"
    }
    AllowInternetOutBound = {
      priority                   = 65001
      direction                  = "Outbound"
      access                     = "Allow"
      protocol                   = "*"
      source_port_range          = "*"
      destination_port_range     = "*"
      source_address_prefix      = "*"
      destination_address_prefix = "Internet"
    }
    DenyAllOutBound = {
      priority                   = 65500
      direction                  = "Outbound"
      access                     = "Deny"
      protocol                   = "*"
      source_port_range          = "*"
      destination_port_range     = "*"
      source_address_prefix      = "*"
      destination_address_prefix = "*"
    }
  }
}

# NSG Rules
resource "azurerm_network_security_rule" "rules" {
  for_each = var.enable_network_security_groups ? {
    for item in flatten([
      for nsg_key, nsg in azurerm_network_security_group.nsg : [
        for rule_key, rule in local.default_nsg_rules : {
          key                        = "${nsg_key}-${rule_key}"
          nsg_name                   = nsg.name
          resource_group_name        = nsg.resource_group_name
          name                       = rule_key
          priority                   = rule.priority
          direction                  = rule.direction
          access                     = rule.access
          protocol                   = rule.protocol
          source_port_range          = rule.source_port_range
          destination_port_range     = rule.destination_port_range
          source_address_prefix      = rule.source_address_prefix
          destination_address_prefix = rule.destination_address_prefix
        }
      ]
    ]) : item.key => item
  } : {}
  
  name                        = each.value.name
  priority                    = each.value.priority
  direction                   = each.value.direction
  access                      = each.value.access
  protocol                    = each.value.protocol
  source_port_range           = each.value.source_port_range
  destination_port_range      = each.value.destination_port_range
  source_address_prefix       = each.value.source_address_prefix
  destination_address_prefix  = each.value.destination_address_prefix
  resource_group_name         = each.value.resource_group_name
  network_security_group_name = each.value.nsg_name
}

# Associate NSGs with Subnets
resource "azurerm_subnet_network_security_group_association" "subnet_nsg" {
  for_each = var.enable_network_security_groups ? var.subnets : {}
  
  subnet_id                 = azurerm_subnet.subnets[each.key].id
  network_security_group_id = azurerm_network_security_group.nsg[each.key].id
}

# NAT Gateway for outbound connectivity
resource "azurerm_public_ip" "nat" {
  count = var.enable_nat_gateway ? 1 : 0
  
  name                = "${var.vnet_name}-nat-pip"
  location            = var.location
  resource_group_name = var.resource_group_name
  allocation_method   = "Static"
  sku                 = "Standard"
  availability_zone   = "Zone-Redundant"
  
  tags = var.tags
}

resource "azurerm_nat_gateway" "main" {
  count = var.enable_nat_gateway ? 1 : 0
  
  name                    = "${var.vnet_name}-nat"
  location                = var.location
  resource_group_name     = var.resource_group_name
  sku_name                = "Standard"
  idle_timeout_in_minutes = 10
  
  tags = var.tags
}

resource "azurerm_nat_gateway_public_ip_association" "main" {
  count = var.enable_nat_gateway ? 1 : 0
  
  nat_gateway_id       = azurerm_nat_gateway.main[0].id
  public_ip_address_id = azurerm_public_ip.nat[0].id
}

# Associate NAT Gateway with subnets
resource "azurerm_subnet_nat_gateway_association" "subnet_nat" {
  for_each = var.enable_nat_gateway ? { for k, v in var.subnets : k => v if contains(var.nat_gateway_subnet_names, k) } : {}
  
  subnet_id      = azurerm_subnet.subnets[each.key].id
  nat_gateway_id = azurerm_nat_gateway.main[0].id
}

# VNet Peering (if needed)
resource "azurerm_virtual_network_peering" "peering" {
  for_each = var.vnet_peerings
  
  name                      = each.key
  resource_group_name       = var.resource_group_name
  virtual_network_name      = azurerm_virtual_network.main.name
  remote_virtual_network_id = each.value.remote_vnet_id
  
  allow_virtual_network_access = each.value.allow_virtual_network_access
  allow_forwarded_traffic      = each.value.allow_forwarded_traffic
  allow_gateway_transit        = each.value.allow_gateway_transit
  use_remote_gateways          = each.value.use_remote_gateways
}