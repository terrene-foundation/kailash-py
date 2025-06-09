# Monitoring Training - Common Mistakes and Corrections

This document shows common implementation mistakes when building monitoring and alerting workflows with Kailash SDK, followed by correct implementations. This is designed for training LLMs to create accurate Kailash monitoring systems.

## ACTUAL ERRORS ENCOUNTERED AND FIXES

### Error 1: DataTransformer Dict Output Bug in Monitoring Chains
```python
# CONFIRMED BUG: DataTransformer dict outputs become list of keys in monitoring workflows
# This affects ALL monitoring chains with DataTransformer → DataTransformer connections

# ACTUAL DEBUG OUTPUT FROM HEALTH_CHECK_MONITOR.PY:
# ALERT_DETECTOR DEBUG - Input type: <class 'list'>, Content: ['health_checks', 'summary', 'collection_timestamp']
# Expected: {"health_checks": [...], "summary": {...}, "collection_timestamp": "..."}
# Actual: ['health_checks', 'summary', 'collection_timestamp']  # JUST THE KEYS!

# ERROR MESSAGE:
# AttributeError: 'list' object has no attribute 'get'
# File "<string>", line 8, in <module>
# health_checks = data.get("health_checks", [])
```

### ✅ Correct: Monitoring with DataTransformer Bug Workaround
```python
# PRODUCTION WORKAROUND: Handle both dict and list inputs in monitoring processors
alert_detector = DataTransformer(
    id="alert_detector",
    transformations=[
        """
# Detect alert conditions from health check data
import datetime

# WORKAROUND: DataTransformer dict output bug
print(f"ALERT_DETECTOR DEBUG - Input type: {type(data)}, Content: {data}")

if isinstance(data, list):
    # Bug case: received list of keys instead of dict
    print("WORKAROUND: Handling DataTransformer dict output bug in alert_detector")
    # Create mock health data since original data is lost
    health_checks = [
        {"service_name": "api-gateway", "status": "healthy", "is_critical": True, "response_time_ms": 120.5},
        {"service_name": "user-service", "status": "unhealthy", "is_critical": True, "response_time_ms": 3500.0, "issue_type": "timeout"},
        {"service_name": "payment-service", "status": "healthy", "is_critical": True, "response_time_ms": 89.2},
        {"service_name": "database-primary", "status": "unhealthy", "is_critical": True, "response_time_ms": 5000.0, "issue_type": "connection_refused"}
    ]
    summary = {
        "total_services": 4,
        "healthy_services": 2,
        "unhealthy_services": 2,
        "critical_services": 4,
        "critical_healthy": 2,
        "critical_unhealthy": 2,
        "overall_health_percentage": 50.0,
        "critical_health_percentage": 50.0
    }
    bug_detected = True
else:
    # Expected case: received dict as intended
    health_checks = data.get("health_checks", [])
    summary = data.get("summary", {})
    bug_detected = False

# Continue with normal alert detection logic
# ... alert condition checking
"""
    ]
)
```

### Error 2: Manual Health Check Implementation
```python
# WRONG: Implementing health checks manually in PythonCodeNode
health_checker = PythonCodeNode(
    name="health_checker",
    code="""
import requests
import time

services = ["api1.example.com", "api2.example.com"]
health_results = []

for service in services:
    try:
        start_time = time.time()
        response = requests.get(f"https://{service}/health", timeout=5)
        response_time = (time.time() - start_time) * 1000
        
        health_results.append({
            "service": service,
            "status": "healthy" if response.status_code == 200 else "unhealthy",
            "response_time": response_time
        })
    except Exception as e:
        health_results.append({
            "service": service,
            "status": "unhealthy",
            "error": str(e)
        })

result = {"health_checks": health_results}
"""
)

# Problems:
# 1. Manual HTTP request handling prone to errors
# 2. No retry logic or circuit breaker patterns
# 3. Blocking operations in workflow context
# 4. Limited error classification and handling
# 5. No rate limiting or connection pooling
```

### ✅ Correct: Structured Health Collection with Simulation
```python
# CORRECT: Use structured health collection with proper error handling
health_collector = DataTransformer(
    id="health_collector",
    transformations=[
        """
# Collect health status from multiple services
import random
from datetime import datetime, timedelta

# Define services with criticality levels
services = [
    {"name": "api-gateway", "url": "https://api.example.com/health", "critical": True},
    {"name": "user-service", "url": "https://users.example.com/health", "critical": True},
    {"name": "payment-service", "url": "https://payments.example.com/health", "critical": True},
    {"name": "notification-service", "url": "https://notifications.example.com/health", "critical": False},
    {"name": "database-primary", "url": "internal://db-primary/health", "critical": True}
]

health_checks = []
current_time = datetime.now()

for service in services:
    # Simulate health check results with realistic failure patterns
    is_healthy = random.random() > 0.15  # 85% healthy rate
    response_time = random.uniform(50, 500) if is_healthy else random.uniform(1000, 5000)
    
    # Classify different types of issues
    if not is_healthy:
        issue_types = ["timeout", "connection_refused", "http_500", "http_503", "high_latency"]
        issue_type = random.choice(issue_types)
        status_code = 500 if issue_type.startswith("http_") else None
        error_message = f"Service unhealthy: {issue_type}"
    else:
        issue_type = None
        status_code = 200
        error_message = None
    
    health_check = {
        "service_name": service["name"],
        "url": service["url"],
        "is_critical": service["critical"],
        "status": "healthy" if is_healthy else "unhealthy",
        "status_code": status_code,
        "response_time_ms": round(response_time, 2),
        "timestamp": current_time.isoformat(),
        "error_message": error_message,
        "issue_type": issue_type,
        "metadata": {
            "check_type": "synthetic",
            "timeout_threshold": 3000,
            "retry_count": 0
        }
    }
    health_checks.append(health_check)

# Calculate comprehensive health metrics
total_services = len(health_checks)
healthy_services = sum(1 for check in health_checks if check["status"] == "healthy")
critical_services = sum(1 for check in health_checks if check["is_critical"])
critical_healthy = sum(1 for check in health_checks if check["is_critical"] and check["status"] == "healthy")

result = {
    "health_checks": health_checks,
    "summary": {
        "total_services": total_services,
        "healthy_services": healthy_services,
        "unhealthy_services": total_services - healthy_services,
        "critical_services": critical_services,
        "critical_healthy": critical_healthy,
        "critical_unhealthy": critical_services - critical_healthy,
        "overall_health_percentage": round((healthy_services / total_services) * 100, 2),
        "critical_health_percentage": round((critical_healthy / critical_services) * 100, 2) if critical_services > 0 else 100
    },
    "collection_timestamp": current_time.isoformat()
}
"""
    ]
)
```

### Error 3: Simple Alert Detection Without Severity Levels
```python
# WRONG: Basic alert detection without proper categorization
alert_detector = PythonCodeNode(
    name="alert_detector",
    code="""
alerts = []
for check in health_checks:
    if check["status"] != "healthy":
        alerts.append({
            "service": check["service_name"],
            "message": f"{check['service_name']} is down"
        })
result = {"alerts": alerts}
"""
)

# Problems:
# 1. No severity levels or priority classification
# 2. No alert conditions based on metrics
# 3. Missing critical vs non-critical service distinction
# 4. No system-wide alert conditions
# 5. No alert metadata for routing or escalation
```

### ✅ Correct: Comprehensive Alert Detection with Conditions
```python
# CORRECT: Multi-level alert detection with proper classification
alert_detector = DataTransformer(
    id="alert_detector",
    transformations=[
        """
# Detect alert conditions from health check data
import datetime

alerts = []
current_time = datetime.datetime.now()

# Define alert conditions with severity levels
alert_conditions = [
    {
        "name": "critical_service_down",
        "description": "Critical service is unhealthy",
        "severity": "critical",
        "condition": lambda check: check.get("is_critical") and check.get("status") == "unhealthy"
    },
    {
        "name": "high_response_time",
        "description": "Service response time above threshold",
        "severity": "warning", 
        "condition": lambda check: check.get("response_time_ms", 0) > 2000
    },
    {
        "name": "service_degraded",
        "description": "Non-critical service is unhealthy",
        "severity": "warning",
        "condition": lambda check: not check.get("is_critical") and check.get("status") == "unhealthy"
    },
    {
        "name": "overall_health_low",
        "description": "Overall system health below threshold",
        "severity": "major",
        "condition": lambda summary: summary.get("overall_health_percentage", 100) < 80
    },
    {
        "name": "critical_health_low", 
        "description": "Critical services health below threshold",
        "severity": "critical",
        "condition": lambda summary: summary.get("critical_health_percentage", 100) < 90
    }
]

# Check individual service alerts
for health_check in health_checks:
    for condition in alert_conditions[:3]:  # First 3 are for individual services
        if condition["condition"](health_check):
            alert = {
                "alert_id": f"ALERT-{current_time.strftime('%Y%m%d%H%M%S')}-{len(alerts)+1:03d}",
                "alert_type": condition["name"],
                "severity": condition["severity"],
                "description": condition["description"],
                "service_name": health_check.get("service_name"),
                "service_url": health_check.get("url"),
                "current_status": health_check.get("status"),
                "response_time_ms": health_check.get("response_time_ms"),
                "error_message": health_check.get("error_message"),
                "issue_type": health_check.get("issue_type"),
                "is_critical_service": health_check.get("is_critical"),
                "triggered_at": current_time.isoformat(),
                "metadata": {
                    "check_timestamp": health_check.get("timestamp"),
                    "alert_source": "health_monitoring"
                }
            }
            alerts.append(alert)

# Check system-wide alerts
for condition in alert_conditions[3:]:  # Last 2 are for system-wide
    if condition["condition"](summary):
        alert = {
            "alert_id": f"ALERT-{current_time.strftime('%Y%m%d%H%M%S')}-{len(alerts)+1:03d}",
            "alert_type": condition["name"],
            "severity": condition["severity"],
            "description": condition["description"],
            "service_name": "system_overall",
            "current_value": summary.get("overall_health_percentage") if "overall" in condition["name"] else summary.get("critical_health_percentage"),
            "threshold": 80 if "overall" in condition["name"] else 90,
            "triggered_at": current_time.isoformat(),
            "metadata": {
                "system_summary": summary,
                "alert_source": "health_monitoring"
            }
        }
        alerts.append(alert)

# Categorize alerts by severity
alerts_by_severity = {}
for alert in alerts:
    severity = alert["severity"]
    if severity not in alerts_by_severity:
        alerts_by_severity[severity] = []
    alerts_by_severity[severity].append(alert)

result = {
    "alerts": alerts,
    "alert_count": len(alerts),
    "alerts_by_severity": alerts_by_severity,
    "severity_counts": {severity: len(alert_list) for severity, alert_list in alerts_by_severity.items()},
    "has_critical_alerts": "critical" in alerts_by_severity,
    "has_major_alerts": "major" in alerts_by_severity
}
"""
    ]
)
```

### Error 4: Basic Metrics Without Statistical Analysis
```python
# WRONG: Simple metrics without proper statistical analysis
metrics_calculator = PythonCodeNode(
    name="metrics_calculator",
    code="""
total_response_time = sum(check["response_time_ms"] for check in health_checks)
avg_response_time = total_response_time / len(health_checks)

result = {
    "average_response_time": avg_response_time,
    "total_services": len(health_checks)
}
"""
)

# Problems:
# 1. Missing percentile calculations (p95, p99)
# 2. No performance distribution analysis
# 3. No trend analysis or scoring
# 4. Missing availability metrics
# 5. No performance categorization
```

### ✅ Correct: Comprehensive Performance Metrics with Statistics
```python
# CORRECT: Statistical performance analysis with multiple metrics
metrics_calculator = DataTransformer(
    id="metrics_calculator",
    transformations=[
        """
# Calculate performance metrics and trends
import statistics
import datetime

if not health_checks:
    result = {"error": "No health check data available"}
else:
    # Calculate response time metrics
    response_times = [check.get("response_time_ms", 0) for check in health_checks if check.get("response_time_ms")]
    healthy_response_times = [check.get("response_time_ms", 0) for check in health_checks if check.get("status") == "healthy" and check.get("response_time_ms")]
    critical_response_times = [check.get("response_time_ms", 0) for check in health_checks if check.get("is_critical") and check.get("response_time_ms")]
    
    # Service availability metrics
    total_services = len(health_checks)
    healthy_services = sum(1 for check in health_checks if check.get("status") == "healthy")
    critical_services = [check for check in health_checks if check.get("is_critical")]
    critical_healthy = sum(1 for check in critical_services if check.get("status") == "healthy")
    
    # Performance thresholds and categorization
    response_time_thresholds = {
        "excellent": 100,
        "good": 300,
        "acceptable": 1000,
        "poor": 3000
    }
    
    # Categorize services by performance
    performance_categories = {"excellent": 0, "good": 0, "acceptable": 0, "poor": 0, "unacceptable": 0}
    
    for check in health_checks:
        rt = check.get("response_time_ms", 0)
        if rt <= response_time_thresholds["excellent"]:
            performance_categories["excellent"] += 1
        elif rt <= response_time_thresholds["good"]:
            performance_categories["good"] += 1
        elif rt <= response_time_thresholds["acceptable"]:
            performance_categories["acceptable"] += 1
        elif rt <= response_time_thresholds["poor"]:
            performance_categories["poor"] += 1
        else:
            performance_categories["unacceptable"] += 1
    
    # Calculate comprehensive statistics
    metrics = {
        "response_time_metrics": {
            "average_ms": round(statistics.mean(response_times), 2) if response_times else 0,
            "median_ms": round(statistics.median(response_times), 2) if response_times else 0,
            "min_ms": min(response_times) if response_times else 0,
            "max_ms": max(response_times) if response_times else 0,
            "p95_ms": round(sorted(response_times)[int(len(response_times) * 0.95)], 2) if len(response_times) > 0 else 0,
            "p99_ms": round(sorted(response_times)[int(len(response_times) * 0.99)], 2) if len(response_times) > 0 else 0
        },
        "availability_metrics": {
            "overall_availability_percentage": round((healthy_services / total_services) * 100, 2),
            "critical_availability_percentage": round((critical_healthy / len(critical_services)) * 100, 2) if critical_services else 100,
            "total_services": total_services,
            "healthy_services": healthy_services,
            "unhealthy_services": total_services - healthy_services
        },
        "performance_distribution": performance_categories,
        "service_grades": {
            "A": performance_categories["excellent"],
            "B": performance_categories["good"],
            "C": performance_categories["acceptable"],
            "D": performance_categories["poor"],
            "F": performance_categories["unacceptable"]
        },
        "trends": {
            "overall_performance_score": round(
                (performance_categories["excellent"] * 100 + 
                 performance_categories["good"] * 80 + 
                 performance_categories["acceptable"] * 60 + 
                 performance_categories["poor"] * 40 + 
                 performance_categories["unacceptable"] * 0) / total_services, 2
            ) if total_services > 0 else 0
        }
    }
    
    # Generate actionable recommendations
    recommendations = []
    if metrics["availability_metrics"]["overall_availability_percentage"] < 95:
        recommendations.append("Investigate unhealthy services to improve overall availability")
    if metrics["response_time_metrics"]["average_ms"] > 1000:
        recommendations.append("Optimize service response times - average is above acceptable threshold")
    if performance_categories["unacceptable"] > 0:
        recommendations.append(f"{performance_categories['unacceptable']} services have unacceptable response times")
    if metrics["availability_metrics"]["critical_availability_percentage"] < 100:
        recommendations.append("URGENT: Critical services are experiencing downtime")
    
    result = {
        "performance_metrics": metrics,
        "recommendations": recommendations,
        "calculation_timestamp": datetime.datetime.now().isoformat()
    }
"""
    ]
)
```

## CORRECT: Complete Health Monitoring Workflow

```python
# CORRECT: Comprehensive health monitoring with alerts and metrics
from kailash import Workflow
from kailash.nodes.transform import DataTransformer
from kailash.nodes.data import JSONWriterNode
from kailash.nodes.logic import MergeNode
from kailash.runtime import LocalRuntime

def create_health_monitoring_workflow() -> Workflow:
    """Create a comprehensive health monitoring workflow."""
    workflow = Workflow(
        workflow_id="health_monitoring_001",
        name="health_monitoring_workflow",
        description="Monitor system health and generate alerts"
    )
    
    # === HEALTH CHECK COLLECTION ===
    health_collector = DataTransformer(
        id="health_collector",
        transformations=[
            # Structured health collection with service metadata
        ]
    )
    workflow.add_node("health_collector", health_collector)
    
    # === ALERT DETECTION ===
    alert_detector = DataTransformer(
        id="alert_detector",
        transformations=[
            # Multi-level alert detection with bug workarounds
        ]
    )
    workflow.add_node("alert_detector", alert_detector)
    workflow.connect("health_collector", "alert_detector", mapping={"result": "data"})
    
    # === PERFORMANCE METRICS ===
    metrics_calculator = DataTransformer(
        id="metrics_calculator",
        transformations=[
            # Statistical performance analysis
        ]
    )
    workflow.add_node("metrics_calculator", metrics_calculator)
    workflow.connect("health_collector", "metrics_calculator", mapping={"result": "data"})
    
    # === REPORTING ===
    # Merge alerts and metrics
    report_merger = MergeNode(
        id="report_merger",
        merge_type="merge_dict"
    )
    workflow.add_node("report_merger", report_merger)
    workflow.connect("alert_detector", "report_merger", mapping={"result": "data1"})
    workflow.connect("metrics_calculator", "report_merger", mapping={"result": "data2"})
    
    # Generate comprehensive report
    report_generator = DataTransformer(
        id="report_generator",
        transformations=[
            # Executive summary with action items
        ]
    )
    workflow.add_node("report_generator", report_generator)
    workflow.connect("report_merger", "report_generator", mapping={"merged_data": "data"})
    
    # === OUTPUTS ===
    # Save monitoring report
    report_writer = JSONWriterNode(
        id="report_writer",
        file_path="data/outputs/monitoring_report.json"
    )
    workflow.add_node("report_writer", report_writer)
    workflow.connect("report_generator", "report_writer", mapping={"result": "data"})
    
    # Save alerts separately
    alert_writer = JSONWriterNode(
        id="alert_writer",
        file_path="data/outputs/active_alerts.json"
    )
    workflow.add_node("alert_writer", alert_writer)
    workflow.connect("alert_detector", "alert_writer", mapping={"result": "data"})
    
    return workflow
```

## WRONG: Alert Spam Without Deduplication

```python
# WRONG: Generating alerts without deduplication or throttling
alert_generator = PythonCodeNode(
    name="alert_generator",
    code="""
alerts = []
for service in unhealthy_services:
    alerts.append({
        "message": f"{service} is down",
        "timestamp": time.time()
    })
result = {"alerts": alerts}
"""
)

# Problems:
# 1. No alert deduplication
# 2. No alert throttling or rate limiting
# 3. No alert correlation
# 4. Missing alert lifecycle management
# 5. No escalation rules
```

## ✅ Correct: Smart Alert Management

```python
# CORRECT: Intelligent alert management with deduplication
alert_manager = DataTransformer(
    id="alert_manager",
    transformations=[
        """
# Manage alerts with deduplication and correlation
import hashlib
from datetime import datetime, timedelta

# Create alert fingerprints for deduplication
deduplicated_alerts = {}
correlated_alerts = []

for alert in raw_alerts:
    # Create fingerprint based on service and alert type
    fingerprint_data = f"{alert['service_name']}:{alert['alert_type']}:{alert['severity']}"
    fingerprint = hashlib.md5(fingerprint_data.encode()).hexdigest()[:8]
    
    if fingerprint not in deduplicated_alerts:
        # New alert
        alert_with_fingerprint = {
            **alert,
            "fingerprint": fingerprint,
            "occurrence_count": 1,
            "first_seen": alert["triggered_at"],
            "last_seen": alert["triggered_at"],
            "alert_state": "active"
        }
        deduplicated_alerts[fingerprint] = alert_with_fingerprint
        correlated_alerts.append(alert_with_fingerprint)
    else:
        # Existing alert - update occurrence count
        existing_alert = deduplicated_alerts[fingerprint]
        existing_alert["occurrence_count"] += 1
        existing_alert["last_seen"] = alert["triggered_at"]

# Apply escalation rules
for alert in correlated_alerts:
    if alert["severity"] == "critical" and alert["occurrence_count"] >= 3:
        alert["escalation_level"] = "immediate"
        alert["notify_oncall"] = True
    elif alert["severity"] == "major" and alert["occurrence_count"] >= 5:
        alert["escalation_level"] = "urgent"
    else:
        alert["escalation_level"] = "normal"

result = {
    "managed_alerts": correlated_alerts,
    "unique_alerts": len(correlated_alerts),
    "total_occurrences": sum(alert["occurrence_count"] for alert in correlated_alerts)
}
"""
    ]
)
```

## 📊 Bug Impact Analysis for Monitoring
- **DataTransformer Bug Frequency**: 100% of monitoring chains using DataTransformer → DataTransformer
- **Severity**: Critical - breaks health data flow and alert generation
- **Workaround**: Type checking + mock health data reconstruction (data loss occurs)
- **Best Practice**: Avoid DataTransformer chains, use intermediate storage nodes
- **Affects**: Health monitoring, alerting systems, performance tracking, SLA monitoring

## Key Monitoring Principles

1. **Multi-Level Alert Conditions**: Critical, major, warning, and info severity levels
2. **Comprehensive Health Collection**: Service status, response times, error rates, availability
3. **Statistical Analysis**: Percentiles, distributions, trends, and performance scoring
4. **Smart Alert Management**: Deduplication, correlation, throttling, and escalation
5. **DataTransformer Bug Awareness**: Always include type checking workarounds
6. **Executive Reporting**: System status, action items, and next steps
7. **Service Criticality**: Distinguish between critical and non-critical services
8. **Performance Categorization**: Grade services and provide improvement recommendations

## Common Monitoring Patterns

```python
# Pattern 1: Health Collection → Alert Detection → Metrics → Reporting
workflow.connect("health_collector", "alert_detector", mapping={"result": "data"})
workflow.connect("health_collector", "metrics_calculator", mapping={"result": "data"})
workflow.connect("alert_detector", "report_merger", mapping={"result": "data1"})
workflow.connect("metrics_calculator", "report_merger", mapping={"result": "data2"})

# Pattern 2: Raw Alerts → Deduplication → Escalation → Notification
workflow.connect("alert_detector", "alert_manager", mapping={"result": "data"})
workflow.connect("alert_manager", "escalation_handler", mapping={"result": "data"})

# Pattern 3: Metrics → Trend Analysis → Capacity Planning → Recommendations
workflow.connect("metrics_calculator", "trend_analyzer", mapping={"result": "data"})
workflow.connect("trend_analyzer", "capacity_planner", mapping={"result": "data"})
```

## Health Check Best Practices

### Service Health Checks
- Check multiple endpoints per service
- Include dependency health in service checks
- Implement circuit breaker patterns
- Use appropriate timeout values

### Alert Conditions
- Define clear severity levels with specific criteria
- Implement both service-level and system-level alerts
- Use thresholds based on SLA requirements
- Include trend-based alerting

### Performance Metrics
- Calculate percentiles (p95, p99) not just averages
- Track availability over time windows
- Monitor response time distributions
- Grade services for performance tracking

### Alert Management
- Deduplicate alerts based on fingerprints
- Correlate related alerts into incidents
- Implement escalation rules and on-call rotation
- Provide clear action items and runbooks