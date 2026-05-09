---
skill: nexus-production-deployment
description: Production deployment patterns, Docker, Kubernetes, scaling, and health checks
priority: MEDIUM
tags: [nexus, production, deployment, docker, kubernetes, scaling]
---

# Nexus Production Deployment

## Shared Production Configuration

These settings apply across all SDKs:

```
app = Nexus(
    api_port=8000,          # Or from PORT env var
    auto_discovery=False,   # Manual registration only
    preset="enterprise",    # Or configure individually
)

# Register workflows explicitly
app.register("workflow-name", workflow.build())

# Add auth plugin
app.add_plugin(auth_plugin)

# Start
app.start()
```

## Production Checklist

| Setting          | Value            | Why                                     |
| ---------------- | ---------------- | --------------------------------------- |
| `auto_discovery` | `False`          | Prevents blocking with DataFlow         |
| Authentication   | Enabled          | Use NEXUS_ENV=production or auth plugin |
| Rate limiting    | 100-5000 req/min | DoS protection                          |
| Session backend  | Redis            | Multi-replica session sharing           |
| Monitoring       | Enabled          | Health and performance metrics          |
| Log format       | JSON             | Machine-parseable logs                  |

## Health Checks

```
health = app.health_check()
```

```bash
curl http://localhost:8000/health
# {"status": "healthy", "version": "...", "uptime": 3600, "workflows": 5}
```

## Docker

### Dockerfile

Adapt base image and build steps for your SDK language.

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
            - { containerPort: 8000, name: api }
            - { containerPort: 3001, name: mcp }
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef: { name: nexus-secrets, key: database-url }
            - name: REDIS_URL
              valueFrom:
                secretKeyRef: { name: nexus-secrets, key: redis-url }
          resources:
            requests: { memory: "512Mi", cpu: "500m" }
            limits: { memory: "2Gi", cpu: "2000m" }
          livenessProbe:
            httpGet: { path: /health, port: 8000 }
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet: { path: /health, port: 8000 }
            initialDelaySeconds: 5
            periodSeconds: 5
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
        name: cpu
        target: { type: Utilization, averageUtilization: 70 }
```

## MUST NOT in Production

- Disable auth without API gateway protection
- Disable rate limiting
- Enable auto-discovery (causes blocking delay)
- Hardcode secrets in source code

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

See language-specific variant for full constructor parameter lists and SDK-specific production configuration.
