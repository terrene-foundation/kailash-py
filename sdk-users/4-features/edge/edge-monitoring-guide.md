# Edge Monitoring Guide

## Overview

Edge Monitoring provides comprehensive observability for edge node operations, including real-time metrics collection, health monitoring, alerting, and analytics. The system helps identify performance issues, detect anomalies, and maintain edge infrastructure reliability.

## Key Features

- **Real-time Metrics**: Collect and query performance metrics
- **Health Monitoring**: Track edge node health and availability
- **Smart Alerting**: Threshold-based alerts with cooldown periods
- **Analytics**: Trend detection and anomaly identification
- **Recommendations**: Actionable insights for optimization

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  EdgeMonitoringNode                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────┐      ┌──────────────────┐        │
│  │ Metrics Collector│      │ Health Checker   │        │
│  │                 │      │                  │        │
│  │ - Latency       │      │ - Status        │        │
│  │ - Throughput    │─────▶│ - Uptime        │        │
│  │ - Errors        │      │ - Issues        │        │
│  │ - Resources     │      └──────────────────┘        │
│  └─────────────────┘               │                   │
│           │                        │                   │
│           ▼                        ▼                   │
│  ┌─────────────────┐      ┌──────────────────┐        │
│  │ Alert Engine    │      │ Analytics Engine │        │
│  │                 │      │                  │        │
│  │ - Thresholds    │      │ - Trends        │        │
│  │ - Severity      │      │ - Anomalies     │        │
│  │ - Cooldown      │      │ - Baselines     │        │
│  └─────────────────┘      └──────────────────┘        │
└─────────────────────────────────────────────────────────┘
```

## Metric Types

| Metric | Description | Unit | Threshold Guidance |
|--------|-------------|------|-------------------|
| `latency` | Response time | seconds | Warning: 0.5s, Error: 1s, Critical: 2s |
| `throughput` | Requests processed | req/sec | Based on capacity |
| `error_rate` | Failed requests ratio | 0-1 | Warning: 5%, Error: 10%, Critical: 20% |
| `resource_usage` | CPU/Memory utilization | 0-1 | Warning: 70%, Error: 85%, Critical: 95% |
| `availability` | Uptime ratio | 0-1 | Warning: 99%, Error: 95%, Critical: 90% |
| `cache_hit_rate` | Cache effectiveness | 0-1 | Warning: 70%, Error: 50%, Critical: 30% |

## Quick Start

### Basic Monitoring Setup

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = WorkflowBuilder()

# Start monitoring service
workflow.add_node(
    "EdgeMonitoringNode",
    "monitor_starter",
    {
        "operation": "start_monitor",
        "health_check_interval": 30,
        "anomaly_detection": True
    }
)

# Record a metric
workflow.add_node(
    "EdgeMonitoringNode",
    "metric_recorder",
    {
        "operation": "record_metric",
        "edge_node": "edge-west-1",
        "metric_type": "latency",
        "value": 0.250,
        "tags": {"region": "us-west", "service": "api"}
    }
)

# Connect and execute
workflow.add_connection("monitor_starter", "result", "metric_recorder", "input")
runtime = LocalRuntime()
results, run_id = await runtime.execute_async(workflow.build())
```

### Health Monitoring

```python
# Check edge node health
workflow.add_node(
    "EdgeMonitoringNode",
    "health_checker",
    {
        "operation": "get_health",
        "edge_node": "edge-west-1"
    }
)

# Response includes:
# - status: healthy/degraded/unhealthy/unknown
# - uptime_seconds: How long the node has been running
# - metrics_summary: Recent metric values
# - issues: List of current problems
```

### Query Metrics

```python
# Query recent metrics
workflow.add_node(
    "EdgeMonitoringNode",
    "metrics_query",
    {
        "operation": "query_metrics",
        "edge_node": "edge-west-1",
        "metric_type": "latency",
        "time_range_minutes": 60,
        "tags": {"service": "api"}
    }
)
```

## Alert Management

### Setting Custom Thresholds

```python
# Customize alert thresholds
workflow.add_node(
    "EdgeMonitoringNode",
    "threshold_setter",
    {
        "operation": "set_threshold",
        "metric_type": "latency",
        "severity": "warning",
        "threshold_value": 0.3  # 300ms warning threshold
    }
)
```

### Getting Alerts

```python
# Get active alerts
workflow.add_node(
    "EdgeMonitoringNode",
    "alert_getter",
    {
        "operation": "get_alerts",
        "edge_node": "edge-west-1",
        "severity": "error",
        "active_only": True,
        "time_range_minutes": 30
    }
)
```

## Analytics and Insights

### Get Analytics Summary

```python
# Get comprehensive analytics
workflow.add_node(
    "EdgeMonitoringNode",
    "analytics",
    {
        "operation": "get_analytics",
        "edge_node": "edge-west-1"
    }
)

# Returns:
# - metrics_summary: Statistical analysis (mean, p95, p99, etc.)
# - trends: Direction and rate of change
# - anomalies: Detected unusual patterns
# - recommendations: Actionable insights
```

### Monitoring Dashboard

```python
# Get overall monitoring summary
workflow.add_node(
    "EdgeMonitoringNode",
    "summary",
    {
        "operation": "get_summary"
    }
)

# Returns:
# - total_nodes: Number of monitored nodes
# - active_nodes: Currently reporting nodes
# - health_summary: Breakdown by health status
# - recent_alerts: Alert counts by severity
```

## Advanced Usage

### Complete Monitoring Workflow

```python
workflow = WorkflowBuilder()

# 1. Start monitoring
workflow.add_node(
    "EdgeMonitoringNode",
    "monitor",
    {"operation": "start_monitor"}
)

# 2. Simulate edge operations
workflow.add_node(
    "PythonCodeNode",
    "simulator",
    {
        "code": """
import random
metrics = []
for i in range(10):
    latency = 0.1 + random.random() * 0.3
    error_rate = random.random() * 0.05
    cpu_usage = 0.3 + random.random() * 0.4

    metrics.append({
        'latency': latency,
        'error_rate': error_rate,
        'cpu_usage': cpu_usage
    })
result = {'metrics': metrics}
"""
    }
)

# 3. Record metrics
workflow.add_node(
    "EdgeMonitoringNode",
    "recorder",
    {
        "operation": "record_metric",
        "edge_node": "edge-prod-1",
        "metric_type": "latency"
    }
)

# 4. Check health after metrics
workflow.add_node(
    "EdgeMonitoringNode",
    "health",
    {
        "operation": "get_health",
        "edge_node": "edge-prod-1"
    }
)

# 5. Get analytics
workflow.add_node(
    "EdgeMonitoringNode",
    "analytics",
    {
        "operation": "get_analytics",
        "edge_node": "edge-prod-1"
    }
)

# Connect workflow with metric recording loop
workflow.add_connection("monitor", "result", "simulator", "input")
# Use PythonCodeNode to extract latency from metrics array
workflow.add_node("PythonCodeNode", "extract_latency", {
    "code": "result = {'value': data['metrics'][0]['latency'] if data.get('metrics') else 0.0}"
})
workflow.add_connection("simulator", "metrics", "extract_latency", "data")
workflow.add_connection("extract_latency", "result", "recorder", "value")
workflow.add_connection("recorder", "result", "health", "input")
workflow.add_connection("health", "result", "analytics", "input")

# Execute
runtime = LocalRuntime()
results, run_id = await runtime.execute_async(workflow.build())

print(f"Health: {results['health']['health']['status']}")
print(f"Analytics: {results['analytics']['analytics']['recommendations']}")
```

### Integration with Edge Warming

```python
# Monitor-driven edge warming
workflow = WorkflowBuilder()

# Monitor edge performance
workflow.add_node(
    "EdgeMonitoringNode",
    "monitor",
    {
        "operation": "get_analytics",
        "edge_node": "edge-west-1"
    }
)

# Decide on warming based on metrics
workflow.add_node(
    "PythonCodeNode",
    "decision",
    {
        "code": """
analytics = parameters.get('analytics', {})
metrics = analytics.get('metrics_summary', {})

# Check if latency is increasing
should_warm = False
if 'latency' in metrics:
    if metrics['latency']['p95'] > 0.5:  # 500ms p95
        should_warm = True

result = {'should_warm': should_warm}
"""
    }
)

# Warm edge if needed
workflow.add_node(
    "EdgeWarmingNode",
    "warmer",
    {
        "operation": "warm_nodes",
        "nodes_to_warm": ["edge-west-2", "edge-west-3"]
    }
)

# Connect with conditional execution
workflow.add_connection("monitor", "analytics", "decision", "analytics")
# Use conditional node to check if warming is needed
workflow.add_node("SwitchNode", "warm_check", {
    "condition_field": "should_warm",
    "operator": "==",
    "value": True
})
workflow.add_connection("decision", "output", "warm_check", "input_data")
workflow.add_connection("warm_check", "result", "warmer", "input")
```

## Best Practices

### 1. Metric Recording
- Include relevant tags for filtering
- Use consistent metric names
- Record metrics at regular intervals
- Batch recordings when possible

### 2. Alert Configuration
- Set realistic thresholds based on SLAs
- Use cooldown periods to prevent alert fatigue
- Start with higher thresholds and tune down
- Different thresholds for different edge locations

### 3. Health Monitoring
- Run health checks at appropriate intervals
- Monitor all critical edge nodes
- Set up automated responses to health issues
- Track uptime for SLA compliance

### 4. Analytics Usage
- Review trends regularly
- Act on anomaly detections
- Follow recommendations
- Establish baselines during normal operation

## Troubleshooting

### Missing Metrics
- Verify edge nodes are recording metrics
- Check retention period settings
- Ensure monitoring service is started

### False Alerts
- Review and adjust thresholds
- Increase alert cooldown period
- Check for temporary spikes vs sustained issues

### Performance Impact
- Reduce health check frequency if needed
- Limit retention period for high-volume metrics
- Use sampling for extremely high-frequency metrics

## Configuration Reference

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `retention_period` | int | 86400 (24h) | How long to keep metrics |
| `alert_cooldown` | int | 300 (5m) | Minimum time between alerts |
| `health_check_interval` | int | 30 | Seconds between health checks |
| `anomaly_detection` | bool | True | Enable anomaly detection |

## Metrics Interpretation

### Latency Patterns
- **Stable**: Consistent response times
- **Increasing**: Possible resource constraints
- **Spiky**: Intermittent issues or batch processing
- **High baseline**: Need optimization or scaling

### Error Rate Patterns
- **Zero/Low**: System healthy
- **Sudden spike**: Deployment or external issue
- **Gradual increase**: Degrading component
- **Periodic**: Scheduled job failures

### Resource Usage Patterns
- **Low (<50%)**: Room for more load
- **Moderate (50-70%)**: Healthy utilization
- **High (70-85%)**: Monitor closely
- **Critical (>85%)**: Scale or optimize

## Integration Examples

### With Load Balancing
```python
# Route traffic based on health
healthy_edges = []
for edge in edges:
    health = await monitor.get_health(edge)
    if health.status == "healthy":
        healthy_edges.append(edge)
```

### With Auto-scaling
```python
# Scale based on metrics
analytics = await monitor.get_analytics(edge)
if analytics['metrics_summary']['resource_usage']['p95'] > 0.8:
    # Trigger scaling
    scale_edge(edge)
```

### With Incident Management
```python
# Create incidents from critical alerts
alerts = await monitor.get_alerts(severity="critical")
for alert in alerts:
    create_incident(alert)
```

## Future Enhancements

- Machine learning for anomaly detection
- Predictive alerting
- Custom metric types
- Distributed tracing integration
- Metric aggregation across regions
- SLA tracking and reporting
