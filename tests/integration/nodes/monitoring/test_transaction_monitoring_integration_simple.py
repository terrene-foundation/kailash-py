"""Simplified integration tests for Transaction Monitoring nodes.

Tests transaction monitoring functionality with real infrastructure using the actual node APIs.
Follows 3-tier testing policy: uses real Docker services, no mocking.
"""

import threading
import time
from datetime import UTC, datetime

import pytest
from kailash.nodes.monitoring import (
    DeadlockDetectorNode,
    PerformanceAnomalyNode,
    RaceConditionDetectorNode,
    TransactionMetricsNode,
    TransactionMonitorNode,
)
from kailash.sdk_exceptions import NodeExecutionError

# Mark all tests in this file as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]


class TestTransactionMonitoringIntegrationSimple:
    """Simplified integration tests for transaction monitoring nodes."""

    @pytest.fixture(scope="class")
    def metrics_node(self):
        """Create a TransactionMetricsNode instance for testing."""
        return TransactionMetricsNode()

    @pytest.fixture(scope="class")
    def monitor_node(self):
        """Create a TransactionMonitorNode instance for testing."""
        return TransactionMonitorNode()

    @pytest.fixture(scope="class")
    def deadlock_node(self):
        """Create a DeadlockDetectorNode instance for testing."""
        return DeadlockDetectorNode()

    @pytest.fixture(scope="class")
    def race_node(self):
        """Create a RaceConditionDetectorNode instance for testing."""
        return RaceConditionDetectorNode()

    @pytest.fixture(scope="class")
    def anomaly_node(self):
        """Create a PerformanceAnomalyNode instance for testing."""
        return PerformanceAnomalyNode()

    def test_transaction_metrics_basic_integration(self, metrics_node):
        """Test basic transaction metrics functionality."""
        # Process a simple transaction lifecycle
        txn_id = "integration_test_001"

        # Start transaction
        result = metrics_node.execute(
            operation="start_transaction",
            transaction_id=txn_id,
            operation_type="integration_test",
            metadata={"test_type": "basic"},
        )
        assert result["status"] == "success"

        # End transaction
        result = metrics_node.execute(
            operation="end_transaction",
            transaction_id=txn_id,
            status="success",
            custom_metrics={"processing_time": 0.1},
        )
        assert result["status"] == "success"

        # Get metrics
        result = metrics_node.execute(
            operation="get_metrics",
            metric_types=["latency", "throughput", "success_rate"],
        )
        assert result["status"] == "success"
        assert result["transaction_count"] >= 1

    def test_transaction_monitor_tracing_integration(self, monitor_node):
        """Test transaction monitor tracing functionality."""
        # Start monitoring
        result = monitor_node.execute(
            operation="start_monitoring", alert_thresholds={"latency_ms": 1000}
        )
        assert result["status"] == "success"

        # Create a trace
        trace_id = "integration_trace_001"
        result = monitor_node.execute(
            operation="create_trace",
            trace_id=trace_id,
            operation_name="integration_test",
            metadata={"test_scenario": "tracing"},
        )
        assert result["status"] == "success"

        # Add a span
        result = monitor_node.execute(
            operation="add_span",
            trace_id=trace_id,
            span_id="span_001",
            operation_name="database_query",
            start_time=time.time(),
        )
        assert result["status"] == "success"

        # Finish the span
        result = monitor_node.execute(
            operation="finish_span", trace_id=trace_id, span_id="span_001", success=True
        )
        assert result["status"] == "success"

        # Get the trace
        result = monitor_node.execute(operation="get_trace", trace_id=trace_id)
        assert result["status"] == "success"
        assert "trace_data" in result

        # Stop monitoring
        result = monitor_node.execute(operation="stop_monitoring")
        assert result["status"] == "success"

    def test_deadlock_detector_resource_management_integration(self, deadlock_node):
        """Test deadlock detector resource management."""
        # Start monitoring
        result = deadlock_node.execute(operation="start_monitoring")
        assert result["status"] == "success"

        # Simulate resource acquisition
        txn1 = "deadlock_test_txn1"
        txn2 = "deadlock_test_txn2"

        # Transaction 1 registers lock on resource A
        result = deadlock_node.execute(
            operation="register_lock",
            transaction_id=txn1,
            resource_id="resource_A",
            lock_type="EXCLUSIVE",
        )
        assert result["status"] == "success"

        # Transaction 2 registers lock on resource B
        result = deadlock_node.execute(
            operation="register_lock",
            transaction_id=txn2,
            resource_id="resource_B",
            lock_type="EXCLUSIVE",
        )
        assert result["status"] == "success"

        # Create potential deadlock by cross-waiting
        result = deadlock_node.execute(
            operation="register_wait",
            transaction_id=txn1,
            waiting_for_transaction_id=txn2,
            resource_id="resource_B",
        )
        assert result["status"] == "success"

        result = deadlock_node.execute(
            operation="register_wait",
            transaction_id=txn2,
            waiting_for_transaction_id=txn1,
            resource_id="resource_A",
        )
        assert result["status"] == "success"

        # Wait for detection
        time.sleep(2.0)

        # Check for deadlocks
        result = deadlock_node.execute(operation="detect_deadlocks")
        assert result["status"] == "success"

        # Clean up resources
        deadlock_node.execute(
            operation="release_lock", transaction_id=txn1, resource_id="resource_A"
        )
        deadlock_node.execute(
            operation="release_lock", transaction_id=txn2, resource_id="resource_B"
        )

        # Stop monitoring
        deadlock_node.execute(operation="stop_monitoring")

    def test_race_condition_detector_concurrent_operations(self, race_node):
        """Test race condition detector with concurrent operations."""
        # Start monitoring
        result = race_node.execute(
            operation="start_monitoring", detection_window=5.0, confidence_threshold=0.7
        )
        assert result["status"] == "success"

        # Simulate concurrent operations
        shared_resource = "shared_data_structure"

        def simulate_operation(thread_id):
            for i in range(3):
                op_id = f"op_{thread_id}_{i}"

                # Report operation
                race_node.execute(
                    operation="register_access",
                    access_id=op_id,
                    resource_id=shared_resource,
                    access_type="read_write",
                    thread_id=str(thread_id),
                )

                # Small delay
                time.sleep(0.01)

                # End access
                race_node.execute(operation="end_access", access_id=op_id)

        # Run concurrent operations
        threads = []
        for thread_id in range(3):
            thread = threading.Thread(target=simulate_operation, args=(thread_id,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Wait for detection analysis
        time.sleep(1.0)

        # Detect races
        result = race_node.execute(operation="detect_races")
        assert result["status"] == "success"

        # Get status
        result = race_node.execute(operation="get_status")
        assert result["status"] == "success"

        # Stop monitoring
        result = race_node.execute(operation="stop_monitoring")
        assert result["status"] == "success"

    def test_performance_anomaly_baseline_learning_integration(self, anomaly_node):
        """Test performance anomaly detection baseline learning."""
        # Initialize baseline
        metric_name = "response_time_integration"
        result = anomaly_node.execute(
            operation="initialize_baseline",
            metric_name=metric_name,
            sensitivity=0.8,
            min_samples=10,
        )
        assert result["status"] == "success"

        # Feed normal data
        base_value = 100.0
        for i in range(15):
            value = base_value + (i % 5 - 2) * 5  # Vary between 90-110
            result = anomaly_node.execute(
                operation="add_metric",
                metric_name=metric_name,
                value=value,
                tags={"test": "integration"},
            )
            assert result["status"] == "success"

        # Add potential anomaly
        result = anomaly_node.execute(
            operation="add_metric",
            metric_name=metric_name,
            value=base_value * 2,  # Spike
        )
        assert result["status"] == "success"

        # Detect anomalies
        result = anomaly_node.execute(
            operation="detect_anomalies",
            metric_names=[metric_name],
            detection_methods=["statistical", "threshold_based"],
        )
        assert result["status"] == "success"
        assert "anomalies_detected" in result
        assert "detection_summary" in result

        # Get baseline
        result = anomaly_node.execute(operation="get_baseline", metric_name=metric_name)
        assert result["status"] == "success"
        assert metric_name in result["baselines"]
        baseline = result["baselines"][metric_name]
        assert baseline["sample_count"] == 16  # 15 normal + 1 spike
        assert baseline["mean"] > 0

    def test_monitoring_nodes_error_handling_integration(
        self, metrics_node, deadlock_node
    ):
        """Test error handling scenarios with real infrastructure."""
        # Test invalid operations
        with pytest.raises(NodeExecutionError):
            metrics_node.execute(operation="invalid_operation")

        with pytest.raises(NodeExecutionError):
            deadlock_node.execute(operation="invalid_operation")

    def test_comprehensive_monitoring_workflow_integration(
        self, metrics_node, monitor_node, anomaly_node
    ):
        """Test a comprehensive monitoring workflow with multiple nodes."""
        # Initialize components
        monitor_node.execute(operation="start_monitoring")

        anomaly_node.execute(
            operation="initialize_baseline",
            metric_name="workflow_latency",
            min_samples=5,
        )

        # Process multiple transactions
        for i in range(8):
            txn_id = f"workflow_txn_{i}"
            trace_id = f"workflow_trace_{i}"

            # Start transaction in metrics
            metrics_node.execute(
                operation="start_transaction",
                transaction_id=txn_id,
                operation_type="workflow_test",
            )

            # Create trace in monitor
            monitor_node.execute(
                operation="create_trace",
                trace_id=trace_id,
                operation_name="workflow_test",
            )

            # Simulate processing
            latency = 50 + i * 10  # Increasing latency
            time.sleep(latency / 10000)  # Scale down for test speed

            # Feed to anomaly detector
            anomaly_node.execute(
                operation="add_metric", metric_name="workflow_latency", value=latency
            )

            # Complete operations
            success = i % 7 != 0  # One failure for testing

            status = "success" if success else "failed"
            metrics_node.execute(
                operation="end_transaction", transaction_id=txn_id, status=status
            )

            monitor_node.execute(
                operation="add_span",
                trace_id=trace_id,
                span_id=f"span_{i}",
                operation_name="process",
                start_time=time.time(),
            )

        # Verify results
        metrics_result = metrics_node.execute(operation="get_metrics")
        assert metrics_result["transaction_count"] >= 8

        alerts_result = monitor_node.execute(operation="get_alerts")
        assert alerts_result["status"] == "success"

        anomaly_result = anomaly_node.execute(
            operation="detect_anomalies", metric_names=["workflow_latency"]
        )
        assert anomaly_result["status"] == "success"

        # Cleanup
        monitor_node.execute(operation="stop_monitoring")

    def test_monitoring_performance_under_load_integration(self, metrics_node):
        """Test monitoring performance under moderate load."""
        start_time = time.time()

        # Process 50 transactions rapidly
        transaction_count = 50
        for i in range(transaction_count):
            txn_id = f"load_test_integration_{i}"

            metrics_node.execute(
                operation="start_transaction",
                transaction_id=txn_id,
                operation_type="load_test",
            )

            metrics_node.execute(
                operation="end_transaction", transaction_id=txn_id, status="success"
            )

        processing_time = time.time() - start_time

        # Verify performance
        result = metrics_node.execute(operation="get_metrics")
        assert result["transaction_count"] >= transaction_count

        # Should complete within reasonable time (less than 5 seconds)
        assert processing_time < 5.0
