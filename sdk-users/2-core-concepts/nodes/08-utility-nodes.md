# Utility Nodes

**Modules**: Various utility modules for visualization, security, and performance tracking
**Last Updated**: 2025-07-05

This document covers utility nodes that provide support functionality including visualization, security, tracking, and performance monitoring features.

## Overview

Utility nodes extend the Kailash SDK with essential support capabilities:
- **Visualization**: Workflow diagrams, real-time dashboards, performance reports
- **Security**: Input validation, secure file operations, audit logging
- **Performance**: Monitoring, profiling, metrics collection
- **Tracking**: State management, execution tracking, debugging support

## Table of Contents
- [Visualization Nodes](#visualization-nodes)
- [Security Nodes](#security-nodes)
- [Performance Nodes](#performance-nodes)
- [Integration Examples](#integration-examples)
- [Best Practices](#best-practices)

## Visualization Nodes

### WorkflowVisualizerNode

Generate workflow visualizations and diagrams for documentation and debugging.

```python
from kailash.nodes.visualization import WorkflowVisualizerNode
from kailash.workflow.builder import WorkflowBuilder

# Create workflow visualizer
visualizer = WorkflowVisualizerNode(
    name="workflow_visualizer",
    output_format="svg",  # svg, png, mermaid
    include_parameters=True,
    include_connections=True,
    theme="default"  # default, dark, light
)

# Example workflow to visualize
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("FilterNode", "filter", {"condition": "value > 100"})
workflow.add_node("JSONWriterNode", "writer", {"file_path": "output.json"})
workflow.add_connection("reader", "filter", "data", "input_data")
workflow.add_connection("filter", "writer", "filtered_data", "data")

# Generate visualization
result = await visualizer.run(
    workflow=workflow,
    output_path="workflow_diagram.svg",
    title="Data Processing Workflow"
)

print(f"Visualization saved to: {result['output_path']}")
```

**Features:**
- Multiple output formats (SVG, PNG, Mermaid)
- Interactive diagrams with clickable nodes
- Customizable themes and styling
- Parameter and connection visualization
- Export to documentation formats

### RealTimeDashboardNode

Create real-time monitoring dashboards with WebSocket streaming.

```python
from kailash.nodes.visualization.dashboard import RealTimeDashboardNode
from kailash.tracking.metrics_collector import MetricsCollector

# Create dashboard node
dashboard = RealTimeDashboardNode(
    name="monitoring_dashboard",
    port=8080,
    enable_websockets=True,
    update_interval=5.0,  # seconds
    max_connections=100
)

# Configure dashboard panels
dashboard_config = {
    "title": "Kailash Workflow Monitor",
    "panels": [
        {
            "id": "metrics_panel",
            "type": "line_chart",
            "title": "Performance Metrics",
            "metrics": ["cpu_usage", "memory_usage", "task_completion_rate"],
            "refresh_interval": 5
        },
        {
            "id": "status_panel",
            "type": "status_grid",
            "title": "Node Status",
            "show_health": True,
            "show_errors": True
        },
        {
            "id": "logs_panel",
            "type": "log_viewer",
            "title": "Recent Logs",
            "max_entries": 50,
            "auto_scroll": True
        }
    ]
}

# Start dashboard
result = await dashboard.run(
    config=dashboard_config,
    metrics_source=MetricsCollector(),
    enable_export=True
)

print(f"Dashboard running at: http://localhost:{result['port']}")
```

**Features:**
- Real-time WebSocket updates
- Customizable panel layouts
- Chart.js integration for visualizations
- Log streaming and filtering
- Metric aggregation and alerting
- Export capabilities (PDF, PNG)

### PerformanceReporterNode

Generate comprehensive performance reports with detailed analytics.

```python
from kailash.nodes.visualization.reports import PerformanceReporterNode
from kailash.tracking.performance_tracker import PerformanceTracker

# Create performance reporter
reporter = PerformanceReporterNode(
    name="performance_reporter",
    output_format="html",  # html, markdown, json, pdf
    include_charts=True,
    include_recommendations=True
)

# Configure report sections
report_config = {
    "title": "Workflow Performance Analysis",
    "time_period": "last_24h",
    "sections": [
        "executive_summary",
        "performance_metrics",
        "bottleneck_analysis",
        "resource_utilization",
        "error_analysis",
        "optimization_recommendations"
    ],
    "chart_types": ["line", "bar", "heatmap", "pie"],
    "export_data": True
}

# Generate report
result = await reporter.run(
    config=report_config,
    data_source=PerformanceTracker(),
    output_path="performance_report.html",
    include_raw_data=True
)

print(f"Report generated: {result['report_path']}")
print(f"Performance score: {result['overall_score']}")
```

**Features:**
- Multiple output formats (HTML, PDF, Markdown)
- Interactive charts and graphs
- Automated bottleneck detection
- Performance optimization recommendations
- Executive summary generation
- Raw data export capabilities

## Security Nodes

### SecureFileNode

Secure file operations with comprehensive validation and safety checks.

```python
from kailash.nodes.security import SecureFileNode
from pathlib import Path

# Create secure file node
secure_file = SecureFileNode(
    name="secure_file_handler",
    allowed_paths=["/safe/data/", "/tmp/uploads/"],
    allowed_extensions=[".txt", ".csv", ".json", ".pdf"],
    max_file_size_mb=100,
    enable_virus_scan=True,
    enable_audit_log=True
)

# Safe file operations
result = await secure_file.run(
    operation="read",
    file_path="/safe/data/input.csv",
    validate_content=True,
    sanitize_output=True
)

# Write with validation
write_result = await secure_file.run(
    operation="write",
    file_path="/safe/data/output.json",
    content={"processed": True, "timestamp": "2024-01-15T10:30:00Z"},
    backup_original=True,
    verify_write=True
)

print(f"File operations completed safely: {result['success']}")
```

**Features:**
- Path traversal prevention
- File type validation
- Size limit enforcement
- Virus scanning integration
- Content sanitization
- Audit logging for compliance
- Backup and recovery support

### SecurityValidatorNode

Input validation and security scanning for workflow data.

```python
from kailash.nodes.security import SecurityValidatorNode

# Create security validator
validator = SecurityValidatorNode(
    name="security_validator",
    enable_xss_protection=True,
    enable_sql_injection_check=True,
    enable_command_injection_check=True,
    max_input_length=10000,
    blocked_patterns=["<script>", "DROP TABLE", "rm -rf"]
)

# Validate input data
validation_result = await validator.run(
    data={
        "user_input": "John Doe",
        "query": "SELECT * FROM users WHERE id = 123",
        "file_path": "../safe/data/file.txt"
    },
    strict_mode=True,
    log_violations=True
)

if validation_result["is_safe"]:
    print("Input validation passed")
else:
    print(f"Security violations found: {validation_result['violations']}")
```

**Features:**
- XSS attack prevention
- SQL injection detection
- Command injection protection
- Input sanitization
- Pattern-based filtering
- Configurable security levels
- Detailed violation reporting

## Performance Nodes

### MetricsCollectorNode

Comprehensive metrics collection and performance monitoring.

```python
from kailash.nodes.performance import MetricsCollectorNode
from kailash.nodes.performance.exporters import PrometheusExporter

# Create metrics collector
metrics = MetricsCollectorNode(
    name="metrics_collector",
    collection_interval=30.0,  # seconds
    enable_system_metrics=True,
    enable_workflow_metrics=True,
    enable_custom_metrics=True
)

# Configure exporters
prometheus_exporter = PrometheusExporter(
    port=9090,
    metrics_path="/metrics"
)

# Collect and export metrics
result = await metrics.run(
    collectors=["cpu", "memory", "disk", "network", "workflow"],
    exporters=[prometheus_exporter],
    aggregation_window="5m",
    enable_alerting=True
)

print(f"Metrics collected: {result['metrics_count']}")
print(f"Export endpoint: http://localhost:9090/metrics")
```

**Features:**
- System resource monitoring
- Workflow performance tracking
- Custom metric collection
- Multiple export formats (Prometheus, InfluxDB, JSON)
- Real-time alerting
- Historical data retention
- Automated aggregation

## Integration Examples

### Complete Monitoring Stack

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.visualization import RealTimeDashboardNode, PerformanceReporterNode
from kailash.nodes.security import SecureFileNode
from kailash.nodes.performance import MetricsCollectorNode

# Create monitoring workflow
monitoring_workflow = WorkflowBuilder()

# Add utility nodes
monitoring_workflow.add_node("MetricsCollectorNode", "metrics", {
    "collection_interval": 30.0,
    "enable_system_metrics": True
})

monitoring_workflow.add_node("RealTimeDashboardNode", "dashboard", {
    "port": 8080,
    "update_interval": 5.0
})

monitoring_workflow.add_node("PerformanceReporterNode", "reporter", {
    "output_format": "html",
    "schedule": "daily"
})

monitoring_workflow.add_node("SecureFileNode", "secure_storage", {
    "allowed_paths": ["/safe/reports/"],
    "enable_audit_log": True
})

# Connect monitoring pipeline
monitoring_workflow.add_connection("metrics", "dashboard", "metrics_data", "live_metrics")
monitoring_workflow.add_connection("metrics", "reporter", "metrics_data", "performance_data")
monitoring_workflow.add_connection("reporter", "secure_storage", "report_path", "file_path")

# Execute monitoring
result = await monitoring_runtime.execute(workflow.build(), {
    "metrics": {"start_collection": True},
    "dashboard": {"start_server": True},
    "reporter": {"generate_report": True}
})

print("Complete monitoring stack deployed successfully")
```

### Security-First Data Processing

```python
# Secure data processing pipeline
secure_pipeline = WorkflowBuilder()

# Add security validation
secure_pipeline.add_node("SecurityValidatorNode", "validator", {
    "strict_mode": True,
    "enable_all_checks": True
})

secure_pipeline.add_node("SecureFileNode", "secure_reader", {
    "operation": "read",
    "validate_content": True
})

secure_pipeline.add_node("SecureFileNode", "secure_writer", {
    "operation": "write",
    "backup_original": True
})

# Add monitoring
secure_pipeline.add_node("MetricsCollectorNode", "security_metrics", {
    "focus": "security_events"
})

# Connect secure pipeline
secure_pipeline.add_connection("validator", "secure_reader", "validated_input", "file_path")
secure_pipeline.add_connection("secure_reader", "secure_writer", "file_content", "content")
secure_pipeline.add_connection("validator", "security_metrics", "security_events", "events")

print("Secure processing pipeline configured")
```

## Best Practices

### 1. Visualization Strategy

```python
# Effective visualization configuration
visualization_best_practices = {
    "choose_right_format": {
        "svg": "Interactive diagrams, web embedding",
        "png": "Documentation, presentations",
        "mermaid": "Code documentation, GitHub"
    },

    "dashboard_optimization": {
        "update_frequency": "Balance real-time vs performance",
        "panel_count": "Maximum 6-8 panels per view",
        "data_retention": "Keep 24-48 hours for dashboards"
    },

    "report_scheduling": {
        "daily": "Operations teams",
        "weekly": "Management review",
        "monthly": "Strategic planning"
    }
}
```

### 2. Security Configuration

```python
# Security-first configuration
security_best_practices = {
    "file_operations": {
        "always_validate_paths": True,
        "use_allowlists": "Never rely on blocklists alone",
        "enable_auditing": "Log all file operations",
        "backup_strategy": "Before any destructive operations"
    },

    "input_validation": {
        "validate_early": "At workflow entry points",
        "sanitize_always": "Even trusted inputs",
        "log_violations": "For security monitoring",
        "fail_secure": "Reject on validation failure"
    }
}
```

### 3. Performance Monitoring

```python
# Performance monitoring strategy
monitoring_best_practices = {
    "metrics_collection": {
        "frequency": "30-60 seconds for system metrics",
        "retention": "1 hour detailed, 24 hours aggregated",
        "export_format": "Prometheus for production"
    },

    "alerting_thresholds": {
        "cpu_usage": "Warning: 70%, Critical: 90%",
        "memory_usage": "Warning: 80%, Critical: 95%",
        "response_time": "Warning: 1s, Critical: 5s"
    }
}
```

## See Also

- [Base Classes](01-base-nodes.md) - Core node abstractions
- [Security Patterns](../patterns/security-patterns.md) - Security implementation patterns
- [Monitoring Guide](../developer/monitoring-observability-guide.md) - Comprehensive monitoring setup
- [Performance Optimization](../developer/performance-optimization.md) - Performance tuning guide

---

**Utility nodes provide essential support capabilities for production Kailash workflows with security, monitoring, and visualization features.**
