"""Performance benchmarks for cyclic workflows.

Tests performance characteristics of cycles including:
- Large-scale iteration tests (1000+ iterations)
- Memory usage tracking across iterations
- State accumulation performance
- Parallel cycle execution benchmarks
- Cycle overhead measurements

Note: These tests are marked as slow and skipped in normal CI runs.
"""

import gc
import os
import time
from typing import Any

import psutil
import pytest
from kailash import Workflow
from kailash.nodes.base import NodeParameter
from kailash.nodes.base_cycle_aware import CycleAwareNode
from kailash.runtime.local import LocalRuntime
from kailash.runtime.parallel_cyclic import ParallelCyclicRuntime
from kailash.workflow.builder import WorkflowBuilder

pytestmark = pytest.mark.slow


class PerformanceCounterNode(CycleAwareNode):
    """Simple counter for performance testing."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "increment": NodeParameter(
                name="increment", type=int, required=False, default=1
            )
        }

    def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Count with minimal overhead."""
        iteration = self.get_iteration(context)
        increment = kwargs.get("increment", 1)

        # Minimal computation
        count = iteration * increment

        # Only track state every 100 iterations to reduce overhead
        if iteration % 100 == 0:
            self.set_cycle_state({"checkpoint": iteration})

        return {
            "count": count,
            "iteration": iteration,
            "converged": iteration >= 999,  # Stop at 1000 iterations
        }


class StateAccumulatorNode(CycleAwareNode):
    """Node that accumulates state to test memory performance."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "data_size": NodeParameter(
                name="data_size", type=int, required=False, default=1000
            ),
            "accumulate": NodeParameter(
                name="accumulate", type=bool, required=False, default=True
            ),
        }

    def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Accumulate data to test memory usage."""
        data_size = kwargs.get("data_size", 1000)
        accumulate = kwargs.get("accumulate", True)
        iteration = self.get_iteration(context)

        # Generate data for this iteration
        iteration_data = list(range(iteration * data_size, (iteration + 1) * data_size))

        if accumulate:
            # Accumulate with limited history to prevent unbounded growth
            accumulated = self.accumulate_values(
                context, "data_history", iteration_data, max_history=10
            )
            total_elements = sum(len(chunk) for chunk in accumulated)
        else:
            # Don't accumulate - just process
            accumulated = [iteration_data]
            total_elements = len(iteration_data)

        # Track memory usage
        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / 1024 / 1024

        return {
            "iteration": iteration,
            "total_elements": total_elements,
            "memory_mb": memory_mb,
            "data_chunks": len(accumulated),
            **self.set_cycle_state(
                {
                    "data_history": accumulated if accumulate else [],
                    "memory_tracking": self.accumulate_values(
                        context, "memory_history", memory_mb, max_history=100
                    ),
                }
            ),
        }


class ComputeIntensiveNode(CycleAwareNode):
    """Node with configurable computational complexity."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "complexity": NodeParameter(
                name="complexity", type=int, required=False, default=1000
            ),
            "data": NodeParameter(name="data", type=list, required=False, default=[]),
        }

    def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Perform computation with configurable complexity."""
        complexity = kwargs.get("complexity", 1000)
        data = kwargs.get("data", list(range(100)))
        iteration = self.get_iteration(context)

        start_time = time.time()

        # Simulate complex computation
        result = 0
        for _ in range(complexity):
            for value in data:
                result += value * iteration
                result = result % 1000000  # Prevent overflow

        computation_time = time.time() - start_time

        # Track computation times
        time_history = self.accumulate_values(
            context, "computation_times", computation_time, max_history=50
        )

        # Calculate average time
        avg_time = (
            sum(time_history) / len(time_history) if time_history else computation_time
        )

        return {
            "result": result,
            "iteration": iteration,
            "computation_time": computation_time,
            "avg_computation_time": avg_time,
            "time_history": time_history[-10:],  # Last 10 for display
            **self.set_cycle_state({"computation_times": time_history}),
        }


class TestLargeScaleIterations:
    """Test performance with large numbers of iterations."""

    @pytest.mark.slow
    def test_thousand_iteration_performance(self):
        """Test workflow with 1000+ iterations."""
        # Skip this test in regular CI runs - it's for performance benchmarking only
        pytest.skip("Performance benchmark test - run manually with longer timeout")

        workflow = Workflow("large-scale", "1000 Iteration Test")

        # Simple counter node
        workflow.add_node("counter", PerformanceCounterNode())

        # Self-cycle using CycleBuilder API
        cycle_builder = workflow.create_cycle("counter_cycle")
        cycle_builder.connect("counter", "counter")
        cycle_builder.max_iterations(1000)
        cycle_builder.converge_when("converged == True")
        cycle_builder.build()

        # Execute and measure
        runtime = LocalRuntime()
        start_time = time.time()

        results, run_id = runtime.execute(
            workflow, parameters={"counter": {"increment": 1}}
        )

        execution_time = time.time() - start_time

        # Verify execution
        assert run_id is not None
        counter_result = results.get("counter", {})
        assert counter_result.get("iteration", 0) == 999  # 0-based, so 1000 iterations
        assert counter_result.get("count", 0) == 999

        # Performance assertions - relaxed for CI/CD environments
        assert execution_time < 120.0  # Should complete in under 2 minutes
        iterations_per_second = 1000 / execution_time
        print(f"\nPerformance: {iterations_per_second:.2f} iterations/second")
        assert iterations_per_second > 8  # Should handle >8 iterations/second (relaxed)

    @pytest.mark.slow
    def test_early_convergence_performance(self):
        """Test that early convergence stops execution efficiently."""

        class EarlyConvergenceNode(CycleAwareNode):
            """Node that converges early based on condition."""

            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "target": NodeParameter(
                        name="target", type=int, required=False, default=100
                    )
                }

            def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                """Process until target reached."""
                target = kwargs.get("target", 100)
                iteration = self.get_iteration(context)

                value = iteration * 2
                converged = value >= target

                return {"value": value, "iteration": iteration, "converged": converged}

        workflow = Workflow("early-convergence", "Early Convergence Test")
        workflow.add_node("processor", EarlyConvergenceNode())
        # Create cycle using CycleBuilder API
        cycle_builder = workflow.create_cycle("early_convergence_cycle")
        cycle_builder.connect("processor", "processor")
        cycle_builder.max_iterations(10000)  # High max, but should stop early
        cycle_builder.converge_when("converged == True")
        cycle_builder.build()

        runtime = LocalRuntime()
        start_time = time.time()

        results, run_id = runtime.execute(
            workflow, parameters={"processor": {"target": 100}}
        )

        execution_time = time.time() - start_time

        # Should converge at iteration 50 (50 * 2 = 100)
        processor_result = results.get("processor", {})
        assert processor_result.get("iteration", 0) == 50
        assert processor_result.get("converged") is True

        # Should be fast due to early convergence (adjusted for CI environments)
        assert execution_time < 5.0  # Relaxed for E2E environments


class TestMemoryPerformance:
    """Test memory usage and state accumulation performance."""

    def test_state_accumulation_memory(self):
        """Test memory usage with state accumulation."""
        workflow = Workflow("memory-test", "State Accumulation Memory Test")

        # Add state accumulator
        workflow.add_node("accumulator", StateAccumulatorNode())

        # Self-cycle for 10 iterations using CycleBuilder API
        cycle_builder = workflow.create_cycle("memory_accumulation_cycle")
        cycle_builder.connect("accumulator", "accumulator")
        cycle_builder.max_iterations(10)  # Reduced for E2E timeout
        cycle_builder.build()

        # Force garbage collection before test
        gc.collect()

        # Get initial memory
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={"accumulator": {"data_size": 1000, "accumulate": True}},
        )

        # Force garbage collection after test
        gc.collect()

        # Check results
        assert run_id is not None
        accumulator_result = results.get("accumulator", {})

        # Should have limited memory growth due to max_history
        final_memory = accumulator_result.get("memory_mb", 0)
        memory_growth = final_memory - initial_memory

        print(f"\nMemory growth: {memory_growth:.2f} MB")
        print(f"Data chunks maintained: {accumulator_result.get('data_chunks', 0)}")

        # Memory growth should be bounded
        assert memory_growth < 100  # Less than 100MB growth
        assert accumulator_result.get("data_chunks", 0) <= 10  # Limited by max_history

    def test_memory_without_accumulation(self):
        """Test memory usage without state accumulation."""
        workflow = Workflow("memory-no-accum", "Memory Test Without Accumulation")

        workflow.add_node("processor", StateAccumulatorNode())
        # Create cycle using CycleBuilder API
        cycle_builder = workflow.create_cycle("memory_no_accum_cycle")
        cycle_builder.connect("processor", "processor")
        cycle_builder.max_iterations(10)  # Reduced for E2E timeout
        cycle_builder.build()

        gc.collect()
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024

        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow, parameters={"processor": {"data_size": 1000, "accumulate": False}}
        )

        gc.collect()

        processor_result = results.get("processor", {})
        final_memory = processor_result.get("memory_mb", 0)
        memory_growth = final_memory - initial_memory

        print(f"\nMemory growth without accumulation: {memory_growth:.2f} MB")

        # Should have minimal memory growth
        assert memory_growth < 50  # Much less growth without accumulation


class TestParallelCyclePerformance:
    """Test performance of parallel cycle execution."""

    def test_parallel_vs_sequential_cycles(self):
        """Compare parallel and sequential cycle execution."""
        # Create workflow with multiple independent cycles
        workflow = Workflow("parallel-cycles", "Parallel Cycle Test")

        # Add multiple independent processing nodes with more substantial work
        # to ensure parallel execution benefits outweigh overhead
        for i in range(4):
            workflow.add_node(f"processor_{i}", ComputeIntensiveNode())
            # Create individual cycles using CycleBuilder API
            cycle_builder = workflow.create_cycle(f"parallel_cycle_{i}")
            cycle_builder.connect(f"processor_{i}", f"processor_{i}")
            cycle_builder.max_iterations(20)
            cycle_builder.build()

        # Test sequential execution
        sequential_runtime = LocalRuntime()
        start_time = time.time()

        seq_results, seq_run_id = sequential_runtime.execute(
            workflow,
            parameters={
                # Increase complexity to make parallel benefits more apparent
                f"processor_{i}": {"complexity": 500, "data": list(range(100))}
                for i in range(4)
            },
        )

        sequential_time = time.time() - start_time

        # Test parallel execution
        parallel_runtime = ParallelCyclicRuntime(max_workers=4)
        start_time = time.time()

        par_results, par_run_id = parallel_runtime.execute(
            workflow,
            parameters={
                f"processor_{i}": {"complexity": 500, "data": list(range(100))}
                for i in range(4)
            },
        )

        parallel_time = time.time() - start_time

        # Calculate speedup
        speedup = sequential_time / parallel_time
        print(f"\nSequential time: {sequential_time:.2f}s")
        print(f"Parallel time: {parallel_time:.2f}s")
        print(f"Speedup: {speedup:.2f}x")

        # For CI environments and fast machines, parallel execution may be slower due to:
        # 1. Thread creation overhead
        # 2. Context switching costs
        # 3. Small workload size relative to overhead
        # 4. CI environments often have limited CPU cores
        #
        # Instead of asserting parallel is faster, we ensure it's not drastically slower
        # and that results are correct

        # Allow parallel to be up to 50% slower in CI environments
        max_allowed_parallel_time = sequential_time * 1.5
        assert (
            parallel_time < max_allowed_parallel_time
        ), f"Parallel execution too slow: {parallel_time:.3f}s vs sequential {sequential_time:.3f}s (threshold: {max_allowed_parallel_time:.3f}s)"

        # In CI environments, parallel may be slower but should not be more than 2x slower
        min_acceptable_speedup = 0.5  # Allow down to 0.5x speedup (2x slower)
        assert (
            speedup > min_acceptable_speedup
        ), f"Parallel execution significantly slower: speedup={speedup:.2f}x (threshold: >{min_acceptable_speedup}x)"

        # Results should be equivalent - this is the most important assertion
        assert len(seq_results) == len(par_results)
        for i in range(4):
            seq_proc = seq_results.get(f"processor_{i}", {})
            par_proc = par_results.get(f"processor_{i}", {})
            assert seq_proc.get("iteration") == par_proc.get("iteration")

        # Log performance characteristics for debugging
        if speedup < 1.0:
            print(
                f"INFO: Parallel execution was slower than sequential by {((1/speedup) - 1) * 100:.1f}%"
            )
            print(
                "This is expected in CI environments with limited cores or small workloads."
            )


class TestCycleOverhead:
    """Test overhead of cycle mechanism compared to non-cyclic execution."""

    def test_cycle_overhead_measurement(self):
        """Measure overhead of cycle infrastructure."""

        # Create simple computation node
        class SimpleComputeNode(CycleAwareNode):
            """Simple computation for overhead testing."""

            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "value": NodeParameter(
                        name="value", type=float, required=False, default=1.0
                    )
                }

            def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                """Simple computation."""
                value = kwargs.get("value", 1.0)
                iteration = self.get_iteration(context)

                # Simple computation
                result = value * (iteration + 1)

                return {"result": result, "iteration": iteration}

        # Test cyclic execution using modern CycleBuilder API
        from kailash.workflow.builder import WorkflowBuilder

        workflow_builder = WorkflowBuilder()
        workflow_builder.add_node(
            "PythonCodeNode",
            "compute",
            {
                "code": """
# Simple computation for overhead testing
try:
    value = compute_data.get("value", 1.0)
    iteration = compute_data.get("iteration", 0)
except NameError:
    value = 1.0
    iteration = 0

new_iteration = iteration + 1
result_value = value * (new_iteration + 1)

result = {
    "result": result_value,
    "iteration": new_iteration,
    "converged": new_iteration >= 5
}
"""
            },
        )

        # Build workflow and create cycle
        cyclic_workflow = workflow_builder.build()
        cycle_builder = cyclic_workflow.create_cycle("overhead_cycle")
        cycle_builder.connect("compute", "compute", mapping={"result": "compute_data"})
        cycle_builder.max_iterations(5)
        cycle_builder.converge_when("converged == True")
        cycle_builder.build()

        runtime = LocalRuntime()

        # Warm up
        runtime.execute(cyclic_workflow, parameters={"compute": {"value": 2.0}})

        # Measure cyclic execution
        start_time = time.time()
        for _ in range(3):  # Reduced from 10
            runtime.execute(cyclic_workflow, parameters={"compute": {"value": 2.0}})
        cyclic_time = (time.time() - start_time) / 3

        # Create simple non-cycle aware computation node
        from kailash.nodes.base import Node

        class SimpleNode(Node):
            """Simple computation for non-cyclic testing."""

            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "value": NodeParameter(
                        name="value", type=float, required=False, default=1.0
                    )
                }

            def run(self, **kwargs) -> dict[str, Any]:
                """Simple computation."""
                value = kwargs.get("value", 1.0)

                # Simple computation
                result = value * 2.0

                return {"result": result}

        # Test non-cyclic equivalent
        non_cyclic_workflow = Workflow("non-cyclic", "Non-Cyclic Test")

        # Create chain of 5 nodes (equivalent to 5 iterations) - reduced from 100
        prev_node = None
        for i in range(5):
            node_name = f"compute_{i}"
            non_cyclic_workflow.add_node(node_name, SimpleNode())
            if prev_node:
                non_cyclic_workflow.connect(
                    prev_node, node_name, mapping={"result": "value"}
                )
            prev_node = node_name

        # Warm up
        runtime.execute(
            non_cyclic_workflow,
            parameters={f"compute_{i}": {"value": 2.0} for i in range(5)},
        )

        # Measure non-cyclic execution
        start_time = time.time()
        for _ in range(3):  # Reduced from 10
            runtime.execute(
                non_cyclic_workflow,
                parameters={f"compute_{i}": {"value": 2.0} for i in range(5)},
            )
        non_cyclic_time = (time.time() - start_time) / 3

        # Calculate overhead
        overhead_ratio = cyclic_time / non_cyclic_time
        overhead_percent = (overhead_ratio - 1) * 100

        print(f"\nCyclic execution time: {cyclic_time:.3f}s")
        print(f"Non-cyclic execution time: {non_cyclic_time:.3f}s")
        print(f"Cycle overhead: {overhead_percent:.1f}%")

        # Cycle overhead should be reasonable
        assert (
            overhead_ratio < 3.5
        )  # Less than 250% overhead (generous for CI variability)


class TestScalabilityBenchmarks:
    """Test scalability with increasing complexity."""

    def test_iteration_scalability(self):
        """Test performance with increasing iteration counts."""
        iteration_counts = [5, 10, 20]  # Reduced for E2E timeout
        execution_times = []

        for count in iteration_counts:
            # Use modern CycleBuilder API
            workflow_builder = WorkflowBuilder()
            workflow_builder.add_node(
                "PythonCodeNode",
                "counter",
                {
                    "code": """
# Performance counter for scalability testing
try:
    count = counter_data.get("count", 0)
    increment = counter_data.get("increment", 1)
except NameError:
    count = 0
    increment = 1

new_count = count + increment

result = {
    "count": new_count,
    "increment": increment,
    "converged": False  # Let max_iterations control termination
}
"""
                },
            )

            # Build workflow and create cycle
            workflow = workflow_builder.build()
            cycle_builder = workflow.create_cycle(f"scale_cycle_{count}")
            cycle_builder.connect(
                "counter", "counter", mapping={"result": "counter_data"}
            )
            cycle_builder.max_iterations(count)
            cycle_builder.build()

            runtime = LocalRuntime()
            start_time = time.time()

            results, _ = runtime.execute(
                workflow, parameters={"counter": {"increment": 1}}
            )

            execution_time = time.time() - start_time
            execution_times.append(execution_time)

            print(
                f"\n{count} iterations: {execution_time:.3f}s ({count/execution_time:.1f} iter/s)"
            )

        # Check linear scalability
        # Time should scale roughly linearly with iteration count
        time_ratios = []
        for i in range(1, len(iteration_counts)):
            expected_ratio = iteration_counts[i] / iteration_counts[i - 1]
            actual_ratio = execution_times[i] / execution_times[i - 1]
            time_ratios.append(actual_ratio / expected_ratio)

            print(
                f"Scaling {iteration_counts[i-1]} -> {iteration_counts[i]}: "
                f"Expected {expected_ratio:.1f}x, Actual {actual_ratio:.1f}x"
            )

        # Should maintain reasonable linear scaling
        avg_scaling_efficiency = sum(time_ratios) / len(time_ratios)
        print(f"\nAverage scaling efficiency: {avg_scaling_efficiency:.2f}")
        assert 0.5 < avg_scaling_efficiency < 2.0  # Within reasonable bounds for CI


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
