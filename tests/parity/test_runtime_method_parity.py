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
