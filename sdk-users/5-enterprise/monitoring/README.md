# Monitoring & Observability Guide

*Complete monitoring patterns for Kailash SDK applications*

## 📊 Quick Start Monitoring

```python
from kailash.runtime.local import LocalRuntime
from kailash.monitoring import MetricsCollector, TracingProvider

# Enable monitoring in runtime
runtime = LocalRuntime(
    enable_monitoring=True,
    enable_tracing=True,
    metrics_export_interval=60,
    trace_sample_rate=0.1  # 10% sampling
)

# Execute with monitoring
results, run_id = runtime.execute(workflow.build())

# Get execution metrics
metrics = runtime.get_metrics(run_id)
print(f"Total time: {metrics['total_time_ms']}ms")
print(f"Node metrics: {metrics['node_metrics']}")

```

## 🔍 Monitoring Layers

### 1. **Application Metrics**
- Workflow execution times
- Node performance metrics
- Error rates and types
- Resource utilization

### 2. **Infrastructure Metrics**
- CPU and memory usage
- Network I/O
- Database connections
- Cache hit rates

### 3. **Business Metrics**
- Transaction volumes
- Processing throughput
- Success/failure rates
- SLA compliance

## 📈 Metrics Collection

### Built-in Metrics
```python
# Automatic metrics collection
workflow.add_node("DataProcessorNode", "processor", {}))

# Custom metrics collector
workflow.add_node("MetricsCollectorNode", "metrics", {}))

```

### Custom Metrics
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.code import PythonCodeNode

workflow = WorkflowBuilder()
runtime = LocalRuntime(enable_monitoring=True)

workflow.add_node("PythonCodeNode", "custom_metrics", {})

# Process data
processed = process_items(data)

# Record custom metrics
metrics = {
    "processing_duration_ms": (time.time() - start) * 1000,
    "items_processed": len(processed),
    "success_rate": len([p for p in processed if p["success"]]) / len(processed),
    "avg_item_size": sum(p["size"] for p in processed) / len(processed)
}

# Export to monitoring system
export_metrics(metrics)

result = {"data": processed, "metrics": metrics}
''',
    input_types={"data": list}
))

```

## 🔍 Distributed Tracing

### OpenTelemetry Integration
```python
from kailash.monitoring import OpenTelemetryProvider

# Configure tracing
tracing = OpenTelemetryProvider(
    service_name="kailash-app",
    endpoint="http://jaeger:4318",
    environment="production"
)

# Traced workflow execution
with tracing.start_span("workflow_execution") as span:
    span.set_attribute("workflow.id", workflow.id)
    span.set_attribute("workflow.name", workflow.name)

    results, run_id = runtime.execute(workflow.build())

    span.set_attribute("execution.run_id", run_id)
    span.set_status("OK" if results else "ERROR")

```

### Trace Context Propagation
```python
workflow.add_node("HTTPRequestNode", "traced_api", {}),
        "tracestate": ctx.get_trace_state()
    }
))

```

## 📊 Monitoring Dashboards

### Prometheus + Grafana Setup
```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'kailash-app'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
```

### Key Metrics to Monitor
```python
CRITICAL_METRICS = {
    # Performance
    "workflow_execution_time": {
        "type": "histogram",
        "alert_threshold": 5000,  # 5 seconds
        "aggregation": "p95"
    },

    # Reliability
    "workflow_error_rate": {
        "type": "gauge",
        "alert_threshold": 0.01,  # 1% error rate
        "window": "5m"
    },

    # Throughput
    "workflows_per_second": {
        "type": "counter",
        "alert_threshold": 100,
        "aggregation": "rate"
    },

    # Resources
    "memory_usage_mb": {
        "type": "gauge",
        "alert_threshold": 1024,  # 1GB
        "action": "scale_up"
    }
}

```

## 🚨 Alerting

### Alert Configuration
```python
from kailash.monitoring import AlertManager

alerts = AlertManager(
    webhook_url="https://alerts.company.com/webhook",
    channels=["email", "slack", "pagerduty"]
)

# Define alert rules
alerts.add_rule(
    name="high_error_rate",
    condition="error_rate > 0.05",
    severity="critical",
    notification_channels=["pagerduty"],
    cooldown_minutes=15
)

alerts.add_rule(
    name="slow_execution",
    condition="p95_latency > 10000",
    severity="warning",
    notification_channels=["slack"],
    aggregation_window="5m"
)

```

### Health Checks
```python
workflow.add_node("HealthCheckNode", "health_check", {}))

```

## 📈 Performance Monitoring

### Profiling
```python
from kailash.monitoring import PerformanceProfiler

# Profile workflow execution
with PerformanceProfiler() as profiler:
    results, run_id = runtime.execute(workflow.build())

profile_data = profiler.get_profile()
print(f"CPU time: {profile_data['cpu_time_ms']}ms")
print(f"Memory peak: {profile_data['memory_peak_mb']}MB")
print(f"Slowest nodes: {profile_data['slowest_nodes']}")

```

### Resource Monitoring
```python
workflow.add_node("PythonCodeNode", "resource_monitor", {})
cpu_percent = process.cpu_percent(interval=1)
memory_info = process.memory_info()

# Custom resource metrics
resource_metrics = {
    "cpu_usage_percent": cpu_percent,
    "memory_usage_mb": memory_info.rss / 1024 / 1024,
    "memory_usage_percent": process.memory_percent(),
    "open_files": len(process.open_files()),
    "num_threads": process.num_threads()
}

# Export metrics
export_metrics(resource_metrics)

result = {"resource_metrics": resource_metrics}
'''
))

```

## 🔄 Log Aggregation

### Structured Logging
```python
import structlog
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.code import PythonCodeNode

# Configure structured logging
logger = structlog.get_logger()
workflow = WorkflowBuilder()

workflow.add_node("PythonCodeNode", "logged_processor", {})

logger.info("processing_started",
    items_count=len(data),
    source="api",
    correlation_id=context.get("correlation_id")
)

try:
    processed = process_data(data)
    logger.info("processing_completed",
        items_processed=len(processed),
        duration_ms=elapsed_ms
    )
    result = {"data": processed}

except Exception as e:
    logger.error("processing_failed",
        error=str(e),
        error_type=type(e).__name__,
        stack_trace=traceback.format_exc()
    )
    result = {"error": str(e)}
''',
    input_types={"data": list}
))

```

### Log Export
```python
# Export logs to centralized system
workflow.add_node("PythonCodeNode", "log_exporter", {}).isoformat(),
        "level": "INFO",
        "service": "kailash_workflow",
        "event_type": event["type"],
        "correlation_id": context.get("correlation_id"),
        "data": event["data"]
    }
    log_entries.append(log_entry)

# Export to log aggregation service
if log_entries:
    try:
        response = requests.post(
            "https://logs.company.com/api/bulk",
            json={"logs": log_entries},
            headers={"Authorization": f"Bearer {log_api_token}"}
        )
        response.raise_for_status()
    except Exception as e:
        logger.error("Failed to export logs", error=str(e))

result = {"logs_exported": len(log_entries)}
''',
    input_types={"processing_events": list, "context": dict}
))

```

## 🎯 SLA Monitoring

```python
# SLA compliance monitoring
workflow.add_node("PythonCodeNode", "sla_monitor", {})
window_start = current_time - timedelta(hours=24)

# Availability calculation
total_requests = sum(metrics["requests"])
successful_requests = total_requests - sum(metrics["errors"])
availability = successful_requests / total_requests if total_requests > 0 else 1.0

# Response time P95
response_times = metrics["response_times"]
response_times.sort()
p95_index = int(len(response_times) * 0.95)
p95_response_time = response_times[p95_index] if response_times else 0

# Error rate
error_rate = sum(metrics["errors"]) / total_requests if total_requests > 0 else 0

# SLA compliance status
sla_status = {
    "availability": {
        "actual": availability,
        "target": sla_targets["availability"],
        "compliant": availability >= sla_targets["availability"]
    },
    "response_time_p95": {
        "actual": p95_response_time,
        "target": sla_targets["response_time_p95"],
        "compliant": p95_response_time <= sla_targets["response_time_p95"]
    },
    "error_rate": {
        "actual": error_rate,
        "target": sla_targets["error_rate"],
        "compliant": error_rate <= sla_targets["error_rate"]
    }
}

result = {"sla_status": sla_status, "timestamp": current_time.isoformat()}
''',
    input_types={"metrics": dict}
))

```

## 📊 Monitoring Best Practices

### 1. **Use Appropriate Metrics**
- Counter: For cumulative values (requests, errors)
- Gauge: For current values (memory, connections)
- Histogram: For distributions (latency, sizes)
- Summary: For percentiles over time

### 2. **Set Meaningful Alerts**
- Alert on symptoms, not causes
- Include context in alerts
- Set appropriate thresholds
- Implement alert fatigue prevention

### 3. **Dashboard Guidelines**
- One dashboard per service/workflow
- Include both technical and business metrics
- Use consistent time ranges
- Add annotations for deployments

### 4. **Retention Policies**
- High-frequency metrics: 7 days
- Aggregated metrics: 30 days
- Daily summaries: 1 year
- Critical business metrics: 5 years

## 🔗 Integration Examples

### Datadog Integration
```python
from kailash.monitoring.integrations import DatadogExporter

exporter = DatadogExporter(
    api_key="${DD_API_KEY}",
    app_key="${DD_APP_KEY}",
    site="datadoghq.com",
    tags=["env:prod", "service:kailash"]
)

runtime = LocalRuntime(
    metrics_exporter=exporter,
    custom_metrics_prefix="kailash.app"
)

```

### AWS CloudWatch
```python
from kailash.monitoring.integrations import CloudWatchExporter

exporter = CloudWatchExporter(
    namespace="Kailash/Application",
    region="us-east-1",
    dimensions={
        "Environment": "production",
        "Service": "workflow-processor"
    }
)

```

## 🔗 Next Steps

- [Performance Patterns](../architecture/performance-patterns.md) - Performance optimization
- [Production Guide](../developer/04-production.md) - Production monitoring
- [Troubleshooting](../developer/05-troubleshooting.md) - Debug with metrics
