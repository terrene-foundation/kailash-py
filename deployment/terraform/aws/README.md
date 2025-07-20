# AWS EKS Enterprise Deployment

## 🚀 Overview

Enterprise-grade Terraform configuration for deploying Kailash SDK on AWS EKS with complete networking, security, and high availability.

## 🏗️ Architecture

### Core Components
- **EKS Cluster**: Multi-AZ with managed node groups
- **VPC**: Custom VPC with private/public subnets
- **RDS**: Multi-AZ PostgreSQL with encryption
- **ElastiCache**: Redis cluster with failover
- **ALB**: Application Load Balancer with SSL termination
- **Route53**: DNS management and health checks
- **KMS**: Encryption key management
- **IAM**: Fine-grained access control

### Security Features
- **Private subnets**: Worker nodes in private subnets only
- **NAT Gateway**: High availability outbound internet access
- **Security Groups**: Micro-segmentation at network level
- **IRSA**: IAM Roles for Service Accounts
- **Encryption**: At-rest and in-transit encryption
- **Secrets Manager**: Secure secret storage

### High Availability
- **Multi-AZ**: Deployment across 3 availability zones
- **Auto Scaling**: Cluster and pod auto-scaling
- **Load Balancing**: Application and network load balancers
- **Backup**: Automated backups and point-in-time recovery

## 📁 Module Structure

```
terraform/aws/
├── main.tf                    # Root module
├── variables.tf               # Input variables
├── outputs.tf                # Output values
├── versions.tf               # Provider versions
├── terraform.tfvars.example  # Example configuration
├── modules/
│   ├── vpc/                  # VPC and networking
│   ├── eks/                  # EKS cluster
│   ├── rds/                  # PostgreSQL database
│   ├── elasticache/          # Redis cache
│   ├── security/             # Security groups and policies
│   ├── monitoring/           # CloudWatch and observability
│   └── dns/                  # Route53 configuration
└── environments/
    ├── development/          # Dev environment
    ├── staging/             # Staging environment
    └── production/          # Production environment
```

## 🚀 Quick Start

### Prerequisites
```bash
# Install required tools
brew install terraform awscli kubectl

# Configure AWS credentials
aws configure

# Or use AWS CLI profiles
export AWS_PROFILE=your-profile
```

### 1. Initialize Terraform
```bash
cd deployment/terraform/aws
terraform init
```

### 2. Configure Environment
```bash
# Copy example configuration
cp terraform.tfvars.example terraform.tfvars

# Edit with your values
vi terraform.tfvars
```

### 3. Plan Deployment
```bash
# Review planned changes
terraform plan

# Plan for specific environment
terraform plan -var-file="environments/production/terraform.tfvars"
```

### 4. Deploy Infrastructure
```bash
# Deploy development environment
terraform apply -var-file="environments/development/terraform.tfvars"

# Deploy production environment
terraform apply -var-file="environments/production/terraform.tfvars"
```

### 5. Configure kubectl
```bash
# Update kubeconfig
aws eks update-kubeconfig --region us-west-2 --name kailash-cluster-prod

# Verify connection
kubectl get nodes
```

## ⚙️ Configuration

### Essential Variables
```hcl
# terraform.tfvars
region = "us-west-2"
environment = "production"
cluster_name = "kailash-cluster"

# Network configuration
vpc_cidr = "10.0.0.0/16"
availability_zones = ["us-west-2a", "us-west-2b", "us-west-2c"]

# EKS configuration
kubernetes_version = "1.28"
node_groups = {
  general = {
    instance_types = ["m6i.large"]
    scaling_config = {
      desired_size = 3
      max_size     = 10
      min_size     = 1
    }
  }
}

# Database configuration
db_instance_class = "db.r6g.large"
db_allocated_storage = 100
db_max_allocated_storage = 1000

# Cache configuration
redis_node_type = "cache.r6g.large"
redis_num_cache_nodes = 3

# Domain configuration
domain_name = "your-domain.com"
create_route53_zone = true
```

### Security Configuration
```hcl
# Enable encryption
encrypt_secrets = true
kms_key_rotation = true

# IRSA configuration
enable_irsa = true

# Network security
enable_flow_logs = true
enable_vpc_endpoints = true

# Compliance
enable_config = true
enable_cloudtrail = true
```

## 🔧 Customization

### Environment-Specific Configurations

#### Development
```hcl
# environments/development/terraform.tfvars
instance_types = ["t3.medium"]
desired_capacity = 1
max_capacity = 3
db_instance_class = "db.t3.micro"
```

#### Production
```hcl
# environments/production/terraform.tfvars
instance_types = ["m6i.xlarge"]
desired_capacity = 3
max_capacity = 20
db_instance_class = "db.r6g.xlarge"
multi_az = true
backup_retention_period = 30
```

### Add-on Modules
```hcl
# Enable additional features
enable_cluster_autoscaler = true
enable_aws_load_balancer_controller = true
enable_external_dns = true
enable_cert_manager = true
enable_velero = true
```

## 📊 Monitoring & Observability

### CloudWatch Integration
- **Container Insights**: EKS cluster monitoring
- **Application Insights**: Application performance monitoring
- **Log Groups**: Centralized log aggregation
- **Custom Metrics**: Business metrics collection

### Prometheus & Grafana
```hcl
# Enable monitoring stack
enable_prometheus = true
enable_grafana = true
enable_jaeger = true
```

## 🔐 Security Best Practices

### Network Security
- Private worker nodes
- Security group rules based on least privilege
- VPC endpoints for AWS services
- NAT Gateway for outbound traffic

### Identity & Access Management
- IAM roles for service accounts (IRSA)
- Pod security policies
- Network policies
- RBAC configurations

### Encryption
- EKS secrets encryption with KMS
- RDS encryption at rest
- ElastiCache encryption in transit
- S3 bucket encryption

## 💾 Backup & Disaster Recovery

### Automated Backups
- RDS automated backups with point-in-time recovery
- ElastiCache backup and restore
- EKS cluster configuration backup
- Application data backup with Velero

### Multi-Region Setup
```hcl
# Enable cross-region replication
enable_cross_region_backup = true
backup_region = "us-east-1"
```

## 🎯 Cost Optimization

### Resource Optimization
- Spot instances for non-production workloads
- Reserved instances for predictable workloads
- Right-sizing recommendations
- Auto-scaling policies

### Cost Monitoring
```hcl
# Enable cost monitoring
enable_cost_anomaly_detection = true
billing_alerts = {
  threshold = 1000
  email = "admin@your-domain.com"
}
```

## 🔄 CI/CD Integration

### GitHub Actions
```yaml
# .github/workflows/terraform.yml
name: Terraform
on:
  push:
    paths: ['deployment/terraform/**']
  
jobs:
  terraform:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - uses: hashicorp/setup-terraform@v2
    - run: terraform init
    - run: terraform plan
    - run: terraform apply -auto-approve
```

### GitLab CI
```yaml
# .gitlab-ci.yml
terraform:
  image: hashicorp/terraform:latest
  script:
    - terraform init
    - terraform plan
    - terraform apply -auto-approve
```

## 🛠️ Troubleshooting

### Common Issues
1. **IAM Permissions**: Ensure adequate AWS permissions
2. **Quota Limits**: Check AWS service quotas
3. **Network Connectivity**: Verify VPC and subnet configuration
4. **DNS Resolution**: Check Route53 configuration

### Debug Commands
```bash
# Check cluster status
kubectl get nodes
kubectl get pods --all-namespaces

# Check AWS resources
aws eks describe-cluster --name kailash-cluster
aws rds describe-db-instances
aws elasticache describe-cache-clusters

# Terraform debugging
export TF_LOG=DEBUG
terraform plan
```

## 📖 Documentation

- [AWS EKS Best Practices](https://aws.github.io/aws-eks-best-practices/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [EKS Workshop](https://www.eksworkshop.com/)

---

**🚀 Enterprise-ready AWS EKS deployment with comprehensive security and monitoring**