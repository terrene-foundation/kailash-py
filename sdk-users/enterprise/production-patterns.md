# Enterprise Production Patterns

*Scaling, monitoring, deployment, and operational excellence patterns*

## 🚀 Overview

This guide covers production deployment patterns for Kailash SDK enterprise applications, including containerization, auto-scaling, monitoring, logging, performance optimization, and operational best practices.

## 🐳 Container Deployment Patterns

### Docker Containerization

```python
# gateway_app.py - Production gateway application
import os
from kailash.middleware import create_gateway
from kailash.middleware.auth import MiddlewareAuthManager
# Note: Import PerformanceBenchmarkNode when added to exports

# Environment-based configuration
config = {
    "database_url": os.environ.get("DATABASE_URL", "postgresql://localhost/kailash"),
    "redis_url": os.environ.get("REDIS_URL", "redis://localhost:6379"),
    "jwt_secret": os.environ.get("JWT_SECRET_KEY", "change-in-production"),
    "environment": os.environ.get("ENVIRONMENT", "production"),
    "port": int(os.environ.get("PORT", "8000")),
    "workers": int(os.environ.get("WORKERS", "4"))
}

# Create production gateway
gateway = create_gateway(
    title="Enterprise Production Gateway",
    description="Scalable production deployment",
    version="1.0.0",

    # Security configuration
    cors_origins=os.environ.get("CORS_ORIGINS", "").split(","),
    enable_docs=config["environment"] != "production",

    # Authentication
    auth_manager=MiddlewareAuthManager(
        secret_key=config["jwt_secret"],
        token_expiry_hours=8,
        enable_api_keys=True,
        enable_audit=True,
        database_url=config["database_url"]
    ),

    # Performance
    max_sessions=10000,
    database_url=config["database_url"]
)

if __name__ == "__main__":
    # Production server with monitoring
    gateway.run(
        host="0.0.0.0",
        port=config["port"],
        workers=config["workers"],
        access_log=True
    )
```

### Production Dockerfile

```dockerfile
# Multi-stage build for optimized image
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -r kailash && chown -R kailash:kailash /app
USER kailash

# Set Python path
ENV PATH=/root/.local/bin:$PATH

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Run production server
CMD ["python", "gateway_app.py"]
```

### Docker Compose for Production

```yaml
version: '3.8'

services:
  gateway:
    build: .
    image: kailash-gateway:latest
    restart: always
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://kailash:password@postgres:5432/kailash
      - REDIS_URL=redis://redis:6379
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - ENVIRONMENT=production
      - WORKERS=4
    depends_on:
      - postgres
      - redis
    volumes:
      - ./logs:/app/logs
    networks:
      - kailash-network
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3

  postgres:
    image: postgres:15-alpine
    restart: always
    environment:
      - POSTGRES_DB=kailash
      - POSTGRES_USER=kailash
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres-data:/var/lib/postgresql/data
    networks:
      - kailash-network
    deploy:
      placement:
        constraints:
          - node.role == manager

  redis:
    image: redis:7-alpine
    restart: always
    command: redis-server --appendonly yes
    volumes:
      - redis-data:/data
    networks:
      - kailash-network
    deploy:
      placement:
        constraints:
          - node.role == manager

  nginx:
    image: nginx:alpine
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - gateway
    networks:
      - kailash-network

volumes:
  postgres-data:
  redis-data:

networks:
  kailash-network:
    driver: overlay
    attachable: true
```

## 📊 Monitoring and Observability

### Comprehensive Monitoring Workflow

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.monitoring import (
    ConnectionDashboardNode,
    HealthCheckNode,
    MetricsCollectorNode,
    PerformanceBenchmarkNode
)
from kailash.nodes.alerts import DiscordAlertNode
from kailash.nodes.security import ThreatDetectionNode, BehaviorAnalysisNode

# Production monitoring workflow
monitoring_workflow = WorkflowBuilder()

# Connection monitoring
monitoring_workflow.add_node("ConnectionDashboardNode", "connection_monitor", {
    "refresh_interval": 5,
    "show_active_connections": True,
    "show_workflow_graph": True,
    "track_performance": True
})

# Health checks using the real HealthCheckNode
monitoring_workflow.add_node("HealthCheckNode", "health_checker", {
    "services": [
        {
            "name": "database",
            "type": "database",
            "connection_string": "postgresql://user:pass@postgres:5432/kailash",
            "test_query": "SELECT 1"
        },
        {
            "name": "redis",
            "type": "redis",
            "url": "redis://redis:6379"
        },
        {
            "name": "external_api",
            "type": "http",
            "url": "https://api.partner.com/health",
            "method": "GET",
            "expected_status": [200, 204]
        },
        {
            "name": "gateway",
            "type": "http",
            "url": "http://gateway:8000/health",
            "expected_status": 200
        }
    ],
    "timeout": 30.0,
    "parallel": True,
    "fail_fast": False,
    "retries": 3,
    "retry_delay": 1.0
})

# Threat detection for security monitoring
monitoring_workflow.add_node("ThreatDetectionNode", "threat_monitor", {
    "detection_rules": [
        {
            "name": "brute_force_attack",
            "pattern": "multiple_failed_logins",
            "threshold": 5,
            "window": 300,
            "severity": "high"
        },
        {
            "name": "sql_injection_attempt",
            "pattern": "sql_keywords_in_input",
            "severity": "critical"
        }
    ],
    "alert_threshold": "medium"
})

# Behavior analysis for anomaly detection
monitoring_workflow.add_node("BehaviorAnalysisNode", "anomaly_detector", {
    "baseline_window": 7,  # days
    "sensitivity": 0.8,
    "metrics_to_track": [
        "request_rate",
        "error_rate",
        "response_time",
        "unique_users"
    ]
})

# Performance metrics collection using PythonCodeNode
monitoring_workflow.add_node("PythonCodeNode", "metrics_collector", {
    "code": """
import psutil
import time
from prometheus_client import Counter, Histogram, Gauge, generate_latest

# Define Prometheus metrics
request_count = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
request_duration = Histogram('http_request_duration_seconds', 'HTTP request duration', ['method', 'endpoint'])
active_sessions = Gauge('active_sessions', 'Active user sessions', ['tenant_id'])
cpu_usage = Gauge('cpu_usage_percent', 'CPU usage percentage')
memory_usage = Gauge('memory_usage_percent', 'Memory usage percentage')

# Collect system metrics
cpu_usage.set(psutil.cpu_percent(interval=1))
memory_usage.set(psutil.virtual_memory().percent)

# Generate Prometheus format output
result = {
    "metrics": generate_latest().decode('utf-8'),
    "timestamp": time.time(),
    "cpu": psutil.cpu_percent(),
    "memory": psutil.virtual_memory().percent,
    "disk": psutil.disk_usage('/').percent
}
"""
})

# Alert on issues
monitoring_workflow.add_node("DiscordAlertNode", "alerting", {
    "webhook_url": "${DISCORD_WEBHOOK_URL}",
    "message_template": "🚨 **{severity}** Alert: {alert_name}\n{message}\nTime: {timestamp}"
})

# Connect monitoring components
monitoring_workflow.add_connection(
    "health_checker", "result",
    "alerting", "health_data"
)

monitoring_workflow.add_connection(
    "threat_monitor", "threats",
    "alerting", "threat_data"
)

monitoring_workflow.add_connection(
    "anomaly_detector", "anomalies",
    "alerting", "anomaly_data"
)
```

### Metrics Collection

```python
# Metrics collection workflow
metrics_workflow = WorkflowBuilder()

# Collect system and application metrics
metrics_workflow.add_node("MetricsCollectorNode", "metrics_collector", {
    "metric_types": [
        "system.cpu",
        "system.memory",
        "system.disk",
        "system.network"
    ],
    "custom_metrics": [
        {
            "name": "workflow_executions_total",
            "type": "counter",
            "value": 1000,
            "labels": {"workflow": "production_monitoring"}
        },
        {
            "name": "api_response_time_ms",
            "type": "gauge",
            "value": 125.5,
            "labels": {"endpoint": "/api/v1/workflows"}
        },
        {
            "name": "queue_depth",
            "type": "gauge",
            "value": 42,
            "labels": {"queue": "task_queue"}
        }
    ],
    "format": "prometheus",  # Output in Prometheus format
    "labels": {
        "environment": "production",
        "region": "us-west-2",
        "service": "kailash-gateway"
    },
    "include_process": True,
    "aggregate": True,
    "interval": 60.0  # Aggregate over 1 minute
})

# Performance benchmarking for specific operations
metrics_workflow.add_node("PerformanceBenchmarkNode", "benchmark", {
    "operations": [
        {"name": "database_query", "function": "query_users"},
        {"name": "cache_lookup", "function": "get_from_cache"},
        {"name": "api_call", "function": "external_api_request"}
    ],
    "iterations": 100,
    "warmup_iterations": 10,
    "enable_monitoring": True,
    "performance_targets": [
        {
            "operation": "database_query",
            "metric_type": "response_time",
            "target_value": 50.0,
            "threshold_warning": 100.0,
            "threshold_critical": 200.0,
            "unit": "ms"
        }
    ],
    "alert_thresholds": {
        "response_time": 200,
        "error_rate": 0.05
    }
})

# Export metrics to monitoring system
metrics_workflow.add_node("HTTPRequestNode", "metrics_exporter", {
    "url": "http://prometheus-pushgateway:9091/metrics/job/kailash",
    "method": "POST",
    "headers": {"Content-Type": "text/plain"},
    "timeout": 10
})

# Connect nodes
metrics_workflow.add_connection(
    "metrics_collector", "metrics",
    "metrics_exporter", "body"
)
```

### Prometheus Integration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093

rule_files:
  - "alerts/*.yml"

scrape_configs:
  - job_name: 'kailash-gateway'
    static_configs:
      - targets: ['gateway:8000']
    metrics_path: '/metrics'
    scrape_interval: 10s

  - job_name: 'node-exporter'
    static_configs:
      - targets: ['node-exporter:9100']

  - job_name: 'postgres-exporter'
    static_configs:
      - targets: ['postgres-exporter:9187']

  - job_name: 'redis-exporter'
    static_configs:
      - targets: ['redis-exporter:9121']
```

## 🔄 Auto-Scaling Patterns

### Kubernetes Deployment

```yaml
# kailash-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kailash-gateway
  labels:
    app: kailash-gateway
spec:
  replicas: 3
  selector:
    matchLabels:
      app: kailash-gateway
  template:
    metadata:
      labels:
        app: kailash-gateway
    spec:
      containers:
      - name: gateway
        image: kailash-gateway:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: kailash-secrets
              key: database-url
        - name: JWT_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: kailash-secrets
              key: jwt-secret
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
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: kailash-gateway-service
spec:
  selector:
    app: kailash-gateway
  ports:
    - protocol: TCP
      port: 80
      targetPort: 8000
  type: LoadBalancer
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: kailash-gateway-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: kailash-gateway
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
  - type: Pods
    pods:
      metric:
        name: http_requests_per_second
      target:
        type: AverageValue
        averageValue: "1000"
```

### Dynamic Scaling Workflow

```python
# Auto-scaling logic using PythonCodeNode and external orchestration
scaling_workflow = WorkflowBuilder()

# Monitor load and determine scaling needs
scaling_workflow.add_node("PythonCodeNode", "scaling_monitor", {
    "code": """
import psutil
import docker
import time

# Get current metrics
cpu_percent = psutil.cpu_percent(interval=1)
memory_percent = psutil.virtual_memory().percent
current_time = time.time()

# Connect to Docker
client = docker.from_env()

# Count running instances
service_name = "kailash-gateway"
running_instances = len([c for c in client.containers.list()
                        if service_name in c.name])

# Scaling policy
min_instances = 3
max_instances = 20
scale_up_threshold = 80
scale_down_threshold = 50
target_cpu = 70

# Determine scaling action
scaling_action = None
if cpu_percent > scale_up_threshold and running_instances < max_instances:
    scaling_action = "scale_up"
    new_instances = min(running_instances + 2, max_instances)
elif cpu_percent < scale_down_threshold and running_instances > min_instances:
    scaling_action = "scale_down"
    new_instances = max(running_instances - 1, min_instances)
else:
    scaling_action = "maintain"
    new_instances = running_instances

result = {
    "current_cpu": cpu_percent,
    "current_memory": memory_percent,
    "current_instances": running_instances,
    "scaling_action": scaling_action,
    "target_instances": new_instances,
    "timestamp": current_time
}
"""
})

# Apply scaling decision
scaling_workflow.add_node("PythonCodeNode", "scale_executor", {
    "code": """
import subprocess
import json

if scaling_action == "scale_up" or scaling_action == "scale_down":
    # Execute scaling command
    cmd = f"docker service scale kailash-gateway={target_instances}"
    result = subprocess.run(cmd.split(), capture_output=True, text=True)

    if result.returncode == 0:
        status = "success"
        message = f"Scaled to {target_instances} instances"
    else:
        status = "failed"
        message = result.stderr
else:
    status = "no_action"
    message = f"Maintaining {current_instances} instances"

result = {
    "status": status,
    "message": message,
    "instances": target_instances,
    "action": scaling_action
}
"""
})

# Health-based load distribution using HTTPRequestNode
scaling_workflow.add_node("HTTPRequestNode", "health_monitor", {
    "url": "http://localhost/health",
    "method": "GET",
    "timeout": 5,
    "retry_attempts": 3
})
```

## 📝 Logging and Tracing

### Structured Logging Configuration

```python
# logging_config.py
import logging
import json
from datetime import datetime
from kailash.nodes.monitoring import LogProcessorNode

# Structured logging setup
class StructuredFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "trace_id": getattr(record, 'trace_id', None),
            "user_id": getattr(record, 'user_id', None),
            "tenant_id": getattr(record, 'tenant_id', None)
        }

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)

# Configure logging
def setup_production_logging():
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Console handler with structured output
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(console_handler)

    # File handler for persistent logs
    file_handler = logging.handlers.RotatingFileHandler(
        'logs/kailash.log',
        maxBytes=100_000_000,  # 100MB
        backupCount=10
    )
    file_handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(file_handler)

    return root_logger
```

### Log Processing Workflow

```python
# Log aggregation and processing using existing nodes
log_workflow = WorkflowBuilder()

# Collect logs using DirectoryReaderNode and JSONReaderNode
log_workflow.add_node("DirectoryReaderNode", "log_file_collector", {
    "directory": "/app/logs",
    "file_pattern": "*.log",
    "recursive": False
})

# Process each log file
log_workflow.add_node("JSONReaderNode", "log_parser", {
    "file_path": "${log_file_collector.files[0]}",  # Process first file
    "parse_array": True  # If logs are in JSON array format
})

# Enhanced log processing with PythonCodeNode
log_workflow.add_node("PythonCodeNode", "log_processor", {
    "code": """
import json
import glob
import re
from datetime import datetime

# Collect logs from multiple sources
all_logs = []

# File-based logs
for log_file in glob.glob('/app/logs/*.log'):
    try:
        with open(log_file, 'r') as f:
            for line in f:
                try:
                    log_entry = json.loads(line)
                    all_logs.append(log_entry)
                except json.JSONDecodeError:
                    # Handle plain text logs
                    all_logs.append({
                        'message': line.strip(),
                        'source': log_file,
                        'timestamp': datetime.now().isoformat()
                    })
    except Exception as e:
        pass

# Apply filters
filtered_logs = []
for log in all_logs:
    # Level filter
    if log.get('level') in ['ERROR', 'CRITICAL']:
        filtered_logs.append(log)
    # Performance filter
    elif log.get('response_time', 0) > 1000:
        filtered_logs.append(log)

# Enrich logs
import socket
for log in filtered_logs:
    # Add hostname
    log['hostname'] = socket.gethostname()

    # Parse user agent if present
    user_agent = log.get('user_agent', '')
    if 'Mozilla' in user_agent:
        log['browser'] = 'Web Browser'
    elif 'curl' in user_agent:
        log['browser'] = 'CLI Tool'

    # Extract IP location (simplified)
    client_ip = log.get('client_ip', '')
    if client_ip.startswith('10.'):
        log['location'] = 'Internal Network'
    else:
        log['location'] = 'External'

result = {
    'total_logs': len(all_logs),
    'filtered_logs': filtered_logs,
    'timestamp': datetime.now().isoformat()
}
"""
})

# Analyze patterns
log_workflow.add_node("PythonCodeNode", "pattern_analyzer", {
    "code": """
from collections import Counter
import re

# Analyze error patterns
error_patterns = Counter()
performance_issues = []

for log in logs:
    if log.get('level') in ['ERROR', 'CRITICAL']:
        # Extract error pattern
        error_msg = log.get('message', '')
        pattern = re.sub(r'\\d+', 'N', error_msg)  # Replace numbers with N
        pattern = re.sub(r'[a-f0-9]{8,}', 'ID', pattern)  # Replace IDs
        error_patterns[pattern] += 1

    # Track slow requests
    if log.get('response_time', 0) > 1000:
        performance_issues.append({
            'endpoint': log.get('endpoint'),
            'response_time': log.get('response_time'),
            'timestamp': log.get('timestamp')
        })

result = {
    'top_errors': error_patterns.most_common(10),
    'performance_issues': performance_issues[:100],
    'total_errors': sum(error_patterns.values()),
    'unique_error_patterns': len(error_patterns)
}
"""
})

# Store for analysis
log_workflow.add_node("AsyncSQLDatabaseNode", "log_storage", {
    "connection_string": "${LOG_DATABASE_URL}",
    "query": """
    INSERT INTO log_analytics (
        timestamp, error_patterns, performance_issues, summary
    ) VALUES (
        NOW(), :error_patterns::jsonb, :performance_issues::jsonb, :summary::jsonb
    )
    """,
    "query_params": {
        "error_patterns": "${pattern_analyzer.top_errors}",
        "performance_issues": "${pattern_analyzer.performance_issues}",
        "summary": {
            "total_errors": "${pattern_analyzer.total_errors}",
            "unique_patterns": "${pattern_analyzer.unique_error_patterns}"
        }
    }
})
```

## 🚦 Performance Optimization

### Caching Strategy

```python
# Performance optimization workflow with Redis-based caching
perf_workflow = WorkflowBuilder()

# Redis caching using PythonCodeNode
perf_workflow.add_node("PythonCodeNode", "redis_cache", {
    "code": """
import redis
import json
import hashlib
import gzip
from datetime import datetime

# Connect to Redis
r = redis.from_url(redis_url)

# Cache key generation
def generate_cache_key(tenant_id, endpoint, params):
    params_str = json.dumps(params, sort_keys=True)
    params_hash = hashlib.md5(params_str.encode()).hexdigest()
    return f"edge:{tenant_id}:{endpoint}:{params_hash}"

# Cache operations
cache_key = generate_cache_key(tenant_id, endpoint, request_params)

# Try to get from cache
cached_data = r.get(cache_key)
if cached_data:
    # Decompress if needed
    if cached_data.startswith(b'\\x1f\\x8b'):  # gzip magic number
        cached_data = gzip.decompress(cached_data)

    result = {
        "cache_hit": True,
        "data": json.loads(cached_data),
        "source": "redis_cache"
    }
else:
    # Cache miss - data will be fetched and cached later
    result = {
        "cache_hit": False,
        "cache_key": cache_key,
        "ttl": 300  # 5 minutes
    }
"""
})

# In-memory caching using PythonCodeNode
perf_workflow.add_node("PythonCodeNode", "memory_cache", {
    "code": """
from functools import lru_cache
from collections import OrderedDict
import time

# Simple TTL cache implementation
class TTLCache:
    def __init__(self, max_size=10000, ttl=60):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.ttl = ttl

    def get(self, key):
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                # Move to end (LRU)
                self.cache.move_to_end(key)
                return value
            else:
                # Expired
                del self.cache[key]
        return None

    def set(self, key, value):
        self.cache[key] = (value, time.time())
        # Evict oldest if over capacity
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

# Global cache instance
if 'app_cache' not in globals():
    app_cache = TTLCache(max_size=10000, ttl=60)

# Check memory cache
cached_value = app_cache.get(cache_key)
if cached_value:
    result = {"cache_hit": True, "data": cached_value, "source": "memory"}
else:
    result = {"cache_hit": False, "cache_instance": app_cache}
"""
})

# Database query optimization
perf_workflow.add_node("AsyncSQLDatabaseNode", "optimized_db", {
    "connection_string": "${DATABASE_URL}",
    "pool_size": 50,
    "max_overflow": 100,
    "pool_pre_ping": True,
    "pool_recycle": 3600
})

# Cache invalidation using PythonCodeNode
perf_workflow.add_node("PythonCodeNode", "cache_invalidator", {
    "code": """
import redis
import fnmatch

r = redis.from_url(redis_url)

# Invalidation strategies
def invalidate_pattern(pattern, cascade=False):
    keys_to_delete = []

    # Find matching keys
    for key in r.scan_iter(match=pattern):
        keys_to_delete.append(key)

    # Delete keys
    if keys_to_delete:
        r.delete(*keys_to_delete)

    # Cascade to related patterns if needed
    if cascade and tenant_id:
        related_patterns = [
            f"user:{tenant_id}:*",
            f"session:{tenant_id}:*"
        ]
        for pattern in related_patterns:
            for key in r.scan_iter(match=pattern):
                r.delete(key)

    return {"invalidated_keys": len(keys_to_delete), "cascade": cascade}

# Handle different invalidation events
if event_type == "data_update":
    result = invalidate_pattern(f"edge:{tenant_id}:*", cascade=True)
elif event_type == "user_logout":
    result = invalidate_pattern(f"session:{user_id}:*", cascade=False)
else:
    result = {"status": "no_action", "event": event_type}
"""
})
```

### Connection Pooling

```python
# Connection pooling is handled through node configuration
pool_workflow = WorkflowBuilder()

# Database connection pooling via AsyncSQLDatabaseNode
pool_workflow.add_node("AsyncSQLDatabaseNode", "pooled_db", {
    "connection_string": "${DATABASE_URL}",
    # Connection pool settings
    "pool_size": 20,           # Number of connections to maintain
    "max_overflow": 80,        # Maximum overflow connections (total = 100)
    "pool_timeout": 30,        # Timeout waiting for connection
    "pool_recycle": 3600,      # Recycle connections after 1 hour
    "pool_pre_ping": True,     # Test connections before use

    # Query for testing connection health
    "query": "SELECT 1 as health_check"
})

# HTTP connection pooling using PythonCodeNode with aiohttp
pool_workflow.add_node("PythonCodeNode", "http_pool_manager", {
    "code": """
import aiohttp
import asyncio
from typing import Optional

# Global connection pool
class HTTPPoolManager:
    _instance: Optional['HTTPPoolManager'] = None
    _session: Optional[aiohttp.ClientSession] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            # Configure connection pool
            connector = aiohttp.TCPConnector(
                limit=200,              # Total connection pool limit
                limit_per_host=50,      # Per-host connection limit
                ttl_dns_cache=300,      # DNS cache timeout
                enable_cleanup_closed=True
            )

            # Configure timeouts
            timeout = aiohttp.ClientTimeout(
                total=30,
                connect=10,
                sock_read=30
            )

            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={'User-Agent': 'Kailash-SDK/1.0'}
            )

        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

# Get or create pool manager
pool_manager = HTTPPoolManager()
session = await pool_manager.get_session()

# Make pooled HTTP request
async with session.get(url) as response:
    result = {
        "status": response.status,
        "data": await response.json(),
        "headers": dict(response.headers),
        "pool_stats": {
            "total_connections": len(session.connector._conns),
            "available_connections": session.connector._limit - len(session.connector._conns)
        }
    }
"""
})
```

## 🔐 Production Security

### Security Hardening

```python
from kailash.nodes.security import ThreatDetectionNode, AuditLogNode
from kailash.nodes.api import RateLimitedAPINode
from kailash.middleware import create_gateway

# Security hardening workflow
security_workflow = WorkflowBuilder()

# Security headers via middleware configuration
# Note: Security headers are best configured at the gateway level
secure_gateway = create_gateway(
    title="Secure Enterprise Gateway",
    # Gateway automatically adds security headers
    enable_security_headers=True,
    security_headers={
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy": "default-src 'self'",
        "Referrer-Policy": "strict-origin-when-cross-origin"
    }
)

# IP whitelist implementation using PythonCodeNode
security_workflow.add_node("PythonCodeNode", "ip_whitelist", {
    "code": """
import ipaddress
from datetime import datetime

# Define whitelisted networks
whitelist_networks = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16")
]

# Admin endpoints that require whitelist
protected_endpoints = ["/admin/", "/api/v1/admin/"]

# Check if request should be allowed
client_ip = ipaddress.ip_address(request_ip)
is_protected = any(endpoint in request_path for endpoint in protected_endpoints)
is_whitelisted = any(client_ip in network for network in whitelist_networks)

# Check bypass header
has_bypass = request_headers.get("X-Admin-Token") == admin_token

if is_protected and not (is_whitelisted or has_bypass):
    # Log blocked attempt
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "event": "blocked_access",
        "ip": str(client_ip),
        "path": request_path,
        "reason": "ip_not_whitelisted"
    }

    result = {
        "allowed": False,
        "status_code": 403,
        "message": "Access denied",
        "log": log_entry
    }
else:
    result = {
        "allowed": True,
        "ip": str(client_ip),
        "whitelisted": is_whitelisted
    }
"""
})

# Threat detection for DDoS and attacks
security_workflow.add_node("ThreatDetectionNode", "threat_detector", {
    "detection_rules": [
        {
            "name": "ddos_attack",
            "pattern": "high_request_rate",
            "threshold": 1000,
            "window": 60,
            "severity": "critical"
        },
        {
            "name": "brute_force",
            "pattern": "repeated_auth_failures",
            "threshold": 10,
            "window": 300,
            "severity": "high"
        },
        {
            "name": "path_traversal",
            "pattern": "suspicious_path_patterns",
            "severity": "high"
        }
    ],
    "response_actions": ["block_ip", "alert_security", "rate_limit"]
})

# Audit logging for security events
security_workflow.add_node("AuditLogNode", "security_audit", {
    "log_categories": ["security", "access_control", "authentication"],
    "retention_days": 90,
    "include_request_details": True,
    "sensitive_fields": ["password", "token", "secret"]
})
```

## 🎯 Deployment Checklist

### Pre-Deployment Validation

```python
# Deployment validation workflow
validation_workflow = WorkflowBuilder()

validation_workflow.add_node("PythonCodeNode", "deployment_validator", {
    "code": """
import os
import sys

checks = {
    'environment_variables': [
        'DATABASE_URL',
        'REDIS_URL',
        'JWT_SECRET_KEY',
        'CORS_ORIGINS'
    ],
    'required_files': [
        'requirements.txt',
        'Dockerfile',
        'docker-compose.yml',
        '.env.production'
    ],
    'security_checks': {
        'debug_mode': os.environ.get('DEBUG', 'False') == 'False',
        'secret_key_length': len(os.environ.get('JWT_SECRET_KEY', '')) >= 32,
        'ssl_enabled': os.environ.get('SSL_ENABLED', 'True') == 'True'
    }
}

failures = []

# Check environment variables
for var in checks['environment_variables']:
    if not os.environ.get(var):
        failures.append(f"Missing environment variable: {var}")

# Check required files
for file in checks['required_files']:
    if not os.path.exists(file):
        failures.append(f"Missing required file: {file}")

# Security checks
for check, passed in checks['security_checks'].items():
    if not passed:
        failures.append(f"Security check failed: {check}")

if failures:
    result = {'status': 'failed', 'issues': failures}
else:
    result = {'status': 'passed', 'message': 'All deployment checks passed'}
"""
})
```

## 📊 Production Metrics Dashboard

### Key Performance Indicators

```python
# KPI monitoring workflow
kpi_workflow = WorkflowBuilder()

kpi_workflow.add_node("MetricsCollectorNode", "kpi_collector", {
    "metrics": [
        # Availability
        {"name": "uptime", "type": "gauge", "unit": "percent"},
        {"name": "error_rate", "type": "gauge", "unit": "percent"},

        # Performance
        {"name": "p50_latency", "type": "gauge", "unit": "ms"},
        {"name": "p95_latency", "type": "gauge", "unit": "ms"},
        {"name": "p99_latency", "type": "gauge", "unit": "ms"},

        # Throughput
        {"name": "requests_per_second", "type": "gauge"},
        {"name": "concurrent_users", "type": "gauge"},

        # Resources
        {"name": "cpu_usage", "type": "gauge", "unit": "percent"},
        {"name": "memory_usage", "type": "gauge", "unit": "percent"},
        {"name": "disk_usage", "type": "gauge", "unit": "percent"},

        # Business metrics
        {"name": "active_tenants", "type": "gauge"},
        {"name": "api_calls_today", "type": "counter"},
        {"name": "workflow_executions", "type": "counter"}
    ]
})
```

## 🚀 Zero-Downtime Deployment

### Blue-Green Deployment Strategy

```bash
#!/bin/bash
# deploy.sh - Zero-downtime deployment script

set -e

# Configuration
BLUE_PORT=8000
GREEN_PORT=8001
HEALTH_CHECK_URL="http://localhost:${GREEN_PORT}/health"
LOAD_BALANCER_CONFIG="/etc/nginx/conf.d/kailash.conf"

echo "Starting zero-downtime deployment..."

# 1. Build new image
docker build -t kailash-gateway:green .

# 2. Start green environment
docker-compose -f docker-compose.green.yml up -d

# 3. Wait for green to be healthy
echo "Waiting for green environment to be healthy..."
for i in {1..60}; do
    if curl -f ${HEALTH_CHECK_URL} > /dev/null 2>&1; then
        echo "Green environment is healthy"
        break
    fi
    sleep 2
done

# 4. Run smoke tests
echo "Running smoke tests..."
python smoke_tests.py --url http://localhost:${GREEN_PORT}

# 5. Switch traffic to green
echo "Switching traffic to green environment..."
sed -i "s/localhost:${BLUE_PORT}/localhost:${GREEN_PORT}/g" ${LOAD_BALANCER_CONFIG}
nginx -s reload

# 6. Wait for connections to drain
echo "Waiting for blue connections to drain..."
sleep 30

# 7. Stop blue environment
docker-compose -f docker-compose.blue.yml down

# 8. Update blue to match green
docker tag kailash-gateway:green kailash-gateway:blue

echo "Deployment completed successfully!"
```

## 📚 Production Best Practices

### Essential Production Patterns
- [ ] **Containerization**: Docker multi-stage builds with security scanning
- [ ] **Orchestration**: Kubernetes with auto-scaling and self-healing
- [ ] **Monitoring**: Prometheus + Grafana with custom dashboards
- [ ] **Logging**: Centralized structured logging with ELK stack
- [ ] **Tracing**: Distributed tracing with OpenTelemetry
- [ ] **Caching**: Multi-layer caching with Redis and CDN
- [ ] **Security**: WAF, DDoS protection, and security headers
- [ ] **Backup**: Automated backups with point-in-time recovery
- [ ] **Deployment**: Zero-downtime blue-green deployments
- [ ] **Performance**: Connection pooling and query optimization

### Production Readiness Checklist
- **Load Testing**: Verify system handles expected load
- **Failover Testing**: Test automatic failover mechanisms
- **Security Audit**: Penetration testing and vulnerability scanning
- **Disaster Recovery**: Test backup and restore procedures
- **Documentation**: Runbooks and incident response procedures
- **Monitoring**: Alerts configured for all critical metrics
- **Compliance**: Ensure regulatory requirements are met

### Related Enterprise Guides
- **[Security Patterns](security-patterns.md)** - Authentication and authorization
- **[Gateway Patterns](gateway-patterns.md)** - API gateway and integration
- **[Middleware Patterns](middleware-patterns.md)** - Advanced middleware setup
- **[Compliance Patterns](compliance-patterns.md)** - Regulatory compliance

---

**Ready for production?** Start with containerization, add monitoring, then scale with Kubernetes and implement zero-downtime deployments.
