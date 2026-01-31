---
name: deployment-patterns
description: "Docker and Kubernetes deployment patterns for containerized applications. Use for 'Docker Compose', 'Kubernetes deployment', 'container orchestration', 'health checks', or 'secrets management'."
---

# Deployment Patterns

> **Skill Metadata**
> Category: `deployment`
> Priority: `HIGH`
> Technologies: Docker, Docker Compose, Kubernetes

## Docker Compose Service Architecture

```yaml
version: '3.8'

services:
  # Backend API Service
  backend:
    build:
      context: .
      dockerfile: docker/Dockerfile.backend
      target: ${BUILD_TARGET:-production}
      args:
        - PYTHON_VERSION=${PYTHON_VERSION:-3.10}
    container_name: ${PROJECT_NAME}_backend
    environment:
      - ENVIRONMENT=${ENVIRONMENT:-production}
      - DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
    ports:
      - "${BACKEND_PORT:-8000}:8000"
    volumes:
      - ./backend:/app/backend:cached
      - backend_logs:/var/log/app
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - app_frontend
      - app_backend
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  # PostgreSQL Database
  postgres:
    image: postgres:15-alpine
    container_name: ${PROJECT_NAME}_postgres
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_HOST_AUTH_METHOD: scram-sha-256
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./docker/init-scripts:/docker-entrypoint-initdb.d/
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s
    networks:
      - app_backend
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G

  # Redis Cache
  redis:
    image: redis:7-alpine
    container_name: ${PROJECT_NAME}_redis
    ports:
      - "${REDIS_PORT:-6379}:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - app_backend
    restart: unless-stopped
    command: >
      redis-server
      --appendonly yes
      --appendfsync everysec
      --maxmemory 1gb
      --maxmemory-policy allkeys-lru
      --requirepass ${REDIS_PASSWORD}

volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local
  backend_logs:
    driver: local

networks:
  app_frontend:
    driver: bridge
  app_backend:
    driver: bridge
    internal: true  # No external access for security
```

## Environment Configuration Template

```bash
# ==============================================================================
# APPLICATION ENVIRONMENT
# ==============================================================================

ENVIRONMENT=production
DEBUG=false
BUILD_TARGET=production

# ==============================================================================
# DATABASE CONFIGURATION (PostgreSQL)
# ==============================================================================

POSTGRES_DB=app_db
POSTGRES_USER=app_user
POSTGRES_PASSWORD=change_this_to_secure_password
POSTGRES_PORT=5432

DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=40
DATABASE_POOL_TIMEOUT=30

# ==============================================================================
# REDIS CONFIGURATION
# ==============================================================================

REDIS_PASSWORD=change_this_to_secure_redis_password
REDIS_PORT=6379
REDIS_EXPIRE_SECONDS=7200
REDIS_MAX_CONNECTIONS=50

# ==============================================================================
# AUTHENTICATION AND SECURITY
# ==============================================================================

# Generate with: openssl rand -hex 32
JWT_SECRET_KEY=change_this_to_a_secure_random_key_minimum_32_characters
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=480

# ==============================================================================
# CORS AND FRONTEND
# ==============================================================================

CORS_ORIGINS=http://localhost:3000,https://app.yourdomain.com
FRONTEND_URL=https://app.yourdomain.com

# ==============================================================================
# SERVICE PORTS
# ==============================================================================

BACKEND_PORT=8000
FRONTEND_PORT=3000

# ==============================================================================
# SECURITY NOTES
# ==============================================================================
# 1. NEVER commit .env files to version control
# 2. Generate secrets with: openssl rand -hex 32
# 3. Use secrets management tools (Vault, AWS Secrets Manager)
# 4. Rotate secrets regularly
```

## Secret Generation Commands

```bash
# JWT Secret Key (32 bytes = 64 hex characters)
openssl rand -hex 32

# Database Password (16 bytes = 32 hex characters)
openssl rand -hex 16

# Redis Password (16 bytes = 32 hex characters)
openssl rand -hex 16

# Strong alphanumeric password (24 characters)
openssl rand -base64 24
```

## Kubernetes Deployment

### Backend Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  labels:
    app: backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      containers:
      - name: backend
        image: your-registry/backend:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: database-url
        - name: JWT_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: jwt-secret
        envFrom:
        - configMapRef:
            name: app-config
        resources:
          requests:
            cpu: 500m
            memory: 1Gi
          limits:
            cpu: 2000m
            memory: 4Gi
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: backend-service
spec:
  selector:
    app: backend
  ports:
  - protocol: TCP
    port: 8000
    targetPort: 8000
  type: ClusterIP
```

### PostgreSQL StatefulSet

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
spec:
  serviceName: postgres
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15-alpine
        ports:
        - containerPort: 5432
        env:
        - name: POSTGRES_DB
          valueFrom:
            configMapKeyRef:
              name: app-config
              key: POSTGRES_DB
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: postgres-password
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
        resources:
          requests:
            cpu: 500m
            memory: 2Gi
          limits:
            cpu: 2000m
            memory: 4Gi
  volumeClaimTemplates:
  - metadata:
      name: postgres-storage
    spec:
      accessModes: [ "ReadWriteOnce" ]
      resources:
        requests:
          storage: 50Gi
```

### Horizontal Pod Autoscaler

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: backend-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: backend
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### ConfigMap and Secrets

```yaml
# ConfigMap (non-sensitive configuration)
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
data:
  ENVIRONMENT: "production"
  LOG_LEVEL: "INFO"
  POSTGRES_DB: "app_db"
---
# Secrets (sensitive data)
apiVersion: v1
kind: Secret
metadata:
  name: app-secrets
type: Opaque
data:
  # Base64-encoded values
  database-url: cG9zdGdyZXNxbDovL3VzZXI6cGFzc0Bwb3N0Z3Jlczo1NDMyL2RiCg==
  jwt-secret: Y2hhbmdlX3RoaXNfdG9fc2VjdXJlX2tleQo=
```

## Common Deployment Workflows

### Initial Setup (Docker Compose)

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Generate secure secrets
JWT_SECRET=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -hex 16)
REDIS_PASSWORD=$(openssl rand -hex 16)

# 3. Update .env file
sed -i "s/change_this_to_a_secure_random_key_minimum_32_characters/$JWT_SECRET/" .env
sed -i "s/change_this_to_secure_password/$POSTGRES_PASSWORD/" .env
sed -i "s/change_this_to_secure_redis_password/$REDIS_PASSWORD/" .env

# 4. Start services
docker-compose up -d

# 5. Check service health
docker-compose ps
docker-compose logs -f backend

# 6. Verify API health
curl http://localhost:8000/health
```

### Production Deployment (Kubernetes)

```bash
# 1. Create namespace
kubectl create namespace production

# 2. Create secrets
kubectl create secret generic app-secrets \
  --from-literal=database-url="postgresql://user:pass@postgres:5432/db" \
  --from-literal=jwt-secret="$(openssl rand -hex 32)" \
  --namespace=production

# 3. Create ConfigMap
kubectl create configmap app-config \
  --from-env-file=.env.production \
  --namespace=production

# 4. Apply deployments
kubectl apply -f k8s/postgres-statefulset.yaml -n production
kubectl apply -f k8s/backend-deployment.yaml -n production

# 5. Apply HPA
kubectl apply -f k8s/hpa.yaml -n production

# 6. Verify deployment
kubectl get pods -n production
kubectl describe hpa backend-hpa -n production
```

### Rolling Update (Zero Downtime)

```bash
# Update image
kubectl set image deployment/backend \
  backend=your-registry/backend:v2.0.0 \
  --namespace=production

# Monitor rollout
kubectl rollout status deployment/backend -n production

# Rollback if needed
kubectl rollout undo deployment/backend -n production
```

## Health Check Patterns

### Application Health Endpoints (Python)

```python
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

app = FastAPI()

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Liveness probe - is the application running?"""
    return {"status": "healthy"}

@app.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check():
    """Readiness probe - can the application serve traffic?"""
    try:
        await db.execute("SELECT 1")
        await redis.ping()
        return {"status": "ready"}
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not ready", "error": str(e)}
        )
```

### Docker Compose Health Checks

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s      # Check every 30 seconds
  timeout: 10s       # Wait 10 seconds for response
  retries: 3         # Retry 3 times before marking unhealthy
  start_period: 40s  # Wait 40 seconds before starting checks
```

### Kubernetes Probes

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 5
  successThreshold: 1
  failureThreshold: 3
```

## Troubleshooting Commands

### Service Issues

```bash
# Check logs
docker-compose logs -f backend
kubectl logs -f deployment/backend -n production

# Check health
docker-compose ps
kubectl get pods -n production

# Verify environment variables
docker-compose exec backend env | grep DATABASE_URL
kubectl exec -it pod/backend-xyz -n production -- env | grep DATABASE_URL

# Check network connectivity
docker-compose exec backend ping postgres
kubectl exec -it pod/backend-xyz -n production -- nc -zv postgres 5432
```

### Database Connection

```bash
# Verify PostgreSQL is running
docker-compose ps postgres
kubectl get pods -l app=postgres -n production

# Test connection from backend
docker-compose exec backend psql -h postgres -U app_user -d app_db
```

### Resource Usage

```bash
# Check resource usage
docker stats
kubectl top pods -n production
kubectl top nodes
```

<!-- Trigger Keywords: Docker Compose, Kubernetes deployment, container orchestration, health checks, secrets management, docker deployment, k8s deployment, environment variables, docker secrets, kubernetes secrets -->
