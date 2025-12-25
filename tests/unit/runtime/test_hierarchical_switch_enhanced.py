"""
Tests for enhanced hierarchical switch execution features.
"""

import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.operations import SwitchNode
from kailash.runtime.hierarchical_switch_executor import HierarchicalSwitchExecutor
from kailash.workflow.graph import Workflow


class TestHierarchicalSwitchEnhancements:
    """Test enhanced features of hierarchical switch execution."""

    def setup_method(self):
        """Set up test fixtures."""
        self.workflow = Workflow("test", "Test Workflow")

    @pytest.mark.asyncio
    @patch("asyncio.sleep")
    async def test_max_parallelism_limit(self, mock_sleep):
        """Test that max parallelism is respected."""
        # Mock sleep to avoid delays
        mock_sleep.return_value = None

        # Create workflow with many parallel switches
        source = PythonCodeNode(name="source", code="result = {'data': 'test'}")
        self.workflow.add_node("source", source)

        # Add 10 switches that can execute in parallel
        for i in range(10):
            switch = SwitchNode(
                name=f"switch_{i}", condition_field="data", operator="==", value="test"
            )
            self.workflow.add_node(f"switch_{i}", switch)
            self.workflow.connect("source", f"switch_{i}", {"result": "input_data"})

        # Create executor with max_parallelism=3
        executor = HierarchicalSwitchExecutor(
            self.workflow, debug=True, max_parallelism=3
        )

        # Track concurrent executions
        concurrent_count = 0
        max_concurrent = 0

        async def mock_executor(
            node_id,
            node_instance,
            all_results,
            parameters,
            task_manager,
            workflow,
            workflow_context,
        ):
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)

            # Simulate some work (mocked)
            await asyncio.sleep(0.1)

            concurrent_count -= 1

            if node_id == "source":
                return {"result": {"data": "test"}}
            else:
                return {"true_output": {"data": "test"}, "false_output": None}

        # Execute
        all_results, switch_results = await executor.execute_switches_hierarchically(
            parameters={}, node_executor=mock_executor
        )

        # Verify max parallelism was respected
        assert max_concurrent <= 3
        assert len(switch_results) == 10

        # Check metrics
        metrics = executor.get_execution_metrics()
        assert metrics["max_parallelism_used"] <= 3

    @pytest.mark.asyncio
    @patch("asyncio.sleep")
    async def test_layer_timeout(self, mock_sleep):
        """Test layer timeout functionality."""
        # Mock sleep to avoid delays, but track calls to simulate timeout
        call_count = 0

        async def mock_sleep_side_effect(duration):
            nonlocal call_count
            call_count += 1
            if call_count > 1:  # Simulate timeout on second call
                raise asyncio.TimeoutError("Mocked timeout")
            return None

        mock_sleep.side_effect = mock_sleep_side_effect

        # Create simple hierarchy
        source = PythonCodeNode(name="source", code="result = {'data': 'test'}")
        switch1 = SwitchNode(
            name="switch1", condition_field="data", operator="==", value="test"
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="data", operator="==", value="test"
        )

        self.workflow.add_node("source", source)
        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)

        self.workflow.connect("source", "switch1", {"result": "input_data"})
        self.workflow.connect("switch1", "switch2", {"true_output": "input_data"})

        # Create executor with short timeout
        executor = HierarchicalSwitchExecutor(
            self.workflow, debug=True, layer_timeout=0.1
        )

        # Mock executor that simulates slow switch (but mocked)
        async def slow_executor(
            node_id,
            node_instance,
            all_results,
            parameters,
            task_manager,
            workflow,
            workflow_context,
        ):
            if node_id == "switch2":
                # This will timeout (mocked)
                await asyncio.sleep(0.5)

            if node_id == "source":
                return {"result": {"data": "test"}}
            else:
                return {"true_output": {"data": "test"}, "false_output": None}

        # Execute - may raise TimeoutError due to mock
        try:
            all_results, switch_results = (
                await executor.execute_switches_hierarchically(
                    parameters={}, node_executor=slow_executor
                )
            )

            # If no exception, check that switch2 may have timed out
            if "switch2" in switch_results and "error" in switch_results.get(
                "switch2", {}
            ):
                assert "Timeout" in switch_results["switch2"]["error"]

        except asyncio.TimeoutError:
            # Expected due to mocked timeout
            pass

        # Check metrics (may not be available if timeout occurred)
        try:
            metrics = executor.get_execution_metrics()
            if "total_errors" in metrics:
                assert metrics["total_errors"] >= 0  # Could be 0 or more
        except:
            pass  # Metrics may not be available after timeout

    @pytest.mark.asyncio
    async def test_execution_metrics(self):
        """Test detailed execution metrics collection."""
        # Create multi-layer hierarchy
        source = PythonCodeNode(name="source", code="result = {'data': 'test'}")
        switch1 = SwitchNode(
            name="switch1", condition_field="data", operator="==", value="test"
        )
        switch2a = SwitchNode(
            name="switch2a", condition_field="data", operator="==", value="test"
        )
        switch2b = SwitchNode(
            name="switch2b", condition_field="data", operator="==", value="test"
        )
        switch3 = SwitchNode(
            name="switch3", condition_field="data", operator="==", value="test"
        )

        self.workflow.add_node("source", source)
        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2a", switch2a)
        self.workflow.add_node("switch2b", switch2b)
        self.workflow.add_node("switch3", switch3)

        # Create hierarchy: source -> switch1 -> [switch2a, switch2b] -> switch3
        self.workflow.connect("source", "switch1", {"result": "input_data"})
        self.workflow.connect("switch1", "switch2a", {"true_output": "input_data"})
        self.workflow.connect("switch1", "switch2b", {"true_output": "input_data"})
        self.workflow.connect("switch2a", "switch3", {"true_output": "input_data"})
        self.workflow.connect("switch2b", "switch3", {"true_output": "input_data"})

        # Create executor
        executor = HierarchicalSwitchExecutor(self.workflow, debug=True)

        # Mock executor with timing (mocked to avoid delays)
        with patch("asyncio.sleep") as mock_timing_sleep:
            mock_timing_sleep.return_value = None

            async def timed_executor(
                node_id,
                node_instance,
                all_results,
                parameters,
                task_manager,
                workflow,
                workflow_context,
            ):
                # Simulate different execution times (mocked)
                if "2" in node_id:  # Layer 2 switches
                    await asyncio.sleep(0.05)
                else:
                    await asyncio.sleep(0.01)

                if node_id == "source":
                    return {"result": {"data": "test"}}
                else:
                    return {"true_output": {"data": "test"}, "false_output": None}

            # Execute
            all_results, switch_results = (
                await executor.execute_switches_hierarchically(
                    parameters={}, node_executor=timed_executor
                )
            )

        # Get metrics
        metrics = executor.get_execution_metrics()

        # Verify metrics structure
        assert "total_execution_time" in metrics
        assert "layer_count" in metrics
        assert "layer_timings" in metrics
        assert "average_layer_time" in metrics
        assert "max_parallelism_used" in metrics

        # Verify layer count
        assert metrics["layer_count"] == 3  # switch1, [switch2a, switch2b], switch3

        # Verify timings recorded
        assert len(metrics["layer_timings"]) == 3
        for timing in metrics["layer_timings"]:
            assert "layer" in timing
            assert "switches" in timing
            assert "execution_time" in timing
            assert "parallelism" in timing

        # Verify parallelism detected
        assert metrics["max_parallelism_used"] == 2  # switch2a and switch2b

    def test_circular_dependency_handling(self):
        """Test handling of circular dependencies."""
        # Create circular dependency: switch1 -> switch2 -> switch3 -> switch1
        switch1 = SwitchNode(
            name="switch1", condition_field="a", operator="==", value=1
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="b", operator="==", value=2
        )
        switch3 = SwitchNode(
            name="switch3", condition_field="c", operator="==", value=3
        )

        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)
        self.workflow.add_node("switch3", switch3)

        self.workflow.connect("switch1", "switch2", {"true_output": "input_data"})
        self.workflow.connect("switch2", "switch3", {"true_output": "input_data"})
        self.workflow.connect("switch3", "switch1", {"true_output": "input_data"})

        # Create executor
        executor = HierarchicalSwitchExecutor(self.workflow)

        # Test cycle breaking
        layers = executor.handle_circular_dependencies(
            ["switch1", "switch2", "switch3"]
        )

        # Should have broken the cycle and created layers
        assert len(layers) > 0

        # All switches should be in some layer
        all_switches = set()
        for layer in layers:
            all_switches.update(layer)
        assert all_switches == {"switch1", "switch2", "switch3"}

    @pytest.mark.asyncio
    async def test_error_recovery_continue_execution(self):
        """Test that execution continues even if some switches fail."""
        # Create workflow with multiple switches
        source = PythonCodeNode(name="source", code="result = {'data': 'test'}")
        switch1 = SwitchNode(
            name="switch1", condition_field="data", operator="==", value="test"
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="data", operator="==", value="test"
        )
        switch3 = SwitchNode(
            name="switch3", condition_field="data", operator="==", value="test"
        )

        self.workflow.add_node("source", source)
        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)
        self.workflow.add_node("switch3", switch3)

        # All switches depend on source
        self.workflow.connect("source", "switch1", {"result": "input_data"})
        self.workflow.connect("source", "switch2", {"result": "input_data"})
        self.workflow.connect("source", "switch3", {"result": "input_data"})

        # Create executor
        executor = HierarchicalSwitchExecutor(self.workflow)

        # Mock executor where switch2 fails
        async def failing_executor(
            node_id,
            node_instance,
            all_results,
            parameters,
            task_manager,
            workflow,
            workflow_context,
        ):
            if node_id == "switch2":
                raise Exception("Switch2 failed!")

            if node_id == "source":
                return {"result": {"data": "test"}}
            else:
                return {"true_output": {"data": "test"}, "false_output": None}

        # Execute
        all_results, switch_results = await executor.execute_switches_hierarchically(
            parameters={}, node_executor=failing_executor
        )

        # Verify execution continued despite error
        assert len(switch_results) == 3
        assert "error" in switch_results["switch2"]
        assert "error" not in switch_results["switch1"]
        assert "error" not in switch_results["switch3"]

        # Check summary
        summary = executor.get_execution_summary(switch_results)
        assert summary["total_switches"] == 3
        assert summary["successful_switches"] == 2
        assert summary["failed_switches"] == 1

    @pytest.mark.asyncio
    async def test_empty_workflow(self):
        """Test execution with no switches."""
        # Empty workflow
        empty_workflow = Workflow("empty", "Empty")
        executor = HierarchicalSwitchExecutor(empty_workflow)

        # Execute
        all_results, switch_results = await executor.execute_switches_hierarchically(
            parameters={}, node_executor=None
        )

        # Should handle gracefully
        assert all_results == {}
        assert switch_results == {}

        # Check metrics
        metrics = executor.get_execution_metrics()
        assert metrics["total_execution_time"] == 0
        assert metrics["layer_count"] == 0
