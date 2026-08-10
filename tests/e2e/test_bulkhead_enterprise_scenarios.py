"""E2E tests for bulkhead pattern in enterprise scenarios.

Tier 3 tests - End-to-end testing with complete real infrastructure.
Tests complete business scenarios with PostgreSQL, Redis, and concurrent workloads.
NO MOCKING - uses real Docker services for enterprise validation.
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from src.kailash.core.resilience.bulkhead import (
    BulkheadManager,
    BulkheadPartition,
    BulkheadRejectionError,
    PartitionConfig,
    PartitionType,
    execute_with_bulkhead,
    get_bulkhead_manager,
)
from src.kailash.nodes.data.sql import SQLDatabaseNode

from tests.utils.docker_config import get_postgres_connection_string, get_redis_url


@pytest.mark.e2e
@pytest.mark.requires_docker
class TestBulkheadEnterpriseWorkflowE2E:
    """Test bulkhead pattern in complete enterprise workflow scenarios."""

    @pytest.fixture
    def postgres_connection_string(self):
        """Get PostgreSQL connection string from Docker config."""
        return get_postgres_connection_string("kailash_test")

    @pytest.fixture
    def enterprise_bulkhead_manager(self):
        """Create enterprise-configured bulkhead manager."""
        return BulkheadManager()

    @pytest.mark.asyncio
    async def test_enterprise_data_processing_pipeline_e2e(
        self, postgres_connection_string, enterprise_bulkhead_manager
    ):
        """Test complete enterprise data processing pipeline with bulkhead isolation."""
        # Create enterprise partitions for different workload types

        # High-priority customer data partition
        customer_config = PartitionConfig(
            name="customer_data",
            partition_type=PartitionType.CRITICAL,
            max_concurrent_operations=3,
            timeout=15,
            priority=10,
            queue_size=20,
        )
        customer_partition = enterprise_bulkhead_manager.create_partition(
            customer_config
        )

        # Analytics partition for background processing
        analytics_config = PartitionConfig(
            name="analytics",
            partition_type=PartitionType.BACKGROUND,
            max_concurrent_operations=5,
            timeout=60,
            priority=2,
            queue_size=100,
        )
        analytics_partition = enterprise_bulkhead_manager.create_partition(
            analytics_config
        )

        # Reporting partition for business intelligence
        reporting_config = PartitionConfig(
            name="reporting",
            partition_type=PartitionType.IO_BOUND,
            max_concurrent_operations=4,
            timeout=30,
            priority=5,
            queue_size=50,
        )
        reporting_partition = enterprise_bulkhead_manager.create_partition(
            reporting_config
        )

        # Setup enterprise tables
        sql_node = SQLDatabaseNode(connection_string=postgres_connection_string)
        test_id = int(time.time())  # Unique test run identifier

        setup_queries = [
            f"""
            CREATE TABLE IF NOT EXISTS enterprise_customers_{test_id} (
                id SERIAL PRIMARY KEY,
                customer_id VARCHAR(50),
                name VARCHAR(100),
                tier VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS enterprise_transactions_{test_id} (
                id SERIAL PRIMARY KEY,
                customer_id VARCHAR(50),
                amount DECIMAL(10,2),
                transaction_type VARCHAR(50),
                processed_by VARCHAR(50),
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS enterprise_analytics_{test_id} (
                id SERIAL PRIMARY KEY,
                metric_name VARCHAR(100),
                metric_value DECIMAL(15,4),
                partition_used VARCHAR(50),
                calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ]

        def execute_sql(query):
            return sql_node.execute(query=query)

        # Setup database schema
        for query in setup_queries:
            await customer_partition.execute(execute_sql, query)

        # Simulate enterprise workloads running concurrently

        # 1. Critical customer data operations (high priority)
        customer_operations = []
        for i in range(5):
            query = f"""
            INSERT INTO enterprise_customers_{test_id} (customer_id, name, tier)
            VALUES ('CUST_{i:03d}', 'Customer {i}', 'PREMIUM')
            """
            customer_operations.append(customer_partition.execute(execute_sql, query))

        # 2. Background analytics processing (low priority, can be delayed)
        analytics_operations = []
        for i in range(8):
            query = f"""
            INSERT INTO enterprise_analytics_{test_id} (metric_name, metric_value, partition_used)
            VALUES ('daily_revenue_calc_{i}', {(i + 1) * 1000.50}, 'analytics')
            """
            analytics_operations.append(analytics_partition.execute(execute_sql, query))

        # 3. Real-time transaction processing (medium priority)
        transaction_operations = []
        for i in range(6):
            query = f"""
            INSERT INTO enterprise_transactions_{test_id} (customer_id, amount, transaction_type, processed_by)
            VALUES ('CUST_{i % 5:03d}', {(i + 1) * 25.75}, 'PURCHASE', 'reporting')
            """
            transaction_operations.append(
                reporting_partition.execute(execute_sql, query)
            )

        # Execute all workloads concurrently - simulating real enterprise load
        all_operations = (
            customer_operations + analytics_operations + transaction_operations
        )

        start_time = time.time()
        results = await asyncio.gather(*all_operations, return_exceptions=True)
        execution_time = time.time() - start_time

        # Verify all operations completed successfully
        successful_results = [r for r in results if not isinstance(r, Exception)]
        failed_results = [r for r in results if isinstance(r, Exception)]

        assert len(successful_results) >= 15  # Expect most to succeed
        assert len(failed_results) <= 4  # Allow some failures under high load

        # Validate enterprise metrics across all partitions
        customer_status = customer_partition.get_status()
        analytics_status = analytics_partition.get_status()
        reporting_status = reporting_partition.get_status()

        # Customer partition should have handled critical operations efficiently
        assert (
            customer_status["metrics"]["total_operations"] >= 8
        )  # Setup + 5 customer ops
        assert customer_status["metrics"]["success_rate"] >= 0.8

        # Analytics partition should have processed background work
        assert analytics_status["metrics"]["total_operations"] >= 8

        # Reporting partition should have handled transaction processing
        assert reporting_status["metrics"]["total_operations"] >= 6

        # Verify data consistency in enterprise database
        verification_queries = [
            f"SELECT COUNT(*) as count FROM enterprise_customers_{test_id}",
            f"SELECT COUNT(*) as count FROM enterprise_analytics_{test_id}",
            f"SELECT COUNT(*) as count FROM enterprise_transactions_{test_id}",
        ]

        verification_results = []
        for query in verification_queries:
            result = await customer_partition.execute(execute_sql, query)
            verification_results.append(result["data"][0]["count"])

        # Should have data in all tables
        assert all(count > 0 for count in verification_results)

        # Performance validation - enterprise SLA requirements
        assert execution_time < 30  # Complete enterprise pipeline within 30 seconds

        # Cleanup enterprise test data
        cleanup_queries = [
            f"DROP TABLE enterprise_customers_{test_id}",
            f"DROP TABLE enterprise_transactions_{test_id}",
            f"DROP TABLE enterprise_analytics_{test_id}",
        ]
        for query in cleanup_queries:
            await customer_partition.execute(execute_sql, query)

    @pytest.mark.asyncio
    async def test_bulkhead_under_extreme_concurrent_load_e2e(
        self, postgres_connection_string
    ):
        """Test bulkhead behavior under extreme concurrent load - enterprise stress test."""
        # Create stress test partitions with different characteristics
        stress_configs = [
            PartitionConfig(
                name="high_throughput",
                partition_type=PartitionType.IO_BOUND,
                max_concurrent_operations=10,
                timeout=20,
                queue_size=200,
                circuit_breaker_enabled=True,
            ),
            PartitionConfig(
                name="low_latency",
                partition_type=PartitionType.CRITICAL,
                max_concurrent_operations=3,
                timeout=5,
                queue_size=10,
                circuit_breaker_enabled=True,
            ),
            PartitionConfig(
                name="batch_processing",
                partition_type=PartitionType.BACKGROUND,
                max_concurrent_operations=15,
                timeout=120,
                queue_size=500,
                circuit_breaker_enabled=False,
            ),
        ]

        manager = BulkheadManager()
        partitions = {}
        for config in stress_configs:
            partitions[config.name] = manager.create_partition(config)

        # Setup stress test infrastructure
        sql_node = SQLDatabaseNode(connection_string=postgres_connection_string)
        stress_test_id = int(time.time())

        setup_sql = f"""
        CREATE TABLE IF NOT EXISTS stress_test_{stress_test_id} (
            id SERIAL PRIMARY KEY,
            partition_name VARCHAR(50),
            operation_id INTEGER,
            worker_thread VARCHAR(20),
            latency_ms INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """

        def execute_sql(query):
            return sql_node.execute(query=query)

        # Setup test table
        await partitions["high_throughput"].execute(execute_sql, setup_sql)

        # Generate extreme concurrent load - 100 operations across partitions
        stress_operations = []

        # High throughput partition - 60 operations
        for i in range(60):
            query = f"""
            INSERT INTO stress_test_{stress_test_id}
            (partition_name, operation_id, worker_thread, latency_ms)
            VALUES ('high_throughput', {i}, 'worker_{i % 10}', {(i % 5) * 10})
            """
            stress_operations.append(
                partitions["high_throughput"].execute(execute_sql, query)
            )

        # Low latency partition - 20 operations (should complete fast)
        for i in range(20):
            query = f"""
            INSERT INTO stress_test_{stress_test_id}
            (partition_name, operation_id, worker_thread, latency_ms)
            VALUES ('low_latency', {i}, 'priority_{i}', 1)
            """
            stress_operations.append(
                partitions["low_latency"].execute(execute_sql, query)
            )

        # Batch processing partition - 20 operations (can take longer)
        for i in range(20):
            query = f"""
            INSERT INTO stress_test_{stress_test_id}
            (partition_name, operation_id, worker_thread, latency_ms)
            VALUES ('batch_processing', {i}, 'batch_{i}', {(i % 3) * 20})
            """
            stress_operations.append(
                partitions["batch_processing"].execute(execute_sql, query)
            )

        # Execute stress test
        start_time = time.time()
        results = await asyncio.gather(*stress_operations, return_exceptions=True)
        total_execution_time = time.time() - start_time

        # Analyze stress test results
        successful_ops = [r for r in results if not isinstance(r, Exception)]
        failed_ops = [r for r in results if isinstance(r, Exception)]
        rejection_errors = [
            r for r in failed_ops if isinstance(r, BulkheadRejectionError)
        ]

        # Enterprise stress test validation
        success_rate = len(successful_ops) / len(results)

        # Should handle majority of operations successfully
        assert success_rate >= 0.7  # At least 70% success under extreme load

        # Low latency partition should maintain its SLA
        low_latency_status = partitions["low_latency"].get_status()
        if low_latency_status["metrics"]["total_operations"] > 0:
            assert (
                low_latency_status["metrics"]["avg_execution_time"] < 2.0
            )  # < 2 seconds avg

        # High throughput partition should process many operations
        high_throughput_status = partitions["high_throughput"].get_status()
        assert high_throughput_status["metrics"]["total_operations"] >= 20

        # Verify circuit breaker behavior under load
        if rejection_errors:
            # If we have rejections, circuit breakers are working correctly
            assert len(rejection_errors) <= 30  # Should not reject everything

        # Check final data consistency
        final_count = await partitions["high_throughput"].execute(
            execute_sql, f"SELECT COUNT(*) as count FROM stress_test_{stress_test_id}"
        )
        assert final_count["data"][0]["count"] >= 50  # Significant data processed

        # Performance requirements for enterprise deployment
        assert total_execution_time < 60  # Complete stress test within 1 minute

        # Verify partition isolation - each partition should have handled its workload
        all_status = manager.get_all_status()
        for partition_name, status in all_status.items():
            if partition_name in partitions:
                assert status["metrics"]["total_operations"] >= 0
                # No partition should have 100% failure rate
                if status["metrics"]["total_operations"] > 0:
                    assert status["metrics"]["success_rate"] > 0

        # Cleanup stress test data
        await partitions["high_throughput"].execute(
            execute_sql, f"DROP TABLE stress_test_{stress_test_id}"
        )

    @pytest.mark.asyncio
    async def test_bulkhead_enterprise_failure_recovery_e2e(
        self, postgres_connection_string
    ):
        """Test enterprise failure recovery scenarios with bulkhead pattern."""
        # Create failure-resilient partitions
        resilient_config = PartitionConfig(
            name="resilient_ops",
            partition_type=PartitionType.IO_BOUND,
            max_concurrent_operations=5,
            timeout=10,
            circuit_breaker_enabled=True,
            queue_size=20,
        )

        critical_config = PartitionConfig(
            name="critical_ops",
            partition_type=PartitionType.CRITICAL,
            max_concurrent_operations=2,
            timeout=5,
            circuit_breaker_enabled=True,
            queue_size=5,
        )

        manager = BulkheadManager()
        resilient_partition = manager.create_partition(resilient_config)
        critical_partition = manager.create_partition(critical_config)

        sql_node = SQLDatabaseNode(connection_string=postgres_connection_string)
        recovery_test_id = int(time.time())

        def execute_sql(query):
            return sql_node.execute(query=query)

        def failing_operation():
            # Simulate database failure
            return sql_node.execute(
                query="SELECT * FROM nonexistent_table_failure_test"
            )

        def successful_operation():
            return sql_node.execute(
                query=f"SELECT 'recovery_success' as status, {recovery_test_id} as test_id"
            )

        # Phase 1: Induce failures to trigger circuit breaker
        failure_operations = []
        for i in range(8):  # More failures than circuit breaker threshold
            failure_operations.append(resilient_partition.execute(failing_operation))

        # Execute failure operations (expecting failures)
        from src.kailash.core.exceptions import NodeExecutionError

        failure_results = []
        for op in failure_operations:
            try:
                result = await op
                failure_results.append(result)
            except (NodeExecutionError, Exception):
                failure_results.append("FAILED")

        # Verify failures were recorded
        resilient_status = resilient_partition.get_status()
        assert resilient_status["metrics"]["failed_operations"] >= 5

        # Phase 2: Test that critical partition remains unaffected
        critical_operations = []
        for i in range(3):
            critical_operations.append(critical_partition.execute(successful_operation))

        critical_results = await asyncio.gather(*critical_operations)

        # Critical partition should remain functional despite other failures
        assert len(critical_results) == 3
        assert all("data" in result for result in critical_results)

        # Phase 3: Test recovery - resilient partition should still handle successful operations
        recovery_operations = []
        for i in range(5):
            recovery_operations.append(
                resilient_partition.execute(successful_operation)
            )

        recovery_results = await asyncio.gather(*recovery_operations)

        # Recovery should work
        assert len(recovery_results) == 5
        assert all("data" in result for result in recovery_results)

        # Verify enterprise metrics show proper failure handling and recovery
        final_resilient_status = resilient_partition.get_status()
        final_critical_status = critical_partition.get_status()

        # Resilient partition should show both failures and recoveries
        assert (
            final_resilient_status["metrics"]["total_operations"] >= 13
        )  # 8 failures + 5 recovery
        assert final_resilient_status["metrics"]["failed_operations"] >= 5
        assert final_resilient_status["metrics"]["successful_operations"] >= 5

        # Critical partition should show only successes
        assert final_critical_status["metrics"]["total_operations"] >= 3
        assert final_critical_status["metrics"]["successful_operations"] >= 3
        assert final_critical_status["metrics"]["success_rate"] >= 0.9

        # Verify circuit breaker behavior
        if final_resilient_status["circuit_breaker"]:
            cb_status = final_resilient_status["circuit_breaker"]
            assert "state" in cb_status
            assert "failure_count" in cb_status


@pytest.mark.e2e
@pytest.mark.requires_docker
class TestBulkheadEnterpriseIntegrationE2E:
    """Test bulkhead integration with complete enterprise infrastructure."""

    @pytest.fixture
    def postgres_connection_string(self):
        """Get PostgreSQL connection string from Docker config."""
        return get_postgres_connection_string("kailash_test")

    @pytest.mark.asyncio
    async def test_global_bulkhead_manager_enterprise_deployment(
        self, postgres_connection_string
    ):
        """Test global bulkhead manager in enterprise deployment scenario."""
        # Simulate enterprise application using global bulkhead manager
        sql_node = SQLDatabaseNode(connection_string=postgres_connection_string)
        enterprise_test_id = int(time.time())

        # Enterprise operations using global manager
        async def customer_service_operation():
            def db_query():
                return sql_node.execute(
                    query=f"SELECT 'customer_service' as service, {enterprise_test_id} as deployment_id"
                )

            return await execute_with_bulkhead("critical", db_query)

        async def analytics_service_operation():
            def db_query():
                return sql_node.execute(
                    query=f"SELECT 'analytics' as service, {enterprise_test_id} as deployment_id"
                )

            return await execute_with_bulkhead("background", db_query)

        async def reporting_service_operation():
            def db_query():
                return sql_node.execute(
                    query=f"SELECT 'reporting' as service, {enterprise_test_id} as deployment_id"
                )

            return await execute_with_bulkhead("database", db_query)

        # Simulate enterprise microservices making concurrent requests
        enterprise_operations = []

        # Customer service operations (high priority)
        for i in range(5):
            enterprise_operations.append(customer_service_operation())

        # Analytics operations (background priority)
        for i in range(10):
            enterprise_operations.append(analytics_service_operation())

        # Reporting operations (normal priority)
        for i in range(7):
            enterprise_operations.append(reporting_service_operation())

        # Execute enterprise workload
        start_time = time.time()
        enterprise_results = await asyncio.gather(*enterprise_operations)
        total_time = time.time() - start_time

        # Validate enterprise deployment
        assert len(enterprise_results) == 22
        assert all("data" in result for result in enterprise_results)

        # Verify service isolation through global manager
        global_manager = get_bulkhead_manager()
        global_status = global_manager.get_all_status()

        # Each partition should have handled its respective service operations
        assert "critical" in global_status
        assert "background" in global_status
        assert "database" in global_status

        critical_ops = global_status["critical"]["metrics"]["total_operations"]
        background_ops = global_status["background"]["metrics"]["total_operations"]
        database_ops = global_status["database"]["metrics"]["total_operations"]

        # Should show operations distributed across partitions
        assert critical_ops >= 5  # Customer service operations
        assert background_ops >= 10  # Analytics operations
        assert database_ops >= 7  # Reporting operations

        # Enterprise performance requirements
        assert total_time < 15  # All enterprise operations within 15 seconds

        # High availability requirement - success rate should be very high
        for partition_name, status in global_status.items():
            if status["metrics"]["total_operations"] > 0:
                assert status["metrics"]["success_rate"] >= 0.95  # 95% uptime SLA
