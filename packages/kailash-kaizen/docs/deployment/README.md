# Deployment Guide

Complete guide for deploying Kaizen AI to development, staging, and production environments.

## Quick Start

```bash
# Development with Docker Compose
cd examples/deployment/simple-qa
docker-compose up

# Production with Kubernetes
kubectl apply -f k8s/
```

## Environments

### Development
- Local Docker Compose
- Mock LLM providers for testing
- Hot reload enabled
- Debug logging

### Staging
- Kubernetes cluster
- Real LLM providers with dev keys
- Production-like configuration
- Full monitoring stack

### Production
- Kubernetes with high availability
- Production LLM keys
- Security hardening enabled
- Full observability

## See Also

- [Docker Deployment](./docker.md)
- [Kubernetes Deployment](./kubernetes.md)
- [Configuration Guide](../configuration/README.md)
