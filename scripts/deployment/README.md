# Deployment Scripts

Infrastructure setup and deployment automation scripts.

## 📁 Scripts Overview

| Script | Purpose | Environment | Risk Level |
|--------|---------|-------------|------------|
| `deploy-tenant.sh` | Deploy tenant environments | Production | 🔴 High |
| `setup-github-projects.sh` | Setup GitHub project boards | Development | 🟡 Medium |
| `teardown-databases.sh` | Remove test databases | Testing | 🟡 Medium |

## 🚀 Quick Usage

### GitHub Project Setup
```bash
# Setup project boards and workflows
./setup-github-projects.sh
```

### Database Management
```bash
# Remove test databases (DESTRUCTIVE)
./teardown-databases.sh --confirm
```

### Tenant Deployment
```bash
# Deploy tenant environment (production)
./deploy-tenant.sh --tenant customer-123 --environment prod
```

## 📋 Script Details

### `deploy-tenant.sh`
**Purpose**: Deploy multi-tenant Kailash environments

**⚠️ PRODUCTION SCRIPT**: Requires careful configuration

**Features**:
- Multi-environment support (dev, staging, prod)
- Tenant isolation
- Resource provisioning
- Health validation

**Usage**:
```bash
# Deploy to staging
./deploy-tenant.sh --tenant acme-corp --environment staging

# Production deployment
./deploy-tenant.sh --tenant acme-corp --environment prod --confirm

# Dry run
./deploy-tenant.sh --tenant acme-corp --dry-run
```

### `setup-github-projects.sh`
**Purpose**: Automated GitHub project board and workflow setup

**Creates**:
- Project boards with standard columns
- Issue templates
- Workflow automation rules
- Label schemes

**Usage**:
```bash
# Interactive setup
./setup-github-projects.sh

# Automated setup
./setup-github-projects.sh --auto --project-name "Kailash Sprint 1"
```

### `teardown-databases.sh`
**Purpose**: Clean removal of test databases

**⚠️ DESTRUCTIVE**: Permanently removes data

**Features**:
- Multiple database support
- Confirmation prompts
- Volume cleanup
- Network removal

**Usage**:
```bash
# Interactive teardown
./teardown-databases.sh

# Force teardown (for CI)
./teardown-databases.sh --force

# Specific database only
./teardown-databases.sh --database postgres
```

## 🔧 Prerequisites

### Required Tools
- Docker & Docker Compose
- GitHub CLI (`gh`)
- kubectl (for tenant deployment)
- Cloud provider CLI (AWS/GCP/Azure)

### Authentication
```bash
# GitHub
gh auth login

# Cloud providers (example for AWS)
aws configure

# Kubernetes
kubectl config current-context
```

## 🐛 Troubleshooting

### Common Issues

**GitHub API rate limits**:
```bash
# Check rate limit
gh api rate_limit

# Authenticate if needed
gh auth refresh
```

**Docker permissions**:
```bash
# Add user to docker group
sudo usermod -aG docker $USER
```

**Kubernetes access**:
```bash
# Verify cluster access
kubectl cluster-info
```

## ⚠️ Safety Guidelines

### Before Deployment
1. **Test in staging first**
2. **Backup production data**
3. **Verify rollback procedures**
4. **Confirm resource quotas**

### Production Checklist
- [ ] Staging deployment successful
- [ ] All tests passing
- [ ] Monitoring configured
- [ ] Rollback plan ready
- [ ] Team notified

---

**Risk Level**: High - These scripts affect infrastructure
**Dependencies**: Docker, GitHub CLI, kubectl, cloud CLI tools
**Last Updated**: Scripts directory reorganization
