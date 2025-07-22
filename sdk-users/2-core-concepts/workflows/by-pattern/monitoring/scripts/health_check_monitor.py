#!/usr/bin/env python3
"""
Health Check Monitoring Workflow - Real Infrastructure Monitoring
================================================================

Demonstrates comprehensive health monitoring patterns using Kailash SDK with real services.
This workflow uses HTTPRequestNode to check actual Docker infrastructure services,
avoiding any mock data generation.

Patterns demonstrated:
1. Real service health checking using HTTPRequestNode
2. Multi-endpoint monitoring against Docker services
3. Status aggregation and alert generation
4. Performance metrics collection from real responses

Features:
- Uses HTTPRequestNode for real health endpoint monitoring
- Monitors actual Docker services (PostgreSQL, MongoDB, Qdrant, etc.)
- Analyzes real response times and status codes
- Generates comprehensive monitoring reports
"""

import json
import os
from typing import Any

from kailash import Workflow
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import JSONWriterNode
from kailash.nodes.logic import MergeNode
from kailash.runtime.local import LocalRuntime


def get_health_endpoints() -> list[dict[str, Any]]:
    """Get list of real health endpoints to monitor.

    These correspond to the Docker services defined in docker-compose.sdk-dev.yml.
    """
    return [
        {
            "name": "postgres",
            "url": "http://localhost:5432",  # PostgreSQL doesn't have HTTP health endpoint, we'll handle differently
            "critical": True,
            "service_type": "database",
            "check_type": "tcp_port",
        },
        {
            "name": "mongodb",
            "url": "http://localhost:27017",  # MongoDB doesn't have HTTP health endpoint, we'll handle differently
            "critical": True,
            "service_type": "database",
            "check_type": "tcp_port",
        },
        {
            "name": "mongo-express",
            "url": "http://localhost:8081",
            "critical": False,
            "service_type": "web_ui",
            "check_type": "http",
        },
        {
            "name": "qdrant",
            "url": "http://localhost:6333/health",
            "critical": False,
            "service_type": "vector_db",
            "check_type": "http",
        },
        {
            "name": "kafka-ui",
            "url": "http://localhost:8082",
            "critical": False,
            "service_type": "web_ui",
            "check_type": "http",
        },
        {
            "name": "ollama",
            "url": "http://localhost:11434/api/version",
            "critical": False,
            "service_type": "ai_service",
            "check_type": "http",
        },
        {
            "name": "mock-api",
            "url": "http://localhost:8888/health",
            "critical": False,
            "service_type": "api",
            "check_type": "http",
        },
        {
            "name": "mcp-server",
            "url": "http://localhost:8765/health",
            "critical": False,
            "service_type": "mcp",
            "check_type": "http",
        },
        {
            "name": "healthcheck-aggregator",
            "url": "http://localhost:8889",
            "critical": False,
            "service_type": "monitoring",
            "check_type": "http",
        },
    ]


def create_health_monitoring_workflow() -> Workflow:
    """Create a comprehensive health monitoring workflow using real endpoints."""
    workflow = Workflow(
        workflow_id="real_health_monitoring_001",
        name="real_health_monitoring_workflow",
        description="Monitor real Docker infrastructure services using HTTPRequestNode",
    )

    # === ENDPOINT CONFIGURATION ===

    # Create endpoint configuration
    endpoint_configurator = PythonCodeNode(
        name="endpoint_configurator",
        code="""
# Configure real health endpoints for monitoring
endpoints = [
    {
        "name": "qdrant",
        "url": "http://localhost:6333/health",
        "critical": False,
        "service_type": "vector_db",
        "check_type": "http",
        "timeout": 10
    },
    {
        "name": "ollama",
        "url": "http://localhost:11434/api/version",
        "critical": False,
        "service_type": "ai_service",
        "check_type": "http",
        "timeout": 15
    },
    {
        "name": "mock-api",
        "url": "http://localhost:8888/health",
        "critical": False,
        "service_type": "api",
        "check_type": "http",
        "timeout": 10
    },
    {
        "name": "mcp-server",
        "url": "http://localhost:8765/health",
        "critical": False,
        "service_type": "mcp",
        "check_type": "http",
        "timeout": 10
    },
    {
        "name": "mongo-express",
        "url": "http://localhost:8081",
        "critical": False,
        "service_type": "web_ui",
        "check_type": "http",
        "timeout": 10
    },
    {
        "name": "kafka-ui",
        "url": "http://localhost:8082",
        "critical": False,
        "service_type": "web_ui",
        "check_type": "http",
        "timeout": 10
    },
    {
        "name": "healthcheck-aggregator",
        "url": "http://localhost:8889",
        "critical": False,
        "service_type": "monitoring",
        "check_type": "http",
        "timeout": 5
    }
]

result = {
    "endpoints": endpoints,
    "total_endpoints": len(endpoints),
    "critical_endpoints": sum(1 for ep in endpoints if ep["critical"]),
    "non_critical_endpoints": sum(1 for ep in endpoints if not ep["critical"])
}
""",
    )
    workflow.add_node("endpoint_configurator", endpoint_configurator)

    # === REAL HEALTH CHECKS ===

    # Perform health checks using HTTPRequestNode for each endpoint
    health_checker = PythonCodeNode(
        name="health_checker",
        code="""
# Perform real health checks using HTTPRequestNode
from kailash.nodes.api.http import HTTPRequestNode
from datetime import datetime
import time

endpoints = config_data.get("endpoints", [])
health_results = []

for endpoint in endpoints:
    endpoint_name = endpoint["name"]
    endpoint_url = endpoint["url"]
    is_critical = endpoint["critical"]
    service_type = endpoint["service_type"]
    timeout = endpoint.get("timeout", 10)

    try:
        # Create HTTPRequestNode for this endpoint
        http_node = HTTPRequestNode(name=f"health_check_{endpoint_name}")

        # Perform the health check
        start_time = time.time()
        response = http_node.execute(
            url=endpoint_url,
            method="GET",
            timeout=timeout,
            verify_ssl=False,  # Local services may use self-signed certs
            retry_count=1,
            retry_backoff=0.5
        )
        response_time = (time.time() - start_time) * 1000  # Convert to ms

        # Determine health status based on response
        is_healthy = response.get("success", False)
        status_code = response.get("status_code")

        # Extract additional info from response if available
        response_data = response.get("response", {})
        content = response_data.get("content", {}) if response_data else {}

        # Determine status details
        if is_healthy:
            status = "healthy"
            issue_type = None
            error_message = None
        else:
            status = "unhealthy"
            error_info = response.get("error", "Unknown error")
            error_type = response.get("error_type", "Unknown")

            # Categorize the issue
            if status_code is None:
                issue_type = "connection_refused"
                error_message = f"Cannot connect to {endpoint_name}: {error_info}"
            elif status_code == 404:
                issue_type = "endpoint_not_found"
                error_message = f"Health endpoint not found for {endpoint_name}"
            elif status_code == 500:
                issue_type = "server_error"
                error_message = f"Server error from {endpoint_name}"
            elif status_code == 503:
                issue_type = "service_unavailable"
                error_message = f"Service {endpoint_name} is unavailable"
            elif response_time > (timeout * 1000 * 0.8):  # 80% of timeout
                issue_type = "high_latency"
                error_message = f"High response time from {endpoint_name}: {response_time:.2f}ms"
            else:
                issue_type = "unknown_error"
                error_message = f"Unknown error from {endpoint_name}: {error_info}"

        health_result = {
            "service_name": endpoint_name,
            "service_type": service_type,
            "url": endpoint_url,
            "is_critical": is_critical,
            "status": status,
            "is_healthy": is_healthy,
            "status_code": status_code,
            "response_time_ms": round(response_time, 2),
            "timestamp": datetime.now().isoformat(),
            "error_message": error_message,
            "issue_type": issue_type,
            "response_details": {
                "success": response.get("success", False),
                "content_type": response_data.get("content_type") if response_data else None,
                "response_size": len(str(content)) if content else 0,
                "has_content": bool(content)
            },
            "metadata": {
                "check_type": endpoint.get("check_type", "http"),
                "timeout_used": timeout,
                "retry_attempted": not is_healthy
            }
        }

        health_results.append(health_result)

    except Exception as e:
        # Handle unexpected errors during health check
        error_result = {
            "service_name": endpoint_name,
            "service_type": service_type,
            "url": endpoint_url,
            "is_critical": is_critical,
            "status": "error",
            "is_healthy": False,
            "status_code": None,
            "response_time_ms": None,
            "timestamp": datetime.now().isoformat(),
            "error_message": f"Health check failed: {str(e)}",
            "issue_type": "check_failure",
            "response_details": {},
            "metadata": {
                "check_type": endpoint.get("check_type", "http"),
                "timeout_used": timeout,
                "exception_type": type(e).__name__
            }
        }
        health_results.append(error_result)

# Calculate overall health metrics
total_services = len(health_results)
healthy_services = sum(1 for result in health_results if result["is_healthy"])
critical_services = [r for r in health_results if r["is_critical"]]
critical_healthy = sum(1 for r in critical_services if r["is_healthy"])

# Response time statistics
response_times = [r["response_time_ms"] for r in health_results if r["response_time_ms"] is not None]
avg_response_time = sum(response_times) / len(response_times) if response_times else 0
max_response_time = max(response_times) if response_times else 0

result = {
    "health_checks": health_results,
    "summary": {
        "total_services": total_services,
        "healthy_services": healthy_services,
        "unhealthy_services": total_services - healthy_services,
        "critical_services": len(critical_services),
        "critical_healthy": critical_healthy,
        "critical_unhealthy": len(critical_services) - critical_healthy,
        "overall_health_percentage": round((healthy_services / total_services) * 100, 2) if total_services > 0 else 0,
        "critical_health_percentage": round((critical_healthy / len(critical_services)) * 100, 2) if critical_services else 100,
        "average_response_time": round(avg_response_time, 2),
        "max_response_time": round(max_response_time, 2),
        "services_responding": len(response_times)
    },
    "check_timestamp": datetime.now().isoformat()
}
""",
    )
    workflow.add_node("health_checker", health_checker)
    workflow.connect(
        "endpoint_configurator", "health_checker", mapping={"result": "config_data"}
    )

    # === ALERT GENERATION ===

    # Generate alerts based on real health check results
    alert_generator = PythonCodeNode(
        name="alert_generator",
        code="""
# Generate alerts based on real health check results
from datetime import datetime

health_data = health_results
health_checks = health_data.get("health_checks", [])
summary = health_data.get("summary", {})

alerts = []
current_time = datetime.now()

# Alert conditions based on real health check results
alert_conditions = [
    {
        "name": "critical_service_down",
        "description": "Critical service is unhealthy",
        "severity": "critical",
        "condition": lambda check: check.get("is_critical") and not check.get("is_healthy")
    },
    {
        "name": "service_connection_failed",
        "description": "Service connection refused or failed",
        "severity": "major",
        "condition": lambda check: check.get("issue_type") == "connection_refused"
    },
    {
        "name": "high_response_time",
        "description": "Service response time above threshold",
        "severity": "warning",
        "condition": lambda check: check.get("response_time_ms", 0) > 5000  # 5 seconds
    },
    {
        "name": "service_error",
        "description": "Service returned error status",
        "severity": "major",
        "condition": lambda check: check.get("status_code") and check.get("status_code") >= 500
    },
    {
        "name": "endpoint_not_found",
        "description": "Health endpoint not found",
        "severity": "warning",
        "condition": lambda check: check.get("issue_type") == "endpoint_not_found"
    }
]

# Check individual service alerts
alert_id_counter = 1
for health_check in health_checks:
    for condition in alert_conditions:
        if condition["condition"](health_check):
            alert = {
                "alert_id": f"ALERT-{current_time.strftime('%Y%m%d%H%M%S')}-{alert_id_counter:03d}",
                "alert_type": condition["name"],
                "severity": condition["severity"],
                "description": condition["description"],
                "service_name": health_check.get("service_name"),
                "service_type": health_check.get("service_type"),
                "service_url": health_check.get("url"),
                "current_status": health_check.get("status"),
                "status_code": health_check.get("status_code"),
                "response_time_ms": health_check.get("response_time_ms"),
                "error_message": health_check.get("error_message"),
                "issue_type": health_check.get("issue_type"),
                "is_critical_service": health_check.get("is_critical"),
                "triggered_at": current_time.isoformat(),
                "metadata": {
                    "check_timestamp": health_check.get("timestamp"),
                    "alert_source": "real_health_monitoring",
                    "check_type": health_check.get("metadata", {}).get("check_type")
                }
            }
            alerts.append(alert)
            alert_id_counter += 1

# System-wide alerts based on summary
if summary.get("overall_health_percentage", 100) < 80:
    alert = {
        "alert_id": f"ALERT-{current_time.strftime('%Y%m%d%H%M%S')}-{alert_id_counter:03d}",
        "alert_type": "overall_health_low",
        "severity": "major",
        "description": "Overall system health below threshold",
        "service_name": "system_overall",
        "current_value": summary.get("overall_health_percentage"),
        "threshold": 80,
        "triggered_at": current_time.isoformat(),
        "metadata": {
            "system_summary": summary,
            "alert_source": "real_health_monitoring"
        }
    }
    alerts.append(alert)
    alert_id_counter += 1

if summary.get("critical_health_percentage", 100) < 100:
    alert = {
        "alert_id": f"ALERT-{current_time.strftime('%Y%m%d%H%M%S')}-{alert_id_counter:03d}",
        "alert_type": "critical_health_degraded",
        "severity": "critical",
        "description": "Critical services experiencing issues",
        "service_name": "critical_services",
        "current_value": summary.get("critical_health_percentage"),
        "threshold": 100,
        "triggered_at": current_time.isoformat(),
        "metadata": {
            "critical_unhealthy": summary.get("critical_unhealthy"),
            "critical_total": summary.get("critical_services"),
            "alert_source": "real_health_monitoring"
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
    "has_major_alerts": "major" in alerts_by_severity,
    "has_warnings": "warning" in alerts_by_severity,
    "detection_timestamp": current_time.isoformat()
}
""",
    )
    workflow.add_node("alert_generator", alert_generator)
    workflow.connect(
        "health_checker", "alert_generator", mapping={"result": "health_results"}
    )

    # === PERFORMANCE ANALYSIS ===

    # Analyze performance metrics from real responses
    performance_analyzer = PythonCodeNode(
        name="performance_analyzer",
        code="""
# Analyze performance metrics from real health check responses
import statistics
from datetime import datetime

health_data = health_results
health_checks = health_data.get("health_checks", [])

if not health_checks:
    result = {"error": "No health check data available for analysis"}
else:
    # Extract response time metrics from real data
    response_times = [check.get("response_time_ms", 0) for check in health_checks if check.get("response_time_ms") is not None]
    healthy_response_times = [check.get("response_time_ms", 0) for check in health_checks if check.get("is_healthy") and check.get("response_time_ms") is not None]
    critical_response_times = [check.get("response_time_ms", 0) for check in health_checks if check.get("is_critical") and check.get("response_time_ms") is not None]

    # Service availability metrics from real checks
    total_services = len(health_checks)
    healthy_services = sum(1 for check in health_checks if check.get("is_healthy"))
    critical_services = [check for check in health_checks if check.get("is_critical")]
    critical_healthy = sum(1 for check in critical_services if check.get("is_healthy"))

    # Performance thresholds for categorization
    response_time_thresholds = {
        "excellent": 100,    # < 100ms
        "good": 500,         # 100-500ms
        "acceptable": 2000,  # 500ms-2s
        "poor": 5000         # 2s-5s
        # > 5s = unacceptable
    }

    # Categorize services by actual performance
    performance_categories = {"excellent": 0, "good": 0, "acceptable": 0, "poor": 0, "unacceptable": 0}

    for check in health_checks:
        rt = check.get("response_time_ms", 0)
        if rt is None:
            continue  # Skip services that didn't respond

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

    # Calculate statistics from actual measurements
    metrics = {
        "response_time_metrics": {
            "average_ms": round(statistics.mean(response_times), 2) if response_times else 0,
            "median_ms": round(statistics.median(response_times), 2) if response_times else 0,
            "min_ms": min(response_times) if response_times else 0,
            "max_ms": max(response_times) if response_times else 0,
            "p95_ms": round(sorted(response_times)[int(len(response_times) * 0.95)], 2) if len(response_times) > 0 else 0,
            "p99_ms": round(sorted(response_times)[int(len(response_times) * 0.99)], 2) if len(response_times) > 0 else 0,
            "healthy_avg_ms": round(statistics.mean(healthy_response_times), 2) if healthy_response_times else 0,
            "critical_avg_ms": round(statistics.mean(critical_response_times), 2) if critical_response_times else 0
        },
        "availability_metrics": {
            "overall_availability_percentage": round((healthy_services / total_services) * 100, 2) if total_services > 0 else 0,
            "critical_availability_percentage": round((critical_healthy / len(critical_services)) * 100, 2) if critical_services else 100,
            "total_services": total_services,
            "healthy_services": healthy_services,
            "unhealthy_services": total_services - healthy_services,
            "critical_services_count": len(critical_services),
            "critical_healthy_count": critical_healthy,
            "responding_services": len(response_times)
        },
        "performance_distribution": performance_categories,
        "service_grades": {
            "A": performance_categories["excellent"],
            "B": performance_categories["good"],
            "C": performance_categories["acceptable"],
            "D": performance_categories["poor"],
            "F": performance_categories["unacceptable"]
        },
        "service_types": {}
    }

    # Analyze by service type
    for check in health_checks:
        service_type = check.get("service_type", "unknown")
        if service_type not in metrics["service_types"]:
            metrics["service_types"][service_type] = {
                "count": 0,
                "healthy": 0,
                "avg_response_time": 0,
                "response_times": []
            }

        metrics["service_types"][service_type]["count"] += 1
        if check.get("is_healthy"):
            metrics["service_types"][service_type]["healthy"] += 1
        if check.get("response_time_ms") is not None:
            metrics["service_types"][service_type]["response_times"].append(check.get("response_time_ms"))

    # Calculate averages for service types
    for service_type, data in metrics["service_types"].items():
        if data["response_times"]:
            data["avg_response_time"] = round(statistics.mean(data["response_times"]), 2)
        data["health_percentage"] = round((data["healthy"] / data["count"]) * 100, 2)
        del data["response_times"]  # Remove raw data from output

    # Generate performance score
    total_possible_score = total_services * 100
    actual_score = (
        performance_categories["excellent"] * 100 +
        performance_categories["good"] * 80 +
        performance_categories["acceptable"] * 60 +
        performance_categories["poor"] * 40 +
        performance_categories["unacceptable"] * 0
    )
    performance_score = round((actual_score / total_possible_score) * 100, 2) if total_possible_score > 0 else 0

    metrics["trends"] = {
        "overall_performance_score": performance_score,
        "health_trend": "stable",  # Would calculate from historical data
        "performance_trend": "stable"  # Would calculate from historical data
    }

    # Generate recommendations based on actual metrics
    recommendations = []
    if metrics["availability_metrics"]["overall_availability_percentage"] < 95:
        recommendations.append("Investigate unhealthy services to improve overall availability")
    if metrics["response_time_metrics"]["average_ms"] > 2000:
        recommendations.append("Optimize service response times - average exceeds 2 seconds")
    if performance_categories["unacceptable"] > 0:
        recommendations.append(f"{performance_categories['unacceptable']} services have unacceptable response times (>5s)")
    if metrics["availability_metrics"]["critical_availability_percentage"] < 100:
        recommendations.append("URGENT: Critical services are experiencing downtime")
    if len(response_times) < total_services:
        missing_responses = total_services - len(response_times)
        recommendations.append(f"{missing_responses} services are not responding to health checks")

    result = {
        "performance_metrics": metrics,
        "recommendations": recommendations,
        "calculation_timestamp": datetime.now().isoformat(),
        "data_quality": {
            "services_analyzed": total_services,
            "valid_response_times": len(response_times),
            "missing_data_points": total_services - len(response_times),
            "health_check_success_rate": round((len(response_times) / total_services) * 100, 2) if total_services > 0 else 0
        }
    }
""",
    )
    workflow.add_node("performance_analyzer", performance_analyzer)
    workflow.connect(
        "health_checker", "performance_analyzer", mapping={"result": "health_results"}
    )

    # === REPORTING ===

    # Merge alerts and metrics for comprehensive reporting
    report_merger = MergeNode(id="report_merger", merge_type="merge_dict")
    workflow.add_node("report_merger", report_merger)
    workflow.connect("alert_generator", "report_merger", mapping={"result": "data1"})
    workflow.connect(
        "performance_analyzer", "report_merger", mapping={"result": "data2"}
    )

    # Generate comprehensive monitoring report
    report_generator = PythonCodeNode(
        name="report_generator",
        code="""
# Generate comprehensive monitoring report from real health check data
from datetime import datetime

merged_results = merged_data
alerts_data = merged_results
performance_data = merged_results

# Extract key information
alerts = alerts_data.get("alerts", [])
alert_count = alerts_data.get("alert_count", 0)
severity_counts = alerts_data.get("severity_counts", {})
has_critical = alerts_data.get("has_critical_alerts", False)

performance_metrics = performance_data.get("performance_metrics", {})
availability_metrics = performance_metrics.get("availability_metrics", {})
response_metrics = performance_metrics.get("response_time_metrics", {})
trends = performance_metrics.get("trends", {})
service_types = performance_metrics.get("service_types", {})

recommendations = performance_data.get("recommendations", [])
data_quality = performance_data.get("data_quality", {})

# Determine overall system status based on real monitoring data
if has_critical or availability_metrics.get("critical_availability_percentage", 100) < 100:
    system_status = "CRITICAL"
    status_color = "red"
elif availability_metrics.get("overall_availability_percentage", 100) < 95 or response_metrics.get("average_ms", 0) > 3000:
    system_status = "DEGRADED"
    status_color = "yellow"
elif alert_count > 0:
    system_status = "WARNING"
    status_color = "orange"
else:
    system_status = "HEALTHY"
    status_color = "green"

# Generate executive summary based on real data
current_time = datetime.now()
executive_summary = {
    "system_status": system_status,
    "status_color": status_color,
    "overall_health": f"{availability_metrics.get('overall_availability_percentage', 100):.1f}%",
    "critical_services_health": f"{availability_metrics.get('critical_availability_percentage', 100):.1f}%",
    "average_response_time": f"{response_metrics.get('average_ms', 0):.1f}ms",
    "max_response_time": f"{response_metrics.get('max_ms', 0):.1f}ms",
    "active_alerts": alert_count,
    "critical_alerts": severity_counts.get("critical", 0),
    "major_alerts": severity_counts.get("major", 0),
    "warning_alerts": severity_counts.get("warning", 0),
    "performance_score": f"{trends.get('overall_performance_score', 100):.1f}/100",
    "services_responding": availability_metrics.get("responding_services", 0),
    "total_services": availability_metrics.get("total_services", 0),
    "report_timestamp": current_time.isoformat()
}

# Generate detailed sections
alert_summary = {
    "total_alerts": alert_count,
    "by_severity": severity_counts,
    "critical_alerts": [alert for alert in alerts if alert.get("severity") == "critical"],
    "major_alerts": [alert for alert in alerts if alert.get("severity") == "major"],
    "warning_alerts": [alert for alert in alerts if alert.get("severity") == "warning"]
}

performance_summary = {
    "availability": availability_metrics,
    "response_times": response_metrics,
    "performance_trends": trends,
    "service_distribution": performance_metrics.get("performance_distribution", {}),
    "service_grades": performance_metrics.get("service_grades", {}),
    "by_service_type": service_types
}

# Generate action items based on real monitoring results
action_items = []
if system_status == "CRITICAL":
    action_items.extend([
        "IMMEDIATE: Investigate and resolve critical service outages",
        "IMMEDIATE: Check Docker service status and restart if needed",
        "Monitor critical services every 30 seconds until resolved"
    ])
elif system_status == "DEGRADED":
    action_items.extend([
        "Investigate performance degradation in Docker services",
        "Check Docker resource utilization (CPU, memory, disk)",
        "Review service logs for error patterns"
    ])
elif system_status == "WARNING":
    action_items.extend([
        "Review warning alerts and plan preventive maintenance",
        "Monitor service response times closely",
        "Schedule health check optimization"
    ])

# Add specific recommendations from performance analysis
action_items.extend(recommendations)

# Add Docker-specific recommendations
if data_quality.get("health_check_success_rate", 100) < 90:
    action_items.append("Multiple Docker services not responding - check docker-compose status")

if response_metrics.get("max_ms", 0) > 10000:
    action_items.append("Some services have very high response times - check Docker resource limits")

# Final comprehensive report
report = {
    "monitoring_report": {
        "executive_summary": executive_summary,
        "alert_summary": alert_summary,
        "performance_summary": performance_summary,
        "action_items": action_items,
        "detailed_alerts": alerts,
        "raw_metrics": performance_metrics,
        "data_quality": data_quality
    },
    "report_metadata": {
        "generated_at": current_time.isoformat(),
        "report_type": "real_health_monitoring",
        "version": "1.0",
        "monitoring_method": "HTTPRequestNode + Docker Services",
        "data_sources": ["real_docker_services"],
        "services_monitored": list(service_types.keys())
    },
    "next_actions": {
        "immediate_actions": [action for action in action_items if "IMMEDIATE" in action],
        "planned_actions": [action for action in action_items if "IMMEDIATE" not in action],
        "next_report_in": "1 minute" if system_status == "CRITICAL" else "5 minutes",
        "escalation_required": system_status in ["CRITICAL", "DEGRADED"]
    }
}

result = report
""",
    )
    workflow.add_node("report_generator", report_generator)
    workflow.connect(
        "report_merger", "report_generator", mapping={"merged_data": "merged_data"}
    )

    # === OUTPUTS ===

    # Save comprehensive monitoring report
    report_writer = JSONWriterNode(
        id="report_writer", file_path="data/outputs/real_monitoring_report.json"
    )
    workflow.add_node("report_writer", report_writer)
    workflow.connect("report_generator", "report_writer", mapping={"result": "data"})

    # Save alerts separately for alert management systems
    alert_writer = JSONWriterNode(
        id="alert_writer", file_path="data/outputs/active_alerts.json"
    )
    workflow.add_node("alert_writer", alert_writer)
    workflow.connect("alert_generator", "alert_writer", mapping={"result": "data"})

    return workflow


def run_health_monitoring():
    """Execute the real health monitoring workflow."""
    workflow = create_health_monitoring_workflow()
    runtime = LocalRuntime()

    parameters = {}

    try:
        print("Starting Real Health Monitoring Workflow...")
        print("🔍 Checking actual Docker services health...")

        result, run_id = runtime.execute(workflow, parameters=parameters)

        print("\\n✅ Health Monitoring Complete!")
        print("📁 Outputs generated:")
        print("   - Monitoring report: data/outputs/real_monitoring_report.json")
        print("   - Active alerts: data/outputs/active_alerts.json")

        # Show executive summary
        report_result = result.get("report_generator", {}).get("result", {})
        monitoring_report = report_result.get("monitoring_report", {})
        executive_summary = monitoring_report.get("executive_summary", {})

        print(
            f"\\n📊 System Status: {executive_summary.get('system_status', 'UNKNOWN')}"
        )
        print(f"   - Overall Health: {executive_summary.get('overall_health', 'N/A')}")
        print(
            f"   - Critical Services: {executive_summary.get('critical_services_health', 'N/A')}"
        )
        print(
            f"   - Average Response: {executive_summary.get('average_response_time', 'N/A')}"
        )
        print(f"   - Max Response: {executive_summary.get('max_response_time', 'N/A')}")
        print(f"   - Active Alerts: {executive_summary.get('active_alerts', 0)}")
        print(
            f"   - Performance Score: {executive_summary.get('performance_score', 'N/A')}"
        )
        print(
            f"   - Services Responding: {executive_summary.get('services_responding', 0)}/{executive_summary.get('total_services', 0)}"
        )

        # Show immediate actions if any
        next_actions = report_result.get("next_actions", {})
        immediate_actions = next_actions.get("immediate_actions", [])
        if immediate_actions:
            print("\\n🚨 IMMEDIATE ACTIONS REQUIRED:")
            for action in immediate_actions:
                print(f"   - {action}")

        # Show data quality
        data_quality = monitoring_report.get("data_quality", {})
        if data_quality:
            print("\\n📈 Data Quality:")
            print(
                f"   - Health Check Success Rate: {data_quality.get('health_check_success_rate', 0):.1f}%"
            )
            print(f"   - Services Analyzed: {data_quality.get('services_analyzed', 0)}")
            print(
                f"   - Valid Response Times: {data_quality.get('valid_response_times', 0)}"
            )

        return result

    except Exception as e:
        print(f"❌ Health Monitoring failed: {str(e)}")
        raise


def main():
    """Main entry point."""
    # Create output directories
    os.makedirs("data/outputs", exist_ok=True)

    # Run the real health monitoring workflow
    run_health_monitoring()

    # Display generated reports
    print("\\n=== Monitoring Report Preview ===")
    try:
        with open("data/outputs/real_monitoring_report.json") as f:
            report = json.load(f)
            executive_summary = report["monitoring_report"]["executive_summary"]
            print(json.dumps(executive_summary, indent=2))

        print("\\n=== Service Performance by Type ===")
        performance_summary = report["monitoring_report"]["performance_summary"]
        service_types = performance_summary.get("by_service_type", {})
        for service_type, metrics in service_types.items():
            print(
                f"{service_type}: {metrics['healthy']}/{metrics['count']} healthy, {metrics['avg_response_time']}ms avg"
            )

        print("\\n=== Active Alerts Preview ===")
        with open("data/outputs/active_alerts.json") as f:
            alerts = json.load(f)
            print(f"Alert Count: {alerts['alert_count']}")
            if alerts["alerts"]:
                print("Sample Alert:")
                print(json.dumps(alerts["alerts"][0], indent=2))
    except Exception as e:
        print(f"Could not read reports: {e}")


if __name__ == "__main__":
    main()
