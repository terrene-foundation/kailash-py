# Monitoring & Alerting Patterns

## Overview

Kailash SDK v0.8.4+ provides enterprise-grade monitoring and alerting capabilities for comprehensive observability of workflow execution, validation metrics, security events, and performance optimization.

## Core Components

### 1. Metrics Collection

```python
from kailash.monitoring.metrics import (
    get_validation_metrics,
    get_security_metrics,
    get_performance_metrics,
    get_metrics_registry
)

# Global metrics collectors
validation_metrics = get_validation_metrics()
security_metrics = get_security_metrics()
performance_metrics = get_performance_metrics()
registry = get_metrics_registry()
```

### 2. Alert Management

```python
from kailash.monitoring.alerts import (
    AlertManager, AlertRule, AlertSeverity,
    LogNotificationChannel, SlackNotificationChannel,
    EmailNotificationChannel, WebhookNotificationChannel
)

# Create alert manager
alert_manager = AlertManager(registry)

# Configure rules and channels
alert_manager.add_rule(AlertRule(...))
alert_manager.add_notification_channel(LogNotificationChannel())
```

## Basic Monitoring Setup

### Simple Monitoring

```python
from kailash.monitoring.metrics import get_validation_metrics
from kailash.monitoring.alerts import AlertManager, AlertRule, AlertSeverity
from kailash.runtime.local import LocalRuntime

# Enable monitoring
runtime = LocalRuntime(connection_validation="strict")
validation_metrics = get_validation_metrics()

# Basic alert rule
alert_manager = AlertManager(validation_metrics.registry)
alert_manager.add_rule(AlertRule(
    name="validation_failures",
    description="High validation failure rate",
    severity=AlertSeverity.WARNING,
    metric_name="validation_failure",
    condition="> 5",
    threshold=5
))

# Start monitoring
alert_manager.start()

# Execute workflow with monitoring
results, run_id = runtime.execute(workflow.build())

# View metrics
print(f"Success rate: {validation_metrics.get_success_rate():.2%}")
print(f"Cache hit rate: {validation_metrics.get_cache_hit_rate():.2%}")

alert_manager.stop()
```

## Advanced Monitoring Patterns

### 1. Multi-Channel Alerting

```python
from kailash.monitoring.alerts import (
    LogNotificationChannel, SlackNotificationChannel,
    EmailNotificationChannel, WebhookNotificationChannel
)

alert_manager = AlertManager(registry)

# Multiple notification channels
alert_manager.add_notification_channel(LogNotificationChannel("ERROR"))

# Slack notifications (requires webhook URL)
slack_channel = SlackNotificationChannel(
    webhook_url="https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
    channel="#alerts"
)
alert_manager.add_notification_channel(slack_channel)

# Email notifications
email_channel = EmailNotificationChannel(
    smtp_host="smtp.company.com",
    smtp_port=587,
    username="alerts@company.com",
    password="secure_password",
    from_email="kailash-alerts@company.com",
    to_emails=["devops@company.com", "security@company.com"],
    use_tls=True
)
alert_manager.add_notification_channel(email_channel)

# Webhook for external systems
webhook_channel = WebhookNotificationChannel(
    webhook_url="https://api.company.com/alerts",
    headers={"Authorization": "Bearer YOUR_API_TOKEN"}
)
alert_manager.add_notification_channel(webhook_channel)
```

### 2. Comprehensive Security Monitoring

```python
from kailash.monitoring.metrics import get_security_metrics, MetricSeverity
from kailash.monitoring.alerts import AlertRule, AlertSeverity
from datetime import timedelta

security_metrics = get_security_metrics()
alert_manager = AlertManager(security_metrics.registry)

# Security violation alerts
security_rules = [
    AlertRule(
        name="critical_security_violations",
        description="Critical security violations detected",
        severity=AlertSeverity.CRITICAL,
        metric_name="security_violations_total",
        condition="> 0",
        threshold=0,
        time_window=timedelta(minutes=1),
        notification_interval=timedelta(minutes=5)
    ),
    AlertRule(
        name="sql_injection_attempts",
        description="SQL injection attempts detected",
        severity=AlertSeverity.ERROR,
        metric_name="sql_injection_attempts",
        condition="> 0",
        threshold=0,
        time_window=timedelta(minutes=5)
    ),
    AlertRule(
        name="high_blocked_connections",
        description="High number of blocked connections",
        severity=AlertSeverity.WARNING,
        metric_name="blocked_connections",
        condition="> 10",
        threshold=10,
        time_window=timedelta(minutes=10)
    )
]

for rule in security_rules:
    alert_manager.add_rule(rule)

# Record security events
security_metrics.record_security_violation(
    "sql_injection",
    MetricSeverity.CRITICAL,
    "DatabaseNode",
    {"query": "'; DROP TABLE users; --"}
)

security_metrics.record_blocked_connection(
    "untrusted_source",
    "database",
    "SQL injection detected"
)

# Monitor security metrics
violation_rate = security_metrics.get_violation_rate(timedelta(hours=1))
critical_violations = security_metrics.get_critical_violations(timedelta(hours=24))

print(f"Violation rate: {violation_rate:.2f} per minute")
print(f"Critical violations (24h): {critical_violations}")
```

### 3. Performance Monitoring

```python
from kailash.monitoring.metrics import get_performance_metrics
from kailash.monitoring.alerts import AlertRule, AlertSeverity
from datetime import timedelta

performance_metrics = get_performance_metrics()
alert_manager = AlertManager(performance_metrics.registry)

# Performance alert rules
performance_rules = [
    AlertRule(
        name="high_response_time",
        description="Average response time above 1 second",
        severity=AlertSeverity.WARNING,
        metric_name="response_time",
        condition="avg > 1000",
        threshold=1000,
        time_window=timedelta(minutes=5)
    ),
    AlertRule(
        name="high_memory_usage",
        description="Memory usage above 90%",
        severity=AlertSeverity.ERROR,
        metric_name="memory_usage",
        condition="> 90",
        threshold=90
    ),
    AlertRule(
        name="high_error_rate",
        description="Error rate above 5%",
        severity=AlertSeverity.ERROR,
        metric_name="error_rate",
        condition="> 5",
        threshold=5
    )
]

for rule in performance_rules:
    alert_manager.add_rule(rule)

# Record performance metrics
performance_metrics.record_operation("validation", 125.5, success=True)
performance_metrics.record_operation("database_query", 1500.0, success=False)  # Slow
performance_metrics.update_system_metrics(memory_mb=512.0, cpu_percent=75.0, rps=150.0)

# Performance analytics
p95_response_time = performance_metrics.get_p95_response_time(timedelta(hours=1))
print(f"95th percentile response time: {p95_response_time:.2f}ms")
```

## Metrics Export & Integration

### 1. JSON Export

```python
from kailash.monitoring.metrics import get_metrics_registry

registry = get_metrics_registry()

# Export all metrics as JSON
json_metrics = registry.export_metrics("json")
print(json_metrics)

# Parse JSON for external systems
import json
metrics_data = json.loads(json_metrics)
for collector_name, collector_data in metrics_data.items():
    print(f"Collector: {collector_name}")
    for metric_name, metric_data in collector_data.items():
        latest_value = metric_data.get("latest_value")
        print(f"  {metric_name}: {latest_value}")
```

### 2. Prometheus Export

```python
# Export in Prometheus format
prometheus_metrics = registry.export_metrics("prometheus")
print(prometheus_metrics)

# Example output:
# # HELP kailash_validation_validation_total Total validation attempts
# # TYPE kailash_validation_validation_total counter
# kailash_validation_validation_total{node_type="PythonCodeNode"} 42
```

### 3. Custom Metrics Collection

```python
from kailash.monitoring.metrics import MetricsCollector, MetricType

# Create custom collector
custom_collector = MetricsCollector(max_series=100)

# Custom metrics
custom_collector.create_metric(
    "workflow_execution_time",
    MetricType.TIMER,
    "Time taken to execute workflows",
    "milliseconds"
)

custom_collector.create_metric(
    "active_users",
    MetricType.GAUGE,
    "Number of active users"
)

# Record custom metrics
custom_collector.record_timer("workflow_execution_time", 2500.0, {"workflow_type": "etl"})
custom_collector.set_gauge("active_users", 42)

# Register with global registry
registry.register_collector("custom", custom_collector)
```

## Production Deployment Patterns

### 1. Centralized Monitoring

```python
from kailash.monitoring.alerts import create_default_alert_rules
import logging

# Configure logging for alerts
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/kailash/alerts.log'),
        logging.StreamHandler()
    ]
)

# Set up comprehensive monitoring
alert_manager = AlertManager(registry)

# Use default alert rules as starting point
default_rules = create_default_alert_rules()
for rule in default_rules:
    alert_manager.add_rule(rule)

# Production notification channels
alert_manager.add_notification_channel(LogNotificationChannel("ERROR"))
alert_manager.add_notification_channel(slack_channel)  # For immediate alerts
alert_manager.add_notification_channel(email_channel)  # For escalation

# Start monitoring in background
alert_manager.start()
```

### 2. Health Check Integration

```python
from kailash.monitoring.metrics import get_validation_metrics, get_security_metrics
from datetime import timedelta

def health_check():
    """Health check endpoint for load balancers."""
    validation_metrics = get_validation_metrics()
    security_metrics = get_security_metrics()

    # Check validation health
    success_rate = validation_metrics.get_success_rate(timedelta(minutes=5))
    if success_rate < 0.9:  # Less than 90% success
        return {"status": "unhealthy", "reason": "High validation failure rate"}

    # Check security health
    critical_violations = security_metrics.get_critical_violations(timedelta(minutes=5))
    if critical_violations > 0:
        return {"status": "unhealthy", "reason": "Critical security violations"}

    return {"status": "healthy"}

# Example Flask integration
from flask import Flask, jsonify
app = Flask(__name__)

@app.route("/health")
def health():
    return jsonify(health_check())
```

### 3. Metrics Dashboard Integration

```python
from kailash.monitoring.metrics import get_metrics_registry
import time

def metrics_collector_daemon():
    """Background daemon to collect metrics for dashboard."""
    registry = get_metrics_registry()

    while True:
        # Export metrics for dashboard
        metrics_json = registry.export_metrics("json")

        # Send to dashboard system (e.g., Grafana, custom dashboard)
        # send_to_dashboard(metrics_json)

        # Wait before next collection
        time.sleep(30)  # Collect every 30 seconds

# Start as background thread
import threading
collector_thread = threading.Thread(target=metrics_collector_daemon, daemon=True)
collector_thread.start()
```

## Alert Management

### 1. Alert Lifecycle

```python
# Get active alerts
active_alerts = alert_manager.get_active_alerts()
for alert in active_alerts:
    print(f"Alert: {alert.title} - {alert.severity.value}")
    print(f"Status: {alert.status.value}")
    print(f"Fired at: {alert.fired_at}")

# Silence alerts
alert_manager.silence_alert("high_validation_failures_validation")

# Acknowledge alerts
alert_manager.acknowledge_alert("security_violations_security")

# Get all alerts (including resolved)
all_alerts = alert_manager.get_all_alerts()
```

### 2. Custom Alert Rules

```python
from datetime import timedelta

# Custom alert rule with complex condition
custom_rule = AlertRule(
    name="custom_business_metric",
    description="Business KPI threshold exceeded",
    severity=AlertSeverity.WARNING,
    metric_name="revenue_per_minute",
    condition="< 1000",
    threshold=1000,
    time_window=timedelta(minutes=15),
    evaluation_interval=timedelta(minutes=5),
    notification_interval=timedelta(minutes=30),
    labels={"team": "business", "priority": "high"},
    annotations={"runbook": "https://wiki.company.com/revenue-alerts"}
)

alert_manager.add_rule(custom_rule)
```

## Best Practices

### 1. Monitoring Configuration

```python
# Production monitoring configuration
monitoring_config = {
    "validation": {
        "success_rate_threshold": 0.95,
        "cache_hit_rate_threshold": 0.8,
        "max_response_time_ms": 1000
    },
    "security": {
        "max_violations_per_hour": 0,
        "blocked_connections_threshold": 10,
        "critical_alert_interval_minutes": 5
    },
    "performance": {
        "max_memory_usage_percent": 85,
        "max_cpu_usage_percent": 80,
        "p95_response_time_ms": 500
    }
}

# Apply configuration to alert rules
def create_production_alert_rules(config):
    rules = []

    # Validation rules
    val_config = config["validation"]
    rules.append(AlertRule(
        name="low_success_rate",
        description=f"Success rate below {val_config['success_rate_threshold']:.0%}",
        severity=AlertSeverity.ERROR,
        metric_name="validation_success",
        condition=f"rate < {val_config['success_rate_threshold']}",
        threshold=val_config['success_rate_threshold']
    ))

    # Security rules
    sec_config = config["security"]
    rules.append(AlertRule(
        name="security_violations",
        description="Security violations detected",
        severity=AlertSeverity.CRITICAL,
        metric_name="security_violations_total",
        condition=f"> {sec_config['max_violations_per_hour']}",
        threshold=sec_config['max_violations_per_hour'],
        notification_interval=timedelta(minutes=sec_config['critical_alert_interval_minutes'])
    ))

    return rules

production_rules = create_production_alert_rules(monitoring_config)
for rule in production_rules:
    alert_manager.add_rule(rule)
```

### 2. Error Handling

```python
import logging

logger = logging.getLogger(__name__)

def safe_monitoring_setup():
    """Set up monitoring with error handling."""
    try:
        # Initialize monitoring
        registry = get_metrics_registry()
        alert_manager = AlertManager(registry)

        # Add rules with error handling
        try:
            rules = create_default_alert_rules()
            for rule in rules:
                alert_manager.add_rule(rule)
        except Exception as e:
            logger.error(f"Failed to add alert rule: {e}")

        # Add notification channels with fallback
        try:
            alert_manager.add_notification_channel(LogNotificationChannel())
        except Exception as e:
            logger.error(f"Failed to add notification channel: {e}")

        # Start monitoring
        alert_manager.start()
        return alert_manager

    except Exception as e:
        logger.error(f"Failed to initialize monitoring: {e}")
        return None

# Use in production
alert_manager = safe_monitoring_setup()
if alert_manager:
    logger.info("Monitoring initialized successfully")
else:
    logger.warning("Running without monitoring")
```

### 3. Resource Management

```python
import atexit

def setup_monitoring_lifecycle():
    """Proper lifecycle management for monitoring."""
    alert_manager = AlertManager(registry)

    # Configure monitoring
    # ... (configuration code)

    # Start monitoring
    alert_manager.start()

    # Ensure cleanup on exit
    def cleanup():
        try:
            alert_manager.stop()
            logger.info("Monitoring stopped gracefully")
        except Exception as e:
            logger.error(f"Error stopping monitoring: {e}")

    atexit.register(cleanup)

    return alert_manager

# Use for long-running applications
alert_manager = setup_monitoring_lifecycle()
```

## Integration Examples

### 1. FastAPI Integration

```python
from fastapi import FastAPI
from kailash.monitoring.metrics import get_metrics_registry

app = FastAPI()
registry = get_metrics_registry()

@app.get("/metrics")
def get_metrics():
    """Prometheus metrics endpoint."""
    return Response(
        content=registry.export_metrics("prometheus"),
        media_type="text/plain"
    )

@app.get("/metrics/json")
def get_metrics_json():
    """JSON metrics endpoint."""
    return registry.export_metrics("json")

@app.get("/health")
def health_check():
    """Health check with metrics."""
    validation_metrics = get_validation_metrics()
    success_rate = validation_metrics.get_success_rate()

    if success_rate < 0.9:
        return {"status": "unhealthy", "success_rate": success_rate}

    return {"status": "healthy", "success_rate": success_rate}
```

### 2. Django Integration

```python
# settings.py
KAILASH_MONITORING = {
    'ENABLED': True,
    'ALERT_RULES': [
        {
            'name': 'high_validation_failures',
            'threshold': 5,
            'severity': 'ERROR'
        }
    ],
    'NOTIFICATION_CHANNELS': [
        {
            'type': 'log',
            'level': 'ERROR'
        },
        {
            'type': 'slack',
            'webhook_url': os.environ.get('SLACK_WEBHOOK_URL')
        }
    ]
}

# monitoring.py
from django.conf import settings
from kailash.monitoring.alerts import AlertManager, AlertRule, AlertSeverity

def setup_django_monitoring():
    if not settings.KAILASH_MONITORING.get('ENABLED'):
        return None

    alert_manager = AlertManager(get_metrics_registry())

    # Configure from Django settings
    for rule_config in settings.KAILASH_MONITORING['ALERT_RULES']:
        rule = AlertRule(
            name=rule_config['name'],
            description=f"Alert for {rule_config['name']}",
            severity=getattr(AlertSeverity, rule_config['severity']),
            metric_name="validation_failure",
            condition=f"> {rule_config['threshold']}",
            threshold=rule_config['threshold']
        )
        alert_manager.add_rule(rule)

    alert_manager.start()
    return alert_manager

# apps.py
from django.apps import AppConfig

class MyAppConfig(AppConfig):
    def ready(self):
        from .monitoring import setup_django_monitoring
        setup_django_monitoring()
```

## Troubleshooting

### Common Issues

1. **Alert Manager Not Starting**
   ```python
   # Check for port conflicts or permission issues
   try:
       alert_manager.start()
   except Exception as e:
       logger.error(f"Failed to start alert manager: {e}")
   ```

2. **Missing Metrics**
   ```python
   # Verify metric registration
   registry = get_metrics_registry()
   collectors = registry.get_all_collectors()
   print(f"Registered collectors: {list(collectors.keys())}")
   ```

3. **Notification Failures**
   ```python
   # Test notification channels individually
   channel = LogNotificationChannel()
   test_alert = Alert("test", "test_rule", AlertSeverity.INFO, "Test", "Test alert")
   result = channel.send_notification(test_alert, {})
   print(f"Notification result: {result}")
   ```

### Performance Tuning

```python
# Optimize metrics collection
optimized_registry = MetricsRegistry()

# Limit metric series to prevent memory issues
validation_metrics = ValidationMetrics()
validation_metrics.max_series = 50  # Reduce from default

# Batch alert evaluation
alert_manager = AlertManager(optimized_registry)
# Evaluation runs every 10 seconds by default
```

This comprehensive monitoring and alerting system provides production-ready observability for Kailash SDK workflows with enterprise-grade features for security, performance, and operational monitoring.
