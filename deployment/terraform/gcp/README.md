# Google Cloud Platform (GCP) Terraform Infrastructure

This directory contains enterprise-grade Terraform modules for deploying the Kailash SDK Template on Google Cloud Platform with GKE (Google Kubernetes Engine).

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                          GCP Project                             │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐     ┌──────────────┐    ┌──────────────┐ │
│  │   VPC Network   │     │ Cloud Router │    │  Cloud NAT   │ │
│  │   10.0.0.0/16   │────▶│              │────▶│              │ │
│  └─────────────────┘     └──────────────┘    └──────────────┘ │
│           │                                                      │
│  ┌────────┴────────┐                                           │
│  │     Subnets     │                                           │
│  ├─────────────────┤                                           │
│  │ Primary: /24    │                                           │
│  │ Pods: /16       │                                           │
│  │ Services: /16   │                                           │
│  └─────────────────┘                                           │
│           │                                                      │
│  ┌────────┴────────────────────────────────┐                  │
│  │            GKE Cluster                   │                  │
│  ├──────────────────────────────────────────┤                  │
│  │ ┌──────────┐ ┌──────────┐ ┌──────────┐ │                  │
│  │ │  System  │ │ General  │ │   Spot   │ │                  │
│  │ │   Pool   │ │   Pool   │ │   Pool   │ │                  │
│  │ └──────────┘ └──────────┘ └──────────┘ │                  │
│  └──────────────────────────────────────────┘                  │
│           │                                                      │
│  ┌────────┴────────┐    ┌─────────────┐    ┌────────────────┐ │
│  │   Cloud SQL     │    │ Memorystore │    │  GCS Buckets   │ │
│  │  (PostgreSQL)   │    │   (Redis)   │    │                │ │
│  └─────────────────┘    └─────────────┘    └────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## 📁 Module Structure

```
gcp/
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
    ├── vpc/                  # VPC networking
    ├── gke/                  # GKE cluster
    ├── cloud-sql/            # PostgreSQL database
    ├── memorystore/          # Redis cache
    ├── gcs/                  # Cloud Storage
    ├── iam/                  # IAM & Workload Identity
    └── monitoring/           # Stackdriver monitoring
```

## 🚀 Quick Start

### Prerequisites

1. **GCP Account**: Project with billing enabled
2. **Tools Required**:
   ```bash
   # Install gcloud CLI
   curl https://sdk.cloud.google.com | bash
   
   # Install Terraform
   brew install terraform  # macOS
   # or
   wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
   echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
   sudo apt update && sudo apt install terraform
   ```

3. **Enable Required APIs**:
   ```bash
   gcloud services enable compute.googleapis.com
   gcloud services enable container.googleapis.com
   gcloud services enable sqladmin.googleapis.com
   gcloud services enable redis.googleapis.com
   gcloud services enable servicenetworking.googleapis.com
   gcloud services enable cloudresourcemanager.googleapis.com
   gcloud services enable iam.googleapis.com
   gcloud services enable monitoring.googleapis.com
   ```

### Authentication

```bash
# Authenticate with GCP
gcloud auth login
gcloud auth application-default login

# Set default project
gcloud config set project YOUR_PROJECT_ID
```

### Create State Bucket

```bash
# Create GCS bucket for Terraform state
gsutil mb -p YOUR_PROJECT_ID gs://YOUR_PROJECT_ID-terraform-state
gsutil versioning set on gs://YOUR_PROJECT_ID-terraform-state
```

### Deploy Infrastructure

1. **Initialize Terraform**:
   ```bash
   cd deployment/terraform/gcp
   
   # Initialize with backend config
   terraform init \
     -backend-config="bucket=YOUR_PROJECT_ID-terraform-state" \
     -backend-config="prefix=terraform/state/kailash"
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
| `project_id` | GCP project ID | Required |
| `region` | Deployment region | `us-central1` |
| `environment` | Environment name | Required |
| `kubernetes_version` | GKE version | `1.28` |
| `regional_cluster` | Deploy regional cluster | `true` (prod) |

### Environment-Specific Settings

#### Development
- Zonal cluster (single zone)
- Preemptible nodes
- Minimal resources
- Basic monitoring

#### Production
- Regional cluster (multi-zone HA)
- Standard nodes with autoscaling
- High-performance databases
- Comprehensive monitoring

## 🔒 Security Features

### Network Security
- Private GKE nodes
- Cloud NAT for egress
- VPC-native networking
- Network policies enabled

### Identity & Access
- Workload Identity for pods
- Least privilege IAM roles
- Service account per workload
- Binary Authorization ready

### Data Protection
- Encryption at rest (Cloud KMS)
- Private service connections
- SSL/TLS for all services
- Backup configurations

### Compliance
- VPC Flow Logs
- Cloud Audit Logs
- Shielded GKE nodes
- Security Command Center integration

## 📊 Monitoring & Observability

### Built-in Monitoring
- GKE metrics and logs
- Custom dashboards
- Alert policies
- Uptime checks

### Integration Points
```yaml
# Prometheus scraping
monitoring_config: ["SYSTEM_COMPONENTS", "WORKLOADS"]

# Managed Prometheus
managed_prometheus:
  enabled: true
```

## 🔄 High Availability

### GKE Cluster
- Regional deployment (3 zones)
- Auto-repair and auto-upgrade
- Pod disruption budgets
- Multiple node pools

### Databases
- Cloud SQL HA configuration
- Automated backups
- Point-in-time recovery
- Read replicas (optional)

### Redis
- Standard HA tier
- Automatic failover
- Persistence enabled

## 💰 Cost Optimization

### Development
- Preemptible/Spot instances
- Smaller machine types
- Zonal resources
- Minimal replicas

### Production
- Reserved instances discount
- Autoscaling policies
- Lifecycle policies for storage
- Cost allocation tracking

## 📝 Post-Deployment Steps

1. **Configure kubectl**:
   ```bash
   gcloud container clusters get-credentials CLUSTER_NAME \
     --location LOCATION \
     --project PROJECT_ID
   ```

2. **Deploy applications**:
   ```bash
   # Install Helm
   curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
   
   # Deploy ingress controller
   helm install nginx-ingress ingress-nginx/ingress-nginx \
     --namespace ingress-nginx \
     --create-namespace
   
   # Deploy cert-manager
   helm install cert-manager jetstack/cert-manager \
     --namespace cert-manager \
     --create-namespace \
     --set installCRDs=true
   ```

3. **Setup monitoring**:
   ```bash
   # Deploy Prometheus & Grafana
   helm install prometheus prometheus-community/kube-prometheus-stack \
     --namespace monitoring \
     --create-namespace
   ```

## 🚨 Troubleshooting

### Common Issues

1. **API not enabled**:
   ```bash
   ERROR: API [container.googleapis.com] not enabled
   
   # Fix:
   gcloud services enable container.googleapis.com
   ```

2. **Insufficient quotas**:
   ```bash
   # Check quotas
   gcloud compute project-info describe --project=PROJECT_ID
   
   # Request increase via Console
   ```

3. **Network connectivity**:
   ```bash
   # Test cluster connectivity
   kubectl cluster-info
   
   # Check firewall rules
   gcloud compute firewall-rules list
   ```

## 🔗 Useful Commands

```bash
# Get cluster credentials
gcloud container clusters get-credentials $(terraform output -raw cluster_name) \
  --location $(terraform output -raw cluster_location)

# Connect to Cloud SQL
gcloud sql connect $(terraform output -raw cloud_sql_instance_name) \
  --user=postgres \
  --database=kailash

# View monitoring dashboards
echo "Monitoring URL: $(terraform output -raw monitoring_console_url)"

# SSH to node (debugging)
gcloud compute ssh NODE_NAME --zone=ZONE
```

## 📋 Maintenance

### Regular Tasks
- Review security advisories
- Update GKE version (via release channel)
- Rotate service account keys
- Review and optimize costs
- Test disaster recovery

### Upgrade Process
1. Test in dev environment
2. Update Terraform modules
3. Plan and review changes
4. Apply during maintenance window
5. Verify application health

## 🆘 Support

- [GCP Documentation](https://cloud.google.com/docs)
- [GKE Best Practices](https://cloud.google.com/kubernetes-engine/docs/best-practices)
- [Terraform GCP Provider](https://registry.terraform.io/providers/hashicorp/google/latest/docs)
- [Community Support](https://github.com/your-org/kailash-template/issues)