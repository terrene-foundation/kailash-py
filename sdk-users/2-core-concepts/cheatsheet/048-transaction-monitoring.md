# Transaction Monitoring Cheatsheet

Quick reference for enterprise transaction monitoring: performance metrics, real-time monitoring, deadlock detection, race condition analysis, and performance anomaly detection.

## Transaction Metrics - Quick Start

```python
from kailash.nodes.monitoring import TransactionMetricsNode

# Basic metrics collection
metrics = TransactionMetricsNode()
result = metrics.execute(
    operation="start_transaction",
    transaction_id="txn_001",
    operation_type="database",
    metadata={"user_id": "user123", "endpoint": "/api/orders"}
)

# Complete transaction (can also use complete_transaction)
result = metrics.execute(
    operation="end_transaction",  # or "complete_transaction"
    transaction_id="txn_001",
    status="success"
)

# Get aggregated metrics
result = metrics.execute(
    operation="get_metrics",
    include_raw=True,
    export_format="json"
)
print(f"Success rate: {result['success_rate']}")
print(f"Total transactions: {result['total_transactions']}")
```

## Real-time Transaction Monitor - Quick Start

```python
from kailash.nodes.monitoring import TransactionMonitorNode

# Start monitoring
monitor = TransactionMonitorNode()
result = monitor.execute(
    operation="start_monitoring",
    monitoring_interval=1.0,  # Check every second
    alert_thresholds={
        "latency_ms": 1000,
        "error_rate": 0.05,
        "concurrent_transactions": 100
    }
)

# Create trace for monitoring
result = monitor.execute(
    operation="create_trace",
    trace_id="trace_002",
    operation_name="api_call",
    metadata={"endpoint": "/api/users", "method": "POST"}
)

# Get alerts
result = monitor.execute(operation="get_alerts")
print(f"Active alerts: {len(result.get('alerts', []))}")

# Get trace information
result = monitor.execute(operation="get_trace", trace_id="trace_002")
print(f"Trace status: {result.get('monitoring_status', 'unknown')}")
```

## Deadlock Detection - Quick Start

```python
from kailash.nodes.monitoring import DeadlockDetectorNode

# Initialize and start deadlock monitoring
detector = DeadlockDetectorNode()
result = detector.execute(operation="initialize")
result = detector.execute(operation="start_monitoring")

# Register lock acquisition (can also use acquire_resource)
result = detector.execute(
    operation="register_lock",  # or "acquire_resource"
    transaction_id="txn_003",
    resource_id="table_users",
    lock_type="EXCLUSIVE"
)

# Request a resource (simplified E2E testing operation)
result = detector.execute(
    operation="request_resource",
    transaction_id="txn_004",
    resource_id="table_orders",
    resource_type="database_table",
    lock_type="SHARED"
)

# Check for deadlocks
result = detector.execute(operation="detect_deadlocks")
if result["deadlocks_detected"]:
    for deadlock in result["deadlocks"]:
        print(f"Deadlock detected: {deadlock['deadlock_id']}")
        print(f"Victim: {deadlock['victim_transaction']}")
```

## Race Condition Detection - Quick Start

```python
from kailash.nodes.monitoring import RaceConditionDetectorNode

# Start race condition monitoring
detector = RaceConditionDetectorNode()
result = detector.execute(operation="start_monitoring")

# Register resource access or operation
result = detector.execute(
    operation="register_access",  # or "register_operation"
    access_id="access_001",       # or "operation_id" for register_operation
    resource_id="shared_counter",
    access_type="read_write",
    thread_id="thread_1"
)

# Complete an operation (finalize race detection analysis)
result = detector.execute(
    operation="complete_operation",
    operation_id="access_001",
    resource_id="shared_counter",
    success=True
)

# Detect race conditions
result = detector.execute(operation="detect_races")
for race in result["races_detected"]:
    print(f"Race condition: {race['race_type']}")
    print(f"Confidence: {race['confidence']}")
```

## Performance Anomaly Detection - Quick Start

```python
from kailash.nodes.monitoring import PerformanceAnomalyNode

# Initialize baseline learning
anomaly_detector = PerformanceAnomalyNode()
result = anomaly_detector.execute(
    operation="initialize_baseline",
    metric_name="api_response_time",
    sensitivity=0.8,
    min_samples=30
)

# Feed performance data
for response_time in [120, 115, 130, 125, 118]:  # Normal data
    result = anomaly_detector.execute(
        operation="add_metric",
        metric_name="api_response_time",
        value=response_time
    )

# Add anomalous data point
result = anomaly_detector.execute(
    operation="add_metric",
    metric_name="api_response_time",
    value=500  # Spike!
)

# Detect anomalies
result = anomaly_detector.execute(
    operation="detect_anomalies",
    metric_names=["api_response_time"],
    detection_methods=["statistical", "threshold_based"]
)
print(f"Anomalies found: {result['anomaly_count']}")
```

## Common Patterns

### Pattern 1: Complete Transaction Lifecycle

```python
from kailash.nodes.monitoring import TransactionMetricsNode, TransactionMonitorNode

# Setup monitoring
metrics = TransactionMetricsNode()
monitor = TransactionMonitorNode()

# Start monitoring
monitor.execute(operation="start_monitoring")

# Process transaction
txn_id = "order_processing_001"

# Start transaction
metrics.execute(
    operation="start_transaction",
    transaction_id=txn_id,
    operation_type="order_processing",
    metadata={"user_id": "user123", "order_value": 150.00}
)

# Create trace in real-time monitor
monitor.execute(
    operation="create_trace",
    trace_id=f"trace_{txn_id}",
    operation_name="order_processing",
    metadata={"user_id": "user123", "order_value": 150.00}
)

# ... business logic ...

# Complete transaction
metrics.execute(
    operation="end_transaction",
    transaction_id=txn_id,
    status="success",
    custom_metrics={"items_processed": 3, "payment_method": "credit_card"}
)

# Add and finish span in monitor
monitor.execute(
    operation="add_span",
    trace_id=f"trace_{txn_id}",
    span_id=f"span_{txn_id}",
    operation_name="order_processing"
)

monitor.execute(
    operation="finish_span",
    span_id=f"span_{txn_id}"
)
```

### Pattern 2: Database Operation Monitoring

```python
from kailash.nodes.monitoring import DeadlockDetectorNode, RaceConditionDetectorNode
from kailash.nodes.data import SQLDatabaseNode

# Setup detectors
deadlock_detector = DeadlockDetectorNode()
race_detector = RaceConditionDetectorNode()

# Start monitoring
deadlock_detector.execute(operation="start_monitoring")
race_detector.execute(operation="start_monitoring")

# Database operation with monitoring
def monitored_db_operation(query, params, txn_id):
    # Register lock acquisition
    deadlock_detector.execute(
        operation="register_lock",
        transaction_id=txn_id,
        resource_id="table_orders",
        lock_type="SHARED"
    )

    # Register resource access
    race_detector.execute(
        operation="register_access",
        access_id=f"db_access_{txn_id}",
        resource_id="table_orders",
        access_type="read",
        thread_id=str(threading.current_thread().ident)
    )

    # Execute query
    db_node = SQLDatabaseNode(connection_string="postgresql://...")
    result = db_node.execute(query=query, params=params)

    # End access and release lock
    race_detector.execute(
        operation="end_access",
        access_id=f"db_access_{txn_id}"
    )

    deadlock_detector.execute(
        operation="release_lock",
        transaction_id=txn_id,
        resource_id="table_orders"
    )

    return result
```

### Pattern 3: Performance Baseline with Monitoring

```python
from kailash.nodes.monitoring import PerformanceAnomalyNode, TransactionMetricsNode

# Setup
anomaly_detector = PerformanceAnomalyNode()
metrics = TransactionMetricsNode()

# Initialize baselines for different metrics
for metric in ["api_latency", "cpu_usage", "memory_usage"]:
    anomaly_detector.execute(
        operation="initialize_baseline",
        metric_name=metric,
        sensitivity=0.7,
        min_samples=50
    )

# Continuous monitoring function
def monitor_performance():
    # Get current metrics
    current_metrics = metrics.execute(
        operation="get_metrics",
        metric_types=["latency", "throughput"]
    )

    # Feed to anomaly detector
    for metric_name, value in current_metrics.items():
        anomaly_detector.execute(
            operation="add_metric",
            metric_name=metric_name,
            value=value
        )

    # Check for anomalies
    result = anomaly_detector.execute(
        operation="detect_anomalies",
        metric_names=list(current_metrics.keys()),
        detection_methods=["statistical", "iqr"]
    )

    # Handle anomalies
    if result["anomaly_count"] > 0:
        for anomaly in result["anomalies_detected"]:
            print(f"ALERT: {anomaly['anomaly_type']} detected")
            print(f"Metric: {anomaly['metric_name']}")
            print(f"Severity: {anomaly['severity']}")

            # Take action based on severity
            if anomaly["severity"] == "critical":
                # Emergency response
                trigger_emergency_protocol()
```

### Pattern 4: Workflow with Transaction Monitoring

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Build monitoring workflow
workflow = WorkflowBuilder()

# Start transaction metrics
workflow.add_node("TransactionMetricsNode", "metrics", {
    "operation": "start_transaction",
    "transaction_id": "workflow_001",
    "operation_type": "data_processing"
})

# Add business logic nodes
workflow.add_node("CSVReaderNode", "reader", {
    "file_path": "/data/input.csv"
})

workflow.add_node("LLMAgentNode", "processor", {
    "model": "gpt-4",
    "prompt": "Analyze this data for insights"
})

# Monitor for deadlocks during processing
workflow.add_node("DeadlockDetectorNode", "deadlock_monitor", {
    "operation": "start_monitoring"
})

# Complete transaction tracking
workflow.add_node("TransactionMetricsNode", "complete_metrics", {
    "operation": "end_transaction",
    "transaction_id": "workflow_001",
    "status": "success"
})

# Connect nodes
workflow.add_connection("metrics", "status", "reader", "start_signal")
workflow.add_connection("reader", "data", "processor", "input_data")
workflow.add_connection("processor", "result", "complete_metrics", "final_result")

# Execute with monitoring
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## New Operations & Enhancements (v0.6.6+)

### Enhanced Operation Support

```python
# TransactionMetricsNode - New complete_transaction operation
metrics = TransactionMetricsNode()
result = metrics.execute(
    operation="complete_transaction",  # Alias for end_transaction
    transaction_id="txn_123",
    success=True  # Boolean success parameter
)
print(f"Success rate: {result['success_rate']}")  # New field
print(f"Total transactions: {result['total_transactions']}")  # New alias field
```

### DeadlockDetectorNode - Enhanced Operations

```python
# New initialize operation
detector = DeadlockDetectorNode()
result = detector.execute(
    operation="initialize",
    deadlock_timeout=30.0,
    cycle_detection_enabled=True
)

# Acquire/release resource aliases
detector.execute(
    operation="acquire_resource",  # Alias for register_lock
    transaction_id="txn_123",
    resource_id="table_users",
    lock_type="exclusive"
)

detector.execute(
    operation="release_resource",  # Alias for release_lock
    transaction_id="txn_123",
    resource_id="table_users"
)

# Request resource for E2E scenarios
detector.execute(
    operation="request_resource",
    transaction_id="txn_456",
    resource_id="table_orders",
    resource_type="database_table",
    lock_type="SHARED"
)
```

### RaceConditionDetectorNode - Complete Operation Cycle

```python
detector = RaceConditionDetectorNode()

# Register operation
detector.execute(
    operation="register_operation",
    operation_id="op_123",
    resource_id="shared_resource",
    thread_id="thread_1"
)

# Complete operation with final analysis
result = detector.execute(
    operation="complete_operation",  # New operation
    operation_id="op_123",
    resource_id="shared_resource",
    success=True
)
print(f"Race conditions detected: {result['race_count']}")
print(f"Operation status: {result['monitoring_status']}")
```

### TransactionMonitorNode - Enhanced Tracing

```python
monitor = TransactionMonitorNode()

# Complete transaction with enhanced schema
result = monitor.execute(
    operation="complete_transaction",  # New operation
    transaction_id="monitor_test_123",
    success=True  # Boolean success parameter
)
# New fields in output
assert "trace_data" in result
assert "span_data" in result
assert "correlation_id" in result
```

## Configuration Reference

### Transaction Metrics Settings

```python
# Metric collection configuration
TransactionMetricsNode({
    "aggregation_window": 60,    # Seconds for metric aggregation
    "retention_period": 3600,    # How long to keep metrics
    "export_interval": 30,       # Export metrics every 30 seconds
    "export_format": "prometheus", # or "cloudwatch", "json"
    "custom_percentiles": [50, 75, 90, 95, 99]
})
```

### Monitoring Thresholds

```python
# Real-time monitoring thresholds
{
    "latency_ms": 1000,          # Alert on >1s latency
    "error_rate": 0.05,          # Alert on >5% error rate
    "concurrent_transactions": 100, # Alert on >100 concurrent
    "queue_depth": 50,           # Alert on >50 queued
    "memory_usage_mb": 1024,     # Alert on >1GB memory
    "cpu_usage_percent": 80      # Alert on >80% CPU
}
```

### Deadlock Detection Settings

```python
# Deadlock detector configuration
{
    "detection_interval": 5.0,    # Check every 5 seconds
    "timeout_threshold": 30.0,    # Consider deadlock after 30s
    "max_wait_graph_size": 1000,  # Limit graph size
    "victim_selection": "youngest", # or "oldest", "lowest_cost"
    "enable_prevention": True,    # Enable deadlock prevention
    "prevention_strategy": "wound_wait" # or "wait_die"
}
```

### Anomaly Detection Parameters

```python
# Performance anomaly detection
{
    "sensitivity": 0.8,           # Higher = more sensitive
    "min_samples": 30,           # Minimum samples for baseline
    "detection_window": 300,     # Analysis window (seconds)
    "zscore_threshold": 2.5,     # Z-score threshold for anomalies
    "learning_rate": 0.1,        # Baseline learning rate
    "decay_factor": 0.95,        # Historical data decay
    "enable_ml_detection": True   # Enable ML-based detection
}
```

## Error Handling

### Transaction Failures

```python
try:
    result = metrics.execute(
        operation="end_transaction",
        transaction_id=txn_id,
        status="failed",
        error="DB_TIMEOUT: Database operation timed out"
    )
except Exception as e:
    # Handle monitoring system failure
    logger.error(f"Transaction monitoring failed: {e}")
```

### Deadlock Resolution

```python
result = deadlock_detector.execute(operation="detect_deadlocks")
if result["deadlocks_detected"]:
    for deadlock in result["deadlocks"]:
        victim_txn = deadlock["victim_transaction"]

        # Automatically resolve deadlock
        deadlock_detector.execute(
            operation="resolve_deadlock",
            deadlock_id=deadlock["deadlock_id"],
            resolution_strategy="abort_victim"
        )

        # Retry victim transaction
        retry_transaction(victim_txn)
```

### Anomaly Response

```python
result = anomaly_detector.execute(operation="detect_anomalies")
for anomaly in result.get("anomalies_detected", []):
    severity = anomaly["severity"]

    if severity == "critical":
        # Immediate action required
        trigger_circuit_breaker(anomaly["metric_name"])
        send_alert(anomaly)
    elif severity == "high":
        # Schedule investigation
        schedule_investigation(anomaly)
    elif severity == "medium":
        # Log for analysis
        log_performance_issue(anomaly)
```

## Testing Patterns

### Test Transaction Metrics

```python
def test_transaction_lifecycle():
    metrics = TransactionMetricsNode()

    # Start transaction
    result = metrics.execute(
        operation="start_transaction",
        transaction_id="test_001"
    )
    assert result["status"] == "success"

    # Complete transaction
    result = metrics.execute(
        operation="end_transaction",
        transaction_id="test_001",
        status="success"
    )
    assert result["status"] == "success"

    # Verify metrics
    result = metrics.execute(operation="get_metrics")
    assert result["total_transactions"] == 1
    assert result["success_rate"] == 1.0
```

### Test Deadlock Detection

```python
def test_deadlock_scenario():
    detector = DeadlockDetectorNode()
    detector.execute(operation="start_monitoring")

    # Create potential deadlock scenario
    # Transaction 1 acquires A, waits for txn2
    detector.execute(
        operation="register_lock",
        transaction_id="txn1",
        resource_id="resource_A"
    )
    detector.execute(
        operation="register_wait",
        transaction_id="txn1",
        waiting_for_transaction_id="txn2",
        resource_id="resource_B"
    )

    # Transaction 2 acquires B, waits for txn1
    detector.execute(
        operation="register_lock",
        transaction_id="txn2",
        resource_id="resource_B"
    )
    detector.execute(
        operation="register_wait",
        transaction_id="txn2",
        waiting_for_transaction_id="txn1",
        resource_id="resource_A"
    )

    # Should detect deadlock
    result = detector.execute(operation="detect_deadlocks")
    assert result["deadlocks_detected"] > 0
```

### Test Anomaly Detection

```python
def test_performance_anomaly():
    detector = PerformanceAnomalyNode()

    # Initialize baseline
    detector.execute(
        operation="initialize_baseline",
        metric_name="test_metric"
    )

    # Add normal data
    for value in [100, 105, 95, 110, 90]:
        detector.execute(
            operation="add_metric",
            metric_name="test_metric",
            value=value
        )

    # Add anomalous data
    detector.execute(
        operation="add_metric",
        metric_name="test_metric",
        value=500  # Clear anomaly
    )

    # Should detect anomaly
    result = detector.execute(
        operation="detect_anomalies",
        metric_names=["test_metric"]
    )
    assert result["anomaly_count"] > 0
```

## Best Practices

1. **Layer monitoring** - Use multiple monitoring nodes together for comprehensive coverage
2. **Set appropriate thresholds** - Based on baseline performance and SLA requirements
3. **Monitor the monitors** - Ensure monitoring systems don't become bottlenecks
4. **Automate responses** - Configure automatic responses for common scenarios
5. **Regular baseline updates** - Keep performance baselines current with system changes
6. **Test failure scenarios** - Regularly test deadlock and race condition handling
7. **Monitor resource usage** - Ensure monitoring overhead stays under 5%

## Integration Patterns

### With Circuit Breakers

```python
from kailash.core.resilience.circuit_breaker import get_circuit_breaker

# Integrate monitoring with circuit breaker
breaker = get_circuit_breaker("database")

@breaker
def monitored_db_operation():
    # Monitor transaction
    metrics.execute(operation="start_transaction", transaction_id="db_op")

    try:
        result = execute_database_query()
        metrics.execute(operation="end_transaction", transaction_id="db_op", status="success")
        return result
    except Exception as e:
        metrics.execute(operation="end_transaction", transaction_id="db_op", status="failed")
        raise
```

### With Health Checks

```python
from kailash.nodes.monitoring import HealthCheckNode

# Combine transaction monitoring with health checks
health = HealthCheckNode()
monitor = TransactionMonitorNode()

# Check system health before processing
health_result = health.execute(operation="check_health")
if health_result["overall_status"] == "healthy":
    # Start transaction monitoring
    monitor.execute(operation="start_monitoring")
    # Process transactions...
else:
    # Handle unhealthy system
    logger.warning("System unhealthy, limiting transaction processing")
```

## See Also

- [Resilience Patterns](046-resilience-patterns.md)
- [Full Enterprise Guide](../enterprise/transaction-monitoring.md)
- [Production Monitoring](../monitoring/production-monitoring.md)
- [Performance Optimization](026-performance-optimization.md)
