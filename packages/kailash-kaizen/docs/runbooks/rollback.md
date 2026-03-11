# Deployment Rollback Runbook

## Overview

This runbook provides step-by-step procedures for rolling back a failed or problematic deployment of Kailash Kaizen to a previous stable version.

## Prerequisites

Before initiating a rollback, ensure you have:

- [ ] Access to the deployment environment (kubectl/cluster access)
- [ ] Permissions to modify deployments in the target environment
- [ ] Knowledge of the target rollback version
- [ ] Backup of current deployment state (automated by rollback script)
- [ ] Communication channel open with stakeholders
- [ ] Access to monitoring and logging systems

## Required Tools

- `kubectl` - Kubernetes CLI (if using K8s)
- `docker` - Container runtime
- `bash` - Shell for running scripts
- `curl` - For health checks
- Access to container registry (GHCR, Docker Hub, etc.)

## Rollback Decision Criteria

Consider rollback when:

1. **Critical Bugs**: New version has critical bugs affecting core functionality
2. **Performance Degradation**: Significant performance regression (>50% slower)
3. **Security Issues**: Security vulnerabilities discovered post-deployment
4. **Failed Health Checks**: Health checks consistently failing
5. **Data Integrity Issues**: Data corruption or loss
6. **Integration Failures**: Critical integrations broken

## Automated Rollback (Recommended)

### Quick Rollback Command

```bash
# Rollback to previous version
./scripts/rollback.sh previous --force

# Rollback to specific version
./scripts/rollback.sh v1.2.3 --force

# Dry run (see what would happen)
./scripts/rollback.sh v1.2.3 --dry-run
```

### Step 1: Identify Target Version

Determine which version to rollback to:

```bash
# List recent deployments
kubectl rollout history deployment/kailash-kaizen -n production

# Or check container registry tags
docker images | grep kailash-kaizen

# Or use git tags
git tag --sort=-version:refname | head -5
```

### Step 2: Verify Target Version Exists

```bash
# Check if target image exists in registry
docker manifest inspect ghcr.io/your-org/kailash-kaizen:v1.2.3

# Verify the image is healthy
docker pull ghcr.io/your-org/kailash-kaizen:v1.2.3
```

### Step 3: Execute Rollback

```bash
# Set environment
export ENVIRONMENT=production  # or staging, dev

# Run rollback script
cd packages/kailash-kaizen
./scripts/rollback.sh v1.2.3
```

The script will:
1. ✅ Validate target version exists
2. ✅ Show confirmation prompt (skip with `--force`)
3. ✅ Backup current deployment state
4. ✅ Update deployment to target version
5. ✅ Wait for rollout completion
6. ✅ Verify deployment health
7. ✅ Log rollback action to audit trail

### Step 4: Verify Rollback Success

```bash
# Check deployment status
kubectl get deployments -n production
kubectl get pods -n production

# Run validation script
./scripts/validate_deployment.sh

# Check application logs
kubectl logs -l app=kailash-kaizen -n production --tail=100
```

## Manual Rollback Procedure

If automated rollback fails, use manual procedure:

### Step 1: Update Deployment Manually

```bash
# Update deployment image
kubectl set image deployment/kailash-kaizen \
  kailash-kaizen=ghcr.io/your-org/kailash-kaizen:v1.2.3 \
  -n production

# Or edit deployment directly
kubectl edit deployment kailash-kaizen -n production
```

### Step 2: Monitor Rollout

```bash
# Watch rollout progress
kubectl rollout status deployment/kailash-kaizen -n production --timeout=5m

# Monitor pods
watch kubectl get pods -n production -l app=kailash-kaizen
```

### Step 3: Verify Health

```bash
# Check pod status
kubectl get pods -n production -l app=kailash-kaizen

# Check logs
kubectl logs -l app=kailash-kaizen -n production --tail=50

# Test health endpoint
curl https://kaizen.production.example.com/health
```

### Step 4: Validate Functionality

Run smoke tests to verify core functionality:

```bash
# Basic connectivity
curl -I https://kaizen.production.example.com/

# Health check
curl https://kaizen.production.example.com/health

# Version check
curl https://kaizen.production.example.com/version

# Run validation script
./scripts/validate_deployment.sh
```

## Rollback Verification Checklist

After rollback completion, verify:

- [ ] All pods are running and healthy
- [ ] Health check endpoint returns 200 OK
- [ ] Application logs show no errors
- [ ] Response times are normal (<2s)
- [ ] All integrations are functioning
- [ ] Monitoring shows normal metrics
- [ ] No error alerts firing
- [ ] User-facing features work correctly
- [ ] Database connections are healthy
- [ ] Cache is functioning properly

## Post-Rollback Actions

### 1. Notify Stakeholders

```bash
# Example notification
echo "Deployment rolled back from v1.3.0 to v1.2.3 due to [REASON]" | \
  # Send to Slack/Teams/Email
```

### 2. Document Incident

Create incident report with:
- Rollback reason
- Affected version
- Target version
- Time of rollback
- Impact assessment
- Root cause (if known)

### 3. Update Deployment Pipeline

```bash
# Tag the problematic version
git tag -a v1.3.0-failed -m "Failed deployment - do not use"

# Update deployment blocklist if needed
```

### 4. Schedule Root Cause Analysis

- Schedule postmortem meeting
- Gather logs and metrics
- Document timeline
- Identify preventive measures

## Troubleshooting Common Issues

### Issue: Rollback Script Fails

**Symptoms**: Script exits with error

**Solutions**:
```bash
# Check permissions
ls -la scripts/rollback.sh
chmod +x scripts/rollback.sh

# Run with debug output
bash -x scripts/rollback.sh v1.2.3

# Try manual rollback procedure
```

### Issue: Pods Not Starting After Rollback

**Symptoms**: Pods in CrashLoopBackOff or Error state

**Solutions**:
```bash
# Check pod events
kubectl describe pod <pod-name> -n production

# Check logs
kubectl logs <pod-name> -n production

# Verify image exists
docker pull ghcr.io/your-org/kailash-kaizen:v1.2.3

# Check resource constraints
kubectl top pods -n production
```

### Issue: Health Checks Failing Post-Rollback

**Symptoms**: Health endpoint returns errors

**Solutions**:
```bash
# Check application logs
kubectl logs -l app=kailash-kaizen -n production --tail=100

# Verify configuration
kubectl get configmap kailash-kaizen-config -n production -o yaml

# Check database connectivity
kubectl exec -it <pod-name> -n production -- curl database:5432

# Restart pods if needed
kubectl rollout restart deployment/kailash-kaizen -n production
```

### Issue: Version Mismatch After Rollback

**Symptoms**: Deployment shows wrong version

**Solutions**:
```bash
# Verify deployment image
kubectl get deployment kailash-kaizen -n production -o jsonpath='{.spec.template.spec.containers[0].image}'

# Check actual running version
kubectl exec <pod-name> -n production -- cat /app/VERSION

# Force pod recreation
kubectl delete pods -l app=kailash-kaizen -n production
```

### Issue: Database Schema Incompatibility

**Symptoms**: Application fails due to schema mismatch

**Solutions**:
```bash
# Check if migrations need rollback
kubectl exec <pod-name> -n production -- alembic downgrade <revision>

# Or restore database backup
./scripts/restore_database.sh <backup-timestamp>

# Verify schema version
kubectl exec <pod-name> -n production -- alembic current
```

## Rollback Testing

Regularly test rollback procedures in non-production environments:

### Monthly Rollback Drill (Staging)

```bash
# 1. Deploy latest to staging
./scripts/deploy.sh staging latest

# 2. Test rollback
./scripts/rollback.sh previous --force

# 3. Verify functionality
./scripts/validate_deployment.sh

# 4. Document any issues
```

### Rollback Simulation

```bash
# Test rollback script in dry-run mode
./scripts/rollback.sh v1.2.3 --dry-run

# Verify script logic and output
```

## Emergency Contacts

In case of rollback issues:

1. **DevOps Team Lead**: [contact info]
2. **Platform Engineer**: [contact info]
3. **Database Administrator**: [contact info]
4. **Security Team**: [contact info]
5. **Executive On-Call**: [contact info]

## Monitoring During Rollback

Monitor these metrics during rollback:

- **Pod Status**: `kubectl get pods -n production -w`
- **Application Logs**: `kubectl logs -f -l app=kailash-kaizen -n production`
- **Error Rate**: Check monitoring dashboard
- **Response Time**: Check APM dashboard
- **Database Connections**: Check database monitoring
- **Memory/CPU**: `kubectl top pods -n production`

## Rollback Logs and Audit Trail

All rollback actions are logged to:

1. **Script Logs**: `/tmp/rollback-audit.log`
2. **Kubernetes Events**: `kubectl get events -n production`
3. **Application Logs**: Check centralized logging (ELK/Splunk)
4. **Deployment History**: `kubectl rollout history deployment/kailash-kaizen -n production`

## Success Criteria

Rollback is considered successful when:

1. ✅ All pods are running with target version
2. ✅ Health checks pass consistently
3. ✅ No application errors in logs
4. ✅ Response times are normal
5. ✅ All smoke tests pass
6. ✅ Monitoring shows healthy metrics
7. ✅ Stakeholders are notified
8. ✅ Incident is documented

## Related Documentation

- [Deployment Guide](../guides/deployment.md)
- [Health Checks Documentation](../health-checks.md)
- [Monitoring Setup](../monitoring.md)
- [Incident Response Playbook](../../operations/incident-response.md)

## Revision History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2025-10-04 | Initial rollback runbook | DevOps Team |
