# Velero Backup and Disaster Recovery

This directory contains comprehensive backup and disaster recovery solutions for the Kailash platform using Velero.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Backup & DR Architecture                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐        ┌──────────────────┐             │
│  │   Primary        │        │   Disaster       │             │
│  │   Region         │◄──────►│   Recovery       │             │
│  │   (us-east-1)    │        │   (us-west-2)    │             │
│  └──────────────────┘        └──────────────────┘             │
│           │                           │                         │
│           │                           │                         │
│  ┌────────┴────────┐        ┌────────┴────────┐               │
│  │  Velero Agent   │        │  Velero Agent   │               │
│  │  + Plugins      │        │  + Plugins      │               │
│  └─────────────────┘        └─────────────────┘               │
│           │                           │                         │
│           └─────────────┬─────────────┘                         │
│                         │                                       │
│  ┌─────────────────────┴─────────────────────┐                │
│  │            Backup Storage                 │                │
│  │                                           │                │
│  │  ┌─────────────┐  ┌─────────────┐       │                │
│  │  │   Primary   │  │   Cross     │       │                │
│  │  │   Backups   │  │   Region    │       │                │
│  │  │ (S3 Bucket) │  │   Backups   │       │                │
│  │  └─────────────┘  └─────────────┘       │                │
│  │                                           │                │
│  │  ┌─────────────┐  ┌─────────────┐       │                │
│  │  │    EBS      │  │    EBS      │       │                │
│  │  │  Snapshots  │  │  Snapshots  │       │                │
│  │  │ (us-east-1) │  │ (us-west-2) │       │                │
│  │  └─────────────┘  └─────────────┘       │                │
│  └─────────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────────────┘
```

## 📁 Directory Structure

```
backup/
├── README.md                              # This file
├── kustomization.yaml                     # Kustomize configuration
├── velero/                               # Velero deployment configs
│   ├── velero-aws.yaml                  # Main Velero installation
│   └── backup-schedules.yaml            # Automated backup schedules
├── disaster-recovery/                    # DR procedures and automation
│   └── disaster-recovery-plan.yaml      # Comprehensive DR plan
└── scripts/                             # Manual recovery scripts
    └── manual-recovery.sh               # Emergency recovery script
```

## 🎯 Backup Strategy

### Multi-Tier Backup Approach

| **Tier** | **Frequency** | **Retention** | **Scope** | **RTO** | **RPO** |
|----------|---------------|---------------|-----------|---------|---------|
| **Hot** | Hourly | 7 days | Critical data only | 15 min | 1 hour |
| **Critical** | Daily | 30 days | Core namespaces | 1 hour | 4 hours |
| **Full** | Weekly | 90 days | Entire cluster | 4 hours | 24 hours |
| **Config** | Every 30min | 3 days | Configuration only | 30 min | 30 min |
| **DR** | Monthly | 1 year | Cross-region backup | 2 hours | 24 hours |

### Backup Schedules

1. **Hourly Hot Backup** (`0 * * * *`)
   - Application data only (kailash-app namespace)
   - No volume snapshots (uses Restic)
   - 7-day retention

2. **Daily Critical Backup** (`0 2 * * *`)
   - Critical namespaces (app, monitoring, logging, vault)
   - Full volume snapshots
   - Application consistency hooks
   - 30-day retention

3. **Weekly Full Backup** (`0 3 * * 0`)
   - Complete cluster backup
   - All namespaces except system
   - 90-day retention

4. **Configuration Backup** (`*/30 * * * *`)
   - ConfigMaps, Secrets, RBAC, etc.
   - No persistent volumes
   - 3-day retention

5. **Monthly DR Backup** (`0 4 1 * *`)
   - Cross-region backup for disaster recovery
   - 1-year retention
   - Complete cluster state

## 🚀 Quick Start

### Prerequisites

1. **AWS Resources**:
   ```bash
   # Create S3 bucket for backups
   aws s3 mb s3://kailash-velero-backups --region us-east-1
   
   # Create cross-region bucket for DR
   aws s3 mb s3://kailash-velero-dr-backups --region us-west-2
   
   # Enable versioning and encryption
   aws s3api put-bucket-versioning \
     --bucket kailash-velero-backups \
     --versioning-configuration Status=Enabled
   
   aws s3api put-bucket-encryption \
     --bucket kailash-velero-backups \
     --server-side-encryption-configuration '{
       "Rules": [{
         "ApplyServerSideEncryptionByDefault": {
           "SSEAlgorithm": "AES256"
         }
       }]
     }'
   ```

2. **IAM Role for Velero**:
   ```bash
   # Create IAM policy (see terraform/aws/modules/velero-iam/)
   aws iam create-policy \
     --policy-name VeleroPolicy \
     --policy-document file://velero-policy.json
   
   # Create service account with IRSA
   eksctl create iamserviceaccount \
     --cluster=kailash-prod \
     --namespace=velero \
     --name=velero \
     --attach-policy-arn=arn:aws:iam::ACCOUNT:policy/VeleroPolicy \
     --approve
   ```

### Installation

1. **Deploy Velero**:
   ```bash
   # Apply Velero configuration
   kubectl apply -k deployment/backup/
   
   # Wait for Velero to be ready
   kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=velero -n velero --timeout=300s
   
   # Verify installation
   velero version
   ```

2. **Verify Backup Locations**:
   ```bash
   # Check backup storage locations
   velero backup-location get
   
   # Check volume snapshot locations
   velero snapshot-location get
   ```

3. **Test Backup**:
   ```bash
   # Create a test backup
   velero backup create test-backup --include-namespaces kailash-app --wait
   
   # Check backup status
   velero backup describe test-backup
   ```

## 🔧 Operations

### Manual Backup Operations

**Create Emergency Backup**:
```bash
# Full cluster emergency backup
velero backup create emergency-$(date +%Y%m%d-%H%M%S) \
  --include-cluster-resources=true \
  --snapshot-volumes=true \
  --wait

# Application-specific backup
velero backup create app-emergency-$(date +%Y%m%d-%H%M%S) \
  --include-namespaces kailash-app \
  --snapshot-volumes=true \
  --wait
```

**List Available Backups**:
```bash
# List all backups
velero backup get

# Filter by labels
velero backup get --selector backup-tier=critical

# Show backup details
velero backup describe <backup-name>
```

### Manual Restore Operations

**Restore Specific Namespace**:
```bash
# Restore to original namespace
velero restore create restore-$(date +%s) \
  --from-backup <backup-name> \
  --include-namespaces kailash-app \
  --wait

# Restore to different namespace
velero restore create restore-$(date +%s) \
  --from-backup <backup-name> \
  --namespace-mappings kailash-app:kailash-app-restored \
  --wait
```

**Full Cluster Restore**:
```bash
# CAUTION: This will overwrite existing resources
velero restore create full-restore-$(date +%s) \
  --from-backup <backup-name> \
  --exclude-namespaces kube-system,kube-public,velero \
  --include-cluster-resources=true \
  --wait
```

### Using the Recovery Script

The manual recovery script provides guided disaster recovery:

```bash
# List available backups
./deployment/backup/scripts/manual-recovery.sh list-backups

# Restore specific namespace
./deployment/backup/scripts/manual-recovery.sh restore-namespace daily-critical-20240120-020000 kailash-app-test

# Full cluster recovery (requires confirmation)
./deployment/backup/scripts/manual-recovery.sh full-recovery weekly-full-20240120-030000 CONFIRM

# Cross-region disaster recovery
./deployment/backup/scripts/manual-recovery.sh cross-region-recovery monthly-dr-20240101-040000 CONFIRM

# Check system status
./deployment/backup/scripts/manual-recovery.sh status

# Create emergency backup
./deployment/backup/scripts/manual-recovery.sh emergency-backup
```

## 🚨 Disaster Recovery Scenarios

### Scenario 1: Namespace Corruption

**Detection**: Health check failures, persistent pod crashes

**Recovery**:
1. Isolate affected namespace
2. Create emergency backup of current state
3. Restore from latest daily backup
4. Validate restored services

### Scenario 2: Cluster Failure

**Detection**: API server unreachable, multiple node failures

**Recovery**:
1. Provision new cluster infrastructure
2. Install Velero
3. Restore cluster state from weekly backup
4. Restore application data from daily backup
5. Update DNS and load balancer configuration

### Scenario 3: Regional Outage

**Detection**: Region-wide connectivity loss

**Recovery**:
1. Activate DR region infrastructure
2. Install Velero in DR cluster
3. Restore from cross-region monthly backup
4. Update traffic routing to DR region
5. Notify stakeholders

## 📊 Monitoring & Alerting

### Prometheus Metrics

Velero exposes metrics for monitoring:

```yaml
# Backup success rate
rate(velero_backup_success_total[24h]) / 
(rate(velero_backup_success_total[24h]) + rate(velero_backup_failure_total[24h]))

# Backup duration
velero_backup_duration_seconds

# Last successful backup timestamp
velero_backup_last_successful_timestamp

# Storage usage
aws_s3_bucket_size_bytes{bucket="kailash-velero-backups"}
```

### Grafana Dashboard

A comprehensive Grafana dashboard is included showing:
- Backup success rates
- Backup duration trends
- Storage usage
- RTO/RPO compliance
- Recovery status

### Alerts

Critical alerts configured:
- `VeleroBackupFailure`: Backup failures
- `VeleroBackupMissing`: No backup in 24 hours
- `VeleroRestoreFailure`: Restore failures
- `RPOViolation`: Recovery Point Objective exceeded

## 🔒 Security

### Encryption

- **S3 Buckets**: Server-side encryption (AES-256 or KMS)
- **EBS Snapshots**: Encrypted by default
- **Backup Data**: Velero supports client-side encryption

### Access Control

- **IAM Roles**: Least privilege access to AWS resources
- **RBAC**: Kubernetes role-based access control
- **Network Policies**: Restricted network access

### Compliance

Backup procedures support:
- **SOC2**: Data protection and availability controls
- **HIPAA**: Data backup and recovery safeguards
- **ISO27001**: Business continuity management

## 🧪 Testing & Validation

### Automated Validation

Daily backup validation includes:
1. Backup completion verification
2. Test restore to temporary namespace
3. Data integrity checks
4. Cleanup of test resources

### Disaster Recovery Drills

Monthly drills include:
1. Simulated cluster failure
2. Full recovery procedure execution
3. RTO/RPO measurement
4. Documentation updates

### Performance Testing

Regular testing of:
- Backup duration vs. data size
- Restore performance
- Network impact during operations

## 📝 Best Practices

1. **Regular Testing**: Test restore procedures monthly
2. **Multi-Region**: Use cross-region backups for true DR
3. **Monitoring**: Monitor backup health and storage usage
4. **Documentation**: Keep recovery procedures updated
5. **Automation**: Automate as much as possible
6. **Validation**: Always validate restored data
7. **Security**: Encrypt backups and limit access

## 🔗 Related Documentation

- [Velero Documentation](https://velero.io/docs/)
- [AWS EBS CSI Driver](https://github.com/kubernetes-sigs/aws-ebs-csi-driver)
- [Kubernetes Backup Best Practices](https://kubernetes.io/docs/concepts/cluster-administration/backing-up/)
- [Disaster Recovery Planning](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/disaster-recovery-dr-objectives.html)

## 🆘 Emergency Contacts

In case of disaster:
1. **On-call Engineer**: Check PagerDuty rotation
2. **Platform Team**: Slack #platform-emergency
3. **Management**: Follow incident escalation procedures

Remember: The best disaster recovery plan is the one that's tested regularly!