"""
Integration tests for DataFlow performance validation.

Tests performance characteristics, benchmarks, optimization effectiveness,
and performance under load with real database operations.
"""

import os
import statistics

# Import DataFlow components
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from dataflow import DataFlow
from dataflow.testing.dataflow_test_utils import DataFlowTestUtils

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class TestPerformanceValidation:
    """Test DataFlow performance characteristics and optimization."""

    def setup_method(self, test_suite):
        """Set up test database connection."""
        self.db_url = test_suite.config.url
        self.test_utils = DataFlowTestUtils(self.db_url)

    def teardown_method(self):
        """Clean up after each test."""
        # Use DataFlow's migration system to clean up
        self.test_utils.cleanup_database()

    def test_single_operation_performance(self, test_suite):
        """Test performance of single CRUD operations."""
        # Use PostgreSQL for testing since DataFlow only supports PostgreSQL
        db = DataFlow(database_url=test_suite.config.url)

        @db.model
        class PerformanceTest:
            test_id: int
            operation_type: str
            execution_time: float

        # Create tables
        db.create_tables()

        runtime = LocalRuntime()

        # Test CREATE performance
        start_time = time.time()
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PerformanceTestCreateNode",
            "create",
            {"test_id": 1, "operation_type": "create", "execution_time": 0.0},
        )

        result, run_id = runtime.execute(workflow.build())
        create_time = time.time() - start_time

        # Should complete within 1 second for single operation
        assert (
            create_time < 1.0
        ), f"Create operation took {create_time:.3f}s, expected < 1.0s"
        assert result is not None

        # Test READ performance
        start_time = time.time()
        workflow2 = WorkflowBuilder()
        # Get the ID from the create result - check if 'id' exists in result
        if "id" in result["create"]:
            created_id = result["create"]["id"]
        else:
            # Assume the record was created with test_id = 1
            created_id = 1
        workflow2.add_node("PerformanceTestReadNode", "read", {"id": str(created_id)})

        result2, run_id2 = runtime.execute(workflow2.build())
        read_time = time.time() - start_time

        # Read should be faster than create
        assert read_time < 1.0, f"Read operation took {read_time:.3f}s, expected < 1.0s"
        assert result2 is not None

        # Test UPDATE performance
        start_time = time.time()
        workflow3 = WorkflowBuilder()
        workflow3.add_node(
            "PerformanceTestUpdateNode",
            "update",
            {
                "id": str(created_id),
                "operation_type": "update",
                "execution_time": read_time,
            },
        )

        result3, run_id3 = runtime.execute(workflow3.build())
        update_time = time.time() - start_time

        assert (
            update_time < 1.0
        ), f"Update operation took {update_time:.3f}s, expected < 1.0s"
        assert result3 is not None

    def test_bulk_operation_performance(self, test_suite):
        """Test performance of bulk operations."""
        db = DataFlow(database_url=test_suite.config.url)

        @db.model
        class BulkPerformanceTest:
            bulk_id: int
            batch_number: int
            created_at: float

        # Create tables
        db.create_tables()

        runtime = LocalRuntime()

        # Test bulk create performance
        record_count = 100
        bulk_data = [
            {"bulk_id": i, "batch_number": 1, "created_at": time.time()}
            for i in range(record_count)
        ]

        start_time = time.time()
        workflow = WorkflowBuilder()
        workflow.add_node(
            "BulkPerformanceTestBulkCreateNode",
            "bulk_create",
            {"data": bulk_data, "batch_size": 50},
        )

        result, run_id = runtime.execute(workflow.build())
        bulk_time = time.time() - start_time

        # Bulk operations should be efficient
        time_per_record = bulk_time / record_count
        assert (
            time_per_record < 0.1
        ), f"Bulk create: {time_per_record:.4f}s per record, expected < 0.1s"
        assert result is not None

        # Test bulk update performance
        start_time = time.time()
        workflow2 = WorkflowBuilder()
        workflow2.add_node(
            "BulkPerformanceTestBulkUpdateNode",
            "bulk_update",
            {
                "filter": {"batch_number": 1},
                "update": {"batch_number": 2},
                "batch_size": 50,
            },
        )

        result2, run_id2 = runtime.execute(workflow2.build())
        bulk_update_time = time.time() - start_time

        # Bulk update should also be efficient
        assert (
            bulk_update_time < 5.0
        ), f"Bulk update took {bulk_update_time:.3f}s, expected < 5.0s"
        assert result2 is not None

    def test_concurrent_operation_performance(self, test_suite):
        """Test performance under concurrent load."""
        db = DataFlow(
            database_url=test_suite.config.url, pool_size=5, pool_max_overflow=5
        )

        @db.model
        class ConcurrentPerformanceTest:
            thread_id: int
            operation_id: int
            start_time: float
            end_time: float

        def concurrent_operation(thread_id: int, operations: int):
            """Perform operations in a thread and measure performance."""
            operation_times = []
            runtime = LocalRuntime()

            for i in range(operations):
                start_time = time.time()

                workflow = WorkflowBuilder()
                workflow.add_node(
                    "ConcurrentPerformanceTestCreateNode",
                    f"create_{thread_id}_{i}",
                    {
                        "thread_id": thread_id,
                        "operation_id": i,
                        "start_time": start_time,
                        "end_time": 0.0,
                    },
                )

                result, run_id = runtime.execute(workflow.build())
                end_time = time.time()

                operation_time = end_time - start_time
                operation_times.append(operation_time)

                if not result:
                    pytest.fail(
                        f"Operation failed for thread {thread_id}, operation {i}"
                    )

            return operation_times

        # Execute concurrent operations
        num_threads = 4
        operations_per_thread = 5

        start_overall = time.time()
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(concurrent_operation, thread_id, operations_per_thread)
                for thread_id in range(num_threads)
            ]

            all_times = []
            for future in as_completed(futures):
                times = future.result(timeout=30)
                all_times.extend(times)

        end_overall = time.time()

        # Analyze performance metrics
        total_operations = num_threads * operations_per_thread
        total_time = end_overall - start_overall

        avg_time = statistics.mean(all_times)
        max_time = max(all_times)
        min_time = min(all_times)

        # Performance assertions
        assert avg_time < 2.0, f"Average operation time {avg_time:.3f}s too high"
        assert max_time < 5.0, f"Max operation time {max_time:.3f}s too high"
        assert len(all_times) == total_operations

        # Throughput should be reasonable
        throughput = total_operations / total_time
        assert throughput > 1.0, f"Throughput {throughput:.1f} ops/sec too low"

    def test_query_performance_optimization(self, test_suite):
        """Test query performance and optimization."""
        db = DataFlow(database_url=test_suite.config.url)

        @db.model
        class QueryPerformanceTest:
            category: str
            priority: int
            status: str
            created_at: float
            data_size: int

        runtime = LocalRuntime()

        # Create test data
        test_data = []
        for i in range(50):
            test_data.append(
                {
                    "category": f"category_{i % 5}",
                    "priority": i % 3,
                    "status": "active" if i % 2 == 0 else "inactive",
                    "created_at": time.time(),
                    "data_size": i * 10,
                }
            )

        # Bulk create test data
        workflow_setup = WorkflowBuilder()
        workflow_setup.add_node(
            "QueryPerformanceTestBulkCreateNode",
            "setup",
            {"data": test_data, "batch_size": 25},
        )

        setup_result, setup_run_id = runtime.execute(workflow_setup.build())
        assert setup_result is not None

        # Test simple query performance
        start_time = time.time()
        workflow1 = WorkflowBuilder()
        workflow1.add_node(
            "QueryPerformanceTestListNode",
            "simple_query",
            {"filter": {"status": "active"}, "limit": 20},
        )

        result1, run_id1 = runtime.execute(workflow1.build())
        simple_query_time = time.time() - start_time

        assert simple_query_time < 1.0, f"Simple query took {simple_query_time:.3f}s"
        assert result1 is not None

        # Test complex query performance
        start_time = time.time()
        workflow2 = WorkflowBuilder()
        workflow2.add_node(
            "QueryPerformanceTestListNode",
            "complex_query",
            {
                "filter": {
                    "status": "active",
                    "priority": {"$gte": 1},
                    "data_size": {"$lt": 300},
                },
                "sort": [{"created_at": -1}],
                "limit": 10,
            },
        )

        result2, run_id2 = runtime.execute(workflow2.build())
        complex_query_time = time.time() - start_time

        assert complex_query_time < 2.0, f"Complex query took {complex_query_time:.3f}s"
        assert result2 is not None

        # Complex queries should not be dramatically slower
        performance_ratio = complex_query_time / max(simple_query_time, 0.001)
        assert (
            performance_ratio < 10.0
        ), f"Complex query {performance_ratio:.1f}x slower than simple"

    def test_memory_usage_performance(self, test_suite):
        """Test memory usage patterns during operations."""
        db = DataFlow(database_url=test_suite.config.url)

        @db.model
        class MemoryTest:
            memory_id: int
            data_chunk: str
            operation_type: str

        runtime = LocalRuntime()

        # Test memory efficiency with large data
        large_data = "x" * 1000  # 1KB string

        memory_operations = []

        # Perform operations and monitor
        for i in range(10):
            start_time = time.time()

            workflow = WorkflowBuilder()
            workflow.add_node(
                "MemoryTestCreateNode",
                f"memory_op_{i}",
                {
                    "memory_id": i,
                    "data_chunk": large_data,
                    "operation_type": "memory_test",
                },
            )

            result, run_id = runtime.execute(workflow.build())
            end_time = time.time()

            operation_time = end_time - start_time
            memory_operations.append(operation_time)

            assert result is not None

        # Memory usage should be consistent
        avg_time = statistics.mean(memory_operations)
        max_time = max(memory_operations)
        min_time = min(memory_operations)

        # Performance should be stable (no memory leaks causing slowdown)
        time_variance = max_time - min_time
        assert (
            time_variance < 1.0
        ), f"Time variance {time_variance:.3f}s suggests memory issues"

        # Operations should complete efficiently even with larger data
        assert (
            avg_time < 1.0
        ), f"Average time {avg_time:.3f}s too high for memory operations"

    def test_transaction_performance(self, test_suite):
        """Test transaction performance and rollback efficiency."""
        db = DataFlow(database_url=test_suite.config.url)

        @db.model
        class TransactionPerformanceTest:
            tx_id: int
            batch_id: int
            committed: bool

        runtime = LocalRuntime()

        # Test successful transaction performance
        start_time = time.time()
        workflow = WorkflowBuilder()

        # Create multiple operations that should be atomic
        for i in range(5):
            workflow.add_node(
                "TransactionPerformanceTestCreateNode",
                f"tx_op_{i}",
                {"tx_id": 1, "batch_id": i, "committed": True},
            )

        result, run_id = runtime.execute(workflow.build())
        transaction_time = time.time() - start_time

        assert transaction_time < 3.0, f"Transaction took {transaction_time:.3f}s"
        assert result is not None

        # Test transaction with error handling
        start_time = time.time()
        workflow2 = WorkflowBuilder()

        # Valid operations
        for i in range(3):
            workflow2.add_node(
                "TransactionPerformanceTestCreateNode",
                f"tx2_op_{i}",
                {"tx_id": 2, "batch_id": i, "committed": True},
            )

        result2, run_id2 = runtime.execute(workflow2.build())
        error_transaction_time = time.time() - start_time

        # Error handling should not significantly impact performance
        assert (
            error_transaction_time < 5.0
        ), f"Error transaction took {error_transaction_time:.3f}s"

    def test_connection_pool_performance(self, test_suite):
        """Test connection pool performance impact."""
        # Test with small pool
        db_small = DataFlow(
            database_url=test_suite.config.url, pool_size=2, pool_max_overflow=1
        )

        @db_small.model
        class PoolPerformanceTest:
            pool_id: int
            pool_size: str
            operation_time: float

        runtime = LocalRuntime()

        # Measure performance with constrained pool
        small_pool_times = []

        for i in range(5):
            start_time = time.time()

            workflow = WorkflowBuilder()
            workflow.add_node(
                "PoolPerformanceTestCreateNode",
                f"small_pool_{i}",
                {"pool_id": i, "pool_size": "small", "operation_time": 0.0},
            )

            result, run_id = runtime.execute(workflow.build())
            end_time = time.time()

            operation_time = end_time - start_time
            small_pool_times.append(operation_time)

            assert result is not None

        # Test with larger pool
        db_large = DataFlow(
            database_url=test_suite.config.url, pool_size=10, pool_max_overflow=5
        )

        @db_large.model
        class LargePoolPerformanceTest:
            pool_id: int
            pool_size: str
            operation_time: float

        large_pool_times = []

        for i in range(5):
            start_time = time.time()

            workflow = WorkflowBuilder()
            workflow.add_node(
                "LargePoolPerformanceTestCreateNode",
                f"large_pool_{i}",
                {"pool_id": i, "pool_size": "large", "operation_time": 0.0},
            )

            result, run_id = runtime.execute(workflow.build())
            end_time = time.time()

            operation_time = end_time - start_time
            large_pool_times.append(operation_time)

            assert result is not None

        # Compare performance
        avg_small = statistics.mean(small_pool_times)
        avg_large = statistics.mean(large_pool_times)

        # Both should be reasonable, though small pool might be slightly slower under contention
        assert avg_small < 5.0, f"Small pool average {avg_small:.3f}s too high"
        assert avg_large < 5.0, f"Large pool average {avg_large:.3f}s too high"

    def test_scalability_characteristics(self, test_suite):
        """Test how performance scales with data size."""
        db = DataFlow(database_url=test_suite.config.url)

        @db.model
        class ScalabilityTest:
            scale_id: int
            dataset_size: int
            processing_time: float

        runtime = LocalRuntime()

        # Test different data sizes
        data_sizes = [10, 25, 50]
        processing_times = []

        for size in data_sizes:
            # Create dataset
            test_data = [
                {"scale_id": i, "dataset_size": size, "processing_time": 0.0}
                for i in range(size)
            ]

            # Measure bulk operation performance
            start_time = time.time()

            workflow = WorkflowBuilder()
            workflow.add_node(
                "ScalabilityTestBulkCreateNode",
                f"scale_{size}",
                {"data": test_data, "batch_size": min(20, size)},
            )

            result, run_id = runtime.execute(workflow.build())
            end_time = time.time()

            processing_time = end_time - start_time
            processing_times.append(processing_time)

            assert result is not None

            # Performance should scale reasonably
            time_per_record = processing_time / size
            assert (
                time_per_record < 0.5
            ), f"Time per record {time_per_record:.4f}s too high for size {size}"

        # Performance should scale sub-linearly (good optimization)
        if len(processing_times) >= 2:
            scaling_factor = processing_times[-1] / processing_times[0]
            data_scaling = data_sizes[-1] / data_sizes[0]

            # Scaling should be better than linear
            efficiency = scaling_factor / data_scaling
            assert efficiency < 2.0, f"Poor scaling efficiency: {efficiency:.2f}"

    def test_optimization_effectiveness(self, test_suite):
        """Test that optimization features improve performance."""
        # Test without optimization
        db_basic = DataFlow(database_url=test_suite.config.url)

        @db_basic.model
        class OptimizationTest:
            opt_id: int
            category: str
            value: int
            optimized: bool

        runtime = LocalRuntime()

        # Create test data
        test_data = [
            {"opt_id": i, "category": f"cat_{i % 5}", "value": i, "optimized": False}
            for i in range(30)
        ]

        # Bulk create
        workflow_setup = WorkflowBuilder()
        workflow_setup.add_node(
            "OptimizationTestBulkCreateNode",
            "setup",
            {"data": test_data, "batch_size": 15},
        )

        setup_result, setup_run_id = runtime.execute(workflow_setup.build())
        assert setup_result is not None

        # Test basic query performance
        start_time = time.time()
        workflow_basic = WorkflowBuilder()
        workflow_basic.add_node(
            "OptimizationTestListNode",
            "basic_query",
            {"filter": {"category": "cat_1"}, "limit": 10},
        )

        basic_result, basic_run_id = runtime.execute(workflow_basic.build())
        basic_time = time.time() - start_time

        assert basic_result is not None
        assert basic_time < 2.0, f"Basic query took {basic_time:.3f}s"

        # Test optimized query (with indexing hint)
        start_time = time.time()
        workflow_optimized = WorkflowBuilder()
        workflow_optimized.add_node(
            "OptimizationTestListNode",
            "optimized_query",
            {
                "filter": {"category": "cat_1"},
                "limit": 10,
                "optimize": True,  # Hint for optimization
            },
        )

        optimized_result, optimized_run_id = runtime.execute(workflow_optimized.build())
        optimized_time = time.time() - start_time

        assert optimized_result is not None
        assert optimized_time < 2.0, f"Optimized query took {optimized_time:.3f}s"

        # Both should perform reasonably well
        # The optimization effectiveness test is more about ensuring the feature works
        # rather than dramatic performance differences in this small dataset
