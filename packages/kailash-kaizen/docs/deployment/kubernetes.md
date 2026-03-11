# Kubernetes Deployment Guide

## Prerequisites

- Kubernetes cluster 1.24+
- kubectl configured
- Namespace created
- Secrets configured

## Quick Deploy

```bash
# Create namespace
kubectl create namespace kaizen

# Create secrets
kubectl create secret generic kaizen-secrets \
  --from-literal=openai-api-key=your-key \
  --from-literal=anthropic-api-key=your-key \
  -n kaizen

# Deploy application
kubectl apply -f k8s/ -n kaizen

# Verify deployment
kubectl get pods -n kaizen
kubectl get svc -n kaizen
```

## Components

- `deployment.yaml` - Application deployment
- `service.yaml` - Load balancer service
- `configmap.yaml` - Configuration
- `secret.yaml.example` - Secret template
- `network-policy.yaml` - Network security

## Scaling

```bash
# Manual scaling
kubectl scale deployment/kaizen -n kaizen --replicas=5

# Horizontal Pod Autoscaler
kubectl autoscale deployment kaizen -n kaizen --cpu-percent=70 --min=3 --max=10
```
