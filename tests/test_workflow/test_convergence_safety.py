"""
Test suite for Phase 2: Convergence & Safety Framework

Tests the convergence and safety features implemented in Phase 2.1-2.3:
- Expression-based convergence conditions
- Timeout safety mechanisms
- Maximum iteration limits
- Compound convergence conditions
- Resource monitoring and safety
"""

import sys
import time
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from kailash.nodes.base import Node, NodeParameter
from kailash.workflow.cyclic_runner import CyclicWorkflowExecutor
from kailash.workflow.graph import Workflow


class QualityOptimizerTestNode(Node):
    """Test node that gradually improves a quality score."""

    def get_parameters(self):
        return {
            "quality": NodeParameter(
                name="quality",
                type=float,
                required=False,
                default=0.0,
                description="Current quality score",
            ),
            "improvement_rate": NodeParameter(
                name="improvement_rate",
                type=float,
                required=False,
                default=0.1,
                description="Rate of improvement",
            ),
        }

    def run(self, context, **kwargs):

        quality = kwargs.get("quality", 0.0)
        improvement_rate = kwargs.get("improvement_rate", 0.1)

        # Get cycle information
        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        # Deterministic improvement for testing
        new_quality = min(1.0, quality + improvement_rate)

        return {
            "quality": new_quality,
            "improvement": new_quality - quality,
            "iteration": iteration,
        }


class ProcessorTestNode(Node):
    """Test node that processes data with error rate improvement."""

    def get_parameters(self):
        return {
            "error_rate": NodeParameter(
                name="error_rate",
                type=float,
                required=False,
                default=0.5,
                description="Current error rate",
            ),
            "processed_count": NodeParameter(
                name="processed_count",
                type=int,
                required=False,
                default=0,
                description="Processed count",
            ),
        }

    def run(self, context, **kwargs):
        error_rate = kwargs.get("error_rate", 0.5)
        processed_count = kwargs.get("processed_count", 0)

        # Get cycle information
        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        # Deterministic improvement for testing
        new_error_rate = max(0.01, error_rate * 0.9)  # 10% improvement each iteration
        new_processed_count = processed_count + 100

        return {
            "error_rate": new_error_rate,
            "processed_count": new_processed_count,
            "iteration": iteration,
        }


class ResourceTestNode(Node):
    """Test node that simulates resource usage."""

    def get_parameters(self):
        return {
            "processing_time": NodeParameter(
                name="processing_time",
                type=float,
                required=False,
                default=0.05,
                description="Processing time",
            ),
            "iteration": NodeParameter(
                name="iteration",
                type=int,
                required=False,
                default=0,
                description="Iteration count",
            ),
        }

    def run(self, context, **kwargs):
        processing_time = kwargs.get("processing_time", 0.05)
        iteration = kwargs.get("iteration", 0)

        # Simulate short processing time for tests
        time.sleep(processing_time)

        return {"processing_time": processing_time, "iteration": iteration + 1}


class TestConvergenceFramework:
    """Test suite for convergence and safety framework."""

    def test_expression_convergence_simple(self):
        """Test simple expression-based convergence."""
        workflow = Workflow(
            workflow_id="test_expression_convergence",
            name="Test Expression Convergence",
        )

        optimizer = QualityOptimizerTestNode()
        workflow.add_node("optimizer", optimizer)

        # Create cycle with expression convergence
        workflow.connect(
            "optimizer",
            "optimizer",
            mapping={"quality": "quality", "improvement_rate": "improvement_rate"},
            cycle=True,
            max_iterations=10,
            convergence_check="quality >= 0.5",
            cycle_id="quality_loop",
        )

        # Execute
        executor = CyclicWorkflowExecutor()
        results, run_id = executor.execute(
            workflow,
            parameters={
                "optimizer": {
                    "quality": 0.0,
                    "improvement_rate": 0.2,  # Will reach 0.5 in 3 iterations
                }
            },
        )

        # Verify convergence
        final_quality = results.get("optimizer", {}).get("quality")
        assert final_quality is not None
        assert final_quality >= 0.5
        assert final_quality <= 0.6  # Should stop at ~0.6 after 3 iterations

    def test_expression_convergence_greater_than(self):
        """Test expression convergence with greater than condition."""
        workflow = Workflow(
            workflow_id="test_gt_convergence", name="Test Greater Than Convergence"
        )

        optimizer = QualityOptimizerTestNode()
        workflow.add_node("optimizer", optimizer)

        workflow.connect(
            "optimizer",
            "optimizer",
            mapping={"quality": "quality", "improvement_rate": "improvement_rate"},
            cycle=True,
            max_iterations=15,
            convergence_check="quality > 0.8",
            cycle_id="gt_loop",
        )

        executor = CyclicWorkflowExecutor()
        results, run_id = executor.execute(
            workflow,
            parameters={"optimizer": {"quality": 0.0, "improvement_rate": 0.25}},
        )

        final_quality = results.get("optimizer", {}).get("quality")
        assert final_quality > 0.8

    def test_compound_convergence_and(self):
        """Test compound convergence with AND condition."""
        workflow = Workflow(
            workflow_id="test_compound_and", name="Test Compound AND Convergence"
        )

        processor = ProcessorTestNode()
        workflow.add_node("processor", processor)

        # Create cycle with compound convergence (AND condition)
        workflow.connect(
            "processor",
            "processor",
            mapping={"error_rate": "error_rate", "processed_count": "processed_count"},
            cycle=True,
            max_iterations=15,
            convergence_check="error_rate < 0.2 and processed_count >= 300",
            cycle_id="and_loop",
        )

        executor = CyclicWorkflowExecutor()
        results, run_id = executor.execute(
            workflow,
            parameters={"processor": {"error_rate": 0.5, "processed_count": 0}},
        )

        # Verify both conditions are met
        final_error_rate = results.get("processor", {}).get("error_rate")
        final_processed = results.get("processor", {}).get("processed_count")

        assert final_error_rate < 0.2
        assert final_processed >= 300

    def test_compound_convergence_or(self):
        """Test compound convergence with OR condition."""
        workflow = Workflow(
            workflow_id="test_compound_or", name="Test Compound OR Convergence"
        )

        processor = ProcessorTestNode()
        workflow.add_node("processor", processor)

        # Create cycle with compound convergence (OR condition)
        workflow.connect(
            "processor",
            "processor",
            mapping={"error_rate": "error_rate", "processed_count": "processed_count"},
            cycle=True,
            max_iterations=15,
            convergence_check="error_rate < 0.1 or processed_count >= 500",
            cycle_id="or_loop",
        )

        executor = CyclicWorkflowExecutor()
        results, run_id = executor.execute(
            workflow,
            parameters={"processor": {"error_rate": 0.5, "processed_count": 0}},
        )

        # Verify at least one condition is met
        final_error_rate = results.get("processor", {}).get("error_rate")
        final_processed = results.get("processor", {}).get("processed_count")

        # Should reach 500 processed before error_rate gets below 0.1
        assert final_processed >= 500 or final_error_rate < 0.1

    def test_max_iterations_safety(self):
        """Test maximum iterations safety limit."""
        workflow = Workflow(
            workflow_id="test_max_iterations", name="Test Max Iterations Safety"
        )

        optimizer = QualityOptimizerTestNode()
        workflow.add_node("optimizer", optimizer)

        # Create cycle with low max_iterations
        workflow.connect(
            "optimizer",
            "optimizer",
            mapping={"quality": "quality", "improvement_rate": "improvement_rate"},
            cycle=True,
            max_iterations=3,  # Low limit
            convergence_check="quality >= 2.0",  # Impossible to reach
            cycle_id="limited_loop",
        )

        executor = CyclicWorkflowExecutor()
        results, run_id = executor.execute(
            workflow,
            parameters={
                "optimizer": {
                    "quality": 0.0,
                    "improvement_rate": 0.1,  # Small improvement
                }
            },
        )

        # Should stop after 3 iterations due to max_iterations limit
        final_iteration = results.get("optimizer", {}).get("iteration")
        final_quality = results.get("optimizer", {}).get("quality")

        assert final_iteration is not None
        assert final_iteration <= 3  # Should respect max_iterations
        assert final_quality < 2.0  # Should not reach impossible convergence
        assert (
            final_quality <= 0.31
        )  # Should be around 0.3 after 3 iterations (allow for floating point precision)

    def test_timeout_safety(self):
        """Test timeout safety mechanism."""
        workflow = Workflow(workflow_id="test_timeout", name="Test Timeout Safety")

        processor = ResourceTestNode()
        workflow.add_node("processor", processor)

        # Create cycle with timeout
        workflow.connect(
            "processor",
            "processor",
            mapping={"processing_time": "processing_time", "iteration": "iteration"},
            cycle=True,
            max_iterations=20,
            timeout=0.5,  # 0.5 second timeout
            convergence_check="iteration >= 50",  # Unrealistic convergence
            cycle_id="timeout_loop",
        )

        start_time = time.time()
        executor = CyclicWorkflowExecutor()

        # Should complete before timeout or be terminated by timeout
        results, run_id = executor.execute(
            workflow,
            parameters={
                "processor": {
                    "processing_time": 0.1,  # Each iteration takes 0.1s
                    "iteration": 0,
                }
            },
        )

        end_time = time.time()
        total_time = end_time - start_time

        # Should respect timeout (allow some overhead)
        assert total_time <= 1.0  # Should terminate within reasonable time

        final_iteration = results.get("processor", {}).get("iteration")
        assert final_iteration is not None
        assert final_iteration < 50  # Should not reach unrealistic convergence

    def test_no_convergence_max_iterations(self):
        """Test behavior when no convergence is reached and max iterations hit."""
        workflow = Workflow(
            workflow_id="test_no_convergence", name="Test No Convergence"
        )

        optimizer = QualityOptimizerTestNode()
        workflow.add_node("optimizer", optimizer)

        workflow.connect(
            "optimizer",
            "optimizer",
            mapping={"quality": "quality", "improvement_rate": "improvement_rate"},
            cycle=True,
            max_iterations=5,
            convergence_check="quality >= 10.0",  # Impossible condition
            cycle_id="no_convergence_loop",
        )

        executor = CyclicWorkflowExecutor()
        results, run_id = executor.execute(
            workflow,
            parameters={"optimizer": {"quality": 0.0, "improvement_rate": 0.1}},
        )

        # Should stop at max_iterations
        final_iteration = results.get("optimizer", {}).get("iteration")
        final_quality = results.get("optimizer", {}).get("quality")

        assert final_iteration <= 5
        assert final_quality < 10.0  # Should not reach impossible convergence
        assert final_quality <= 0.5  # Should be around 0.5 after 5 iterations

    def test_immediate_convergence(self):
        """Test immediate convergence on first iteration."""
        workflow = Workflow(
            workflow_id="test_immediate", name="Test Immediate Convergence"
        )

        optimizer = QualityOptimizerTestNode()
        workflow.add_node("optimizer", optimizer)

        workflow.connect(
            "optimizer",
            "optimizer",
            mapping={"quality": "quality", "improvement_rate": "improvement_rate"},
            cycle=True,
            max_iterations=10,
            convergence_check="quality >= 0.0",  # Always true after first iteration
            cycle_id="immediate_loop",
        )

        executor = CyclicWorkflowExecutor()
        results, run_id = executor.execute(
            workflow,
            parameters={"optimizer": {"quality": 0.0, "improvement_rate": 0.3}},
        )

        # Should converge after first iteration
        final_quality = results.get("optimizer", {}).get("quality")
        assert final_quality >= 0.3  # Should have improved in first iteration
        assert final_quality <= 0.3  # Should stop after first iteration

    def test_convergence_with_complex_expression(self):
        """Test convergence with complex mathematical expressions."""
        workflow = Workflow(
            workflow_id="test_complex_expr", name="Test Complex Expression"
        )

        processor = ProcessorTestNode()
        workflow.add_node("processor", processor)

        # Complex expression with mathematical operations
        workflow.connect(
            "processor",
            "processor",
            mapping={"error_rate": "error_rate", "processed_count": "processed_count"},
            cycle=True,
            max_iterations=10,
            convergence_check="(error_rate * processed_count) < 50",
            cycle_id="complex_expr_loop",
        )

        executor = CyclicWorkflowExecutor()
        results, run_id = executor.execute(
            workflow,
            parameters={"processor": {"error_rate": 0.5, "processed_count": 0}},
        )

        final_error_rate = results.get("processor", {}).get("error_rate")
        final_processed = results.get("processor", {}).get("processed_count")

        # Verify complex expression condition
        assert (final_error_rate * final_processed) < 50


if __name__ == "__main__":
    # Run tests when executed directly
    pytest.main([__file__, "-v"])
