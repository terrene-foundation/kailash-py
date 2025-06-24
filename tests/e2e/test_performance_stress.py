"""
Performance and stress testing for the async testing framework.

These tests validate the framework under high load, concurrent execution,
and stress conditions to ensure production readiness.
"""

import asyncio
import random
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

from kailash.testing import (
    AsyncAssertions,
    AsyncTestUtils,
    AsyncWorkflowFixtures,
    AsyncWorkflowTestCase,
)
from kailash.workflow import AsyncWorkflowBuilder

# Mark all tests as performance-intensive and slow
pytestmark = [pytest.mark.performance, pytest.mark.slow]


@pytest.mark.asyncio
class TestPerformanceStress:
    """Performance and stress testing suite."""

    async def test_high_concurrency_workflow_execution(self):
        """Test high-concurrency workflow execution."""

        class HighConcurrencyTest(AsyncWorkflowTestCase):
            async def setUp(self):
                await super().setUp()

                # Set up shared resources for concurrent access
                self.shared_counter = 0
                self.execution_times = []
                self.concurrent_results = []

                # Create shared mock resources
                class ConcurrentCounter:
                    def __init__(self):
                        self.value = 0
                        self.lock = asyncio.Lock()
                        self.call_count = 0

                    async def increment(self, amount=1):
                        async with self.lock:
                            self.value += amount
                            self.call_count += 1
                            await asyncio.sleep(0.001)  # Simulate small delay
                            return self.value

                    async def get_value(self):
                        return self.value

                self.counter = ConcurrentCounter()
                await self.create_test_resource("counter", lambda: self.counter)

                # Create mock cache for concurrent access
                self.shared_cache = await AsyncWorkflowFixtures.create_test_cache()
                await self.create_test_resource("cache", lambda: self.shared_cache)

            async def test_concurrent_workflow_execution(self):
                """Test concurrent execution of multiple workflows."""
                # Create workflow that performs concurrent operations
                workflow = (
                    AsyncWorkflowBuilder("concurrent_test")
                    .add_async_code(
                        "concurrent_operations",
                        """
import asyncio
import random
import json

# Get shared resources
counter = await get_resource("counter")
cache = await get_resource("cache")

# Worker identification
worker_start_time = asyncio.get_event_loop().time()

# Perform multiple concurrent operations
operations_results = []

# 1. Counter operations
for i in range(10):
    result = await counter.increment(random.randint(1, 5))
    operations_results.append(f"increment_{i}: {result}")

# 2. Cache operations
cache_operations = []
for i in range(20):
    key = f"worker_{worker_id}_key_{i}"
    value = {"data": random.randint(1, 1000), "timestamp": worker_start_time}
    cache_op = cache.set(key, json.dumps(value), ttl=60)
    cache_operations.append(cache_op)

# Execute cache operations concurrently
await asyncio.gather(*cache_operations)

# 3. Verify cache operations
cache_reads = []
for i in range(20):
    key = f"worker_{worker_id}_key_{i}"
    cache_reads.append(cache.get(key))

cached_values = await asyncio.gather(*cache_reads)
valid_cache_ops = sum(1 for val in cached_values if val is not None)

# 4. Simulate CPU-intensive work
cpu_work_start = asyncio.get_event_loop().time()
cpu_result = sum(i * i for i in range(1000))
cpu_work_time = asyncio.get_event_loop().time() - cpu_work_start

# 5. Simulate I/O work with delays
io_tasks = []
for i in range(5):
    async def io_simulation():
        await asyncio.sleep(random.uniform(0.01, 0.05))
        return random.randint(100, 999)

    io_tasks.append(io_simulation())

io_results = await asyncio.gather(*io_tasks)

worker_total_time = asyncio.get_event_loop().time() - worker_start_time

result = {
    "worker_id": worker_id,
    "operations_completed": len(operations_results),
    "cache_operations": 20,
    "valid_cache_reads": valid_cache_ops,
    "cpu_result": cpu_result,
    "cpu_work_time": cpu_work_time,
    "io_results": io_results,
    "total_execution_time": worker_total_time,
    "counter_final_contribution": result,  # Last counter value from this worker
    "success": True
}
""",
                    )
                    .build()
                )

                # Execute 50 concurrent workflows
                concurrent_count = 50
                start_time = time.time()

                # Create concurrent tasks
                tasks = []
                for i in range(concurrent_count):
                    task = self.execute_workflow(workflow, {"worker_id": i})
                    tasks.append(task)

                # Execute all workflows concurrently
                concurrent_results = await AsyncTestUtils.run_concurrent(*tasks)

                total_execution_time = time.time() - start_time

                # Validate all workflows succeeded
                successful_executions = 0
                total_operations = 0
                execution_times = []

                for result in concurrent_results:
                    self.assert_workflow_success(result)

                    output = result.get_output("concurrent_operations")
                    if output and output.get("success"):
                        successful_executions += 1
                        total_operations += output.get("operations_completed", 0)
                        execution_times.append(output.get("total_execution_time", 0))

                # Performance assertions
                assert (
                    successful_executions == concurrent_count
                ), f"All {concurrent_count} workflows should succeed"
                assert (
                    total_execution_time < 30.0
                ), f"Concurrent execution too slow: {total_execution_time:.2f}s"
                assert (
                    self.counter.call_count == concurrent_count * 10
                ), "All counter operations should complete"

                # Calculate performance metrics
                avg_execution_time = statistics.mean(execution_times)
                max_execution_time = max(execution_times)
                min_execution_time = min(execution_times)

                assert (
                    avg_execution_time < 2.0
                ), f"Average execution time too high: {avg_execution_time:.2f}s"
                assert (
                    max_execution_time < 5.0
                ), f"Max execution time too high: {max_execution_time:.2f}s"

                # Throughput validation
                workflows_per_second = concurrent_count / total_execution_time
                assert (
                    workflows_per_second > 5.0
                ), f"Throughput too low: {workflows_per_second:.2f} workflows/sec"

                # Resource contention validation
                final_counter_value = await self.counter.get_value()
                assert final_counter_value > 0, "Counter should have been incremented"

                # Cache validation
                cache_hit_rate = 0
                cache_tests = 0
                for i in range(min(10, concurrent_count)):  # Test first 10 workers
                    for j in range(5):  # Test first 5 keys per worker
                        key = f"worker_{i}_key_{j}"
                        value = await self.shared_cache.get(key)
                        cache_tests += 1
                        if value:
                            cache_hit_rate += 1

                hit_rate = cache_hit_rate / cache_tests if cache_tests > 0 else 0
                assert hit_rate > 0.8, f"Cache hit rate too low: {hit_rate:.2%}"

        async with HighConcurrencyTest("high_concurrency_test") as test:
            await test.test_concurrent_workflow_execution()

    async def test_memory_intensive_data_processing(self):
        """Test memory-intensive data processing workflows."""

        class MemoryIntensiveTest(AsyncWorkflowTestCase):
            async def test_large_dataset_processing(self):
                """Test processing of large datasets."""
                workflow = (
                    AsyncWorkflowBuilder("memory_intensive")
                    .add_async_code(
                        "generate_large_dataset",
                        """
# Generate large dataset for memory testing
import random
from datetime import datetime, timedelta

# Create large dataset (100k records)
dataset_size = 100000
large_dataset = []

base_date = datetime.now()

for i in range(dataset_size):
    record = {
        "id": f"record_{i:06d}",
        "timestamp": (base_date - timedelta(days=random.randint(0, 365))).isoformat(),
        "value": random.uniform(0, 10000),
        "category": random.choice(["A", "B", "C", "D", "E"]),
        "metadata": {
            "source": random.choice(["system1", "system2", "system3"]),
            "quality": random.uniform(0.7, 1.0),
            "tags": [f"tag_{random.randint(1, 100)}" for _ in range(random.randint(1, 5))],
            "processed": False,
            "score": random.randint(1, 100)
        }
    }
    large_dataset.append(record)

result = {
    "dataset": large_dataset,
    "dataset_size": len(large_dataset),
    "memory_usage_estimate": len(str(large_dataset)) // 1024,  # Rough KB estimate
    "generation_complete": True
}
""",
                    )
                    .add_async_code(
                        "memory_intensive_processing",
                        """
# Perform memory-intensive processing operations
import asyncio
from collections import defaultdict, Counter
import statistics

processing_start = asyncio.get_event_loop().time()

# 1. Data aggregation and grouping
category_groups = defaultdict(list)
source_groups = defaultdict(list)
daily_groups = defaultdict(list)

for record in dataset:
    category = record["category"]
    source = record["metadata"]["source"]
    date = record["timestamp"][:10]  # Extract date part

    category_groups[category].append(record)
    source_groups[source].append(record)
    daily_groups[date].append(record)

# 2. Statistical calculations
category_stats = {}
for category, records in category_groups.items():
    values = [r["value"] for r in records]
    scores = [r["metadata"]["score"] for r in records]
    qualities = [r["metadata"]["quality"] for r in records]

    category_stats[category] = {
        "count": len(records),
        "avg_value": statistics.mean(values),
        "median_value": statistics.median(values),
        "stddev_value": statistics.stdev(values) if len(values) > 1 else 0,
        "min_value": min(values),
        "max_value": max(values),
        "avg_score": statistics.mean(scores),
        "avg_quality": statistics.mean(qualities),
        "value_range": max(values) - min(values)
    }

# 3. Complex data transformations
transformed_records = []
enrichment_lookup = {}

# Create enrichment lookup table
for record in dataset[:10000]:  # Use subset for lookup
    enrichment_lookup[record["id"]] = {
        "enriched_score": record["metadata"]["score"] * record["metadata"]["quality"],
        "risk_level": "high" if record["value"] > 7000 else "medium" if record["value"] > 3000 else "low",
        "processing_priority": random.randint(1, 10)
    }

# Transform records with enrichment
for record in dataset:
    enrichment = enrichment_lookup.get(record["id"], {})

    transformed_record = {
        "original_id": record["id"],
        "processed_value": record["value"] * 1.1,  # Apply 10% markup
        "normalized_score": record["metadata"]["score"] / 100.0,
        "quality_weighted_value": record["value"] * record["metadata"]["quality"],
        "enriched_score": enrichment.get("enriched_score", 0),
        "risk_level": enrichment.get("risk_level", "unknown"),
        "processing_priority": enrichment.get("processing_priority", 5),
        "category": record["category"],
        "source": record["metadata"]["source"],
        "tag_count": len(record["metadata"]["tags"]),
        "processing_timestamp": datetime.now().isoformat()
    }
    transformed_records.append(transformed_record)

# 4. Memory-intensive analytics
# Create correlation matrix
categories = list(category_stats.keys())
correlation_matrix = {}

for cat1 in categories:
    correlation_matrix[cat1] = {}
    cat1_values = [r["value"] for r in category_groups[cat1]]

    for cat2 in categories:
        cat2_values = [r["value"] for r in category_groups[cat2]]

        # Simple correlation calculation (Pearson-like)
        if len(cat1_values) > 1 and len(cat2_values) > 1:
            # Use min length for comparison
            min_len = min(len(cat1_values), len(cat2_values))
            corr_data = list(zip(cat1_values[:min_len], cat2_values[:min_len]))

            if corr_data:
                mean1 = statistics.mean([x for x, y in corr_data])
                mean2 = statistics.mean([y for x, y in corr_data])

                numerator = sum((x - mean1) * (y - mean2) for x, y in corr_data)
                denom1 = sum((x - mean1) ** 2 for x, y in corr_data)
                denom2 = sum((y - mean2) ** 2 for x, y in corr_data)

                if denom1 > 0 and denom2 > 0:
                    correlation = numerator / (denom1 * denom2) ** 0.5
                else:
                    correlation = 0
            else:
                correlation = 0
        else:
            correlation = 0

        correlation_matrix[cat1][cat2] = round(correlation, 4)

processing_time = asyncio.get_event_loop().time() - processing_start

result = {
    "processed_records": len(transformed_records),
    "category_statistics": category_stats,
    "correlation_matrix": correlation_matrix,
    "processing_metrics": {
        "processing_time_seconds": processing_time,
        "records_per_second": len(dataset) / processing_time,
        "memory_efficiency": len(transformed_records) / len(dataset),
        "enrichment_coverage": len(enrichment_lookup) / len(dataset)
    },
    "data_quality": {
        "categories_found": len(category_groups),
        "sources_found": len(source_groups),
        "date_range_days": len(daily_groups),
        "avg_quality_score": statistics.mean([r["metadata"]["quality"] for r in dataset])
    }
}
""",
                    )
                    .add_async_code(
                        "memory_cleanup_and_validation",
                        """
# Perform memory cleanup and validate results
import gc
import asyncio

validation_start = asyncio.get_event_loop().time()

# Validate processing results
validation_results = {
    "data_integrity_checks": {},
    "performance_validation": {},
    "memory_cleanup": {}
}

# Data integrity checks
original_count = dataset_size
processed_count = processed_records

validation_results["data_integrity_checks"] = {
    "record_count_match": processed_count == original_count,
    "category_stats_complete": len(category_statistics) > 0,
    "correlation_matrix_complete": len(correlation_matrix) > 0,
    "no_null_processing": all(r.get("processing_timestamp") for r in transformed_records[:100])  # Check first 100
}

# Performance validation
proc_metrics = processing_metrics
validation_results["performance_validation"] = {
    "processing_speed_acceptable": proc_metrics["records_per_second"] > 1000,  # >1k records/sec
    "processing_time_reasonable": proc_metrics["processing_time_seconds"] < 30,  # <30 seconds
    "memory_efficiency_good": proc_metrics["memory_efficiency"] >= 0.95,  # 95% efficiency
    "enrichment_adequate": proc_metrics["enrichment_coverage"] > 0.05  # >5% enrichment
}

# Memory cleanup simulation
gc_start = asyncio.get_event_loop().time()

# Clear large data structures (simulate cleanup)
large_dataset_size = len(dataset)
transformed_size = len(transformed_records)

# Simulate memory cleanup by keeping only summaries
cleanup_summary = {
    "original_dataset_size": large_dataset_size,
    "transformed_dataset_size": transformed_size,
    "category_count": len(category_statistics),
    "processing_time": proc_metrics["processing_time_seconds"],
    "cleanup_timestamp": datetime.now().isoformat()
}

# Force garbage collection
gc.collect()
gc_time = asyncio.get_event_loop().time() - gc_start

validation_results["memory_cleanup"] = {
    "cleanup_time": gc_time,
    "summary_preserved": bool(cleanup_summary),
    "gc_completed": True
}

validation_time = asyncio.get_event_loop().time() - validation_start

result = {
    "validation_results": validation_results,
    "cleanup_summary": cleanup_summary,
    "validation_time": validation_time,
    "overall_success": all(
        validation_results["data_integrity_checks"]["record_count_match"],
        validation_results["performance_validation"]["processing_speed_acceptable"],
        validation_results["memory_cleanup"]["gc_completed"]
    ),
    "memory_test_complete": True
}
""",
                    )
                    .add_connection(
                        "generate_large_dataset",
                        "dataset",
                        "memory_intensive_processing",
                        "dataset",
                    )
                    .add_connection(
                        "generate_large_dataset",
                        "dataset_size",
                        "memory_intensive_processing",
                        "dataset_size",
                    )
                    .add_connection(
                        "memory_intensive_processing",
                        "processed_records",
                        "memory_cleanup_and_validation",
                        "processed_records",
                    )
                    .add_connection(
                        "memory_intensive_processing",
                        "category_statistics",
                        "memory_cleanup_and_validation",
                        "category_statistics",
                    )
                    .add_connection(
                        "memory_intensive_processing",
                        "correlation_matrix",
                        "memory_cleanup_and_validation",
                        "correlation_matrix",
                    )
                    .add_connection(
                        "memory_intensive_processing",
                        "processing_metrics",
                        "memory_cleanup_and_validation",
                        "processing_metrics",
                    )
                    .build()
                )

                # Execute memory-intensive workflow with extended timeout
                async with self.assert_time_limit(120.0):  # 2 minutes for large dataset
                    result = await self.execute_workflow(workflow, {})

                # Validate memory-intensive workflow
                self.assert_workflow_success(result)

                # Verify dataset generation
                generation_output = result.get_output("generate_large_dataset")
                assert (
                    generation_output["dataset_size"] == 100000
                ), "Should generate 100k records"
                assert generation_output[
                    "generation_complete"
                ], "Should complete generation"

                # Verify processing performance
                processing_output = result.get_output("memory_intensive_processing")
                proc_metrics = processing_output["processing_metrics"]

                assert (
                    proc_metrics["records_per_second"] > 500
                ), f"Processing too slow: {proc_metrics['records_per_second']:.1f} rec/sec"
                assert (
                    proc_metrics["processing_time_seconds"] < 60
                ), f"Processing took too long: {proc_metrics['processing_time_seconds']:.1f}s"
                assert (
                    proc_metrics["memory_efficiency"] > 0.9
                ), f"Memory efficiency too low: {proc_metrics['memory_efficiency']:.2%}"

                # Verify data quality
                data_quality = processing_output["data_quality"]
                assert (
                    data_quality["categories_found"] >= 5
                ), "Should find all categories"
                assert data_quality["sources_found"] >= 3, "Should find all sources"
                assert (
                    data_quality["avg_quality_score"] > 0.7
                ), "Should maintain quality"

                # Verify validation and cleanup
                validation_output = result.get_output("memory_cleanup_and_validation")
                assert validation_output[
                    "overall_success"
                ], "Should pass all validations"
                assert validation_output[
                    "memory_test_complete"
                ], "Should complete memory test"

                # Performance-specific validations
                validation_results = validation_output["validation_results"]
                perf_validation = validation_results["performance_validation"]

                assert perf_validation[
                    "processing_speed_acceptable"
                ], "Processing speed should be acceptable"
                assert perf_validation[
                    "processing_time_reasonable"
                ], "Processing time should be reasonable"
                assert perf_validation[
                    "memory_efficiency_good"
                ], "Memory efficiency should be good"

        async with MemoryIntensiveTest("memory_intensive_test") as test:
            await test.test_large_dataset_processing()

    async def test_stress_testing_under_resource_constraints(self):
        """Test framework behavior under resource constraints."""

        class StressTest(AsyncWorkflowTestCase):
            async def setUp(self):
                await super().setUp()

                # Create resource-constrained environment
                self.connection_pool_size = 5  # Limited connections
                self.max_concurrent_operations = 10
                self.stress_test_duration = 30  # seconds

                # Create limited resource pool
                class LimitedResourcePool:
                    def __init__(self, max_size=5):
                        self.max_size = max_size
                        self.active_connections = 0
                        self.semaphore = asyncio.Semaphore(max_size)
                        self.total_requests = 0
                        self.failed_requests = 0
                        self.avg_wait_time = 0
                        self.wait_times = []

                    async def acquire_connection(self):
                        start_time = asyncio.get_event_loop().time()

                        try:
                            await asyncio.wait_for(
                                self.semaphore.acquire(), timeout=5.0
                            )
                            wait_time = asyncio.get_event_loop().time() - start_time
                            self.wait_times.append(wait_time)
                            self.active_connections += 1
                            self.total_requests += 1
                            return f"connection_{self.active_connections}"
                        except asyncio.TimeoutError:
                            self.failed_requests += 1
                            raise Exception("Connection pool exhausted")

                    async def release_connection(self, conn_id):
                        await asyncio.sleep(random.uniform(0.1, 0.5))  # Simulate work
                        self.active_connections -= 1
                        self.semaphore.release()
                        return True

                    def get_stats(self):
                        return {
                            "total_requests": self.total_requests,
                            "failed_requests": self.failed_requests,
                            "success_rate": (self.total_requests - self.failed_requests)
                            / max(1, self.total_requests),
                            "avg_wait_time": (
                                statistics.mean(self.wait_times)
                                if self.wait_times
                                else 0
                            ),
                            "max_wait_time": (
                                max(self.wait_times) if self.wait_times else 0
                            ),
                        }

                self.resource_pool = LimitedResourcePool(self.connection_pool_size)
                await self.create_test_resource(
                    "limited_pool", lambda: self.resource_pool
                )

                # Create error-prone resource
                class FlakyResource:
                    def __init__(self, failure_rate=0.1):
                        self.failure_rate = failure_rate
                        self.call_count = 0
                        self.failure_count = 0

                    async def unreliable_operation(self, data):
                        self.call_count += 1

                        if random.random() < self.failure_rate:
                            self.failure_count += 1
                            raise Exception(f"Simulated failure #{self.failure_count}")

                        # Simulate variable processing time
                        await asyncio.sleep(random.uniform(0.01, 0.1))
                        return {"processed": data, "call_number": self.call_count}

                self.flaky_resource = FlakyResource(
                    failure_rate=0.15
                )  # 15% failure rate
                await self.create_test_resource("flaky", lambda: self.flaky_resource)

            async def test_stress_under_constraints(self):
                """Test workflow execution under resource constraints."""
                workflow = (
                    AsyncWorkflowBuilder("stress_test")
                    .add_async_code(
                        "stress_operations",
                        """
import asyncio
import random

# Get constrained resources
limited_pool = await get_resource("limited_pool")
flaky = await get_resource("flaky")

stress_start_time = asyncio.get_event_loop().time()
operation_results = []
errors_encountered = []
successful_operations = 0

# Perform stress operations
for operation_id in range(stress_intensity):
    try:
        # 1. Acquire limited resource
        connection = await limited_pool.acquire_connection()

        # 2. Perform unreliable operation
        try:
            operation_data = {
                "worker_id": worker_id,
                "operation_id": operation_id,
                "timestamp": asyncio.get_event_loop().time(),
                "payload": [random.randint(1, 1000) for _ in range(100)]  # Some data
            }

            result = await flaky.unreliable_operation(operation_data)
            operation_results.append({
                "operation_id": operation_id,
                "result": result,
                "status": "success"
            })
            successful_operations += 1

        except Exception as flaky_error:
            errors_encountered.append({
                "operation_id": operation_id,
                "error_type": "flaky_operation",
                "error_message": str(flaky_error)
            })

        # 3. Release resource
        await limited_pool.release_connection(connection)

    except Exception as pool_error:
        errors_encountered.append({
            "operation_id": operation_id,
            "error_type": "resource_exhaustion",
            "error_message": str(pool_error)
        })

    # Small delay to prevent overwhelming
    await asyncio.sleep(random.uniform(0.001, 0.01))

stress_execution_time = asyncio.get_event_loop().time() - stress_start_time

# Calculate stress metrics
total_operations = stress_intensity
error_rate = len(errors_encountered) / total_operations
success_rate = successful_operations / total_operations
operations_per_second = total_operations / stress_execution_time

result = {
    "worker_id": worker_id,
    "total_operations": total_operations,
    "successful_operations": successful_operations,
    "errors_encountered": len(errors_encountered),
    "error_details": errors_encountered,
    "success_rate": success_rate,
    "error_rate": error_rate,
    "operations_per_second": operations_per_second,
    "execution_time": stress_execution_time,
    "stress_test_complete": True
}
""",
                    )
                    .build()
                )

                # Execute stress test with multiple concurrent workers
                stress_workers = 20
                stress_intensity_per_worker = 50

                start_time = time.time()

                # Create stress test tasks
                stress_tasks = []
                for worker_id in range(stress_workers):
                    task = self.execute_workflow(
                        workflow,
                        {
                            "worker_id": worker_id,
                            "stress_intensity": stress_intensity_per_worker,
                        },
                    )
                    stress_tasks.append(task)

                # Execute stress test with timeout
                async with self.assert_time_limit(60.0):  # 1 minute stress test
                    stress_results = await AsyncTestUtils.run_concurrent(*stress_tasks)

                total_stress_time = time.time() - start_time

                # Analyze stress test results
                total_operations = 0
                total_successful = 0
                total_errors = 0
                worker_success_rates = []
                worker_throughputs = []

                for result in stress_results:
                    self.assert_workflow_success(result)

                    output = result.get_output("stress_operations")
                    total_operations += output["total_operations"]
                    total_successful += output["successful_operations"]
                    total_errors += output["errors_encountered"]
                    worker_success_rates.append(output["success_rate"])
                    worker_throughputs.append(output["operations_per_second"])

                # Calculate aggregate metrics
                overall_success_rate = (
                    total_successful / total_operations if total_operations > 0 else 0
                )
                overall_error_rate = (
                    total_errors / total_operations if total_operations > 0 else 0
                )
                avg_worker_success_rate = statistics.mean(worker_success_rates)
                avg_throughput = statistics.mean(worker_throughputs)
                total_throughput = total_operations / total_stress_time

                # Get resource pool statistics
                pool_stats = self.resource_pool.get_stats()

                # Stress test validations
                assert (
                    overall_success_rate > 0.7
                ), f"Success rate too low under stress: {overall_success_rate:.2%}"
                assert (
                    overall_error_rate < 0.3
                ), f"Error rate too high under stress: {overall_error_rate:.2%}"
                assert (
                    total_throughput > 50
                ), f"Throughput too low under stress: {total_throughput:.1f} ops/sec"

                # Resource constraint validations
                assert (
                    pool_stats["success_rate"] > 0.8
                ), f"Resource pool success rate too low: {pool_stats['success_rate']:.2%}"
                assert (
                    pool_stats["avg_wait_time"] < 2.0
                ), f"Average wait time too high: {pool_stats['avg_wait_time']:.2f}s"

                # Performance degradation should be reasonable
                assert (
                    avg_throughput > 20
                ), f"Worker throughput too low: {avg_throughput:.1f} ops/sec"
                assert (
                    total_stress_time < 45
                ), f"Stress test took too long: {total_stress_time:.1f}s"

                # System should remain stable
                assert (
                    len(stress_results) == stress_workers
                ), "All workers should complete"
                assert all(
                    r.status == "success" for r in stress_results
                ), "All workflows should succeed"

        async with StressTest("stress_test") as test:
            await test.test_stress_under_constraints()

    async def test_endurance_testing(self):
        """Test long-running workflow endurance."""

        class EnduranceTest(AsyncWorkflowTestCase):
            async def test_long_running_workflow(self):
                """Test workflow endurance over extended time."""
                workflow = (
                    AsyncWorkflowBuilder("endurance_test")
                    .add_async_code(
                        "endurance_operations",
                        """
import asyncio
import random
from datetime import datetime

endurance_start = asyncio.get_event_loop().time()
iterations_completed = 0
memory_checkpoints = []
error_recoveries = 0
phase_results = []

# Run endurance test for specified duration
target_duration = endurance_duration_seconds
checkpoint_interval = 10  # seconds

while (asyncio.get_event_loop().time() - endurance_start) < target_duration:
    iteration_start = asyncio.get_event_loop().time()

    try:
        # Phase 1: Data processing simulation
        data_batch = [random.randint(1, 10000) for _ in range(1000)]
        processed_data = [x * 1.1 + random.uniform(-10, 10) for x in data_batch]

        # Phase 2: Computational work
        computational_result = sum(x ** 0.5 for x in processed_data)

        # Phase 3: Memory allocation and cleanup
        temp_data = [[random.random() for _ in range(100)] for _ in range(100)]
        aggregated = [sum(row) / len(row) for row in temp_data]

        # Phase 4: Async operations simulation
        async def async_task():
            await asyncio.sleep(random.uniform(0.01, 0.05))
            return random.randint(1, 100)

        async_results = await asyncio.gather(*[async_task() for _ in range(10)])

        iteration_time = asyncio.get_event_loop().time() - iteration_start

        phase_results.append({
            "iteration": iterations_completed,
            "computation_result": computational_result,
            "async_results_sum": sum(async_results),
            "iteration_time": iteration_time,
            "timestamp": datetime.now().isoformat()
        })

        iterations_completed += 1

        # Memory checkpoint
        if iterations_completed % 10 == 0:
            memory_checkpoints.append({
                "iteration": iterations_completed,
                "phase_results_count": len(phase_results),
                "elapsed_time": asyncio.get_event_loop().time() - endurance_start
            })

    except Exception as e:
        error_recoveries += 1
        # Continue execution even with errors
        await asyncio.sleep(0.1)  # Brief recovery pause

    # Brief pause between iterations
    await asyncio.sleep(random.uniform(0.001, 0.01))

total_endurance_time = asyncio.get_event_loop().time() - endurance_start

# Calculate endurance metrics
avg_iteration_time = sum(r["iteration_time"] for r in phase_results) / len(phase_results) if phase_results else 0
iterations_per_second = iterations_completed / total_endurance_time
memory_growth_rate = len(memory_checkpoints) / total_endurance_time if total_endurance_time > 0 else 0

result = {
    "endurance_duration": total_endurance_time,
    "iterations_completed": iterations_completed,
    "iterations_per_second": iterations_per_second,
    "avg_iteration_time": avg_iteration_time,
    "error_recoveries": error_recoveries,
    "error_rate": error_recoveries / iterations_completed if iterations_completed > 0 else 0,
    "memory_checkpoints": len(memory_checkpoints),
    "memory_growth_rate": memory_growth_rate,
    "phase_results_sample": phase_results[-10:] if len(phase_results) >= 10 else phase_results,
    "endurance_test_complete": True,
    "stability_metrics": {
        "consistent_performance": max(r["iteration_time"] for r in phase_results) / min(r["iteration_time"] for r in phase_results) if phase_results else 1,
        "memory_stability": len(memory_checkpoints) > 0,
        "error_recovery_capability": error_recoveries < iterations_completed * 0.05  # Less than 5% error rate
    }
}
""",
                    )
                    .build()
                )

                # Execute endurance test
                endurance_duration = 60  # 1 minute endurance test

                async with self.assert_time_limit(90.0):  # Allow extra time for cleanup
                    result = await self.execute_workflow(
                        workflow, {"endurance_duration_seconds": endurance_duration}
                    )

                # Validate endurance test
                self.assert_workflow_success(result)

                output = result.get_output("endurance_operations")

                # Endurance validations
                assert output[
                    "endurance_test_complete"
                ], "Endurance test should complete"
                assert (
                    output["endurance_duration"] >= endurance_duration * 0.9
                ), "Should run for expected duration"
                assert (
                    output["iterations_completed"] > 100
                ), "Should complete substantial iterations"
                assert (
                    output["iterations_per_second"] > 1
                ), "Should maintain reasonable iteration rate"

                # Stability validations
                stability = output["stability_metrics"]
                assert stability["memory_stability"], "Should maintain memory stability"
                assert stability[
                    "error_recovery_capability"
                ], "Should handle errors gracefully"
                assert (
                    stability["consistent_performance"] < 10
                ), "Performance should be consistent"

                # Error rate validation
                assert (
                    output["error_rate"] < 0.1
                ), f"Error rate too high: {output['error_rate']:.2%}"

                # Performance degradation check
                assert (
                    output["avg_iteration_time"] < 1.0
                ), f"Iteration time too high: {output['avg_iteration_time']:.3f}s"

        async with EnduranceTest("endurance_test") as test:
            await test.test_long_running_workflow()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
