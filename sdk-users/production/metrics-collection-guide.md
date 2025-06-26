# Comprehensive Metrics Collection Guide

## Overview
The Kailash SDK provides production-grade metrics collection for deep observability into your database operations, connection health, and system performance.

## Quick Start

### Enable Metrics Collection
```python
from kailash.nodes.data import WorkflowConnectionPool

pool = WorkflowConnectionPool(
    name="production_pool",
    database_type="postgresql",
    # Enable comprehensive metrics
    enable_metrics=True,
    metrics_retention_minutes=60,  # Keep 1 hour of detailed metrics
)

# Access metrics
metrics = await pool.get_comprehensive_status()
```

## Metric Types

### 1. Counters (Cumulative Values)
Track totals that only increase:
```python
metrics["counters"] = {
    "connections_created": 152,
    "connections_recycled": 12,
    "queries_executed": 48291,
    "query_errors": 23,
    "circuit_breaker_trips": 2
}
```

### 2. Gauges (Point-in-Time Values)
Current state measurements:
```python
metrics["gauges"] = {
    "active_connections": 8,
    "available_connections": 42,
    "pool_utilization": 0.16,  # 16% utilized
    "average_health_score": 95.2,
    "memory_usage_mb": 124.5
}
```

### 3. Histograms (Distributions)
Track value distributions over time:
```python
metrics["histograms"] = {
    "query_duration_ms": {
        "p50": 2.3,      # Median
        "p95": 45.2,     # 95th percentile
        "p99": 102.5,    # 99th percentile
        "max": 523.1,
        "buckets": {     # Histogram buckets
            "1": 1523,   # Queries under 1ms
            "10": 4821,  # Queries under 10ms
            "100": 523,  # Queries under 100ms
            "1000": 12   # Queries under 1s
        }
    }
}
```

### 4. Time Series Data
Metrics over time windows:
```python
metrics["time_series"] = {
    "qps_1min": [45.2, 48.1, 52.3, ...],  # Queries per second
    "error_rate_1min": [0.001, 0.002, ...],
    "p95_latency_1min": [43.2, 44.1, ...]
}
```

## Connection Metrics

### Pool Utilization
```python
pool_metrics = await pool.get_pool_statistics()

print(f"Total connections: {pool_metrics['total_connections']}")
print(f"Active connections: {pool_metrics['active_connections']}")
print(f"Idle connections: {pool_metrics['idle_connections']}")
print(f"Utilization: {pool_metrics['utilization_percentage']}%")
```

### Connection Health
```python
health_metrics = pool_metrics["health_distribution"]
print(f"Healthy (>80): {health_metrics['healthy']}")
print(f"Degraded (50-80): {health_metrics['degraded']}")
print(f"Unhealthy (<50): {health_metrics['unhealthy']}")
```

### Connection Lifecycle
```python
lifecycle = pool_metrics["connection_lifecycle"]
print(f"Avg connection age: {lifecycle['average_age_seconds']}s")
print(f"Oldest connection: {lifecycle['oldest_connection_age']}s")
print(f"Recycled today: {lifecycle['recycled_count']}")
```

## Query Metrics

### Query Performance by Type
```python
query_metrics = metrics["query_metrics"]

for query_type in ["SELECT", "INSERT", "UPDATE", "DELETE"]:
    stats = query_metrics[query_type]
    print(f"{query_type}:")
    print(f"  Count: {stats['count']}")
    print(f"  Avg time: {stats['avg_time_ms']}ms")
    print(f"  P95 time: {stats['p95_time_ms']}ms")
    print(f"  Error rate: {stats['error_rate']:.2%}")
```

### Slow Query Tracking
```python
slow_queries = metrics["slow_queries"]
for query in slow_queries:
    print(f"Query: {query['query'][:50]}...")
    print(f"Duration: {query['duration_ms']}ms")
    print(f"Timestamp: {query['timestamp']}")
```

## Export Formats

### Prometheus Format
```python
# Enable Prometheus endpoint
prometheus_metrics = pool.metrics_collector.export_prometheus()

# Output format:
# kailash_connections_created_total 152
# kailash_active_connections 8
# kailash_query_duration_ms_bucket{le="10"} 4821
# kailash_query_duration_ms_p95 45.2
```

### JSON Format
```python
# Get metrics as JSON
json_metrics = pool.metrics_collector.export_json()

# Save to file
with open("metrics.json", "w") as f:
    json.dump(json_metrics, f, indent=2)
```

### Custom Export
```python
# Export specific metrics
custom_export = {
    "timestamp": datetime.now().isoformat(),
    "service": "api-gateway",
    "metrics": {
        "qps": metrics["current_qps"],
        "p95_latency": metrics["histograms"]["query_duration_ms"]["p95"],
        "error_rate": metrics["error_rate"],
        "pool_health": metrics["average_health_score"]
    }
}
```

## Real-Time Monitoring

### Metric Streaming
```python
# Stream metrics via callback
def on_metrics_update(metrics):
    # Send to monitoring service
    monitoring_client.send(metrics)

pool.metrics_collector.add_listener(on_metrics_update)
```

### Threshold Alerts
```python
# Set up metric thresholds
thresholds = {
    "error_rate": 0.01,      # Alert if >1% errors
    "p95_latency": 100,      # Alert if P95 >100ms
    "pool_utilization": 0.8   # Alert if >80% utilized
}

async def check_thresholds():
    metrics = await pool.get_comprehensive_status()

    if metrics["error_rate"] > thresholds["error_rate"]:
        alert("High error rate", metrics["error_rate"])

    if metrics["histograms"]["query_duration_ms"]["p95"] > thresholds["p95_latency"]:
        alert("High latency", metrics["histograms"]["query_duration_ms"]["p95"])
```

## Performance Analysis

### Identify Bottlenecks
```python
analysis = pool.analyze_performance()

print("Performance Analysis:")
print(f"Bottleneck: {analysis['primary_bottleneck']}")
print(f"Recommendations: {analysis['recommendations']}")

# Example output:
# Bottleneck: connection_acquisition
# Recommendations: [
#   "Increase min_connections from 5 to 10",
#   "Enable connection pre-warming",
#   "Reduce health check frequency"
# ]
```

### Capacity Planning
```python
capacity = pool.estimate_capacity()

print(f"Current QPS: {capacity['current_qps']}")
print(f"Max sustainable QPS: {capacity['max_qps']}")
print(f"Headroom: {capacity['headroom_percentage']}%")
print(f"Scale at: {capacity['scale_threshold_qps']} QPS")
```

## Best Practices

### 1. Metric Retention
```python
# Short retention for detailed metrics
metrics_retention_minutes=60  # 1 hour of second-level data

# Aggregate older data
hourly_aggregates = aggregate_metrics(metrics, "1h")
daily_aggregates = aggregate_metrics(metrics, "1d")
```

### 2. Selective Collection
```python
# Disable expensive metrics in production
pool = WorkflowConnectionPool(
    enable_query_logging=False,  # Don't log query text
    enable_stack_traces=False,   # Don't collect stack traces
    histogram_buckets=[1, 10, 100, 1000]  # Limit bucket count
)
```

### 3. Metric Naming
```python
# Use consistent naming conventions
metric_names = {
    "kailash.pool.connections.active",
    "kailash.pool.connections.total",
    "kailash.query.duration.p95",
    "kailash.query.count.by_type",
    "kailash.circuit_breaker.state"
}
```

## Integration Examples

### Grafana Dashboard
```json
{
  "dashboard": {
    "title": "Kailash Connection Pool",
    "panels": [
      {
        "title": "Query Rate",
        "targets": [{
          "expr": "rate(kailash_queries_executed_total[1m])"
        }]
      },
      {
        "title": "P95 Latency",
        "targets": [{
          "expr": "kailash_query_duration_ms_p95"
        }]
      }
    ]
  }
}
```

### CloudWatch Integration
```python
import boto3

cloudwatch = boto3.client('cloudwatch')

async def publish_metrics():
    metrics = await pool.get_comprehensive_status()

    cloudwatch.put_metric_data(
        Namespace='KailashSDK',
        MetricData=[
            {
                'MetricName': 'QueryLatencyP95',
                'Value': metrics['histograms']['query_duration_ms']['p95'],
                'Unit': 'Milliseconds'
            },
            {
                'MetricName': 'ConnectionPoolUtilization',
                'Value': metrics['gauges']['pool_utilization'] * 100,
                'Unit': 'Percent'
            }
        ]
    )
```

## Troubleshooting

### High Memory Usage
- Reduce `metrics_retention_minutes`
- Limit histogram buckets
- Disable query logging

### Missing Metrics
- Ensure `enable_metrics=True`
- Check metric export format
- Verify retention period

### Performance Impact
- Metrics add <1% overhead
- Use sampling for high-volume
- Aggregate before export

## Related Guides
- [Circuit Breaker Guide](./circuit-breaker-guide.md)
- [Query Pipeline Guide](./query-pipeline-guide.md)
- [Monitoring Dashboard](./monitoring-dashboard-guide.md)
