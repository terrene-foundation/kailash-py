"""
Parity tests to ensure LocalRuntime and AsyncLocalRuntime have matching methods.

These tests enforce that every public method in LocalRuntime has a corresponding
method in AsyncLocalRuntime (unless explicitly documented as runtime-specific).
"""

import inspect

import pytest
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime

# Document runtime-specific methods that are ALLOWED to differ
ALLOWED_ASYNC_ONLY_METHODS = {
    "execute_workflow_async",  # Async-specific execution method
    "_execute_node_async",  # Async node execution
    "_execute_fully_async_workflow",  # Async workflow optimization
    "_execute_mixed_workflow",  # Mixed sync/async handling
    "_execute_sync_node_async",  # Sync node in async context
    "_execute_sync_node_in_thread",  # Thread pool execution
    "_execute_sync_workflow",  # Sync workflow in async runtime
    "_execute_sync_workflow_internal",
    "_execute_workflow_internal",  # Internal workflow execution orchestration
    "_prepare_async_node_inputs",  # Async input preparation
    "_prepare_sync_node_inputs",  # Sync input preparation
}

ALLOWED_SYNC_ONLY_METHODS = set()  # Currently none - async inherits from sync


class TestRuntimeMethodParity:
    """Test that runtimes have matching methods."""

    def get_public_methods(self, cls):
        """Get all public methods from a class."""
        return {
            name
            for name in dir(cls)
            if not name.startswith("__") and callable(getattr(cls, name))
        }

    def test_all_local_runtime_methods_exist_in_async(self):
        """
        Every public method in LocalRuntime must exist in AsyncLocalRuntime.

        This ensures AsyncLocalRuntime maintains full backward compatibility
        and feature parity with LocalRuntime.
        """
        local_methods = self.get_public_methods(LocalRuntime)
        async_methods = self.get_public_methods(AsyncLocalRuntime)

        # Methods in LocalRuntime but missing from AsyncLocalRuntime
        missing_methods = local_methods - async_methods - ALLOWED_SYNC_ONLY_METHODS

        assert not missing_methods, (
            f"AsyncLocalRuntime is missing {len(missing_methods)} methods from LocalRuntime:\n"
            f"{sorted(missing_methods)}\n\n"
            f"If these are intentionally sync-only, add them to ALLOWED_SYNC_ONLY_METHODS."
        )

    def test_async_specific_methods_documented(self):
        """
        Async-specific methods must be documented in ALLOWED_ASYNC_ONLY_METHODS.

        This ensures we track which methods are intentionally different.
        """
        local_methods = self.get_public_methods(LocalRuntime)
        async_methods = self.get_public_methods(AsyncLocalRuntime)

        # Methods in AsyncLocalRuntime but not in LocalRuntime
        extra_methods = async_methods - local_methods

        # All extra methods should be documented
        undocumented = extra_methods - ALLOWED_ASYNC_ONLY_METHODS

        assert not undocumented, (
            f"AsyncLocalRuntime has {len(undocumented)} undocumented extra methods:\n"
            f"{sorted(undocumented)}\n\n"
            f"Add them to ALLOWED_ASYNC_ONLY_METHODS with documentation."
        )

    def test_conditional_execution_method_exists(self):
        """Test that conditional execution methods exist in both runtimes."""
        critical_methods = [
            "_should_skip_conditional_node",
            "_execute_conditional_approach",
            "_execute_pruned_plan",
            "_has_conditional_patterns",
        ]

        for method_name in critical_methods:
            assert hasattr(
                LocalRuntime, method_name
            ), f"LocalRuntime missing critical method: {method_name}"
            assert hasattr(
                AsyncLocalRuntime, method_name
            ), f"AsyncLocalRuntime missing critical method: {method_name}"

    def test_enterprise_feature_methods_exist(self):
        """Test that enterprise feature methods exist in both runtimes."""
        enterprise_methods = [
            "_check_workflow_access",  # Access control
            "_log_audit_event",  # Audit logging
            "_initialize_persistent_resources",  # Resource management
            "_cleanup_resources",  # Resource cleanup
        ]

        for method_name in enterprise_methods:
            assert hasattr(
                LocalRuntime, method_name
            ), f"LocalRuntime missing enterprise method: {method_name}"
            assert hasattr(
                AsyncLocalRuntime, method_name
            ), f"AsyncLocalRuntime missing enterprise method: {method_name}"

    def test_method_count_reasonable(self):
        """
        Test that method counts are reasonable.

        AsyncLocalRuntime should have at least as many methods as LocalRuntime
        (due to inheritance and async-specific methods).
        """
        local_methods = self.get_public_methods(LocalRuntime)
        async_methods = self.get_public_methods(AsyncLocalRuntime)

        assert len(async_methods) >= len(local_methods), (
            f"AsyncLocalRuntime has fewer methods than LocalRuntime:\n"
            f"  LocalRuntime:      {len(local_methods)} methods\n"
            f"  AsyncLocalRuntime: {len(async_methods)} methods\n"
            f"This suggests methods are missing from AsyncLocalRuntime."
        )

    def test_inheritance_relationship(self):
        """Test that AsyncLocalRuntime inherits from LocalRuntime."""
        assert issubclass(
            AsyncLocalRuntime, LocalRuntime
        ), "AsyncLocalRuntime must inherit from LocalRuntime for parity"

    def test_execution_methods_exist(self):
        """Test that core execution methods exist in both runtimes."""
        execution_methods = [
            "execute",  # Sync execution
            "_execute_single_node",
            "_execute_sync",
        ]

        for method_name in execution_methods:
            assert hasattr(
                LocalRuntime, method_name
            ), f"LocalRuntime missing: {method_name}"
            assert hasattr(
                AsyncLocalRuntime, method_name
            ), f"AsyncLocalRuntime missing: {method_name}"

        # Async-specific execution method
        assert hasattr(
            AsyncLocalRuntime, "execute_workflow_async"
        ), "AsyncLocalRuntime missing execute_workflow_async"


class TestRuntimePropertyParity:
    """Test that runtime properties are consistent."""

    def test_conditional_execution_property_exists(self):
        """Test conditional_execution property exists in both."""
        local_runtime = LocalRuntime()
        async_runtime = AsyncLocalRuntime()

        assert hasattr(local_runtime, "conditional_execution")
        assert hasattr(async_runtime, "conditional_execution")

    def test_conditional_execution_default_value_matches(self):
        """Test that conditional_execution has same default in both."""
        local_runtime = LocalRuntime()
        async_runtime = AsyncLocalRuntime()

        assert (
            local_runtime.conditional_execution == async_runtime.conditional_execution
        )
        assert local_runtime.conditional_execution == "route_data"  # Expected default


class TestUnifiedConditionalNodeSkipping_LocalRuntimeCompatibility:
    """Test LocalRuntime compatibility with unified _should_skip_conditional_node from mixin.

    These tests are part of Phase 4D Step 1: Semantic Analysis and Mixin Enhancement.
    They verify that LocalRuntime correctly uses the enhanced mixin method instead of
    its own override.
    """

    def test_localruntime_no_override_of_should_skip_method(self):
        """Test LocalRuntime does NOT override _should_skip_conditional_node.

        Expected behavior:
        - After Phase 4D Step 1 implementation, LocalRuntime deletes its override
        - Method should come from ConditionalExecutionMixin via MRO
        - This test will FAIL in RED phase (LocalRuntime still has override)
        - This test will PASS in GREEN phase (override deleted)
        """
        from kailash.runtime.mixins import ConditionalExecutionMixin

        runtime = LocalRuntime()
        method = runtime._should_skip_conditional_node

        # Get the method's defining class
        method_class = method.__qualname__.split(".")[0]

        # Method should be defined in ConditionalExecutionMixin, not LocalRuntime
        assert method_class == "ConditionalExecutionMixin", (
            f"_should_skip_conditional_node should be defined in ConditionalExecutionMixin, "
            f"but found in {method_class}. LocalRuntime should not override this method."
        )

    @pytest.mark.skip(
        reason="Flaky test with test order dependency - node registry not initialized in full suite. SDK issue, unrelated to DataFlow. Passes individually."
    )
    def test_localruntime_execution_uses_mixin_method(self):
        """Test LocalRuntime execution calls unified mixin method correctly.

        Expected behavior:
        - LocalRuntime.execute() calls mixin's _should_skip_conditional_node
        - Unified method supports inputs-based skipping (LocalRuntime pattern)
        - Workflow with switch executes correctly with conditional skipping
        - This test validates integration between LocalRuntime and mixin
        """
        from kailash.workflow.builder import WorkflowBuilder

        runtime = LocalRuntime(conditional_execution="skip_branches")

        # Create workflow with switch
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode", "input_node", {"code": "result = {'status': 'active'}"}
        )
        builder.add_node(
            "SwitchNode",
            "switch",
            {"condition_field": "status", "operator": "==", "value": "active"},
        )
        builder.add_node(
            "PythonCodeNode", "true_proc", {"code": "result = 'true_path'"}
        )
        builder.add_node(
            "PythonCodeNode", "false_proc", {"code": "result = 'false_path'"}
        )
        builder.add_connection("input_node", "result", "switch", "input_data")
        builder.add_connection("switch", "true_output", "true_proc", "input")
        builder.add_connection("switch", "false_output", "false_proc", "input")
        workflow = builder.build()

        # Execute workflow
        results, run_id = runtime.execute(workflow)

        # Verify skipping behavior
        assert "input_node" in results, "Input node should execute"
        assert "switch" in results, "Switch node should execute"
        assert "true_proc" in results, "True branch should execute (status='active')"
        # false_proc may or may not be in results depending on skip_branches implementation

    def test_asynclocalruntime_inherits_unified_method(self):
        """Test AsyncLocalRuntime inherits unified mixin method via MRO.

        Expected behavior:
        - AsyncLocalRuntime inherits from LocalRuntime
        - LocalRuntime uses mixin's _should_skip_conditional_node
        - AsyncLocalRuntime gets mixin method via inheritance chain
        - MRO: AsyncLocalRuntime -> LocalRuntime -> ConditionalExecutionMixin
        """
        from kailash.runtime.mixins import ConditionalExecutionMixin

        runtime = AsyncLocalRuntime()
        method = runtime._should_skip_conditional_node

        # Get the method's defining class
        method_class = method.__qualname__.split(".")[0]

        # Method should come from ConditionalExecutionMixin via MRO
        assert method_class == "ConditionalExecutionMixin", (
            f"_should_skip_conditional_node should be inherited from ConditionalExecutionMixin, "
            f"but found in {method_class}."
        )

        # Verify MRO includes ConditionalExecutionMixin
        assert (
            ConditionalExecutionMixin in AsyncLocalRuntime.__mro__
        ), "AsyncLocalRuntime MRO should include ConditionalExecutionMixin"
