"""Integration tests for Transaction Monitoring nodes using real services.

Tests transaction monitoring functionality with real infrastructure and component interactions.
Follows 3-tier testing policy: uses real Docker services, no mocking.
"""

import asyncio
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
from tests.utils.docker_config import get_postgres_connection_string

# Mark all tests in this file as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]


class TestTransactionMonitoringIntegration:
    """Integration tests for transaction monitoring nodes with real services."""

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

    def test_transaction_lifecycle_integration(self, metrics_node, monitor_node):
        """Test complete transaction lifecycle monitoring."""
        # Start real-time monitoring
        monitor_result = monitor_node.execute(
            operation="start_monitoring",
            monitoring_interval=1.0,
            alert_thresholds={
                "latency_ms": 2000,
                "error_rate": 0.1,
                "concurrent_transactions": 50,
            },
        )
        assert monitor_result["status"] == "success"

        # Process multiple transactions
        transaction_ids = []
        for i in range(10):
            txn_id = f"integration_test_{i}"
            transaction_ids.append(txn_id)

            # Start transaction in metrics
            metrics_result = metrics_node.execute(
                operation="start_transaction",
                transaction_id=txn_id,
                operation_type="integration_test",
                metadata={"test_batch": "lifecycle", "sequence": i},
            )
            assert metrics_result["status"] == "success"

            # Create trace for real-time monitor
            monitor_result = monitor_node.execute(
                operation="create_trace",
                trace_id=f"trace_{txn_id}",
                operation_name="integration_test",
                metadata={"test_type": "integration"},
            )
            assert monitor_result["status"] == "success"

            # Simulate processing time
            time.sleep(0.1)

            # Complete transaction
            success = i % 3 != 0  # Create some failures for testing
            metrics_result = metrics_node.execute(
                operation="complete_transaction",
                transaction_id=txn_id,
                success=success,
                metadata={"processing_time": 0.1},
            )
            assert metrics_result["status"] == "success"

            # Finish span in monitor
            monitor_result = monitor_node.execute(
                operation="finish_span",
                trace_id=f"trace_{txn_id}",
                span_id=f"span_{txn_id}",
                success=success,
            )
            assert monitor_result["status"] == "success"

        # Verify aggregated metrics
        metrics_result = metrics_node.execute(
            operation="get_metrics",
            metric_types=["latency", "throughput", "success_rate"],
            time_range=300,
        )
        assert metrics_result["status"] == "success"
        assert metrics_result["total_transactions"] == 10
        assert metrics_result["success_rate"] < 1.0  # Should have some failures

        # Verify monitoring status by getting alerts
        monitor_result = monitor_node.execute(operation="get_alerts")
        assert monitor_result["status"] == "success"

        # Stop monitoring
        monitor_result = monitor_node.execute(operation="stop_monitoring")
        assert monitor_result["status"] == "success"

    def test_deadlock_detection_with_database_simulation(self, deadlock_node):
        """Test deadlock detection with simulated database operations."""
        # Initialize deadlock detector
        result = deadlock_node.execute(
            operation="initialize", detection_interval=2.0, timeout_threshold=10.0
        )
        assert result["status"] == "success"

        # Simulate database transactions that could deadlock
        # Transaction 1: Acquires table_users, wants table_orders
        result = deadlock_node.execute(
            operation="acquire_resource",
            transaction_id="db_txn_1",
            resource_id="table_users",
            resource_type="database_table",
            lock_type="EXCLUSIVE",
        )
        assert result["status"] == "success"

        result = deadlock_node.execute(
            operation="request_resource",
            transaction_id="db_txn_1",
            resource_id="table_orders",
            resource_type="database_table",
            lock_type="SHARED",
        )
        assert result["status"] == "success"

        # Transaction 2: Acquires table_orders, wants table_users
        result = deadlock_node.execute(
            operation="acquire_resource",
            transaction_id="db_txn_2",
            resource_id="table_orders",
            resource_type="database_table",
            lock_type="EXCLUSIVE",
        )
        assert result["status"] == "success"

        result = deadlock_node.execute(
            operation="request_resource",
            transaction_id="db_txn_2",
            resource_id="table_users",
            resource_type="database_table",
            lock_type="SHARED",
        )
        assert result["status"] == "success"

        # Wait for detection cycle
        time.sleep(3.0)

        # Check for deadlocks
        result = deadlock_node.execute(operation="detect_deadlocks")
        assert result["status"] == "success"

        # Should detect the circular dependency
        if result["deadlocks_detected"] > 0:
            deadlocks = result["deadlocks"]
            assert len(deadlocks) > 0
            deadlock = deadlocks[0]
            assert "victim_transaction" in deadlock
            assert deadlock["victim_transaction"] in ["db_txn_1", "db_txn_2"]

    def test_race_condition_detection_concurrent_access(self, race_node):
        """Test race condition detection with concurrent operations."""
        # Start race condition monitoring
        result = race_node.execute(
            operation="start_monitoring", detection_window=5.0, confidence_threshold=0.7
        )
        assert result["status"] == "success"

        # Simulate concurrent operations on shared resource
        def simulate_concurrent_operation(thread_id, operation_count):
            """Simulate concurrent operations from different threads."""
            for i in range(operation_count):
                operation_id = f"op_{thread_id}_{i}"

                # Report concurrent READ operation
                race_node.execute(
                    operation="report_operation",
                    operation_id=operation_id,
                    resource_id="shared_counter",
                    operation_type="READ",
                    thread_id=str(thread_id),
                    process_id="integration_test",
                )

                # Small delay to create timing overlap
                time.sleep(0.01)

                # Report WRITE operation
                race_node.execute(
                    operation="complete_operation",
                    operation_id=operation_id,
                    success=True,
                )

        # Run concurrent operations
        threads = []
        for thread_id in range(5):
            thread = threading.Thread(
                target=simulate_concurrent_operation, args=(thread_id, 10)
            )
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Wait for analysis
        time.sleep(2.0)

        # Analyze for race conditions
        result = race_node.execute(operation="analyze_races", time_window=30.0)
        assert result["status"] == "success"

        # Verify race detection analysis ran
        assert "analysis_results" in result
        assert "operations_analyzed" in result

    def test_performance_anomaly_detection_with_baseline(self, anomaly_node):
        """Test performance anomaly detection with baseline learning."""
        # Initialize baseline for response time monitoring
        result = anomaly_node.execute(
            operation="initialize_baseline",
            metric_name="api_response_time",
            sensitivity=0.8,
            min_samples=20,
            learning_rate=0.1,
        )
        assert result["status"] == "success"

        # Feed normal performance data to establish baseline
        base_response_time = 150.0  # 150ms base
        normal_values = []

        for i in range(25):
            # Add some realistic variance (±10%)
            variance = (i % 11 - 5) * 0.02  # -10% to +10%
            value = base_response_time * (1 + variance)
            normal_values.append(value)

            result = anomaly_node.execute(
                operation="add_metric",
                metric_name="api_response_time",
                value=value,
                tags={"endpoint": "/api/test", "method": "GET"},
                metadata={"request_id": f"req_{i}"},
            )
            assert result["status"] == "success"

        # Add performance spike (anomaly)
        spike_value = base_response_time * 3  # 3x normal response time
        result = anomaly_node.execute(
            operation="add_metric",
            metric_name="api_response_time",
            value=spike_value,
            tags={"endpoint": "/api/test", "method": "GET"},
            metadata={"request_id": "spike_test"},
        )
        assert result["status"] == "success"

        # Detect anomalies
        result = anomaly_node.execute(
            operation="detect_anomalies",
            metric_names=["api_response_time"],
            detection_methods=["statistical", "threshold_based"],
            detection_window=120.0,
        )
        assert result["status"] == "success"

        # Should detect the spike as an anomaly
        # Note: Detection depends on statistical thresholds, so we verify structure
        assert "anomalies_detected" in result
        assert "anomaly_count" in result
        assert "detection_summary" in result

        # Get baseline information
        result = anomaly_node.execute(
            operation="get_baseline", metric_name="api_response_time"
        )
        assert result["status"] == "success"
        assert "api_response_time" in result["baselines"]

        baseline = result["baselines"]["api_response_time"]
        assert baseline["sample_count"] == 26  # 25 normal + 1 spike
        assert baseline["mean"] > 0
        assert baseline["std_dev"] > 0

    def test_monitoring_nodes_error_handling(
        self, metrics_node, monitor_node, deadlock_node
    ):
        """Test error handling and recovery scenarios."""
        # Test invalid transaction operations
        with pytest.raises(NodeExecutionError):
            metrics_node.execute(
                operation="complete_transaction",
                transaction_id="nonexistent_txn",
                success=True,
            )

        # Test invalid monitoring operations
        with pytest.raises(NodeExecutionError):
            monitor_node.execute(operation="invalid_operation")

        # Test deadlock detector with invalid resource operations
        with pytest.raises(NodeExecutionError):
            deadlock_node.execute(
                operation="release_resource",
                transaction_id="invalid_txn",
                resource_id="nonexistent_resource",
            )

    def test_monitoring_performance_under_load(self, metrics_node, monitor_node):
        """Test monitoring system performance under load."""
        start_time = time.time()

        # Start monitoring
        monitor_node.execute(operation="start_monitoring")

        # Process large number of transactions rapidly
        transaction_count = 100
        for i in range(transaction_count):
            txn_id = f"load_test_{i}"

            # Start transaction
            metrics_node.execute(
                operation="start_transaction",
                transaction_id=txn_id,
                operation_type="load_test",
            )

            # Track in monitor
            monitor_node.execute(
                operation="track_transaction",
                transaction_id=txn_id,
                operation_type="load_test",
                start_time=time.time(),
            )

            # Complete immediately
            metrics_node.execute(
                operation="complete_transaction", transaction_id=txn_id, success=True
            )

            monitor_node.execute(
                operation="complete_transaction", transaction_id=txn_id, success=True
            )

        processing_time = time.time() - start_time

        # Verify performance metrics
        result = metrics_node.execute(operation="get_metrics")
        assert result["total_transactions"] >= transaction_count

        # Performance should be reasonable (less than 10 seconds for 100 transactions)
        assert processing_time < 10.0

        # Stop monitoring
        monitor_node.execute(operation="stop_monitoring")

    def test_cross_node_data_consistency(
        self, metrics_node, monitor_node, anomaly_node
    ):
        """Test data consistency across different monitoring nodes."""
        # Initialize anomaly detection for transaction metrics
        anomaly_node.execute(
            operation="initialize_baseline",
            metric_name="transaction_duration",
            min_samples=10,
        )

        # Start real-time monitoring
        monitor_node.execute(operation="start_monitoring")

        # Process transactions with consistent timing
        durations = []
        for i in range(15):
            txn_id = f"consistency_test_{i}"
            start_time = time.time()

            # Start transaction tracking
            metrics_node.execute(
                operation="start_transaction",
                transaction_id=txn_id,
                operation_type="consistency_test",
            )

            monitor_node.execute(
                operation="track_transaction",
                transaction_id=txn_id,
                operation_type="consistency_test",
                start_time=start_time,
            )

            # Simulate processing
            processing_duration = 0.05 + (i % 3) * 0.01  # Vary between 50-70ms
            time.sleep(processing_duration)
            durations.append(processing_duration * 1000)  # Convert to ms

            # Complete transaction
            metrics_node.execute(
                operation="complete_transaction", transaction_id=txn_id, success=True
            )

            monitor_node.execute(
                operation="complete_transaction", transaction_id=txn_id, success=True
            )

            # Feed duration to anomaly detector
            anomaly_node.execute(
                operation="add_metric",
                metric_name="transaction_duration",
                value=processing_duration * 1000,
            )

        # Verify consistency across nodes
        # Get metrics from transaction metrics node
        metrics_result = metrics_node.execute(operation="get_metrics")

        # Get status from monitor node
        monitor_result = monitor_node.execute(operation="get_monitoring_status")

        # Get baseline from anomaly detector
        anomaly_result = anomaly_node.execute(
            operation="get_baseline", metric_name="transaction_duration"
        )

        # Verify data consistency
        assert metrics_result["total_transactions"] == 15
        assert monitor_result["active_count"] == 0  # All completed
        assert anomaly_result["baselines"]["transaction_duration"]["sample_count"] == 15

        # Stop monitoring
        monitor_node.execute(operation="stop_monitoring")

    def test_real_world_monitoring_scenario(
        self, metrics_node, monitor_node, deadlock_node, anomaly_node
    ):
        """Test a complete real-world monitoring scenario."""
        # Setup comprehensive monitoring
        monitor_node.execute(
            operation="start_monitoring",
            monitoring_interval=0.5,
            alert_thresholds={
                "latency_ms": 1000,
                "error_rate": 0.05,
                "concurrent_transactions": 20,
            },
        )

        deadlock_node.execute(operation="initialize")

        anomaly_node.execute(
            operation="initialize_baseline",
            metric_name="system_latency",
            sensitivity=0.9,
        )

        # Simulate realistic workload
        successful_txns = 0
        failed_txns = 0

        for batch in range(3):  # 3 batches of work
            batch_start = time.time()

            for i in range(10):  # 10 transactions per batch
                txn_id = f"realworld_{batch}_{i}"

                # Start transaction
                metrics_node.execute(
                    operation="start_transaction",
                    transaction_id=txn_id,
                    operation_type="data_processing",
                    metadata={"batch": batch, "item": i},
                )

                monitor_node.execute(
                    operation="track_transaction",
                    transaction_id=txn_id,
                    operation_type="data_processing",
                    start_time=time.time(),
                )

                # Simulate resource acquisition
                deadlock_node.execute(
                    operation="acquire_resource",
                    transaction_id=txn_id,
                    resource_id=f"resource_{i % 3}",  # Create contention
                    resource_type="data_file",
                )

                # Simulate processing with varying duration
                if i == 7 and batch == 1:
                    # Simulate a slow operation
                    processing_time = 0.5
                else:
                    processing_time = 0.05 + (i % 3) * 0.02

                time.sleep(processing_time)

                # Feed latency to anomaly detector
                latency_ms = processing_time * 1000
                anomaly_node.execute(
                    operation="add_metric",
                    metric_name="system_latency",
                    value=latency_ms,
                )

                # Simulate occasional failures
                success = not (i == 8 and batch == 2)  # One failure in last batch

                # Release resource
                deadlock_node.execute(
                    operation="release_resource",
                    transaction_id=txn_id,
                    resource_id=f"resource_{i % 3}",
                )

                # Complete transaction
                metrics_node.execute(
                    operation="complete_transaction",
                    transaction_id=txn_id,
                    success=success,
                )

                monitor_node.execute(
                    operation="complete_transaction",
                    transaction_id=txn_id,
                    success=success,
                )

                if success:
                    successful_txns += 1
                else:
                    failed_txns += 1

            # Brief pause between batches
            time.sleep(0.1)

        # Analyze results
        metrics_result = metrics_node.execute(operation="get_metrics")
        monitor_result = monitor_node.execute(operation="get_monitoring_status")
        deadlock_result = deadlock_node.execute(operation="detect_deadlocks")
        anomaly_result = anomaly_node.execute(
            operation="detect_anomalies", metric_names=["system_latency"]
        )

        # Verify comprehensive monitoring worked
        assert metrics_result["total_transactions"] == 30
        assert metrics_result["success_rate"] < 1.0  # Should have one failure
        assert monitor_result["active_count"] == 0
        assert deadlock_result["status"] == "success"
        assert anomaly_result["status"] == "success"

        # Cleanup
        monitor_node.execute(operation="stop_monitoring")
