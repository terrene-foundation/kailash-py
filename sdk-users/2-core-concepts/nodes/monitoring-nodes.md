# Monitoring Nodes - Comprehensive Guide

Enterprise-grade transaction monitoring, deadlock detection, race condition analysis, and performance anomaly detection.

## 🚀 What's New in v0.6.6+

- **Enhanced Operations**: New `complete_transaction`, `acquire_resource`, `release_resource`, `request_resource`, `complete_operation`, and `initialize` operations
- **Success Rate Calculations**: Automatic success rate calculation in TransactionMetricsNode output
- **Alias Support**: Multiple operation names for better API compatibility
- **Schema Compliance**: Enhanced output schemas with new fields like `total_transactions`, `trace_data`, `span_data`
- **Async Performance**: Improved AsyncNode base class with proper event loop handling

## 🎯 Quick Node Selection

| Need | Use This Node | Key Features |
|------|---------------|--------------|
| **Transaction Metrics** | `TransactionMetricsNode` | Timing, success rates, latency percentiles |
| **Real-time Monitoring** | `TransactionMonitorNode` | Live tracing, alerting, distributed tracing |
| **Deadlock Detection** | `DeadlockDetectorNode` | Wait-for graphs, victim selection, prevention |
| **Race Conditions** | `RaceConditionDetectorNode` | Concurrent access analysis, confidence scoring |
| **Performance Anomalies** | `PerformanceAnomalyNode` | Statistical baselines, ML detection, alerting |

## TransactionMetricsNode

**Purpose**: Collect and aggregate transaction performance metrics with enterprise export formats.

### Core Operations

```python
from kailash.nodes.monitoring import TransactionMetricsNode

metrics = TransactionMetricsNode()

# Start transaction tracking
result = metrics.execute(
    operation="start_transaction",
    transaction_id="txn_001",
    name="order_processing",
    tags={"service": "orders", "region": "us-west"}
)

# End transaction with metrics (can also use complete_transaction)
result = metrics.execute(
    operation="end_transaction",  # or "complete_transaction"
    transaction_id="txn_001",
    status="success",  # or "failed"
    custom_metrics={"items_processed": 5, "db_queries": 3}
)

# Alternative: Complete transaction with boolean success
result = metrics.execute(
    operation="complete_transaction",  # New v0.6.6+
    transaction_id="txn_001",
    success=True  # Boolean parameter
)

# Get aggregated metrics
result = metrics.execute(
    operation="get_metrics",
    include_raw=True,
    export_format="json"
)
print(f"Success rate: {result['success_rate']}")  # New field
print(f"Total transactions: {result['total_transactions']}")  # New alias

# Get aggregated data with percentiles
result = metrics.execute(
    operation="get_aggregated",
    metric_names=["order_processing"],
    aggregation_window=60.0,
    aggregation_types=["count", "avg", "p50", "p95", "p99"]
)
```

### Export Formats

```python
# Prometheus format
result = metrics.execute(
    operation="get_metrics",
    export_format="prometheus"
)

# CloudWatch format
result = metrics.execute(
    operation="get_metrics",
    export_format="cloudwatch"
)

# DataDog format
result = metrics.execute(
    operation="get_metrics",
    export_format="datadog"
)

# OpenTelemetry format
result = metrics.execute(
    operation="get_metrics",
    export_format="opentelemetry"
)
```

## TransactionMonitorNode

**Purpose**: Real-time transaction monitoring with distributed tracing and alerting.

### Core Operations

```python
from kailash.nodes.monitoring import TransactionMonitorNode

monitor = TransactionMonitorNode()

# Start monitoring with thresholds
result = monitor.execute(
    operation="start_monitoring",
    monitoring_interval=1.0,
    alert_thresholds={
        "latency_ms": 1000,
        "error_rate": 0.05,
        "concurrent_transactions": 100
    }
)

# Create trace
result = monitor.execute(
    operation="create_trace",
    trace_id="trace_001",
    operation_name="user_registration",
    metadata={"user_id": "user123", "source": "web"}
)

# Add span to trace
result = monitor.execute(
    operation="add_span",
    trace_id="trace_001",
    span_id="db_span",
    operation_name="database_query",
    start_time=time.time()
)

# Finish span
result = monitor.execute(
    operation="finish_span",
    trace_id="trace_001",
    span_id="db_span",
    success=True
)

# Get trace data
result = monitor.execute(
    operation="get_trace",
    trace_id="trace_001"
)

# Get alerts
result = monitor.execute(operation="get_alerts")

# Complete transaction monitoring (new v0.6.6+)
result = monitor.execute(
    operation="complete_transaction",
    transaction_id="txn_001",
    success=True
)
# New enhanced output fields
print(f"Correlation ID: {result['correlation_id']}")
print(f"Trace data: {result['trace_data']}")
print(f"Span data: {result['span_data']}")

# Correlate transactions
result = monitor.execute(
    operation="correlate_transactions",
    correlation_window=30.0
)

# Stop monitoring
result = monitor.execute(operation="stop_monitoring")
```

## DeadlockDetectorNode

**Purpose**: Detect and resolve database deadlocks using wait-for graph analysis.

### Core Operations

```python
from kailash.nodes.monitoring import DeadlockDetectorNode

detector = DeadlockDetectorNode()

# Initialize detector (new v0.6.6+)
result = detector.execute(
    operation="initialize",
    deadlock_timeout=30.0,
    cycle_detection_enabled=True
)

# Start monitoring
result = detector.execute(operation="start_monitoring")

# Register lock acquisition (multiple operation names available)
result = detector.execute(
    operation="register_lock",  # or "acquire_resource"
    transaction_id="txn_001",
    resource_id="table_users",
    lock_type="EXCLUSIVE"  # or "SHARED", "UPDATE"
)

# Request resource (simplified for E2E testing)
result = detector.execute(
    operation="request_resource",  # New v0.6.6+
    transaction_id="txn_002",
    resource_id="table_orders",
    resource_type="database_table",
    lock_type="SHARED"
)

# Register wait condition (creates deadlock potential)
result = detector.execute(
    operation="register_wait",
    transaction_id="txn_001",
    waiting_for_transaction_id="txn_002",
    resource_id="table_orders"
)

# Release lock (multiple operation names available)
result = detector.execute(
    operation="release_lock",  # or "release_resource"
    transaction_id="txn_001",
    resource_id="table_users"
)

# Detect deadlocks
result = detector.execute(
    operation="detect_deadlocks",
    detection_algorithm="wait_for_graph"  # or "timeout_based", "combined"
)

# Resolve deadlock
if result["deadlocks_detected"] > 0:
    for deadlock in result["deadlocks"]:
        detector.execute(
            operation="resolve_deadlock",
            deadlock_id=deadlock["deadlock_id"],
            resolution_strategy="victim_selection"  # or "timeout_rollback"
        )

# Get status
result = detector.execute(operation="get_status")

# Stop monitoring
result = detector.execute(operation="stop_monitoring")
```

## RaceConditionDetectorNode

**Purpose**: Detect race conditions in concurrent resource access patterns.

### Core Operations

```python
from kailash.nodes.monitoring import RaceConditionDetectorNode

detector = RaceConditionDetectorNode()

# Start monitoring
result = detector.execute(operation="start_monitoring")

# Register resource access
result = detector.execute(
    operation="register_access",
    access_id="access_001",
    resource_id="shared_counter",
    access_type="read_write",  # or "read", "write", "delete", "create"
    thread_id="thread_1"
)

# Register operation (alternative to access)
result = detector.execute(
    operation="register_operation",
    operation_id="op_001",
    resource_id="shared_data",
    operation_type="concurrent_update",
    thread_id="worker_thread"
)

# End access
result = detector.execute(
    operation="end_access",
    access_id="access_001"
)

# End operation
result = detector.execute(
    operation="end_operation",
    operation_id="op_001"
)

# Complete operation with final analysis (new v0.6.6+)
result = detector.execute(
    operation="complete_operation",
    operation_id="op_001",
    resource_id="shared_data",
    success=True
)
print(f"Race conditions detected: {result['race_count']}")
print(f"Operation status: {result['monitoring_status']}")

# Detect race conditions
result = detector.execute(operation="detect_races")

# Get status
result = detector.execute(operation="get_status")

# Stop monitoring
result = detector.execute(operation="stop_monitoring")
```

## PerformanceAnomalyNode

**Purpose**: Detect performance anomalies using statistical baselines and ML techniques.

### Core Operations

```python
from kailash.nodes.monitoring import PerformanceAnomalyNode

detector = PerformanceAnomalyNode()

# Initialize baseline for metric
result = detector.execute(
    operation="initialize_baseline",
    metric_name="api_response_time",
    sensitivity=0.8,  # Higher = more sensitive
    min_samples=30,   # Minimum samples before detection
    detection_window=300  # 5-minute detection window
)

# Add metric data point
result = detector.execute(
    operation="add_metric",
    metric_name="api_response_time",
    value=150.5,
    tags={"endpoint": "/api/users", "method": "GET"},
    metadata={"request_id": "req_123"}
)

# Detect anomalies
result = detector.execute(
    operation="detect_anomalies",
    metric_names=["api_response_time"],
    detection_methods=["statistical", "threshold_based", "iqr"]
)

# Get baseline information
result = detector.execute(
    operation="get_baseline",
    metric_name="api_response_time"
)

# Get status
result = detector.execute(operation="get_status")
```

## Production Patterns

### Enterprise Monitoring Stack

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Build comprehensive monitoring workflow
workflow = WorkflowBuilder()

# Transaction metrics with enterprise settings
workflow.add_node("TransactionMetricsNode", "metrics", {
    "aggregation_window": 60,
    "retention_period": 86400,  # 24 hours
    "export_format": "prometheus",
    "custom_percentiles": [50, 75, 90, 95, 99, 99.9]
})

# Real-time monitoring with alerting
workflow.add_node("TransactionMonitorNode", "monitor", {
    "monitoring_interval": 1.0,
    "alert_thresholds": {
        "latency_ms": 1000,
        "error_rate": 0.05,
        "concurrent_transactions": 100
    },
    "enable_distributed_tracing": True
})

# Deadlock detection
workflow.add_node("DeadlockDetectorNode", "deadlock_detector", {
    "detection_interval": 5.0,
    "timeout_threshold": 30.0,
    "victim_selection": "youngest"
})

# Race condition detection
workflow.add_node("RaceConditionDetectorNode", "race_detector", {
    "detection_window": 10.0,
    "confidence_threshold": 0.8
})

# Performance anomaly detection
workflow.add_node("PerformanceAnomalyNode", "anomaly_detector", {
    "sensitivity": 0.8,
    "min_samples": 100,
    "detection_methods": ["statistical", "threshold_based", "iqr"]
})
```

### Database Operation Monitoring

```python
def monitored_database_operation(query, params, transaction_id):
    """Example of database operation with comprehensive monitoring."""

    # Initialize monitoring nodes
    metrics = TransactionMetricsNode()
    deadlock_detector = DeadlockDetectorNode()
    race_detector = RaceConditionDetectorNode()

    # Start monitoring
    deadlock_detector.execute(operation="start_monitoring")
    race_detector.execute(operation="start_monitoring")

    try:
        # Start transaction metrics
        metrics.execute(
            operation="start_transaction",
            transaction_id=transaction_id,
            name="database_operation",
            tags={"query_type": "select", "table": "users"}
        )

        # Register lock for deadlock detection
        deadlock_detector.execute(
            operation="register_lock",
            transaction_id=transaction_id,
            resource_id="table_users",
            lock_type="SHARED"
        )

        # Register access for race detection
        access_id = f"db_access_{transaction_id}"
        race_detector.execute(
            operation="register_access",
            access_id=access_id,
            resource_id="table_users",
            access_type="read"
        )

        # Execute database query
        from kailash.nodes.data import SQLDatabaseNode
        db = SQLDatabaseNode(connection_string="postgresql://...")
        result = db.execute(query=query, params=params)

        # End monitoring
        race_detector.execute(operation="end_access", access_id=access_id)
        deadlock_detector.execute(
            operation="release_lock",
            transaction_id=transaction_id,
            resource_id="table_users"
        )

        # Complete transaction metrics
        metrics.execute(
            operation="end_transaction",
            transaction_id=transaction_id,
            status="success",
            custom_metrics={"rows_returned": len(result.get("data", []))}
        )

        return result

    except Exception as e:
        # Handle failure
        metrics.execute(
            operation="end_transaction",
            transaction_id=transaction_id,
            status="failed",
            error=str(e)
        )
        raise
    finally:
        # Cleanup monitoring
        deadlock_detector.execute(operation="stop_monitoring")
        race_detector.execute(operation="stop_monitoring")
```

### Performance Monitoring Dashboard

```python
def create_monitoring_dashboard():
    """Create real-time monitoring dashboard workflow."""

    workflow = WorkflowBuilder()

    # Metrics collection
    workflow.add_node("TransactionMetricsNode", "metrics_collector", {
        "operation": "get_metrics",
        "metric_types": ["latency", "throughput", "success_rate"],
        "time_range": 300
    })

    # Performance anomaly analysis
    workflow.add_node("PerformanceAnomalyNode", "anomaly_analyzer", {
        "operation": "detect_anomalies",
        "metric_names": ["api_latency", "cpu_usage", "memory_usage"],
        "detection_methods": ["statistical", "threshold_based"]
    })

    # Real-time status
    workflow.add_node("TransactionMonitorNode", "status_monitor", {
        "operation": "get_monitoring_status"
    })

    # Dashboard aggregation
    workflow.add_node("PythonCodeNode", "dashboard_builder", {
        "code": """
# Aggregate monitoring data for dashboard
dashboard_data = {
    "timestamp": datetime.now().isoformat(),
    "metrics": {
        "total_transactions": metrics_data.get("transaction_count", 0),
        "active_transactions": status_data.get("active_count", 0),
        "avg_latency": metrics_data.get("latency", {}).get("mean", 0),
        "p95_latency": metrics_data.get("latency", {}).get("p95", 0),
        "error_rate": metrics_data.get("error_rate", 0.0),
        "success_rate": metrics_data.get("success_rate", 1.0)
    },
    "anomalies": {
        "count": anomaly_data.get("anomaly_count", 0),
        "critical": len([a for a in anomaly_data.get("anomalies_detected", [])
                        if a.get("severity") == "critical"])
    },
    "status": "healthy" if metrics_data.get("error_rate", 0) < 0.05 else "degraded"
}

result = dashboard_data
"""
    })

    # Connect dashboard workflow
    workflow.add_connection("metrics_collector", "metrics", "dashboard_builder", "metrics_data")
    workflow.add_connection("anomaly_analyzer", "anomalies", "dashboard_builder", "anomaly_data")
    workflow.add_connection("status_monitor", "status", "dashboard_builder", "status_data")

    return workflow
```

## Testing Patterns

### Unit Testing

```python
def test_transaction_lifecycle():
    """Test complete transaction lifecycle."""
    metrics = TransactionMetricsNode()

    # Start transaction
    result = metrics.execute(
        operation="start_transaction",
        transaction_id="test_001",
        name="test_operation"
    )
    assert result["status"] == "success"

    # End transaction
    result = metrics.execute(
        operation="end_transaction",
        transaction_id="test_001",
        status="success"
    )
    assert result["status"] == "success"

    # Verify metrics
    result = metrics.execute(operation="get_metrics")
    assert result["transaction_count"] >= 1
```

### Integration Testing with Docker

```python
def test_monitoring_integration():
    """Test monitoring with real infrastructure."""

    # Requires Docker test environment
    # ./tests/utils/test-env up

    metrics = TransactionMetricsNode()
    monitor = TransactionMonitorNode()

    # Start monitoring
    monitor.execute(operation="start_monitoring")

    # Process transactions
    for i in range(10):
        txn_id = f"integration_test_{i}"

        # Start transaction
        metrics.execute(
            operation="start_transaction",
            transaction_id=txn_id,
            name="integration_test"
        )

        # Create trace
        monitor.execute(
            operation="create_trace",
            trace_id=f"trace_{txn_id}",
            operation_name="integration_test"
        )

        # Simulate processing
        time.sleep(0.1)

        # Complete
        success = i % 5 != 0  # 80% success rate
        status = "success" if success else "failed"

        metrics.execute(
            operation="end_transaction",
            transaction_id=txn_id,
            status=status
        )

    # Verify results
    result = metrics.execute(operation="get_metrics")
    assert result["transaction_count"] == 10
    assert 0.7 <= result["success_rate"] <= 0.9

    # Cleanup
    monitor.execute(operation="stop_monitoring")
```

## Configuration Reference

### Production Configuration

```python
# High-volume production settings
PRODUCTION_CONFIG = {
    "TransactionMetricsNode": {
        "aggregation_window": 60,     # 1-minute aggregation
        "retention_period": 86400,    # 24-hour retention
        "export_interval": 30,        # Export every 30 seconds
        "export_format": "prometheus",
        "custom_percentiles": [50, 75, 90, 95, 99, 99.9],
        "max_transactions": 100000    # Memory limit
    },
    "TransactionMonitorNode": {
        "monitoring_interval": 0.5,   # 500ms checks
        "alert_thresholds": {
            "latency_ms": 500,         # Alert on >500ms
            "error_rate": 0.01,        # Alert on >1% errors
            "concurrent_transactions": 1000,
            "queue_depth": 100
        },
        "enable_distributed_tracing": True,
        "tracing_sample_rate": 0.1    # Sample 10%
    },
    "DeadlockDetectorNode": {
        "detection_interval": 1.0,    # Check every second
        "timeout_threshold": 10.0,    # Faster deadlock detection
        "victim_selection": "youngest",
        "enable_prevention": True,
        "max_wait_graph_size": 10000
    },
    "PerformanceAnomalyNode": {
        "sensitivity": 0.9,           # High sensitivity
        "min_samples": 50,            # Fast baseline establishment
        "detection_window": 60,       # 1-minute windows
        "detection_methods": ["statistical", "threshold_based", "iqr"]
    }
}
```

## Best Practices

1. **Layer Monitoring**: Use multiple monitoring nodes together for comprehensive coverage
2. **Set Realistic Thresholds**: Base alert thresholds on historical performance data
3. **Monitor the Monitors**: Ensure monitoring nodes don't become performance bottlenecks
4. **Test Failure Scenarios**: Regularly test deadlock and race condition handling in staging
5. **Use Appropriate Sampling**: Don't trace every transaction in high-volume systems
6. **Regular Baseline Updates**: Keep performance baselines current with system changes

## Troubleshooting

### Common Issues

**TransactionMetricsNode**:
- Use `end_transaction`, not `complete_transaction`
- Use `status="success"/"failed"`, not `success=True/False`

**DeadlockDetectorNode**:
- Use `start_monitoring`, not `initialize`
- `register_wait` requires `waiting_for_transaction_id`

**RaceConditionDetectorNode**:
- Use `register_access`/`end_access`, not `report_operation`/`complete_operation`
- Use lowercase access types: `"read_write"`, not `"READ_WRITE"`

### Performance Optimization

- Limit monitoring overhead to <5% of total system resources
- Use sampling for high-volume transaction monitoring
- Set appropriate retention periods based on storage capacity
- Configure alert thresholds to minimize false positives

## See Also

- [Transaction Monitoring Cheatsheet](../cheatsheet/048-transaction-monitoring.md)
- [Enterprise Production Patterns](../enterprise/production-patterns.md)
- [Resilience Patterns](../cheatsheet/046-resilience-patterns.md)
- [Testing Framework](../developer/12-testing-production-quality.md)
