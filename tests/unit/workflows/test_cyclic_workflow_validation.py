#!/usr/bin/env python3
"""
Comprehensive cyclic workflow validation tests for tier 1 (unit tests).
Tests all cyclic patterns using CycleBuilder API with actual execution.
"""

import sys
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))


class TestCyclicWorkflowValidation:
    """Unit tests for cyclic workflow patterns."""

    def test_basic_counter_cycle(self):
        """Test basic counter cycle that converges."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()

        # Simple counter that increments until it reaches 3
        workflow.add_node(
            "PythonCodeNode",
            "counter",
            {
                "code": """
# Simple counter cycle
try:
    count = counter_input.get("count", 0)
except NameError:
    count = 0

new_count = count + 1
result = {
    "count": new_count,
    "converged": new_count >= 3
}
"""
            },
        )

        # Build workflow first
        built_workflow = workflow.build()

        # Create cycle using CycleBuilder API
        cycle_builder = built_workflow.create_cycle("counter_cycle")
        cycle_builder.connect("counter", "counter", mapping={"result": "counter_input"})
        cycle_builder.max_iterations(5)
        cycle_builder.converge_when("converged == True")
        cycle_builder.build()

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(built_workflow)

        final_count = results.get("counter", {}).get("result", {}).get("count", 0)
        converged = results.get("counter", {}).get("result", {}).get("converged", False)

        assert final_count == 3
        assert converged is True

    def test_quality_improvement_cycle(self):
        """Test quality improvement cycle."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()

        # Quality improvement processor
        workflow.add_node(
            "PythonCodeNode",
            "improver",
            {
                "code": """
# Quality improvement cycle
try:
    quality = quality_data.get("quality", 0.4)
    iteration = quality_data.get("iteration", 0)
except NameError:
    quality = 0.4
    iteration = 0

# Improve quality each iteration
new_quality = min(quality + 0.15, 1.0)
new_iteration = iteration + 1

result = {
    "quality": new_quality,
    "iteration": new_iteration,
    "converged": new_quality >= 0.9
}
"""
            },
        )

        # Build and create cycle
        built_workflow = workflow.build()
        cycle_builder = built_workflow.create_cycle("quality_cycle")
        cycle_builder.connect(
            "improver", "improver", mapping={"result": "quality_data"}
        )
        cycle_builder.max_iterations(4)
        cycle_builder.converge_when("converged == True")
        cycle_builder.build()

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(built_workflow)

        final_quality = results.get("improver", {}).get("result", {}).get("quality", 0)
        converged = (
            results.get("improver", {}).get("result", {}).get("converged", False)
        )

        assert converged is True
        assert final_quality >= 0.9

    def test_retry_cycle(self):
        """Test retry cycle pattern."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()

        # Retry processor
        workflow.add_node(
            "PythonCodeNode",
            "retrier",
            {
                "code": """
# Retry cycle - simulates success after retries
try:
    retry_count = retry_data.get("retry_count", 0)
    max_retries = retry_data.get("max_retries", 3)
except NameError:
    retry_count = 0
    max_retries = 3

new_retry_count = retry_count + 1

# Simulate success after 2 retries
success = new_retry_count >= 2
data = {"records": 100} if success else None

result = {
    "retry_count": new_retry_count,
    "max_retries": max_retries,
    "success": success,
    "data": data,
    "converged": success or new_retry_count >= max_retries
}
"""
            },
        )

        # Build and create cycle
        built_workflow = workflow.build()
        cycle_builder = built_workflow.create_cycle("retry_cycle")
        cycle_builder.connect("retrier", "retrier", mapping={"result": "retry_data"})
        cycle_builder.max_iterations(5)
        cycle_builder.converge_when("converged == True")
        cycle_builder.build()

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(built_workflow)

        retry_count = results.get("retrier", {}).get("result", {}).get("retry_count", 0)
        success = results.get("retrier", {}).get("result", {}).get("success", False)
        converged = results.get("retrier", {}).get("result", {}).get("converged", False)

        assert converged is True
        assert success is True
        assert retry_count == 2

    def test_batch_processing_cycle(self):
        """Test batch processing cycle."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()

        # Batch processor
        workflow.add_node(
            "PythonCodeNode",
            "batcher",
            {
                "code": """
# Batch processing cycle
try:
    processed = batch_data.get("processed", 0)
    total = batch_data.get("total", 50)
    batch_size = batch_data.get("batch_size", 15)
except NameError:
    processed = 0
    total = 50
    batch_size = 15

# Process next batch
new_processed = min(processed + batch_size, total)
progress = new_processed / total

result = {
    "processed": new_processed,
    "total": total,
    "batch_size": batch_size,
    "progress": progress,
    "converged": new_processed >= total
}
"""
            },
        )

        # Build and create cycle
        built_workflow = workflow.build()
        cycle_builder = built_workflow.create_cycle("batch_cycle")
        cycle_builder.connect("batcher", "batcher", mapping={"result": "batch_data"})
        cycle_builder.max_iterations(4)
        cycle_builder.converge_when("converged == True")
        cycle_builder.build()

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(built_workflow)

        processed = results.get("batcher", {}).get("result", {}).get("processed", 0)
        total = results.get("batcher", {}).get("result", {}).get("total", 0)
        progress = results.get("batcher", {}).get("result", {}).get("progress", 0)
        converged = results.get("batcher", {}).get("result", {}).get("converged", False)

        assert converged is True
        assert processed == total
        assert progress == 1.0

    def test_conditional_cycle(self):
        """Test conditional cycle with multi-stage processing."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()

        # Simple conditional processor that routes based on iteration count
        workflow.add_node(
            "PythonCodeNode",
            "processor",
            {
                "code": """
try:
    iteration = feedback_data.get("iteration", 0)
    status = feedback_data.get("status", "start")
except NameError:
    iteration = 0
    status = "start"

new_iteration = iteration + 1

# Simple logic: process -> validate -> complete
if new_iteration == 1:
    action = "processing"
    converged = False
elif new_iteration == 2:
    action = "validating"
    converged = False
else:
    action = "completed"
    converged = True

result = {
    "action": action,
    "iteration": new_iteration,
    "converged": converged
}
"""
            },
        )

        # Build and create cycle
        built_workflow = workflow.build()

        # Simple cycle - processor cycles back to itself
        cycle_builder = built_workflow.create_cycle("conditional_cycle")
        cycle_builder.connect(
            "processor", "processor", mapping={"result": "feedback_data"}
        )
        cycle_builder.max_iterations(5)
        cycle_builder.converge_when("converged == True")
        cycle_builder.build()

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(built_workflow)

        # Check that we reached completion
        processor_result = results.get("processor", {}).get("result", {})
        converged = processor_result.get("converged", False)
        action = processor_result.get("action", "")
        iteration = processor_result.get("iteration", 0)

        assert converged is True
        assert action == "completed"
        assert iteration >= 3


class TestAdvancedCyclicPatterns:
    """Tests for advanced cyclic patterns including SwitchNode routing."""

    def test_switchnode_conditional_cycle(self):
        """Test actual SwitchNode conditional routing in a cycle."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()

        # Data source that changes status over iterations
        workflow.add_node(
            "PythonCodeNode",
            "data_source",
            {
                "code": """
try:
    iteration = feedback.get("iteration", 0)
    last_action = feedback.get("action", "start")
except NameError:
    iteration = 0
    last_action = "start"

new_iteration = iteration + 1

# Progress through states based on what happened last
if new_iteration == 1 or last_action == "start":
    status = "needs_processing"
elif last_action == "processed":
    status = "needs_validation"
elif last_action == "validated":
    status = "complete"
else:
    status = "complete"

result = {
    "iteration": new_iteration,
    "status": status,
    "data": [1, 2, 3],
    "last_action": last_action
}
"""
            },
        )

        # SwitchNode for routing based on status
        workflow.add_node(
            "SwitchNode",
            "router",
            {
                "condition_field": "status",
                "cases": ["needs_processing", "needs_validation", "complete"],
            },
        )

        # Processor for processing path (cycles back)
        workflow.add_node(
            "PythonCodeNode",
            "processor",
            {
                "code": """
result = {
    "action": "processed",
    "iteration": source_data.get("iteration", 0),
    "converged": False
}
"""
            },
        )

        # Validator for validation path (cycles back)
        workflow.add_node(
            "PythonCodeNode",
            "validator",
            {
                "code": """
result = {
    "action": "validated",
    "iteration": source_data.get("iteration", 0),
    "converged": False
}
"""
            },
        )

        # Completer for completion path (terminates - no cycle)
        workflow.add_node(
            "PythonCodeNode",
            "completer",
            {
                "code": """
result = {
    "action": "completed",
    "iteration": source_data.get("iteration", 0),
    "converged": True
}
"""
            },
        )

        # Forward connections
        workflow.add_connection("data_source", "result", "router", "input")
        workflow.add_connection(
            "router", "case_needs_processing", "processor", "source_data"
        )
        workflow.add_connection(
            "router", "case_needs_validation", "validator", "source_data"
        )
        workflow.add_connection("router", "case_complete", "completer", "source_data")

        # Build workflow
        built_workflow = workflow.build()

        # Create cycles for processor and validator paths (but NOT completer)
        cycle1 = built_workflow.create_cycle("processing_cycle")
        cycle1.connect("processor", "data_source", mapping={"result": "feedback"})
        cycle1.max_iterations(3)
        cycle1.build()

        cycle2 = built_workflow.create_cycle("validation_cycle")
        cycle2.connect("validator", "data_source", mapping={"result": "feedback"})
        cycle2.max_iterations(3)
        cycle2.build()

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(built_workflow)

        # Check which nodes executed
        executed_nodes = []
        if "processor" in results and results["processor"] is not None:
            executed_nodes.append("processor")
        if "validator" in results and results["validator"] is not None:
            executed_nodes.append("validator")
        if "completer" in results and results["completer"] is not None:
            executed_nodes.append("completer")

        # Check if we progressed through the workflow properly
        data_source_result = results.get("data_source", {}).get("result", {})
        final_iteration = data_source_result.get("iteration", 0)

        # Check if execution progressed and router made decisions
        assert final_iteration >= 2
        assert len(executed_nodes) > 0

    def test_multi_node_cycle(self):
        """Test a simple two-node cycle (A -> B -> A)."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()

        # Node A - increments counter
        workflow.add_node(
            "PythonCodeNode",
            "node_a",
            {
                "code": """
try:
    count = b_data.get("count", 0)
    stage = b_data.get("stage", "start")
except NameError:
    count = 0
    stage = "start"

new_count = count + 1

result = {
    "count": new_count,
    "stage": "processed_by_a",
    "converged": new_count >= 3
}
"""
            },
        )

        # Node B - processes and passes back
        workflow.add_node(
            "PythonCodeNode",
            "node_b",
            {
                "code": """
result = {
    "count": a_data.get("count", 0),
    "stage": "processed_by_b",
    "converged": a_data.get("converged", False)
}
"""
            },
        )

        # Forward connection A -> B
        workflow.add_connection("node_a", "result", "node_b", "a_data")

        # Build and create cycle B -> A
        built_workflow = workflow.build()
        cycle_builder = built_workflow.create_cycle("two_node_cycle")
        cycle_builder.connect("node_b", "node_a", mapping={"result": "b_data"})
        cycle_builder.max_iterations(4)
        cycle_builder.build()

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(built_workflow)

        node_a_result = results.get("node_a", {}).get("result", {})

        count = node_a_result.get("count", 0)
        converged = node_a_result.get("converged", False)

        assert converged is True
        assert count >= 3
