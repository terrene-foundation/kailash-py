# DataFlow Production Deployment

Complete guide to deploying DataFlow applications in production environments.

## Overview

DataFlow is designed for production deployment with enterprise-grade features built-in. This guide covers deployment strategies, configuration, monitoring, and best practices for running DataFlow in production.

## Deployment Architecture

### Recommended Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Load Balancer │    │   Application   │    │    Database     │
│    (HAProxy)    │────│    Servers      │────│   (PostgreSQL)  │
│                 │    │   (DataFlow)    │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                       ┌─────────────────┐
                       │     Cache       │
                       │    (Redis)      │
                       └─────────────────┘
```

### Component Breakdown

1. **Load Balancer**: Distributes traffic across application servers
2. **Application Servers**: Run DataFlow applications
3. **Database**: Primary data storage (PostgreSQL recommended)
4. **Cache**: Redis for query caching and session storage
5. **Monitoring**: Prometheus + Grafana for metrics
6. **Logging**: ELK stack for centralized logging

## Environment Configuration

### Production Configuration

```python
# config/production.py
import os
from kailash_dataflow import DataFlow, DataFlowConfig
from kailash_dataflow.config import DatabaseConfig, CacheConfig, MonitoringConfig

# Database configuration
database_config = DatabaseConfig(
    # Connection settings
    url=os.getenv("DATABASE_URL"),
    pool_size=50,
    max_overflow=100,
    pool_recycle=3600,
    pool_pre_ping=True,

    # Read replica support
    read_replicas=[
        os.getenv("DATABASE_READ_REPLICA_1"),
        os.getenv("DATABASE_READ_REPLICA_2")
    ],

    # Performance settings
    statement_timeout=30,
    query_timeout=60,
    connection_timeout=10,

    # Security
    ssl_mode="require",
    ssl_cert_path="/etc/ssl/certs/client.crt",
    ssl_key_path="/etc/ssl/private/client.key",
    ssl_ca_path="/etc/ssl/certs/ca.crt"
)

# Cache configuration
cache_config = CacheConfig(
    redis_url=os.getenv("REDIS_URL"),
    redis_cluster_nodes=[
        os.getenv("REDIS_NODE_1"),
        os.getenv("REDIS_NODE_2"),
        os.getenv("REDIS_NODE_3")
    ],

    # Cache settings
    default_ttl=3600,
    max_memory="2gb",
    eviction_policy="allkeys-lru",

    # Performance
    connection_pool_size=50,
    socket_timeout=5,
    socket_connect_timeout=5
)

# Monitoring configuration
monitoring_config = MonitoringConfig(
    enabled=True,
    metrics_port=9090,
    metrics_path="/metrics",
    export_format="prometheus",

    # Performance monitoring
    slow_query_threshold=1.0,
    track_query_performance=True,
    track_memory_usage=True,

    # Alerting
    alert_on_high_memory=True,
    alert_on_slow_queries=True,
    alert_on_connection_issues=True
)

# Production DataFlow configuration
production_config = DataFlowConfig(
    environment="production",
    debug=False,

    database=database_config,
    cache=cache_config,
    monitoring=monitoring_config,

    # Security settings
    encryption_key=os.getenv("ENCRYPTION_KEY"),
    audit_logging=True,
    access_control=True,

    # Performance settings
    bulk_optimization=True,
    connection_pooling=True,
    query_optimization=True,

    # Multi-tenancy
    multi_tenant=True,
    tenant_isolation="strict",

    # Reliability
    auto_retry=True,
    circuit_breaker=True,
    health_checks=True
)

# Initialize DataFlow
db = DataFlow(config=production_config)
```

### Environment Variables

```bash
# Database
export DATABASE_URL="postgresql://user:password@primary-db:5432/dataflow_prod"
export DATABASE_READ_REPLICA_1="postgresql://user:password@replica1-db:5432/dataflow_prod"
export DATABASE_READ_REPLICA_2="postgresql://user:password@replica2-db:5432/dataflow_prod"

# Cache
export REDIS_URL="redis://redis-cluster:6379/0"
export REDIS_NODE_1="redis://redis-node1:6379"
export REDIS_NODE_2="redis://redis-node2:6379"
export REDIS_NODE_3="redis://redis-node3:6379"

# Security
export ENCRYPTION_KEY="your-32-character-encryption-key"
export JWT_SECRET="your-jwt-secret-key"
export API_SECRET="your-api-secret-key"

# Monitoring
export PROMETHEUS_ENDPOINT="http://prometheus:9090"
export GRAFANA_ENDPOINT="http://grafana:3000"
export LOG_LEVEL="INFO"

# Performance
export WORKER_PROCESSES=4
export WORKER_THREADS=8
export MAX_CONNECTIONS=1000
```

## Containerization

### Docker Configuration

```dockerfile
# Dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create application directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start application
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "app:app"]
```

### Docker Compose

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  # DataFlow application
  dataflow-app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://dataflow:password@postgres:5432/dataflow_prod
      - REDIS_URL=redis://redis:6379/0
      - ENVIRONMENT=production
    depends_on:
      - postgres
      - redis
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'
        reservations:
          memory: 1G
          cpus: '0.5'

  # PostgreSQL database
  postgres:
    image: postgres:15
    environment:
      - POSTGRES_DB=dataflow_prod
      - POSTGRES_USER=dataflow
      - POSTGRES_PASSWORD=password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    restart: unless-stopped
    command: >
      postgres
      -c shared_preload_libraries=pg_stat_statements
      -c max_connections=200
      -c shared_buffers=256MB
      -c effective_cache_size=1GB
      -c maintenance_work_mem=64MB
      -c checkpoint_completion_target=0.9
      -c wal_buffers=16MB
      -c default_statistics_target=100

  # Redis cache
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped
    command: >
      redis-server
      --maxmemory 1gb
      --maxmemory-policy allkeys-lru
      --save 900 1
      --save 300 10
      --save 60 10000

  # Monitoring
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
  prometheus_data:
  grafana_data:
```

## Kubernetes Deployment

### DataFlow Application Deployment

```yaml
# k8s/dataflow-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dataflow-app
  namespace: dataflow
spec:
  replicas: 3
  selector:
    matchLabels:
      app: dataflow-app
  template:
    metadata:
      labels:
        app: dataflow-app
    spec:
      containers:
      - name: dataflow-app
        image: dataflow:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: dataflow-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: dataflow-secrets
              key: redis-url
        - name: ENCRYPTION_KEY
          valueFrom:
            secretKeyRef:
              name: dataflow-secrets
              key: encryption-key
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
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
        volumeMounts:
        - name: logs
          mountPath: /app/logs
      volumes:
      - name: logs
        emptyDir: {}
```

### Service Configuration

```yaml
# k8s/dataflow-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: dataflow-service
  namespace: dataflow
spec:
  selector:
    app: dataflow-app
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: ClusterIP

---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: dataflow-ingress
  namespace: dataflow
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  rules:
  - host: dataflow.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: dataflow-service
            port:
              number: 80
```

### ConfigMap and Secrets

```yaml
# k8s/dataflow-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: dataflow-config
  namespace: dataflow
data:
  ENVIRONMENT: "production"
  LOG_LEVEL: "INFO"
  WORKER_PROCESSES: "4"
  WORKER_THREADS: "8"

---
apiVersion: v1
kind: Secret
metadata:
  name: dataflow-secrets
  namespace: dataflow
type: Opaque
data:
  database-url: <base64-encoded-database-url>
  redis-url: <base64-encoded-redis-url>
  encryption-key: <base64-encoded-encryption-key>
```

## Database Setup

### PostgreSQL Configuration

```sql
-- init.sql
-- Create database and user
CREATE DATABASE dataflow_prod;
CREATE USER dataflow WITH ENCRYPTED PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE dataflow_prod TO dataflow;

-- Connect to the database
\c dataflow_prod;

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create schemas
CREATE SCHEMA IF NOT EXISTS dataflow;
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS monitoring;

-- Grant permissions
GRANT ALL ON SCHEMA dataflow TO dataflow;
GRANT ALL ON SCHEMA audit TO dataflow;
GRANT ALL ON SCHEMA monitoring TO dataflow;

-- Set default search path
ALTER USER dataflow SET search_path TO dataflow, public;
```

### Database Performance Tuning

```sql
-- postgresql.conf optimizations
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200
work_mem = 4MB
min_wal_size = 1GB
max_wal_size = 4GB
max_worker_processes = 8
max_parallel_workers_per_gather = 2
max_parallel_workers = 8
max_parallel_maintenance_workers = 2
```

### Database Migrations

```python
# migrations/manage.py
from kailash_dataflow.migrations import MigrationManager
from config.production import db

# Initialize migration manager
migration_manager = MigrationManager(db)

# Run migrations
def migrate():
    """Run database migrations."""
    migration_manager.migrate()

# Rollback migrations
def rollback(version=None):
    """Rollback to specific migration version."""
    migration_manager.rollback(version)

# Check migration status
def status():
    """Check migration status."""
    return migration_manager.status()

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python manage.py <migrate|rollback|status>")
        sys.exit(1)

    command = sys.argv[1]

    if command == "migrate":
        migrate()
    elif command == "rollback":
        version = sys.argv[2] if len(sys.argv) > 2 else None
        rollback(version)
    elif command == "status":
        status()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
```

## Application Structure

### Production Application

```python
# app.py
import os
import logging
from flask import Flask, jsonify, request
from kailash_dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from config.production import production_config

# Initialize Flask app
app = Flask(__name__)

# Initialize DataFlow
db = DataFlow(config=production_config)

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Health check endpoint
@app.route('/health')
def health():
    """Health check endpoint."""
    try:
        # Check database connection
        db.health_check()
        return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

# Readiness check endpoint
@app.route('/ready')
def ready():
    """Readiness check endpoint."""
    try:
        # Check if application is ready to serve traffic
        db.ready_check()
        return jsonify({"status": "ready", "timestamp": datetime.now().isoformat()})
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return jsonify({"status": "not_ready", "error": str(e)}), 503

# Metrics endpoint
@app.route('/metrics')
def metrics():
    """Prometheus metrics endpoint."""
    return db.get_metrics()

# API endpoints
@app.route('/api/users', methods=['POST'])
def create_user():
    """Create a new user."""
    try:
        data = request.get_json()

        # Create workflow
        workflow = WorkflowBuilder()
        workflow.add_node("UserCreateNode", "create_user", data)

        # Execute workflow with runtime parameters
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build(), {
            "create_user": data  # Pass data to specific node
        })

        return jsonify({
            "success": True,
            "data": results["create_user"]["data"],
            "run_id": run_id
        })
    except Exception as e:
        logger.error(f"User creation failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    """Get user by ID."""
    try:
        # Create workflow
        workflow = WorkflowBuilder()
        workflow.add_node("UserReadNode", "get_user", {"id": user_id})

        # Execute workflow with runtime parameters
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build(), {
            "get_user": {"id": user_id}  # Pass parameters to specific node
        })

        return jsonify({
            "success": True,
            "data": results["get_user"]["data"],
            "run_id": run_id
        })
    except Exception as e:
        logger.error(f"User retrieval failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({"error": "Internal server error"}), 500

# Initialize database on startup
@app.before_first_request
def initialize_database():
    """Initialize database on application startup."""
    try:
        db.initialize()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

if __name__ == '__main__':
    # Run development server
    app.run(host='0.0.0.0', port=8000, debug=False)
```

### WSGI Configuration

```python
# wsgi.py
from app import app

if __name__ == "__main__":
    app.run()
```

### Gunicorn Configuration

```python
# gunicorn.conf.py
import multiprocessing
import os

# Server socket
bind = "0.0.0.0:8000"
backlog = 2048

# Worker processes
workers = int(os.getenv("WORKER_PROCESSES", multiprocessing.cpu_count() * 2))
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50
timeout = 30
keepalive = 5

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Logging
accesslog = "/app/logs/access.log"
errorlog = "/app/logs/error.log"
loglevel = os.getenv("LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = "dataflow-app"

# Preload application
preload_app = True

# Graceful shutdown
graceful_timeout = 30
```

## Monitoring and Observability

### Prometheus Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'dataflow'
    static_configs:
      - targets: ['dataflow-app:8000']
    metrics_path: '/metrics'
    scrape_interval: 15s

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres:5432']
    metrics_path: '/metrics'

  - job_name: 'redis'
    static_configs:
      - targets: ['redis:6379']
    metrics_path: '/metrics'
```

### Grafana Dashboard

```json
{
  "dashboard": {
    "title": "DataFlow Production Dashboard",
    "panels": [
      {
        "title": "Request Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(dataflow_requests_total[5m])",
            "legendFormat": "{{method}} {{endpoint}}"
          }
        ]
      },
      {
        "title": "Response Time",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, dataflow_request_duration_seconds_bucket)",
            "legendFormat": "95th percentile"
          }
        ]
      },
      {
        "title": "Database Connections",
        "type": "graph",
        "targets": [
          {
            "expr": "dataflow_db_connections_active",
            "legendFormat": "Active"
          },
          {
            "expr": "dataflow_db_connections_idle",
            "legendFormat": "Idle"
          }
        ]
      }
    ]
  }
}
```

### Logging Configuration

```ini
# logging.conf
[loggers]
keys=root,dataflow,kailash

[handlers]
keys=consoleHandler,fileHandler

[formatters]
keys=simpleFormatter,jsonFormatter

[logger_root]
level=INFO
handlers=consoleHandler,fileHandler

[logger_dataflow]
level=INFO
handlers=consoleHandler,fileHandler
qualname=dataflow
propagate=0

[logger_kailash]
level=INFO
handlers=consoleHandler,fileHandler
qualname=kailash
propagate=0

[handler_consoleHandler]
class=StreamHandler
level=INFO
formatter=jsonFormatter
args=(sys.stdout,)

[handler_fileHandler]
class=FileHandler
level=INFO
formatter=jsonFormatter
args=('/app/logs/app.log',)

[formatter_simpleFormatter]
format=%(asctime)s - %(name)s - %(levelname)s - %(message)s

[formatter_jsonFormatter]
format={"timestamp": "%(asctime)s", "logger": "%(name)s", "level": "%(levelname)s", "message": "%(message)s"}
```

## Security Configuration

### SSL/TLS Configuration

```python
# security.py
import ssl
from kailash_dataflow.security import SecurityConfig

# SSL configuration
ssl_config = SecurityConfig(
    # Database SSL
    database_ssl=True,
    database_ssl_cert="/etc/ssl/certs/client.crt",
    database_ssl_key="/etc/ssl/private/client.key",
    database_ssl_ca="/etc/ssl/certs/ca.crt",

    # Redis SSL
    redis_ssl=True,
    redis_ssl_cert="/etc/ssl/certs/redis-client.crt",
    redis_ssl_key="/etc/ssl/private/redis-client.key",

    # Application SSL
    api_ssl=True,
    api_ssl_cert="/etc/ssl/certs/api.crt",
    api_ssl_key="/etc/ssl/private/api.key",

    # Encryption
    encryption_key=os.getenv("ENCRYPTION_KEY"),
    encrypt_at_rest=True,
    encrypt_in_transit=True,

    # Access control
    access_control=True,
    authentication=True,
    authorization=True,

    # Audit
    audit_logging=True,
    audit_level="all",

    # Compliance
    gdpr_mode=True,
    data_retention_days=365
)
```

### Access Control

```python
# auth.py
from kailash_dataflow.auth import AuthManager, User, Role

# Initialize auth manager
auth_manager = AuthManager(db)

# Define roles
admin_role = Role("admin", permissions=["create", "read", "update", "delete"])
user_role = Role("user", permissions=["read", "create"])

# Create users
admin_user = User("admin", "admin@example.com", roles=[admin_role])
regular_user = User("user", "user@example.com", roles=[user_role])

# Protect endpoints
@app.route('/api/admin/users', methods=['GET'])
@auth_manager.require_role("admin")
def admin_list_users():
    """Admin-only user listing."""
    # Implementation
    pass

@app.route('/api/users/me', methods=['GET'])
@auth_manager.require_authentication()
def get_current_user():
    """Get current authenticated user."""
    # Implementation
    pass
```

## Scaling Strategies

### Horizontal Scaling

```yaml
# k8s/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: dataflow-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: dataflow-app
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

### Database Scaling

```python
# Database read replicas
database_config = DatabaseConfig(
    # Primary database
    url=os.getenv("DATABASE_PRIMARY_URL"),

    # Read replicas
    read_replicas=[
        os.getenv("DATABASE_REPLICA_1_URL"),
        os.getenv("DATABASE_REPLICA_2_URL"),
        os.getenv("DATABASE_REPLICA_3_URL")
    ],

    # Load balancing
    read_strategy="round_robin",  # round_robin, random, least_connections

    # Failover
    failover_enabled=True,
    failover_timeout=5,

    # Connection pooling
    pool_size=50,
    max_overflow=100
)
```

## Backup and Recovery

### Database Backup

```bash
#!/bin/bash
# backup.sh

# Configuration
DB_HOST="postgres"
DB_PORT="5432"
DB_NAME="dataflow_prod"
DB_USER="dataflow"
BACKUP_DIR="/backups"
RETENTION_DAYS=30

# Create backup
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/dataflow_backup_$TIMESTAMP.sql"

# Perform backup
pg_dump -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME > $BACKUP_FILE

# Compress backup
gzip $BACKUP_FILE

# Remove old backups
find $BACKUP_DIR -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete

echo "Backup completed: $BACKUP_FILE.gz"
```

### Application State Backup

```python
# backup_manager.py
import os
import shutil
import datetime
from kailash_dataflow.backup import BackupManager

class DataFlowBackupManager:
    def __init__(self, db):
        self.db = db
        self.backup_dir = "/backups"

    def create_full_backup(self):
        """Create full application backup."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(self.backup_dir, f"full_backup_{timestamp}")

        # Create backup directory
        os.makedirs(backup_path, exist_ok=True)

        # Backup database
        self._backup_database(backup_path)

        # Backup application state
        self._backup_application_state(backup_path)

        # Backup configuration
        self._backup_configuration(backup_path)

        # Create archive
        archive_path = f"{backup_path}.tar.gz"
        shutil.make_archive(backup_path, 'gztar', backup_path)

        # Cleanup temp directory
        shutil.rmtree(backup_path)

        return archive_path

    def restore_backup(self, backup_path):
        """Restore from backup."""
        # Extract backup
        extract_path = f"{backup_path}_extracted"
        shutil.unpack_archive(backup_path, extract_path)

        # Restore database
        self._restore_database(extract_path)

        # Restore application state
        self._restore_application_state(extract_path)

        # Restore configuration
        self._restore_configuration(extract_path)

        # Cleanup
        shutil.rmtree(extract_path)
```

## Performance Optimization

### Application Performance

```python
# performance.py
from kailash_dataflow.performance import PerformanceOptimizer

# Initialize performance optimizer
optimizer = PerformanceOptimizer(db)

# Enable optimizations
optimizer.enable_query_optimization()
optimizer.enable_connection_pooling()
optimizer.enable_bulk_operations()
optimizer.enable_caching()

# Configure performance settings
optimizer.configure(
    # Query optimization
    query_cache_size="512MB",
    query_plan_cache_size="128MB",

    # Connection pooling
    pool_size=50,
    max_overflow=100,
    pool_recycle=3600,

    # Bulk operations
    bulk_batch_size=1000,
    bulk_parallel_workers=4,

    # Caching
    cache_ttl=3600,
    cache_max_memory="1GB"
)
```

### Database Performance

```sql
-- Performance optimization queries
-- Analyze query performance
SELECT
    query,
    calls,
    total_time,
    mean_time,
    max_time,
    stddev_time
FROM pg_stat_statements
ORDER BY total_time DESC
LIMIT 20;

-- Check index usage
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;

-- Check table statistics
SELECT
    schemaname,
    tablename,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC;
```

## Disaster Recovery

### Recovery Plan

```python
# disaster_recovery.py
import logging
from kailash_dataflow.recovery import DisasterRecoveryManager

class DataFlowDisasterRecovery:
    def __init__(self, db):
        self.db = db
        self.logger = logging.getLogger(__name__)

    def execute_recovery_plan(self):
        """Execute disaster recovery plan."""
        try:
            # Step 1: Assess damage
            damage_assessment = self._assess_damage()

            # Step 2: Activate backup systems
            self._activate_backup_systems()

            # Step 3: Restore data
            self._restore_data()

            # Step 4: Verify system integrity
            self._verify_system_integrity()

            # Step 5: Resume operations
            self._resume_operations()

            self.logger.info("Disaster recovery completed successfully")

        except Exception as e:
            self.logger.error(f"Disaster recovery failed: {e}")
            raise

    def _assess_damage(self):
        """Assess system damage."""
        # Check database connectivity
        # Check application health
        # Check data integrity
        pass

    def _activate_backup_systems(self):
        """Activate backup systems."""
        # Switch to backup database
        # Redirect traffic to backup servers
        # Activate emergency procedures
        pass

    def _restore_data(self):
        """Restore data from backups."""
        # Restore database from latest backup
        # Restore application state
        # Restore configuration
        pass

    def _verify_system_integrity(self):
        """Verify system integrity."""
        # Run data integrity checks
        # Verify application functionality
        # Check performance metrics
        pass

    def _resume_operations(self):
        """Resume normal operations."""
        # Switch back to primary systems
        # Restore normal traffic routing
        # Update monitoring and alerting
        pass
```

## Testing in Production

### Health Checks

```python
# health_checks.py
from kailash_dataflow.health import HealthChecker

class DataFlowHealthChecker:
    def __init__(self, db):
        self.db = db
        self.health_checker = HealthChecker(db)

    def run_health_checks(self):
        """Run comprehensive health checks."""
        checks = [
            self.health_checker.check_database_connectivity(),
            self.health_checker.check_cache_connectivity(),
            self.health_checker.check_application_health(),
            self.health_checker.check_system_resources(),
            self.health_checker.check_external_dependencies()
        ]

        return {
            "overall_health": all(checks),
            "database": checks[0],
            "cache": checks[1],
            "application": checks[2],
            "resources": checks[3],
            "dependencies": checks[4]
        }
```

### Load Testing

```python
# load_test.py
import asyncio
import aiohttp
import time

async def load_test():
    """Run load test against production endpoint."""
    url = "https://dataflow.example.com/api/users"
    concurrent_requests = 100
    total_requests = 10000

    async with aiohttp.ClientSession() as session:
        tasks = []
        start_time = time.time()

        for i in range(total_requests):
            task = asyncio.create_task(
                make_request(session, url, i)
            )
            tasks.append(task)

            # Control concurrency
            if len(tasks) >= concurrent_requests:
                await asyncio.gather(*tasks)
                tasks = []

        # Wait for remaining tasks
        if tasks:
            await asyncio.gather(*tasks)

        end_time = time.time()
        duration = end_time - start_time

        print(f"Load test completed: {total_requests} requests in {duration:.2f}s")
        print(f"Requests per second: {total_requests / duration:.2f}")

async def make_request(session, url, request_id):
    """Make a single request."""
    try:
        async with session.post(url, json={
            "name": f"User {request_id}",
            "email": f"user{request_id}@example.com"
        }) as response:
            return await response.json()
    except Exception as e:
        print(f"Request {request_id} failed: {e}")
        return None

if __name__ == "__main__":
    asyncio.run(load_test())
```

## Best Practices

### 1. Configuration Management

```python
# Use environment-specific configuration
# Separate secrets from configuration
# Use configuration validation
# Implement configuration hot-reloading
```

### 2. Security

```python
# Enable SSL/TLS for all connections
# Use strong encryption keys
# Implement proper authentication and authorization
# Enable audit logging
# Regular security updates
```

### 3. Monitoring

```python
# Monitor application metrics
# Set up alerting for critical issues
# Track performance trends
# Monitor resource usage
# Implement distributed tracing
```

### 4. Scaling

```python
# Design for horizontal scaling
# Use load balancing
# Implement connection pooling
# Use read replicas for read-heavy workloads
# Consider database sharding for very large datasets
```

### 5. Reliability

```python
# Implement circuit breakers
# Use graceful degradation
# Have rollback plans
# Test disaster recovery procedures
# Implement health checks
```

## Troubleshooting

### Common Issues

1. **Database Connection Issues**
   - Check connection string
   - Verify network connectivity
   - Check database server status
   - Review connection pool settings

2. **Performance Issues**
   - Monitor query performance
   - Check index usage
   - Review connection pool utilization
   - Analyze resource usage

3. **Memory Issues**
   - Monitor memory usage
   - Check for memory leaks
   - Optimize bulk operations
   - Review garbage collection

4. **Scaling Issues**
   - Monitor load balancer health
   - Check horizontal scaling metrics
   - Review database performance
   - Analyze network throughput

### Debugging Tools

```python
# Debug configuration
debug_config = DataFlowConfig(
    debug=True,
    log_level="DEBUG",
    enable_profiling=True,
    track_memory_usage=True,
    enable_query_logging=True
)

# Performance profiling
from kailash_dataflow.profiling import ProfileManager

profiler = ProfileManager(db)
profiler.enable_profiling()
profiler.generate_report()
```

## Next Steps

- **Advanced Features**: [Advanced Features Guide](../advanced/)
- **Performance Tuning**: [Performance Guide](performance.md)
- **Security**: [Security Guide](../advanced/security.md)
- **Monitoring**: [Monitoring Guide](../advanced/monitoring.md)

DataFlow provides enterprise-grade capabilities for production deployment, ensuring reliability, performance, and security at scale.
