"""Regression tests for Phase 0a Quick Win optimizations.

Validates that all P0A performance optimizations are in place and functional:
- P0A-001: Module-level imports (DataTypeValidator, resource_manager errors, networkx)
- P0A-002: Shared MetricsCollector per workflow execution
- P0A-003: psutil resource checks opt-in via enable_resource_limits
- P0A-004: Cached environment variable lookups in Node base class
- P0A-005: Cached graph node IDs in _prepare_node_inputs and parameter methods
"""

from unittest.mock import patch

import pytest

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# --- P0A-001: Module-level imports ---


class TestP0A001ModuleLevelImports:
    """Verify that DataTypeValidator and resource_manager errors are module-level imports."""

    def test_datatypevalidator_is_module_level(self):
        """DataTypeValidator should be importable from local module scope, not lazy."""
        import kailash.runtime.local as local_module

        assert hasattr(local_module, "DataTypeValidator")
        from kailash.utils.data_validation import DataTypeValidator

        assert local_module.DataTypeValidator is DataTypeValidator

    def test_resource_error_classes_are_module_level(self):
        """Resource manager error classes should be module-level imports."""
        import kailash.runtime.local as local_module
        from kailash.runtime.resource_manager import (
            ConnectionLimitExceededError,
            CPULimitExceededError,
            MemoryLimitExceededError,
        )

        assert local_module.CPULimitExceededError is CPULimitExceededError
        assert local_module.ConnectionLimitExceededError is ConnectionLimitExceededError
        assert local_module.MemoryLimitExceededError is MemoryLimitExceededError

    def test_no_inline_datatypevalidator_import_in_execute(self):
        """Source code of local.py should have exactly one DataTypeValidator import."""
        import inspect

        import kailash.runtime.local as local_module

        source = inspect.getsource(local_module)
        import_line = "from kailash.utils.data_validation import DataTypeValidator"
        occurrences = source.count(import_line)
        assert occurrences == 1, (
            f"Expected exactly 1 module-level DataTypeValidator import, "
            f"found {occurrences}. In-loop imports may have been re-added."
        )

    def test_networkx_removed_from_conditional_execution(self):
        """P0C: networkx should be fully removed from conditional_execution.py (replaced by WorkflowDAG)."""
        import inspect

        import kailash.runtime.mixins.conditional_execution as ce_module

        source = inspect.getsource(ce_module)
        # P0C: networkx should not be imported at all (replaced by WorkflowDAG)
        assert "import networkx" not in source, (
            "conditional_execution.py still imports networkx. "
            "P0C replaced all networkx usage with WorkflowDAG."
        )
        assert not hasattr(ce_module, "nx"), (
            "networkx (as nx) still found at module level in conditional_execution.py. "
            "P0C replaced all networkx usage with WorkflowDAG."
        )

    def test_networkx_removed_from_hierarchical_switch(self):
        """P0C: networkx should be fully removed from hierarchical_switch_executor.py (replaced by WorkflowDAG)."""
        import inspect

        import kailash.runtime.hierarchical_switch_executor as hs_module

        source = inspect.getsource(hs_module)
        # P0C: networkx should not be imported at all (replaced by WorkflowDAG)
        assert "import networkx" not in source, (
            "hierarchical_switch_executor.py still imports networkx. "
            "P0C replaced all networkx usage with WorkflowDAG."
        )
        assert not hasattr(hs_module, "nx"), (
            "networkx (as nx) still found at module level in hierarchical_switch_executor.py. "
            "P0C replaced all networkx usage with WorkflowDAG."
        )

    def test_networkx_removed_from_compatibility_reporter(self):
        """P0C: networkx should be fully removed from compatibility_reporter.py (replaced by WorkflowDAG)."""
        import inspect

        import kailash.runtime.compatibility_reporter as cr_module

        source = inspect.getsource(cr_module)
        # P0C: networkx should not be imported at all (replaced by WorkflowDAG)
        assert "import networkx" not in source, (
            "compatibility_reporter.py still imports networkx. "
            "P0C replaced all networkx usage with WorkflowDAG."
        )
        assert not hasattr(cr_module, "nx"), (
            "networkx (as nx) still found at module level in compatibility_reporter.py. "
            "P0C replaced all networkx usage with WorkflowDAG."
        )


# --- P0A-002: Shared MetricsCollector ---


class TestP0A002SharedMetricsCollector:
    """Verify that MetricsCollector is created once per workflow execution."""

    def test_shared_collector_in_source(self):
        """The _shared_collector variable should exist in the execute method source."""
        import inspect

        source = inspect.getsource(LocalRuntime._execute_workflow_async)
        assert "_shared_collector = MetricsCollector(" in source, (
            "Shared MetricsCollector not found in _execute_workflow_async. "
            "P0A-002 optimization may have been reverted."
        )
        assert (
            "_shared_collector.collect(" in source
        ), "Shared collector not used in execution loop."

    def test_workflow_executes_with_shared_collector(self):
        """Workflow execution should work correctly with shared MetricsCollector."""
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode", "node_a", {"code": "result = {'data': 'hello'}"}
        )
        builder.add_node(
            "PythonCodeNode", "node_b", {"code": "result = {'data': 'world'}"}
        )
        builder.add_connection("node_a", "result", "node_b", "input")

        with LocalRuntime(debug=True) as runtime:
            results, run_id = runtime.execute(builder.build())

        assert "node_a" in results
        assert "node_b" in results


# --- P0A-003: psutil opt-in ---


class TestP0A003PsutilOptIn:
    """Verify that resource limit checks are gated by enable_resource_limits."""

    def test_enable_resource_limits_default_false(self):
        """BaseRuntime should default enable_resource_limits to False."""
        with LocalRuntime() as runtime:
            assert hasattr(runtime, "enable_resource_limits")
            assert runtime.enable_resource_limits is False

    def test_enable_resource_limits_can_be_enabled(self):
        """enable_resource_limits=True should be accepted."""
        with LocalRuntime(enable_resource_limits=True) as runtime:
            assert runtime.enable_resource_limits is True

    def test_resource_checks_skipped_when_disabled(self):
        """When enable_resource_limits=False, check_all_limits should not be called."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "node", {"code": "result = {'out': 'test'}"})

        with LocalRuntime(enable_resource_limits=False) as runtime:
            if runtime._resource_enforcer:
                with patch.object(
                    runtime._resource_enforcer, "check_all_limits"
                ) as mock_check:
                    results, _ = runtime.execute(builder.build())
                    mock_check.assert_not_called()
            else:
                results, _ = runtime.execute(builder.build())

            assert "node" in results

    def test_source_has_enable_resource_limits_guard(self):
        """The resource limit check should be guarded by enable_resource_limits."""
        import inspect

        source = inspect.getsource(LocalRuntime._execute_async)
        assert "self.enable_resource_limits" in source, (
            "enable_resource_limits guard not found in execution method. "
            "P0A-003 optimization may have been reverted."
        )


# --- P0A-005: Cached graph node IDs ---


class TestP0A005CachedNodeIds:
    """Verify that graph node IDs are cached once per execution."""

    def test_node_ids_precomputed_in_source(self):
        """_node_ids should be computed before the execution loop."""
        import inspect

        source = inspect.getsource(LocalRuntime._execute_workflow_async)
        assert "_node_ids" in source, (
            "_node_ids not found in execution method. "
            "P0A-005 optimization may have been reverted."
        )
        assert (
            "frozenset(workflow.graph.nodes())" in source
        ), "frozenset precomputation not found."

    def test_prepare_node_inputs_accepts_node_ids(self):
        """_prepare_node_inputs should accept optional _node_ids parameter."""
        import inspect

        sig = inspect.signature(LocalRuntime._prepare_node_inputs)
        assert "_node_ids" in sig.parameters, (
            "_node_ids parameter not found in _prepare_node_inputs. "
            "P0A-005 optimization may have been reverted."
        )
        param = sig.parameters["_node_ids"]
        assert (
            param.default is None
        ), "_node_ids should default to None for backward compatibility."

    def test_workflow_execution_with_cached_ids(self):
        """Multi-node workflow should execute correctly with cached node IDs."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "first", {"code": "result = {'data': '1'}"})
        builder.add_node("PythonCodeNode", "second", {"code": "result = {'data': '2'}"})
        builder.add_node("PythonCodeNode", "third", {"code": "result = {'data': '3'}"})
        builder.add_connection("first", "result", "second", "input")
        builder.add_connection("second", "result", "third", "input")

        with LocalRuntime() as runtime:
            results, run_id = runtime.execute(builder.build())

        assert len(results) == 3
        assert "first" in results
        assert "second" in results
        assert "third" in results

    def test_prepare_node_inputs_backward_compatible(self):
        """_prepare_node_inputs should work without _node_ids (backward compat)."""
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode", "node_a", {"code": "result = {'out': 'test'}"}
        )
        workflow = builder.build()

        with LocalRuntime() as runtime:
            result = runtime._prepare_node_inputs(
                workflow=workflow,
                node_id="node_a",
                node_instance=workflow._node_instances["node_a"],
                node_outputs={},
                parameters={},
            )
            assert result is None or isinstance(result, dict)


# --- Integration: Full pipeline with all optimizations ---


class TestPhase0aIntegration:
    """End-to-end tests verifying all P0A optimizations work together."""

    def test_simple_workflow_all_optimizations(self):
        """Basic workflow should execute correctly with all P0A optimizations active."""
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode", "input_node", {"code": "result = {'data': 'hello'}"}
        )
        builder.add_node(
            "PythonCodeNode", "output_node", {"code": "result = {'data': 'world'}"}
        )
        builder.add_connection("input_node", "result", "output_node", "input")

        with LocalRuntime(debug=True) as runtime:
            results, run_id = runtime.execute(builder.build())

        assert run_id is not None
        assert "input_node" in results
        assert "output_node" in results

    def test_parameterized_workflow(self):
        """Workflow with runtime parameters should work with cached node IDs."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "node", {"code": "result = {'out': x}"})

        with LocalRuntime() as runtime:
            results, run_id = runtime.execute(
                builder.build(),
                parameters={"node": {"x": "from_params"}},
            )

        assert "node" in results

    def test_multiple_executions_independent(self):
        """Multiple workflow executions should be independent (no shared state leakage)."""
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode", "node", {"code": "result = {'data': 'default'}"}
        )

        with LocalRuntime() as runtime:
            workflow = builder.build()

            results1, run_id1 = runtime.execute(workflow)
            results2, run_id2 = runtime.execute(workflow)

        assert "node" in results1
        assert "node" in results2
        assert run_id1 != run_id2

    def test_single_node_no_connections(self):
        """Single-node workflow should work (tests _node_ids with minimal graph)."""
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode", "solo", {"code": "result = {'data': 'alone'}"}
        )

        with LocalRuntime() as runtime:
            results, run_id = runtime.execute(builder.build())

        assert "solo" in results


# --- P0A-004: Cached environment variable lookups ---


class TestP0A004EnvCache:
    """Verify that Node base class caches environment variable lookups."""

    def test_get_env_classmethod_exists(self):
        """Node class should have _get_env classmethod for cached env lookups."""
        from kailash.nodes.base import Node

        assert hasattr(
            Node, "_get_env"
        ), "Node._get_env classmethod not found. P0A-004 not implemented."
        assert callable(Node._get_env)

    def test_clear_env_cache_exists(self):
        """Node class should have _clear_env_cache classmethod for test isolation."""
        from kailash.nodes.base import Node

        assert hasattr(
            Node, "_clear_env_cache"
        ), "Node._clear_env_cache classmethod not found. P0A-004 not implemented."
        assert callable(Node._clear_env_cache)

    def test_get_env_returns_cached_value(self):
        """_get_env should cache values and return same result on second call."""
        import os

        from kailash.nodes.base import Node

        Node._clear_env_cache()

        os.environ["_KAILASH_TEST_P0A004"] = "cached_value"
        try:
            val1 = Node._get_env("_KAILASH_TEST_P0A004")
            assert val1 == "cached_value"

            # Change env var — cached value should persist
            os.environ["_KAILASH_TEST_P0A004"] = "new_value"
            val2 = Node._get_env("_KAILASH_TEST_P0A004")
            assert (
                val2 == "cached_value"
            ), "_get_env did not return cached value. Cache not working."
        finally:
            del os.environ["_KAILASH_TEST_P0A004"]
            Node._clear_env_cache()

    def test_clear_env_cache_forces_reread(self):
        """_clear_env_cache should force re-read from os.environ."""
        import os

        from kailash.nodes.base import Node

        Node._clear_env_cache()

        os.environ["_KAILASH_TEST_P0A004_CLR"] = "original"
        try:
            val1 = Node._get_env("_KAILASH_TEST_P0A004_CLR")
            assert val1 == "original"

            os.environ["_KAILASH_TEST_P0A004_CLR"] = "updated"
            Node._clear_env_cache()

            val2 = Node._get_env("_KAILASH_TEST_P0A004_CLR")
            assert (
                val2 == "updated"
            ), "After _clear_env_cache, _get_env should re-read from os.environ."
        finally:
            del os.environ["_KAILASH_TEST_P0A004_CLR"]
            Node._clear_env_cache()

    def test_get_env_returns_default_for_missing(self):
        """_get_env should return default for keys not in os.environ."""
        from kailash.nodes.base import Node

        Node._clear_env_cache()
        val = Node._get_env("_KAILASH_NONEXISTENT_KEY_P0A004", "fallback")
        assert val == "fallback"
        Node._clear_env_cache()

    def test_env_cache_used_in_node_init(self):
        """Node.__init__ should use _get_env for KAILASH_PARAM_CACHE_SIZE and
        KAILASH_DISABLE_PARAM_CACHE instead of direct os.environ.get."""
        import inspect

        from kailash.nodes.base import Node

        source = inspect.getsource(Node.__init__)
        # Should use _get_env or cls._get_env, not raw os.environ.get
        assert "os.environ.get" not in source, (
            "Node.__init__ still uses os.environ.get directly. "
            "P0A-004: Replace with self._get_env() or cls._get_env()."
        )


# --- P0A-005: Additional _separate_parameter_formats and _is_node_specific_format ---


class TestP0A005ParameterMethodsAcceptNodeIds:
    """Verify parameter methods accept pre-computed node_ids to avoid redundant set() calls."""

    def test_separate_parameter_formats_accepts_node_ids(self):
        """_separate_parameter_formats should accept optional node_ids_set parameter."""
        import inspect

        sig = inspect.signature(LocalRuntime._separate_parameter_formats)
        assert "node_ids_set" in sig.parameters, (
            "_separate_parameter_formats should accept node_ids_set parameter. "
            "P0A-005 optimization incomplete."
        )
        param = sig.parameters["node_ids_set"]
        assert (
            param.default is None
        ), "node_ids_set should default to None for backward compatibility."

    def test_is_node_specific_format_accepts_node_ids(self):
        """_is_node_specific_format should accept optional node_ids_set parameter."""
        import inspect

        sig = inspect.signature(LocalRuntime._is_node_specific_format)
        assert "node_ids_set" in sig.parameters, (
            "_is_node_specific_format should accept node_ids_set parameter. "
            "P0A-005 optimization incomplete."
        )
        param = sig.parameters["node_ids_set"]
        assert (
            param.default is None
        ), "node_ids_set should default to None for backward compatibility."

    def test_separate_parameter_formats_uses_provided_node_ids(self):
        """When node_ids_set is provided, _separate_parameter_formats should use it
        instead of computing set(workflow.graph.nodes())."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "node_a", {"code": "result = {'out': 1}"})
        builder.add_node("PythonCodeNode", "node_b", {"code": "result = {'out': 2}"})
        workflow = builder.build()

        with LocalRuntime() as runtime:
            node_ids = frozenset(workflow.graph.nodes())
            params = {"node_a": {"x": 1}, "global_param": "value"}
            node_specific, workflow_level = runtime._separate_parameter_formats(
                params, workflow, node_ids_set=node_ids
            )
            assert "node_a" in node_specific
            assert "global_param" in workflow_level

    def test_is_node_specific_format_uses_provided_node_ids(self):
        """When node_ids_set is provided, _is_node_specific_format should use it."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "node_a", {"code": "result = {'out': 1}"})
        workflow = builder.build()

        with LocalRuntime() as runtime:
            node_ids = frozenset(workflow.graph.nodes())
            result = runtime._is_node_specific_format(
                {"node_a": {"x": 1}}, workflow, node_ids_set=node_ids
            )
            assert result is True

    def test_no_set_graph_nodes_in_parameter_methods(self):
        """_separate_parameter_formats and _is_node_specific_format should not
        compute set(workflow.graph.nodes()) when node_ids_set is provided."""
        import inspect

        # Check _separate_parameter_formats uses node_ids_set
        source_sep = inspect.getsource(LocalRuntime._separate_parameter_formats)
        assert (
            "node_ids_set" in source_sep
        ), "_separate_parameter_formats does not reference node_ids_set parameter."

        # Check _is_node_specific_format uses node_ids_set
        source_fmt = inspect.getsource(LocalRuntime._is_node_specific_format)
        assert (
            "node_ids_set" in source_fmt
        ), "_is_node_specific_format does not reference node_ids_set parameter."
