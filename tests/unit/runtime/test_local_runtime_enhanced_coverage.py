"""
Enhanced tests for LocalRuntime to achieve 80%+ coverage.

These tests target advanced methods, error handling, and edge cases that are likely
under-covered in the existing test suite.
"""

import asyncio
import hashlib
import json
import threading
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from kailash.nodes.base_async import AsyncNode
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.operations import MergeNode, SwitchNode
from kailash.runtime.local import (
    LocalRuntime,
    _get_conditional_analyzer,
    _get_execution_planner,
)
from kailash.runtime.secret_provider import EnvironmentSecretProvider
from kailash.runtime.validation.connection_context import ConnectionContext
from kailash.runtime.validation.enhanced_error_formatter import EnhancedErrorFormatter
from kailash.runtime.validation.error_categorizer import ErrorCategorizer
from kailash.runtime.validation.suggestion_engine import ValidationSuggestionEngine
from kailash.sdk_exceptions import (
    NodeExecutionError,
    RuntimeExecutionError,
    WorkflowValidationError,
)
from kailash.tracking import TaskManager, TaskStatus
from kailash.tracking.metrics_collector import MetricsCollector
from kailash.workflow.contracts import ConnectionContract, ContractValidator
from kailash.workflow.graph import Workflow


class TestLocalRuntimeInitialization:
    """Test LocalRuntime initialization and configuration."""

    def test_init_with_default_values(self):
        """Test LocalRuntime initialization with default values."""
        runtime = LocalRuntime()

        assert runtime.debug is False
        assert runtime.enable_cycles is True
        assert runtime.enable_async is True
        assert runtime.max_concurrency == 10
        assert runtime.user_context is None
        assert runtime.enable_monitoring is True
        assert runtime.enable_security is False
        assert runtime.enable_audit is False
        assert runtime.resource_limits == {}
        assert runtime.connection_validation == "warn"
        assert runtime.conditional_execution == "route_data"

    def test_init_with_custom_values(self):
        """Test LocalRuntime initialization with custom values."""
        user_context = {"user_id": "test123", "roles": ["admin"]}
        resource_limits = {"memory_mb": 1024, "cpu_cores": 2}
        secret_provider = EnvironmentSecretProvider()

        runtime = LocalRuntime(
            debug=True,
            enable_cycles=False,
            enable_async=False,
            max_concurrency=20,
            user_context=user_context,
            enable_monitoring=False,
            enable_security=True,
            enable_audit=True,
            resource_limits=resource_limits,
            secret_provider=secret_provider,
            connection_validation="strict",
            conditional_execution="skip_branches"
        )

        assert runtime.debug is True
        assert runtime.enable_cycles is False
        assert runtime.enable_async is False
        assert runtime.max_concurrency == 20
        assert runtime.user_context == user_context
        assert runtime.enable_monitoring is False
        assert runtime.enable_security is True
        assert runtime.enable_audit is True
        assert runtime.resource_limits == resource_limits
        assert runtime.secret_provider == secret_provider
        assert runtime.connection_validation == "strict"
        assert runtime.conditional_execution == "skip_branches"

    def test_init_invalid_connection_validation(self):
        """Test initialization with invalid connection_validation mode."""
        with pytest.raises(ValueError, match="Invalid connection_validation mode"):
            LocalRuntime(connection_validation="invalid")

    def test_init_invalid_conditional_execution(self):
        """Test initialization with invalid conditional_execution mode."""
        with pytest.raises(ValueError, match="Invalid conditional_execution mode"):
            LocalRuntime(conditional_execution="invalid")

    def test_lazy_loading_conditional_components(self):
        """Test lazy loading of conditional execution components."""
        runtime = LocalRuntime()

        # Components should be None initially
        assert runtime._conditional_branch_analyzer is None
        assert runtime._dynamic_execution_planner is None

        # Lazy loaders should work
        analyzer_class = _get_conditional_analyzer()
        planner_class = _get_execution_planner()

        assert analyzer_class is not None
        assert planner_class is not None

        # Multiple calls should return same class
        assert _get_conditional_analyzer() is analyzer_class
        assert _get_execution_planner() is planner_class


class TestSecretAndParameterHandling:
    """Test secret extraction and parameter handling."""

    def test_extract_secret_requirements_no_secrets(self):
        """Test _extract_secret_requirements with no secrets."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        # Add node without secret requirements
        node = PythonCodeNode(name="node", code="result = {'data': 1}")
        workflow.add_node("node", node)

        requirements = runtime._extract_secret_requirements(workflow)
        assert requirements == []

    def test_extract_secret_requirements_with_secrets(self):
        """Test _extract_secret_requirements with nodes having secrets."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        # Mock node with secret requirements
        node = Mock()
        node.get_secret_requirements.return_value = ["API_KEY", "DB_PASSWORD"]
        workflow.add_node("secret_node", node)

        requirements = runtime._extract_secret_requirements(workflow)
        assert requirements == ["API_KEY", "DB_PASSWORD"]

    def test_extract_secret_requirements_multiple_nodes(self):
        """Test _extract_secret_requirements with multiple nodes having secrets."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        # Mock nodes with different secret requirements
        node1 = Mock()
        node1.get_secret_requirements.return_value = ["API_KEY"]

        node2 = Mock()
        node2.get_secret_requirements.return_value = ["DB_PASSWORD", "OAUTH_TOKEN"]

        workflow.add_node("node1", node1)
        workflow.add_node("node2", node2)

        requirements = runtime._extract_secret_requirements(workflow)
        assert set(requirements) == {"API_KEY", "DB_PASSWORD", "OAUTH_TOKEN"}

    def test_process_workflow_parameters_none(self):
        """Test _process_workflow_parameters with None parameters."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        result = runtime._process_workflow_parameters(workflow, None)
        assert result == {}

    def test_process_workflow_parameters_empty_dict(self):
        """Test _process_workflow_parameters with empty dict."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        result = runtime._process_workflow_parameters(workflow, {})
        assert result == {}

    def test_separate_parameter_formats(self):
        """Test _separate_parameter_formats method."""
        runtime = LocalRuntime()

        # Test with mixed formats
        parameters = {
            "node1": {"param1": "value1"},  # Node-specific
            "global_param": "global_value",  # Global
            "node2": {"param2": "value2"}   # Node-specific
        }

        node_specific, global_params = runtime._separate_parameter_formats(parameters)

        assert node_specific == {
            "node1": {"param1": "value1"},
            "node2": {"param2": "value2"}
        }
        assert global_params == {"global_param": "global_value"}

    def test_is_node_specific_format(self):
        """Test _is_node_specific_format method."""
        runtime = LocalRuntime()

        # Test node-specific format
        assert runtime._is_node_specific_format({"param": "value"}) is True
        assert runtime._is_node_specific_format({"param1": 1, "param2": 2}) is True

        # Test non-dict values
        assert runtime._is_node_specific_format("string_value") is False
        assert runtime._is_node_specific_format(123) is False
        assert runtime._is_node_specific_format([1, 2, 3]) is False
        assert runtime._is_node_specific_format(None) is False


class TestWorkflowValidation:
    """Test workflow validation methods."""

    def test_validate_workflow_empty(self):
        """Test validate_workflow with empty workflow."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        errors = runtime.validate_workflow(workflow)
        # Empty workflow might be valid or have specific errors
        assert isinstance(errors, list)

    def test_validate_workflow_with_nodes(self):
        """Test validate_workflow with valid workflow."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        # Add valid nodes
        node1 = PythonCodeNode(name="node1", code="result = {'data': 1}")
        node2 = PythonCodeNode(name="node2", code="result = {'data': 2}")

        workflow.add_node("node1", node1)
        workflow.add_node("node2", node2)
        workflow.connect("node1", "node2", {"result": "input"})

        errors = runtime.validate_workflow(workflow)
        assert isinstance(errors, list)

    def test_workflow_has_cycles(self):
        """Test _workflow_has_cycles method."""
        runtime = LocalRuntime()

        # Test workflow without cycles
        workflow = Workflow("test", "Test")
        assert runtime._workflow_has_cycles(workflow) is False

        # Test workflow with has_cycles method returning True
        workflow_with_cycles = Mock()
        workflow_with_cycles.has_cycles.return_value = True
        assert runtime._workflow_has_cycles(workflow_with_cycles) is True

        # Test workflow without has_cycles method
        workflow_no_method = Mock()
        del workflow_no_method.has_cycles
        assert runtime._workflow_has_cycles(workflow_no_method) is False

    def test_should_stop_on_error(self):
        """Test _should_stop_on_error method."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        # Test basic behavior
        assert runtime._should_stop_on_error(workflow, "node1") is True

        # Test with workflow having stop_on_error attribute
        workflow_with_attr = Mock()
        workflow_with_attr.stop_on_error = False
        assert runtime._should_stop_on_error(workflow_with_attr, "node1") is False


class TestExecutionMethods:
    """Test execution methods and async/sync handling."""

    def test_execute_no_workflow(self):
        """Test execute with no workflow."""
        runtime = LocalRuntime()

        with pytest.raises(RuntimeExecutionError, match="No workflow provided"):
            runtime.execute(None)

    def test_execute_sync_from_event_loop(self):
        """Test execute sync when called from within event loop."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        # Add a simple node
        node = PythonCodeNode(name="node", code="result = {'data': 1}")
        workflow.add_node("node", node)

        # Mock being in an event loop
        with patch('asyncio.get_running_loop', return_value=Mock()):
            with patch.object(runtime, '_execute_sync') as mock_sync:
                mock_sync.return_value = ({"node": {"result": {"data": 1}}}, "test-id")

                results, run_id = runtime.execute(workflow)

                mock_sync.assert_called_once()
                assert results == {"node": {"result": {"data": 1}}}
                assert run_id == "test-id"

    def test_execute_async_no_event_loop(self):
        """Test execute async when no event loop is running."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        # Add a simple node
        node = PythonCodeNode(name="node", code="result = {'data': 1}")
        workflow.add_node("node", node)

        # Execute normally (no event loop)
        results, run_id = runtime.execute(workflow)

        assert "node" in results
        assert results["node"]["result"]["data"] == 1

    @pytest.mark.asyncio
    async def test_execute_async_direct(self):
        """Test execute_async method directly."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        # Add a simple node
        node = PythonCodeNode(name="node", code="result = {'data': 42}")
        workflow.add_node("node", node)

        results, run_id = await runtime.execute_async(workflow)

        assert "node" in results
        assert results["node"]["result"]["data"] == 42

    def test_execute_sync_thread_handling(self):
        """Test _execute_sync thread handling."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        # Add a node
        node = PythonCodeNode(name="node", code="result = {'value': 123}")
        workflow.add_node("node", node)

        # Test direct sync execution
        results, run_id = runtime._execute_sync(workflow)

        assert "node" in results
        assert results["node"]["result"]["value"] == 123

    def test_execute_sync_thread_exception(self):
        """Test _execute_sync with exception in thread."""
        runtime = LocalRuntime()

        # Mock workflow that will cause an exception
        workflow = Mock()
        workflow.__bool__.return_value = True  # Make it truthy

        # Patch _execute_async to raise exception
        with patch.object(runtime, '_execute_async', side_effect=RuntimeError("Test error")):
            with pytest.raises(RuntimeError, match="Test error"):
                runtime._execute_sync(workflow)


class TestConditionalExecution:
    """Test conditional execution features."""

    def test_has_conditional_patterns_no_switches(self):
        """Test _has_conditional_patterns with no switches."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        # Add non-switch nodes
        node = PythonCodeNode(name="node", code="result = {'data': 1}")
        workflow.add_node("node", node)

        assert runtime._has_conditional_patterns(workflow) is False

    def test_has_conditional_patterns_with_switches(self):
        """Test _has_conditional_patterns with switches."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        # Add switch node
        switch = SwitchNode(name="switch", condition_field="status", operator="==", value="active")
        workflow.add_node("switch", switch)

        # Mock the analyzer
        mock_analyzer = Mock()
        mock_analyzer._find_switch_nodes.return_value = ["switch"]
        runtime._conditional_branch_analyzer = mock_analyzer

        assert runtime._has_conditional_patterns(workflow) is True

    def test_validate_conditional_execution_prerequisites(self):
        """Test _validate_conditional_execution_prerequisites method."""
        runtime = LocalRuntime(conditional_execution="skip_branches")
        workflow = Workflow("test", "Test")

        # Test with cycles
        mock_workflow = Mock()
        mock_workflow.has_cycles.return_value = True
        assert runtime._validate_conditional_execution_prerequisites(mock_workflow) is False

        # Test without cycles
        mock_workflow.has_cycles.return_value = False
        assert runtime._validate_conditional_execution_prerequisites(mock_workflow) is True

    def test_validate_switch_results_valid(self):
        """Test _validate_switch_results with valid results."""
        runtime = LocalRuntime()

        switch_results = {
            "switch1": {"true_output": {"data": 1}, "false_output": None},
            "switch2": {"true_output": None, "false_output": {"data": 2}}
        }

        assert runtime._validate_switch_results(switch_results) is True

    def test_validate_switch_results_invalid(self):
        """Test _validate_switch_results with invalid results."""
        runtime = LocalRuntime()

        # Empty results
        assert runtime._validate_switch_results({}) is False

        # None results
        assert runtime._validate_switch_results(None) is False

        # Invalid format
        assert runtime._validate_switch_results({"switch": "invalid"}) is False

    def test_validate_conditional_execution_results(self):
        """Test _validate_conditional_execution_results method."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        # Add nodes
        node1 = PythonCodeNode(name="node1", code="result = {'data': 1}")
        node2 = PythonCodeNode(name="node2", code="result = {'data': 2}")
        workflow.add_node("node1", node1)
        workflow.add_node("node2", node2)

        # Test with valid results
        results = {
            "node1": {"result": {"data": 1}},
            "node2": {"result": {"data": 2}}
        }

        assert runtime._validate_conditional_execution_results(results, workflow) is True

        # Test with missing nodes
        partial_results = {"node1": {"result": {"data": 1}}}
        assert runtime._validate_conditional_execution_results(partial_results, workflow) is True

    def test_should_skip_conditional_node(self):
        """Test _should_skip_conditional_node method."""
        runtime = LocalRuntime(conditional_execution="skip_branches")

        # Test with route_data mode
        runtime.conditional_execution = "route_data"
        assert runtime._should_skip_conditional_node("node1", {"node1", "node2"}) is False

        # Test with skip_branches mode - node in pruned plan
        runtime.conditional_execution = "skip_branches"
        assert runtime._should_skip_conditional_node("node1", {"node1", "node2"}) is False

        # Test with skip_branches mode - node not in pruned plan
        assert runtime._should_skip_conditional_node("node3", {"node1", "node2"}) is True


class TestPerformanceAndAnalytics:
    """Test performance tracking and analytics methods."""

    def test_track_conditional_execution_performance(self):
        """Test _track_conditional_execution_performance method."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        # Add multiple nodes
        for i in range(5):
            node = PythonCodeNode(name=f"node{i}", code=f"result = {{'data': {i}}}")
            workflow.add_node(f"node{i}", node)

        results = {f"node{i}": {"result": {"data": i}} for i in range(3)}

        # Track performance
        runtime._track_conditional_execution_performance(results, workflow)

        # Check analytics data was updated
        assert len(runtime._analytics_data["conditional_executions"]) > 0

        # Verify performance data
        perf_data = runtime._analytics_data["conditional_executions"][-1]
        assert perf_data["total_nodes"] == 5
        assert perf_data["executed_nodes"] == 3
        assert perf_data["performance_improvement"] == 0.4  # (5-3)/5

    def test_log_conditional_execution_failure(self):
        """Test _log_conditional_execution_failure method."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        error = RuntimeError("Test failure")
        nodes_completed = 3

        # Should not raise exception
        runtime._log_conditional_execution_failure(error, workflow, nodes_completed)

    def test_track_fallback_usage(self):
        """Test _track_fallback_usage method."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")
        workflow.name = "test_workflow"

        runtime._track_fallback_usage(workflow, "Test error", "Missing prerequisites")

        # Check fallback metrics
        assert "test_workflow" in runtime._fallback_metrics
        assert runtime._fallback_metrics["test_workflow"]["count"] == 1
        assert runtime._fallback_metrics["test_workflow"]["reasons"]["Missing prerequisites"] == 1

    def test_get_execution_plan_cached(self):
        """Test get_execution_plan_cached method."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        switch_results = {"switch1": {"true_output": {"data": 1}}}

        # Mock the planner
        mock_planner = Mock()
        mock_planner.create_execution_plan.return_value = ["node1", "node2"]
        runtime._dynamic_execution_planner = mock_planner

        # First call should create plan
        plan1 = runtime.get_execution_plan_cached(workflow, switch_results)
        assert plan1 == ["node1", "node2"]
        assert runtime._analytics_data["cache_misses"] == 1

        # Second call should use cache
        plan2 = runtime.get_execution_plan_cached(workflow, switch_results)
        assert plan2 == ["node1", "node2"]
        assert runtime._analytics_data["cache_hits"] == 1

    def test_create_execution_plan_cache_key(self):
        """Test _create_execution_plan_cache_key method."""
        runtime = LocalRuntime()

        workflow = Mock()
        workflow.name = "test_workflow"
        workflow.version = "1.0"

        switch_results = {
            "switch1": {"true_output": {"data": 1}, "false_output": None},
            "switch2": {"true_output": None, "false_output": {"data": 2}}
        }

        key = runtime._create_execution_plan_cache_key(workflow, switch_results)

        assert isinstance(key, str)
        assert len(key) > 0

        # Same inputs should produce same key
        key2 = runtime._create_execution_plan_cache_key(workflow, switch_results)
        assert key == key2

    def test_get_execution_analytics(self):
        """Test get_execution_analytics method."""
        runtime = LocalRuntime()

        # Add some analytics data
        runtime._analytics_data["cache_hits"] = 5
        runtime._analytics_data["cache_misses"] = 3
        runtime._analytics_data["conditional_executions"] = [
            {"performance_improvement": 0.3},
            {"performance_improvement": 0.5}
        ]

        analytics = runtime.get_execution_analytics()

        assert analytics["cache_performance"]["hit_rate"] == 0.625  # 5/(5+3)
        assert analytics["conditional_execution_stats"]["average_performance_improvement"] == 0.4

    def test_record_execution_performance(self):
        """Test record_execution_performance method."""
        runtime = LocalRuntime()
        workflow = Mock()
        workflow.name = "test_workflow"

        runtime.record_execution_performance(
            workflow=workflow,
            execution_time=1.5,
            nodes_executed=10,
            used_conditional=True,
            performance_improvement=0.25
        )

        # Check performance history
        assert len(runtime._analytics_data["performance_history"]) == 1
        perf = runtime._analytics_data["performance_history"][0]
        assert perf["workflow_name"] == "test_workflow"
        assert perf["execution_time"] == 1.5
        assert perf["nodes_executed"] == 10
        assert perf["used_conditional"] is True
        assert perf["performance_improvement"] == 0.25

    def test_clear_analytics_data(self):
        """Test clear_analytics_data method."""
        runtime = LocalRuntime()

        # Add some data
        runtime._analytics_data["cache_hits"] = 10
        runtime._analytics_data["execution_patterns"]["pattern1"] = 5
        runtime._analytics_data["performance_history"] = [{"data": 1}]

        # Clear without keeping patterns
        runtime.clear_analytics_data(keep_patterns=False)

        assert runtime._analytics_data["cache_hits"] == 0
        assert runtime._analytics_data["cache_misses"] == 0
        assert len(runtime._analytics_data["performance_history"]) == 0
        assert len(runtime._analytics_data["execution_patterns"]) == 0

        # Add data again
        runtime._analytics_data["execution_patterns"]["pattern1"] = 5

        # Clear keeping patterns
        runtime.clear_analytics_data(keep_patterns=True)
        assert len(runtime._analytics_data["execution_patterns"]) == 1


class TestHealthAndOptimization:
    """Test health diagnostics and optimization methods."""

    def test_get_health_diagnostics(self):
        """Test get_health_diagnostics method."""
        runtime = LocalRuntime()

        # Add some data for diagnostics
        runtime._analytics_data["cache_hits"] = 8
        runtime._analytics_data["cache_misses"] = 2
        runtime._fallback_metrics["workflow1"] = {"count": 3}

        diagnostics = runtime.get_health_diagnostics()

        assert diagnostics["status"] in ["healthy", "degraded", "unhealthy"]
        assert "memory_usage_mb" in diagnostics
        assert "cpu_percent" in diagnostics
        assert diagnostics["cache_hit_rate"] == 0.8
        assert diagnostics["total_fallbacks"] == 3

    def test_optimize_runtime_performance(self):
        """Test optimize_runtime_performance method."""
        runtime = LocalRuntime()

        # Add performance data
        runtime._analytics_data["performance_history"] = [
            {"performance_improvement": 0.1},
            {"performance_improvement": 0.2},
            {"performance_improvement": 0.3}
        ]

        recommendations = runtime.optimize_runtime_performance()

        assert "recommendations" in recommendations
        assert "current_settings" in recommendations
        assert "optimization_potential" in recommendations

    def test_check_performance_switch(self):
        """Test _check_performance_switch method."""
        runtime = LocalRuntime()

        # Add performance history
        runtime._analytics_data["performance_history"] = [
            {"used_conditional": True, "performance_improvement": 0.1},
            {"used_conditional": True, "performance_improvement": 0.05},
            {"used_conditional": True, "performance_improvement": 0.03}
        ]

        should_switch, reason, new_mode = runtime._check_performance_switch("skip_branches")

        # Low performance improvement should suggest switching
        assert isinstance(should_switch, bool)
        assert isinstance(reason, str)
        assert new_mode in ["route_data", "skip_branches"]


class TestAuditAndSecurity:
    """Test audit and security methods."""

    def test_check_workflow_access_no_security(self):
        """Test _check_workflow_access with security disabled."""
        runtime = LocalRuntime(enable_security=False)
        workflow = Workflow("test", "Test")

        # Should not raise exception
        runtime._check_workflow_access(workflow)

    def test_check_workflow_access_with_security(self):
        """Test _check_workflow_access with security enabled."""
        runtime = LocalRuntime(enable_security=True)
        workflow = Workflow("test", "Test")

        # Without access control manager, should still work
        runtime._check_workflow_access(workflow)

    def test_log_audit_event_disabled(self):
        """Test _log_audit_event with audit disabled."""
        runtime = LocalRuntime(enable_audit=False)

        # Should not raise exception
        runtime._log_audit_event("test_event", {"data": "test"})

    def test_log_audit_event_enabled(self):
        """Test _log_audit_event with audit enabled."""
        runtime = LocalRuntime(enable_audit=True)

        # Should handle audit event
        runtime._log_audit_event("workflow_execution", {
            "workflow": "test",
            "status": "started"
        })

    @pytest.mark.asyncio
    async def test_log_audit_event_async(self):
        """Test _log_audit_event_async method."""
        runtime = LocalRuntime(enable_audit=True)

        # Should handle async audit event
        await runtime._log_audit_event_async("async_event", {
            "workflow": "test",
            "status": "completed"
        })

    def test_serialize_user_context(self):
        """Test _serialize_user_context method."""
        runtime = LocalRuntime()

        # Test with None context
        assert runtime._serialize_user_context() is None

        # Test with dict context
        runtime.user_context = {"user_id": "123", "roles": ["admin"]}
        serialized = runtime._serialize_user_context()
        assert serialized == {"user_id": "123", "roles": ["admin"]}

        # Test with object context
        mock_context = Mock()
        mock_context.to_dict.return_value = {"user_id": "456", "roles": ["user"]}
        runtime.user_context = mock_context
        serialized = runtime._serialize_user_context()
        assert serialized == {"user_id": "456", "roles": ["user"]}


class TestValidationAndErrorHandling:
    """Test validation and error handling methods."""

    def test_prepare_node_inputs(self):
        """Test _prepare_node_inputs method."""
        runtime = LocalRuntime()

        # Test with various input formats
        node_config = {"param1": "value1"}
        runtime_params = {"param2": "value2"}

        result = runtime._prepare_node_inputs(
            node_id="test_node",
            node_config=node_config,
            runtime_params=runtime_params,
            workflow_context={"context": "data"}
        )

        # Should merge parameters
        assert "param1" in result
        assert "param2" in result

    def test_generate_enhanced_validation_error(self):
        """Test _generate_enhanced_validation_error method."""
        runtime = LocalRuntime()

        error_details = {
            "missing_params": ["param1", "param2"],
            "validation_errors": ["Type mismatch"]
        }

        connection_context = ConnectionContext(
            source_node="node1",
            target_node="node2",
            mapping={"output": "input"}
        )

        error_msg = runtime._generate_enhanced_validation_error(
            error_details,
            connection_context
        )

        assert isinstance(error_msg, str)
        assert "param1" in error_msg
        assert "param2" in error_msg

    def test_build_connection_context(self):
        """Test _build_connection_context method."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        # Add nodes and connection
        node1 = PythonCodeNode(name="node1", code="result = {'data': 1}")
        node2 = PythonCodeNode(name="node2", code="result = {'data': 2}")
        workflow.add_node("node1", node1)
        workflow.add_node("node2", node2)
        workflow.connect("node1", "node2", {"result": "input"})

        context = runtime._build_connection_context(workflow, "node1", "node2")

        assert context is not None
        assert context.source_node == "node1"
        assert context.target_node == "node2"

    def test_validate_connection_contracts_off(self):
        """Test _validate_connection_contracts with validation off."""
        runtime = LocalRuntime(connection_validation="off")

        # Should always return True when off
        assert runtime._validate_connection_contracts({}, {}, "node1", "node2", None) is True

    def test_validate_connection_contracts_warn(self):
        """Test _validate_connection_contracts with warn mode."""
        runtime = LocalRuntime(connection_validation="warn")
        workflow = Mock()

        # Mock contract validator
        with patch('kailash.workflow.contracts.ContractValidator') as mock_validator:
            mock_validator.return_value.validate.return_value = (False, ["Error 1"])

            # Should return False but not raise
            result = runtime._validate_connection_contracts(
                {"param": "value"},
                {"contract": "test"},
                "node1",
                "node2",
                workflow
            )
            assert result is False

    def test_validate_connection_contracts_strict(self):
        """Test _validate_connection_contracts with strict mode."""
        runtime = LocalRuntime(connection_validation="strict")
        workflow = Mock()

        # Mock contract validator with failure
        with patch('kailash.workflow.contracts.ContractValidator') as mock_validator:
            mock_validator.return_value.validate.return_value = (False, ["Error 1"])

            # Should raise exception in strict mode
            with pytest.raises(WorkflowValidationError):
                runtime._validate_connection_contracts(
                    {"param": "value"},
                    {"contract": "test"},
                    "node1",
                    "node2",
                    workflow
                )


class TestMetricsAndReporting:
    """Test metrics and reporting functionality."""

    def test_get_validation_metrics(self):
        """Test get_validation_metrics method."""
        runtime = LocalRuntime()

        metrics = runtime.get_validation_metrics()

        assert "total_validations" in metrics
        assert "validation_errors" in metrics
        assert "validation_warnings" in metrics
        assert "error_categories" in metrics

    def test_reset_validation_metrics(self):
        """Test reset_validation_metrics method."""
        runtime = LocalRuntime()

        # Reset metrics
        runtime.reset_validation_metrics()

        # Get fresh metrics
        metrics = runtime.get_validation_metrics()
        assert metrics["total_validations"] == 0
        assert metrics["validation_errors"] == 0

    def test_get_performance_report(self):
        """Test get_performance_report method."""
        runtime = LocalRuntime()

        # Add some performance data
        runtime._analytics_data["performance_history"] = [
            {"execution_time": 1.0, "nodes_executed": 5},
            {"execution_time": 2.0, "nodes_executed": 10}
        ]

        report = runtime.get_performance_report()

        assert "summary" in report
        assert "execution_history" in report
        assert report["summary"]["total_executions"] == 2
        assert report["summary"]["average_execution_time"] == 1.5

    def test_generate_compatibility_report(self):
        """Test generate_compatibility_report method."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        # Add nodes
        node = PythonCodeNode(name="node", code="result = {'data': 1}")
        workflow.add_node("node", node)

        # Mock compatibility reporter
        runtime._compatibility_reporter = Mock()
        runtime._compatibility_reporter.analyze_workflow.return_value = {
            "compatibility_score": 0.95,
            "issues": []
        }

        report = runtime.generate_compatibility_report(workflow)

        assert "compatibility_score" in report
        assert report["compatibility_score"] == 0.95

    def test_get_compatibility_report_markdown(self):
        """Test get_compatibility_report_markdown method."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        # Mock compatibility reporter
        runtime._compatibility_reporter = Mock()
        runtime._compatibility_reporter.generate_markdown_report.return_value = "# Report\nTest report"

        markdown = runtime.get_compatibility_report_markdown(workflow)

        assert isinstance(markdown, str)
        assert "# Report" in markdown

    def test_performance_monitoring_setters(self):
        """Test performance monitoring setter methods."""
        runtime = LocalRuntime()

        # Test set_performance_monitoring
        runtime.set_performance_monitoring(True)
        assert runtime._enable_performance_monitoring is True

        runtime.set_performance_monitoring(False)
        assert runtime._enable_performance_monitoring is False

        # Test set_automatic_mode_switching
        runtime.set_automatic_mode_switching(True)
        assert runtime._performance_switch_enabled is True

        # Test set_compatibility_reporting
        runtime.set_compatibility_reporting(True)
        assert runtime._enable_compatibility_reporting is True

    def test_get_execution_path_debug_info(self):
        """Test get_execution_path_debug_info method."""
        runtime = LocalRuntime()

        # Add some execution data
        runtime._execution_plan_cache["key1"] = ["node1", "node2"]
        runtime._analytics_data["conditional_executions"] = [
            {"total_nodes": 5, "executed_nodes": 3}
        ]

        debug_info = runtime.get_execution_path_debug_info()

        assert "execution_mode" in debug_info
        assert "cache_entries" in debug_info
        assert "recent_executions" in debug_info
        assert debug_info["cache_entries"] == 1


class TestEdgeCasesAndIntegration:
    """Test edge cases and integration scenarios."""

    @pytest.mark.asyncio
    async def test_execute_workflow_async_with_cycles(self):
        """Test _execute_workflow_async with cyclic workflow."""
        runtime = LocalRuntime(enable_cycles=True)

        # Create cyclic workflow
        workflow = Workflow("test", "Test")
        node = PythonCodeNode(name="counter", code="result = {'count': parameters.get('count', 0) + 1}")
        workflow.add_node("counter", node)
        workflow.create_cycle("test_cycle").connect("counter", "counter", {"result.count": "count"}).max_iterations(3).build()

        # Mock cyclic executor
        runtime.cyclic_executor = Mock()
        runtime.cyclic_executor.execute.return_value = ({"counter": {"result": {"count": 3}}}, None)

        results = await runtime._execute_workflow_async(
            workflow=workflow,
            injected_parameters={},
            task_manager=None,
            run_id="test-run",
            workflow_context={}
        )

        assert "counter" in results
        runtime.cyclic_executor.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_conditional_approach_with_error(self):
        """Test _execute_conditional_approach with execution error."""
        runtime = LocalRuntime(conditional_execution="skip_branches")
        workflow = Workflow("test", "Test")

        # Add switch that will fail
        switch = SwitchNode(name="switch", condition_field="missing", operator="==", value="test")
        workflow.add_node("switch", switch)

        # Mock analyzer and planner
        runtime._conditional_branch_analyzer = Mock()
        runtime._dynamic_execution_planner = Mock()
        runtime._dynamic_execution_planner.create_execution_plan.side_effect = Exception("Planning failed")

        # Should fall back to regular execution
        results = await runtime._execute_conditional_approach(
            workflow=workflow,
            parameters={},
            task_manager=None,
            run_id="test-run",
            workflow_context={}
        )

        # Should still have results from fallback
        assert isinstance(results, dict)

    def test_record_execution_metrics(self):
        """Test _record_execution_metrics method."""
        runtime = LocalRuntime()
        workflow = Mock()
        workflow.name = "test_workflow"

        runtime._record_execution_metrics(
            workflow=workflow,
            start_time=100.0,
            end_time=101.5,
            nodes_executed=10,
            success=True,
            execution_mode="conditional",
            performance_improvement=0.3
        )

        # Check metrics were recorded
        assert len(runtime._performance_metrics) > 0

    @pytest.mark.asyncio
    async def test_execute_single_node_async(self):
        """Test _execute_single_node with async node."""
        runtime = LocalRuntime(enable_async=True)

        # Create async node
        async_node = AsyncMock()
        async_node.execute_async.return_value = {"result": {"async_data": 42}}

        result = await runtime._execute_single_node(
            node_id="async_node",
            node=async_node,
            inputs={"param": "value"},
            workflow_context={},
            task_manager=None
        )

        assert result == {"result": {"async_data": 42}}
        async_node.execute_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_switch_nodes_phase1(self):
        """Test _execute_switch_nodes for phase 1 execution."""
        runtime = LocalRuntime()
        workflow = Workflow("test", "Test")

        # Add switches
        switch1 = SwitchNode(name="switch1", condition_field="field1", operator="==", value="test1")
        switch2 = SwitchNode(name="switch2", condition_field="field2", operator="==", value="test2")

        workflow.add_node("switch1", switch1)
        workflow.add_node("switch2", switch2)

        # Mock analyzer
        runtime._conditional_branch_analyzer = Mock()
        runtime._conditional_branch_analyzer._find_switch_nodes.return_value = ["switch1", "switch2"]

        parameters = {
            "switch1": {"field1": "test1"},
            "switch2": {"field2": "test2"}
        }

        switch_results = await runtime._execute_switch_nodes(
            workflow=workflow,
            switch_nodes=["switch1", "switch2"],
            parameters=parameters,
            task_manager=None,
            workflow_context={}
        )

        assert "switch1" in switch_results
        assert "switch2" in switch_results

    def test_workflow_validation_complex(self):
        """Test complex workflow validation scenarios."""
        runtime = LocalRuntime()

        # Create complex workflow
        workflow = Workflow("complex", "Complex Test")

        # Add multiple node types
        python_node = PythonCodeNode(name="python", code="result = {'data': 1}")
        switch_node = SwitchNode(name="switch", condition_field="status", operator="==", value="active")
        merge_node = MergeNode(name="merge", merge_type="merge_dict")

        workflow.add_node("python", python_node)
        workflow.add_node("switch", switch_node)
        workflow.add_node("merge", merge_node)

        # Create connections
        workflow.connect("python", "switch", {"result": "input_data"})
        workflow.connect("switch", "merge", {"true_output": "input1"})

        errors = runtime.validate_workflow(workflow)
        assert isinstance(errors, list)

    def test_execution_with_resource_limits(self):
        """Test execution with resource limits."""
        resource_limits = {
            "memory_mb": 512,
            "cpu_cores": 1,
            "execution_timeout": 30
        }

        runtime = LocalRuntime(resource_limits=resource_limits)
        workflow = Workflow("test", "Test")

        # Add simple node
        node = PythonCodeNode(name="node", code="result = {'data': 1}")
        workflow.add_node("node", node)

        # Execute with resource limits
        results, run_id = runtime.execute(workflow)

        assert "node" in results
        assert runtime.resource_limits == resource_limits
