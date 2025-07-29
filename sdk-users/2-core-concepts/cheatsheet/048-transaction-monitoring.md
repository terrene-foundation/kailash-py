# Transaction Monitoring Cheatsheet

Quick reference for enterprise transaction monitoring: performance metrics, real-time monitoring, deadlock detection, race condition analysis, and performance anomaly detection.

## Transaction Metrics - Quick Start

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Basic metrics collection workflow
metrics_workflow = WorkflowBuilder()
metrics_workflow.add_node("TransactionMetricsNode", "start_metrics", {
    "operation": "start_transaction",
    "transaction_id": "txn_001",
    "operation_type": "database",
    "metadata": {"user_id": "user123", "endpoint": "/api/orders"}
})

# Complete transaction (can also use complete_transaction)
metrics_workflow.add_node("TransactionMetricsNode", "end_metrics", {
    "operation": "end_transaction",  # or "complete_transaction"
    "transaction_id": "txn_001",
    "status": "success"
})

# Get aggregated metrics
metrics_workflow.add_node("TransactionMetricsNode", "get_metrics", {
    "operation": "get_metrics",
    "include_raw": True,
    "export_format": "json"
})

# Connect workflow
metrics_workflow.add_connection("start_metrics", "result", "end_metrics", "previous_state")
metrics_workflow.add_connection("end_metrics", "result", "get_metrics", "transaction_state")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(metrics_workflow.build())
print(f"Success rate: {results['get_metrics']['result']['success_rate']}")
print(f"Total transactions: {results['get_metrics']['result']['total_transactions']}")
```

## Real-time Transaction Monitor - Quick Start

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Start monitoring workflow
monitor_workflow = WorkflowBuilder()
monitor_workflow.add_node("TransactionMonitorNode", "start_monitor", {
    "operation": "start_monitoring",
    "monitoring_interval": 1.0,  # Check every second
    "alert_thresholds": {
        "latency_ms": 1000,
        "error_rate": 0.05,
        "concurrent_transactions": 100
    }
})

# Create trace for monitoring
monitor_workflow.add_node("TransactionMonitorNode", "create_trace", {
    "operation": "create_trace",
    "trace_id": "trace_002",
    "operation_name": "api_call",
    "metadata": {"endpoint": "/api/users", "method": "POST"}
})

# Get alerts
monitor_workflow.add_node("TransactionMonitorNode", "get_alerts", {
    "operation": "get_alerts"
})

# Get trace information
monitor_workflow.add_node("TransactionMonitorNode", "get_trace", {
    "operation": "get_trace",
    "trace_id": "trace_002"
})

# Connect workflow
monitor_workflow.add_connection("start_monitor", "result", "create_trace", "monitor_config")
monitor_workflow.add_connection("create_trace", "result", "get_alerts", "trace_state")
monitor_workflow.add_connection("get_alerts", "result", "get_trace", "alert_state")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(monitor_workflow.build())
print(f"Active alerts: {len(results['get_alerts']['result'].get('alerts', []))}")
print(f"Trace status: {results['get_trace']['result'].get('monitoring_status', 'unknown')}")
```

## Deadlock Detection - Quick Start

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Initialize and start deadlock monitoring workflow
deadlock_workflow = WorkflowBuilder()
deadlock_workflow.add_node("DeadlockDetectorNode", "init_detector", {
    "operation": "initialize"
})

deadlock_workflow.add_node("DeadlockDetectorNode", "start_detector", {
    "operation": "start_monitoring"
})

# Register lock acquisition (can also use acquire_resource)
deadlock_workflow.add_node("DeadlockDetectorNode", "register_lock", {
    "operation": "register_lock",  # or "acquire_resource"
    "transaction_id": "txn_003",
    "resource_id": "table_users",
    "lock_type": "EXCLUSIVE"
})

# Request a resource (simplified E2E testing operation)
deadlock_workflow.add_node("DeadlockDetectorNode", "request_resource", {
    "operation": "request_resource",
    "transaction_id": "txn_004",
    "resource_id": "table_orders",
    "resource_type": "database_table",
    "lock_type": "SHARED"
})

# Check for deadlocks
deadlock_workflow.add_node("DeadlockDetectorNode", "detect_deadlocks", {
    "operation": "detect_deadlocks"
})

# Process deadlock results
deadlock_workflow.add_node("PythonCodeNode", "process_deadlocks", {
    "code": """
deadlock_results = parameters.get('deadlock_results', {})
if deadlock_results.get('deadlocks_detected', False):
    for deadlock in deadlock_results.get('deadlocks', []):
        print(f"Deadlock detected: {deadlock.get('deadlock_id', 'unknown')}")
        print(f"Victim: {deadlock.get('victim_transaction', 'unknown')}")
result = {'processed': True}
"""
})

# Connect workflow
deadlock_workflow.add_connection("init_detector", "result", "start_detector", "init_state")
deadlock_workflow.add_connection("start_detector", "result", "register_lock", "monitor_state")
deadlock_workflow.add_connection("register_lock", "result", "request_resource", "lock_state")
deadlock_workflow.add_connection("request_resource", "result", "detect_deadlocks", "resource_state")
deadlock_workflow.add_connection("detect_deadlocks", "result", "process_deadlocks", "deadlock_results")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(deadlock_workflow.build())
```

## Race Condition Detection - Quick Start

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Start race condition monitoring workflow
race_workflow = WorkflowBuilder()
race_workflow.add_node("RaceConditionDetectorNode", "start_race_monitor", {
    "operation": "start_monitoring"
})

# Register resource access or operation
race_workflow.add_node("RaceConditionDetectorNode", "register_access", {
    "operation": "register_access",  # or "register_operation"
    "access_id": "access_001",       # or "operation_id" for register_operation
    "resource_id": "shared_counter",
    "access_type": "read_write",
    "thread_id": "thread_1"
})

# Complete an operation (finalize race detection analysis)
race_workflow.add_node("RaceConditionDetectorNode", "complete_operation", {
    "operation": "complete_operation",
    "operation_id": "access_001",
    "resource_id": "shared_counter",
    "success": True
})

# Detect race conditions
race_workflow.add_node("RaceConditionDetectorNode", "detect_races", {
    "operation": "detect_races"
})

# Process race results
race_workflow.add_node("PythonCodeNode", "process_races", {
    "code": """
race_results = parameters.get('race_results', {})
for race in race_results.get('races_detected', []):
    print(f"Race condition: {race.get('race_type', 'unknown')}")
    print(f"Confidence: {race.get('confidence', 0)}")
result = {'processed': True}
"""
})

# Connect workflow
race_workflow.add_connection("start_race_monitor", "result", "register_access", "monitor_state")
race_workflow.add_connection("register_access", "result", "complete_operation", "access_state")
race_workflow.add_connection("complete_operation", "result", "detect_races", "operation_state")
race_workflow.add_connection("detect_races", "result", "process_races", "race_results")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(race_workflow.build())
```

## Performance Anomaly Detection - Quick Start

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Initialize baseline learning workflow
anomaly_workflow = WorkflowBuilder()
anomaly_workflow.add_node("PerformanceAnomalyNode", "init_baseline", {
    "operation": "initialize_baseline",
    "metric_name": "api_response_time",
    "sensitivity": 0.8,
    "min_samples": 30
})

# Feed performance data
data_values = [120, 115, 130, 125, 118, 500]  # Normal data + spike
for i, response_time in enumerate(data_values):
    anomaly_workflow.add_node("PerformanceAnomalyNode", f"add_metric_{i}", {
        "operation": "add_metric",
        "metric_name": "api_response_time",
        "value": response_time
    })
    if i == 0:
        anomaly_workflow.add_connection("init_baseline", "result", f"add_metric_{i}", "baseline_state")
    else:
        anomaly_workflow.add_connection(f"add_metric_{i-1}", "result", f"add_metric_{i}", "previous_state")

# Detect anomalies
anomaly_workflow.add_node("PerformanceAnomalyNode", "detect_anomalies", {
    "operation": "detect_anomalies",
    "metric_names": ["api_response_time"],
    "detection_methods": ["statistical", "threshold_based"]
})

# Connect last metric to detection
anomaly_workflow.add_connection(f"add_metric_{len(data_values)-1}", "result", "detect_anomalies", "metrics_state")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(anomaly_workflow.build())
print(f"Anomalies found: {results['detect_anomalies']['result']['anomaly_count']}")
```

## Common Patterns

### Pattern 1: Complete Transaction Lifecycle

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Setup monitoring workflow
txn_workflow = WorkflowBuilder()

# Start monitoring
txn_workflow.add_node("TransactionMonitorNode", "start_monitoring", {
    "operation": "start_monitoring"
})

# Process transaction
txn_id = "order_processing_001"

# Start transaction
txn_workflow.add_node("TransactionMetricsNode", "start_transaction", {
    "operation": "start_transaction",
    "transaction_id": txn_id,
    "operation_type": "order_processing",
    "metadata": {"user_id": "user123", "order_value": 150.00}
})

# Create trace in real-time monitor
txn_workflow.add_node("TransactionMonitorNode", "create_trace", {
    "operation": "create_trace",
    "trace_id": f"trace_{txn_id}",
    "operation_name": "order_processing",
    "metadata": {"user_id": "user123", "order_value": 150.00}
})

# Business logic node
txn_workflow.add_node("PythonCodeNode", "business_logic", {
    "code": """# Simulate business logic
result = {'processed': True, 'items': 3}
"""
})

# Complete transaction
txn_workflow.add_node("TransactionMetricsNode", "end_transaction", {
    "operation": "end_transaction",
    "transaction_id": txn_id,
    "status": "success",
    "custom_metrics": {"items_processed": 3, "payment_method": "credit_card"}
})

# Add and finish span in monitor
txn_workflow.add_node("TransactionMonitorNode", "add_span", {
    "operation": "add_span",
    "trace_id": f"trace_{txn_id}",
    "span_id": f"span_{txn_id}",
    "operation_name": "order_processing"
})

txn_workflow.add_node("TransactionMonitorNode", "finish_span", {
    "operation": "finish_span",
    "span_id": f"span_{txn_id}"
})

# Connect workflow
txn_workflow.add_connection("start_monitoring", "result", "start_transaction", "monitor_state")
txn_workflow.add_connection("start_transaction", "result", "create_trace", "txn_state")
txn_workflow.add_connection("create_trace", "result", "business_logic", "trace_state")
txn_workflow.add_connection("business_logic", "result", "end_transaction", "business_result")
txn_workflow.add_connection("end_transaction", "result", "add_span", "txn_complete")
txn_workflow.add_connection("add_span", "result", "finish_span", "span_state")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(txn_workflow.build())
```

### Pattern 2: Database Operation Monitoring

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Database operation with monitoring workflow
def create_monitored_db_workflow(query, params, txn_id):
    workflow = WorkflowBuilder()

    # Start monitoring
    workflow.add_node("DeadlockDetectorNode", "start_deadlock_monitor", {
        "operation": "start_monitoring"
    })

    workflow.add_node("RaceConditionDetectorNode", "start_race_monitor", {
        "operation": "start_monitoring"
    })

    # Register lock acquisition
    workflow.add_node("DeadlockDetectorNode", "register_lock", {
        "operation": "register_lock",
        "transaction_id": txn_id,
        "resource_id": "table_orders",
        "lock_type": "SHARED"
    })

    # Register resource access
    workflow.add_node("RaceConditionDetectorNode", "register_access", {
        "operation": "register_access",
        "access_id": f"db_access_{txn_id}",
        "resource_id": "table_orders",
        "access_type": "read",
        "thread_id": "workflow_thread"
    })

    # Execute query
    workflow.add_node("SQLDatabaseNode", "execute_query", {
        "connection_string": "postgresql://...",
        "query": query,
        "parameters": params
    })

    # End access
    workflow.add_node("RaceConditionDetectorNode", "end_access", {
        "operation": "end_access",
        "access_id": f"db_access_{txn_id}"
    })

    # Release lock
    workflow.add_node("DeadlockDetectorNode", "release_lock", {
        "operation": "release_lock",
        "transaction_id": txn_id,
        "resource_id": "table_orders"
    })

    # Connect workflow
    workflow.add_connection("start_deadlock_monitor", "result", "start_race_monitor", "deadlock_state")
    workflow.add_connection("start_race_monitor", "result", "register_lock", "race_state")
    workflow.add_connection("register_lock", "result", "register_access", "lock_state")
    workflow.add_connection("register_access", "result", "execute_query", "access_state")
    workflow.add_connection("execute_query", "result", "end_access", "query_result")
    workflow.add_connection("end_access", "result", "release_lock", "access_complete")

    return workflow
```

### Pattern 3: Performance Baseline with Monitoring

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Setup performance monitoring workflow
def create_performance_monitoring_workflow():
    workflow = WorkflowBuilder()

    # Initialize baselines for different metrics
    metrics = ["api_latency", "cpu_usage", "memory_usage"]
    for i, metric in enumerate(metrics):
        workflow.add_node("PerformanceAnomalyNode", f"init_baseline_{metric}", {
            "operation": "initialize_baseline",
            "metric_name": metric,
            "sensitivity": 0.7,
            "min_samples": 50
        })
        if i > 0:
            workflow.add_connection(f"init_baseline_{metrics[i-1]}", "result", f"init_baseline_{metric}", "previous_baseline")

    # Get current metrics
    workflow.add_node("TransactionMetricsNode", "get_current_metrics", {
        "operation": "get_metrics",
        "metric_types": ["latency", "throughput"]
    })

    # Process metrics and detect anomalies
    workflow.add_node("PythonCodeNode", "process_metrics", {
        "code": """
metrics_data = parameters.get('metrics_data', {})
# Would feed each metric to anomaly detector in real implementation
result = {'metrics_processed': len(metrics_data)}
"""
    })

    # Detect anomalies
    workflow.add_node("PerformanceAnomalyNode", "detect_anomalies", {
        "operation": "detect_anomalies",
        "metric_names": ["api_latency", "cpu_usage", "memory_usage"],
        "detection_methods": ["statistical", "iqr"]
    })

    # Handle anomalies
    workflow.add_node("PythonCodeNode", "handle_anomalies", {
        "code": """
anomalies = parameters.get('anomaly_results', {})
if anomalies.get('anomaly_count', 0) > 0:
    for anomaly in anomalies.get('anomalies_detected', []):
        print(f"ALERT: {anomaly.get('anomaly_type', 'unknown')} detected")
        print(f"Metric: {anomaly.get('metric_name', 'unknown')}")
        print(f"Severity: {anomaly.get('severity', 'unknown')}")
result = {'handled': True}
"""
    })

    # Connect workflow
    workflow.add_connection(f"init_baseline_{metrics[-1]}", "result", "get_current_metrics", "baseline_complete")
    workflow.add_connection("get_current_metrics", "result", "process_metrics", "metrics_data")
    workflow.add_connection("process_metrics", "result", "detect_anomalies", "processed_metrics")
    workflow.add_connection("detect_anomalies", "result", "handle_anomalies", "anomaly_results")

    return workflow
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
complete_workflow = WorkflowBuilder()
complete_workflow.add_node("TransactionMetricsNode", "complete_txn", {
    "operation": "complete_transaction",  # Alias for end_transaction
    "transaction_id": "txn_123",
    "success": True  # Boolean success parameter
})

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(complete_workflow.build())
result = results["complete_txn"]["result"]
print(f"Success rate: {result['success_rate']}")  # New field
print(f"Total transactions: {result['total_transactions']}")  # New alias field
```

### DeadlockDetectorNode - Enhanced Operations

```python
# New initialize operation
deadlock_ops_workflow = WorkflowBuilder()
deadlock_ops_workflow.add_node("DeadlockDetectorNode", "init_deadlock", {
    "operation": "initialize",
    "deadlock_timeout": 30.0,
    "cycle_detection_enabled": True
})

# Acquire/release resource aliases
deadlock_ops_workflow.add_node("DeadlockDetectorNode", "acquire_resource", {
    "operation": "acquire_resource",  # Alias for register_lock
    "transaction_id": "txn_123",
    "resource_id": "table_users",
    "lock_type": "exclusive"
})

deadlock_ops_workflow.add_node("DeadlockDetectorNode", "release_resource", {
    "operation": "release_resource",  # Alias for release_lock
    "transaction_id": "txn_123",
    "resource_id": "table_users"
})

# Request resource for E2E scenarios
deadlock_ops_workflow.add_node("DeadlockDetectorNode", "request_resource", {
    "operation": "request_resource",
    "transaction_id": "txn_456",
    "resource_id": "table_orders",
    "resource_type": "database_table",
    "lock_type": "SHARED"
})

# Connect workflow
deadlock_ops_workflow.add_connection("init_deadlock", "result", "acquire_resource", "init_state")
deadlock_ops_workflow.add_connection("acquire_resource", "result", "release_resource", "acquire_state")
deadlock_ops_workflow.add_connection("release_resource", "result", "request_resource", "release_state")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(deadlock_ops_workflow.build())
```

### RaceConditionDetectorNode - Complete Operation Cycle

```python
race_ops_workflow = WorkflowBuilder()

# Register operation
race_ops_workflow.add_node("RaceConditionDetectorNode", "register_op", {
    "operation": "register_operation",
    "operation_id": "op_123",
    "resource_id": "shared_resource",
    "thread_id": "thread_1"
})

# Complete operation with final analysis
race_ops_workflow.add_node("RaceConditionDetectorNode", "complete_op", {
    "operation": "complete_operation",  # New operation
    "operation_id": "op_123",
    "resource_id": "shared_resource",
    "success": True
})

# Connect workflow
race_ops_workflow.add_connection("register_op", "result", "complete_op", "operation_state")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(race_ops_workflow.build())
result = results["complete_op"]["result"]
print(f"Race conditions detected: {result['race_count']}")
print(f"Operation status: {result['monitoring_status']}")
```

### TransactionMonitorNode - Enhanced Tracing

```python
monitor_ops_workflow = WorkflowBuilder()

# Complete transaction with enhanced schema
monitor_ops_workflow.add_node("TransactionMonitorNode", "complete_monitor_txn", {
    "operation": "complete_transaction",  # New operation
    "transaction_id": "monitor_test_123",
    "success": True  # Boolean success parameter
})

# Verify output fields
monitor_ops_workflow.add_node("PythonCodeNode", "verify_fields", {
    "code": """
monitor_result = parameters.get('monitor_result', {})
assert "trace_data" in monitor_result
assert "span_data" in monitor_result
assert "correlation_id" in monitor_result
result = {'verified': True}
"""
})

# Connect workflow
monitor_ops_workflow.add_connection("complete_monitor_txn", "result", "verify_fields", "monitor_result")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(monitor_ops_workflow.build())
```

## Configuration Reference

### Transaction Metrics Settings

```python
# Metric collection configuration
metric_config_workflow = WorkflowBuilder()
metric_config_workflow.add_node("TransactionMetricsNode", "configured_metrics", {
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
    test_workflow = WorkflowBuilder()

    # Start transaction
    test_workflow.add_node("TransactionMetricsNode", "start_test_txn", {
        "operation": "start_transaction",
        "transaction_id": "test_001"
    })

    # Complete transaction
    test_workflow.add_node("TransactionMetricsNode", "end_test_txn", {
        "operation": "end_transaction",
        "transaction_id": "test_001",
        "status": "success"
    })

    # Verify metrics
    test_workflow.add_node("TransactionMetricsNode", "get_test_metrics", {
        "operation": "get_metrics"
    })

    # Connect workflow
    test_workflow.add_connection("start_test_txn", "result", "end_test_txn", "start_state")
    test_workflow.add_connection("end_test_txn", "result", "get_test_metrics", "end_state")

    # Execute
    runtime = LocalRuntime()
    results, run_id = runtime.execute(test_workflow.build())

    assert results["start_test_txn"]["result"]["status"] == "success"
    assert results["end_test_txn"]["result"]["status"] == "success"
    assert results["get_test_metrics"]["result"]["total_transactions"] == 1
    assert results["get_test_metrics"]["result"]["success_rate"] == 1.0
```

### Test Deadlock Detection

```python
def test_deadlock_scenario():
    test_deadlock_workflow = WorkflowBuilder()

    test_deadlock_workflow.add_node("DeadlockDetectorNode", "start_deadlock_test", {
        "operation": "start_monitoring"
    })

    # Create potential deadlock scenario
    # Transaction 1 acquires A, waits for txn2
    test_deadlock_workflow.add_node("DeadlockDetectorNode", "txn1_lock_A", {
        "operation": "register_lock",
        "transaction_id": "txn1",
        "resource_id": "resource_A"
    })

    test_deadlock_workflow.add_node("DeadlockDetectorNode", "txn1_wait_B", {
        "operation": "register_wait",
        "transaction_id": "txn1",
        "waiting_for_transaction_id": "txn2",
        "resource_id": "resource_B"
    })

    # Transaction 2 acquires B, waits for txn1
    test_deadlock_workflow.add_node("DeadlockDetectorNode", "txn2_lock_B", {
        "operation": "register_lock",
        "transaction_id": "txn2",
        "resource_id": "resource_B"
    })

    test_deadlock_workflow.add_node("DeadlockDetectorNode", "txn2_wait_A", {
        "operation": "register_wait",
        "transaction_id": "txn2",
        "waiting_for_transaction_id": "txn1",
        "resource_id": "resource_A"
    })

    # Should detect deadlock
    test_deadlock_workflow.add_node("DeadlockDetectorNode", "detect_test_deadlocks", {
        "operation": "detect_deadlocks"
    })

    # Connect workflow
    test_deadlock_workflow.add_connection("start_deadlock_test", "result", "txn1_lock_A", "monitor_state")
    test_deadlock_workflow.add_connection("txn1_lock_A", "result", "txn1_wait_B", "lock_state")
    test_deadlock_workflow.add_connection("txn1_wait_B", "result", "txn2_lock_B", "wait_state")
    test_deadlock_workflow.add_connection("txn2_lock_B", "result", "txn2_wait_A", "lock_state")
    test_deadlock_workflow.add_connection("txn2_wait_A", "result", "detect_test_deadlocks", "wait_state")

    # Execute
    runtime = LocalRuntime()
    results, run_id = runtime.execute(test_deadlock_workflow.build())

    assert results["detect_test_deadlocks"]["result"]["deadlocks_detected"] > 0
```

### Test Anomaly Detection

```python
def test_performance_anomaly():
    test_anomaly_workflow = WorkflowBuilder()

    # Initialize baseline
    test_anomaly_workflow.add_node("PerformanceAnomalyNode", "init_test_baseline", {
        "operation": "initialize_baseline",
        "metric_name": "test_metric"
    })

    # Add normal data
    normal_values = [100, 105, 95, 110, 90]
    for i, value in enumerate(normal_values):
        test_anomaly_workflow.add_node("PerformanceAnomalyNode", f"add_normal_{i}", {
            "operation": "add_metric",
            "metric_name": "test_metric",
            "value": value
        })
        if i == 0:
            test_anomaly_workflow.add_connection("init_test_baseline", "result", f"add_normal_{i}", "baseline_state")
        else:
            test_anomaly_workflow.add_connection(f"add_normal_{i-1}", "result", f"add_normal_{i}", "previous_state")

    # Add anomalous data
    test_anomaly_workflow.add_node("PerformanceAnomalyNode", "add_anomaly", {
        "operation": "add_metric",
        "metric_name": "test_metric",
        "value": 500  # Clear anomaly
    })
    test_anomaly_workflow.add_connection(f"add_normal_{len(normal_values)-1}", "result", "add_anomaly", "previous_state")

    # Should detect anomaly
    test_anomaly_workflow.add_node("PerformanceAnomalyNode", "detect_test_anomalies", {
        "operation": "detect_anomalies",
        "metric_names": ["test_metric"]
    })
    test_anomaly_workflow.add_connection("add_anomaly", "result", "detect_test_anomalies", "metrics_state")

    # Execute
    runtime = LocalRuntime()
    results, run_id = runtime.execute(test_anomaly_workflow.build())

    assert results["detect_test_anomalies"]["result"]["anomaly_count"] > 0
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
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Integrate monitoring with circuit breaker workflow
def create_monitored_db_workflow():
    workflow = WorkflowBuilder()

    # Circuit breaker protection
    workflow.add_node("CircuitBreakerNode", "db_breaker", {
        "operation": "check_circuit",
        "service_name": "database"
    })

    # Monitor transaction
    workflow.add_node("TransactionMetricsNode", "start_db_txn", {
        "operation": "start_transaction",
        "transaction_id": "db_op"
    })

    # Database operation
    workflow.add_node("SQLDatabaseNode", "db_query", {
        "connection_string": "postgresql://...",
        "query": "SELECT * FROM users"
    })

    # End transaction based on success
    workflow.add_node("TransactionMetricsNode", "end_db_txn_success", {
        "operation": "end_transaction",
        "transaction_id": "db_op",
        "status": "success"
    })

    workflow.add_node("TransactionMetricsNode", "end_db_txn_failure", {
        "operation": "end_transaction",
        "transaction_id": "db_op",
        "status": "failed"
    })

    # Switch based on query result
    workflow.add_node("SwitchNode", "check_success", {
        "condition": "result != None"
    })

    # Connect workflow
    workflow.add_connection("db_breaker", "result", "start_db_txn", "breaker_state")
    workflow.add_connection("start_db_txn", "result", "db_query", "txn_state")
    workflow.add_connection("db_query", "result", "check_success", "result")
    workflow.add_connection("check_success", "true_output", "end_db_txn_success", "query_result")
    workflow.add_connection("check_success", "false_output", "end_db_txn_failure", "query_error")

    return workflow
```

### With Health Checks

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Combine transaction monitoring with health checks workflow
health_workflow = WorkflowBuilder()

# Check system health
health_workflow.add_node("HealthCheckNode", "check_health", {
    "operation": "check_health"
})

# Conditional monitoring based on health
health_workflow.add_node("SwitchNode", "health_switch", {
    "condition": "result.overall_status == 'healthy'"
})

# Healthy path: Start transaction monitoring
health_workflow.add_node("TransactionMonitorNode", "start_monitoring", {
    "operation": "start_monitoring"
})

# Unhealthy path: Log warning
health_workflow.add_node("PythonCodeNode", "log_unhealthy", {
    "code": """
print("System unhealthy, limiting transaction processing")
result = {'status': 'limited'}
"""
})

# Connect workflow
health_workflow.add_connection("check_health", "result", "health_switch", "result")
health_workflow.add_connection("health_switch", "true_output", "start_monitoring", "health_state")
health_workflow.add_connection("health_switch", "false_output", "log_unhealthy", "health_state")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(health_workflow.build())
```

## See Also

- [Resilience Patterns](046-resilience-patterns.md)
- [Full Enterprise Guide](../enterprise/transaction-monitoring.md)
- [Production Monitoring](../monitoring/production-monitoring.md)
- [Performance Optimization](026-performance-optimization.md)
