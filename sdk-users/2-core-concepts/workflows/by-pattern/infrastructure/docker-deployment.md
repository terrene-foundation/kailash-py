# Docker Deployment Workflows

Deploy your Kailash SDK workflows using Docker for consistent, scalable execution.

## Basic Docker Workflow

```python
"""Basic workflow that runs in Docker container"""
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.docker import DockerRuntime

# Create workflow
workflow = WorkflowBuilder()

# Add nodes
workflow.add_node("InputNode", "input", {})
workflow.add_node("CSVReaderNode", "reader", {})
workflow.add_node("DataTransformerNode", "transformer", {})
workflow.add_node("OutputNode", "output", {})

# Connect nodes
workflow.add_connection("input", "file_path", "reader", "file_path")
workflow.add_connection("reader", "data", "transformer", "input_data")
workflow.add_connection("transformer", "result", "output", "result")

# Run in Docker
runtime = DockerRuntime()
result = runtime.execute(
    workflow.build(),
    parameters={"file_path": "/data/input.csv"},
    docker_config={
        "image": "kailash-sdk:latest",
        "volumes": {"/local/data": "/data"},
        "environment": {"LOG_LEVEL": "INFO"}
    }
)

```

## Multi-Service Workflow

```python
"""Workflow using multiple Docker services"""
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# Database operations
workflow.add_node("DatabaseNode", "db_reader", {})

# Cache layer
workflow.add_node("CacheNode", "cache", {})

# Stream processing
workflow.add_node("StreamProcessorNode", "processor", {})

# Connect with caching strategy
workflow.add_connection("db_reader", "data", "cache", "data")
workflow.add_connection("cache", "data", "processor", "events")

# Docker Compose Configuration
docker_compose = """
version: '3.8'
services:
  workflow:
    build: .
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/mydb
      - REDIS_URL=redis://redis:6379
      - KAFKA_BROKERS=kafka:9092
    depends_on:
      - db
      - redis
      - kafka

  db:
    image: postgres:15
    environment:
      POSTGRES_PASSWORD: pass

  redis:
    image: redis:7-alpine

  kafka:
    image: confluentinc/cp-kafka:latest
    environment:
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
"""

```

## Production Deployment Pattern

```python
"""Production-ready Docker deployment"""
import os
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.docker import DockerRuntime
from kailash.security import SecurityConfig

# Create workflow
workflow = WorkflowBuilder()
# Load nodes from configuration or add them programmatically
# workflow.add_node("NodeType", "node_id", {})

# Configure security
security = SecurityConfig(
    enable_auth=True,
    api_key=os.environ["API_KEY"],
    allowed_origins=["https://app.example.com"]
)

# Production runtime configuration
runtime = DockerRuntime(
    security_config=security,
    resource_limits={
        "cpu": "2.0",
        "memory": "4g"
    },
    health_check={
        "endpoint": "/health",
        "interval": 30,
        "timeout": 10
    }
)

# Dockerfile for production
dockerfile = """
FROM python:3.11-slim

# Install dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Security: Non-root user
RUN useradd -m -u 1000 workflow && chown -R workflow:workflow /app
USER workflow

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# Run workflow API
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
"""

```

## Kubernetes Job Pattern

```python
"""Deploy workflow as Kubernetes Job"""
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.kubernetes import KubernetesRuntime

workflow = WorkflowBuilder()
# Add nodes to workflow

# Kubernetes Job manifest
k8s_job = {
    "apiVersion": "batch/v1",
    "kind": "Job",
    "metadata": {
        "name": "workflow-batch-processor"
    },
    "spec": {
        "template": {
            "spec": {
                "containers": [{
                    "name": "workflow",
                    "image": "myregistry/kailash-workflow:latest",
                    "env": [
                        {"name": "WORKFLOW_ID", "value": "batch-processor"},
                        {"name": "INPUT_PATH", "value": "/data/input"},
                        {"name": "OUTPUT_PATH", "value": "/data/output"}
                    ],
                    "volumeMounts": [{
                        "name": "data",
                        "mountPath": "/data"
                    }]
                }],
                "volumes": [{
                    "name": "data",
                    "persistentVolumeClaim": {
                        "claimName": "workflow-data"
                    }
                }],
                "restartPolicy": "OnFailure"
            }
        },
        "backoffLimit": 3
    }
}

# Deploy to Kubernetes
runtime = KubernetesRuntime()
runtime.deploy_job(workflow, k8s_job)

```

## Environment-Based Configuration

```python
"""Configure workflows for different environments"""
import os
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.docker import DockerRuntime
import yaml

# Load environment-specific config
env = os.environ.get("ENVIRONMENT", "development")
config_file = f"config/{env}.yaml"

# Create workflow using WorkflowBuilder
workflow = WorkflowBuilder()
# Load workflow configuration from YAML
with open("workflow.yaml", "r") as f:
    workflow_config = yaml.safe_load(f)
# Apply configuration to workflow (add nodes based on config)

# Environment-specific Docker settings
docker_configs = {
    "development": {
        "image": "kailash-dev:latest",
        "volumes": {"./data": "/data"},
        "ports": {"8000": "8000"}
    },
    "staging": {
        "image": "kailash-staging:latest",
        "replicas": 2,
        "health_check": True
    },
    "production": {
        "image": "kailash-prod:latest",
        "replicas": 5,
        "resource_limits": {"cpu": "4.0", "memory": "8g"},
        "auto_scaling": True
    }
}

runtime = DockerRuntime()
result, run_id = runtime.execute(workflow.build(), docker_config=docker_configs[env])

```

## Infrastructure as Code

```python
"""Complete infrastructure setup"""

# docker-compose.yml
compose_config = """
version: '3.8'

services:
  # Workflow API
  api:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/workflows
      - REDIS_URL=redis://redis:6379
      - MINIO_URL=http://minio:9000
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
      minio:
        condition: service_started
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  # PostgreSQL
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: workflows
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Redis
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data

  # MinIO (S3-compatible storage)
  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - minio_data:/data
    ports:
      - "9001:9001"  # Console

volumes:
  postgres_data:
  redis_data:
  minio_data:
"""

# Setup script
setup_script = """#!/bin/bash
# setup-infrastructure.sh

echo "Setting up Kailash workflow infrastructure..."

# Create necessary directories
mkdir -p data/input data/output logs

# Copy environment template
cp .env.example .env

# Build Docker image
docker compose build

# Start services
docker compose up -d

# Wait for services
echo "Waiting for services to be ready..."
sleep 10

# Run database migrations
docker compose exec api python -m kailash.db.migrate

# Create MinIO buckets
docker compose exec minio mc alias set local http://localhost:9000 minioadmin minioadmin
docker compose exec minio mc mb local/workflows

echo "Infrastructure ready! Access API at http://localhost:8000"
"""

```

## Best Practices

1. **Container Optimization**
   - Use multi-stage builds to reduce image size
   - Pin specific versions for reproducibility
   - Run as non-root user for security

2. **Resource Management**
   - Set appropriate CPU/memory limits
   - Use health checks for reliability
   - Implement graceful shutdown

3. **Configuration**
   - Use environment variables for config
   - Separate config by environment
   - Never hardcode secrets

4. **Monitoring**
   - Export metrics to Prometheus
   - Use structured logging
   - Set up alerts for failures

5. **Development Workflow**
   - Use docker-compose for local development
   - Hot reload for faster iteration
   - Consistent environments across team

## Troubleshooting

### Common Issues

1. **Container won't start**
   - Check logs: `docker logs <container>`
   - Verify environment variables
   - Ensure volumes are mounted correctly

2. **Connection errors**
   - Use service names, not localhost
   - Check network configuration
   - Verify service dependencies

3. **Performance issues**
   - Monitor resource usage
   - Optimize Docker build layers
   - Use appropriate base images

### Debug Commands

```bash
# View running containers
docker ps

# Check container logs
docker logs -f <container>

# Execute commands in container
docker exec -it <container> bash

# Inspect container configuration
docker inspect <container>

# Clean up resources
docker system prune -a
```
