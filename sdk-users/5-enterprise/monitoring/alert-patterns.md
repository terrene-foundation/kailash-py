# Alert & Notification Patterns

*Comprehensive alerting strategies for Kailash applications*

## 🚨 Alert Types & Triggers

### Threshold-Based Alerts
```python
from kailash.monitoring import AlertManager, AlertRule

# Performance threshold alerts
alerts = AlertManager(
    webhook_url="https://alerts.company.com/webhook",
    default_channels=["slack", "email"]
)

# Response time alert
alerts.add_rule(AlertRule(
    name="high_response_time",
    metric="http_response_time_p95",
    condition="value > 2000",  # 2 seconds
    severity="warning",
    channels=["slack"],
    cooldown_minutes=5,
    description="95th percentile response time above threshold"
))

# Error rate alert
alerts.add_rule(AlertRule(
    name="high_error_rate",
    metric="error_rate",
    condition="value > 0.05",  # 5% error rate
    severity="critical",
    channels=["pagerduty", "slack"],
    cooldown_minutes=1,
    auto_resolve=True
))

```

### Anomaly Detection Alerts
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.monitoring import AnomalyDetectorNode

workflow = WorkflowBuilder()

# ML-based anomaly detection
workflow.add_node("AnomalyDetectorNode", "anomaly_detector", {}))

# Anomaly alert configuration
alerts.add_rule(AlertRule(
    name="traffic_anomaly",
    metric="request_rate",
    condition="anomaly_score > 0.8",
    severity="warning",
    channels=["slack"],
    metadata={
        "runbook": "https://docs.company.com/runbooks/traffic-anomaly",
        "escalation_path": ["on-call-engineer", "team-lead"]
    }
))

```

### Rate of Change Alerts
```python
# Sudden change detection
alerts.add_rule(AlertRule(
    name="sudden_traffic_drop",
    metric="request_rate",
    condition="rate_of_change < -0.5",  # 50% drop
    window="5m",
    severity="critical",
    channels=["pagerduty"],
    description="Traffic dropped significantly"
))

# Growth rate monitoring
alerts.add_rule(AlertRule(
    name="rapid_growth",
    metric="queue_depth",
    condition="rate_of_change > 2.0",  # 200% increase
    window="10m",
    severity="warning",
    channels=["slack"],
    auto_scale_action=True
))

```

## 📊 SLO-Based Alerting

### Error Budget Alerts
```python
# SLO configuration
slo_config = {
    "availability": {
        "target": 0.999,  # 99.9% uptime
        "window": "30d",
        "error_budget": 0.001  # 0.1% error budget
    },
    "latency": {
        "target": {"p95": 1000},  # 95th percentile < 1s
        "window": "7d"
    }
}

# Error budget burn rate alerts
alerts.add_rule(AlertRule(
    name="error_budget_burn_rate_fast",
    metric="error_budget_burn_rate",
    condition="value > 14.4",  # Exhausted in 2 hours
    severity="critical",
    channels=["pagerduty"],
    escalation_delay_minutes=15
))

alerts.add_rule(AlertRule(
    name="error_budget_burn_rate_slow",
    metric="error_budget_burn_rate",
    condition="value > 6",  # Exhausted in 5 hours
    severity="warning",
    channels=["slack"],
    escalation_delay_minutes=60
))

```

### Multi-Window Alerts
```python
# Sophisticated SLO alerting with multiple time windows
alerts.add_rule(AlertRule(
    name="slo_burn_rate_multi_window",
    metric="error_budget_burn_rate",
    conditions=[
        {"window": "1m", "threshold": 14.4},   # Fast burn
        {"window": "5m", "threshold": 6.0},    # Medium burn
        {"window": "30m", "threshold": 1.0}    # Slow burn
    ],
    severity_# mapping removed,
        "5m": "warning",
        "30m": "info"
    },
    require_all_windows=False  # Alert if any window breaches
))

# Time-of-day aware thresholds
alerts.add_rule(AlertRule(
    name="adaptive_response_time",
    metric="response_time_p95",
    condition="value > {threshold}",
    dynamic_threshold={
        "business_hours": 1000,  # 1s during 9-5
        "off_hours": 2000,      # 2s during off hours
        "weekend": 3000         # 3s on weekends
    }
))

```

## 🔄 Alert Lifecycle Management

### Alert States
```python
class AlertState:
    PENDING = "pending"      # Alert condition detected
    FIRING = "firing"        # Alert actively firing
    RESOLVED = "resolved"    # Condition no longer met
    SILENCED = "silenced"    # Manually suppressed
    ACKNOWLEDGED = "acked"   # Someone is working on it

# Alert with state management
from kailash.monitoring import StatefulAlertManager

stateful_alerts = StatefulAlertManager(
    state_store="redis://localhost:6379",
    alert_history_retention="30d"
)

# Add alert with state transitions
stateful_alerts.add_rule(AlertRule(
    name="database_down",
    metric="database_health",
    condition="value == 0",
    severity="critical",
    state_transitions={
        AlertState.PENDING: {
            "delay_seconds": 30,  # Wait 30s before firing
            "action": "send_notification"
        },
        AlertState.FIRING: {
            "escalation_delay": 300,  # Escalate after 5m
            "auto_acknowledge": False
        },
        AlertState.RESOLVED: {
            "send_resolution_notification": True,
            "close_incident": True
        }
    }
))

```

### Incident Correlation
```python
# Group related alerts into incidents
from kailash.monitoring import IncidentManager

incident_manager = IncidentManager(
    correlation_rules=[
        {
            "name": "database_incident",
            "pattern": ["database_*", "connection_*", "query_*"],
            "time_window": 300,  # 5 minutes
            "minimum_matches": 2
        },
        {
            "name": "service_degradation",
            "pattern": ["high_latency", "error_rate_*", "timeout_*"],
            "time_window": 180,
            "minimum_matches": 3
        }
    ]
)

# Configure incident lifecycle
incident_manager.configure_lifecycle(
    auto_create_incident=True,
    severity_escalation={
        "warning": {"after": 900, "to": "critical"},  # 15m
        "critical": {"after": 300, "to": "emergency"}   # 5m
    },
    notification_channels={
        "warning": ["slack"],
        "critical": ["slack", "email"],
        "emergency": ["pagerduty", "phone"]
    }
)

```

## 📱 Notification Channels

### Multi-Channel Setup
```python
# Configure notification channels
notification_config = {
    "slack": {
        "webhook_url": "${SLACK_WEBHOOK_URL}",
        "channel": "#alerts",
        "username": "AlertBot",
        "emoji": ":warning:",
        "template": {
            "title": "🚨 Alert: {alert_name}",
            "color": "danger",
            "fields": [
                {"title": "Severity", "value": "{severity}", "short": True},
                {"title": "Service", "value": "{service}", "short": True},
                {"title": "Value", "value": "{current_value}", "short": True},
                {"title": "Threshold", "value": "{threshold}", "short": True}
            ]
        }
    },

    "email": {
        "smtp_server": "smtp.company.com",
        "from_address": "alerts@company.com",
        "to_addresses": ["oncall@company.com"],
        "template": "alert_email.html"
    },

    "pagerduty": {
        "integration_key": "${PAGERDUTY_KEY}",
        "severity_mapping": {
            "critical": "critical",
            "warning": "warning",
            "info": "info"
        }
    },

    "webhook": {
        "url": "https://webhook.company.com/alerts",
        "method": "POST",
        "headers": {"Authorization": "Bearer ${WEBHOOK_TOKEN}"},
        "retry_attempts": 3
    }
}

```

### Smart Routing
```python
# Route alerts based on conditions
from kailash.monitoring import SmartAlertRouter

router = SmartAlertRouter([
    {
        "condition": "severity == 'critical' and service == 'payment'",
        "channels": ["pagerduty"],
        "escalation": {
            "primary": "payment-team",
            "backup": "on-call-engineer",
            "timeout_minutes": 5
        }
    },
    {
        "condition": "time_of_day >= '09:00' and time_of_day <= '17:00'",
        "channels": ["slack", "email"],
        "teams": ["dev-team", "ops-team"]
    },
    {
        "condition": "time_of_day < '09:00' or time_of_day > '17:00'",
        "channels": ["pagerduty"],
        "teams": ["on-call-engineer"]
    },
    {
        "condition": "alert_frequency > 5 in '10m'",
        "action": "suppress",
        "reason": "alert_storm_protection",
        "notification": "Alert storm detected, suppressing similar alerts"
    }
])

# Apply routing to alerts
alerts.set_router(router)

```

## 🛠️ Alert Tuning

### Reduce Alert Fatigue
```python
# Intelligent alerting to reduce noise
from kailash.monitoring import IntelligentAlerting

intelligent_alerts = IntelligentAlerting([
    # Deduplication
    {
        "strategy": "deduplicate",
        "window": "5m",
        "fields": ["alert_name", "service", "severity"]
    },

    # Rate limiting
    {
        "strategy": "rate_limit",
        "max_alerts_per_hour": 10,
        "burst_threshold": 3
    },

    # Smart grouping
    {
        "strategy": "group_similar",
        "similarity_threshold": 0.8,
        "max_group_size": 5,
        "group_notification": "📊 {count} similar alerts grouped"
    },

    # Adaptive thresholds
    {
        "strategy": "adaptive_threshold",
        "learning_period": "7d",
        "adjustment_factor": 0.1,
        "seasonal_awareness": True
    },

    # Alert scoring
    {
        "strategy": "priority_scoring",
        "factors": {
            "business_impact": 0.4,
            "technical_severity": 0.3,
            "historical_relevance": 0.2,
            "time_sensitivity": 0.1
        },
        "min_score_threshold": 0.6
    }
])

```

### Dynamic Thresholds
```python
# Adaptive thresholds based on patterns
from kailash.monitoring import DynamicThresholdManager

dynamic_thresholds = DynamicThresholdManager(
    learning_algorithms=[
        {
            "name": "seasonal_decomposition",
            "enabled": True,
            "seasonality_period": "24h",
            "trend_adjustment": True
        },
        {
            "name": "statistical_outliers",
            "method": "iqr",  # Interquartile range
            "outlier_factor": 1.5,
            "rolling_window": "1h"
        },
        {
            "name": "machine_learning",
            "model": "isolation_forest",
            "training_window": "7d",
            "retrain_interval": "24h"
        }
    ]
)

# Apply to specific metrics
dynamic_thresholds.add_metric(
    name="api_response_time",
    baseline_threshold=1000,  # Initial threshold in ms
    sensitivity=0.05,         # 5% deviation
    min_threshold=100,        # Never go below 100ms
    max_threshold=10000,      # Never exceed 10s
    adaptation_rate=0.1       # 10% adjustment per period
)

```

## 📋 Alert Templates

### Runbook Integration
```python
# Alert with runbook links
alert_template = {
    "title": "🚨 {severity} Alert: {alert_name}",
    "description": "{description}",
    "current_value": "{metric_value}",
    "threshold": "{threshold}",
    "duration": "{alert_duration}",
    "runbook_url": "https://runbooks.company.com/{alert_name}",
    "dashboard_url": "https://grafana.company.com/d/{dashboard_id}",
    "logs_url": "https://logs.company.com/search?q={search_query}",
    "actions": [
        {"text": "View Dashboard", "url": "{dashboard_url}"},
        {"text": "Check Logs", "url": "{logs_url}"},
        {"text": "Acknowledge", "action": "acknowledge"},
        {"text": "Silence 1h", "action": "silence", "duration": "1h"}
    ]
}

```

### Context-Rich Alerts
```python
# Enrich alerts with contextual information
from kailash.monitoring import ContextualAlertEnricher

enricher = ContextualAlertEnricher([
    # Service topology
    {
        "type": "service_dependencies",
        "source": "service_map.yaml",
        "include_upstream": True,
        "include_downstream": True
    },

    # Recent deployments
    {
        "type": "deployment_history",
        "source": "deployment_api",
        "lookback_hours": 24,
        "correlation_threshold": 0.8
    },

    # Similar historical incidents
    {
        "type": "incident_history",
        "similarity_matching": True,
        "max_suggestions": 3,
        "time_weight": 0.3
    },

    # Resource utilization
    {
        "type": "resource_context",
        "metrics": ["cpu", "memory", "disk", "network"],
        "time_range": "1h"
    },

    # Business impact
    {
        "type": "business_impact",
        "revenue_impact_calculator": True,
        "affected_users_estimator": True,
        "sla_impact_calculator": True
    }
])

# Enhanced alert template
contextual_alert_template = {
    "title": "🚨 {severity} Alert: {alert_name}",
    "summary": "{description}",
    "metrics": {
        "current_value": "{metric_value}",
        "threshold": "{threshold}",
        "deviation": "{deviation_percent}%"
    },
    "context": {
        "service_dependencies": "{dependencies}",
        "recent_deployments": "{deployments}",
        "resource_utilization": "{resources}",
        "business_impact": "{impact_assessment}"
    },
    "suggested_actions": "{ai_suggestions}",
    "runbook": "https://runbooks.company.com/{alert_name}",
    "similar_incidents": "{historical_matches}"
}

```

## 🎯 Alert Best Practices

### 1. **Alert Hierarchy**
```python
ALERT_SEVERITY_GUIDE = {
    "critical": {
        "description": "Service down or severely degraded",
        "response_time": "< 5 minutes",
        "channels": ["pagerduty"],
        "examples": ["service unavailable", "data loss", "security breach"]
    },
    "warning": {
        "description": "Service degraded but functional",
        "response_time": "< 30 minutes",
        "channels": ["slack", "email"],
        "examples": ["high latency", "elevated error rate", "resource usage"]
    },
    "info": {
        "description": "Notable events for awareness",
        "response_time": "next business day",
        "channels": ["slack"],
        "examples": ["deployment completed", "capacity threshold", "trend changes"]
    }
}

```

### 2. **Alert Quality Metrics**
```python
# Monitor alert effectiveness
from kailash.monitoring import AlertQualityTracker

quality_tracker = AlertQualityTracker([
    # Precision: How many alerts were actionable?
    {
        "metric": "precision",
        "calculation": "actionable_alerts / total_alerts",
        "target": 0.8,  # 80% of alerts should be actionable
        "window": "7d"
    },

    # Recall: How many real issues were caught?
    {
        "metric": "recall",
        "calculation": "caught_incidents / total_incidents",
        "target": 0.95,  # Catch 95% of real issues
        "window": "30d"
    },

    # Time to detection
    {
        "metric": "mean_time_to_detection",
        "target": 120,  # 2 minutes
        "unit": "seconds"
    },

    # False positive rate
    {
        "metric": "false_positive_rate",
        "calculation": "false_positives / total_alerts",
        "target": 0.1,  # Less than 10% false positives
        "severity_weighted": True
    },

    # Alert resolution time
    {
        "metric": "mean_time_to_resolution",
        "by_severity": {
            "critical": 300,   # 5 minutes
            "warning": 1800,   # 30 minutes
            "info": 3600       # 1 hour
        },
        "unit": "seconds"
    }
])

# Generate quality reports
quality_tracker.generate_weekly_report(
    recipients=["sre-team@company.com"],
    include_recommendations=True,
    include_trends=True
)

```

### 3. **Testing Alerts**
```python
# Test alert system regularly
from kailash.monitoring import AlertTester
from kailash.nodes.code import PythonCodeNode

# Create alert testing workflow
workflow = WorkflowBuilder()

# Automated alert testing
workflow.add_node("PythonCodeNode", "alert_tester", {})
test_results = []

for scenario in test_scenarios:
    # Inject test condition
    test_id = tester.inject_condition(
        metric=scenario["metric"],
        value=scenario["value"],
        duration=30,  # 30 seconds
        tags={"test": True, "scenario": scenario["type"]}
    )

    # Wait for alert to fire
    alert_result = tester.wait_for_alert(
        test_id=test_id,
        timeout=60,  # 1 minute
        expected_channels=["test-channel"]
    )

    test_results.append({
        "scenario": scenario["type"],
        "alert_fired": alert_result["fired"],
        "time_to_fire": alert_result["time_to_fire"],
        "channels_notified": alert_result["channels"],
        "message_quality": alert_result["message_score"]
    })

    # Clean up test condition
    tester.cleanup_test(test_id)

# Generate test report
test_summary = {
    "total_tests": len(test_results),
    "passed": len([r for r in test_results if r["alert_fired"]]),
    "average_detection_time": sum(r["time_to_fire"] for r in test_results if r["alert_fired"]) / len(test_results),
    "results": test_results
}

result = {"test_summary": test_summary}
'''
))

# Schedule regular alert tests
workflow.add_schedule(
    cron="0 6 * * 1",  # Every Monday at 6 AM
    timezone="UTC"
)

```

## 🔗 Next Steps

- [Metrics Patterns](metrics-patterns.md) - Metrics for alerting
- [Logging Patterns](logging-patterns.md) - Log-based alerts
- [Architecture Guide](../architecture/) - System design for monitoring
