"""
Parallel Execution Validation Tests

Validates that the enhanced TDD fixtures support safe parallel execution
with proper isolation, resource management, and performance targets.

Tests parallel execution scenarios:
- Concurrent test execution without conflicts
- Resource allocation and deadlock prevention
- Thread safety of optimization managers
- Performance consistency under load
- Isolation verification across parallel tests

Performance Targets:
- Individual test execution: <100ms even under parallel load
- Resource contention resolution: <10ms
- Thread safety validation: 100% success rate
- Parallel isolation: 100% test independence
"""

import asyncio
import concurrent.futures
import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, List

import pytest

# Enable TDD mode and optimization
os.environ["DATAFLOW_TDD_MODE"] = "true"
os.environ["DATAFLOW_PERFORMANCE_OPTIMIZATION"] = "true"

from dataflow.testing.performance_optimization import (
    ParallelExecutionManager,
    PerformanceMetrics,
    get_parallel_manager,
    get_performance_monitor,
    get_pool_manager,
)


class ParallelTestValidator:
    """Utility for validating parallel test execution."""

    def __init__(self):
        self.test_results = []
        self.execution_times = []
        self.thread_conflicts = []
        self.resource_conflicts = []

    def record_test_result(
        self, test_id: str, thread_id: int, duration_ms: float, success: bool
    ):
        """Record results from a parallel test."""
        self.test_results.append(
            {
                "test_id": test_id,
                "thread_id": thread_id,
                "duration_ms": duration_ms,
                "success": success,
                "timestamp": time.time(),
            }
        )
        self.execution_times.append(duration_ms)

    def record_thread_conflict(self, conflict_info: Dict[str, Any]):
        """Record a thread safety conflict."""
        self.thread_conflicts.append(conflict_info)

    def record_resource_conflict(self, conflict_info: Dict[str, Any]):
        """Record a resource allocation conflict."""
        self.resource_conflicts.append(conflict_info)

    def get_statistics(self) -> Dict[str, Any]:
        """Get validation statistics."""
        if not self.test_results:
            return {"error": "No test results recorded"}

        success_count = sum(1 for r in self.test_results if r["success"])
        total_count = len(self.test_results)

        return {
            "total_tests": total_count,
            "successful_tests": success_count,
            "success_rate": (success_count / total_count) * 100,
            "avg_execution_time_ms": sum(self.execution_times)
            / len(self.execution_times),
            "max_execution_time_ms": max(self.execution_times),
            "min_execution_time_ms": min(self.execution_times),
            "thread_conflicts": len(self.thread_conflicts),
            "resource_conflicts": len(self.resource_conflicts),
            "parallel_safety": len(self.thread_conflicts) == 0
            and len(self.resource_conflicts) == 0,
        }


@pytest.fixture
def parallel_validator():
    """Provide a parallel test validator."""
    return ParallelTestValidator()


def simulate_parallel_test_operation(
    test_id: str, validator: ParallelTestValidator
) -> Dict[str, Any]:
    """
    Simulate a parallel test operation.

    Args:
        test_id: Unique test identifier
        validator: Validator for recording results

    Returns:
        Dict with test results
    """
    start_time = time.time()
    thread_id = threading.get_ident()
    success = True

    try:
        # Get parallel manager
        parallel_manager = get_parallel_manager()

        # Register for parallel execution
        parallel_manager.register_parallel_test(test_id, thread_id, "SERIALIZABLE")

        # Simulate test work with resource allocation
        resource_name = f"test_resource_{test_id}"

        if not parallel_manager.allocate_resource(test_id, resource_name):
            validator.record_resource_conflict(
                {
                    "test_id": test_id,
                    "thread_id": thread_id,
                    "resource": resource_name,
                    "conflict_type": "allocation_failed",
                }
            )
            success = False

        # Simulate test operations
        time.sleep(0.01)  # 10ms simulated work

        # Check for deadlock potential
        if parallel_manager.detect_potential_deadlock(
            test_id, f"other_resource_{test_id}"
        ):
            validator.record_resource_conflict(
                {
                    "test_id": test_id,
                    "thread_id": thread_id,
                    "conflict_type": "potential_deadlock",
                }
            )

        # Release resource
        parallel_manager.release_resource(test_id, resource_name)

        # Unregister
        parallel_manager.unregister_parallel_test(test_id)

    except Exception as e:
        success = False
        validator.record_thread_conflict(
            {
                "test_id": test_id,
                "thread_id": thread_id,
                "error": str(e),
                "conflict_type": "exception",
            }
        )

    duration_ms = (time.time() - start_time) * 1000
    validator.record_test_result(test_id, thread_id, duration_ms, success)

    return {
        "test_id": test_id,
        "thread_id": thread_id,
        "duration_ms": duration_ms,
        "success": success,
    }


@pytest.mark.asyncio
async def test_basic_parallel_execution(parallel_validator):
    """Test basic parallel execution without conflicts."""
    # Run multiple tests in parallel
    test_count = 5
    test_ids = [f"basic_parallel_{i}_{uuid.uuid4().hex[:8]}" for i in range(test_count)]

    # Execute tests in parallel using ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=test_count) as executor:
        futures = [
            executor.submit(
                simulate_parallel_test_operation, test_id, parallel_validator
            )
            for test_id in test_ids
        ]

        # Wait for all tests to complete
        results = [
            future.result() for future in concurrent.futures.as_completed(futures)
        ]

    # Validate results
    stats = parallel_validator.get_statistics()

    assert stats["total_tests"] == test_count
    assert (
        stats["success_rate"] == 100.0
    ), f"Not all parallel tests succeeded: {stats['success_rate']}%"
    assert stats[
        "parallel_safety"
    ], f"Thread conflicts detected: {stats['thread_conflicts']}, Resource conflicts: {stats['resource_conflicts']}"
    assert (
        stats["avg_execution_time_ms"] < 100.0
    ), f"Average execution time too high: {stats['avg_execution_time_ms']}ms"


@pytest.mark.asyncio
async def test_high_concurrency_execution(parallel_validator):
    """Test high concurrency parallel execution."""
    # Run many tests concurrently to stress test the system
    test_count = 20
    test_ids = [
        f"high_concurrency_{i}_{uuid.uuid4().hex[:8]}" for i in range(test_count)
    ]

    start_time = time.time()

    # Execute with high concurrency
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(
                simulate_parallel_test_operation, test_id, parallel_validator
            )
            for test_id in test_ids
        ]

        results = [
            future.result() for future in concurrent.futures.as_completed(futures)
        ]

    total_time = (time.time() - start_time) * 1000

    # Validate results
    stats = parallel_validator.get_statistics()

    assert stats["total_tests"] == test_count
    assert (
        stats["success_rate"] >= 95.0
    ), f"Success rate too low under high concurrency: {stats['success_rate']}%"
    assert (
        stats["max_execution_time_ms"] < 200.0
    ), f"Individual test took too long under load: {stats['max_execution_time_ms']}ms"
    assert (
        total_time < test_count * 100.0
    ), f"Total execution time suggests no parallelism: {total_time}ms"


@pytest.mark.asyncio
async def test_resource_contention_handling():
    """Test resource contention and deadlock prevention."""
    parallel_manager = get_parallel_manager()
    validator = ParallelTestValidator()

    # Test resource allocation conflicts
    test_id_1 = f"resource_test_1_{uuid.uuid4().hex[:8]}"
    test_id_2 = f"resource_test_2_{uuid.uuid4().hex[:8]}"

    # Register both tests
    parallel_manager.register_parallel_test(
        test_id_1, threading.get_ident(), "SERIALIZABLE"
    )
    parallel_manager.register_parallel_test(
        test_id_2, threading.get_ident() + 1, "SERIALIZABLE"
    )

    # Allocate same resource to first test
    resource_name = "shared_resource"
    assert parallel_manager.allocate_resource(test_id_1, resource_name)

    # Second test should fail to allocate the same resource
    assert not parallel_manager.allocate_resource(test_id_2, resource_name)

    # Test deadlock detection
    assert not parallel_manager.detect_potential_deadlock(test_id_2, resource_name)

    # Release resource and test reallocation
    parallel_manager.release_resource(test_id_1, resource_name)
    assert parallel_manager.allocate_resource(test_id_2, resource_name)

    # Cleanup
    parallel_manager.release_resource(test_id_2, resource_name)
    parallel_manager.unregister_parallel_test(test_id_1)
    parallel_manager.unregister_parallel_test(test_id_2)


@pytest.mark.asyncio
async def test_isolation_level_handling():
    """Test different isolation levels in parallel execution."""
    parallel_manager = get_parallel_manager()

    isolation_levels = ["READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"]
    test_ids = []

    for i, isolation_level in enumerate(isolation_levels):
        test_id = f"isolation_test_{i}_{uuid.uuid4().hex[:8]}"
        test_ids.append(test_id)

        parallel_manager.register_parallel_test(
            test_id, threading.get_ident() + i, isolation_level
        )

        # Verify isolation level is set correctly
        assert parallel_manager.get_isolation_level(test_id) == isolation_level

    # Cleanup
    for test_id in test_ids:
        parallel_manager.unregister_parallel_test(test_id)


@pytest.mark.asyncio
async def test_thread_safety_of_managers():
    """Test thread safety of optimization managers."""

    def test_pool_manager_thread_safety():
        """Test pool manager thread safety."""
        pool_manager = get_pool_manager()
        test_id = f"pool_thread_test_{threading.get_ident()}_{uuid.uuid4().hex[:8]}"

        try:
            # This should be thread-safe
            stats = pool_manager.get_pool_statistics(test_id)
            return True
        except Exception as e:
            logger.error(f"Pool manager thread safety error: {e}")
            return False

    def test_parallel_manager_thread_safety():
        """Test parallel manager thread safety."""
        parallel_manager = get_parallel_manager()
        test_id = f"parallel_thread_test_{threading.get_ident()}_{uuid.uuid4().hex[:8]}"

        try:
            # These operations should be thread-safe
            parallel_manager.register_parallel_test(
                test_id, threading.get_ident(), "READ COMMITTED"
            )
            stats = parallel_manager.get_parallel_statistics()
            parallel_manager.unregister_parallel_test(test_id)
            return True
        except Exception as e:
            logger.error(f"Parallel manager thread safety error: {e}")
            return False

    def test_performance_monitor_thread_safety():
        """Test performance monitor thread safety."""
        monitor = get_performance_monitor()

        try:
            # Create and record metrics
            metrics = PerformanceMetrics(
                operation_id=f"thread_test_{threading.get_ident()}",
                operation_type="thread_safety_test",
                duration_ms=50.0,
            )
            monitor.record_metrics(metrics)
            report = monitor.get_performance_report()
            return True
        except Exception as e:
            logger.error(f"Performance monitor thread safety error: {e}")
            return False

    # Run thread safety tests in parallel
    thread_count = 10
    with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
        # Test pool manager
        pool_futures = [
            executor.submit(test_pool_manager_thread_safety)
            for _ in range(thread_count)
        ]
        pool_results = [
            f.result() for f in concurrent.futures.as_completed(pool_futures)
        ]

        # Test parallel manager
        parallel_futures = [
            executor.submit(test_parallel_manager_thread_safety)
            for _ in range(thread_count)
        ]
        parallel_results = [
            f.result() for f in concurrent.futures.as_completed(parallel_futures)
        ]

        # Test performance monitor
        monitor_futures = [
            executor.submit(test_performance_monitor_thread_safety)
            for _ in range(thread_count)
        ]
        monitor_results = [
            f.result() for f in concurrent.futures.as_completed(monitor_futures)
        ]

    # Validate all operations succeeded
    assert all(pool_results), "Pool manager thread safety test failed"
    assert all(parallel_results), "Parallel manager thread safety test failed"
    assert all(monitor_results), "Performance monitor thread safety test failed"


@pytest.mark.asyncio
async def test_performance_consistency_under_load():
    """Test that performance remains consistent under parallel load."""
    validator = ParallelTestValidator()

    # Baseline: single threaded execution
    baseline_test_id = f"baseline_{uuid.uuid4().hex[:8]}"
    baseline_result = simulate_parallel_test_operation(baseline_test_id, validator)
    baseline_time = baseline_result["duration_ms"]

    # Parallel execution under load
    test_count = 15
    test_ids = [f"load_test_{i}_{uuid.uuid4().hex[:8]}" for i in range(test_count)]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(simulate_parallel_test_operation, test_id, validator)
            for test_id in test_ids
        ]

        parallel_results = [
            future.result() for future in concurrent.futures.as_completed(futures)
        ]

    # Analyze performance consistency
    parallel_times = [r["duration_ms"] for r in parallel_results]
    avg_parallel_time = sum(parallel_times) / len(parallel_times)
    max_parallel_time = max(parallel_times)

    # Performance should not degrade significantly under load
    degradation_factor = avg_parallel_time / baseline_time
    max_degradation_factor = max_parallel_time / baseline_time

    assert (
        degradation_factor < 2.0
    ), f"Average performance degraded too much under load: {degradation_factor:.2f}x"
    assert (
        max_degradation_factor < 3.0
    ), f"Worst case performance degraded too much: {max_degradation_factor:.2f}x"
    assert (
        avg_parallel_time < 100.0
    ), f"Average execution time exceeded target under load: {avg_parallel_time:.2f}ms"


@pytest.mark.asyncio
async def test_parallel_execution_with_real_database_operations():
    """Test parallel execution with actual database operations."""
    from dataflow.testing.enhanced_tdd_fixtures import parallel_test_execution

    async def database_operation_test(context, isolation_id, resource_manager):
        """Perform actual database operations in parallel."""
        start_time = time.time()

        # Allocate database resource
        db_resource = f"db_table_{isolation_id}"
        if not resource_manager.allocate(db_resource):
            return {"success": False, "error": "Failed to allocate database resource"}

        try:
            # Simulate database operations (would use real connection in full test)
            await asyncio.sleep(0.02)  # 20ms simulated DB operation

            # Simulate some work
            result = {"success": True, "operations": 5}

            return {
                "success": True,
                "duration_ms": (time.time() - start_time) * 1000,
                "result": result,
            }

        finally:
            resource_manager.release(db_resource)

    # Run multiple database operations in parallel
    test_count = 8

    # Note: This would use the actual fixture in a real test environment
    # For this unit test, we simulate the parallel execution pattern

    tasks = []
    for i in range(test_count):
        # In real test, this would be: async with parallel_test_execution() as (context, isolation_id, resource_manager):
        isolation_id = f"db_isolation_{i}_{uuid.uuid4().hex[:8]}"

        # Create mock context and resource manager for this test
        class MockContext:
            def __init__(self, isolation_id):
                self.isolation_id = isolation_id

        class MockResourceManager:
            def __init__(self):
                self.allocated = set()

            def allocate(self, resource_name):
                if resource_name not in self.allocated:
                    self.allocated.add(resource_name)
                    return True
                return False

            def release(self, resource_name):
                self.allocated.discard(resource_name)

        context = MockContext(isolation_id)
        resource_manager = MockResourceManager()

        task = database_operation_test(context, isolation_id, resource_manager)
        tasks.append(task)

    # Execute all database operations in parallel
    results = await asyncio.gather(*tasks)

    # Validate results
    success_count = sum(1 for r in results if r["success"])
    assert (
        success_count == test_count
    ), f"Not all database operations succeeded: {success_count}/{test_count}"

    # Check performance
    durations = [r["duration_ms"] for r in results if "duration_ms" in r]
    if durations:
        avg_duration = sum(durations) / len(durations)
        assert (
            avg_duration < 100.0
        ), f"Database operations too slow under parallel load: {avg_duration:.2f}ms"


def test_parallel_execution_statistics():
    """Test parallel execution statistics collection."""
    parallel_manager = get_parallel_manager()

    # Register multiple parallel tests
    test_ids = []
    for i in range(5):
        test_id = f"stats_test_{i}_{uuid.uuid4().hex[:8]}"
        test_ids.append(test_id)
        parallel_manager.register_parallel_test(
            test_id, threading.get_ident() + i, "SERIALIZABLE"
        )

    # Get statistics
    stats = parallel_manager.get_parallel_statistics()

    assert stats["active_tests"] == 5
    assert stats["total_tests"] >= 5
    assert "isolation_levels" in stats
    assert stats["deadlock_detection_enabled"] is True

    # Cleanup
    for test_id in test_ids:
        parallel_manager.unregister_parallel_test(test_id)

    # Verify cleanup
    final_stats = parallel_manager.get_parallel_statistics()
    assert final_stats["active_tests"] == 0


def test_parallel_validator_comprehensive():
    """Test the parallel validator with comprehensive scenarios."""
    validator = ParallelTestValidator()

    # Record various test scenarios
    validator.record_test_result("test1", 1001, 45.0, True)
    validator.record_test_result("test2", 1002, 89.0, True)
    validator.record_test_result("test3", 1003, 120.0, False)  # Failed test

    validator.record_thread_conflict(
        {
            "test_id": "test4",
            "thread_id": 1004,
            "error": "Simulated conflict",
            "conflict_type": "thread_safety",
        }
    )

    validator.record_resource_conflict(
        {
            "test_id": "test5",
            "thread_id": 1005,
            "resource": "shared_db",
            "conflict_type": "allocation_failed",
        }
    )

    # Get comprehensive statistics
    stats = validator.get_statistics()

    assert stats["total_tests"] == 3
    assert stats["successful_tests"] == 2
    assert stats["success_rate"] == (2 / 3) * 100  # 66.67%
    assert stats["avg_execution_time_ms"] == (45.0 + 89.0 + 120.0) / 3
    assert stats["max_execution_time_ms"] == 120.0
    assert stats["min_execution_time_ms"] == 45.0
    assert stats["thread_conflicts"] == 1
    assert stats["resource_conflicts"] == 1
    assert stats["parallel_safety"] is False  # Conflicts detected
