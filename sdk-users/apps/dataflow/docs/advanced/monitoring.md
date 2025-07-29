# DataFlow Monitoring Guide

Comprehensive guide to monitoring DataFlow applications in production.

## Overview

Effective monitoring is crucial for maintaining healthy DataFlow applications. This guide covers metrics collection, alerting, performance tracking, and troubleshooting.

## Metrics Collection

### Built-in Metrics

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash_dataflow import DataFlow, MetricsCollector

# Enable metrics collection
db = DataFlow(
    config=config,
    metrics_enabled=True,
    metrics_backend="prometheus"  # or "statsd", "cloudwatch"
)

# Access metrics
metrics = db.get_metrics()
print(f"Total queries: {metrics['queries_total']}")
print(f"Query errors: {metrics['query_errors_total']}")
print(f"Avg query time: {metrics['query_duration_seconds_avg']}")
```

### Workflow Metrics

```python
workflow = WorkflowBuilder()

# Enable workflow metrics
workflow.add_node("MetricsContextNode", "enable_metrics", {
    "track": [
        "execution_time",
        "node_duration",
        "memory_usage",
        "connection_usage",
        "cache_hits"
    ],
    "labels": {
        "app": "dataflow",
        "environment": "production",
        "version": "1.0.0"
    }
})

# Track custom metrics
workflow.add_node("MetricNode", "track_business_metric", {
    "metric_name": "orders_processed",
    "value": ":order_count",
    "metric_type": "counter",
    "labels": {
        "region": ":region",
        "customer_tier": ":tier"
    }
})
```

### Database Metrics

```python
# Monitor database performance
workflow.add_node("DatabaseMetricsNode", "db_metrics", {
    "metrics": [
        "connection_pool_size",
        "active_connections",
        "idle_connections",
        "wait_queue_size",
        "transaction_duration",
        "lock_wait_time",
        "deadlock_count",
        "slow_query_count"
    ],
    "interval": "10s"
})

# Analyze metrics
workflow.add_node("PythonCodeNode", "analyze_db_health", {
    "code": """
metrics = get_input_data("db_metrics")

# Check connection pool health
pool_usage = metrics["active_connections"] / metrics["connection_pool_size"]
if pool_usage > 0.8:
    emit_metric("pool_exhaustion_risk", pool_usage)
    send_alert("Connection pool near capacity", severity="warning")

# Check for issues
if metrics["deadlock_count"] > 0:
    send_alert(f"Deadlocks detected: {metrics['deadlock_count']}", severity="critical")

if metrics["slow_query_count"] > 10:
    trigger_slow_query_analysis()
"""
})
```

## Prometheus Integration

### Exporter Configuration

```python
# Configure Prometheus exporter
from kailash_dataflow.monitoring import PrometheusExporter

exporter = PrometheusExporter(
    port=9090,
    path="/metrics",
    include_golang_metrics=False
)

# Register with DataFlow
db.register_exporter(exporter)

# Custom metrics
from prometheus_client import Counter, Histogram, Gauge

# Define metrics
query_counter = Counter(
    'dataflow_queries_total',
    'Total number of queries executed',
    ['model', 'operation', 'status']
)

query_duration = Histogram(
    'dataflow_query_duration_seconds',
    'Query execution time',
    ['model', 'operation'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
)

connection_gauge = Gauge(
    'dataflow_active_connections',
    'Number of active database connections',
    ['database']
)
```

### Grafana Dashboard

```json
{
  "dashboard": {
    "title": "DataFlow Monitoring",
    "panels": [
      {
        "title": "Query Rate",
        "targets": [
          {
            "expr": "rate(dataflow_queries_total[5m])",
            "legendFormat": "{{model}} - {{operation}}"
          }
        ]
      },
      {
        "title": "Query Duration",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, dataflow_query_duration_seconds)",
            "legendFormat": "95th percentile"
          }
        ]
      },
      {
        "title": "Error Rate",
        "targets": [
          {
            "expr": "rate(dataflow_errors_total[5m])",
            "legendFormat": "{{error_type}}"
          }
        ]
      },
      {
        "title": "Connection Pool",
        "targets": [
          {
            "expr": "dataflow_active_connections / dataflow_pool_size",
            "legendFormat": "Pool Usage %"
          }
        ]
      }
    ]
  }
}
```

## Performance Monitoring

### Query Performance

```python
workflow = WorkflowBuilder()

# Enable query profiling
workflow.add_node("QueryProfilerNode", "enable_profiler", {
    "profile_queries": True,
    "slow_query_threshold": 1.0,  # 1 second
    "explain_slow_queries": True,
    "sample_rate": 0.1  # Profile 10% of queries
})

# Monitor slow queries
workflow.add_node("SlowQueryMonitorNode", "monitor_slow", {
    "check_interval": "1m",
    "actions": {
        "log": True,
        "alert": True,
        "analyze": True,
        "suggest_indexes": True
    }
})

# Analyze query patterns
workflow.add_node("QueryAnalyzerNode", "analyze_patterns", {
    "lookback_period": "1h",
    "group_by": ["model", "operation", "filter_fields"],
    "identify": [
        "missing_indexes",
        "full_table_scans",
        "n_plus_one_queries",
        "unnecessary_joins"
    ]
})
```

### Memory Monitoring

```python
# Track memory usage
workflow.add_node("MemoryMonitorNode", "memory_check", {
    "thresholds": {
        "warning": "80%",
        "critical": "90%"
    },
    "track": [
        "heap_usage",
        "connection_memory",
        "cache_memory",
        "query_result_memory"
    ]
})

# Memory leak detection
workflow.add_node("MemoryLeakDetectorNode", "detect_leaks", {
    "baseline_period": "10m",
    "growth_threshold": "10%",
    "check_interval": "5m",
    "actions": {
        "profile_heap": True,
        "identify_growing_objects": True,
        "alert_on_leak": True
    }
})
```

## Application Performance Monitoring (APM)

### Distributed Tracing

```python
# OpenTelemetry integration
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Configure tracing
tracer = trace.get_tracer("dataflow-app")

# Instrument workflows
@trace_workflow
def process_order(order_id):
    with tracer.start_as_current_span("process_order") as span:
        span.set_attribute("order.id", order_id)

        workflow = WorkflowBuilder()

        # Each node automatically traced
        workflow.add_node("OrderReadNode", "get_order", {
            "id": order_id,
            "trace": True
        })

        workflow.add_node("InventoryCheckNode", "check_inventory", {
            "items": ":order_items",
            "trace": True
        })

        runtime = LocalRuntime()
        return runtime.execute(workflow.build())
```

### Custom Spans

```python
workflow.add_node("PythonCodeNode", "custom_logic", {
    "code": """
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

# Create custom span
with tracer.start_as_current_span("custom_operation") as span:
    span.set_attribute("user.id", user_id)
    span.set_attribute("operation.type", "batch_process")

    # Perform operation
    result = process_batch(data)

    # Record metrics
    span.set_attribute("items.processed", len(result))
    span.set_attribute("duration.ms", elapsed_ms)

    # Record events
    span.add_event("batch_completed", {
        "item_count": len(result),
        "success_rate": success_count / len(result)
    })
"""
})
```

## Alerting

### Alert Configuration

```python
# Configure alerting rules
alert_config = {
    "rules": [
        {
            "name": "high_error_rate",
            "condition": "rate(errors) > 0.05",  # 5% error rate
            "duration": "5m",
            "severity": "critical",
            "channels": ["pagerduty", "slack"]
        },
        {
            "name": "slow_queries",
            "condition": "p95(query_duration) > 2.0",  # 2 seconds
            "duration": "10m",
            "severity": "warning",
            "channels": ["slack", "email"]
        },
        {
            "name": "connection_pool_exhausted",
            "condition": "active_connections >= pool_size",
            "duration": "1m",
            "severity": "critical",
            "channels": ["pagerduty"]
        }
    ]
}

workflow.add_node("AlertManagerNode", "configure_alerts", {
    "config": alert_config,
    "enable": True
})
```

### Custom Alerts

```python
workflow.add_node("PythonCodeNode", "custom_alert_logic", {
    "code": """
# Business-specific alerting
metrics = get_input_data("business_metrics")

# Revenue drop alert
if metrics["revenue_per_minute"] < expected_revenue * 0.8:
    alert = {
        "title": "Revenue Drop Detected",
        "severity": "critical",
        "message": f"Revenue at {metrics['revenue_per_minute']}, expected {expected_revenue}",
        "runbook": "https://wiki/runbooks/revenue-drop",
        "data": metrics
    }
    send_alert(alert)

# User experience alerts
if metrics["checkout_failure_rate"] > 0.02:  # 2%
    alert = {
        "title": "High Checkout Failure Rate",
        "severity": "high",
        "message": f"Checkout failures at {metrics['checkout_failure_rate']*100}%",
        "affected_users": metrics["failed_checkouts"],
        "suggested_action": "Check payment gateway status"
    }
    send_alert(alert)
"""
})
```

## Logging

### Structured Logging

```python
# Configure structured logging
import structlog

logger = structlog.get_logger()

# Log with context
logger.info(
    "workflow_executed",
    workflow_id=workflow_id,
    duration_ms=duration,
    node_count=len(nodes),
    status="success"
)

# Automatic context injection
@db.with_logging_context
def process_request(request_id):
    # All logs within this function include request_id
    logger.info("Processing request")

    workflow = WorkflowBuilder()
    # ... workflow definition ...

    logger.info("Workflow completed", nodes_executed=5)
```

### Log Aggregation

```python
# Send logs to centralized system
workflow.add_node("LogShipperNode", "configure_shipping", {
    "destinations": [
        {
            "type": "elasticsearch",
            "url": "https://logs.example.com",
            "index": "dataflow-{date}"
        },
        {
            "type": "cloudwatch",
            "log_group": "/aws/dataflow/production"
        }
    ],
    "include_fields": [
        "timestamp",
        "level",
        "message",
        "workflow_id",
        "node_id",
        "tenant_id",
        "user_id",
        "duration_ms",
        "error"
    ],
    "exclude_patterns": [
        "password",
        "token",
        "secret"
    ]
})
```

## Health Checks

### Endpoint Configuration

```python
# Health check endpoint
from kailash_dataflow.monitoring import HealthCheck

health = HealthCheck()

# Add checks
health.add_check("database", check_database_connection)
health.add_check("redis", check_redis_connection)
health.add_check("disk_space", check_disk_space)
health.add_check("memory", check_memory_usage)

# Expose endpoint
app.add_route("/health", health.endpoint)
app.add_route("/health/live", health.liveness)
app.add_route("/health/ready", health.readiness)
```

### Custom Health Checks

```python
def check_critical_services():
    """Check critical service health."""
    checks = []

    # Database check
    try:
        db.execute("SELECT 1")
        checks.append({"database": "healthy"})
    except Exception as e:
        checks.append({"database": "unhealthy", "error": str(e)})

    # Cache check
    try:
        cache.set("health_check", "ok", ex=10)
        checks.append({"cache": "healthy"})
    except Exception as e:
        checks.append({"cache": "unhealthy", "error": str(e)})

    # External API check
    try:
        response = requests.get("https://api.service.com/health", timeout=5)
        if response.status_code == 200:
            checks.append({"external_api": "healthy"})
        else:
            checks.append({"external_api": "unhealthy", "status": response.status_code})
    except Exception as e:
        checks.append({"external_api": "unhealthy", "error": str(e)})

    return all(check.get(list(check.keys())[0]) == "healthy" for check in checks), checks
```

## Debugging Production Issues

### Debug Mode

```python
# Enable debug mode for specific workflows
workflow.add_node("DebugContextNode", "enable_debug", {
    "level": "detailed",
    "capture": [
        "sql_queries",
        "sql_explain_plans",
        "memory_snapshots",
        "timing_breakdown",
        "connection_trace"
    ],
    "condition": "request_header['X-Debug-Token'] == debug_token"
})
```

### Production Profiling

```python
# Profile specific requests
workflow.add_node("ProfilerNode", "profile_request", {
    "profile_type": "cpu",  # or "memory", "io"
    "duration": 30,  # seconds
    "output": "flame_graph",
    "upload_to": "s3://profiles/dataflow/"
})
```

## Best Practices

1. **Monitor Everything**: Instrument all critical paths
2. **Set Meaningful Alerts**: Avoid alert fatigue with smart thresholds
3. **Use Structured Logging**: Make logs searchable and analyzable
4. **Track Business Metrics**: Not just technical metrics
5. **Regular Reviews**: Weekly metric reviews to spot trends

## Next Steps

- **Security**: [Security Guide](security.md)
- **Performance**: [Performance Guide](../production/performance.md)
- **Troubleshooting**: [Troubleshooting Guide](../production/troubleshooting.md)

Comprehensive monitoring is essential for production DataFlow applications. Implement multiple layers of monitoring for complete visibility.
