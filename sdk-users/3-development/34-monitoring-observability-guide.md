# Monitoring and Observability Guide

*Comprehensive monitoring infrastructure with metrics, alerting, and real-time dashboards*

## Overview

The Kailash SDK provides enterprise-grade monitoring and observability capabilities including metrics collection, structured logging, distributed tracing, health checks, alerting systems, and real-time dashboards. This guide covers production monitoring patterns for maintaining system reliability and performance.

## Prerequisites

- Completed [Database Integration Guide](33-database-integration-guide.md)
- Understanding of monitoring and observability concepts
- Familiarity with metrics and alerting systems

## Core Monitoring Features

### MetricsCollector

Comprehensive metrics collection with performance tracking and analysis.

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.tracking.metrics_collector import MetricsCollector
from kailash.core.monitoring.connection_metrics import ConnectionMetricsCollector

# Initialize metrics collector
metrics_collector = MetricsCollector(
    name="application_metrics",

    # Collection configuration
    collection_interval=30.0,  # 30 seconds
    buffer_size=1000,
    enable_cpu_monitoring=True,
    enable_memory_monitoring=True,
    enable_io_monitoring=True,

    # Storage configuration
    storage_backend="prometheus",
    storage_config={
        "export_port": 9090,
        "metrics_path": "/metrics",
        "export_format": "prometheus"
    },

    # Aggregation settings
    enable_histograms=True,
    histogram_buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0],

    # Performance settings
    enable_async_collection=True,
    max_concurrent_collections=10
)

# Collect system metrics
async def collect_system_metrics():
    """Demonstrate comprehensive system metrics collection."""

    # Start metrics collection
    await metrics_collector.start()

    # Collect task execution metrics
    task_metrics = await metrics_collector.collect_task_metrics(
        task_id="data_processing_001",
        task_type="data_transformation",
        start_time=time.time()
    )

    # Simulate task execution
    await asyncio.sleep(2.0)  # Simulate 2-second task

    # Complete task metrics
    await metrics_collector.complete_task_metrics(
        task_id="data_processing_001",
        end_time=time.time(),
        success=True,
        output_size=1024*1024,  # 1MB output
        custom_metrics={
            "records_processed": 10000,
            "data_quality_score": 0.95,
            "transformation_accuracy": 0.98
        }
    )

    # Collect resource metrics
    resource_metrics = await metrics_collector.collect_resource_metrics()

    # Get aggregated metrics
    aggregated_metrics = await metrics_collector.get_aggregated_metrics(
        time_window="1h",
        include_percentiles=True
    )

    return {
        "task_metrics": task_metrics,
        "resource_metrics": resource_metrics,
        "aggregated_metrics": aggregated_metrics
    }

# Execute metrics collection
system_metrics = await collect_system_metrics()
```

### ConnectionMetricsCollector

Advanced database connection and query performance monitoring.

```python
from kailash.core.monitoring.connection_metrics import ConnectionMetricsCollector

# Initialize connection metrics collector
connection_metrics = ConnectionMetricsCollector(
    pool_name="production_database_pool",

    # Collection settings
    retention_minutes=60,
    detailed_query_metrics=True,
    enable_slow_query_detection=True,
    slow_query_threshold=1.0,  # 1 second

    # Export configuration
    export_format="prometheus",
    export_labels={
        "environment": "production",
        "service": "analytics_service",
        "version": "2.1.0"
    },

    # Alerting thresholds
    alert_thresholds={
        "connection_pool_utilization": 0.8,  # 80%
        "query_latency_p95": 2.0,            # 2 seconds
        "error_rate": 0.05                   # 5%
    }
)

# Monitor database connections
async def monitor_database_connections():
    """Demonstrate comprehensive database connection monitoring."""

    # Record connection acquisition
    await connection_metrics.record_connection_acquired(
        connection_id="conn_001",
        acquisition_time=0.05,  # 50ms
        pool_size=25,
        active_connections=12
    )

    # Record query execution
    await connection_metrics.record_query_execution(
        connection_id="conn_001",
        query_type="SELECT",
        execution_time=0.75,  # 750ms
        rows_affected=150,
        query_hash="hash_abc123",
        table_names=["users", "projects"]
    )

    # Record connection release
    await connection_metrics.record_connection_released(
        connection_id="conn_001",
        connection_lifetime=30.5,  # 30.5 seconds
        queries_executed=5
    )

    # Get connection pool metrics
    pool_metrics = await connection_metrics.get_pool_metrics()

    # Get query performance analysis
    query_analysis = await connection_metrics.get_query_performance_analysis(
        time_window="1h",
        include_slow_queries=True,
        group_by="table_name"
    )

    # Check alert conditions
    alerts = await connection_metrics.check_alert_conditions()

    return {
        "pool_metrics": pool_metrics,
        "query_analysis": query_analysis,
        "active_alerts": alerts
    }

# Execute connection monitoring
connection_monitor_result = await monitor_database_connections()
```

## Secure Logging Infrastructure

### SecureLogger

Advanced logging with automatic PII masking and security features.

```python
from kailash.utils.secure_logging import SecureLogger

# Initialize secure logger
secure_logger = SecureLogger(
    name="application_logger",

    # Logging configuration
    log_level="INFO",
    log_format="json",  # or "text"

    # Security settings
    enable_pii_masking=True,
    pii_patterns=[
        "credit_card",
        "ssn",
        "email",
        "phone",
        "api_key",
        "password"
    ],

    # Custom masking patterns
    custom_patterns={
        "employee_id": r"EMP\d{6}",
        "transaction_id": r"TXN[A-Z0-9]{8}",
        "internal_ip": r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    },

    # Masking configuration
    masking_char="*",
    preserve_length=True,
    show_first_chars=2,
    show_last_chars=2,

    # Output configuration
    outputs=[
        {
            "type": "file",
            "path": "/var/log/kailash/application.log",
            "rotation": "daily",
            "retention_days": 30
        },
        {
            "type": "elasticsearch",
            "url": "http://elasticsearch:9200",
            "index": "kailash-logs",
            "include_stack_traces": True
        },
        {
            "type": "prometheus",
            "export_log_metrics": True,
            "metrics_port": 9091
        }
    ]
)

# Secure logging examples
async def secure_logging_examples():
    """Demonstrate secure logging with PII protection."""

    # Log user activity (PII will be automatically masked)
    user_data = {
        "user_id": "user_123",
        "email": "john.doe@company.com",
        "phone": "+1-555-123-4567",
        "credit_card": "4532-1234-5678-9012",
        "ssn": "123-45-6789",
        "api_key": "sk_live_abcd1234efgh5678ijkl",
        "transaction_amount": 99.99
    }

    # This will automatically mask sensitive data
    secure_logger.info("User authentication successful", extra={
        "user_data": user_data,
        "event_type": "authentication",
        "timestamp": time.time()
    })

    # Log error with context
    try:
        # Simulate an error
        raise ValueError("Database connection failed")
    except Exception as e:
        secure_logger.error("Database operation failed", extra={
            "error": str(e),
            "user_id": "user_123",
            "operation": "user_data_fetch",
            "database_config": {
                "host": "db.internal.com",
                "password": "secret123",  # This will be masked
                "connection_string": "postgresql://user:secret123@db:5432/prod"  # Password masked
            }
        }, exc_info=True)

    # Log performance metrics
    secure_logger.info("Operation completed", extra={
        "metrics": {
            "execution_time": 1.25,
            "memory_usage_mb": 256,
            "records_processed": 10000,
            "cache_hit_rate": 0.85
        },
        "operation_type": "data_processing"
    })

    # Get logging statistics
    log_stats = await secure_logger.get_statistics()

    return {
        "logs_written": log_stats["total_logs"],
        "pii_items_masked": log_stats["pii_masked"],
        "security_events": log_stats["security_events"]
    }

# Execute secure logging
logging_result = await secure_logging_examples()
```

## Health Checks and System Monitoring

### HealthCheckNode

Comprehensive health monitoring for all system components.

```python
from kailash.nodes.api.monitoring import HealthCheckNode

# Initialize health check node
health_checker = HealthCheckNode(
    name="system_health_monitor",

    # Check configuration
    parallel_execution=True,
    default_timeout=10.0,
    retry_attempts=3,
    retry_delay=1.0,

    # Health check definitions
    health_checks=[
        {
            "name": "database_connectivity",
            "type": "database",
            "config": {
                "connection_string": "postgresql://user:pass@localhost:5432/db",
                "test_query": "SELECT 1",
                "timeout": 5.0
            },
            "critical": True
        },
        {
            "name": "redis_cache",
            "type": "redis",
            "config": {
                "host": "localhost",
                "port": 6379,
                "db": 0,
                "timeout": 3.0
            },
            "critical": False
        },
        {
            "name": "external_api",
            "type": "http",
            "config": {
                "url": "https://api.external-service.com/health",
                "method": "GET",
                "expected_status": 200,
                "timeout": 10.0,
                "headers": {"Authorization": "Bearer token"}
            },
            "critical": False
        },
        {
            "name": "disk_space",
            "type": "disk",
            "config": {
                "path": "/var/lib/data",
                "warning_threshold": 0.8,  # 80%
                "critical_threshold": 0.95  # 95%
            },
            "critical": True
        },
        {
            "name": "memory_usage",
            "type": "memory",
            "config": {
                "warning_threshold": 0.8,  # 80%
                "critical_threshold": 0.9   # 90%
            },
            "critical": True
        },
        {
            "name": "service_endpoint",
            "type": "tcp",
            "config": {
                "host": "internal-service",
                "port": 8080,
                "timeout": 5.0
            },
            "critical": False
        }
    ]
)

# Execute health checks
async def execute_health_checks():
    """Execute comprehensive health checks."""

    # Run all health checks
    health_result = await health_checker.run()

    # Analyze health status
    overall_health = health_result["overall_status"]
    critical_failures = [
        check for check in health_result["checks"]
        if check["critical"] and check["status"] != "healthy"
    ]

    # Get detailed health report
    health_report = {
        "overall_status": overall_health,
        "timestamp": time.time(),
        "total_checks": len(health_result["checks"]),
        "healthy_checks": len([c for c in health_result["checks"] if c["status"] == "healthy"]),
        "warning_checks": len([c for c in health_result["checks"] if c["status"] == "warning"]),
        "critical_checks": len([c for c in health_result["checks"] if c["status"] == "critical"]),
        "failed_checks": len([c for c in health_result["checks"] if c["status"] == "failed"]),
        "critical_failures": critical_failures,
        "response_times": {
            check["name"]: check.get("response_time", 0)
            for check in health_result["checks"]
        }
    }

    # Log health status
    if overall_health == "healthy":
        secure_logger.info("System health check passed", extra=health_report)
    elif overall_health == "warning":
        secure_logger.warning("System health check warnings detected", extra=health_report)
    else:
        secure_logger.error("System health check failures detected", extra=health_report)

    return health_report

# Execute health monitoring
health_status = await execute_health_checks()
```

## Performance Monitoring and Profiling

### PerformanceBenchmarkNode

Advanced performance monitoring with SLA tracking and optimization recommendations.

```python
from kailash.nodes.monitoring.performance_benchmark import PerformanceBenchmarkNode

# Initialize performance benchmark node
performance_monitor = PerformanceBenchmarkNode(
    name="performance_monitor",

    # Benchmark configuration
    benchmark_targets={
        "api_response_time": {
            "target": 200,  # 200ms
            "unit": "milliseconds",
            "tolerance": 0.1,  # 10%
            "critical_threshold": 1000  # 1 second
        },
        "database_query_time": {
            "target": 500,  # 500ms
            "unit": "milliseconds",
            "tolerance": 0.2,  # 20%
            "critical_threshold": 2000  # 2 seconds
        },
        "memory_usage": {
            "target": 512,  # 512MB
            "unit": "megabytes",
            "tolerance": 0.3,  # 30%
            "critical_threshold": 1024  # 1GB
        },
        "throughput": {
            "target": 1000,  # 1000 requests/minute
            "unit": "requests_per_minute",
            "tolerance": 0.15,  # 15%
            "critical_threshold": 500  # 500 req/min
        }
    },

    # SLA configuration
    sla_targets={
        "availability": 99.9,  # 99.9%
        "response_time_p95": 1000,  # 1 second
        "error_rate": 0.1  # 0.1%
    },

    # Monitoring settings
    measurement_window="5m",
    baseline_period="24h",
    enable_trend_analysis=True,
    enable_anomaly_detection=True,

    # Alerting configuration
    alert_channels=["email", "slack", "discord"],
    escalation_policy={
        "warning": {"delay": 300, "channels": ["slack"]},
        "critical": {"delay": 60, "channels": ["email", "slack", "discord"]}
    }
)

# Performance monitoring workflow
async def performance_monitoring_workflow():
    """Comprehensive performance monitoring workflow."""

    # Start performance baseline measurement
    baseline_result = await performance_monitor.run(
        operation="establish_baseline",
        measurement_duration=300,  # 5 minutes
        metrics_to_track=[
            "api_response_time",
            "database_query_time",
            "memory_usage",
            "throughput"
        ]
    )

    # Simulate application load
    await simulate_application_load()

    # Measure current performance
    current_performance = await performance_monitor.run(
        operation="measure_performance",
        benchmark_against="baseline",
        include_optimization_recommendations=True
    )

    # Analyze performance trends
    trend_analysis = await performance_monitor.run(
        operation="analyze_trends",
        time_window="24h",
        trend_types=["linear", "seasonal", "anomaly"],
        forecast_horizon="1h"
    )

    # Check SLA compliance
    sla_status = await performance_monitor.run(
        operation="check_sla_compliance",
        time_window="1h",
        include_business_impact=True
    )

    # Generate optimization recommendations
    optimization_report = await performance_monitor.run(
        operation="generate_optimization_report",
        include_cost_analysis=True,
        include_implementation_priority=True
    )

    return {
        "baseline_established": baseline_result["success"],
        "current_performance": current_performance["performance_score"],
        "sla_compliance": sla_status["compliance_percentage"],
        "optimization_opportunities": len(optimization_report["recommendations"]),
        "performance_trend": trend_analysis["overall_trend"],
        "business_impact": sla_status.get("business_impact", {})
    }

async def simulate_application_load():
    """Simulate application load for testing."""
    # This would contain actual application operations
    await asyncio.sleep(1)  # Placeholder

# Execute performance monitoring
performance_result = await performance_monitoring_workflow()
```

## Alerting and Notification Systems

### DiscordAlertNode

Advanced alerting with multiple channels and escalation policies.

```python
from kailash.nodes.alerts.discord import DiscordAlertNode
from kailash.nodes.alerts.base import AlertSeverity

# Initialize Discord alert node
discord_alerts = DiscordAlertNode(
    name="discord_alerting",
    webhook_url="https://discord.com/api/webhooks/your-webhook-url",

    # Alert configuration
    default_username="Kailash Monitor",
    default_avatar_url="https://example.com/kailash-logo.png",

    # Channel routing
    channel_routing={
        AlertSeverity.CRITICAL: "webhook_critical",
        AlertSeverity.ERROR: "webhook_errors",
        AlertSeverity.WARNING: "webhook_warnings",
        AlertSeverity.INFO: "webhook_general"
    },

    # Rate limiting
    rate_limit_per_minute=10,
    enable_alert_aggregation=True,
    aggregation_window=300,  # 5 minutes

    # Rich formatting
    enable_rich_embeds=True,
    include_context_data=True,
    max_embed_length=2000
)

# Alert management system
async def alert_management_system():
    """Demonstrate comprehensive alert management."""

    # Critical system alert
    await discord_alerts.run(
        severity=AlertSeverity.CRITICAL,
        title="Database Connection Lost",
        message="Primary database connection has been lost. Failing over to read replica.",
        context={
            "database": "production_primary",
            "connection_pool": "exhausted",
            "failed_attempts": 5,
            "last_successful_connection": "2024-01-15T14:30:00Z",
            "estimated_recovery_time": "2-5 minutes",
            "business_impact": "High - User operations affected"
        },
        tags=["database", "critical", "failover"],
        actions=[
            {"label": "View Logs", "url": "https://logs.company.com/database"},
            {"label": "Escalate", "url": "https://oncall.company.com/escalate"},
            {"label": "Status Page", "url": "https://status.company.com"}
        ]
    )

    # Performance degradation warning
    await discord_alerts.run(
        severity=AlertSeverity.WARNING,
        title="Performance Degradation Detected",
        message="API response times are 25% above baseline (target: 200ms, current: 250ms)",
        context={
            "metric": "api_response_time",
            "current_value": 250,
            "target_value": 200,
            "threshold_breach": "25%",
            "affected_endpoints": ["/api/users", "/api/projects", "/api/analytics"],
            "trend": "increasing",
            "duration": "15 minutes"
        },
        tags=["performance", "api", "degradation"]
    )

    # System recovery success
    await discord_alerts.run(
        severity=AlertSeverity.SUCCESS,
        title="System Recovery Complete",
        message="Database connection restored. All systems operating normally.",
        context={
            "recovery_time": "3 minutes 45 seconds",
            "affected_services": ["user_api", "analytics_service"],
            "performance_impact": "minimal",
            "root_cause": "network_connectivity_issue"
        },
        tags=["recovery", "database", "resolved"]
    )

    # Aggregate and send alert summary
    alert_summary = await discord_alerts.run(
        operation="send_summary",
        time_window="1h",
        include_trends=True,
        include_metrics=True
    )

    return {
        "alerts_sent": 3,
        "summary_generated": alert_summary["success"],
        "alert_channels_used": ["critical", "warnings", "general"]
    }

# Execute alert management
alert_result = await alert_management_system()
```

## Real-time Dashboards

### ConnectionDashboardNode

Web-based real-time monitoring dashboard with interactive visualizations.

```python
from kailash.nodes.monitoring.connection_dashboard import ConnectionDashboardNode

# Initialize connection dashboard
dashboard = ConnectionDashboardNode(
    name="realtime_dashboard",

    # Dashboard configuration
    dashboard_title="Kailash System Monitor",
    port=8080,
    enable_websocket_updates=True,
    update_interval=5.0,  # 5 seconds

    # Data sources
    data_sources=[
        {
            "name": "system_metrics",
            "type": "metrics_collector",
            "collector": metrics_collector
        },
        {
            "name": "connection_metrics",
            "type": "connection_metrics",
            "collector": connection_metrics
        },
        {
            "name": "health_status",
            "type": "health_checks",
            "checker": health_checker
        },
        {
            "name": "performance_data",
            "type": "performance_monitor",
            "monitor": performance_monitor
        }
    ],

    # Dashboard panels
    dashboard_panels=[
        {
            "id": "system_overview",
            "title": "System Overview",
            "type": "metrics_grid",
            "metrics": ["cpu_usage", "memory_usage", "disk_usage", "network_io"],
            "refresh_interval": 5
        },
        {
            "id": "database_performance",
            "title": "Database Performance",
            "type": "time_series_chart",
            "metrics": ["query_latency", "connection_pool_usage", "query_throughput"],
            "time_window": "1h"
        },
        {
            "id": "health_status",
            "title": "Service Health",
            "type": "status_grid",
            "services": ["database", "cache", "external_apis", "storage"],
            "show_response_times": True
        },
        {
            "id": "performance_trends",
            "title": "Performance Trends",
            "type": "trend_analysis",
            "metrics": ["api_response_time", "throughput", "error_rate"],
            "trend_window": "24h"
        },
        {
            "id": "alerts_summary",
            "title": "Recent Alerts",
            "type": "alert_feed",
            "max_alerts": 20,
            "filter_severity": ["WARNING", "ERROR", "CRITICAL"]
        }
    ],

    # Customization
    theme="dark",
    enable_fullscreen=True,
    enable_export=True,
    enable_alert_configuration=True
)

# Start monitoring dashboard
async def start_monitoring_dashboard():
    """Start comprehensive monitoring dashboard."""

    # Initialize dashboard
    dashboard_result = await dashboard.run(
        operation="start_dashboard",
        enable_auto_refresh=True,
        enable_alerting=True
    )

    # Configure alert thresholds via dashboard
    alert_config = {
        "cpu_usage": {"warning": 70, "critical": 90},
        "memory_usage": {"warning": 75, "critical": 85},
        "disk_usage": {"warning": 80, "critical": 95},
        "api_response_time": {"warning": 500, "critical": 1000},
        "error_rate": {"warning": 0.05, "critical": 0.1}
    }

    await dashboard.run(
        operation="configure_alerts",
        alert_thresholds=alert_config,
        notification_channels=["discord", "email"]
    )

    # Generate executive summary
    executive_summary = await dashboard.run(
        operation="generate_executive_summary",
        time_window="24h",
        include_business_metrics=True,
        include_recommendations=True
    )

    return {
        "dashboard_url": f"http://localhost:8080",
        "dashboard_started": dashboard_result["success"],
        "panels_active": len(dashboard_result["active_panels"]),
        "alert_rules_configured": len(alert_config),
        "executive_summary": executive_summary
    }

# Start the dashboard
dashboard_result = await start_monitoring_dashboard()
print(f"Dashboard available at: {dashboard_result['dashboard_url']}")
```

## Production Monitoring Integration

### Complete Monitoring Stack

```python
async def create_production_monitoring_stack():
    """Create a complete production monitoring stack."""

    # Initialize all monitoring components
    monitoring_stack = {
        "metrics": MetricsCollector(
            name="production_metrics",
            collection_interval=15.0,
            storage_backend="prometheus",
            enable_async_collection=True
        ),

        "connection_metrics": ConnectionMetricsCollector(
            pool_name="production_pool",
            retention_minutes=1440,  # 24 hours
            enable_slow_query_detection=True
        ),

        "secure_logger": SecureLogger(
            name="production_logger",
            enable_pii_masking=True,
            outputs=[
                {"type": "file", "path": "/var/log/kailash/app.log"},
                {"type": "elasticsearch", "url": "http://es:9200"}
            ]
        ),

        "health_checker": HealthCheckNode(
            name="production_health",
            parallel_execution=True,
            health_checks=production_health_checks
        ),

        "performance_monitor": PerformanceBenchmarkNode(
            name="production_performance",
            benchmark_targets=production_benchmarks,
            sla_targets=production_sla
        ),

        "alerting": DiscordAlertNode(
            name="production_alerts",
            webhook_url=os.getenv("DISCORD_WEBHOOK_URL"),
            enable_alert_aggregation=True
        ),

        "dashboard": ConnectionDashboardNode(
            name="production_dashboard",
            port=8080,
            enable_websocket_updates=True
        )
    }

    # Start all monitoring components
    for name, component in monitoring_stack.items():
        try:
            if hasattr(component, 'start'):
                await component.start()
            print(f"✅ {name} started successfully")
        except Exception as e:
            print(f"❌ Failed to start {name}: {e}")

    # Create monitoring workflow
    monitoring_workflow = WorkflowBuilder()

    # Add monitoring nodes
    monitoring_workflow.add_node("MetricsCollector", "metrics", {
        "collection_interval": 30.0,
        "enable_cpu_monitoring": True,
        "enable_memory_monitoring": True
    })

    monitoring_workflow.add_node("HealthCheckNode", "health", {
        "parallel_execution": True,
        "default_timeout": 10.0
    })

    monitoring_workflow.add_node("PerformanceBenchmarkNode", "performance", {
        "measurement_window": "5m",
        "enable_trend_analysis": True
    })

    # Connect monitoring pipeline
    monitoring_workflow.add_connection("metrics", "performance", "system_metrics", "baseline_metrics")
    monitoring_workflow.add_connection("health", "performance", "health_status", "system_health")

    # Execute monitoring workflow
    monitoring_result = await monitoring_runtime.execute(workflow.build(), {
        "metrics": {"operation": "collect"},
        "health": {"operation": "check_all"},
        "performance": {"operation": "benchmark"}
    })

    return {
        "monitoring_stack": monitoring_stack,
        "workflow_result": monitoring_result,
        "components_started": len(monitoring_stack),
        "dashboard_url": "http://localhost:8080"
    }

# Production monitoring patterns
production_health_checks = [
    {"name": "primary_db", "type": "database", "critical": True},
    {"name": "redis_cache", "type": "redis", "critical": False},
    {"name": "api_gateway", "type": "http", "critical": True},
    {"name": "message_queue", "type": "tcp", "critical": False}
]

production_benchmarks = {
    "api_response_time": {"target": 150, "tolerance": 0.2},
    "database_query_time": {"target": 300, "tolerance": 0.3},
    "throughput": {"target": 2000, "tolerance": 0.15}
}

production_sla = {
    "availability": 99.95,
    "response_time_p95": 800,
    "error_rate": 0.05
}

# Deploy production monitoring
production_monitoring = await create_production_monitoring_stack()
```

## Best Practices

### 1. Metrics Strategy

```python
# Comprehensive metrics strategy
def get_production_metrics_strategy():
    """Define production metrics collection strategy."""
    return {
        "infrastructure_metrics": {
            "cpu_usage": {"collection_interval": 15, "retention": "7d"},
            "memory_usage": {"collection_interval": 15, "retention": "7d"},
            "disk_usage": {"collection_interval": 60, "retention": "30d"},
            "network_io": {"collection_interval": 30, "retention": "7d"}
        },

        "application_metrics": {
            "request_latency": {"collection_interval": 1, "retention": "24h"},
            "error_rate": {"collection_interval": 5, "retention": "30d"},
            "throughput": {"collection_interval": 5, "retention": "30d"},
            "active_users": {"collection_interval": 60, "retention": "90d"}
        },

        "business_metrics": {
            "conversion_rate": {"collection_interval": 300, "retention": "1y"},
            "revenue_per_hour": {"collection_interval": 3600, "retention": "1y"},
            "customer_satisfaction": {"collection_interval": 3600, "retention": "1y"}
        }
    }
```

### 2. Alert Tuning

```python
# Smart alert configuration
def configure_intelligent_alerting():
    """Configure intelligent alerting with noise reduction."""
    return {
        "alert_policies": {
            "cpu_high": {
                "condition": "cpu_usage > 80%",
                "duration": "5m",
                "escalation": "warning -> critical after 10m"
            },
            "api_latency": {
                "condition": "p95_latency > 1000ms",
                "duration": "2m",
                "escalation": "immediate critical"
            }
        },

        "noise_reduction": {
            "enable_deduplication": True,
            "dedup_window": "5m",
            "enable_correlation": True,
            "correlation_window": "10m"
        },

        "escalation_policies": {
            "business_hours": {"channels": ["slack", "email"]},
            "after_hours": {"channels": ["pagerduty", "sms"]},
            "weekends": {"channels": ["pagerduty"]}
        }
    }
```

### 3. Dashboard Optimization

```python
# Dashboard performance optimization
def optimize_dashboard_performance():
    """Optimize dashboard for production performance."""
    return {
        "data_optimization": {
            "enable_data_sampling": True,
            "sample_rate": 0.1,  # 10% sampling for high-volume metrics
            "use_data_aggregation": True,
            "aggregation_window": "1m"
        },

        "rendering_optimization": {
            "enable_client_caching": True,
            "cache_duration": 30,  # 30 seconds
            "lazy_load_panels": True,
            "virtual_scrolling": True
        },

        "update_strategy": {
            "websocket_updates": True,
            "batch_updates": True,
            "update_throttling": 100  # max 100 updates/second
        }
    }
```

## Related Guides

**Prerequisites:**
- [Database Integration Guide](33-database-integration-guide.md) - Database patterns
- [MCP Node Development Guide](32-mcp-node-development-guide.md) - Custom MCP nodes

**Next Steps:**
- [Compliance and Governance Guide](35-compliance-governance-guide.md) - Compliance patterns

---

**Build comprehensive monitoring and observability with enterprise-grade dashboards and intelligent alerting!**
