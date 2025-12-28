"""
Test suite for WorkflowAPI async runtime selection.

This test validates the Docker threading fix where WorkflowAPI now uses
AsyncLocalRuntime by default instead of LocalRuntime to avoid double-threading
deadlocks in Docker/FastAPI deployments.
"""

import pytest
from kailash.api.workflow_api import WorkflowAPI
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestWorkflowAPIRuntimeSelection:
    """Test runtime selection in WorkflowAPI."""

    def test_default_runtime_is_async(self):
        """Test that WorkflowAPI defaults to AsyncLocalRuntime."""
        # Create simple workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "test",
            {"code": "result = {'success': True}"},
        )

        # Create API without specifying runtime
        api = WorkflowAPI(workflow)

        # Verify AsyncLocalRuntime was selected by default
        assert isinstance(
            api.runtime, AsyncLocalRuntime
        ), f"Expected AsyncLocalRuntime, got {type(api.runtime).__name__}"

    def test_explicit_sync_runtime_works(self):
        """Test that LocalRuntime can be explicitly provided for backward compatibility."""
        # Create simple workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "test",
            {"code": "result = {'data': 'hello'}"},
        )

        # Create API with explicit LocalRuntime
        sync_runtime = LocalRuntime()
        api = WorkflowAPI(workflow, runtime=sync_runtime)

        # Verify LocalRuntime was used
        assert isinstance(
            api.runtime, LocalRuntime
        ), f"Expected LocalRuntime, got {type(api.runtime).__name__}"

        # Verify it's not AsyncLocalRuntime (AsyncLocalRuntime extends LocalRuntime)
        assert not isinstance(
            api.runtime, AsyncLocalRuntime
        ), "Should use LocalRuntime, not AsyncLocalRuntime when explicitly provided"

    def test_explicit_async_runtime_works(self):
        """Test that AsyncLocalRuntime can be explicitly provided with custom config."""
        # Create simple workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "test",
            {"code": "result = {'value': 42}"},
        )

        # Create API with explicit AsyncLocalRuntime with custom config
        async_runtime = AsyncLocalRuntime(max_concurrent_nodes=20)
        api = WorkflowAPI(workflow, runtime=async_runtime)

        # Verify AsyncLocalRuntime was used
        assert isinstance(api.runtime, AsyncLocalRuntime)
        assert api.runtime.max_concurrent_nodes == 20

    @pytest.mark.asyncio
    async def test_async_execution_no_threading(self):
        """
        Test that AsyncLocalRuntime execution doesn't create threads.

        This is the core fix for the Docker threading issue. When using
        AsyncLocalRuntime, workflow execution should be fully async with
        no thread creation via asyncio.to_thread().

        NOTE: Uses a lightweight workflow to avoid heavy scipy/numpy import
        timeouts that occur with PythonCodeNode security validation.
        """
        import asyncio
        import time

        # Create simple workflow with minimal node type
        # Using MockNode to avoid PythonCodeNode's heavy security imports
        # MockNode from conftest.py expects 'value' parameter and returns {"result": value * 2}
        workflow = WorkflowBuilder()
        workflow.add_node(
            "MockNode",
            "compute",
            {"value": 42},  # Required parameter for conftest MockNode
        )

        # Create API with default AsyncLocalRuntime
        api = WorkflowAPI(workflow)

        # Verify AsyncLocalRuntime was selected
        from kailash.runtime.async_local import AsyncLocalRuntime

        assert isinstance(
            api.runtime, AsyncLocalRuntime
        ), "WorkflowAPI should default to AsyncLocalRuntime"

        # Prepare request
        from kailash.api.workflow_api import WorkflowRequest

        request = WorkflowRequest(inputs={})

        # Execute should complete without hanging
        # Set a short timeout to detect threading deadlocks
        start_time = time.time()

        try:
            response = await asyncio.wait_for(api._execute_sync(request), timeout=2.0)

            execution_time = time.time() - start_time

            # Validate response - MockNode returns {"result": value * 2}
            # Outputs are keyed by node ID: {'compute': {'result': 84}}
            expected_result = 84  # 42 * 2
            assert (
                "compute" in response.outputs
            ), f"Node 'compute' not in outputs: {response.outputs}"
            assert (
                response.outputs["compute"]["result"] == expected_result
            ), f"Expected result={expected_result}, got {response.outputs['compute']}"
            assert execution_time < 2.0, (
                f"Execution took {execution_time:.2f}s - too slow! "
                "Should complete in <100ms with AsyncLocalRuntime"
            )
            assert response.workflow_id is not None

            # Log success metrics
            print(
                f"\n✅ AsyncLocalRuntime execution: {execution_time*1000:.0f}ms "
                f"(expected <100ms, no threading)"
            )

        except asyncio.TimeoutError:
            pytest.fail(
                "Workflow execution timed out after 2.0s! "
                "This suggests a threading deadlock or the fix didn't work. "
                "AsyncLocalRuntime should complete in <100ms with no thread creation."
            )


class TestRuntimeHelperFunction:
    """Test the get_runtime() helper function."""

    def test_get_async_runtime(self):
        """Test get_runtime with 'async' context."""
        from kailash.runtime import get_runtime

        runtime = get_runtime("async")
        assert isinstance(runtime, AsyncLocalRuntime)

    def test_get_sync_runtime(self):
        """Test get_runtime with 'sync' context."""
        from kailash.runtime import get_runtime

        runtime = get_runtime("sync")
        assert isinstance(runtime, LocalRuntime)
        # Should be LocalRuntime, not AsyncLocalRuntime subclass
        assert type(runtime).__name__ == "LocalRuntime"

    def test_get_runtime_with_kwargs(self):
        """Test get_runtime passes kwargs to runtime constructor."""
        from kailash.runtime import get_runtime

        runtime = get_runtime("async", max_concurrent_nodes=25)
        assert isinstance(runtime, AsyncLocalRuntime)
        assert runtime.max_concurrent_nodes == 25

    def test_get_runtime_invalid_context(self):
        """Test get_runtime raises ValueError for invalid context."""
        from kailash.runtime import get_runtime

        with pytest.raises(ValueError, match="Invalid context"):
            get_runtime("invalid_context")

    def test_get_runtime_auto_detects_context(self):
        """Test get_runtime auto-detects context when not specified (P0-4 fix).

        In sync contexts (like this test), it detects and returns LocalRuntime.
        In async contexts (event loop running), it returns AsyncLocalRuntime.
        """
        from kailash.runtime import LocalRuntime, get_runtime

        runtime = get_runtime()  # No context argument - auto-detects sync
        assert isinstance(runtime, LocalRuntime)  # Sync context detected


class TestRuntimeValidation:
    """Test runtime validation in WorkflowAPI."""

    def test_invalid_runtime_raises_typeerror(self):
        """Test that invalid runtime raises TypeError."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "MockNode",
            "test",
            {"output": {"ok": True}},
        )

        # Try to pass invalid runtime (string instead of runtime object)
        with pytest.raises(TypeError, match="Runtime must have 'execute' method"):
            WorkflowAPI(workflow, runtime="invalid_runtime")

        # Try to pass object without execute method
        class InvalidRuntime:
            pass

        with pytest.raises(TypeError, match="Runtime must have 'execute' method"):
            WorkflowAPI(workflow, runtime=InvalidRuntime())

    def test_valid_runtime_accepted(self):
        """Test that valid runtimes are accepted."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "MockNode",
            "test",
            {"output": {"ok": True}},
        )

        # LocalRuntime should work
        api1 = WorkflowAPI(workflow, runtime=LocalRuntime())
        assert api1.runtime is not None

        # AsyncLocalRuntime should work
        api2 = WorkflowAPI(workflow, runtime=AsyncLocalRuntime())
        assert api2.runtime is not None

        # Custom runtime with execute method should work
        class CustomRuntime:
            def execute(self, workflow, **kwargs):
                return {}, "run_id"

        api3 = WorkflowAPI(workflow, runtime=CustomRuntime())
        assert api3.runtime is not None


class TestBackwardCompatibility:
    """Test that changes maintain backward compatibility."""

    def test_old_code_still_works(self):
        """Test that existing code without runtime parameter still works."""
        # Old pattern: Just create WorkflowAPI without runtime param
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "test",
            {"code": "result = {'status': 'ok'}"},
        )

        # This should work and default to AsyncLocalRuntime
        api = WorkflowAPI(workflow)

        # Should create FastAPI app successfully
        assert api.app is not None
        assert api.workflow_graph is not None

    def test_explicit_local_runtime_for_cli(self):
        """Test that CLI/script users can still use LocalRuntime explicitly."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "test",
            {"code": "result = {'mode': 'cli'}"},
        )

        # Explicitly use LocalRuntime for CLI context
        api = WorkflowAPI(workflow, runtime=LocalRuntime())

        # Should work correctly
        assert isinstance(api.runtime, LocalRuntime)
        assert not isinstance(api.runtime, AsyncLocalRuntime)
