# Deployment Runbook

## Pre-Deployment Checklist

- [ ] All tests passing in CI/CD
- [ ] Security scan completed (Trivy)
- [ ] Staging deployment successful
- [ ] Rollback plan documented
- [ ] Stakeholders notified
- [ ] Maintenance window scheduled (if needed)

## Deployment Steps

### 1. Deploy to Staging

```bash
# Apply to staging namespace
kubectl apply -f k8s/ -n kaizen-staging

# Verify deployment
kubectl rollout status deployment/kaizen -n kaizen-staging

# Run smoke tests
./scripts/smoke-test.sh staging
```

### 2. Deploy to Production

```bash
# Tag release
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0

# Apply to production
kubectl apply -f k8s/ -n kaizen

# Monitor rollout
kubectl rollout status deployment/kaizen -n kaizen --watch
```

## Post-Deployment Verification

```bash
# Check all pods running
kubectl get pods -n kaizen

# Check health endpoints
curl https://api.example.com/health

# Monitor metrics
# Open Grafana: http://grafana.example.com/kaizen-overview

# Check error rates (should be <1%)
```

## Rollback Procedure

```bash
# Rollback to previous version
kubectl rollout undo deployment/kaizen -n kaizen

# Verify rollback successful
kubectl rollout status deployment/kaizen -n kaizen

# Notify stakeholders
```
