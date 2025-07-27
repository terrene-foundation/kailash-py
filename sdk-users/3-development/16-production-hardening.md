# Production Hardening Guide

*Enterprise resilience features for production-ready applications*

## Overview

This guide covers advanced production features that make your Kailash applications resilient, observable, and performant at scale. These features include circuit breakers, comprehensive metrics, and monitoring capabilities.

## Prerequisites

- Completed [Production](04-production.md) - Basic production concepts
- Understanding of [Connection Pool](14-connection-pool-guide.md)
- Familiarity with monitoring tools (Prometheus/Grafana)

## Circuit Breaker Protection

### Why Circuit Breakers?

Circuit breakers prevent cascading failures in distributed systems:

```python
# Without circuit breaker - cascading failure
try:
    result = await db.query("SELECT * FROM users")  # Database is down
except Exception:
    # Retry logic makes it worse
    for attempt in range(5):
        result = await db.query("SELECT * FROM users")  # More load!
    # Thread pool exhausted, application freezes

# With circuit breaker - fail fast
from kailash.core.resilience.circuit_breaker import CircuitBreakerManager, CircuitBreakerConfig, CircuitBreakerError

manager = CircuitBreakerManager()
config = CircuitBreakerConfig(failure_threshold=5, success_threshold=2)
breaker = manager.get_or_create("database_operations", config)

try:
    result = await breaker.call(db.query, "SELECT * FROM users")
except CircuitBreakerError:
    # Return cached data or degraded response
    return cached_users
```

### Circuit Breaker States

```
CLOSED (Normal) → OPEN (Failing) → HALF_OPEN (Testing) → CLOSED
       ↑                                      ↓
       ←──────────── Success ←───────────────┘
```

1. **CLOSED**: Normal operation, monitoring for failures
2. **OPEN**: Failing fast, no load on failing service
3. **HALF_OPEN**: Testing recovery with limited requests

### Using Circuit Breakers

#### Basic Implementation

```python
from kailash.core.resilience import CircuitBreakerConfig, ConnectionCircuitBreaker
from kailash.workflow import AsyncWorkflowBuilder

# Create circuit breaker configuration
config = CircuitBreakerConfig(
    failure_threshold=5,          # Open after 5 failures
    recovery_timeout=60,          # Try recovery after 60s
    error_rate_threshold=0.5,     # Open if error rate > 50%
    window_size=100               # Rolling window for error rate
)

# Create circuit breaker
circuit_breaker = ConnectionCircuitBreaker(config)

# Use in workflow
workflow = (
    AsyncWorkflowBuilder("protected_workflow")
    .add_async_code("fetch_data", """
from kailash.core.resilience import CircuitBreakerManager

# Get circuit breaker from manager
manager = CircuitBreakerManager()
breaker = manager.get_or_create("database_breaker", config)
db = await get_resource("database")

try:
    # Protected database call
    async def query_users():
        async with db.acquire() as conn:
            return await conn.fetch("SELECT * FROM users")

    users = await breaker.call(query_users)
    result = {"users": [dict(u) for u in users]}

except CircuitBreakerError:
    # Circuit is open - use fallback
    cache = await get_resource("cache")
    cached_data = await cache.get("users:backup")
    result = {"users": cached_data, "from_cache": True}
""")
    .build()
)
```

#### With Connection Pool

```python
from kailash.nodes.data import WorkflowConnectionPool

# Connection pool with built-in circuit breaker
pool = WorkflowConnectionPool(
    name="protected_pool",
    database_type="postgresql",
    host="localhost",
    database="production",

    # Circuit breaker configuration
    enable_circuit_breaker=True,
    circuit_breaker_failure_threshold=5,
    circuit_breaker_recovery_timeout=60,
    circuit_breaker_error_rate_threshold=0.5
)

# Use normally - protection is automatic
workflow.add_node("WorkflowConnectionPool", "db_pool", {
    "enable_circuit_breaker": True,
    "circuit_breaker_failure_threshold": 3,  # More sensitive
    "circuit_breaker_recovery_timeout": 120  # Slower recovery
})
```

### Configuration Strategies

#### Conservative (Financial Systems)

```python
# Fail fast, recover slowly
circuit_breaker = CircuitBreaker(
    failure_threshold=3,        # Open quickly
    recovery_timeout=300,       # 5 minute recovery
    error_rate_threshold=0.1,   # 10% error rate
    half_open_max_calls=1       # Very cautious testing
)
```

#### Balanced (E-commerce)

```python
# Standard protection
circuit_breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60,
    error_rate_threshold=0.5,
    half_open_max_calls=3
)
```

#### Tolerant (Analytics)

```python
# Allow more failures
circuit_breaker = CircuitBreaker(
    failure_threshold=10,
    recovery_timeout=30,
    error_rate_threshold=0.7,
    half_open_max_calls=5
)
```

## Comprehensive Metrics

### Automatic Metrics Collection

The SDK automatically collects detailed metrics:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.tracking import MetricsCollector

# Enable metrics collection
metrics = MetricsCollector(
    sampling_interval=0.1  # Sample every 100ms
)

# Metrics are collected for:
# - Workflow execution times
# - Node processing times
# - Resource usage
# - Error rates and types
# - Circuit breaker states
```

### Accessing Metrics

```python
# Get workflow metrics
workflow_metrics = metrics.get_workflow_metrics("data_pipeline")

print(f"Executions: {workflow_metrics['total_executions']}")
print(f"Success rate: {workflow_metrics['success_rate']:.2%}")
print(f"Avg duration: {workflow_metrics['avg_duration_ms']:.1f}ms")
print(f"P95 duration: {workflow_metrics['p95_duration_ms']:.1f}ms")

# Get resource metrics
db_metrics = metrics.get_resource_metrics("database")

print(f"Queries/sec: {db_metrics['queries_per_second']:.1f}")
print(f"Error rate: {db_metrics['error_rate']:.2%}")
print(f"Avg latency: {db_metrics['avg_latency_ms']:.1f}ms")
```

### Error Analysis

```python
# Get error breakdown
error_analysis = metrics.get_error_analysis()

# By category
for category, count in error_analysis['by_category'].items():
    print(f"{category}: {count}")
    # Categories: connection_timeout, query_error,
    # authentication_failed, pool_exhausted, etc.

# By time
hourly_errors = error_analysis['hourly_breakdown']
for hour, errors in hourly_errors.items():
    print(f"{hour}: {errors} errors")

# Most common errors
top_errors = error_analysis['top_errors']
for error_type, details in top_errors[:5]:
    print(f"{error_type}: {details['count']} occurrences")
    print(f"  Last seen: {details['last_seen']}")
    print(f"  Sample: {details['sample_message']}")
```

## Monitoring Integration

### Prometheus Export

```python
from kailash.core.monitoring import PrometheusExporter

# Create exporter
exporter = PrometheusExporter(
    port=9090,
    path="/metrics",
    include_labels=["workflow", "node", "resource"]
)

# Start exporter
await exporter.start()

# Metrics available at http://localhost:9090/metrics
# Example metrics:
# kailash_workflow_duration_seconds{workflow="data_pipeline"} 1.23
# kailash_node_errors_total{node="database_query"} 5
# kailash_circuit_breaker_state{name="database"} 1  # 1=closed, 2=open
```

### Grafana Dashboard

Create dashboards with key metrics:

```json
{
  "dashboard": {
    "title": "Kailash Production Metrics",
    "panels": [
      {
        "title": "Workflow Success Rate",
        "targets": [{
          "expr": "rate(kailash_workflow_success_total[5m]) / rate(kailash_workflow_total[5m])"
        }]
      },
      {
        "title": "Circuit Breaker Status",
        "targets": [{
          "expr": "kailash_circuit_breaker_state"
        }]
      },
      {
        "title": "Database Pool Utilization",
        "targets": [{
          "expr": "kailash_pool_active_connections / kailash_pool_max_connections"
        }]
      }
    ]
  }
}
```

### Alerting Rules

```yaml
# Prometheus alerting rules
groups:
  - name: kailash_alerts
    rules:
      # Circuit breaker open
      - alert: CircuitBreakerOpen
        expr: kailash_circuit_breaker_state == 2
        for: 1m
        annotations:
          summary: "Circuit breaker {{ $labels.name }} is open"

      # High error rate
      - alert: HighErrorRate
        expr: rate(kailash_errors_total[5m]) > 0.05
        for: 5m
        annotations:
          summary: "Error rate above 5%"

      # Pool exhaustion
      - alert: ConnectionPoolExhausted
        expr: kailash_pool_available_connections == 0
        for: 30s
        annotations:
          summary: "Connection pool {{ $labels.pool }} exhausted"
```

## Health Checks

### Implementing Health Endpoints

```python
from kailash.health import HealthChecker

# Create health checker
health = HealthChecker()

# Add component checks
health.add_check("database", check_database_health)
health.add_check("cache", check_cache_health)
health.add_check("external_api", check_api_health, critical=False)

# Health check implementation
async def check_database_health():
    try:
        pool = get_resource("database")
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
        return {"status": "healthy", "latency_ms": 5}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

# Get overall health
overall_health = await health.check_all()
# Returns: {
#   "status": "healthy",  # or "degraded", "unhealthy"
#   "checks": {
#     "database": {"status": "healthy", "latency_ms": 5},
#     "cache": {"status": "healthy", "latency_ms": 1},
#     "external_api": {"status": "unhealthy", "error": "timeout"}
#   }
# }
```

### Kubernetes Integration

```yaml
# Kubernetes deployment with health checks
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kailash-app
spec:
  template:
    spec:
      containers:
      - name: app
        image: myapp:latest
        ports:
        - containerPort: 8080
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
```

## Performance Optimization

### Connection Pool Tuning

```python
# Production-optimized pool configuration
pool = WorkflowConnectionPool(
    name="optimized_pool",

    # Size for expected load
    min_connections=10,      # Pre-warmed connections
    max_connections=50,      # Peak capacity

    # Fast acquisition
    connection_timeout=5.0,  # Fail fast if can't acquire

    # Health management
    health_check_interval=30.0,
    max_lifetime=3600.0,     # Recycle hourly
    max_idle_time=300.0,     # Recycle if idle 5 min

    # Monitoring
    enable_metrics=True,
    metrics_interval=10.0
)
```

### Caching Strategy

```python
# Implement caching with fallback
workflow = (
    AsyncWorkflowBuilder("cached_workflow")
    .add_async_code("fetch_with_cache", """
cache = await get_resource("cache")
db = await get_resource("database")

# Try cache first
cache_key = f"users:{user_id}"
cached = await cache.get(cache_key)

if cached:
    result = {"user": json.loads(cached), "from_cache": True}
else:
    # Fetch from database
    async with db.acquire() as conn:
        user = await conn.fetchone(
            "SELECT * FROM users WHERE id = $1", user_id
        )

    if user:
        user_dict = dict(user)
        # Cache for 5 minutes
        await cache.setex(cache_key, 300, json.dumps(user_dict))
        result = {"user": user_dict, "from_cache": False}
    else:
        result = {"user": None, "from_cache": False}
""")
    .build()
)
```

## Best Practices

### 1. Graceful Degradation

```python
# Always have fallback strategies
async def get_user_data(user_id):
    # Try primary source
    try:
        return await fetch_from_database(user_id)
    except CircuitBreakerError:
        # Try cache
        cached = await fetch_from_cache(user_id)
        if cached:
            return {"user": cached, "degraded": True}
    except Exception:
        # Return minimal data
        return {"user": {"id": user_id}, "error": True}
```

### 2. Timeout Configuration

```python
# Set appropriate timeouts at every level
workflow = (
    AsyncWorkflowBuilder("timeout_aware")
    .add_async_code("query", """
# Node-level timeout
async with timeout(30):  # 30 second total
    db = await get_resource("database")

    # Query-level timeout
    async with db.acquire() as conn:
        # Set statement timeout
        await conn.execute("SET statement_timeout = '5s'")
        result = await conn.fetch("SELECT * FROM large_table")
""")
    .with_timeout(60)  # Workflow-level timeout
    .build()
)
```

### 3. Resource Limits

```python
# Implement resource limits
from kailash.nodes.api.rate_limiting import RateLimitConfig, TokenBucketRateLimiter

# Rate limiting configuration
config = RateLimitConfig(
    max_requests=100,
    time_window=1.0,  # 1 second = 100 requests per second
    strategy="token_bucket",
    burst_limit=150
)

# Create rate limiter
rate_limiter = TokenBucketRateLimiter(config)

# Use in async context
async def process_data(data):
    # Check rate limit
    if await rate_limiter.acquire():
        # Processing logic
        result = await process(data)
        return result
    else:
        raise Exception("Rate limit exceeded")
```

## Troubleshooting

### Circuit Breaker Issues

```python
# Debug circuit breaker state
from kailash.core.resilience import CircuitBreakerManager

manager = CircuitBreakerManager()
breaker = manager.get_breaker("database")

if breaker:
    metrics = breaker.metrics
    print(f"Current state: {breaker.state}")
    print(f"Total calls: {metrics.total_calls}")
    print(f"Failed calls: {metrics.failed_calls}")
    print(f"Rejected calls: {metrics.rejected_calls}")
    print(f"Success rate: {breaker.get_success_rate():.2%}")

    # Check if should transition state
    if breaker._should_attempt_reset():
        print("Circuit breaker ready to test recovery")
```

### Metrics Not Appearing

```python
# Verify metrics collection
metrics = MetricsCollector.get_instance()

# Check if enabled
print(f"Metrics enabled: {metrics.is_enabled()}")

# List registered metrics
for metric in metrics.list_metrics():
    print(f"{metric['name']}: {metric['type']}")

# Force metric export
await metrics.export_now()
```

## Related Guides

**Prerequisites:**
- [Production](04-production.md) - Basic production concepts
- [Connection Pool](14-connection-pool-guide.md) - Database pooling

**Advanced Topics:**
- [Monitoring](../monitoring/) - Detailed monitoring setup
- [Performance](../performance/) - Performance optimization

---

**Build resilient, observable, and performant production applications with Kailash's hardening features!**
