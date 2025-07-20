# Azure AKS Terraform Infrastructure

This directory contains enterprise-grade Terraform modules for deploying the Kailash SDK Template on Azure with AKS (Azure Kubernetes Service).

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Resource Group                            │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐     ┌──────────────┐    ┌──────────────┐ │
│  │  Virtual Network │     │ NAT Gateway  │    │ DDoS Plan    │ │
│  │   10.0.0.0/16    │────▶│              │    │ (Optional)   │ │
│  └─────────────────┘     └──────────────┘    └──────────────┘ │
│           │                                                      │
│  ┌────────┴────────┐                                           │
│  │     Subnets     │                                           │
│  ├─────────────────┤                                           │
│  │ AKS Nodes       │                                           │
│  │ Internal LB     │                                           │
│  │ App Gateway     │                                           │
│  │ PostgreSQL      │                                           │
│  └─────────────────┘                                           │
│           │                                                      │
│  ┌────────┴────────────────────────────────┐                  │
│  │            AKS Cluster                   │                  │
│  ├──────────────────────────────────────────┤                  │
│  │ ┌──────────┐ ┌──────────┐ ┌──────────┐ │                  │
│  │ │  System  │ │ General  │ │   Spot   │ │                  │
│  │ │   Pool   │ │   Pool   │ │   Pool   │ │                  │
│  │ └──────────┘ └──────────┘ └──────────┘ │                  │
│  └──────────────────────────────────────────┘                  │
│           │                                                      │
│  ┌────────┴────────┐    ┌─────────────┐    ┌────────────────┐ │
│  │ Azure Database  │    │ Azure Cache │    │ Storage Account│ │
│  │ for PostgreSQL  │    │  for Redis  │    │                │ │
│  └─────────────────┘    └─────────────┘    └────────────────┘ │
│                                                                  │
│  ┌─────────────────┐    ┌─────────────┐    ┌────────────────┐ │
│  │   Key Vault     │    │     ACR     │    │ Log Analytics  │ │
│  └─────────────────┘    └─────────────┘    └────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## 📁 Module Structure

```
azure/
├── main.tf                    # Root module configuration
├── variables.tf               # Input variables
├── outputs.tf                 # Output values
├── versions.tf               # Provider requirements
├── README.md                 # This file
├── environments/             # Environment-specific configurations
│   ├── dev.tfvars
│   ├── staging.tfvars
│   └── prod.tfvars
└── modules/                  # Reusable modules
    ├── vnet/                 # Virtual Network
    ├── aks/                  # AKS cluster
    ├── postgresql/           # Azure Database for PostgreSQL
    ├── redis/                # Azure Cache for Redis
    ├── storage/              # Storage Accounts
    ├── identity/             # Managed Identities & RBAC
    └── monitoring/           # Application Insights & Alerts
```

## 🚀 Quick Start

### Prerequisites

1. **Azure Account**: Active subscription with required quotas
2. **Tools Required**:
   ```bash
   # Install Azure CLI
   curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
   
   # Install Terraform
   brew install terraform  # macOS
   # or
   wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
   echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
   sudo apt update && sudo apt install terraform
   ```

3. **Required Azure Providers**:
   ```bash
   # Register required resource providers
   az provider register --namespace Microsoft.ContainerService
   az provider register --namespace Microsoft.DBforPostgreSQL
   az provider register --namespace Microsoft.Cache
   az provider register --namespace Microsoft.Storage
   az provider register --namespace Microsoft.KeyVault
   az provider register --namespace Microsoft.ContainerRegistry
   az provider register --namespace Microsoft.OperationalInsights
   ```

### Authentication

```bash
# Login to Azure
az login

# Set subscription
az account set --subscription "YOUR_SUBSCRIPTION_ID"

# Create service principal for Terraform (optional)
az ad sp create-for-rbac --name "terraform-sp" --role="Contributor" --scopes="/subscriptions/YOUR_SUBSCRIPTION_ID"
```

### Create Backend Storage

```bash
# Create resource group for Terraform state
az group create --name terraform-state-rg --location eastus2

# Create storage account
az storage account create \
  --name tfstatekailash$RANDOM \
  --resource-group terraform-state-rg \
  --location eastus2 \
  --sku Standard_LRS \
  --encryption-services blob

# Get storage account key
ACCOUNT_KEY=$(az storage account keys list \
  --resource-group terraform-state-rg \
  --account-name tfstatekailash \
  --query '[0].value' -o tsv)

# Create blob container
az storage container create \
  --name tfstate \
  --account-name tfstatekailash \
  --account-key $ACCOUNT_KEY
```

### Deploy Infrastructure

1. **Initialize Terraform**:
   ```bash
   cd deployment/terraform/azure
   
   # Initialize with backend config
   terraform init \
     -backend-config="resource_group_name=terraform-state-rg" \
     -backend-config="storage_account_name=tfstatekailash" \
     -backend-config="container_name=tfstate" \
     -backend-config="key=kailash.terraform.tfstate"
   ```

2. **Create workspace for environment**:
   ```bash
   terraform workspace new dev    # or staging, prod
   terraform workspace select dev
   ```

3. **Review and apply**:
   ```bash
   # Plan deployment
   terraform plan -var-file=environments/dev.tfvars
   
   # Apply configuration
   terraform apply -var-file=environments/dev.tfvars
   ```

## 🔧 Configuration

### Key Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `location` | Azure region | `eastus2` |
| `environment` | Environment name | Required |
| `kubernetes_version` | AKS version | `1.28` |
| `private_cluster_enabled` | Enable private AKS | `false` (dev) |

### Environment-Specific Settings

#### Development
- Basic tier services
- Minimal node counts
- No HA configurations
- Cost-optimized

#### Production
- Premium tier services
- Zone-redundant deployments
- High availability
- Security hardened

## 🔒 Security Features

### Network Security
- Private AKS cluster (production)
- Network Security Groups
- Service endpoints
- Private endpoints for PaaS

### Identity & Access
- Azure AD integration
- Managed identities
- RBAC enabled
- Key Vault for secrets

### Data Protection
- Encryption at rest
- TLS 1.2 minimum
- Host encryption
- Backup enabled

### Compliance
- Azure Policy enabled
- Diagnostic logs
- Azure Monitor integration
- Audit logging

## 📊 Monitoring & Observability

### Built-in Monitoring
- Log Analytics workspace
- Application Insights
- Container Insights
- Diagnostic settings

### Alert Configuration
```hcl
# Example alert for high CPU
metric_alerts = {
  high_cpu = {
    severity  = 1
    threshold = 90
  }
}
```

## 🔄 High Availability

### AKS Cluster
- Multi-zone deployment
- Auto-scaling enabled
- Multiple node pools
- Spot instances support

### Databases
- Zone redundant (production)
- Automated backups
- Geo-redundant backups
- Read replicas support

### Redis
- Premium tier with zones
- Persistence enabled
- Clustering support

## 💰 Cost Optimization

### Development
- Burstable VMs (B-series)
- Basic tier services
- Single zone deployment
- Spot instances

### Production
- Reserved instances
- Autoscaling policies
- Spot node pools
- Cost allocation tags

## 📝 Post-Deployment Steps

1. **Configure kubectl**:
   ```bash
   az aks get-credentials \
     --resource-group $(terraform output -raw resource_group_name) \
     --name $(terraform output -raw aks_cluster_name)
   ```

2. **Verify cluster**:
   ```bash
   kubectl get nodes
   kubectl get pods --all-namespaces
   ```

3. **Deploy ingress controller**:
   ```bash
   helm install nginx-ingress ingress-nginx/ingress-nginx \
     --namespace ingress-nginx \
     --create-namespace \
     --set controller.service.annotations."service\.beta\.kubernetes\.io/azure-load-balancer-health-probe-request-path"=/healthz
   ```

4. **Configure cert-manager**:
   ```bash
   helm install cert-manager jetstack/cert-manager \
     --namespace cert-manager \
     --create-namespace \
     --set installCRDs=true
   ```

## 🚨 Troubleshooting

### Common Issues

1. **Quota exceeded**:
   ```bash
   # Check quotas
   az vm list-usage --location eastus2 -o table
   
   # Request increase
   az support tickets create
   ```

2. **Node pool scaling issues**:
   ```bash
   # Check cluster autoscaler
   kubectl logs -n kube-system -l component=cluster-autoscaler
   
   # Manual scale
   az aks nodepool scale \
     --resource-group RESOURCE_GROUP \
     --cluster-name CLUSTER_NAME \
     --name NODEPOOL_NAME \
     --node-count 5
   ```

3. **Network connectivity**:
   ```bash
   # Test DNS
   kubectl run -it --rm debug --image=busybox --restart=Never -- nslookup kubernetes
   
   # Check network policies
   kubectl get networkpolicies --all-namespaces
   ```

## 🔗 Useful Commands

```bash
# Get AKS credentials
az aks get-credentials --resource-group $(terraform output -raw resource_group_name) --name $(terraform output -raw aks_cluster_name)

# Access PostgreSQL
az postgres flexible-server connect \
  --name $(terraform output -raw postgresql_server_name) \
  --database-name kailash \
  --username adminuser

# View Application Insights
echo "App Insights: $(terraform output -raw application_insights_instrumentation_key)"

# List storage accounts
az storage account list --resource-group $(terraform output -raw resource_group_name) -o table

# ACR login
az acr login --name $(terraform output -raw acr_name)
```

## 📋 Maintenance

### Regular Tasks
- Review Azure Advisor recommendations
- Update AKS version quarterly
- Rotate service principal credentials
- Review and optimize costs
- Test disaster recovery

### Upgrade Process
1. Test in dev environment
2. Update Terraform modules
3. Plan changes
4. Apply during maintenance window
5. Verify application health

### Backup Strategy
- PostgreSQL: Daily automated backups
- AKS: Velero for cluster backup
- Key Vault: Soft delete enabled
- Storage: Geo-redundant storage

## 🆘 Support

- [Azure Documentation](https://docs.microsoft.com/azure)
- [AKS Best Practices](https://docs.microsoft.com/azure/aks/best-practices)
- [Terraform AzureRM Provider](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs)
- [Community Support](https://github.com/your-org/kailash-template/issues)