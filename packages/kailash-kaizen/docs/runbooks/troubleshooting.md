# Troubleshooting Runbook

## Common Issues and Solutions

### Memory Issues

**Symptom**: Pods being OOMKilled

```bash
# Check memory usage
kubectl top pods -n kaizen

# Check resource limits
kubectl describe pod <pod-name> -n kaizen | grep -A 5 Limits

# Solution: Increase memory limits
kubectl patch deployment kaizen -n kaizen -p '{"spec":{"template":{"spec":{"containers":[{"name":"kaizen","resources":{"limits":{"memory":"2Gi"}}}]}}}}'
```

### Connection Timeouts

**Symptom**: External API timeouts

```bash
# Check network policies
kubectl get networkpolicies -n kaizen

# Test connectivity from pod
kubectl exec -it <pod-name> -n kaizen -- curl -v https://api.openai.com

# Check DNS resolution
kubectl exec -it <pod-name> -n kaizen -- nslookup api.openai.com
```

### High Error Rates

**Symptom**: Increased 500 errors

```bash
# Check recent logs
kubectl logs <pod-name> -n kaizen --tail=100 | grep ERROR

# Check dependency health
kubectl exec -it <pod-name> -n kaizen -- python -c "from kaizen.production.health import HealthCheck; import json; print(json.dumps(HealthCheck().check(), indent=2))"
```

### Database Connection Issues

**Symptom**: Cannot connect to database

```bash
# Verify secret exists
kubectl get secret kaizen-secrets -n kaizen

# Test database connection
kubectl exec -it <pod-name> -n kaizen -- psql $DATABASE_URL -c "SELECT 1"

# Check network policy allows database
kubectl describe networkpolicy kaizen-network-policy -n kaizen
```
