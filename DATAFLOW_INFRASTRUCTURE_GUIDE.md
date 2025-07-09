# DataFlow Infrastructure Setup Guide

## Quick Start with Docker

### 1. Prerequisites
```bash
# Install Docker and Docker Compose
# macOS: brew install docker docker-compose
# Ubuntu: sudo apt-get install docker docker-compose
# Windows: Download Docker Desktop
```

### 2. Infrastructure Configuration

Create `docker-compose.yml`:
```yaml
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: dataflow_db
      POSTGRES_USER: dataflow_user
      POSTGRES_PASSWORD: your_secure_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U dataflow_user -d dataflow_db"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6380:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
  redis_data:
```

### 3. Start Infrastructure
```bash
# Start services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

### 4. DataFlow Configuration

```python
# config.py
import os
from kailash_dataflow import DataFlow

# Production configuration
db = DataFlow(
    database_url=os.getenv("DATABASE_URL", "postgresql://dataflow_user:your_secure_password@localhost:5432/dataflow_db"),
    redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    pool_size=20,
    pool_max_overflow=50,
    pool_recycle=3600,
    monitoring=True,
    multi_tenant=True
)

# Environment variables
os.environ["DATABASE_URL"] = "postgresql://dataflow_user:your_secure_password@localhost:5432/dataflow_db"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
```

### 5. Production Deployment

```python
# production_workflow.py
from kailash_dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Initialize with production config
db = DataFlow(
    database_url="postgresql://user:pass@production-db:5432/dataflow",
    redis_url="redis://production-redis:6379/0",
    pool_size=50,
    monitoring=True,
    multi_tenant=True,
    security_enabled=True
)

# Define production model
@db.model
class Order:
    customer_id: int
    total: float
    status: str = 'pending'

    __dataflow__ = {
        'multi_tenant': True,
        'versioned': True,
        'encrypted_fields': ['customer_id']
    }

# Production workflow
workflow = WorkflowBuilder()

# High-performance order processing
workflow.add_node("OrderBulkCreateNode", "process_orders", {
    "data": order_batch,
    "batch_size": 1000,
    "conflict_resolution": "upsert"
})

# Real-time analytics
workflow.add_node("AnalyticsNode", "track_orders", {
    "events": [
        {"type": "order_created", "data": ":order_data"}
    ]
})

# Execute with monitoring
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### 6. Monitoring & Observability

```python
# monitoring.py
from kailash_dataflow import DataFlow

# Enable comprehensive monitoring
db = DataFlow(
    monitoring=True,
    metrics_endpoint="/metrics",
    health_check_endpoint="/health",
    slow_query_threshold=1.0,
    export_format="prometheus"
)

# Access monitoring data
monitor = db.get_monitor()
metrics = monitor.get_metrics()
health = monitor.get_health_status()
```

### 7. Scaling Configuration

```python
# scaling.py
from kailash_dataflow import DataFlow

# Horizontal scaling setup
db = DataFlow(
    # Primary database
    database_url="postgresql://primary:5432/dataflow",

    # Read replicas
    read_replicas=[
        "postgresql://replica1:5432/dataflow",
        "postgresql://replica2:5432/dataflow"
    ],

    # Distributed cache
    redis_cluster=[
        "redis://redis1:6379",
        "redis://redis2:6379",
        "redis://redis3:6379"
    ],

    # Connection pooling
    pool_size=100,
    max_connections=1000,

    # Performance optimization
    connection_timeout=30,
    query_timeout=60,
    bulk_chunk_size=5000
)
```

### 8. Security Configuration

```python
# security.py
from kailash_dataflow import DataFlow

# Production security
db = DataFlow(
    database_url="postgresql://user:pass@secure-db:5432/dataflow",

    # Security features
    ssl_required=True,
    encrypt_at_rest=True,
    audit_logging=True,
    access_control=True,

    # Multi-tenancy
    multi_tenant=True,
    tenant_isolation_level="strict",

    # Compliance
    gdpr_mode=True,
    data_retention_days=365,
    automatic_backups=True
)
```

## Testing Your Setup

Run the comprehensive test:
```bash
python temp_dataflow_e2e_infrastructure.py
```

This will:
1. ✅ Setup Docker infrastructure
2. ✅ Test PostgreSQL integration
3. ✅ Test Redis caching
4. ✅ Test MongoDB analytics
5. ✅ Run production E2E scenario
6. ✅ Cleanup infrastructure

## Need Help?

- Documentation: [DataFlow User Guide](docs/USER_GUIDE.md)
- Examples: [Production Examples](examples/production/)
- Issues: [GitHub Issues](https://github.com/kailash/dataflow/issues)
