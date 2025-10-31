# Monitoring & Alerting Quick Guide

## TL;DR - Copy & Paste

### Basic Setup (2 minutes)

```python
from kailash.monitoring.metrics import get_validation_metrics
from kailash.monitoring.alerts import AlertManager, AlertRule, AlertSeverity, LogNotificationChannel
from kailash.runtime.local import LocalRuntime

# 1. Enable monitoring
runtime = LocalRuntime(connection_validation="strict")
validation_metrics = get_validation_metrics()

# 2. Create alert manager
alert_manager = AlertManager(validation_metrics.registry)

# 3. Add basic alert rule
alert_manager.add_rule(AlertRule(
    name="validation_failures",
    description="Too many validation failures",
    severity=AlertSeverity.ERROR,
    metric_name="validation_failure",
    condition="> 5",
    threshold=5
))

# 4. Add notification
alert_manager.add_notification_channel(LogNotificationChannel())

# 5. Start monitoring
alert_manager.start()

# 6. Use normally
results, run_id = runtime.execute(workflow.build())

# 7. Check metrics
print(f"Success rate: {validation_metrics.get_success_rate():.2%}")

# 8. Stop when done
alert_manager.stop()
```

### Production Setup (5 minutes)

```python
from kailash.monitoring.metrics import get_validation_metrics, get_security_metrics
from kailash.monitoring.alerts import (
    AlertManager, AlertRule, AlertSeverity,
    LogNotificationChannel, SlackNotificationChannel
)

# Production monitoring
validation_metrics = get_validation_metrics()
security_metrics = get_security_metrics()
alert_manager = AlertManager(validation_metrics.registry)

# Production alert rules
production_rules = [
    AlertRule(
        name="high_validation_failures",
        description="Validation failure rate above 10%",
        severity=AlertSeverity.ERROR,
        metric_name="validation_failure",
        condition="> 10",
        threshold=10
    ),
    AlertRule(
        name="security_violations",
        description="Security violations detected",
        severity=AlertSeverity.CRITICAL,
        metric_name="security_violations_total",
        condition="> 0",
        threshold=0
    ),
    AlertRule(
        name="slow_operations",
        description="Operations taking too long",
        severity=AlertSeverity.WARNING,
        metric_name="response_time",
        condition="avg > 1000",
        threshold=1000
    )
]

for rule in production_rules:
    alert_manager.add_rule(rule)

# Multiple notification channels
alert_manager.add_notification_channel(LogNotificationChannel("ERROR"))
# alert_manager.add_notification_channel(SlackNotificationChannel("YOUR_WEBHOOK_URL"))

alert_manager.start()

# Production usage
runtime = LocalRuntime(connection_validation="strict")
results, run_id = runtime.execute(workflow.build())

# Monitor key metrics
print(f"Validation success: {validation_metrics.get_success_rate():.2%}")
print(f"Cache efficiency: {validation_metrics.get_cache_hit_rate():.2%}")
print(f"Security violations: {security_metrics.get_critical_violations()}")

alert_manager.stop()
```

## Core Concepts

### 1. Metrics Types

```python
from kailash.monitoring.metrics import MetricType

# Counter - Always increasing (errors, requests)
MetricType.COUNTER

# Gauge - Current value (memory usage, active users)
MetricType.GAUGE

# Timer - Duration measurements (response time)
MetricType.TIMER

# Histogram - Value distributions (request sizes)
MetricType.HISTOGRAM
```

### 2. Alert Severities

```python
from kailash.monitoring.alerts import AlertSeverity

AlertSeverity.INFO      # Informational
AlertSeverity.WARNING   # Warning condition
AlertSeverity.ERROR     # Error condition
AlertSeverity.CRITICAL  # Critical issue
```

### 3. Built-in Metrics

```python
from kailash.monitoring.metrics import (
    get_validation_metrics,    # Validation success/failure rates
    get_security_metrics,      # Security violations, blocked connections
    get_performance_metrics    # Response times, memory, CPU
)

# Validation metrics
validation = get_validation_metrics()
validation.get_success_rate()     # Success percentage
validation.get_cache_hit_rate()   # Cache efficiency

# Security metrics
security = get_security_metrics()
security.get_violation_rate()     # Violations per minute
security.get_critical_violations() # Critical violation count

# Performance metrics
performance = get_performance_metrics()
performance.get_p95_response_time() # 95th percentile response time
```

## Alert Conditions

### Common Patterns

```python
# Greater than threshold
condition="> 10"        # More than 10 failures
condition="> 0.05"      # More than 5% error rate

# Less than threshold
condition="< 0.8"       # Cache hit rate below 80%
condition="< 1000"      # Revenue below $1000/min

# Equals
condition="== 0"        # No successful operations
condition="== 500"      # HTTP 500 errors

# Rate-based (per minute)
condition="rate > 0.1"  # More than 0.1 violations/min

# Average over time window
condition="avg > 1000"  # Average response time > 1 second

# Maximum in time window
condition="max > 2000"  # Peak response time > 2 seconds
```

### Time Windows

```python
from datetime import timedelta

AlertRule(
    name="high_error_rate",
    # ... other params ...
    time_window=timedelta(minutes=5),           # Look at last 5 minutes
    evaluation_interval=timedelta(minutes=1),   # Check every minute
    notification_interval=timedelta(minutes=15) # Alert every 15 minutes max
)
```

## Notification Channels

### 1. Log Notifications

```python
from kailash.monitoring.alerts import LogNotificationChannel

# Basic logging
log_channel = LogNotificationChannel()

# Custom log level
log_channel = LogNotificationChannel("ERROR")  # INFO, WARNING, ERROR, CRITICAL
```

### 2. Slack Notifications

```python
from kailash.monitoring.alerts import SlackNotificationChannel

slack_channel = SlackNotificationChannel(
    webhook_url="https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
    channel="#alerts"  # Optional, defaults to webhook channel
)
```

### 3. Email Notifications

```python
from kailash.monitoring.alerts import EmailNotificationChannel

email_channel = EmailNotificationChannel(
    smtp_host="smtp.gmail.com",
    smtp_port=587,
    username="alerts@company.com",
    password="app_password",
    from_email="kailash-alerts@company.com",
    to_emails=["dev@company.com", "ops@company.com"],
    use_tls=True
)
```

### 4. Webhook Notifications

```python
from kailash.monitoring.alerts import WebhookNotificationChannel

webhook_channel = WebhookNotificationChannel(
    webhook_url="https://api.company.com/alerts",
    headers={"Authorization": "Bearer YOUR_TOKEN"}
)
```

## Common Use Cases

### 1. Workflow Health Monitoring

```python
# Monitor workflow execution health
workflow_rules = [
    AlertRule(
        name="workflow_failures",
        description="Workflows failing frequently",
        severity=AlertSeverity.ERROR,
        metric_name="validation_failure",
        condition="> 5",
        threshold=5,
        time_window=timedelta(minutes=10)
    ),
    AlertRule(
        name="slow_workflows",
        description="Workflows running slowly",
        severity=AlertSeverity.WARNING,
        metric_name="response_time",
        condition="avg > 30000",  # 30 seconds
        threshold=30000
    )
]
```

### 2. Security Monitoring

```python
# Monitor for security issues
security_rules = [
    AlertRule(
        name="sql_injection_detected",
        description="SQL injection attempts",
        severity=AlertSeverity.CRITICAL,
        metric_name="sql_injection_attempts",
        condition="> 0",
        threshold=0,
        notification_interval=timedelta(minutes=1)  # Immediate alerts
    ),
    AlertRule(
        name="blocked_connections",
        description="Many blocked connections",
        severity=AlertSeverity.WARNING,
        metric_name="blocked_connections",
        condition="> 20",
        threshold=20,
        time_window=timedelta(minutes=5)
    )
]
```

### 3. Performance Monitoring

```python
# Monitor system performance
performance_rules = [
    AlertRule(
        name="high_memory_usage",
        description="Memory usage critical",
        severity=AlertSeverity.ERROR,
        metric_name="memory_usage",
        condition="> 90",
        threshold=90  # 90% memory usage
    ),
    AlertRule(
        name="high_cpu_usage",
        description="CPU usage high",
        severity=AlertSeverity.WARNING,
        metric_name="cpu_usage",
        condition="> 80",
        threshold=80  # 80% CPU usage
    ),
    AlertRule(
        name="low_throughput",
        description="Throughput below target",
        severity=AlertSeverity.WARNING,
        metric_name="throughput",
        condition="< 100",
        threshold=100  # Less than 100 requests/second
    )
]
```

## Metrics Export

### 1. JSON Export

```python
from kailash.monitoring.metrics import get_metrics_registry
import json

registry = get_metrics_registry()

# Export all metrics as JSON
json_data = registry.export_metrics("json")
metrics = json.loads(json_data)

# Access specific metrics
validation_data = metrics["validation"]
total_validations = validation_data["validation_total"]["latest_value"]
success_rate = validation_data["validation_success"]["latest_value"] / total_validations
```

### 2. Prometheus Export

```python
# Export for Prometheus/Grafana
prometheus_data = registry.export_metrics("prometheus")
print(prometheus_data)

# Output format:
# # HELP kailash_validation_validation_total Total validation attempts
# # TYPE kailash_validation_validation_total counter
# kailash_validation_validation_total{node_type="PythonCodeNode"} 142
```

### 3. Custom Dashboard Integration

```python
def get_dashboard_metrics():
    """Get metrics for custom dashboard."""
    validation = get_validation_metrics()
    security = get_security_metrics()
    performance = get_performance_metrics()

    return {
        "validation": {
            "success_rate": validation.get_success_rate(),
            "cache_hit_rate": validation.get_cache_hit_rate(),
            "total_attempts": validation.get_metric("validation_total").get_latest_value()
        },
        "security": {
            "violations_24h": security.get_critical_violations(timedelta(hours=24)),
            "violation_rate": security.get_violation_rate(timedelta(hours=1)),
            "blocked_connections": security.get_metric("blocked_connections").get_latest_value()
        },
        "performance": {
            "avg_response_time": performance.get_metric("response_time").get_average(),
            "p95_response_time": performance.get_p95_response_time(),
            "memory_usage": performance.get_metric("memory_usage").get_latest_value(),
            "cpu_usage": performance.get_metric("cpu_usage").get_latest_value()
        }
    }

# Use in web endpoint
dashboard_data = get_dashboard_metrics()
```

## Alert Management

### 1. View Active Alerts

```python
# Get currently firing alerts
active_alerts = alert_manager.get_active_alerts()
for alert in active_alerts:
    print(f"🚨 {alert.title}")
    print(f"   Severity: {alert.severity.value}")
    print(f"   Status: {alert.status.value}")
    print(f"   Fired: {alert.fired_at}")
    print(f"   Notifications: {alert.notification_count}")
```

### 2. Silence Alerts

```python
# Silence specific alert
alert_manager.silence_alert("high_validation_failures_validation")

# Acknowledge alert (same as silence)
alert_manager.acknowledge_alert("security_violations_security")
```

### 3. Alert History

```python
# Get all alerts (including resolved)
all_alerts = alert_manager.get_all_alerts()

# Filter by time period
recent_alerts = [
    alert for alert in all_alerts
    if alert.created_at > datetime.now(UTC) - timedelta(hours=24)
]

# Filter by severity
critical_alerts = [
    alert for alert in all_alerts
    if alert.severity == AlertSeverity.CRITICAL
]
```

## Custom Metrics

### 1. Create Custom Collector

```python
from kailash.monitoring.metrics import MetricsCollector, MetricType

# Custom business metrics
business_collector = MetricsCollector(max_series=50)

# Define custom metrics
business_collector.create_metric(
    "revenue_per_minute",
    MetricType.GAUGE,
    "Revenue generated per minute",
    "USD"
)

business_collector.create_metric(
    "active_users",
    MetricType.GAUGE,
    "Number of active users"
)

business_collector.create_metric(
    "orders_processed",
    MetricType.COUNTER,
    "Total orders processed"
)

# Record metrics
business_collector.set_gauge("revenue_per_minute", 1250.50)
business_collector.set_gauge("active_users", 42)
business_collector.increment("orders_processed", 1)

# Register with global registry
registry = get_metrics_registry()
registry.register_collector("business", business_collector)
```

### 2. Custom Alert Rules

```python
# Alert on custom business metrics
business_rule = AlertRule(
    name="low_revenue",
    description="Revenue below target",
    severity=AlertSeverity.WARNING,
    metric_name="revenue_per_minute",
    condition="< 1000",
    threshold=1000,
    time_window=timedelta(minutes=15),
    labels={"team": "business", "department": "sales"},
    annotations={"runbook": "https://wiki.company.com/low-revenue-runbook"}
)

alert_manager.add_rule(business_rule)
```

## Production Best Practices

### 1. Proper Lifecycle Management

```python
import atexit
import logging

logger = logging.getLogger(__name__)

def setup_production_monitoring():
    """Production monitoring setup with proper lifecycle."""
    try:
        # Initialize
        alert_manager = AlertManager(get_metrics_registry())

        # Add rules
        from kailash.monitoring.alerts import create_default_alert_rules
        for rule in create_default_alert_rules():
            alert_manager.add_rule(rule)

        # Add notifications with fallback
        alert_manager.add_notification_channel(LogNotificationChannel())

        # Start monitoring
        alert_manager.start()
        logger.info("Monitoring started")

        # Cleanup on exit
        def cleanup():
            try:
                alert_manager.stop()
                logger.info("Monitoring stopped")
            except Exception as e:
                logger.error(f"Error stopping monitoring: {e}")

        atexit.register(cleanup)
        return alert_manager

    except Exception as e:
        logger.error(f"Failed to setup monitoring: {e}")
        return None

# Use in your application
alert_manager = setup_production_monitoring()
```

### 2. Health Check Integration

```python
def system_health():
    """System health check for load balancers."""
    validation = get_validation_metrics()
    security = get_security_metrics()

    # Check validation health (last 5 minutes)
    success_rate = validation.get_success_rate(timedelta(minutes=5))
    if success_rate < 0.9:
        return {"healthy": False, "reason": f"Low success rate: {success_rate:.1%}"}

    # Check security health
    violations = security.get_critical_violations(timedelta(minutes=5))
    if violations > 0:
        return {"healthy": False, "reason": f"Security violations: {violations}"}

    return {"healthy": True, "success_rate": f"{success_rate:.1%}"}

# Example usage
health = system_health()
if not health["healthy"]:
    print(f"⚠️  System unhealthy: {health['reason']}")
else:
    print(f"✅ System healthy: {health['success_rate']} success rate")
```

### 3. Error Handling

```python
def safe_monitoring_operation(func):
    """Decorator for safe monitoring operations."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Monitoring operation failed: {e}")
            return None
    return wrapper

@safe_monitoring_operation
def get_metrics_safely():
    """Safely get metrics without breaking application."""
    validation = get_validation_metrics()
    return {
        "success_rate": validation.get_success_rate(),
        "cache_hit_rate": validation.get_cache_hit_rate()
    }

# Application won't crash if monitoring fails
metrics = get_metrics_safely()
if metrics:
    print(f"Success rate: {metrics['success_rate']:.2%}")
else:
    print("Metrics unavailable")
```

## Troubleshooting

### Common Issues

1. **No Metrics Showing**
   ```python
   # Check if metrics are being recorded
   registry = get_metrics_registry()
   collectors = registry.get_all_collectors()
   print(f"Registered collectors: {list(collectors.keys())}")

   validation = get_validation_metrics()
   total = validation.get_metric("validation_total")
   print(f"Total validations: {total.get_latest_value() if total else 'None'}")
   ```

2. **Alerts Not Firing**
   ```python
   # Check alert rules
   for rule_name, rule in alert_manager.rules.items():
       print(f"Rule: {rule_name}, Enabled: {rule.enabled}")

   # Check metric values vs thresholds
   metric = validation.get_metric("validation_failure")
   if metric:
       latest = metric.get_latest_value()
       print(f"Current failures: {latest}")
   ```

3. **Notifications Not Sending**
   ```python
   # Test notification channels
   test_alert = Alert("test", "test", AlertSeverity.INFO, "Test", "Test alert")

   for channel in alert_manager.notification_channels:
       result = channel.send_notification(test_alert, {})
       print(f"{type(channel).__name__}: {'✅' if result else '❌'}")
   ```

### Performance Tips

1. **Limit Metric Series**
   ```python
   # Prevent memory issues
   collector = MetricsCollector(max_series=100)  # Lower for high-traffic
   ```

2. **Adjust Alert Intervals**
   ```python
   # Reduce evaluation frequency for less critical alerts
   AlertRule(
       # ... other params ...
       evaluation_interval=timedelta(minutes=5),  # Check every 5 min instead of 1
       notification_interval=timedelta(hours=1)   # Alert max once per hour
   )
   ```

3. **Use Appropriate Time Windows**
   ```python
   # Shorter windows for critical alerts
   AlertRule(
       name="critical_failures",
       time_window=timedelta(minutes=1),  # Very responsive
       # ...
   )

   # Longer windows for trend analysis
   AlertRule(
       name="degrading_performance",
       time_window=timedelta(hours=1),   # Look at trends
       # ...
   )
   ```

This monitoring system provides enterprise-grade observability with minimal setup while being flexible enough for complex production deployments.
