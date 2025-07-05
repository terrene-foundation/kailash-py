# MCP Production Deployment Guide

## Overview

This guide provides comprehensive instructions for deploying MCP (Model Context Protocol) servers and clients in production environments. It covers deployment strategies, configuration management, scaling considerations, and operational best practices.

## Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Deployment Strategies](#deployment-strategies)
3. [Container Deployment](#container-deployment)
4. [Kubernetes Deployment](#kubernetes-deployment)
5. [Cloud Deployments](#cloud-deployments)
6. [Configuration Management](#configuration-management)
7. [Scaling Strategies](#scaling-strategies)
8. [High Availability](#high-availability)
9. [Disaster Recovery](#disaster-recovery)
10. [Operational Procedures](#operational-procedures)

## Pre-Deployment Checklist

### System Requirements

```yaml
# Minimum production requirements
mcp_server:
  cpu: 2 cores
  memory: 4GB
  disk: 20GB SSD
  network: 1Gbps

# Recommended for high-traffic
mcp_server_high_traffic:
  cpu: 8 cores
  memory: 16GB
  disk: 100GB SSD
  network: 10Gbps
```

### Security Checklist

- [ ] SSL/TLS certificates configured
- [ ] Authentication mechanism implemented
- [ ] API keys/tokens securely stored
- [ ] Network policies defined
- [ ] Firewall rules configured
- [ ] Secrets management system integrated
- [ ] Audit logging enabled
- [ ] Security scanning completed

### Performance Checklist

- [ ] Load testing completed
- [ ] Response time benchmarks met
- [ ] Resource limits defined
- [ ] Caching strategy implemented
- [ ] Database indexes optimized
- [ ] Connection pooling configured

## Deployment Strategies

### 1. Blue-Green Deployment

```bash
# Deploy green environment
kubectl apply -f mcp-server-green.yaml

# Test green environment
./scripts/health-check.sh green

# Switch traffic to green
kubectl patch service mcp-server -p '{"spec":{"selector":{"version":"green"}}}'

# Remove blue environment
kubectl delete deployment mcp-server-blue
```

### 2. Canary Deployment

```yaml
# Canary deployment with Istio
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: mcp-server
spec:
  hosts:
  - mcp-server
  http:
  - match:
    - headers:
        canary:
          exact: "true"
    route:
    - destination:
        host: mcp-server
        subset: v2
      weight: 100
  - route:
    - destination:
        host: mcp-server
        subset: v1
      weight: 90
    - destination:
        host: mcp-server
        subset: v2
      weight: 10
```

### 3. Rolling Update

```yaml
# Kubernetes rolling update
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-server
spec:
  replicas: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 1
  template:
    spec:
      containers:
      - name: mcp-server
        image: kailash/mcp-server:v2.0.0
```

## Container Deployment

### Docker Configuration

```dockerfile
# Production Dockerfile
FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Production image
FROM python:3.11-slim

# Copy virtual environment
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Add non-root user
RUN useradd -m -u 1000 mcp
USER mcp

# Copy application
WORKDIR /app
COPY --chown=mcp:mcp . .

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:3000/health')"

# Run
EXPOSE 3000
CMD ["python", "-m", "mcp_server", "--production"]
```

### Docker Compose Production

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  mcp-server:
    image: kailash/mcp-server:latest
    restart: always
    ports:
      - "3000:3000"
    environment:
      - MCP_ENV=production
      - MCP_LOG_LEVEL=info
      - MCP_AUTH_ENABLED=true
    volumes:
      - ./config:/app/config:ro
      - mcp-data:/app/data
    networks:
      - mcp-network
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  redis:
    image: redis:7-alpine
    restart: always
    volumes:
      - redis-data:/data
    networks:
      - mcp-network
    command: redis-server --requirepass ${REDIS_PASSWORD}

  prometheus:
    image: prom/prometheus:latest
    restart: always
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus-data:/prometheus
    networks:
      - mcp-network
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/usr/share/prometheus/console_libraries'
      - '--web.console.templates=/usr/share/prometheus/consoles'

volumes:
  mcp-data:
  redis-data:
  prometheus-data:

networks:
  mcp-network:
    driver: bridge
```

## Kubernetes Deployment

### Complete Kubernetes Manifest

```yaml
# mcp-server-deployment.yaml
---
apiVersion: v1
kind: Namespace
metadata:
  name: mcp-system
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: mcp-server-config
  namespace: mcp-system
data:
  config.yaml: |
    server:
      port: 3000
      transport: sse
      timeout: 30s
    auth:
      enabled: true
      type: jwt
    monitoring:
      metrics_enabled: true
      tracing_enabled: true
---
apiVersion: v1
kind: Secret
metadata:
  name: mcp-server-secrets
  namespace: mcp-system
type: Opaque
stringData:
  jwt-secret: "your-jwt-secret"
  db-password: "your-db-password"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-server
  namespace: mcp-system
  labels:
    app: mcp-server
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mcp-server
  template:
    metadata:
      labels:
        app: mcp-server
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "9090"
    spec:
      serviceAccountName: mcp-server
      containers:
      - name: mcp-server
        image: kailash/mcp-server:v1.0.0
        imagePullPolicy: Always
        ports:
        - containerPort: 3000
          name: http
        - containerPort: 9090
          name: metrics
        env:
        - name: MCP_ENV
          value: "production"
        - name: JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: mcp-server-secrets
              key: jwt-secret
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: mcp-server-secrets
              key: db-password
        volumeMounts:
        - name: config
          mountPath: /app/config
          readOnly: true
        - name: data
          mountPath: /app/data
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 3000
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /ready
            port: 3000
          initialDelaySeconds: 10
          periodSeconds: 10
        securityContext:
          runAsNonRoot: true
          runAsUser: 1000
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
      volumes:
      - name: config
        configMap:
          name: mcp-server-config
      - name: data
        emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: mcp-server
  namespace: mcp-system
  labels:
    app: mcp-server
spec:
  type: ClusterIP
  ports:
  - port: 80
    targetPort: 3000
    protocol: TCP
    name: http
  - port: 9090
    targetPort: 9090
    protocol: TCP
    name: metrics
  selector:
    app: mcp-server
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: mcp-server-hpa
  namespace: mcp-system
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: mcp-server
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
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: mcp-server
  namespace: mcp-system
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/rate-limit: "100"
spec:
  tls:
  - hosts:
    - mcp.example.com
    secretName: mcp-server-tls
  rules:
  - host: mcp.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: mcp-server
            port:
              number: 80
```

### Helm Chart

```yaml
# Chart.yaml
apiVersion: v2
name: mcp-server
description: MCP Server Helm chart for Kubernetes
type: application
version: 1.0.0
appVersion: "1.0.0"

# values.yaml
replicaCount: 3

image:
  repository: kailash/mcp-server
  pullPolicy: IfNotPresent
  tag: "latest"

service:
  type: ClusterIP
  port: 80

ingress:
  enabled: true
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: mcp.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: mcp-server-tls
      hosts:
        - mcp.example.com

resources:
  limits:
    cpu: 1000m
    memory: 2Gi
  requests:
    cpu: 500m
    memory: 1Gi

autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80

nodeSelector: {}
tolerations: []
affinity: {}

persistence:
  enabled: true
  storageClass: "fast-ssd"
  accessMode: ReadWriteOnce
  size: 10Gi

redis:
  enabled: true
  auth:
    enabled: true
    password: "changeme"

postgresql:
  enabled: true
  auth:
    postgresPassword: "changeme"
    database: "mcp"
```

## Cloud Deployments

### AWS Deployment

```terraform
# terraform/aws/main.tf
provider "aws" {
  region = var.aws_region
}

# ECS Task Definition
resource "aws_ecs_task_definition" "mcp_server" {
  family                   = "mcp-server"
  network_mode            = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                     = "1024"
  memory                  = "2048"
  execution_role_arn      = aws_iam_role.ecs_execution_role.arn
  task_role_arn          = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name  = "mcp-server"
      image = "${aws_ecr_repository.mcp_server.repository_url}:latest"

      portMappings = [
        {
          containerPort = 3000
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "MCP_ENV"
          value = "production"
        }
      ]

      secrets = [
        {
          name      = "JWT_SECRET"
          valueFrom = aws_secretsmanager_secret.jwt_secret.arn
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.mcp_server.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:3000/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])
}

# ECS Service
resource "aws_ecs_service" "mcp_server" {
  name            = "mcp-server"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.mcp_server.arn
  desired_count   = 3
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.mcp_server.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.mcp_server.arn
    container_name   = "mcp-server"
    container_port   = 3000
  }

  deployment_configuration {
    maximum_percent         = 200
    minimum_healthy_percent = 100
  }

  enable_ecs_managed_tags = true
  propagate_tags          = "SERVICE"
}

# Application Load Balancer
resource "aws_lb" "mcp_server" {
  name               = "mcp-server-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets           = aws_subnet.public[*].id

  enable_deletion_protection = true
  enable_http2              = true

  tags = {
    Name = "mcp-server-alb"
  }
}

# Auto Scaling
resource "aws_appautoscaling_target" "mcp_server" {
  max_capacity       = 10
  min_capacity       = 3
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.mcp_server.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "mcp_server_cpu" {
  name               = "mcp-server-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.mcp_server.resource_id
  scalable_dimension = aws_appautoscaling_target.mcp_server.scalable_dimension
  service_namespace  = aws_appautoscaling_target.mcp_server.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = 70.0
  }
}
```

### GCP Deployment

```yaml
# Cloud Run deployment
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: mcp-server
  annotations:
    run.googleapis.com/ingress: all
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/minScale: "3"
        autoscaling.knative.dev/maxScale: "100"
        run.googleapis.com/cpu-throttling: "false"
    spec:
      containerConcurrency: 1000
      timeoutSeconds: 300
      serviceAccountName: mcp-server@project.iam.gserviceaccount.com
      containers:
      - image: gcr.io/project/mcp-server:latest
        ports:
        - name: http1
          containerPort: 3000
        env:
        - name: MCP_ENV
          value: "production"
        - name: JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: jwt-secret
              key: latest
        resources:
          limits:
            cpu: "2"
            memory: "4Gi"
        livenessProbe:
          httpGet:
            path: /health
          initialDelaySeconds: 30
          periodSeconds: 30
        startupProbe:
          httpGet:
            path: /health
          initialDelaySeconds: 0
          periodSeconds: 5
          failureThreshold: 10
```

### Azure Deployment

```json
// Azure Container Instances deployment
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "containerGroupName": {
      "type": "string",
      "defaultValue": "mcp-server-group"
    }
  },
  "resources": [
    {
      "type": "Microsoft.ContainerInstance/containerGroups",
      "apiVersion": "2021-09-01",
      "name": "[parameters('containerGroupName')]",
      "location": "[resourceGroup().location]",
      "properties": {
        "containers": [
          {
            "name": "mcp-server",
            "properties": {
              "image": "kailash.azurecr.io/mcp-server:latest",
              "ports": [
                {
                  "port": 3000,
                  "protocol": "TCP"
                }
              ],
              "environmentVariables": [
                {
                  "name": "MCP_ENV",
                  "value": "production"
                },
                {
                  "name": "JWT_SECRET",
                  "secureValue": "[parameters('jwtSecret')]"
                }
              ],
              "resources": {
                "requests": {
                  "cpu": 2,
                  "memoryInGB": 4
                }
              },
              "livenessProbe": {
                "httpGet": {
                  "path": "/health",
                  "port": 3000
                },
                "initialDelaySeconds": 30,
                "periodSeconds": 30
              }
            }
          }
        ],
        "osType": "Linux",
        "ipAddress": {
          "type": "Public",
          "ports": [
            {
              "port": 443,
              "protocol": "TCP"
            }
          ],
          "dnsNameLabel": "mcp-server"
        },
        "sku": "Standard"
      }
    }
  ]
}
```

## Configuration Management

### Environment-Based Configuration

```python
# config/production.py
import os
from typing import Dict, Any

class ProductionConfig:
    """Production configuration"""

    # Server settings
    SERVER_HOST = "0.0.0.0"
    SERVER_PORT = int(os.getenv("MCP_PORT", "3000"))
    SERVER_WORKERS = int(os.getenv("MCP_WORKERS", "4"))

    # Security
    AUTH_ENABLED = True
    AUTH_TYPE = os.getenv("MCP_AUTH_TYPE", "jwt")
    JWT_SECRET = os.getenv("JWT_SECRET")
    JWT_EXPIRY = int(os.getenv("JWT_EXPIRY", "3600"))

    # SSL/TLS
    SSL_ENABLED = True
    SSL_CERT_FILE = os.getenv("SSL_CERT_FILE", "/certs/server.crt")
    SSL_KEY_FILE = os.getenv("SSL_KEY_FILE", "/certs/server.key")

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL")
    DATABASE_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "20"))
    DATABASE_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))

    # Redis
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "50"))

    # Monitoring
    METRICS_ENABLED = True
    METRICS_PORT = int(os.getenv("METRICS_PORT", "9090"))
    TRACING_ENABLED = True
    TRACING_ENDPOINT = os.getenv("TRACING_ENDPOINT")

    # Rate limiting
    RATE_LIMIT_ENABLED = True
    RATE_LIMIT_DEFAULT = "100/minute"
    RATE_LIMIT_STORAGE = "redis"

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT = "json"
    LOG_OUTPUT = os.getenv("LOG_OUTPUT", "stdout")

    @classmethod
    def validate(cls) -> None:
        """Validate required configuration"""
        required = ["JWT_SECRET", "DATABASE_URL"]
        missing = [var for var in required if not getenv(var)]
        if missing:
            raise ValueError(f"Missing required config: {missing}")
```

### Secret Management

```python
# secrets/manager.py
from typing import Dict, Any
import boto3
import google.cloud.secretmanager
from azure.keyvault.secrets import SecretClient

class SecretManager:
    """Multi-cloud secret management"""

    def __init__(self, provider: str):
        self.provider = provider
        self._init_client()

    def _init_client(self):
        if self.provider == "aws":
            self.client = boto3.client('secretsmanager')
        elif self.provider == "gcp":
            self.client = google.cloud.secretmanager.SecretManagerServiceClient()
        elif self.provider == "azure":
            credential = DefaultAzureCredential()
            self.client = SecretClient(
                vault_url="https://mcp-vault.vault.azure.net/",
                credential=credential
            )

    def get_secret(self, secret_id: str) -> str:
        """Get secret value"""
        if self.provider == "aws":
            response = self.client.get_secret_value(SecretId=secret_id)
            return response['SecretString']
        elif self.provider == "gcp":
            name = f"projects/{self.project}/secrets/{secret_id}/versions/latest"
            response = self.client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")
        elif self.provider == "azure":
            return self.client.get_secret(secret_id).value
```

## Scaling Strategies

### Horizontal Scaling

```python
# scaling/horizontal.py
import asyncio
from typing import List
import aioredis

class LoadBalancer:
    """Simple round-robin load balancer"""

    def __init__(self, servers: List[str]):
        self.servers = servers
        self.current = 0
        self.health_checker = HealthChecker(servers)

    async def get_server(self) -> str:
        """Get next healthy server"""
        healthy_servers = await self.health_checker.get_healthy_servers()
        if not healthy_servers:
            raise NoHealthyServersError()

        server = healthy_servers[self.current % len(healthy_servers)]
        self.current += 1
        return server

class AutoScaler:
    """Automatic scaling based on metrics"""

    def __init__(self, min_instances: int = 3, max_instances: int = 10):
        self.min_instances = min_instances
        self.max_instances = max_instances
        self.current_instances = min_instances

    async def scale_decision(self, metrics: Dict[str, float]) -> int:
        """Decide how many instances we need"""
        cpu_usage = metrics.get('cpu_usage', 0)
        memory_usage = metrics.get('memory_usage', 0)
        request_rate = metrics.get('request_rate', 0)

        # Scale up conditions
        if cpu_usage > 80 or memory_usage > 85 or request_rate > 1000:
            return min(self.current_instances + 2, self.max_instances)

        # Scale down conditions
        if cpu_usage < 20 and memory_usage < 30 and request_rate < 100:
            return max(self.current_instances - 1, self.min_instances)

        return self.current_instances
```

### Vertical Scaling

```yaml
# Resource optimization profiles
profiles:
  small:
    cpu: 1
    memory: 2Gi
    connections: 100

  medium:
    cpu: 2
    memory: 4Gi
    connections: 500

  large:
    cpu: 4
    memory: 8Gi
    connections: 1000

  xlarge:
    cpu: 8
    memory: 16Gi
    connections: 2000
```

## High Availability

### Multi-Region Deployment

```python
# ha/multi_region.py
class MultiRegionMCPServer:
    """Multi-region MCP server with failover"""

    def __init__(self):
        self.regions = {
            'us-east-1': 'mcp-us-east.example.com',
            'eu-west-1': 'mcp-eu-west.example.com',
            'ap-south-1': 'mcp-ap-south.example.com'
        }
        self.primary_region = 'us-east-1'

    async def handle_request(self, request: MCPRequest):
        """Route request to appropriate region"""
        # Try primary region first
        try:
            return await self._send_to_region(
                self.primary_region,
                request
            )
        except RegionUnavailableError:
            # Failover to closest available region
            closest = await self._find_closest_region(request.client_location)
            return await self._send_to_region(closest, request)
```

### Database Replication

```yaml
# PostgreSQL HA configuration
postgresql:
  architecture: replication
  replication:
    enabled: true
    slaveReplicas: 2
    synchronousCommit: "on"
    numSynchronousReplicas: 1

  primary:
    persistence:
      enabled: true
      size: 100Gi
      storageClass: fast-ssd

  readReplicas:
    persistence:
      enabled: true
      size: 100Gi

  metrics:
    enabled: true
    serviceMonitor:
      enabled: true
```

## Disaster Recovery

### Backup Strategy

```bash
#!/bin/bash
# backup.sh - Automated backup script

# Configuration
BACKUP_DIR="/backups"
S3_BUCKET="mcp-backups"
RETENTION_DAYS=30

# Database backup
echo "Backing up database..."
pg_dump $DATABASE_URL | gzip > "$BACKUP_DIR/db-$(date +%Y%m%d-%H%M%S).sql.gz"

# Application state backup
echo "Backing up application state..."
tar -czf "$BACKUP_DIR/state-$(date +%Y%m%d-%H%M%S).tar.gz" /app/data

# Upload to S3
echo "Uploading to S3..."
aws s3 sync "$BACKUP_DIR" "s3://$S3_BUCKET/" --storage-class GLACIER

# Clean old backups
echo "Cleaning old backups..."
find "$BACKUP_DIR" -type f -mtime +$RETENTION_DAYS -delete

# Verify backups
echo "Verifying backups..."
aws s3 ls "s3://$S3_BUCKET/" --recursive | tail -10
```

### Recovery Procedures

```python
# recovery/disaster_recovery.py
class DisasterRecovery:
    """Disaster recovery procedures"""

    async def restore_from_backup(self, backup_id: str):
        """Restore system from backup"""

        # 1. Download backup
        backup_path = await self.download_backup(backup_id)

        # 2. Restore database
        await self.restore_database(backup_path)

        # 3. Restore application state
        await self.restore_state(backup_path)

        # 4. Verify restoration
        if not await self.verify_restoration():
            raise RestorationFailedError()

        # 5. Resume operations
        await self.resume_operations()

    async def failover_to_dr_site(self):
        """Failover to DR site"""

        # 1. Verify DR site is ready
        if not await self.verify_dr_site():
            raise DRSiteNotReadyError()

        # 2. Update DNS
        await self.update_dns_to_dr()

        # 3. Sync final data
        await self.sync_final_data()

        # 4. Activate DR site
        await self.activate_dr_site()
```

## Operational Procedures

### Deployment Checklist

```markdown
## Pre-Deployment
- [ ] Code review completed
- [ ] Tests passing (unit, integration, e2e)
- [ ] Security scan completed
- [ ] Performance benchmarks met
- [ ] Documentation updated
- [ ] Change request approved

## Deployment
- [ ] Backup current state
- [ ] Deploy to staging
- [ ] Run smoke tests
- [ ] Deploy to production (canary/blue-green)
- [ ] Monitor metrics
- [ ] Verify health checks

## Post-Deployment
- [ ] Monitor error rates
- [ ] Check performance metrics
- [ ] Verify all features working
- [ ] Update status page
- [ ] Send deployment notification
```

### Monitoring Setup

```python
# monitoring/setup.py
from prometheus_client import Counter, Histogram, Gauge
import time

# Metrics
request_count = Counter(
    'mcp_requests_total',
    'Total MCP requests',
    ['method', 'status']
)

request_duration = Histogram(
    'mcp_request_duration_seconds',
    'MCP request duration',
    ['method']
)

active_connections = Gauge(
    'mcp_active_connections',
    'Active MCP connections'
)

class MetricsMiddleware:
    """Middleware for collecting metrics"""

    async def __call__(self, request, call_next):
        start_time = time.time()

        # Track active connections
        active_connections.inc()

        try:
            response = await call_next(request)

            # Record metrics
            request_count.labels(
                method=request.method,
                status=response.status_code
            ).inc()

            request_duration.labels(
                method=request.method
            ).observe(time.time() - start_time)

            return response

        finally:
            active_connections.dec()
```

### Runbook Template

```markdown
# MCP Server Runbook

## Service Information
- **Service**: MCP Server
- **Owner**: Platform Team
- **SLA**: 99.9% uptime
- **Critical**: Yes

## Common Issues

### High CPU Usage
**Symptoms**: CPU > 80% for > 5 minutes
**Resolution**:
1. Check request patterns: `kubectl top pods -n mcp-system`
2. Scale horizontally: `kubectl scale deployment mcp-server --replicas=5`
3. Check for inefficient queries in logs
4. Enable request rate limiting if needed

### Memory Leak
**Symptoms**: Gradual memory increase, OOM kills
**Resolution**:
1. Identify leaking endpoint from metrics
2. Capture heap dump: `kubectl exec $POD -- python -m pyheapdump`
3. Restart affected pods: `kubectl rollout restart deployment mcp-server`
4. Deploy fix and monitor

### Database Connection Issues
**Symptoms**: "Connection pool exhausted" errors
**Resolution**:
1. Check connection pool metrics
2. Increase pool size if needed
3. Check for connection leaks
4. Review slow query log

## Emergency Procedures

### Complete Outage
1. Check infrastructure status
2. Verify DNS resolution
3. Check load balancer health
4. Review recent deployments
5. Initiate DR procedures if needed

### Data Corruption
1. Stop writes immediately
2. Identify corruption extent
3. Restore from last known good backup
4. Verify data integrity
5. Resume operations

## Contact Information
- **On-Call**: +1-555-ONCALL
- **Escalation**: platform-team@example.com
- **Management**: cto@example.com
```

## Best Practices Summary

1. **Always use health checks** - Ensure services are ready before routing traffic
2. **Implement graceful shutdown** - Handle SIGTERM properly
3. **Use connection pooling** - Reuse connections to external services
4. **Enable monitoring from day 1** - You can't fix what you can't measure
5. **Automate everything** - Deployments, scaling, backups
6. **Plan for failure** - Have DR procedures ready
7. **Document operational procedures** - Keep runbooks updated
8. **Regular disaster recovery drills** - Practice makes perfect
9. **Security first** - Never compromise on security
10. **Monitor costs** - Cloud resources can be expensive

## Conclusion

Successful MCP deployment requires careful planning, robust automation, and continuous monitoring. By following this guide and adapting it to your specific needs, you can build a reliable, scalable, and secure MCP deployment that meets your production requirements.
