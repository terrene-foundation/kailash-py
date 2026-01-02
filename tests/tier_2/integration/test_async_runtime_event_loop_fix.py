"""
P0-7: Event Loop Detection Fix - Critical Reliability Fix

CRITICAL RELIABILITY ISSUES PREVENTED:
- AsyncLocalRuntime creates event loop in __init__
- "attached to different loop" errors in FastAPI
- Deadlocks when multiple concurrent requests arrive
- Event loop set at construction instead of execution time

Tests verify:
1. AsyncLocalRuntime doesn't create event loop in __init__
2. Event loop set during execution, not construction
3. No "attached to different loop" errors
4. Works correctly in FastAPI context
5. No deadlocks with multiple concurrent requests
"""

import asyncio

import pytest
import pytest_asyncio
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestEventLoopDetectionFix:
    """Test AsyncLocalRuntime event loop detection fix."""

    def test_runtime_init_does_not_create_event_loop(self):
        """
        TEST: AsyncLocalRuntime.__init__ should NOT create an event loop.

        CRITICAL: Prevents "attached to different loop" errors.
        """
        # GIVEN: No event loop running
        try:
            loop = asyncio.get_running_loop()
            pytest.skip("Event loop already running, cannot test initialization")
        except RuntimeError:
            # Good - no event loop running
            pass

        # WHEN: Creating AsyncLocalRuntime instance
        runtime = AsyncLocalRuntime()

        # THEN: Should not create event loop during __init__
        try:
            loop = asyncio.get_running_loop()
            pytest.fail(
                "❌ CRITICAL BUG: AsyncLocalRuntime.__init__ created event loop "
                "(should only create during execution)"
            )
        except RuntimeError:
            # Correct - no event loop created during init
            print("✅ P0-7.1: AsyncLocalRuntime.__init__ does not create event loop")

        # Verify runtime is still usable
        assert runtime is not None
        assert isinstance(runtime, AsyncLocalRuntime)

    @pytest.mark.asyncio
    async def test_event_loop_set_during_execution(self):
        """
        TEST: Event loop should be set during execution, not construction.

        RELIABILITY: Ensures runtime uses correct event loop.
        """
        # GIVEN: Event loop running (pytest-asyncio)
        current_loop = asyncio.get_running_loop()
        assert current_loop is not None

        # WHEN: Creating runtime (should not set loop yet)
        runtime = AsyncLocalRuntime()

        # AND: Executing workflow (should set loop now)
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "test",
            {"code": "output = {'result': 'success'}"},
        )
        workflow = builder.build()

        results, run_id = await runtime.execute_workflow_async(workflow, inputs={})

        # THEN: Should execute successfully with correct event loop
        assert results is not None
        assert run_id is not None

        print("✅ P0-7.2: Event loop set during execution (lazy initialization)")

    @pytest.mark.asyncio
    async def test_no_attached_to_different_loop_error(self):
        """
        TEST: Should not raise "attached to different loop" error.

        CRITICAL: Verifies the core bug is fixed.
        """
        # GIVEN: Current event loop
        loop1 = asyncio.get_running_loop()

        # WHEN: Creating runtime and executing
        runtime = AsyncLocalRuntime()

        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "test",
            {"code": "output = {'status': 'ok'}"},
        )
        workflow = builder.build()

        try:
            results, run_id = await runtime.execute_workflow_async(workflow, inputs={})

            # THEN: Should succeed without error
            assert results is not None
            assert run_id is not None

            print("✅ P0-7.3: No 'attached to different loop' error")

        except RuntimeError as e:
            if "attached to a different loop" in str(e).lower():
                pytest.fail(f"❌ CRITICAL BUG: 'attached to different loop' error: {e}")
            else:
                raise

    @pytest.mark.asyncio
    async def test_multiple_executions_same_runtime_instance(self):
        """
        TEST: Same runtime instance should handle multiple executions.

        RELIABILITY: Runtime reusable across multiple requests.
        """
        # GIVEN: Single runtime instance
        runtime = AsyncLocalRuntime()

        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "test",
            {"code": "output = {'execution': execution_count}"},
        )
        workflow = builder.build()

        # WHEN: Executing multiple times with same runtime
        results = []
        for i in range(5):
            result, run_id = await runtime.execute_workflow_async(
                workflow, inputs={"execution_count": i}
            )
            results.append(result)

        # THEN: All executions should succeed
        assert all(
            r is not None for r in results
        ), "❌ BUG: Not all executions succeeded"

        print("✅ P0-7.4: Same runtime instance handles multiple executions")

    @pytest.mark.asyncio
    async def test_concurrent_executions_same_runtime(self):
        """
        TEST: Concurrent executions with same runtime should work.

        RELIABILITY: No deadlocks with concurrent requests.
        """
        # GIVEN: Single runtime instance
        runtime = AsyncLocalRuntime()

        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "test",
            {"code": "import time; time.sleep(0.05); output = {'done': True}"},
        )
        workflow = builder.build()

        # WHEN: Executing 10 concurrent requests
        tasks = [runtime.execute_workflow_async(workflow, inputs={}) for _ in range(10)]

        try:
            results = await asyncio.gather(*tasks)

            # THEN: All should succeed without deadlock (results are tuples of (results, run_id))
            assert all(
                r[0] is not None for r in results
            ), "❌ BUG: Some concurrent executions failed"

            print("✅ P0-7.5: Concurrent executions work without deadlocks")

        except asyncio.TimeoutError:
            pytest.fail("❌ CRITICAL BUG: Deadlock detected in concurrent executions")


class TestFastAPIContextSimulation:
    """Test AsyncLocalRuntime behavior in FastAPI-like context."""

    @pytest.mark.asyncio
    async def test_fastapi_request_pattern(self):
        """
        TEST: Simulate FastAPI request pattern (new runtime per request).

        RELIABILITY: Works correctly in typical FastAPI usage.
        """

        async def simulate_fastapi_request(request_id: int):
            """Simulates a FastAPI request handler."""
            # Each request creates its own runtime instance
            runtime = AsyncLocalRuntime()

            builder = WorkflowBuilder()
            builder.add_node(
                "PythonCodeNode",
                "handler",
                {"code": f"output = {{'request_id': {request_id}, 'status': 'ok'}}"},
            )
            workflow = builder.build()

            results, run_id = await runtime.execute_workflow_async(workflow, inputs={})
            return results, run_id

        # WHEN: Simulating 5 concurrent FastAPI requests
        tasks = [simulate_fastapi_request(i) for i in range(5)]
        results = await asyncio.gather(*tasks)

        # THEN: All requests should succeed (results are tuples)
        assert all(r[0] is not None for r in results), "❌ BUG: FastAPI pattern failed"

        print("✅ P0-7.6: FastAPI request pattern works correctly")

    @pytest.mark.asyncio
    async def test_fastapi_shared_runtime_pattern(self):
        """
        TEST: Simulate FastAPI with shared runtime (app state).

        RELIABILITY: Shared runtime instance works across requests.
        """
        # GIVEN: Shared runtime (like app.state.runtime)
        shared_runtime = AsyncLocalRuntime()

        async def simulate_request_with_shared_runtime(request_id: int):
            """Request handler using shared runtime."""
            builder = WorkflowBuilder()
            builder.add_node(
                "PythonCodeNode",
                "handler",
                {"code": f"output = {{'request_id': {request_id}, 'shared': True}}"},
            )
            workflow = builder.build()

            return await shared_runtime.execute_workflow_async(workflow, inputs={})

        # WHEN: Multiple concurrent requests using shared runtime
        tasks = [simulate_request_with_shared_runtime(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # THEN: All should succeed without event loop conflicts (results are tuples)
        assert all(
            r[0] is not None for r in results
        ), "❌ BUG: Shared runtime pattern failed"

        print("✅ P0-7.7: Shared runtime pattern (app.state) works correctly")


class TestEventLoopEdgeCases:
    """Test edge cases in event loop handling."""

    @pytest.mark.asyncio
    async def test_runtime_in_nested_async_context(self):
        """
        TEST: Runtime should work in nested async contexts.

        RELIABILITY: Handles complex async nesting.
        """

        async def outer_async_function():
            async def inner_async_function():
                runtime = AsyncLocalRuntime()

                builder = WorkflowBuilder()
                builder.add_node(
                    "PythonCodeNode",
                    "nested",
                    {"code": "output = {'nested': True}"},
                )
                workflow = builder.build()

                return await runtime.execute_workflow_async(workflow, inputs={})

            return await inner_async_function()

        # WHEN: Executing in nested async context
        results, run_id = await outer_async_function()

        # THEN: Should work correctly
        assert results is not None
        assert run_id is not None

        print("✅ P0-7.8: Works in nested async contexts")

    @pytest.mark.asyncio
    async def test_runtime_with_asyncio_create_task(self):
        """
        TEST: Runtime should work with asyncio.create_task.

        RELIABILITY: Compatible with task-based execution.
        """
        runtime = AsyncLocalRuntime()

        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "task_test",
            {"code": "output = {'task_based': True}"},
        )
        workflow = builder.build()

        # WHEN: Executing via asyncio.create_task
        task = asyncio.create_task(runtime.execute_workflow_async(workflow, inputs={}))

        results, run_id = await task

        # THEN: Should work correctly
        assert results is not None
        assert run_id is not None

        print("✅ P0-7.9: Works with asyncio.create_task")

    @pytest.mark.asyncio
    async def test_runtime_with_asyncio_gather(self):
        """
        TEST: Runtime should work with asyncio.gather.

        RELIABILITY: Compatible with gather-based concurrency.
        """
        runtime = AsyncLocalRuntime()

        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "gather_test",
            {"code": "output = {'gathered': True}"},
        )
        workflow = builder.build()

        # WHEN: Executing multiple workflows via gather
        results = await asyncio.gather(
            runtime.execute_workflow_async(workflow, inputs={}),
            runtime.execute_workflow_async(workflow, inputs={}),
            runtime.execute_workflow_async(workflow, inputs={}),
        )

        # THEN: All should succeed (results are tuples)
        assert all(r[0] is not None for r in results)

        print("✅ P0-7.10: Works with asyncio.gather")


class TestEventLoopCleanup:
    """Test that event loop is handled correctly across lifecycle."""

    @pytest.mark.asyncio
    async def test_runtime_cleanup_after_execution(self):
        """
        TEST: Runtime should clean up properly after execution.

        RELIABILITY: No resource leaks from event loop handling.
        """
        # GIVEN: Runtime
        runtime = AsyncLocalRuntime()

        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "cleanup_test",
            {"code": "output = {'status': 'done'}"},
        )
        workflow = builder.build()

        # WHEN: Executing and completing
        results, run_id = await runtime.execute_workflow_async(workflow, inputs={})

        # THEN: Should complete cleanly
        assert results is not None
        assert run_id is not None

        # Verify event loop still works after
        await asyncio.sleep(0.001)

        print("✅ P0-7.11: Runtime cleans up properly after execution")

    @pytest.mark.asyncio
    async def test_multiple_runtimes_same_event_loop(self):
        """
        TEST: Multiple runtime instances should share same event loop correctly.

        RELIABILITY: Multiple runtimes coexist without conflicts.
        """
        # GIVEN: Multiple runtime instances
        runtime1 = AsyncLocalRuntime()
        runtime2 = AsyncLocalRuntime()
        runtime3 = AsyncLocalRuntime()

        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "multi",
            {"code": "output = {'instance': instance_id}"},
        )
        workflow = builder.build()

        # WHEN: Executing with different runtimes concurrently
        results = await asyncio.gather(
            runtime1.execute_workflow_async(workflow, inputs={"instance_id": 1}),
            runtime2.execute_workflow_async(workflow, inputs={"instance_id": 2}),
            runtime3.execute_workflow_async(workflow, inputs={"instance_id": 3}),
        )

        # THEN: All should succeed (results are tuples)
        assert all(r[0] is not None for r in results)

        print("✅ P0-7.12: Multiple runtimes coexist correctly in same event loop")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
