# Kailash User Management System - Deployment Guide

This directory contains deployment scripts and configurations for the Kailash User Management System across different environments and platforms.

## 📁 Directory Structure

```
deploy/
├── README.md                    # This file
├── docker-compose/             # Docker Compose deployments
│   ├── production.yml          # Production Docker Compose
│   ├── staging.yml             # Staging Docker Compose
│   └── development.yml         # Development Docker Compose
├── kubernetes/                  # Kubernetes deployment scripts
│   ├── deploy-production.sh    # Production K8s deployment
│   ├── deploy-staging.sh       # Staging K8s deployment
│   ├── deploy-development.sh   # Development K8s deployment
│   └── rollback.sh             # Rollback script
├── helm/                       # Helm deployment scripts
│   ├── install.sh              # Helm installation script
│   ├── upgrade.sh              # Helm upgrade script
│   └── uninstall.sh           # Helm uninstallation script
├── scripts/                    # Utility scripts
│   ├── health-check.sh         # Health check script
│   ├── backup.sh               # Backup script
│   ├── restore.sh              # Restore script
│   └── migrate.sh              # Database migration script
└── environments/               # Environment-specific configurations
    ├── production.env          # Production environment variables
    ├── staging.env            # Staging environment variables
    └── development.env        # Development environment variables
```

## 🚀 Quick Start

### Prerequisites

1. **Docker & Docker Compose** (for local development)
2. **Kubernetes Cluster** (for production deployments)
3. **Helm 3.x** (for Helm deployments)
4. **kubectl** configured for your cluster

### Local Development (Docker Compose)

```bash
# Start development environment
docker-compose -f deploy/docker-compose/development.yml up -d

# Check status
docker-compose -f deploy/docker-compose/development.yml ps

# View logs
docker-compose -f deploy/docker-compose/development.yml logs -f

# Stop environment
docker-compose -f deploy/docker-compose/development.yml down
```

### Staging Deployment (Kubernetes)

```bash
# Deploy to staging
./deploy/kubernetes/deploy-staging.sh

# Check deployment status
kubectl get pods -n kailash-user-management-staging

# Check service status
kubectl get svc -n kailash-user-management-staging
```

### Production Deployment (Helm)

```bash
# Install production deployment
./deploy/helm/install.sh production

# Upgrade existing deployment
./deploy/helm/upgrade.sh production

# Check deployment status
helm status kailash-user-management -n kailash-user-management
```

## 📋 Deployment Environments

### Development Environment
- **Purpose**: Local development and testing
- **Resources**: Minimal (1 replica, limited resources)
- **Database**: Local PostgreSQL container
- **Storage**: Local volumes
- **Access**: localhost only

### Staging Environment
- **Purpose**: Pre-production testing and QA
- **Resources**: Medium (1-3 replicas)
- **Database**: Managed PostgreSQL or dedicated instance
- **Storage**: Persistent volumes
- **Access**: Internal network with basic auth

### Production Environment
- **Purpose**: Live production workloads
- **Resources**: High availability (3+ replicas, auto-scaling)
- **Database**: Managed PostgreSQL with backup/recovery
- **Storage**: High-performance persistent storage
- **Access**: Load balancer with SSL/TLS

## 🔧 Configuration

### Environment Variables

Each environment uses specific configuration files:

- `environments/development.env` - Development settings
- `environments/staging.env` - Staging settings  
- `environments/production.env` - Production settings

### Secrets Management

**Development**: Environment files
**Staging/Production**: Kubernetes secrets or external secret management

### Database Configuration

**Development**: Docker container
**Staging**: Cloud-managed instance
**Production**: High-availability managed service with backup

## 🛠️ Deployment Scripts

### Kubernetes Scripts

- `deploy-production.sh` - Full production deployment with all components
- `deploy-staging.sh` - Staging deployment with reduced resources
- `deploy-development.sh` - Development deployment for testing
- `rollback.sh` - Rollback to previous deployment version

### Helm Scripts

- `install.sh` - Fresh Helm installation
- `upgrade.sh` - Upgrade existing Helm deployment
- `uninstall.sh` - Complete removal of Helm deployment

### Utility Scripts

- `health-check.sh` - Comprehensive health checking
- `backup.sh` - Database and file backup operations
- `restore.sh` - Restore from backup
- `migrate.sh` - Database schema migrations

## 📊 Monitoring & Health Checks

### Health Check Endpoints

- `/health` - Basic application health
- `/health/detailed` - Detailed component health
- `/metrics` - Prometheus metrics

### Monitoring Stack

- **Metrics**: Prometheus + Grafana
- **Logs**: ELK Stack or similar
- **Alerts**: AlertManager
- **Tracing**: Jaeger (optional)

## 🔐 Security Considerations

### Network Security
- All environments use network policies
- Production uses ingress with SSL/TLS
- Staging uses basic authentication
- Development is isolated to local network

### Secrets Management
- All sensitive data stored in Kubernetes secrets
- Rotation policies for production secrets
- Environment-specific secret scoping

### RBAC
- Principle of least privilege
- Service accounts with minimal permissions
- Environment-specific role bindings

## 📈 Scaling & Performance

### Auto-scaling Configuration
- **Production**: 3-20 replicas based on CPU/memory
- **Staging**: 1-5 replicas
- **Development**: Fixed 1 replica

### Resource Limits
- **Production**: 1Gi memory, 500m CPU per pod
- **Staging**: 512Mi memory, 250m CPU per pod
- **Development**: 256Mi memory, 100m CPU per pod

### Performance Targets
- API Response: <100ms (achieved: 45ms)
- Concurrent Users: 500+ (production)
- Success Rate: 99.9%

## 🔄 CI/CD Integration

### GitOps Workflow
1. Code changes trigger CI pipeline
2. Tests run automatically
3. Docker images built and pushed
4. Staging deployment updated
5. Manual approval for production
6. Production deployment with rollback capability

### Deployment Strategies
- **Blue-Green**: Production deployments
- **Rolling Updates**: Staging deployments
- **Recreate**: Development deployments

## 🆘 Troubleshooting

### Common Issues

**Pod Won't Start**
```bash
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace>
```

**Service Unavailable**
```bash
kubectl get svc -n <namespace>
kubectl get endpoints -n <namespace>
```

**Database Connection Issues**
```bash
kubectl exec -it <pod-name> -n <namespace> -- env | grep DATABASE
```

### Recovery Procedures

**Application Rollback**
```bash
./deploy/kubernetes/rollback.sh <previous-version>
```

**Database Recovery**
```bash
./deploy/scripts/restore.sh <backup-file>
```

## 📞 Support

For deployment issues or questions:
1. Check logs using provided scripts
2. Review troubleshooting section
3. Contact the platform team
4. Create incident ticket if needed

## 📝 Notes

- Always test deployments in staging first
- Backup before major upgrades
- Monitor resource usage after scaling
- Keep deployment scripts version controlled
- Document any manual steps or workarounds