# Outputs for Azure Infrastructure

# Resource Group
output "resource_group_name" {
  description = "Name of the resource group"
  value       = azurerm_resource_group.main.name
}

output "resource_group_location" {
  description = "Location of the resource group"
  value       = azurerm_resource_group.main.location
}

# AKS Outputs
output "aks_cluster_name" {
  description = "Name of the AKS cluster"
  value       = module.aks.cluster_name
}

output "aks_cluster_id" {
  description = "ID of the AKS cluster"
  value       = module.aks.cluster_id
}

output "aks_cluster_fqdn" {
  description = "FQDN of the AKS cluster"
  value       = module.aks.cluster_fqdn
  sensitive   = true
}

output "aks_node_resource_group" {
  description = "Resource group containing AKS nodes"
  value       = module.aks.node_resource_group
}

output "kubectl_config_command" {
  description = "Command to configure kubectl"
  value       = "az aks get-credentials --resource-group ${azurerm_resource_group.main.name} --name ${module.aks.cluster_name}"
}

# Network Outputs
output "vnet_id" {
  description = "ID of the Virtual Network"
  value       = module.vnet.vnet_id
}

output "vnet_name" {
  description = "Name of the Virtual Network"
  value       = module.vnet.vnet_name
}

output "subnet_ids" {
  description = "Map of subnet names to IDs"
  value       = module.vnet.subnet_ids
}

# PostgreSQL Outputs
output "postgresql_server_name" {
  description = "Name of the PostgreSQL server"
  value       = module.postgresql.server_name
}

output "postgresql_server_fqdn" {
  description = "FQDN of the PostgreSQL server"
  value       = module.postgresql.fqdn
}

output "postgresql_database_names" {
  description = "Names of the PostgreSQL databases"
  value       = module.postgresql.database_names
}

output "postgresql_connection_string" {
  description = "PostgreSQL connection string template"
  value       = "postgresql://USERNAME:PASSWORD@${module.postgresql.fqdn}:5432/kailash?sslmode=require"
  sensitive   = true
}

# Redis Outputs
output "redis_hostname" {
  description = "Hostname of the Redis cache"
  value       = module.redis.hostname
}

output "redis_port" {
  description = "Port of the Redis cache"
  value       = module.redis.ssl_port
}

output "redis_primary_connection_string" {
  description = "Primary connection string for Redis"
  value       = module.redis.primary_connection_string
  sensitive   = true
}

# Storage Outputs
output "storage_account_names" {
  description = "Names of the storage accounts"
  value       = module.storage.storage_account_names
}

output "storage_primary_endpoints" {
  description = "Primary endpoints for storage accounts"
  value       = module.storage.primary_endpoints
}

output "storage_container_names" {
  description = "Names of storage containers"
  value       = module.storage.container_names
}

# Key Vault Outputs
output "key_vault_name" {
  description = "Name of the Key Vault"
  value       = azurerm_key_vault.main.name
}

output "key_vault_uri" {
  description = "URI of the Key Vault"
  value       = azurerm_key_vault.main.vault_uri
}

# Container Registry Outputs
output "acr_name" {
  description = "Name of the Container Registry"
  value       = azurerm_container_registry.main.name
}

output "acr_login_server" {
  description = "Login server for the Container Registry"
  value       = azurerm_container_registry.main.login_server
}

# Log Analytics Outputs
output "log_analytics_workspace_id" {
  description = "ID of the Log Analytics workspace"
  value       = azurerm_log_analytics_workspace.main.id
}

output "log_analytics_workspace_name" {
  description = "Name of the Log Analytics workspace"
  value       = azurerm_log_analytics_workspace.main.name
}

# Monitoring Outputs
output "application_insights_name" {
  description = "Name of Application Insights"
  value       = var.create_application_insights ? module.monitoring.application_insights_name : null
}

output "application_insights_instrumentation_key" {
  description = "Instrumentation key for Application Insights"
  value       = var.create_application_insights ? module.monitoring.instrumentation_key : null
  sensitive   = true
}

output "application_insights_connection_string" {
  description = "Connection string for Application Insights"
  value       = var.create_application_insights ? module.monitoring.connection_string : null
  sensitive   = true
}

# Connection Information
output "connection_info" {
  description = "Connection information for various services"
  value = {
    aks_connect = "az aks get-credentials --resource-group ${azurerm_resource_group.main.name} --name ${module.aks.cluster_name}"
    
    postgresql = {
      host     = module.postgresql.fqdn
      port     = 5432
      database = "kailash"
      ssl_mode = "require"
    }
    
    redis = {
      host = module.redis.hostname
      port = module.redis.ssl_port
      ssl  = true
    }
    
    storage = {
      account_name = module.storage.storage_account_names[0]
      containers   = module.storage.container_names
    }
    
    acr = {
      login_server = azurerm_container_registry.main.login_server
      login_command = "az acr login --name ${azurerm_container_registry.main.name}"
    }
    
    key_vault = {
      name = azurerm_key_vault.main.name
      uri  = azurerm_key_vault.main.vault_uri
    }
  }
  sensitive = true
}

# Important URLs
output "important_urls" {
  description = "Important URLs for accessing resources"
  value = {
    azure_portal = "https://portal.azure.com/#@${data.azurerm_client_config.current.tenant_id}/resource${azurerm_resource_group.main.id}"
    aks_portal   = "https://portal.azure.com/#@${data.azurerm_client_config.current.tenant_id}/resource${module.aks.cluster_id}"
    acr_portal   = "https://portal.azure.com/#@${data.azurerm_client_config.current.tenant_id}/resource${azurerm_container_registry.main.id}"
    monitoring   = "https://portal.azure.com/#@${data.azurerm_client_config.current.tenant_id}/resource${azurerm_log_analytics_workspace.main.id}"
  }
}

# Kubernetes Configuration
output "kube_config" {
  description = "Kubernetes configuration"
  value       = module.aks.kube_config_raw
  sensitive   = true
}

output "kubernetes_namespaces" {
  description = "Created Kubernetes namespaces"
  value       = [for ns in kubernetes_namespace.namespaces : ns.metadata[0].name]
}

output "storage_class_names" {
  description = "Created storage class names"
  value       = [for sc in kubernetes_storage_class.storage_classes : sc.metadata[0].name]
}