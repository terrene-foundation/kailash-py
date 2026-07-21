---
skill: nexus-production-deployment
description: Production deployment patterns, Docker, Kubernetes, scaling, and security
priority: MEDIUM
tags: [nexus, production, deployment, docker, kubernetes, scaling]
---

# Nexus Production Deployment

## Docker

### Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV NEXUS_ENV=production
EXPOSE 8000 3001
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1
CMD ["python", "app.py"]
```

### docker-compose.yml

```yaml
version: "3.8"
services:
  nexus:
    build: .
    ports: ["8000:8000", "3001:3001"]
    environment:
      - NEXUS_ENV=production
      - DATABASE_URL=postgresql://postgres:password@postgres:5432/nexus
      - REDIS_URL=redis://redis:6379
    depends_on: [postgres, redis]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
    restart: unless-stopped
  postgres:
    image: postgres:15
    environment: [POSTGRES_DB=nexus, POSTGRES_PASSWORD=password]
    volumes: [postgres_data:/var/lib/postgresql/data]
  redis:
    image: redis:7-alpine
    volumes: [redis_data:/data]
volumes:
  postgres_data:
  redis_data:
```

### Production App Configuration

```python
import os
from nexus import Nexus

app = Nexus(
    api_port=int(os.getenv("PORT", "8000")),
    api_host="0.0.0.0",
    enable_auth=True,           # Or set NEXUS_ENV=production for auto-enable
    rate_limit=1000,            # Default 100 req/min
    auto_discovery=False,       # Manual registration only
    max_concurrent_workflows=200,
    enable_caching=True,
    enable_monitoring=True,
    monitoring_backend="prometheus",
    session_backend="redis",
    redis_url=os.getenv("REDIS_URL"),
    log_level="INFO",
    log_format="json",
)
```

## Security (v1.1.1+)

Set `NEXUS_ENV=production` to auto-enable auth and rate limiting.

**Input validation** (automatic, all channels): dangerous keys blocked, 10MB input limit, path traversal prevention, 256-char key limit.

### MUST NOT

```python
app = Nexus(enable_auth=False)     # CRITICAL WARNING in production
app = Nexus(rate_limit=None)       # DoS vulnerability
app = Nexus(auto_discovery=True)   # 5-10s blocking delay
```

## Kubernetes

### Deployment + Service

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: nexus }
spec:
  replicas: 3
  selector: { matchLabels: { app: nexus } }
  template:
    metadata: { labels: { app: nexus } }
    spec:
      containers:
        - name: nexus
          image: nexus-app:latest
          ports:
            [
              { containerPort: 8000, name: api },
              { containerPort: 3001, name: mcp },
            ]
          env:
            - {
                name: DATABASE_URL,
                valueFrom:
                  { secretKeyRef: { name: nexus-secrets, key: database-url } },
              }
            - {
                name: REDIS_URL,
                valueFrom:
                  { secretKeyRef: { name: nexus-secrets, key: redis-url } },
              }
          resources:
            requests: { memory: "512Mi", cpu: "500m" }
            limits: { memory: "2Gi", cpu: "2000m" }
          livenessProbe:
            {
              httpGet: { path: /health, port: 8000 },
              initialDelaySeconds: 30,
              periodSeconds: 10,
            }
          readinessProbe:
            {
              httpGet: { path: /health, port: 8000 },
              initialDelaySeconds: 5,
              periodSeconds: 5,
            }
---
apiVersion: v1
kind: Service
metadata: { name: nexus }
spec:
  selector: { app: nexus }
  ports: [{ name: api, port: 8000 }, { name: mcp, port: 3001 }]
  type: LoadBalancer
```

### HPA (Horizontal Pod Autoscaler)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata: { name: nexus-hpa }
spec:
  scaleTargetRef: { apiVersion: apps/v1, kind: Deployment, name: nexus }
  minReplicas: 3
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        { name: cpu, target: { type: Utilization, averageUtilization: 70 } }
```

### Deploy Commands

```bash
kubectl create namespace nexus
kubectl apply -f k8s/ -n nexus
kubectl get pods -n nexus
kubectl scale deployment/nexus --replicas=5 -n nexus
```

## Production Checklist

| Setting                   | Value       | Why                             |
| ------------------------- | ----------- | ------------------------------- |
| `auto_discovery=False`    | Always      | Prevents blocking with DataFlow |
| `enable_auth=True`        | Production  | Or use NEXUS_ENV=production     |
| `rate_limit=N`            | 100-5000    | DoS protection                  |
| `session_backend="redis"` | Distributed | Multi-replica session sharing   |
| `enable_monitoring=True`  | Always      | Prometheus metrics at /metrics  |
| `log_format="json"`       | Production  | Machine-parseable logs          |

## CI/CD (GitHub Actions)

```yaml
name: Deploy
on: { push: { branches: [main] } }
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: docker build -t nexus-app:${{ github.sha }} .
      - run: docker push registry.example.com/nexus-app:${{ github.sha }}
      - run: kubectl set image deployment/nexus nexus=registry.example.com/nexus-app:${{ github.sha }} -n nexus
```
