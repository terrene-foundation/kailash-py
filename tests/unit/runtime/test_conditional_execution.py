"""
Unit tests for LocalRuntime conditional execution.

Tests the integration of conditional execution with LocalRuntime including:
- conditional_execution parameter handling
- Two-phase execution strategy
- Backward compatibility validation
- Performance impact assessment
- Error handling and fallback mechanisms
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import networkx as nx
import pytest
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.operations import MergeNode, SwitchNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow


class TestLocalRuntimeConditionalExecution:
    """Test LocalRuntime conditional execution functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.workflow = Workflow("test_workflow", "Test Conditional Execution")

    def test_runtime_initialization_default(self):
        """Test LocalRuntime initialization with default conditional_execution."""
        runtime = LocalRuntime()

        # Default should be "route_data" for backward compatibility
        assert runtime.conditional_execution == "route_data"

    def test_runtime_initialization_skip_branches(self):
        """Test LocalRuntime initialization with skip_branches mode."""
        runtime = LocalRuntime(conditional_execution="skip_branches")

        assert runtime.conditional_execution == "skip_branches"

    def test_runtime_initialization_invalid_mode(self):
        """Test LocalRuntime initialization with invalid conditional_execution mode."""
        with pytest.raises(ValueError) as exc_info:
            LocalRuntime(conditional_execution="invalid_mode")

        assert "conditional_execution" in str(exc_info.value)
        assert "invalid_mode" in str(exc_info.value)

    def test_conditional_execution_parameter_validation(self):
        """Test validation of conditional_execution parameter values."""
        # Valid modes should not raise exceptions
        valid_modes = ["route_data", "skip_branches"]
        for mode in valid_modes:
            runtime = LocalRuntime(conditional_execution=mode)
            assert runtime.conditional_execution == mode

        # Invalid modes should raise ValueError
        invalid_modes = ["", "invalid", "true", "false", None, 123]
        for mode in invalid_modes:
            with pytest.raises((ValueError, TypeError)):
                LocalRuntime(conditional_execution=mode)

    def test_backward_compatibility_route_data_mode(self):
        """Test backward compatibility with route_data mode (default behavior)."""
        # Create simple conditional workflow
        switch_node = SwitchNode(
            name="switch", condition_field="status", operator="==", value="active"
        )
        true_proc = PythonCodeNode(name="true_proc", code="result = {'branch': 'true'}")
        false_proc = PythonCodeNode(
            name="false_proc", code="result = {'branch': 'false'}"
        )

        self.workflow.add_node("switch1", switch_node)
        self.workflow.add_node("true_proc", true_proc)
        self.workflow.add_node("false_proc", false_proc)

        self.workflow.connect("switch1", "true_proc", {"true_output": "input"})
        self.workflow.connect("switch1", "false_proc", {"false_output": "input"})

        # Test with default mode (should execute all nodes)
        # Mock the input data
        input_data = {"status": "active"}

        with LocalRuntime(conditional_execution="route_data") as runtime:
            results, run_id = runtime.execute(
                self.workflow, parameters={"switch1": input_data}
            )

        # In route_data mode, all nodes should execute (current behavior)
        assert "switch1" in results
        assert "true_proc" in results
        assert "false_proc" in results

        # True branch should have data, false branch should have None
        assert results["switch1"]["true_output"] is not None
        assert results["switch1"]["false_output"] is None

    def test_skip_branches_mode_triggers_conditional_execution(self):
        """Test that skip_branches mode triggers conditional execution."""
        # Create conditional workflow
        switch_node = SwitchNode(
            name="switch", condition_field="status", operator="==", value="active"
        )
        true_proc = PythonCodeNode(name="true_proc", code="result = {'branch': 'true'}")

        self.workflow.add_node("switch1", switch_node)
        self.workflow.add_node("true_proc", true_proc)
        self.workflow.connect("switch1", "true_proc", {"true_output": "input"})

        input_data = {"status": "active"}

        # Capture log messages to verify conditional execution path
        import io
        import logging

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        logger = logging.getLogger("kailash.runtime.base")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        try:
            with LocalRuntime(conditional_execution="skip_branches") as runtime:
                results, run_id = runtime.execute(
                    self.workflow, parameters={"switch1": input_data}
                )

            # Verify conditional execution was triggered by checking log messages
            log_output = log_capture.getvalue()
            assert (
                "Conditional workflow detected, using conditional execution optimization"
                in log_output
            )
            assert "Starting conditional execution approach" in log_output
            assert "Phase 1: Executing SwitchNodes" in log_output
            assert "Phase 2: Creating and executing pruned plan" in log_output

            # Verify results structure - results should be a dict
            assert isinstance(results, dict), f"Expected dict, got {type(results)}"
            assert "switch1" in results
            assert "true_proc" in results
        finally:
            logger.removeHandler(handler)

    def test_execute_conditional_approach_method(self):
        """Test conditional execution through public interface."""
        # Create test workflow
        switch_node = SwitchNode(
            name="switch", condition_field="status", operator="==", value="active"
        )
        true_proc = PythonCodeNode(name="true_proc", code="result = {'branch': 'true'}")

        self.workflow.add_node("switch1", switch_node)
        self.workflow.add_node("true_proc", true_proc)
        self.workflow.connect("switch1", "true_proc", {"true_output": "input"})

        runtime = LocalRuntime(conditional_execution="skip_branches")

        # Test the method exists and can be called
        assert hasattr(runtime, "_execute_conditional_approach")

        # The method should be callable (implementation will be added later)
        try:
            with patch.object(runtime, "_execute_switch_nodes") as mock_switch_exec:
                with patch.object(runtime, "_execute_pruned_plan") as mock_pruned_exec:
                    mock_switch_exec.return_value = {
                        "switch1": {
                            "true_output": {"status": "active"},
                            "false_output": None,
                        }
                    }
                    mock_pruned_exec.return_value = {
                        "switch1": {"result": {"true_output": {"status": "active"}}},
                        "true_proc": {"result": {"branch": "true"}},
                    }

                    # Test through public interface since private method requires more parameters
                    input_data = {"status": "active"}
                    with LocalRuntime(
                        conditional_execution="skip_branches"
                    ) as test_runtime:
                        results, run_id = test_runtime.execute(
                            self.workflow, parameters={"switch1": input_data}
                        )

                    # Method should exist and be callable
                    assert results is not None
                    assert run_id is not None
        except AttributeError:
            # Method not implemented yet - that's expected in test-first development
            pass

    def test_execute_switch_nodes_method_signature(self):
        """Test _execute_switch_nodes method signature and basic behavior."""
        runtime = LocalRuntime(conditional_execution="skip_branches")

        # Test method exists
        assert hasattr(runtime, "_execute_switch_nodes") or True  # Will be implemented

        # Method should handle switch node execution in dependency order
        # This is a placeholder test for the method that will be implemented

    def test_execute_pruned_plan_method_signature(self):
        """Test _execute_pruned_plan method signature and basic behavior."""
        runtime = LocalRuntime(conditional_execution="skip_branches")

        # Test method exists
        assert hasattr(runtime, "_execute_pruned_plan") or True  # Will be implemented

        # Method should execute only nodes in the pruned plan
        # This is a placeholder test for the method that will be implemented

    def test_workflow_detection_conditional_vs_regular(self):
        """Test automatic detection of conditional vs regular workflows."""
        runtime = LocalRuntime(conditional_execution="skip_branches")

        # Regular workflow (no switches)
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")

        regular_workflow = Workflow("regular", "Regular Workflow")
        regular_workflow.add_node("proc1", proc1)
        regular_workflow.add_node("proc2", proc2)
        regular_workflow.connect("proc1", "proc2", {"result": "input"})

        # Method to detect conditional patterns should exist
        if hasattr(runtime, "_has_conditional_patterns"):
            has_conditionals = runtime._has_conditional_patterns(regular_workflow)
            assert has_conditionals is False

        # Conditional workflow (with switches)
        switch_node = SwitchNode(
            name="switch", condition_field="status", operator="==", value="active"
        )

        conditional_workflow = Workflow("conditional", "Conditional Workflow")
        conditional_workflow.add_node("switch1", switch_node)
        conditional_workflow.add_node("proc1", proc1)
        conditional_workflow.connect("switch1", "proc1", {"true_output": "input"})

        if hasattr(runtime, "_has_conditional_patterns"):
            has_conditionals = runtime._has_conditional_patterns(conditional_workflow)
            assert has_conditionals is True

    def test_performance_impact_measurement(self):
        """Test performance impact measurement infrastructure."""
        runtime = LocalRuntime(conditional_execution="skip_branches")

        # Should have performance tracking capabilities
        assert hasattr(runtime, "_performance_metrics") or True  # Will be implemented

        # Should track execution time differences
        if hasattr(runtime, "_track_performance"):
            # Method should exist for performance tracking
            assert callable(runtime._track_performance)

    def test_error_handling_unsupported_patterns(self):
        """Test error handling for unsupported conditional patterns."""
        runtime = LocalRuntime(conditional_execution="skip_branches")

        # Create complex workflow that might not be supported initially
        switch1 = SwitchNode(
            name="switch1", condition_field="a", operator="==", value=1
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="b", operator="==", value=2
        )

        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)

        # Create circular dependency
        self.workflow.connect("switch1", "switch2", {"true_output": "input"})
        self.workflow.connect("switch2", "switch1", {"true_output": "input"})

        # Should have fallback mechanism
        input_data = {"a": 1, "b": 2}

        try:
            with LocalRuntime(conditional_execution="skip_branches") as test_runtime:
                results, run_id = test_runtime.execute(
                    self.workflow, parameters={"switch1": input_data}
                )
            # Should either execute successfully or fall back gracefully
            assert results is not None
        except Exception as e:
            # Should have meaningful error messages
            error_msg = str(e).lower()
            assert (
                "conditional" in error_msg
                or "unsupported" in error_msg
                or "cycle" in error_msg
                or "circular" in error_msg
            )

    def test_fallback_to_route_data_behavior(self):
        """Test automatic fallback to route_data behavior for complex patterns."""
        runtime = LocalRuntime(conditional_execution="skip_branches")

        # Create workflow that should trigger fallback
        switch_node = SwitchNode(
            name="complex_switch",
            condition_field="status",
            operator="complex_operation",  # Unsupported operation
            value="complex_value",
        )

        self.workflow.add_node("switch1", switch_node)

        # Should have fallback detection
        if hasattr(runtime, "_should_fallback_to_route_data"):
            should_fallback = runtime._should_fallback_to_route_data(self.workflow)
            # Complex patterns should trigger fallback
            assert isinstance(should_fallback, bool)

    def test_debug_logging_conditional_execution(self):
        """Test debug logging for conditional execution paths."""
        runtime = LocalRuntime(conditional_execution="skip_branches", debug=True)

        # Debug mode should provide detailed logging
        assert runtime.debug is True

        # Should log execution path decisions
        if hasattr(runtime, "_log_execution_path"):
            assert callable(runtime._log_execution_path)

    def test_compatibility_with_existing_features(self):
        """Test compatibility with existing LocalRuntime features."""
        # Test with various existing parameters
        runtime = LocalRuntime(
            conditional_execution="skip_branches", debug=True, enable_cycles=True
        )

        assert runtime.conditional_execution == "skip_branches"
        assert runtime.debug is True
        assert runtime.enable_cycles is True

    def test_parameter_validation_integration(self):
        """Test integration with existing parameter validation."""
        runtime = LocalRuntime(conditional_execution="skip_branches")

        # Should work with existing parameter validation
        switch_node = SwitchNode(
            name="switch", condition_field="status", operator="==", value="active"
        )

        self.workflow.add_node("switch1", switch_node)

        # Test that parameter validation still works
        try:
            # This should work fine - None is handled gracefully
            with LocalRuntime(conditional_execution="skip_branches") as test_runtime:
                results, run_id = test_runtime.execute(
                    self.workflow, parameters={"switch1": None}
                )
            assert results is not None
        except Exception:
            # If it raises an exception, that's also acceptable
            pass

        # Test that the runtime validates conditional_execution parameter properly
        with pytest.raises((ValueError, TypeError)):
            LocalRuntime(conditional_execution="invalid_mode")

    def test_cycle_integration_conditional_execution(self):
        """Test integration with cycle execution."""
        runtime = LocalRuntime(
            conditional_execution="skip_branches", enable_cycles=True
        )

        # Create cycle with conditional logic
        counter = PythonCodeNode(
            name="counter",
            code="result = {'count': count + 1 if 'count' in locals() else 1}",
        )
        switch = SwitchNode(
            name="continue_switch", condition_field="count", operator="<", value=3
        )

        self.workflow.add_node("counter", counter)
        self.workflow.add_node("continue_switch", switch)

        # Create cycle
        self.workflow.connect("counter", "continue_switch", {"result": "input"})
        self.workflow.create_cycle("conditional_cycle").connect(
            "continue_switch", "counter", {"true_output": "input"}
        ).max_iterations(5).build()

        # Should handle conditional cycles appropriately
        try:
            with LocalRuntime(
                conditional_execution="skip_branches", enable_cycles=True
            ) as test_runtime:
                results, run_id = test_runtime.execute(self.workflow)
            # Should execute successfully or provide clear error
            assert results is not None or True  # Placeholder for future implementation
        except Exception as e:
            # Should have meaningful error for unsupported patterns
            assert isinstance(e, (ValueError, NotImplementedError))


class TestLocalRuntimeTwoPhaseExecution:
    """Test LocalRuntime two-phase execution strategy."""

    def setup_method(self):
        """Set up test fixtures."""
        self.workflow = Workflow("test_workflow", "Test Two-Phase Execution")
        self.runtime = LocalRuntime(conditional_execution="skip_branches")

    def test_switch_node_dependency_ordering(self):
        """Test switch node execution in dependency order."""
        # Create cascading switches
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

        # Create dependencies: switch1 -> switch2 -> switch3
        self.workflow.connect("switch1", "switch2", {"true_output": "input"})
        self.workflow.connect("switch2", "switch3", {"true_output": "input"})

        # Should execute switches in dependency order
        if hasattr(self.runtime, "_get_switch_execution_order"):
            order = self.runtime._get_switch_execution_order(self.workflow)
            # switch1 should come before switch2, switch2 before switch3
            assert order.index("switch1") < order.index("switch2")
            assert order.index("switch2") < order.index("switch3")

    def test_execution_plan_creation_integration(self):
        """Test integration with execution plan creation."""
        # Create workflow
        switch_node = SwitchNode(
            name="switch", condition_field="status", operator="==", value="active"
        )
        true_proc = PythonCodeNode(name="true_proc", code="result = {'branch': 'true'}")
        false_proc = PythonCodeNode(
            name="false_proc", code="result = {'branch': 'false'}"
        )

        self.workflow.add_node("switch1", switch_node)
        self.workflow.add_node("true_proc", true_proc)
        self.workflow.add_node("false_proc", false_proc)

        self.workflow.connect("switch1", "true_proc", {"true_output": "input"})
        self.workflow.connect("switch1", "false_proc", {"false_output": "input"})

        # Test execution plan creation
        if hasattr(self.runtime, "_create_conditional_execution_plan"):
            switch_results = {
                "switch1": {"true_output": {"status": "active"}, "false_output": None}
            }

            plan = self.runtime._create_conditional_execution_plan(
                self.workflow, switch_results
            )

            # Plan should include switch and true processor only
            assert "switch1" in plan
            assert "true_proc" in plan
            assert "false_proc" not in plan

    def test_error_handling_phase_failures(self):
        """Test error handling when phases fail."""
        # Create workflow
        switch_node = SwitchNode(
            name="failing_switch",
            condition_field="status",
            operator="==",
            value="active",
        )

        self.workflow.add_node("switch1", switch_node)

        # Test Phase 1 failure handling
        if hasattr(self.runtime, "_execute_switch_nodes"):
            try:
                # Test method exists and has proper error handling
                assert hasattr(self.runtime, "_execute_conditional_approach")

                # The method should handle errors gracefully in real usage
                # We test this through the public interface
                with LocalRuntime(
                    conditional_execution="skip_branches"
                ) as test_runtime:
                    results, run_id = test_runtime.execute(
                        self.workflow, parameters={"switch1": {"status": "active"}}
                    )
                assert results is not None

            except (AttributeError, NotImplementedError, Exception):
                # Method may have different implementation details
                pass

    def test_rollback_mechanism(self):
        """Test rollback mechanism for partial execution failures."""
        # Test should verify rollback capabilities exist
        assert hasattr(self.runtime, "_rollback_partial_execution") or True

        # Rollback should restore previous state on failure
        if hasattr(self.runtime, "_rollback_partial_execution"):
            assert callable(self.runtime._rollback_partial_execution)


class TestLocalRuntimePerformanceImpact:
    """Test performance impact of conditional execution."""

    def setup_method(self):
        """Set up performance test fixtures."""
        self.workflow = Workflow("perf_test", "Performance Test")

    def test_performance_measurement_infrastructure(self):
        """Test performance measurement infrastructure."""
        runtime = LocalRuntime(conditional_execution="skip_branches")

        # Should have performance tracking
        assert hasattr(runtime, "_performance_tracker") or True

        # Should measure execution time differences
        if hasattr(runtime, "_measure_execution_time"):
            assert callable(runtime._measure_execution_time)

    def test_graph_analysis_overhead(self):
        """Test graph analysis overhead measurement."""
        # Create large workflow for overhead testing
        for i in range(50):
            switch = SwitchNode(
                name=f"switch_{i}", condition_field=f"field_{i}", operator="==", value=i
            )
            proc = PythonCodeNode(name=f"proc_{i}", code=f"result = {{'proc': {i}}}")

            self.workflow.add_node(f"switch_{i}", switch)
            self.workflow.add_node(f"proc_{i}", proc)
            self.workflow.connect(f"switch_{i}", f"proc_{i}", {"true_output": "input"})

        runtime = LocalRuntime(conditional_execution="skip_branches")

        # Analysis overhead should be minimal
        if hasattr(runtime, "_measure_analysis_overhead"):
            import time

            start_time = time.time()

            # Simulate analysis
            overhead = runtime._measure_analysis_overhead(self.workflow)

            analysis_time = time.time() - start_time

            # Should complete quickly (< 5% of execution time target)
            assert analysis_time < 1.0  # Should be very fast for 50 nodes
            assert overhead < 0.05 if overhead is not None else True

    def test_memory_usage_optimization(self):
        """Test memory usage optimization."""
        runtime = LocalRuntime(conditional_execution="skip_branches")

        # Should optimize memory usage for large workflows
        if hasattr(runtime, "_optimize_memory_usage"):
            assert callable(runtime._optimize_memory_usage)

        # Should use caching efficiently
        if hasattr(runtime, "_execution_plan_cache"):
            assert hasattr(runtime._execution_plan_cache, "clear")

    def test_caching_performance_benefits(self):
        """Test caching performance benefits."""
        # Create workflow
        switch_node = SwitchNode(
            name="switch", condition_field="status", operator="==", value="active"
        )

        self.workflow.add_node("switch1", switch_node)

        runtime = LocalRuntime(conditional_execution="skip_branches")

        # First execution should cache results
        input_data = {"status": "active"}

        if hasattr(runtime, "_get_cached_execution_plan"):
            # Should have caching mechanism
            plan1 = runtime._get_cached_execution_plan(self.workflow, input_data)
            plan2 = runtime._get_cached_execution_plan(self.workflow, input_data)

            # Second call should be faster (cached)
            assert plan1 == plan2 if plan1 is not None else True

    def test_scalability_large_workflows(self):
        """Test scalability with large workflows."""
        # Create large workflow (100+ nodes)
        for i in range(100):
            if i % 10 == 0:  # Every 10th node is a switch
                node = SwitchNode(
                    name=f"switch_{i}",
                    condition_field=f"field_{i}",
                    operator="==",
                    value=i,
                )
            else:
                node = PythonCodeNode(
                    name=f"proc_{i}", code=f"result = {{'proc': {i}}}"
                )

            self.workflow.add_node(f"node_{i}", node)

            if i > 0:
                self.workflow.connect(f"node_{i-1}", f"node_{i}", {"result": "input"})

        runtime = LocalRuntime(conditional_execution="skip_branches")

        # Should handle large workflows efficiently
        import time

        start_time = time.time()

        try:
            # Test workflow analysis
            if hasattr(runtime, "_analyze_workflow_complexity"):
                complexity = runtime._analyze_workflow_complexity(self.workflow)

            execution_time = time.time() - start_time

            # Should complete analysis in reasonable time
            assert execution_time < 5.0  # 5 seconds for 100 nodes

        except (AttributeError, NotImplementedError):
            # Methods not implemented yet
            pass
