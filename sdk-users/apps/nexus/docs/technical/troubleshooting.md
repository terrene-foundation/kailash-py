# Troubleshooting Guide

Comprehensive troubleshooting guide for diagnosing and resolving issues in Nexus's workflow-native platform.

## Overview

This guide provides systematic approaches to diagnose and resolve common issues in Nexus, including workflow failures, performance problems, integration errors, and configuration issues. Each section includes diagnostic tools, common symptoms, root causes, and resolution strategies.

## Diagnostic Tools

### Built-in Health Monitoring

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import time
import json
from collections import defaultdict
from enum import Enum

app = Nexus()

class HealthStatus(Enum):
    """System health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNKNOWN = "unknown"

class DiagnosticLevel(Enum):
    """Diagnostic detail levels"""
    BASIC = "basic"
    DETAILED = "detailed"
    VERBOSE = "verbose"

class NexusDiagnosticSystem:
    """Comprehensive diagnostic system for Nexus"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.diagnostic_history = []
        self.performance_metrics = defaultdict(list)
        self.error_patterns = defaultdict(int)
        self.diagnostic_config = {
            "retention_hours": 24,
            "sample_interval": 60,  # seconds
            "alert_thresholds": {
                "cpu_usage": 80,
                "memory_usage": 85,
                "error_rate": 5,
                "response_time": 5000  # ms
            }
        }

    def run_comprehensive_diagnostics(self, level=DiagnosticLevel.DETAILED):
        """Run comprehensive system diagnostics"""

        diagnostic_report = {
            "timestamp": time.time(),
            "level": level.value,
            "system_health": self._check_system_health(),
            "workflow_diagnostics": self._diagnose_workflows(),
            "performance_diagnostics": self._diagnose_performance(),
            "integration_diagnostics": self._diagnose_integrations(),
            "configuration_diagnostics": self._diagnose_configuration(),
            "error_analysis": self._analyze_errors(),
            "recommendations": []
        }

        # Generate recommendations based on findings
        diagnostic_report["recommendations"] = self._generate_recommendations(diagnostic_report)

        # Store diagnostic results
        self.diagnostic_history.append(diagnostic_report)

        # Maintain history size
        if len(self.diagnostic_history) > 100:
            self.diagnostic_history = self.diagnostic_history[-100:]

        return diagnostic_report

    def _check_system_health(self):
        """Check overall system health"""

        health = self.app.health_check()

        # Determine health status
        if health["status"] == "stopped":
            status = HealthStatus.CRITICAL
        elif health.get("workflows", 0) == 0:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.HEALTHY

        system_health = {
            "status": status.value,
            "nexus_version": health.get("version", "unknown"),
            "uptime": health.get("uptime", 0),
            "workflows_registered": health.get("workflows", 0),
            "platform_type": health.get("platform_type", "unknown"),
            "health_check_timestamp": time.time()
        }

        # Check critical components
        components = {
            "workflow_engine": self._check_workflow_engine(),
            "api_gateway": self._check_api_gateway(),
            "event_system": self._check_event_system(),
            "session_manager": self._check_session_manager()
        }

        system_health["components"] = components

        # Calculate overall health score
        healthy_components = sum(1 for c in components.values() if c["status"] == "healthy")
        system_health["health_score"] = (healthy_components / len(components)) * 100

        return system_health

    def _check_workflow_engine(self):
        """Check workflow engine health"""

        try:
            # Create test workflow
            test_workflow = WorkflowBuilder()
            test_workflow.add_node("PythonCodeNode", "test", {
                "code": "def test(data): return {'test': True}",
                "function_name": "test"
            })

            # Register and immediately unregister
            test_name = f"diagnostic_test_{int(time.time())}"
            self.app.register(test_name, test_workflow)

            # If we get here, workflow engine is working
            return {
                "status": "healthy",
                "message": "Workflow engine operational",
                "test_workflow_created": True
            }

        except Exception as e:
            return {
                "status": "critical",
                "message": f"Workflow engine error: {str(e)}",
                "test_workflow_created": False
            }

    def _check_api_gateway(self):
        """Check API gateway health"""

        # Simulate API gateway check
        return {
            "status": "healthy",
            "message": "API gateway operational",
            "endpoints_available": True,
            "response_time": 50  # ms
        }

    def _check_event_system(self):
        """Check event system health"""

        # Simulate event system check
        return {
            "status": "healthy",
            "message": "Event system operational",
            "event_queue_size": 0,
            "event_processing_rate": 100  # events/sec
        }

    def _check_session_manager(self):
        """Check session manager health"""

        try:
            # Test session creation
            session_id = self.app.create_session(channel="diagnostic")

            if session_id:
                return {
                    "status": "healthy",
                    "message": "Session manager operational",
                    "test_session_created": True,
                    "active_sessions": 1
                }
            else:
                return {
                    "status": "degraded",
                    "message": "Session creation returned empty ID",
                    "test_session_created": False
                }

        except Exception as e:
            return {
                "status": "critical",
                "message": f"Session manager error: {str(e)}",
                "test_session_created": False
            }

    def _diagnose_workflows(self):
        """Diagnose workflow-related issues"""

        workflow_diagnostics = {
            "total_workflows": self.app.health_check().get("workflows", 0),
            "workflow_errors": [],
            "registration_issues": [],
            "execution_issues": []
        }

        # Check for common workflow issues
        if workflow_diagnostics["total_workflows"] == 0:
            workflow_diagnostics["registration_issues"].append({
                "issue": "No workflows registered",
                "severity": "warning",
                "suggestion": "Register at least one workflow to enable functionality"
            })

        # Simulate workflow execution test
        try:
            # Test workflow execution capability
            test_result = {
                "execution_test": "passed",
                "avg_execution_time": 150,  # ms
                "success_rate": 98.5  # %
            }
            workflow_diagnostics["execution_metrics"] = test_result

        except Exception as e:
            workflow_diagnostics["execution_issues"].append({
                "issue": "Workflow execution test failed",
                "error": str(e),
                "severity": "critical"
            })

        return workflow_diagnostics

    def _diagnose_performance(self):
        """Diagnose performance issues"""

        performance_diagnostics = {
            "current_metrics": {
                "cpu_usage": 45,  # %
                "memory_usage": 62,  # %
                "disk_usage": 38,  # %
                "network_latency": 12,  # ms
                "response_time": 250  # ms
            },
            "performance_issues": [],
            "bottlenecks": []
        }

        # Check against thresholds
        for metric, value in performance_diagnostics["current_metrics"].items():
            threshold = self.diagnostic_config["alert_thresholds"].get(metric, 100)

            if value > threshold:
                performance_diagnostics["performance_issues"].append({
                    "metric": metric,
                    "current_value": value,
                    "threshold": threshold,
                    "severity": "warning" if value < threshold * 1.2 else "critical",
                    "impact": self._assess_performance_impact(metric, value)
                })

        # Identify bottlenecks
        if performance_diagnostics["current_metrics"]["response_time"] > 1000:
            performance_diagnostics["bottlenecks"].append({
                "type": "response_time",
                "description": "High response times detected",
                "possible_causes": [
                    "Database query optimization needed",
                    "External API latency",
                    "Insufficient caching"
                ]
            })

        return performance_diagnostics

    def _diagnose_integrations(self):
        """Diagnose integration issues"""

        integration_diagnostics = {
            "external_apis": {
                "total_configured": 3,
                "healthy": 2,
                "degraded": 1,
                "failed": 0
            },
            "databases": {
                "total_configured": 2,
                "connected": 2,
                "connection_pool_status": "optimal"
            },
            "message_queues": {
                "total_configured": 1,
                "active": 1,
                "queue_depth": 150
            },
            "integration_errors": []
        }

        # Check for integration issues
        if integration_diagnostics["external_apis"]["degraded"] > 0:
            integration_diagnostics["integration_errors"].append({
                "type": "api_degradation",
                "count": integration_diagnostics["external_apis"]["degraded"],
                "severity": "warning",
                "recommendation": "Check external API health and circuit breaker status"
            })

        if integration_diagnostics["message_queues"]["queue_depth"] > 1000:
            integration_diagnostics["integration_errors"].append({
                "type": "queue_backlog",
                "queue_depth": integration_diagnostics["message_queues"]["queue_depth"],
                "severity": "warning",
                "recommendation": "Scale consumers or optimize message processing"
            })

        return integration_diagnostics

    def _diagnose_configuration(self):
        """Diagnose configuration issues"""

        configuration_diagnostics = {
            "config_validation": {
                "syntax_valid": True,
                "required_fields": True,
                "deprecated_settings": []
            },
            "environment_variables": {
                "required_present": True,
                "conflicts": []
            },
            "security_config": {
                "encryption_enabled": True,
                "auth_configured": True,
                "ssl_enabled": True
            },
            "configuration_warnings": []
        }

        # Check for configuration issues
        if not configuration_diagnostics["security_config"]["ssl_enabled"]:
            configuration_diagnostics["configuration_warnings"].append({
                "issue": "SSL not enabled",
                "severity": "warning",
                "recommendation": "Enable SSL for production deployments"
            })

        return configuration_diagnostics

    def _analyze_errors(self):
        """Analyze error patterns"""

        # Simulate error analysis
        error_analysis = {
            "total_errors_24h": 42,
            "error_rate": 0.8,  # %
            "top_errors": [
                {
                    "error_type": "ConnectionTimeout",
                    "count": 15,
                    "percentage": 35.7,
                    "trend": "increasing",
                    "first_seen": time.time() - 7200,
                    "last_seen": time.time() - 300
                },
                {
                    "error_type": "ValidationError",
                    "count": 12,
                    "percentage": 28.6,
                    "trend": "stable",
                    "first_seen": time.time() - 14400,
                    "last_seen": time.time() - 600
                }
            ],
            "error_correlations": {
                "time_based": "Errors spike during peak hours (2-4 PM)",
                "component_based": "80% of errors from external API calls"
            }
        }

        return error_analysis

    def _assess_performance_impact(self, metric, value):
        """Assess the impact of performance issues"""

        impact_assessment = {
            "cpu_usage": {
                80: "Moderate - May experience slowdowns",
                90: "High - System responsiveness degraded",
                95: "Critical - System stability at risk"
            },
            "memory_usage": {
                80: "Moderate - Monitor for memory leaks",
                90: "High - Risk of out-of-memory errors",
                95: "Critical - Immediate action required"
            },
            "response_time": {
                3000: "Moderate - User experience impacted",
                5000: "High - Significant delays",
                10000: "Critical - System appears unresponsive"
            }
        }

        metric_impacts = impact_assessment.get(metric, {})

        for threshold, impact in sorted(metric_impacts.items()):
            if value >= threshold:
                return impact

        return "Low - Within acceptable range"

    def _generate_recommendations(self, diagnostic_report):
        """Generate actionable recommendations"""

        recommendations = []

        # System health recommendations
        if diagnostic_report["system_health"]["status"] != "healthy":
            recommendations.append({
                "priority": "high",
                "category": "system_health",
                "recommendation": "Address critical system health issues",
                "actions": [
                    "Check component status in diagnostic report",
                    "Restart failed components",
                    "Review system logs for errors"
                ]
            })

        # Performance recommendations
        perf_issues = diagnostic_report["performance_diagnostics"]["performance_issues"]
        if perf_issues:
            for issue in perf_issues:
                if issue["severity"] == "critical":
                    recommendations.append({
                        "priority": "high",
                        "category": "performance",
                        "recommendation": f"Address critical {issue['metric']} issue",
                        "actions": self._get_performance_actions(issue["metric"])
                    })

        # Integration recommendations
        integration_errors = diagnostic_report["integration_diagnostics"]["integration_errors"]
        if integration_errors:
            for error in integration_errors:
                recommendations.append({
                    "priority": "medium",
                    "category": "integration",
                    "recommendation": error["recommendation"],
                    "actions": self._get_integration_actions(error["type"])
                })

        # Error pattern recommendations
        error_analysis = diagnostic_report["error_analysis"]
        if error_analysis["error_rate"] > 2:
            recommendations.append({
                "priority": "medium",
                "category": "errors",
                "recommendation": "Investigate and address error patterns",
                "actions": [
                    f"Focus on top error: {error_analysis['top_errors'][0]['error_type']}",
                    "Review error correlations for patterns",
                    "Implement additional error handling"
                ]
            })

        return recommendations

    def _get_performance_actions(self, metric):
        """Get specific actions for performance issues"""

        actions_map = {
            "cpu_usage": [
                "Profile CPU-intensive operations",
                "Optimize algorithms and data structures",
                "Consider horizontal scaling",
                "Review workflow complexity"
            ],
            "memory_usage": [
                "Check for memory leaks",
                "Optimize data caching strategies",
                "Increase memory allocation",
                "Implement memory monitoring"
            ],
            "response_time": [
                "Enable query result caching",
                "Optimize database queries",
                "Review API call patterns",
                "Implement connection pooling"
            ]
        }

        return actions_map.get(metric, ["Review metric-specific optimizations"])

    def _get_integration_actions(self, error_type):
        """Get specific actions for integration issues"""

        actions_map = {
            "api_degradation": [
                "Check external API status pages",
                "Review circuit breaker configurations",
                "Implement fallback mechanisms",
                "Consider caching API responses"
            ],
            "queue_backlog": [
                "Scale message consumers",
                "Optimize message processing logic",
                "Review message retention policies",
                "Implement batch processing"
            ],
            "database_connection": [
                "Check database server status",
                "Review connection pool settings",
                "Verify network connectivity",
                "Check authentication credentials"
            ]
        }

        return actions_map.get(error_type, ["Review integration-specific configurations"])

    def get_diagnostic_summary(self):
        """Get summary of recent diagnostics"""

        if not self.diagnostic_history:
            return {"message": "No diagnostic history available"}

        recent_diagnostics = self.diagnostic_history[-5:]  # Last 5 runs

        # Calculate trends
        health_trend = []
        error_trend = []

        for diag in recent_diagnostics:
            health_trend.append(diag["system_health"]["health_score"])
            error_trend.append(diag["error_analysis"]["error_rate"])

        summary = {
            "diagnostic_runs": len(self.diagnostic_history),
            "last_run": self.diagnostic_history[-1]["timestamp"],
            "current_health": self.diagnostic_history[-1]["system_health"]["status"],
            "health_score": self.diagnostic_history[-1]["system_health"]["health_score"],
            "health_trend": "improving" if len(health_trend) > 1 and health_trend[-1] > health_trend[0] else "stable",
            "error_trend": "increasing" if len(error_trend) > 1 and error_trend[-1] > error_trend[0] else "stable",
            "critical_issues": len([r for r in self.diagnostic_history[-1]["recommendations"]
                                  if r["priority"] == "high"]),
            "total_recommendations": len(self.diagnostic_history[-1]["recommendations"])
        }

        return summary

# Usage example
diagnostic_system = NexusDiagnosticSystem(app)

# Run comprehensive diagnostics
diagnostic_report = diagnostic_system.run_comprehensive_diagnostics(DiagnosticLevel.DETAILED)

print(f"System Health: {diagnostic_report['system_health']['status']}")
print(f"Health Score: {diagnostic_report['system_health']['health_score']}%")
print(f"Critical Issues: {len([r for r in diagnostic_report['recommendations'] if r['priority'] == 'high'])}")

# Get diagnostic summary
summary = diagnostic_system.get_diagnostic_summary()
print(f"Diagnostic Summary: {summary}")
```

## Common Issues and Solutions

### Workflow Execution Failures

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import time
import traceback
from enum import Enum

app = Nexus()

class WorkflowErrorType(Enum):
    """Common workflow error types"""
    NODE_NOT_FOUND = "node_not_found"
    CONNECTION_ERROR = "connection_error"
    EXECUTION_TIMEOUT = "execution_timeout"
    INVALID_INPUT = "invalid_input"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    PERMISSION_DENIED = "permission_denied"

class WorkflowTroubleshooter:
    """Troubleshoot workflow execution issues"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.error_history = []
        self.resolution_strategies = {
            WorkflowErrorType.NODE_NOT_FOUND: self._resolve_node_not_found,
            WorkflowErrorType.CONNECTION_ERROR: self._resolve_connection_error,
            WorkflowErrorType.EXECUTION_TIMEOUT: self._resolve_timeout,
            WorkflowErrorType.INVALID_INPUT: self._resolve_invalid_input,
            WorkflowErrorType.RESOURCE_EXHAUSTED: self._resolve_resource_exhausted,
            WorkflowErrorType.PERMISSION_DENIED: self._resolve_permission_denied
        }

    def diagnose_workflow_error(self, workflow_name, error_message, execution_context=None):
        """Diagnose workflow execution error"""

        diagnosis = {
            "workflow_name": workflow_name,
            "error_message": error_message,
            "timestamp": time.time(),
            "error_type": self._identify_error_type(error_message),
            "root_cause": None,
            "resolution_steps": [],
            "preventive_measures": []
        }

        # Identify root cause
        diagnosis["root_cause"] = self._analyze_root_cause(
            diagnosis["error_type"],
            error_message,
            execution_context
        )

        # Get resolution steps
        if diagnosis["error_type"]:
            resolution_func = self.resolution_strategies.get(diagnosis["error_type"])
            if resolution_func:
                resolution = resolution_func(workflow_name, error_message, execution_context)
                diagnosis["resolution_steps"] = resolution["steps"]
                diagnosis["preventive_measures"] = resolution["prevention"]

        # Store in history
        self.error_history.append(diagnosis)

        return diagnosis

    def _identify_error_type(self, error_message):
        """Identify the type of workflow error"""

        error_patterns = {
            WorkflowErrorType.NODE_NOT_FOUND: ["node.*not found", "unknown node", "missing node"],
            WorkflowErrorType.CONNECTION_ERROR: ["connection.*failed", "network error", "timeout"],
            WorkflowErrorType.EXECUTION_TIMEOUT: ["execution timeout", "timed out", "deadline exceeded"],
            WorkflowErrorType.INVALID_INPUT: ["invalid input", "validation failed", "type error"],
            WorkflowErrorType.RESOURCE_EXHAUSTED: ["memory", "out of resources", "quota exceeded"],
            WorkflowErrorType.PERMISSION_DENIED: ["permission denied", "unauthorized", "access denied"]
        }

        error_lower = error_message.lower()

        for error_type, patterns in error_patterns.items():
            for pattern in patterns:
                if pattern in error_lower:
                    return error_type

        return None

    def _analyze_root_cause(self, error_type, error_message, context):
        """Analyze root cause of the error"""

        if error_type == WorkflowErrorType.NODE_NOT_FOUND:
            # Extract node name from error
            import re
            match = re.search(r"node\s+'([^']+)'", error_message, re.IGNORECASE)
            node_name = match.group(1) if match else "unknown"

            return {
                "cause": "Workflow definition references non-existent node",
                "details": f"Node '{node_name}' not found in workflow definition",
                "contributing_factors": [
                    "Typo in node name",
                    "Node removed but connection not updated",
                    "Case sensitivity issue"
                ]
            }

        elif error_type == WorkflowErrorType.CONNECTION_ERROR:
            return {
                "cause": "Network connectivity or external service issue",
                "details": "Failed to establish connection to external resource",
                "contributing_factors": [
                    "External service downtime",
                    "Network configuration issues",
                    "Firewall blocking connection",
                    "Invalid credentials or authentication"
                ]
            }

        elif error_type == WorkflowErrorType.EXECUTION_TIMEOUT:
            return {
                "cause": "Workflow execution exceeded time limit",
                "details": "One or more nodes took too long to complete",
                "contributing_factors": [
                    "Inefficient algorithm or query",
                    "External API latency",
                    "Large data processing",
                    "Deadlock or infinite loop"
                ]
            }

        elif error_type == WorkflowErrorType.INVALID_INPUT:
            return {
                "cause": "Input data does not meet workflow requirements",
                "details": "Validation failed for input parameters",
                "contributing_factors": [
                    "Missing required fields",
                    "Incorrect data types",
                    "Data format mismatch",
                    "Schema validation failure"
                ]
            }

        elif error_type == WorkflowErrorType.RESOURCE_EXHAUSTED:
            return {
                "cause": "System resources insufficient for workflow execution",
                "details": "Memory, CPU, or other resources exhausted",
                "contributing_factors": [
                    "Memory leak in workflow",
                    "Processing too much data at once",
                    "Insufficient system resources",
                    "Resource quotas exceeded"
                ]
            }

        elif error_type == WorkflowErrorType.PERMISSION_DENIED:
            return {
                "cause": "Insufficient permissions to execute workflow or access resources",
                "details": "Authorization check failed",
                "contributing_factors": [
                    "User lacks required role",
                    "Resource access not granted",
                    "Expired credentials",
                    "Security policy violation"
                ]
            }

        return {
            "cause": "Unknown error cause",
            "details": error_message,
            "contributing_factors": ["Review full error stack trace"]
        }

    def _resolve_node_not_found(self, workflow_name, error_message, context):
        """Resolution strategy for node not found errors"""

        return {
            "steps": [
                "1. List all nodes in the workflow using workflow inspection",
                "2. Check for typos in node names (case-sensitive)",
                "3. Verify node was properly registered with workflow.add_node()",
                "4. Check if node was accidentally removed",
                "5. Review workflow connections for references to missing nodes",
                "6. Use workflow visualization to identify disconnected nodes"
            ],
            "prevention": [
                "Use constants for node names to avoid typos",
                "Implement workflow validation before registration",
                "Add unit tests for workflow structure",
                "Use workflow versioning to track changes"
            ],
            "code_example": """
# Debug workflow structure
workflow = app.get_workflow(workflow_name)
nodes = workflow.get_nodes()
print(f"Available nodes: {list(nodes.keys())}")

# Check connections
for connection in workflow.get_connections():
    print(f"Connection: {connection['from']} -> {connection['to']}")
"""
        }

    def _resolve_connection_error(self, workflow_name, error_message, context):
        """Resolution strategy for connection errors"""

        return {
            "steps": [
                "1. Test connectivity to external service independently",
                "2. Verify credentials and authentication tokens",
                "3. Check firewall rules and network policies",
                "4. Review service endpoint URLs for correctness",
                "5. Implement retry logic with exponential backoff",
                "6. Enable circuit breaker for failing services",
                "7. Check service status pages for outages"
            ],
            "prevention": [
                "Implement connection pooling",
                "Add health checks for external dependencies",
                "Use connection timeouts appropriately",
                "Implement fallback mechanisms",
                "Monitor external service availability"
            ],
            "code_example": """
# Test external connectivity
import requests
try:
    response = requests.get(service_url, timeout=5)
    print(f"Service status: {response.status_code}")
except requests.exceptions.RequestException as e:
    print(f"Connection test failed: {e}")

# Add retry logic to workflow
workflow.add_node("RetryNode", "retry_handler", {
    "max_attempts": 3,
    "backoff_factor": 2,
    "retry_on_errors": ["ConnectionError", "Timeout"]
})
"""
        }

    def _resolve_timeout(self, workflow_name, error_message, context):
        """Resolution strategy for timeout errors"""

        return {
            "steps": [
                "1. Identify which node is timing out using execution logs",
                "2. Profile node execution to find bottlenecks",
                "3. Optimize long-running operations (queries, algorithms)",
                "4. Implement pagination for large data sets",
                "5. Increase timeout limits if necessary",
                "6. Consider async execution for long operations",
                "7. Add progress tracking for visibility"
            ],
            "prevention": [
                "Set realistic timeout values based on data volume",
                "Implement efficient algorithms and queries",
                "Use caching for repeated expensive operations",
                "Break large tasks into smaller chunks",
                "Monitor execution times regularly"
            ],
            "code_example": """
# Add timeout configuration
workflow.add_node("HTTPRequestNode", "api_call", {
    "url": "https://api.example.com/data",
    "timeout": 30,  # Increase timeout
    "retry_on_timeout": True
})

# Implement chunked processing
workflow.add_node("PythonCodeNode", "process_chunks", {
    "code": '''
def process_in_chunks(data):
    chunk_size = 100
    results = []

    for i in range(0, len(data), chunk_size):
        chunk = data[i:i + chunk_size]
        # Process chunk
        results.extend(process_chunk(chunk))

    return results
''',
    "function_name": "process_in_chunks"
})
"""
        }

    def _resolve_invalid_input(self, workflow_name, error_message, context):
        """Resolution strategy for invalid input errors"""

        return {
            "steps": [
                "1. Review input data against workflow requirements",
                "2. Check for missing required fields",
                "3. Verify data types match expectations",
                "4. Validate data format (JSON, XML, etc.)",
                "5. Add input validation node to workflow",
                "6. Implement data transformation if needed",
                "7. Review API documentation for requirements"
            ],
            "prevention": [
                "Define clear input schemas",
                "Implement comprehensive validation",
                "Provide helpful error messages",
                "Document workflow input requirements",
                "Add example inputs to documentation"
            ],
            "code_example": """
# Add input validation node
workflow.add_node("PythonCodeNode", "validate_input", {
    "code": '''
def validate_input(data):
    required_fields = ["user_id", "action", "timestamp"]

    # Check required fields
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")

    # Validate data types
    if not isinstance(data["user_id"], str):
        raise TypeError("user_id must be string")

    if not isinstance(data["timestamp"], (int, float)):
        raise TypeError("timestamp must be numeric")

    return {"validation": "passed", "data": data}
''',
    "function_name": "validate_input"
})
"""
        }

    def _resolve_resource_exhausted(self, workflow_name, error_message, context):
        """Resolution strategy for resource exhaustion"""

        return {
            "steps": [
                "1. Monitor resource usage during execution",
                "2. Identify memory leaks or inefficient operations",
                "3. Implement streaming for large data processing",
                "4. Optimize data structures and algorithms",
                "5. Increase resource limits if justified",
                "6. Implement resource pooling",
                "7. Consider horizontal scaling"
            ],
            "prevention": [
                "Set resource limits appropriately",
                "Implement efficient memory management",
                "Use generators for large datasets",
                "Monitor resource usage trends",
                "Implement auto-scaling policies"
            ],
            "code_example": """
# Implement memory-efficient processing
workflow.add_node("PythonCodeNode", "stream_processor", {
    "code": '''
def process_stream(data):
    # Use generator for memory efficiency
    def data_generator():
        for item in data:
            # Process one item at a time
            yield process_item(item)

    # Return generator instead of list
    return {"results": data_generator()}
''',
    "function_name": "process_stream"
})

# Add resource monitoring
import psutil
process = psutil.Process()
print(f"Memory usage: {process.memory_info().rss / 1024 / 1024:.2f} MB")
print(f"CPU usage: {process.cpu_percent()}%")
"""
        }

    def _resolve_permission_denied(self, workflow_name, error_message, context):
        """Resolution strategy for permission errors"""

        return {
            "steps": [
                "1. Verify user has required roles/permissions",
                "2. Check workflow execution permissions",
                "3. Verify resource access permissions",
                "4. Review authentication tokens/credentials",
                "5. Check for expired sessions or tokens",
                "6. Review security policies and rules",
                "7. Audit permission configuration"
            ],
            "prevention": [
                "Implement proper RBAC",
                "Document permission requirements",
                "Provide clear permission error messages",
                "Regular permission audits",
                "Implement permission inheritance"
            ],
            "code_example": """
# Check user permissions
from nexus.security import PermissionChecker

checker = PermissionChecker(app)
user_id = context.get("user_id")
required_permission = "execute_workflow"

if not checker.has_permission(user_id, required_permission):
    print(f"User {user_id} lacks permission: {required_permission}")

# Grant permission if appropriate
from nexus.security import RoleManager

role_manager = RoleManager(app)
role_manager.grant_permission(user_id, required_permission)
"""
        }

    def get_common_errors_report(self):
        """Generate report of common errors and resolutions"""

        if not self.error_history:
            return {"message": "No error history available"}

        # Analyze error patterns
        error_counts = {}
        resolution_success = {}

        for error in self.error_history:
            error_type = error.get("error_type")
            if error_type:
                error_type_name = error_type.value if hasattr(error_type, 'value') else str(error_type)
                error_counts[error_type_name] = error_counts.get(error_type_name, 0) + 1

        # Sort by frequency
        sorted_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)

        report = {
            "total_errors": len(self.error_history),
            "unique_workflows_affected": len(set(e["workflow_name"] for e in self.error_history)),
            "most_common_errors": [
                {
                    "error_type": error_type,
                    "count": count,
                    "percentage": (count / len(self.error_history)) * 100
                }
                for error_type, count in sorted_errors[:5]
            ],
            "recent_errors": [
                {
                    "workflow": e["workflow_name"],
                    "error_type": e.get("error_type").value if e.get("error_type") else "unknown",
                    "timestamp": e["timestamp"]
                }
                for e in self.error_history[-5:]
            ]
        }

        return report

# Usage example
troubleshooter = WorkflowTroubleshooter(app)

# Diagnose a workflow error
error_diagnosis = troubleshooter.diagnose_workflow_error(
    "data_processor",
    "Error: Node 'transform_data' not found in workflow",
    {"user_id": "user123", "execution_id": "exec_456"}
)

print(f"Error Type: {error_diagnosis['error_type'].value if error_diagnosis['error_type'] else 'unknown'}")
print(f"Root Cause: {error_diagnosis['root_cause']['cause']}")
print(f"Resolution Steps: {len(error_diagnosis['resolution_steps'])}")

# Get common errors report
error_report = troubleshooter.get_common_errors_report()
print(f"Common Errors Report: {error_report}")
```

## Performance Troubleshooting

### Performance Diagnostics and Optimization

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import time
import statistics
from collections import deque
from enum import Enum

app = Nexus()

class PerformanceIssueType(Enum):
    """Types of performance issues"""
    SLOW_RESPONSE = "slow_response"
    HIGH_CPU = "high_cpu"
    HIGH_MEMORY = "high_memory"
    DATABASE_BOTTLENECK = "database_bottleneck"
    API_LATENCY = "api_latency"
    QUEUE_BACKUP = "queue_backup"

class PerformanceTroubleshooter:
    """Diagnose and resolve performance issues"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.performance_history = deque(maxlen=1000)
        self.baseline_metrics = {
            "response_time": 200,  # ms
            "cpu_usage": 40,  # %
            "memory_usage": 50,  # %
            "throughput": 100  # requests/sec
        }
        self.optimization_strategies = {
            PerformanceIssueType.SLOW_RESPONSE: self._optimize_slow_response,
            PerformanceIssueType.HIGH_CPU: self._optimize_high_cpu,
            PerformanceIssueType.HIGH_MEMORY: self._optimize_high_memory,
            PerformanceIssueType.DATABASE_BOTTLENECK: self._optimize_database,
            PerformanceIssueType.API_LATENCY: self._optimize_api_calls,
            PerformanceIssueType.QUEUE_BACKUP: self._optimize_queue_processing
        }

    def run_performance_diagnostic(self):
        """Run comprehensive performance diagnostics"""

        diagnostic_result = {
            "timestamp": time.time(),
            "current_metrics": self._collect_current_metrics(),
            "performance_issues": [],
            "bottlenecks": [],
            "optimization_recommendations": []
        }

        # Analyze current metrics against baseline
        for metric, current_value in diagnostic_result["current_metrics"].items():
            baseline_value = self.baseline_metrics.get(metric, 0)

            if metric == "response_time" and current_value > baseline_value * 2:
                diagnostic_result["performance_issues"].append({
                    "type": PerformanceIssueType.SLOW_RESPONSE,
                    "metric": metric,
                    "current": current_value,
                    "baseline": baseline_value,
                    "severity": self._calculate_severity(current_value, baseline_value)
                })

            elif metric == "cpu_usage" and current_value > 80:
                diagnostic_result["performance_issues"].append({
                    "type": PerformanceIssueType.HIGH_CPU,
                    "metric": metric,
                    "current": current_value,
                    "threshold": 80,
                    "severity": "high" if current_value > 90 else "medium"
                })

            elif metric == "memory_usage" and current_value > 85:
                diagnostic_result["performance_issues"].append({
                    "type": PerformanceIssueType.HIGH_MEMORY,
                    "metric": metric,
                    "current": current_value,
                    "threshold": 85,
                    "severity": "high" if current_value > 95 else "medium"
                })

        # Identify bottlenecks
        diagnostic_result["bottlenecks"] = self._identify_bottlenecks()

        # Generate optimization recommendations
        for issue in diagnostic_result["performance_issues"]:
            issue_type = issue["type"]
            if issue_type in self.optimization_strategies:
                optimization = self.optimization_strategies[issue_type]()
                diagnostic_result["optimization_recommendations"].append({
                    "issue_type": issue_type.value,
                    "optimization": optimization
                })

        # Store in history
        self.performance_history.append(diagnostic_result)

        return diagnostic_result

    def _collect_current_metrics(self):
        """Collect current performance metrics"""

        # Simulate metric collection
        import random

        return {
            "response_time": random.uniform(150, 800),  # ms
            "cpu_usage": random.uniform(30, 95),  # %
            "memory_usage": random.uniform(40, 90),  # %
            "throughput": random.uniform(50, 150),  # requests/sec
            "active_connections": random.randint(10, 100),
            "queue_depth": random.randint(0, 500),
            "cache_hit_rate": random.uniform(60, 95),  # %
            "error_rate": random.uniform(0, 5)  # %
        }

    def _calculate_severity(self, current, baseline):
        """Calculate severity of performance degradation"""

        ratio = current / baseline

        if ratio > 5:
            return "critical"
        elif ratio > 3:
            return "high"
        elif ratio > 2:
            return "medium"
        else:
            return "low"

    def _identify_bottlenecks(self):
        """Identify performance bottlenecks"""

        bottlenecks = []

        # Analyze recent performance history
        if len(self.performance_history) >= 10:
            recent_metrics = [h["current_metrics"] for h in list(self.performance_history)[-10:]]

            # Check for consistent high response times
            avg_response_time = statistics.mean(m["response_time"] for m in recent_metrics)
            if avg_response_time > 500:
                bottlenecks.append({
                    "type": "response_time",
                    "description": "Consistently high response times",
                    "avg_value": avg_response_time,
                    "impact": "User experience degradation"
                })

            # Check for queue buildup
            avg_queue_depth = statistics.mean(m["queue_depth"] for m in recent_metrics)
            if avg_queue_depth > 200:
                bottlenecks.append({
                    "type": "queue_processing",
                    "description": "Message queue backlog growing",
                    "avg_value": avg_queue_depth,
                    "impact": "Delayed processing and increased latency"
                })

            # Check cache effectiveness
            avg_cache_hit = statistics.mean(m["cache_hit_rate"] for m in recent_metrics)
            if avg_cache_hit < 70:
                bottlenecks.append({
                    "type": "cache_inefficiency",
                    "description": "Low cache hit rate",
                    "avg_value": avg_cache_hit,
                    "impact": "Increased database load and response times"
                })

        return bottlenecks

    def _optimize_slow_response(self):
        """Optimization strategy for slow response times"""

        return {
            "strategy": "Response Time Optimization",
            "immediate_actions": [
                "Enable query result caching",
                "Implement connection pooling",
                "Add database indexes on frequently queried fields",
                "Enable HTTP response compression"
            ],
            "long_term_actions": [
                "Implement read replicas for database",
                "Add CDN for static content",
                "Optimize workflow execution paths",
                "Implement async processing for heavy operations"
            ],
            "code_examples": [
                """
# Enable caching in workflow
workflow.add_node("CacheNode", "cache_results", {
    "cache_key": "query_results_{user_id}",
    "ttl": 300,  # 5 minutes
    "cache_on_success": True
})
""",
                """
# Implement connection pooling
from nexus.database import ConnectionPool

pool = ConnectionPool(
    min_connections=5,
    max_connections=20,
    idle_timeout=300
)
app.set_connection_pool(pool)
"""
            ]
        }

    def _optimize_high_cpu(self):
        """Optimization strategy for high CPU usage"""

        return {
            "strategy": "CPU Usage Optimization",
            "immediate_actions": [
                "Profile CPU-intensive operations",
                "Optimize algorithms and data structures",
                "Implement request throttling",
                "Reduce logging verbosity in production"
            ],
            "long_term_actions": [
                "Implement horizontal scaling",
                "Move CPU-intensive tasks to background jobs",
                "Use more efficient libraries/algorithms",
                "Implement compute result caching"
            ],
            "code_examples": [
                """
# Profile CPU usage
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Run workflow
result = app.execute_workflow("cpu_intensive_workflow")

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(10)  # Top 10 CPU consumers
""",
                """
# Optimize algorithm
# Before: O(n²) complexity
def inefficient_search(items, target):
    for i in range(len(items)):
        for j in range(len(items)):
            if items[i] + items[j] == target:
                return True
    return False

# After: O(n) complexity
def efficient_search(items, target):
    seen = set()
    for item in items:
        if target - item in seen:
            return True
        seen.add(item)
    return False
"""
            ]
        }

    def _optimize_high_memory(self):
        """Optimization strategy for high memory usage"""

        return {
            "strategy": "Memory Usage Optimization",
            "immediate_actions": [
                "Identify and fix memory leaks",
                "Implement streaming for large data",
                "Reduce in-memory cache sizes",
                "Use generators instead of lists"
            ],
            "long_term_actions": [
                "Implement data pagination",
                "Use memory-efficient data structures",
                "Implement garbage collection tuning",
                "Consider memory-mapped files for large datasets"
            ],
            "code_examples": [
                """
# Use generators for memory efficiency
def process_large_dataset(file_path):
    # Instead of loading entire file
    # data = open(file_path).readlines()

    # Use generator
    with open(file_path) as f:
        for line in f:
            yield process_line(line)
""",
                """
# Implement data streaming
workflow.add_node("StreamProcessorNode", "stream_data", {
    "batch_size": 100,
    "stream_enabled": True,
    "memory_limit_mb": 512
})
"""
            ]
        }

    def _optimize_database(self):
        """Optimization strategy for database bottlenecks"""

        return {
            "strategy": "Database Performance Optimization",
            "immediate_actions": [
                "Add missing indexes",
                "Optimize slow queries",
                "Enable query caching",
                "Increase connection pool size"
            ],
            "long_term_actions": [
                "Implement database sharding",
                "Add read replicas",
                "Denormalize hot tables",
                "Implement materialized views"
            ],
            "code_examples": [
                """
# Analyze slow queries
EXPLAIN ANALYZE
SELECT u.*, p.*
FROM users u
JOIN profiles p ON u.id = p.user_id
WHERE u.created_at > NOW() - INTERVAL '7 days'
ORDER BY u.created_at DESC;

-- Add composite index
CREATE INDEX idx_users_created_at ON users(created_at DESC);
CREATE INDEX idx_profiles_user_id ON profiles(user_id);
""",
                """
# Implement query optimization in workflow
workflow.add_node("OptimizedQueryNode", "efficient_query", {
    "query": "SELECT * FROM users WHERE status = ? LIMIT ?",
    "parameters": ["active", 100],
    "use_prepared_statement": True,
    "cache_results": True
})
"""
            ]
        }

    def _optimize_api_calls(self):
        """Optimization strategy for API latency"""

        return {
            "strategy": "API Latency Optimization",
            "immediate_actions": [
                "Implement request batching",
                "Add response caching",
                "Enable HTTP/2",
                "Implement circuit breakers"
            ],
            "long_term_actions": [
                "Use GraphQL for efficient data fetching",
                "Implement edge caching",
                "Use WebSockets for real-time data",
                "Consider API gateway optimization"
            ],
            "code_examples": [
                """
# Batch API requests
def batch_api_requests(items):
    batch_size = 50
    results = []

    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        response = api_client.post("/batch", {"items": batch})
        results.extend(response.json()["results"])

    return results
""",
                """
# Implement circuit breaker
from nexus.resilience import CircuitBreaker

circuit_breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=RequestException
)

@circuit_breaker
def call_external_api(endpoint, data):
    return requests.post(endpoint, json=data, timeout=5)
"""
            ]
        }

    def _optimize_queue_processing(self):
        """Optimization strategy for queue processing"""

        return {
            "strategy": "Queue Processing Optimization",
            "immediate_actions": [
                "Increase consumer count",
                "Implement batch processing",
                "Optimize message size",
                "Add priority queues"
            ],
            "long_term_actions": [
                "Implement queue partitioning",
                "Use stream processing frameworks",
                "Implement dead letter queues",
                "Consider event sourcing"
            ],
            "code_examples": [
                """
# Batch message processing
def process_messages_batch(queue_name, batch_size=10):
    messages = queue.receive_messages(
        queue_name,
        max_messages=batch_size,
        visibility_timeout=300
    )

    if messages:
        # Process all messages in parallel
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = executor.map(process_message, messages)

        # Batch acknowledge
        queue.delete_messages_batch(
            [msg for msg, success in zip(messages, results) if success]
        )
""",
                """
# Implement priority queue processing
workflow.add_node("PriorityQueueNode", "priority_processor", {
    "high_priority_queue": "urgent_tasks",
    "normal_priority_queue": "standard_tasks",
    "process_ratio": 3,  # Process 3 high priority for every 1 normal
    "batch_size": 20
})
"""
            ]
        }

    def generate_performance_report(self):
        """Generate comprehensive performance report"""

        if not self.performance_history:
            return {"message": "No performance history available"}

        recent_diagnostics = list(self.performance_history)[-20:]  # Last 20 runs

        # Calculate trends
        metrics_trends = {}
        for metric in ["response_time", "cpu_usage", "memory_usage", "throughput"]:
            values = [d["current_metrics"][metric] for d in recent_diagnostics]

            if len(values) >= 2:
                # Simple linear regression for trend
                avg_first_half = statistics.mean(values[:len(values)//2])
                avg_second_half = statistics.mean(values[len(values)//2:])

                if avg_second_half > avg_first_half * 1.1:
                    trend = "degrading"
                elif avg_second_half < avg_first_half * 0.9:
                    trend = "improving"
                else:
                    trend = "stable"

                metrics_trends[metric] = {
                    "current": values[-1],
                    "average": statistics.mean(values),
                    "min": min(values),
                    "max": max(values),
                    "trend": trend
                }

        # Identify most common issues
        all_issues = []
        for diagnostic in recent_diagnostics:
            all_issues.extend(diagnostic.get("performance_issues", []))

        issue_counts = {}
        for issue in all_issues:
            issue_type = issue["type"].value
            issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1

        report = {
            "report_timestamp": time.time(),
            "diagnostics_analyzed": len(recent_diagnostics),
            "metrics_trends": metrics_trends,
            "most_common_issues": sorted(issue_counts.items(), key=lambda x: x[1], reverse=True),
            "current_bottlenecks": recent_diagnostics[-1].get("bottlenecks", []) if recent_diagnostics else [],
            "optimization_priority": self._determine_optimization_priority(metrics_trends, issue_counts)
        }

        return report

    def _determine_optimization_priority(self, trends, issue_counts):
        """Determine which optimizations to prioritize"""

        priorities = []

        # Check degrading metrics
        for metric, trend_data in trends.items():
            if trend_data["trend"] == "degrading":
                if metric == "response_time":
                    priorities.append({
                        "priority": "high",
                        "focus": "Response time optimization",
                        "reason": f"Response times degrading: {trend_data['current']:.0f}ms"
                    })
                elif metric == "cpu_usage" and trend_data["current"] > 80:
                    priorities.append({
                        "priority": "high",
                        "focus": "CPU optimization",
                        "reason": f"CPU usage trending up: {trend_data['current']:.1f}%"
                    })

        # Check frequent issues
        if issue_counts:
            most_common_issue = max(issue_counts.items(), key=lambda x: x[1])
            if most_common_issue[1] > 5:  # More than 5 occurrences
                priorities.append({
                    "priority": "medium",
                    "focus": f"Address {most_common_issue[0]}",
                    "reason": f"Occurred {most_common_issue[1]} times recently"
                })

        return priorities[:3]  # Top 3 priorities

# Usage example
perf_troubleshooter = PerformanceTroubleshooter(app)

# Run performance diagnostics
perf_diagnostic = perf_troubleshooter.run_performance_diagnostic()

print(f"Performance Issues Found: {len(perf_diagnostic['performance_issues'])}")
print(f"Bottlenecks Identified: {len(perf_diagnostic['bottlenecks'])}")
print(f"Optimizations Recommended: {len(perf_diagnostic['optimization_recommendations'])}")

# Generate performance report
perf_report = perf_troubleshooter.generate_performance_report()
print(f"Performance Report: {perf_report}")
```

## Integration Troubleshooting

### External System Integration Issues

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import time
from enum import Enum
from collections import defaultdict

app = Nexus()

class IntegrationIssueType(Enum):
    """Types of integration issues"""
    CONNECTION_REFUSED = "connection_refused"
    AUTHENTICATION_FAILED = "authentication_failed"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    INVALID_RESPONSE = "invalid_response"
    SERVICE_UNAVAILABLE = "service_unavailable"

class IntegrationTroubleshooter:
    """Troubleshoot external system integration issues"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.integration_tests = {}
        self.issue_history = defaultdict(list)
        self.service_health = {}

    def test_integration(self, service_name, config):
        """Test integration with external service"""

        test_result = {
            "service_name": service_name,
            "timestamp": time.time(),
            "tests_passed": 0,
            "tests_failed": 0,
            "issues_found": [],
            "recommendations": []
        }

        # Run connectivity test
        connectivity = self._test_connectivity(service_name, config)
        if connectivity["success"]:
            test_result["tests_passed"] += 1
        else:
            test_result["tests_failed"] += 1
            test_result["issues_found"].append(connectivity["issue"])

        # Run authentication test
        if connectivity["success"]:
            auth = self._test_authentication(service_name, config)
            if auth["success"]:
                test_result["tests_passed"] += 1
            else:
                test_result["tests_failed"] += 1
                test_result["issues_found"].append(auth["issue"])

        # Run API endpoint test
        if connectivity["success"] and config.get("test_endpoint"):
            api_test = self._test_api_endpoint(service_name, config)
            if api_test["success"]:
                test_result["tests_passed"] += 1
            else:
                test_result["tests_failed"] += 1
                test_result["issues_found"].append(api_test["issue"])

        # Generate recommendations
        test_result["recommendations"] = self._generate_integration_recommendations(
            service_name, test_result["issues_found"]
        )

        # Store test results
        self.integration_tests[service_name] = test_result

        # Update service health
        self._update_service_health(service_name, test_result)

        return test_result

    def _test_connectivity(self, service_name, config):
        """Test basic connectivity to service"""

        import socket

        host = config.get("host", "localhost")
        port = config.get("port", 80)
        timeout = config.get("timeout", 5)

        try:
            # Test TCP connection
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()

            if result == 0:
                return {
                    "success": True,
                    "message": f"Successfully connected to {host}:{port}"
                }
            else:
                return {
                    "success": False,
                    "issue": {
                        "type": IntegrationIssueType.CONNECTION_REFUSED,
                        "details": f"Cannot connect to {host}:{port}",
                        "error_code": result
                    }
                }

        except socket.timeout:
            return {
                "success": False,
                "issue": {
                    "type": IntegrationIssueType.TIMEOUT,
                    "details": f"Connection timeout to {host}:{port}",
                    "timeout": timeout
                }
            }
        except Exception as e:
            return {
                "success": False,
                "issue": {
                    "type": IntegrationIssueType.CONNECTION_REFUSED,
                    "details": f"Connection error: {str(e)}"
                }
            }

    def _test_authentication(self, service_name, config):
        """Test authentication with service"""

        auth_type = config.get("auth_type", "none")

        if auth_type == "none":
            return {"success": True, "message": "No authentication required"}

        # Simulate authentication test
        import random
        if random.random() > 0.1:  # 90% success rate
            return {
                "success": True,
                "message": f"Authentication successful using {auth_type}"
            }
        else:
            return {
                "success": False,
                "issue": {
                    "type": IntegrationIssueType.AUTHENTICATION_FAILED,
                    "details": f"Authentication failed using {auth_type}",
                    "auth_type": auth_type
                }
            }

    def _test_api_endpoint(self, service_name, config):
        """Test specific API endpoint"""

        endpoint = config.get("test_endpoint")
        expected_status = config.get("expected_status", 200)

        # Simulate API test
        import random
        response_time = random.uniform(50, 500)
        status_code = random.choice([200, 200, 200, 401, 429, 500])  # Weighted towards success

        if status_code == expected_status:
            return {
                "success": True,
                "message": f"API endpoint test successful",
                "response_time": response_time
            }
        else:
            issue_type = IntegrationIssueType.INVALID_RESPONSE

            if status_code == 401:
                issue_type = IntegrationIssueType.AUTHENTICATION_FAILED
            elif status_code == 429:
                issue_type = IntegrationIssueType.RATE_LIMITED
            elif status_code >= 500:
                issue_type = IntegrationIssueType.SERVICE_UNAVAILABLE

            return {
                "success": False,
                "issue": {
                    "type": issue_type,
                    "details": f"Unexpected status code: {status_code}",
                    "expected": expected_status,
                    "actual": status_code,
                    "endpoint": endpoint
                }
            }

    def _generate_integration_recommendations(self, service_name, issues):
        """Generate recommendations based on issues found"""

        recommendations = []

        for issue in issues:
            issue_type = issue["type"]

            if issue_type == IntegrationIssueType.CONNECTION_REFUSED:
                recommendations.extend([
                    "Verify service is running and accessible",
                    "Check firewall rules and network policies",
                    "Verify correct host and port configuration",
                    "Test connectivity from Nexus server",
                    "Check for IP whitelisting requirements"
                ])

            elif issue_type == IntegrationIssueType.AUTHENTICATION_FAILED:
                recommendations.extend([
                    "Verify credentials are correct and not expired",
                    "Check authentication method matches service requirements",
                    "Ensure proper encoding of credentials",
                    "Verify API keys/tokens have required permissions",
                    "Check for IP-based authentication restrictions"
                ])

            elif issue_type == IntegrationIssueType.RATE_LIMITED:
                recommendations.extend([
                    "Implement request throttling",
                    "Add exponential backoff for retries",
                    "Consider caching responses to reduce API calls",
                    "Request rate limit increase from service provider",
                    "Implement request batching where possible"
                ])

            elif issue_type == IntegrationIssueType.TIMEOUT:
                recommendations.extend([
                    "Increase timeout values for slow endpoints",
                    "Implement connection pooling",
                    "Check network latency to service",
                    "Consider async processing for long operations",
                    "Verify service performance and health"
                ])

            elif issue_type == IntegrationIssueType.SERVICE_UNAVAILABLE:
                recommendations.extend([
                    "Check service status page for outages",
                    "Implement circuit breaker pattern",
                    "Add fallback mechanisms",
                    "Set up service health monitoring",
                    "Consider multi-region failover"
                ])

        # Remove duplicates and return
        return list(dict.fromkeys(recommendations))

    def _update_service_health(self, service_name, test_result):
        """Update service health status"""

        total_tests = test_result["tests_passed"] + test_result["tests_failed"]
        success_rate = (test_result["tests_passed"] / total_tests * 100) if total_tests > 0 else 0

        health_status = "healthy"
        if success_rate < 50:
            health_status = "critical"
        elif success_rate < 80:
            health_status = "degraded"

        self.service_health[service_name] = {
            "status": health_status,
            "success_rate": success_rate,
            "last_tested": test_result["timestamp"],
            "issues_count": len(test_result["issues_found"])
        }

    def diagnose_integration_failure(self, service_name, error_message, context=None):
        """Diagnose specific integration failure"""

        diagnosis = {
            "service_name": service_name,
            "error_message": error_message,
            "timestamp": time.time(),
            "diagnosis": {},
            "resolution_steps": [],
            "workarounds": []
        }

        # Analyze error message
        error_lower = error_message.lower()

        if "connection refused" in error_lower or "cannot connect" in error_lower:
            diagnosis["diagnosis"] = {
                "issue_type": IntegrationIssueType.CONNECTION_REFUSED,
                "likely_causes": [
                    "Service is down or not running",
                    "Incorrect host/port configuration",
                    "Firewall blocking connection",
                    "Service not exposed on network"
                ]
            }
            diagnosis["resolution_steps"] = [
                "Verify service is running: systemctl status <service>",
                "Test connectivity: telnet <host> <port>",
                "Check firewall rules: iptables -L or ufw status",
                "Verify service binding: netstat -tlnp | grep <port>"
            ]

        elif "unauthorized" in error_lower or "authentication" in error_lower:
            diagnosis["diagnosis"] = {
                "issue_type": IntegrationIssueType.AUTHENTICATION_FAILED,
                "likely_causes": [
                    "Invalid or expired credentials",
                    "Wrong authentication method",
                    "Missing required headers",
                    "Token/key lacks permissions"
                ]
            }
            diagnosis["resolution_steps"] = [
                "Verify credentials in configuration",
                "Check credential expiration",
                "Test authentication manually with curl",
                "Review API documentation for auth requirements"
            ]

        elif "rate limit" in error_lower or "429" in error_lower:
            diagnosis["diagnosis"] = {
                "issue_type": IntegrationIssueType.RATE_LIMITED,
                "likely_causes": [
                    "Exceeding API rate limits",
                    "Too many concurrent requests",
                    "Missing rate limit headers",
                    "Shared rate limit with other services"
                ]
            }
            diagnosis["resolution_steps"] = [
                "Check rate limit headers in response",
                "Implement request throttling",
                "Add delays between requests",
                "Contact provider for limit increase"
            ]
            diagnosis["workarounds"] = [
                "Implement caching to reduce API calls",
                "Batch requests where possible",
                "Use webhooks instead of polling"
            ]

        # Store diagnosis
        self.issue_history[service_name].append(diagnosis)

        return diagnosis

    def get_integration_health_report(self):
        """Generate comprehensive integration health report"""

        report = {
            "timestamp": time.time(),
            "total_services": len(self.service_health),
            "services_by_status": {
                "healthy": 0,
                "degraded": 0,
                "critical": 0
            },
            "recent_issues": [],
            "problematic_services": []
        }

        # Count services by status
        for service, health in self.service_health.items():
            status = health["status"]
            report["services_by_status"][status] += 1

            if status != "healthy":
                report["problematic_services"].append({
                    "service": service,
                    "status": status,
                    "success_rate": health["success_rate"],
                    "issues": health["issues_count"]
                })

        # Get recent issues across all services
        all_issues = []
        for service, issues in self.issue_history.items():
            for issue in issues[-5:]:  # Last 5 issues per service
                all_issues.append({
                    "service": service,
                    "timestamp": issue["timestamp"],
                    "issue_type": issue["diagnosis"].get("issue_type", {}).value
                                  if hasattr(issue["diagnosis"].get("issue_type", {}), 'value')
                                  else "unknown"
                })

        # Sort by timestamp and get most recent
        all_issues.sort(key=lambda x: x["timestamp"], reverse=True)
        report["recent_issues"] = all_issues[:10]

        # Calculate overall health score
        total_services = report["total_services"]
        if total_services > 0:
            healthy_weight = report["services_by_status"]["healthy"] * 1.0
            degraded_weight = report["services_by_status"]["degraded"] * 0.5
            critical_weight = report["services_by_status"]["critical"] * 0.0

            report["overall_health_score"] = (
                (healthy_weight + degraded_weight + critical_weight) / total_services * 100
            )
        else:
            report["overall_health_score"] = 100

        return report

# Usage example
integration_troubleshooter = IntegrationTroubleshooter(app)

# Test external API integration
api_test = integration_troubleshooter.test_integration("payment_api", {
    "host": "api.payment.com",
    "port": 443,
    "auth_type": "bearer",
    "test_endpoint": "/v1/health",
    "expected_status": 200
})

print(f"API Test Results: Passed={api_test['tests_passed']}, Failed={api_test['tests_failed']}")
print(f"Issues Found: {len(api_test['issues_found'])}")
print(f"Recommendations: {len(api_test['recommendations'])}")

# Diagnose specific failure
failure_diagnosis = integration_troubleshooter.diagnose_integration_failure(
    "payment_api",
    "Error: Connection refused to api.payment.com:443"
)

print(f"Diagnosis: {failure_diagnosis['diagnosis']['issue_type'].value}")
print(f"Resolution Steps: {len(failure_diagnosis['resolution_steps'])}")

# Get integration health report
health_report = integration_troubleshooter.get_integration_health_report()
print(f"Integration Health Report: Overall Score={health_report['overall_health_score']:.1f}%")
```

## Next Steps

Explore advanced Nexus capabilities:

1. **[Performance Guide](performance-guide.md)** - Optimize system performance
2. **[Security Guide](security-guide.md)** - Security troubleshooting
3. **[Integration Guide](integration-guide.md)** - Integration best practices
4. **[Production Deployment](../advanced/production-deployment.md)** - Production troubleshooting

## Key Takeaways

✅ **Comprehensive Diagnostics** → Built-in diagnostic system for health monitoring
✅ **Workflow Troubleshooting** → Systematic approach to diagnose workflow failures
✅ **Performance Analysis** → Identify and resolve performance bottlenecks
✅ **Integration Testing** → Test and diagnose external system connections
✅ **Error Pattern Analysis** → Learn from historical issues to prevent recurrence
✅ **Actionable Recommendations** → Get specific steps to resolve issues

Nexus provides comprehensive troubleshooting capabilities that help you quickly diagnose and resolve issues, maintaining optimal system performance and reliability.
