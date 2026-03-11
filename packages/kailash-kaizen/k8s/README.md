# Kubernetes Deployment for Kaizen

Production-ready Kubernetes manifests for deploying Kaizen agents.

## Overview

This deployment provides:
- Horizontal scaling with replicas
- Resource limits and requests
- Health probes (liveness, readiness, startup)
- ConfigMap for non-sensitive configuration
- Secret management for API keys
- Service for internal communication
- Security best practices

## Quick Start

### 1. Create Namespace

```bash
kubectl create namespace kaizen
```

### 2. Create Secrets

Create secrets for sensitive data:

```bash
kubectl create secret generic kaizen-secrets \
  --from-literal=openai-api-key='your-openai-key' \
  --from-literal=anthropic-api-key='your-anthropic-key' \
  --from-literal=database-url='postgresql://user:pass@host:5432/db' \
  --from-literal=redis-url='redis://host:6379/0' \
  --namespace=kaizen
```

### 3. Apply ConfigMap

```bash
kubectl apply -f k8s/configmap.yaml
```

### 4. Create Service Account

```bash
kubectl create serviceaccount kaizen-agent --namespace=kaizen
```

### 5. Deploy Application

```bash
kubectl apply -f k8s/deployment.yaml
```

### 6. Create Service

```bash
kubectl apply -f k8s/service.yaml
```

### 7. Verify Deployment

```bash
kubectl get pods -n kaizen
kubectl get svc -n kaizen
```

## Configuration

### ConfigMap

Non-sensitive configuration in `configmap.yaml`:
- Environment name
- Log level
- Worker configuration
- Database/Redis hosts (non-sensitive)

Edit and reapply:
```bash
kubectl edit configmap kaizen-config -n kaizen
```

### Secrets

Sensitive configuration:
- API keys
- Database credentials
- Connection strings

Update secrets:
```bash
kubectl create secret generic kaizen-secrets \
  --from-literal=openai-api-key='new-key' \
  --dry-run=client -o yaml | kubectl apply -f -
```

### Resource Limits

Default limits per pod:
- CPU: 500m request, 2000m limit
- Memory: 512Mi request, 1Gi limit

Adjust in `deployment.yaml` based on workload.

## Scaling

### Horizontal Scaling

Manual scaling:
```bash
kubectl scale deployment kaizen --replicas=5 -n kaizen
```

Horizontal Pod Autoscaler:
```bash
kubectl autoscale deployment kaizen \
  --min=3 --max=10 \
  --cpu-percent=80 \
  -n kaizen
```

### Vertical Scaling

Update resource limits in `deployment.yaml`:
```yaml
resources:
  requests:
    memory: "1Gi"
    cpu: "1000m"
  limits:
    memory: "2Gi"
    cpu: "4000m"
```

## Monitoring

### Pod Status

```bash
kubectl get pods -n kaizen -w
```

### Logs

```bash
# Single pod
kubectl logs -f <pod-name> -n kaizen

# All pods
kubectl logs -f -l app=kaizen -n kaizen

# Previous instance (crashed pod)
kubectl logs <pod-name> -n kaizen --previous
```

### Describe

```bash
kubectl describe deployment kaizen -n kaizen
kubectl describe pod <pod-name> -n kaizen
```

### Events

```bash
kubectl get events -n kaizen --sort-by=.metadata.creationTimestamp
```

## Health Checks

### Liveness Probe
- Checks if container is alive
- Restarts container if fails
- 30s initial delay, 30s interval

### Readiness Probe
- Checks if container can accept traffic
- Removes from service if fails
- 10s initial delay, 10s interval

### Startup Probe
- Checks initial startup
- Allows up to 2 minutes for startup
- Prevents liveness/readiness checks during startup

## Security

### Pod Security

- Runs as non-root user (UID 1000)
- Read-only root filesystem
- Drops all capabilities
- No privilege escalation

### Network Policies

Create network policy for isolation:
```bash
kubectl apply -f k8s/network-policy.yaml
```

### RBAC

Service account has minimal permissions:
```bash
kubectl describe serviceaccount kaizen-agent -n kaizen
```

## Troubleshooting

### Pods Not Starting

Check events:
```bash
kubectl describe pod <pod-name> -n kaizen
```

Check logs:
```bash
kubectl logs <pod-name> -n kaizen
```

Common issues:
- Missing secrets
- Image pull errors
- Resource constraints

### Health Check Failures

View probe status:
```bash
kubectl describe pod <pod-name> -n kaizen | grep -A 5 "Liveness\|Readiness"
```

Adjust probe settings if needed:
```yaml
livenessProbe:
  initialDelaySeconds: 60  # Increase if slow startup
  timeoutSeconds: 10       # Increase for slow responses
```

### Out of Memory

Check resource usage:
```bash
kubectl top pods -n kaizen
```

Increase limits:
```yaml
resources:
  limits:
    memory: "2Gi"
```

### Configuration Issues

Verify ConfigMap:
```bash
kubectl get configmap kaizen-config -n kaizen -o yaml
```

Verify Secrets:
```bash
kubectl get secret kaizen-secrets -n kaizen -o jsonpath='{.data}' | jq
```

## Production Best Practices

### 1. Use Namespaces

Isolate environments:
```bash
kubectl create namespace kaizen-prod
kubectl create namespace kaizen-staging
```

### 2. Resource Quotas

Limit namespace resources:
```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: kaizen-quota
spec:
  hard:
    requests.cpu: "10"
    requests.memory: 20Gi
    limits.cpu: "20"
    limits.memory: 40Gi
```

### 3. Pod Disruption Budgets

Ensure availability during updates:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: kaizen-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: kaizen
```

### 4. Rolling Updates

Configure update strategy:
```yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
```

### 5. Monitoring Integration

Add Prometheus annotations:
```yaml
metadata:
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "9090"
    prometheus.io/path: "/metrics"
```

## Cleanup

Remove all resources:
```bash
kubectl delete -f k8s/
kubectl delete namespace kaizen
```

## Next Steps

- Add Ingress for external access
- Configure HPA for auto-scaling
- Add network policies
- Implement GitOps with ArgoCD
- Add service mesh (Istio/Linkerd)
- Configure backup strategy
- Add monitoring with Prometheus/Grafana
