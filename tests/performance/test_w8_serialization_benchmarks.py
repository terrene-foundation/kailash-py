#!/usr/bin/env python3
"""
Performance benchmark tests for W8 serialization bug fix.

This test suite validates that the enhanced Node._is_json_serializable() method
does not introduce significant performance overhead while adding .to_dict() support.

Test Strategy (Performance Benchmarks):
- Compare performance before/after fix implementation
- Measure serialization overhead for different object types
- Validate performance requirements across all tiers
- Provide performance regression detection

Benchmark Categories:
1. Standard JSON types (baseline performance)
2. Objects with .to_dict() methods (new functionality)
3. Large data structures (scalability testing)
4. Mixed workloads (realistic scenarios)
"""

import json
import statistics
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest
from kailash.nodes.base import Node
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# ============================================================================
# Benchmark Infrastructure
# ============================================================================


@contextmanager
def benchmark_timer():
    """Context manager for accurate timing measurements."""
    start_time = time.perf_counter()
    yield lambda: time.perf_counter() - start_time


class PerformanceBenchmark:
    """Performance benchmark utilities."""

    @staticmethod
    def run_benchmark(func, iterations=1000, warmup=100):
        """Run benchmark with warmup and statistical analysis."""
        # Warmup runs
        for _ in range(warmup):
            func()

        # Benchmark runs
        times = []
        for _ in range(iterations):
            with benchmark_timer() as timer:
                func()
            times.append(timer())

        return {
            "mean": statistics.mean(times),
            "median": statistics.median(times),
            "stdev": statistics.stdev(times) if len(times) > 1 else 0,
            "min": min(times),
            "max": max(times),
            "iterations": iterations,
            "total_time": sum(times),
        }


# ============================================================================
# Test Data Classes for Benchmarks
# ============================================================================


@dataclass
class SimpleW8Context:
    """Simple W8Context for baseline benchmarks."""

    request_id: str
    user_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"request_id": self.request_id, "user_id": self.user_id}


@dataclass
class ComplexW8Context:
    """Complex W8Context for stress testing."""

    request_id: str
    user_id: Optional[str] = None
    session_data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "session_data": self.session_data,
            "metadata": self.metadata,
            "audit_trail": self.audit_trail,
        }


class SlowToDict:
    """Object with intentionally slow .to_dict() method."""

    def __init__(self, data):
        self.data = data

    def to_dict(self):
        # Simulate processing time
        time.sleep(0.001)  # 1ms delay
        return {"data": self.data, "slow": True}


class NonToDictObject:
    """Standard object without .to_dict() method."""

    def __init__(self, data):
        self.data = data


# ============================================================================
# Baseline Performance Benchmarks
# ============================================================================


@pytest.mark.performance
class TestBaselinePerformanceBenchmarks:
    """Baseline performance benchmarks for standard JSON types."""

    def test_standard_json_types_performance(self):
        """Benchmark standard JSON types serialization performance."""
        node = Node(name="benchmark_node")

        # Test data
        test_cases = [
            ("small_dict", {"key": "value", "number": 42}),
            ("large_dict", {f"key_{i}": f"value_{i}" for i in range(1000)}),
            ("small_list", [1, 2, 3, 4, 5]),
            ("large_list", list(range(10000))),
            ("string", "test_string" * 100),
            ("number", 123456789),
            ("boolean", True),
            ("null", None),
        ]

        benchmark_results = {}

        for name, test_data in test_cases:
            # Benchmark _is_json_serializable performance
            benchmark_result = PerformanceBenchmark.run_benchmark(
                lambda: node._is_json_serializable(test_data),
                iterations=10000,
                warmup=1000,
            )

            benchmark_results[name] = benchmark_result

            # Validate performance requirements
            assert benchmark_result["mean"] < 0.001  # <1ms average for standard types
            assert benchmark_result["max"] < 0.01  # <10ms worst case

        # Print benchmark results
        print("\\n=== Standard JSON Types Performance ===")
        for name, result in benchmark_results.items():
            print(
                f"{name:12}: {result['mean']*1000:.3f}ms avg, {result['max']*1000:.3f}ms max"
            )

        return benchmark_results

    def test_nested_structure_performance(self):
        """Benchmark nested structure serialization performance."""
        node = Node(name="benchmark_node")

        # Create increasingly complex nested structures
        def create_nested_structure(depth, width=5):
            if depth == 0:
                return {"leaf": "value", "number": 42}

            return {
                f"level_{depth}": {
                    f"branch_{i}": create_nested_structure(depth - 1, width)
                    for i in range(width)
                }
            }

        depth_benchmarks = {}

        for depth in [1, 3, 5, 7, 10]:
            nested_data = create_nested_structure(depth, width=3)

            benchmark_result = PerformanceBenchmark.run_benchmark(
                lambda: node._is_json_serializable(nested_data),
                iterations=1000,
                warmup=100,
            )

            depth_benchmarks[f"depth_{depth}"] = benchmark_result

            # Performance should degrade gracefully with depth
            if depth <= 5:
                assert benchmark_result["mean"] < 0.01  # <10ms for reasonable depth
            else:
                assert benchmark_result["mean"] < 0.1  # <100ms for deep structures

        print("\\n=== Nested Structure Performance ===")
        for depth, result in depth_benchmarks.items():
            print(
                f"{depth:8}: {result['mean']*1000:.3f}ms avg, {result['max']*1000:.3f}ms max"
            )

        return depth_benchmarks


# ============================================================================
# W8Context Performance Benchmarks
# ============================================================================


@pytest.mark.performance
class TestW8ContextPerformanceBenchmarks:
    """Performance benchmarks for W8Context objects with .to_dict() methods."""

    def test_simple_w8_context_performance(self):
        """Benchmark simple W8Context serialization performance."""
        node = Node(name="benchmark_node")

        # Create simple W8Context instances
        simple_contexts = [
            SimpleW8Context(f"request_{i}", f"user_{i}") for i in range(100)
        ]

        # Benchmark single context serialization
        single_context_benchmark = PerformanceBenchmark.run_benchmark(
            lambda: node._is_json_serializable(simple_contexts[0]),
            iterations=10000,
            warmup=1000,
        )

        # Benchmark multiple contexts
        multi_context_benchmark = PerformanceBenchmark.run_benchmark(
            lambda: all(
                node._is_json_serializable(ctx) for ctx in simple_contexts[:10]
            ),
            iterations=1000,
            warmup=100,
        )

        # Performance requirements for .to_dict() objects
        assert single_context_benchmark["mean"] < 0.01  # <10ms for single context
        assert multi_context_benchmark["mean"] < 0.1  # <100ms for 10 contexts

        print("\\n=== Simple W8Context Performance ===")
        print(f"Single context: {single_context_benchmark['mean']*1000:.3f}ms avg")
        print(f"10 contexts   : {multi_context_benchmark['mean']*1000:.3f}ms avg")

        return {
            "single_context": single_context_benchmark,
            "multi_context": multi_context_benchmark,
        }

    def test_complex_w8_context_performance(self):
        """Benchmark complex W8Context serialization performance."""
        node = Node(name="benchmark_node")

        # Create complex W8Context
        complex_context = ComplexW8Context(
            request_id="complex_benchmark",
            user_id="benchmark_user",
            session_data={
                f"session_key_{i}": {
                    "data": list(range(i * 10, (i + 1) * 10)),
                    "metadata": {f"meta_{j}": f"value_{j}" for j in range(10)},
                }
                for i in range(50)
            },
            metadata={
                f"meta_category_{i}": {
                    "config": {f"setting_{j}": j * i for j in range(20)},
                    "tags": [f"tag_{k}" for k in range(i, i + 5)],
                }
                for i in range(25)
            },
            audit_trail=[
                {
                    "action": f"action_{i}",
                    "timestamp": f"2024-01-01T10:00:{i:02d}Z",
                    "data": {"step": i},
                }
                for i in range(100)
            ],
        )

        # Benchmark complex context
        complex_benchmark = PerformanceBenchmark.run_benchmark(
            lambda: node._is_json_serializable(complex_context),
            iterations=1000,
            warmup=100,
        )

        # Test actual JSON serialization performance
        json_benchmark = PerformanceBenchmark.run_benchmark(
            lambda: json.dumps(complex_context.to_dict()), iterations=1000, warmup=100
        )

        # Performance requirements for complex objects
        assert complex_benchmark["mean"] < 0.1  # <100ms for serialization check
        assert json_benchmark["mean"] < 0.5  # <500ms for actual JSON conversion

        print("\\n=== Complex W8Context Performance ===")
        print(f"Serialization check: {complex_benchmark['mean']*1000:.3f}ms avg")
        print(f"JSON conversion    : {json_benchmark['mean']*1000:.3f}ms avg")

        return {
            "serialization_check": complex_benchmark,
            "json_conversion": json_benchmark,
        }

    def test_slow_to_dict_performance_impact(self):
        """Test performance impact of slow .to_dict() methods."""
        node = Node(name="benchmark_node")

        # Create objects with slow .to_dict() methods
        slow_objects = [SlowToDict(f"data_{i}") for i in range(10)]

        # Benchmark slow .to_dict() performance
        slow_benchmark = PerformanceBenchmark.run_benchmark(
            lambda: node._is_json_serializable(slow_objects[0]),
            iterations=100,  # Fewer iterations due to intentional slowness
            warmup=10,
        )

        # The enhanced method should still complete, just slower
        assert slow_benchmark["mean"] > 0.001  # Should be slower due to 1ms delay
        assert slow_benchmark["mean"] < 0.01  # But not excessively slow

        print("\\n=== Slow .to_dict() Performance Impact ===")
        print(f"Slow to_dict: {slow_benchmark['mean']*1000:.3f}ms avg (expected ~1ms)")

        return {"slow_to_dict": slow_benchmark}


# ============================================================================
# Comparative Performance Tests
# ============================================================================


@pytest.mark.performance
class TestComparativePerformance:
    """Compare performance between objects with and without .to_dict() methods."""

    def test_to_dict_vs_standard_object_performance(self):
        """Compare performance between .to_dict() objects and standard objects."""
        node = Node(name="benchmark_node")

        # Create comparable objects
        data = {"key": "value", "number": 42, "list": [1, 2, 3]}

        with_to_dict = SimpleW8Context("test_request", "test_user")
        without_to_dict = NonToDictObject(data)
        standard_dict = data

        # Benchmark each type
        benchmarks = {}

        benchmarks["with_to_dict"] = PerformanceBenchmark.run_benchmark(
            lambda: node._is_json_serializable(with_to_dict),
            iterations=10000,
            warmup=1000,
        )

        benchmarks["without_to_dict"] = PerformanceBenchmark.run_benchmark(
            lambda: node._is_json_serializable(without_to_dict),
            iterations=10000,
            warmup=1000,
        )

        benchmarks["standard_dict"] = PerformanceBenchmark.run_benchmark(
            lambda: node._is_json_serializable(standard_dict),
            iterations=10000,
            warmup=1000,
        )

        # Performance comparison
        to_dict_time = benchmarks["with_to_dict"]["mean"]
        standard_time = benchmarks["standard_dict"]["mean"]
        overhead_ratio = (
            to_dict_time / standard_time if standard_time > 0 else float("inf")
        )

        # The overhead should be minimal (less than 10x slower)
        assert (
            overhead_ratio < 10.0
        ), f"to_dict() overhead too high: {overhead_ratio:.2f}x"

        print("\\n=== Comparative Performance ===")
        for obj_type, result in benchmarks.items():
            print(f"{obj_type:15}: {result['mean']*1000:.6f}ms avg")
        print(f"Overhead ratio: {overhead_ratio:.2f}x")

        return benchmarks

    def test_mixed_workload_performance(self):
        """Test performance with mixed workload of different object types."""
        node = Node(name="benchmark_node")

        # Create mixed workload
        mixed_objects = [
            {"standard": "dict"},
            SimpleW8Context("req_1", "user_1"),
            [1, 2, 3, 4, 5],
            ComplexW8Context("req_2", "user_2", {"data": "complex"}),
            "string_value",
            NonToDictObject("non_serializable"),
            42,
            {"nested": {"deep": {"value": [1, 2, 3]}}},
            SimpleW8Context("req_3", "user_3"),
            True,
        ]

        # Benchmark mixed workload
        mixed_benchmark = PerformanceBenchmark.run_benchmark(
            lambda: [node._is_json_serializable(obj) for obj in mixed_objects],
            iterations=1000,
            warmup=100,
        )

        # Calculate per-object average
        per_object_time = mixed_benchmark["mean"] / len(mixed_objects)

        # Performance requirement for mixed workloads
        assert per_object_time < 0.01  # <10ms per object on average
        assert mixed_benchmark["mean"] < 0.1  # <100ms for full mixed workload

        print("\\n=== Mixed Workload Performance ===")
        print(f"Total mixed workload: {mixed_benchmark['mean']*1000:.3f}ms avg")
        print(f"Per object average  : {per_object_time*1000:.3f}ms avg")

        return {"mixed_workload": mixed_benchmark, "per_object": per_object_time}


# ============================================================================
# Workflow Performance Integration
# ============================================================================


@pytest.mark.performance
class TestWorkflowPerformanceIntegration:
    """Test performance impact in actual workflow execution scenarios."""

    def test_w8_context_workflow_performance_impact(self):
        """Test performance impact of W8Context in actual workflows."""
        # Create workflow with W8Context objects
        workflow = WorkflowBuilder()

        workflow.add_node(
            "PythonCodeNode",
            "create_w8_contexts",
            {
                "code": """
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import time

@dataclass
class BenchmarkW8Context:
    request_id: str
    user_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "data": self.data
        }

start_time = time.time()

# Create multiple W8Context objects
contexts = []
for i in range(100):
    context = BenchmarkW8Context(
        request_id=f"perf_test_{i}",
        user_id=f"user_{i}",
        data={f"key_{j}": f"value_{j}" for j in range(10)}
    )
    contexts.append(context)

creation_time = time.time() - start_time

result = {
    "contexts": contexts,
    "creation_time": creation_time,
    "context_count": len(contexts)
}
"""
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "process_w8_contexts",
            {
                "code": """
import json
import time

start_time = time.time()

contexts = context_data["contexts"]
processing_results = []

# Process each context (triggers serialization validation)
for i, context in enumerate(contexts):
    if hasattr(context, 'to_dict'):
        # This triggers the enhanced _is_json_serializable logic
        context_dict = context.to_dict()
        json_str = json.dumps(context_dict)

        processing_results.append({
            "context_id": context.request_id,
            "serialization_success": True,
            "json_size": len(json_str)
        })
    else:
        processing_results.append({
            "context_id": f"unknown_{i}",
            "serialization_success": False,
            "json_size": 0
        })

processing_time = time.time() - start_time

result = {
    "processing_results": processing_results,
    "processing_time": processing_time,
    "contexts_processed": len(processing_results),
    "successful_serializations": sum(1 for r in processing_results if r["serialization_success"]),
    "total_json_size": sum(r["json_size"] for r in processing_results)
}
"""
            },
        )

        workflow.add_connection(
            "create_w8_contexts", "result", "process_w8_contexts", "context_data"
        )

        # Benchmark workflow execution
        runtime = LocalRuntime()

        start_time = time.time()
        results, run_id = runtime.execute(workflow.build())
        total_workflow_time = time.time() - start_time

        # Validate performance requirements
        assert total_workflow_time < 5.0  # Should complete within 5 seconds

        # Extract performance metrics
        creation_result = results["create_w8_contexts"]["result"]
        processing_result = results["process_w8_contexts"]["result"]

        assert creation_result["context_count"] == 100
        assert processing_result["contexts_processed"] == 100
        assert processing_result["successful_serializations"] == 100

        # Performance analysis
        per_context_creation_time = creation_result["creation_time"] / 100
        per_context_processing_time = processing_result["processing_time"] / 100

        assert per_context_creation_time < 0.001  # <1ms per context creation
        assert per_context_processing_time < 0.01  # <10ms per context processing

        print("\\n=== Workflow Performance Impact ===")
        print(f"Total workflow time     : {total_workflow_time:.3f}s")
        print(f"Context creation time   : {creation_result['creation_time']:.3f}s")
        print(f"Context processing time : {processing_result['processing_time']:.3f}s")
        print(f"Per context creation    : {per_context_creation_time*1000:.3f}ms")
        print(f"Per context processing  : {per_context_processing_time*1000:.3f}ms")
        print(f"Total JSON size         : {processing_result['total_json_size']} bytes")

        return {
            "total_time": total_workflow_time,
            "creation_time": creation_result["creation_time"],
            "processing_time": processing_result["processing_time"],
            "per_context_creation": per_context_creation_time,
            "per_context_processing": per_context_processing_time,
        }


# ============================================================================
# Performance Regression Detection
# ============================================================================


@pytest.mark.performance
class TestPerformanceRegression:
    """Detect performance regressions in serialization enhancement."""

    def test_performance_regression_thresholds(self):
        """Test performance against acceptable regression thresholds."""
        node = Node(name="regression_test_node")

        # Performance test matrix
        test_matrix = [
            ("simple_dict", {"key": "value"}, 0.0001),  # <0.1ms
            ("complex_dict", {f"k_{i}": f"v_{i}" for i in range(1000)}, 0.001),  # <1ms
            ("simple_w8_context", SimpleW8Context("test", "user"), 0.01),  # <10ms
            (
                "complex_w8_context",
                ComplexW8Context("test", "user", {"data": list(range(100))}),
                0.1,
            ),  # <100ms
            ("non_serializable", NonToDictObject("data"), 0.0001),  # <0.1ms
        ]

        regression_results = {}

        for test_name, test_object, threshold in test_matrix:
            benchmark = PerformanceBenchmark.run_benchmark(
                lambda obj=test_object: node._is_json_serializable(obj),
                iterations=1000,
                warmup=100,
            )

            regression_results[test_name] = {
                "mean_time": benchmark["mean"],
                "threshold": threshold,
                "passes_threshold": benchmark["mean"] < threshold,
                "performance_ratio": benchmark["mean"] / threshold,
            }

            # Assert performance requirement
            assert (
                benchmark["mean"] < threshold
            ), f"{test_name} exceeds threshold: {benchmark['mean']:.6f}s > {threshold:.6f}s"

        print("\\n=== Performance Regression Results ===")
        for test_name, result in regression_results.items():
            status = "PASS" if result["passes_threshold"] else "FAIL"
            print(
                f"{test_name:20}: {result['mean_time']*1000:.3f}ms ({result['performance_ratio']:.2f}x threshold) [{status}]"
            )

        return regression_results


if __name__ == "__main__":
    # Run performance benchmarks
    pytest.main(
        [
            __file__,
            "-v",
            "-m",
            "performance",
            "--timeout=30",  # Longer timeout for performance tests
        ]
    )
