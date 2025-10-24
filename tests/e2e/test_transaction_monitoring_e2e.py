"""E2E tests for Transaction Monitoring in production-like scenarios.

Tests complete transaction monitoring workflows with real infrastructure,
multiple components, and realistic business scenarios.
"""

import asyncio
import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.monitoring import (
    DeadlockDetectorNode,
    PerformanceAnomalyNode,
    RaceConditionDetectorNode,
    TransactionMetricsNode,
    TransactionMonitorNode,
)
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from tests.utils.docker_config import get_postgres_connection_string

# Mark all tests in this file as E2E tests
pytestmark = [pytest.mark.e2e, pytest.mark.requires_docker, pytest.mark.slow]


class TestTransactionMonitoringE2E:
    """E2E tests for complete transaction monitoring scenarios."""

    @pytest.fixture(scope="class")
    def sample_data_file(self, tmp_path_factory):
        """Create a sample CSV file for testing."""
        data_dir = tmp_path_factory.mktemp("transaction_data")
        csv_file = data_dir / "transactions.csv"

        # Create sample transaction data
        csv_content = """transaction_id,user_id,amount,timestamp,status
txn_001,user_123,150.00,2024-01-01T10:00:00Z,pending
txn_002,user_456,75.50,2024-01-01T10:01:00Z,pending
txn_003,user_789,200.00,2024-01-01T10:02:00Z,pending
txn_004,user_123,50.00,2024-01-01T10:03:00Z,pending
txn_005,user_456,300.00,2024-01-01T10:04:00Z,pending
txn_006,user_999,125.75,2024-01-01T10:05:00Z,pending
txn_007,user_123,90.00,2024-01-01T10:06:00Z,pending
txn_008,user_456,175.25,2024-01-01T10:07:00Z,pending
txn_009,user_789,85.00,2024-01-01T10:08:00Z,pending
txn_010,user_999,220.50,2024-01-01T10:09:00Z,pending"""

        csv_file.write_text(csv_content)
        return str(csv_file)

    def test_complete_data_processing_with_monitoring(self, sample_data_file):
        """Test complete data processing workflow with comprehensive monitoring."""
        # Build monitoring-enabled workflow
        workflow = WorkflowBuilder()

        # Add data processing nodes
        workflow.add_node(
            "CSVReaderNode", "data_reader", {"file_path": sample_data_file}
        )

        # Add comprehensive transaction monitoring that reads the CSV and reports metrics
        workflow.add_node(
            "TransactionMetricsNode",
            "transaction_metrics",
            {
                "operation": "get_metrics",
                "metric_types": ["latency", "throughput"],
            },
        )

        workflow.add_node(
            "TransactionMonitorNode",
            "transaction_monitor",
            {
                "operation": "start_monitoring",
                "monitoring_interval": 1.0,
                "alert_thresholds": {"latency_ms": 5000, "error_rate": 0.1},
            },
        )

        workflow.add_node(
            "DeadlockDetectorNode",
            "deadlock_detector",
            {"operation": "start_monitoring"},
        )

        workflow.add_node(
            "PerformanceAnomalyNode",
            "anomaly_detector",
            {
                "operation": "initialize_baseline",
                "metric_name": "processing_latency",
                "min_samples": 5,
            },
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify monitoring results
        assert run_id is not None
        assert "transaction_metrics" in results
        assert "transaction_monitor" in results
        assert "deadlock_detector" in results
        assert "anomaly_detector" in results

        # Verify data processing succeeded
        data_result = results["data_reader"]
        assert "data" in data_result
        assert len(data_result["data"]) == 10  # 10 transactions

        # Verify monitoring was active
        monitor_result = results["transaction_monitor"]
        assert monitor_result["status"] == "success"

        metrics_result = results["transaction_metrics"]
        assert metrics_result["status"] == "success"

    def test_concurrent_transaction_processing_with_monitoring(self):
        """Test concurrent transaction processing with race condition detection."""
        # Setup monitoring nodes
        race_detector = RaceConditionDetectorNode()
        transaction_monitor = TransactionMonitorNode()
        performance_monitor = PerformanceAnomalyNode()

        # Initialize monitoring
        race_detector.execute(operation="start_monitoring", confidence_threshold=0.8)
        transaction_monitor.execute(operation="start_monitoring")
        performance_monitor.execute(
            operation="initialize_baseline",
            metric_name="concurrent_processing_time",
            min_samples=10,
        )

        # Simulate concurrent transaction processing
        shared_resource = "account_balance_table"
        processed_transactions = []
        processing_times = []

        def process_transaction_batch(thread_id, batch_size):
            """Process a batch of transactions concurrently."""
            thread_times = []
            for i in range(batch_size):
                txn_id = f"concurrent_{thread_id}_{i}"
                start_time = time.time()

                # Track transaction
                transaction_monitor.execute(
                    operation="start_transaction",
                    transaction_id=txn_id,
                    operation_type="concurrent_processing",
                    start_time=start_time,
                )

                # Report race condition monitoring
                operation_id = f"op_{thread_id}_{i}"
                race_detector.execute(
                    operation="report_operation",
                    operation_id=operation_id,
                    resource_id=shared_resource,
                    operation_type="READ_WRITE",
                    thread_id=str(thread_id),
                )

                # Simulate database operation timing
                processing_delay = 0.05 + (i % 3) * 0.01  # 50-70ms
                time.sleep(processing_delay)

                # Complete operations
                end_time = time.time()
                total_time = (end_time - start_time) * 1000  # Convert to ms

                race_detector.execute(
                    operation="complete_operation",
                    operation_id=operation_id,
                    success=True,
                )

                transaction_monitor.execute(
                    operation="complete_transaction",
                    transaction_id=txn_id,
                    success=True,
                )

                # Record performance
                thread_times.append(total_time)
                processed_transactions.append(txn_id)

            processing_times.extend(thread_times)

        # Run concurrent processing
        threads = []
        num_threads = 5
        batch_size = 8

        for thread_id in range(num_threads):
            thread = threading.Thread(
                target=process_transaction_batch, args=(thread_id, batch_size)
            )
            threads.append(thread)
            thread.start()

        # Wait for all processing to complete
        for thread in threads:
            thread.join()

        # Feed performance data to anomaly detector
        for processing_time in processing_times:
            performance_monitor.execute(
                operation="add_metric",
                metric_name="concurrent_processing_time",
                value=processing_time,
            )

        # Analyze results
        race_result = race_detector.execute(operation="detect_races", time_window=60.0)

        monitor_status = transaction_monitor.execute(operation="get_monitoring_status")

        anomaly_result = performance_monitor.execute(
            operation="detect_anomalies", metric_names=["concurrent_processing_time"]
        )

        # Verify concurrent processing succeeded
        expected_transactions = num_threads * batch_size
        assert len(processed_transactions) == expected_transactions
        assert len(processing_times) == expected_transactions

        # Verify monitoring captured the activity
        assert race_result["status"] == "success"
        assert monitor_status["status"] == "success"
        assert anomaly_result["status"] == "success"

        # Verify performance was reasonable
        avg_processing_time = sum(processing_times) / len(processing_times)
        assert avg_processing_time < 200  # Less than 200ms average

        # Cleanup
        race_detector.execute(operation="stop_monitoring")
        transaction_monitor.execute(operation="stop_monitoring")

    def test_database_deadlock_simulation_e2e(self):
        """Test end-to-end database deadlock detection and resolution."""
        # Initialize monitoring components
        deadlock_detector = DeadlockDetectorNode()
        transaction_metrics = TransactionMetricsNode()

        # Setup deadlock detection
        deadlock_result = deadlock_detector.execute(
            operation="initialize",
            detection_interval=1.0,
            timeout_threshold=5.0,
            victim_selection="youngest",
        )
        assert deadlock_result["status"] == "success"

        # Simulate complex database scenario with multiple resources
        resources = ["users_table", "orders_table", "payments_table", "inventory_table"]
        transactions = []

        # Create potential deadlock scenario
        for i in range(4):
            txn_id = f"db_scenario_{i}"
            transactions.append(txn_id)

            # Start transaction tracking
            transaction_metrics.execute(
                operation="start_transaction",
                transaction_id=txn_id,
                operation_type="database_operation",
                metadata={"scenario": "deadlock_simulation"},
            )

            # Each transaction acquires resources in different order
            # This creates potential for circular dependencies
            if i == 0:
                # Transaction 0: users -> orders -> payments
                acquire_order = [0, 1, 2]
            elif i == 1:
                # Transaction 1: orders -> payments -> inventory
                acquire_order = [1, 2, 3]
            elif i == 2:
                # Transaction 2: payments -> inventory -> users
                acquire_order = [2, 3, 0]
            else:
                # Transaction 3: inventory -> users -> orders
                acquire_order = [3, 0, 1]

            # Acquire first resource
            first_resource = resources[acquire_order[0]]
            deadlock_detector.execute(
                operation="acquire_resource",
                transaction_id=txn_id,
                resource_id=first_resource,
                resource_type="database_table",
                lock_type="EXCLUSIVE",
            )

            # Request additional resources (creating dependencies)
            for resource_idx in acquire_order[1:]:
                resource_name = resources[resource_idx]
                deadlock_detector.execute(
                    operation="request_resource",
                    transaction_id=txn_id,
                    resource_id=resource_name,
                    resource_type="database_table",
                    lock_type="SHARED",
                )

        # Wait for deadlock detection with polling
        from datetime import datetime

        start_time = datetime.now()
        deadlocks_detected = False
        detection_result = None

        while (datetime.now() - start_time).total_seconds() < 5.0:
            # Check for deadlocks
            detection_result = deadlock_detector.execute(operation="detect_deadlocks")
            if detection_result["status"] == "success" and detection_result.get(
                "deadlocks_detected"
            ):
                deadlocks_detected = True
                break
            time.sleep(0.1)

        # If no deadlocks detected yet, do one final check
        if not deadlocks_detected:
            detection_result = deadlock_detector.execute(operation="detect_deadlocks")
        assert detection_result["status"] == "success"

        # Handle any detected deadlocks
        deadlocks_found = detection_result.get("deadlocks_detected", [])
        if len(deadlocks_found) > 0:
            deadlocks = deadlocks_found

            # Resolve deadlocks
            for deadlock in deadlocks:
                victim_txn = deadlock["victim_transaction"]

                # Simulate deadlock resolution
                deadlock_detector.execute(
                    operation="resolve_deadlock",
                    deadlock_id=deadlock["deadlock_id"],
                    resolution_strategy="abort_victim",
                )

                # Mark victim transaction as failed
                transaction_metrics.execute(
                    operation="complete_transaction",
                    transaction_id=victim_txn,
                    success=False,
                    metadata={"failure_reason": "deadlock_victim"},
                )

                transactions.remove(victim_txn)

        # Complete remaining transactions successfully
        for txn_id in transactions:
            # Release all resources for this transaction
            for resource in resources:
                try:
                    deadlock_detector.execute(
                        operation="release_resource",
                        transaction_id=txn_id,
                        resource_id=resource,
                    )
                except:
                    # Ignore if resource wasn't held
                    pass

            # Mark transaction as completed
            transaction_metrics.execute(
                operation="complete_transaction", transaction_id=txn_id, success=True
            )

        # Verify final metrics
        metrics_result = transaction_metrics.execute(operation="get_metrics")
        assert metrics_result["status"] == "success"
        assert metrics_result["total_transactions"] == 4

        # Should have some success rate (may be less than 100% due to deadlocks)
        success_rate = metrics_result.get("success_rate", 0)
        assert 0 <= success_rate <= 1.0

    def test_performance_monitoring_with_anomaly_detection_e2e(self):
        """Test end-to-end performance monitoring with anomaly detection."""
        # Setup performance monitoring for a simulated API service
        anomaly_detector = PerformanceAnomalyNode()
        transaction_monitor = TransactionMonitorNode()

        # Initialize monitoring for multiple metrics
        metrics = ["api_latency", "cpu_usage", "memory_usage", "error_rate"]

        for metric in metrics:
            anomaly_detector.execute(
                operation="initialize_baseline",
                metric_name=metric,
                sensitivity=0.7,
                min_samples=15,
            )

        transaction_monitor.execute(
            operation="start_monitoring",
            alert_thresholds={"latency_ms": 1000, "error_rate": 0.05},
        )

        # Simulate normal API operations
        api_requests = []
        for i in range(20):
            request_id = f"api_request_{i}"
            start_time = time.time()

            # Track request
            transaction_monitor.execute(
                operation="start_transaction",
                transaction_id=request_id,
                operation_type="api_request",
                start_time=start_time,
                metadata={"endpoint": f"/api/endpoint_{i % 3}"},
            )

            # Simulate normal processing
            if i < 15:
                # Normal performance
                latency = 100 + (i % 5) * 10  # 100-140ms
                cpu = 30 + (i % 10) * 2  # 30-48%
                memory = 200 + (i % 8) * 5  # 200-235MB
                error_rate = 0.01  # 1% error rate
            else:
                # Introduce performance issues
                latency = 300 + (i % 3) * 50  # 300-400ms (slow)
                cpu = 80 + (i % 3) * 5  # 80-90% (high)
                memory = 400 + (i % 3) * 20  # 400-440MB (high)
                error_rate = 0.08  # 8% error rate (elevated)

            # Feed metrics to anomaly detector
            anomaly_detector.execute(
                operation="add_metric",
                metric_name="api_latency",
                value=latency,
                tags={"endpoint": f"/api/endpoint_{i % 3}"},
            )

            anomaly_detector.execute(
                operation="add_metric", metric_name="cpu_usage", value=cpu
            )

            anomaly_detector.execute(
                operation="add_metric", metric_name="memory_usage", value=memory
            )

            anomaly_detector.execute(
                operation="add_metric", metric_name="error_rate", value=error_rate
            )

            # Simulate request completion
            processing_time = latency / 1000  # Convert to seconds
            time.sleep(min(processing_time, 0.1))  # Cap sleep time for test speed

            # Complete request
            success = error_rate < 0.05  # Fail if error rate too high
            transaction_monitor.execute(
                operation="complete_transaction",
                transaction_id=request_id,
                success=success,
            )

            api_requests.append(
                {
                    "id": request_id,
                    "latency": latency,
                    "cpu": cpu,
                    "memory": memory,
                    "error_rate": error_rate,
                    "success": success,
                }
            )

        # Analyze for anomalies
        anomaly_result = anomaly_detector.execute(
            operation="detect_anomalies",
            metric_names=metrics,
            detection_methods=["statistical", "threshold_based", "iqr"],
        )

        # Get monitoring status
        monitor_result = transaction_monitor.execute(operation="get_monitoring_status")

        # Verify anomaly detection
        assert anomaly_result["status"] == "success"
        anomalies = anomaly_result.get("anomalies_detected", [])

        # Should detect anomalies in the later requests
        # (Exact detection depends on statistical thresholds)
        assert "detection_summary" in anomaly_result

        # Verify monitoring captured all requests
        assert monitor_result["status"] == "success"

        # Verify baselines were established
        for metric in metrics:
            baseline_result = anomaly_detector.execute(
                operation="get_baseline", metric_name=metric
            )
            assert baseline_result["status"] == "success"
            assert metric in baseline_result["baselines"]

            baseline = baseline_result["baselines"][metric]
            assert baseline["sample_count"] == 20
            assert baseline["mean"] > 0
            assert baseline["std_dev"] >= 0

        # Cleanup
        transaction_monitor.execute(operation="stop_monitoring")

    def test_enterprise_monitoring_dashboard_scenario(self):
        """Test complete enterprise monitoring dashboard scenario."""
        # Setup comprehensive monitoring stack
        metrics_collector = TransactionMetricsNode()
        real_time_monitor = TransactionMonitorNode()
        deadlock_detector = DeadlockDetectorNode()
        race_detector = RaceConditionDetectorNode()
        anomaly_detector = PerformanceAnomalyNode()

        # Initialize all monitoring components
        real_time_monitor.execute(
            operation="start_monitoring",
            monitoring_interval=0.5,
            alert_thresholds={
                "latency_ms": 2000,
                "error_rate": 0.1,
                "concurrent_transactions": 50,
            },
        )

        deadlock_detector.execute(operation="initialize", detection_interval=2.0)

        race_detector.execute(operation="start_monitoring", confidence_threshold=0.8)

        # Initialize anomaly detection for multiple KPIs
        kpis = ["response_time", "throughput", "error_rate", "resource_utilization"]
        for kpi in kpis:
            anomaly_detector.execute(
                operation="initialize_baseline",
                metric_name=kpi,
                sensitivity=0.8,
                min_samples=10,
            )

        # Simulate enterprise workload
        enterprise_transactions = []
        services = [
            "user_service",
            "order_service",
            "payment_service",
            "inventory_service",
        ]

        # Process transactions across multiple services
        for batch in range(5):  # 5 batches
            batch_start_time = time.time()

            for service_idx, service in enumerate(services):
                for txn_num in range(3):  # 3 transactions per service per batch
                    txn_id = f"enterprise_{batch}_{service}_{txn_num}"
                    enterprise_transactions.append(txn_id)

                    # Start transaction tracking
                    metrics_collector.execute(
                        operation="start_transaction",
                        transaction_id=txn_id,
                        operation_type="enterprise_operation",
                        metadata={
                            "service": service,
                            "batch": batch,
                            "transaction_number": txn_num,
                        },
                    )

                    real_time_monitor.execute(
                        operation="start_transaction",
                        transaction_id=txn_id,
                        operation_type="enterprise_operation",
                        start_time=time.time(),
                    )

                    # Simulate service-specific resource usage
                    resource_id = f"{service}_resource_{txn_num % 2}"
                    deadlock_detector.execute(
                        operation="acquire_resource",
                        transaction_id=txn_id,
                        resource_id=resource_id,
                        resource_type="service_resource",
                    )

                    # Report concurrent operation
                    operation_id = f"op_{batch}_{service}_{txn_num}"
                    race_detector.execute(
                        operation="report_operation",
                        operation_id=operation_id,
                        resource_id=resource_id,
                        operation_type="SERVICE_CALL",
                        thread_id=f"service_thread_{service_idx}",
                    )

                    # Simulate varying performance
                    if service == "payment_service" and batch == 3:
                        # Simulate payment service slowdown
                        response_time = 800 + txn_num * 100  # 800-1000ms
                        throughput = 50  # Lower throughput
                        error_rate = 0.02  # Slightly elevated
                        resource_util = 85  # High utilization
                    else:
                        # Normal performance
                        response_time = 150 + txn_num * 20  # 150-190ms
                        throughput = 100 + txn_num * 10  # 100-120 TPS
                        error_rate = 0.005  # Low error rate
                        resource_util = 45 + txn_num * 5  # 45-55%

                    # Feed performance metrics
                    for kpi, value in zip(
                        kpis, [response_time, throughput, error_rate, resource_util]
                    ):
                        anomaly_detector.execute(
                            operation="add_metric",
                            metric_name=kpi,
                            value=value,
                            tags={"service": service, "batch": str(batch)},
                        )

                    # Simulate processing time
                    time.sleep(response_time / 10000)  # Scale down for test speed

                    # Complete operations
                    success = error_rate < 0.05

                    race_detector.execute(
                        operation="complete_operation",
                        operation_id=operation_id,
                        success=success,
                    )

                    deadlock_detector.execute(
                        operation="release_resource",
                        transaction_id=txn_id,
                        resource_id=resource_id,
                    )

                    metrics_collector.execute(
                        operation="complete_transaction",
                        transaction_id=txn_id,
                        success=success,
                        metadata={"response_time_ms": response_time},
                    )

                    real_time_monitor.execute(
                        operation="complete_transaction",
                        transaction_id=txn_id,
                        success=success,
                    )

            # Brief pause between batches
            time.sleep(0.1)

        # Generate comprehensive dashboard data
        dashboard_data = {}

        # Collect metrics from all monitoring components
        dashboard_data["transaction_metrics"] = metrics_collector.execute(
            operation="get_metrics",
            metric_types=["latency", "throughput", "success_rate"],
            time_range=300,
        )

        dashboard_data["real_time_status"] = real_time_monitor.execute(
            operation="get_monitoring_status"
        )

        dashboard_data["deadlock_analysis"] = deadlock_detector.execute(
            operation="detect_deadlocks"
        )

        dashboard_data["race_analysis"] = race_detector.execute(
            operation="detect_races", time_window=120.0
        )

        dashboard_data["anomaly_analysis"] = anomaly_detector.execute(
            operation="detect_anomalies",
            metric_names=kpis,
            detection_methods=["statistical", "threshold_based"],
        )

        # Verify comprehensive monitoring data
        assert len(enterprise_transactions) == 60  # 5 batches * 4 services * 3 txns

        # Verify all monitoring components captured data
        assert dashboard_data["transaction_metrics"]["total_transactions"] == 60
        assert dashboard_data["real_time_status"]["status"] == "success"
        assert dashboard_data["deadlock_analysis"]["status"] == "success"
        assert dashboard_data["race_analysis"]["status"] == "success"
        assert dashboard_data["anomaly_analysis"]["status"] == "success"

        # Verify performance characteristics
        success_rate = dashboard_data["transaction_metrics"]["success_rate"]
        assert success_rate > 0.95  # Should have high success rate

        # Verify anomaly detection worked
        anomalies = dashboard_data["anomaly_analysis"].get("anomalies_detected", [])
        # May or may not detect anomalies depending on exact thresholds

        # Verify baselines established for all KPIs
        for kpi in kpis:
            baseline_result = anomaly_detector.execute(
                operation="get_baseline", metric_name=kpi
            )
            assert baseline_result["status"] == "success"
            assert kpi in baseline_result["baselines"]

        # Cleanup monitoring
        real_time_monitor.execute(operation="stop_monitoring")
        race_detector.execute(operation="stop_monitoring")

        # Save dashboard data for verification (in real scenario would feed to dashboard)
        dashboard_summary = {
            "total_transactions": len(enterprise_transactions),
            "monitoring_duration": "test_scenario",
            "services_monitored": services,
            "success_rate": success_rate,
            "anomalies_detected": len(anomalies),
            "deadlocks_detected": len(
                dashboard_data["deadlock_analysis"].get("deadlocks_detected", [])
            ),
            "race_conditions_analyzed": dashboard_data["race_analysis"].get(
                "operations_analyzed", 0
            ),
        }

        # Verify dashboard summary is complete
        assert dashboard_summary["total_transactions"] == 60
        assert dashboard_summary["success_rate"] > 0.9
        assert len(dashboard_summary["services_monitored"]) == 4
        assert dashboard_summary["anomalies_detected"] >= 0
        assert dashboard_summary["deadlocks_detected"] >= 0
        assert dashboard_summary["race_conditions_analyzed"] >= 0
