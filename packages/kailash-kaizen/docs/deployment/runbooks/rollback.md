# Rollback Runbook

This runbook provides step-by-step procedures for rolling back Kailash Kaizen deployments.

## Prerequisites

Before initiating a rollback:

- [ ] Confirm the issue requires a rollback (not a forward fix)
- [ ] Identify the target rollback version
- [ ] Notify stakeholders of planned rollback
- [ ] Ensure access to deployment systems
- [ ] Have monitoring dashboards ready

## Manual Rollback Steps

### 1. Identify Current and Target Versions

```bash
# Check current deployed version
kubectl get deployment kaizen -o jsonpath='{.spec.template.spec.containers[0].image}'

# List available versions
git tag --list 'v*' | tail -10
```

### 2. Pre-Rollback Checks

```bash
# Check current pod status
kubectl get pods -l app=kaizen

# Check current service health
curl -s http://kaizen-service/health | jq .

# Backup current configuration
kubectl get deployment kaizen -o yaml > backup-deployment-$(date +%Y%m%d-%H%M%S).yaml
```

### 3. Perform Rollback

#### Option A: Kubernetes Native Rollback

```bash
# Rollback to previous revision
kubectl rollout undo deployment/kaizen

# Or rollback to specific revision
kubectl rollout undo deployment/kaizen --to-revision=<revision-number>

# Monitor rollback progress
kubectl rollout status deployment/kaizen
```

#### Option B: Image-Based Rollback

```bash
# Update to specific version
kubectl set image deployment/kaizen kaizen=kaizen:v0.7.0

# Monitor rollback progress
kubectl rollout status deployment/kaizen
```

#### Option C: Helm Rollback

```bash
# List release history
helm history kaizen

# Rollback to previous release
helm rollback kaizen

# Or rollback to specific revision
helm rollback kaizen <revision-number>
```

### 4. Post-Rollback Verification

```bash
# Verify pods are running
kubectl get pods -l app=kaizen

# Check pod logs for errors
kubectl logs -l app=kaizen --tail=100

# Verify service health
curl -s http://kaizen-service/health | jq .

# Run smoke tests
pytest tests/smoke/ -v
```

## Verification Steps

After rollback, verify the following:

- [ ] All pods are running and healthy
- [ ] Health endpoint returns 200 OK
- [ ] No error logs in pod output
- [ ] Key workflows execute successfully
- [ ] Metrics are being collected
- [ ] Alerts are not firing

## Troubleshooting

### Rollback Stuck

If the rollback is stuck:

```bash
# Check rollout status
kubectl rollout status deployment/kaizen

# Check events for errors
kubectl describe deployment kaizen

# Force restart if needed
kubectl rollout restart deployment/kaizen
```

### Pods Failing After Rollback

If pods fail after rollback:

1. Check pod logs: `kubectl logs <pod-name>`
2. Check events: `kubectl describe pod <pod-name>`
3. Verify ConfigMaps/Secrets are compatible with rolled-back version
4. Consider database migration compatibility

### Database Incompatibility

If database schema is incompatible:

1. Do NOT proceed with rollback
2. Apply forward-only migration strategy
3. Consider data-only rollback with forward-compatible code

## Communication

### During Rollback

1. Update status page
2. Notify affected teams via Slack/PagerDuty
3. Log rollback in incident management system

### After Rollback

1. Send completion notification
2. Schedule post-mortem
3. Document lessons learned

## Related Documentation

- [Deployment Guide](../README.md)
- [Disaster Recovery](./disaster-recovery.md)
- [Incident Response](./incident-response.md)
