#!/usr/bin/env python3
"""
DataFlow Performance Benchmark

This script establishes performance baselines for DataFlow core operations
and detects performance regressions during development.

The benchmarks focus on operations that users perform frequently:
- DataFlow instantiation
- Model registration
- Basic CRUD workflows
- Memory usage patterns

Baseline metrics are stored and compared against to detect regressions.
"""

import gc
import json
import os
import sys
import time
import tracemalloc
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class PerformanceBenchmark:
    """Manages performance benchmarking for DataFlow operations"""

    def __init__(self):
        self.results = {}
        self.baseline_file = Path(__file__).parent / "performance_baseline.json"
        self.history_file = Path(__file__).parent / "performance_history.jsonl"

    def measure_time_and_memory(
        self, operation_name: str, operation_func, *args, **kwargs
    ):
        """Measure execution time and memory usage of an operation"""
        # Force garbage collection before measurement
        gc.collect()

        # Start memory tracking
        tracemalloc.start()
        start_memory = tracemalloc.get_traced_memory()[0]

        # Measure execution time
        start_time = time.perf_counter()
        try:
            result = operation_func(*args, **kwargs)
            success = True
            error = None
        except Exception as e:
            result = None
            success = False
            error = str(e)
        end_time = time.perf_counter()

        # Measure memory usage
        end_memory = tracemalloc.get_traced_memory()[0]
        tracemalloc.stop()

        execution_time_ms = (end_time - start_time) * 1000
        memory_used_kb = (end_memory - start_memory) / 1024

        self.results[operation_name] = {
            "execution_time_ms": execution_time_ms,
            "memory_used_kb": memory_used_kb,
            "success": success,
            "error": error,
            "timestamp": datetime.now().isoformat(),
        }

        return result, execution_time_ms, memory_used_kb, success

    def benchmark_dataflow_instantiation(self):
        """Benchmark DataFlow instantiation performance"""
        print("🔍 Benchmarking DataFlow instantiation...")

        def instantiate_dataflow():
            from dataflow import DataFlow

            return DataFlow(":memory:")

        # Warm up
        instantiate_dataflow()

        # Benchmark multiple runs
        times = []
        memories = []

        for i in range(5):
            _, exec_time, memory, success = self.measure_time_and_memory(
                f"dataflow_instantiation_run_{i}", instantiate_dataflow
            )
            if success:
                times.append(exec_time)
                memories.append(memory)

        avg_time = sum(times) / len(times) if times else 0
        avg_memory = sum(memories) / len(memories) if memories else 0

        self.results["dataflow_instantiation"] = {
            "avg_execution_time_ms": avg_time,
            "avg_memory_used_kb": avg_memory,
            "min_time_ms": min(times) if times else 0,
            "max_time_ms": max(times) if times else 0,
            "runs": len(times),
            "timestamp": datetime.now().isoformat(),
        }

        print(f"   Average time: {avg_time:.2f}ms")
        print(f"   Average memory: {avg_memory:.2f}KB")
        return avg_time < 100  # Should be under 100ms

    def benchmark_model_registration(self):
        """Benchmark model registration performance"""
        print("🔍 Benchmarking model registration...")

        def register_model():
            from dataflow import DataFlow

            db = DataFlow(":memory:")

            @db.model
            class BenchmarkModel:
                name: str
                value: int
                active: bool = True
                score: float = 0.0

            return db

        # Warm up
        register_model()

        # Benchmark multiple runs
        times = []
        memories = []

        for i in range(5):
            _, exec_time, memory, success = self.measure_time_and_memory(
                f"model_registration_run_{i}", register_model
            )
            if success:
                times.append(exec_time)
                memories.append(memory)

        avg_time = sum(times) / len(times) if times else 0
        avg_memory = sum(memories) / len(memories) if memories else 0

        self.results["model_registration"] = {
            "avg_execution_time_ms": avg_time,
            "avg_memory_used_kb": avg_memory,
            "min_time_ms": min(times) if times else 0,
            "max_time_ms": max(times) if times else 0,
            "runs": len(times),
            "timestamp": datetime.now().isoformat(),
        }

        print(f"   Average time: {avg_time:.2f}ms")
        print(f"   Average memory: {avg_memory:.2f}KB")
        return avg_time < 50  # Should be under 50ms

    def benchmark_crud_workflow(self):
        """Benchmark basic CRUD workflow performance"""
        print("🔍 Benchmarking CRUD workflow...")

        def crud_workflow():
            from dataflow import DataFlow

            from kailash.runtime.local import LocalRuntime
            from kailash.workflow.builder import WorkflowBuilder

            db = DataFlow(":memory:")

            @db.model
            class BenchmarkItem:
                name: str
                value: int

            # Create workflow
            workflow = WorkflowBuilder()
            workflow.add_node(
                "BenchmarkItemCreateNode",
                "create_item",
                {"name": "Performance Test Item", "value": 42},
            )

            # Execute workflow
            runtime = LocalRuntime()
            results, run_id = runtime.execute(workflow.build())

            return results

        # Warm up
        crud_workflow()

        # Benchmark multiple runs
        times = []
        memories = []

        for i in range(3):  # Fewer runs due to higher cost
            _, exec_time, memory, success = self.measure_time_and_memory(
                f"crud_workflow_run_{i}", crud_workflow
            )
            if success:
                times.append(exec_time)
                memories.append(memory)

        avg_time = sum(times) / len(times) if times else 0
        avg_memory = sum(memories) / len(memories) if memories else 0

        self.results["crud_workflow"] = {
            "avg_execution_time_ms": avg_time,
            "avg_memory_used_kb": avg_memory,
            "min_time_ms": min(times) if times else 0,
            "max_time_ms": max(times) if times else 0,
            "runs": len(times),
            "timestamp": datetime.now().isoformat(),
        }

        print(f"   Average time: {avg_time:.2f}ms")
        print(f"   Average memory: {avg_memory:.2f}KB")
        return avg_time < 500  # Should be under 500ms

    def benchmark_node_generation(self):
        """Benchmark automatic node generation performance"""
        print("🔍 Benchmarking node generation...")

        def generate_nodes():
            from dataflow import DataFlow

            from kailash.workflow.builder import WorkflowBuilder

            db = DataFlow(":memory:")

            @db.model
            class TestModel:
                field1: str
                field2: int
                field3: bool = True

            # Test that all 11 nodes can be referenced
            workflow = WorkflowBuilder()
            node_types = [
                "TestModelCreateNode",
                "TestModelReadNode",
                "TestModelUpdateNode",
                "TestModelDeleteNode",
                "TestModelListNode",
                "TestModelBulkCreateNode",
                "TestModelBulkUpdateNode",
                "TestModelBulkDeleteNode",
                "TestModelCountNode",
            ]

            for i, node_type in enumerate(node_types):
                workflow.add_node(node_type, f"test_{i}", {})

            return workflow.build()

        # Warm up
        generate_nodes()

        # Benchmark multiple runs
        times = []
        memories = []

        for i in range(5):
            _, exec_time, memory, success = self.measure_time_and_memory(
                f"node_generation_run_{i}", generate_nodes
            )
            if success:
                times.append(exec_time)
                memories.append(memory)

        avg_time = sum(times) / len(times) if times else 0
        avg_memory = sum(memories) / len(memories) if memories else 0

        self.results["node_generation"] = {
            "avg_execution_time_ms": avg_time,
            "avg_memory_used_kb": avg_memory,
            "min_time_ms": min(times) if times else 0,
            "max_time_ms": max(times) if times else 0,
            "runs": len(times),
            "timestamp": datetime.now().isoformat(),
        }

        print(f"   Average time: {avg_time:.2f}ms")
        print(f"   Average memory: {avg_memory:.2f}KB")
        return avg_time < 100  # Should be under 100ms

    def load_baseline(self) -> Optional[Dict]:
        """Load performance baseline from file"""
        if self.baseline_file.exists():
            try:
                with open(self.baseline_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Could not load baseline: {e}")
        return None

    def save_baseline(self):
        """Save current results as the performance baseline"""
        try:
            with open(self.baseline_file, "w") as f:
                json.dump(self.results, f, indent=2)
            print(f"✅ Baseline saved to {self.baseline_file}")
        except Exception as e:
            print(f"❌ Failed to save baseline: {e}")

    def save_history(self):
        """Append current results to performance history"""
        try:
            history_entry = {
                "timestamp": datetime.now().isoformat(),
                "results": self.results,
            }
            with open(self.history_file, "a") as f:
                f.write(json.dumps(history_entry) + "\n")
        except Exception as e:
            print(f"Warning: Could not save history: {e}")

    def compare_with_baseline(self, baseline: Dict) -> Tuple[bool, List[str]]:
        """Compare current results with baseline and detect regressions"""
        regressions = []
        warnings = []

        metrics_to_check = [
            ("dataflow_instantiation", "avg_execution_time_ms", 50),  # 50% threshold
            ("model_registration", "avg_execution_time_ms", 50),
            ("crud_workflow", "avg_execution_time_ms", 30),
            ("node_generation", "avg_execution_time_ms", 50),
        ]

        for operation, metric, threshold_percent in metrics_to_check:
            if operation in baseline and operation in self.results:
                baseline_value = baseline[operation].get(metric, 0)
                current_value = self.results[operation].get(metric, 0)

                if baseline_value > 0:
                    percent_change = (
                        (current_value - baseline_value) / baseline_value
                    ) * 100

                    if percent_change > threshold_percent:
                        regressions.append(
                            f"{operation}.{metric}: {percent_change:.1f}% slower "
                            f"({baseline_value:.2f} -> {current_value:.2f})"
                        )
                    elif percent_change > threshold_percent / 2:
                        warnings.append(
                            f"{operation}.{metric}: {percent_change:.1f}% slower "
                            f"({baseline_value:.2f} -> {current_value:.2f})"
                        )

        return len(regressions) == 0, regressions

    def run_all_benchmarks(self) -> bool:
        """Run all performance benchmarks"""
        print("=" * 60)
        print("DataFlow Performance Benchmark")
        print("=" * 60)
        print(f"Started at: {datetime.now().isoformat()}")
        print()

        benchmarks = [
            ("DataFlow Instantiation", self.benchmark_dataflow_instantiation),
            ("Model Registration", self.benchmark_model_registration),
            ("CRUD Workflow", self.benchmark_crud_workflow),
            ("Node Generation", self.benchmark_node_generation),
        ]

        passed_benchmarks = 0

        for name, benchmark_func in benchmarks:
            try:
                print(f"\n📊 {name}")
                if benchmark_func():
                    passed_benchmarks += 1
                    print("   ✅ PASS")
                else:
                    print("   ⚠️  SLOW (exceeds expected performance)")
            except Exception as e:
                print(f"   ❌ FAIL: {e}")
                traceback.print_exc()

        return passed_benchmarks == len(benchmarks)


def main():
    """Main benchmark execution"""
    benchmark = PerformanceBenchmark()

    # Run all benchmarks
    all_passed = benchmark.run_all_benchmarks()

    # Save history
    benchmark.save_history()

    # Load baseline for comparison
    baseline = benchmark.load_baseline()

    if baseline:
        print("\n" + "=" * 60)
        print("REGRESSION ANALYSIS")
        print("=" * 60)

        no_regressions, regressions = benchmark.compare_with_baseline(baseline)

        if no_regressions:
            print("✅ No performance regressions detected")
        else:
            print("🚨 PERFORMANCE REGRESSIONS DETECTED:")
            for regression in regressions:
                print(f"   • {regression}")
    else:
        print("\n" + "=" * 60)
        print("BASELINE CREATION")
        print("=" * 60)
        print("No baseline found. Creating initial baseline...")
        benchmark.save_baseline()
        no_regressions = True

    # Summary
    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY")
    print("=" * 60)

    if all_passed and no_regressions:
        print("🎉 ALL BENCHMARKS PASSED")
        print("Performance is within acceptable limits")
        return True
    elif all_passed:
        print("⚠️  BENCHMARKS PASSED BUT REGRESSIONS DETECTED")
        print("Performance has degraded compared to baseline")
        return False
    else:
        print("❌ SOME BENCHMARKS FAILED")
        print("Performance is below acceptable thresholds")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
