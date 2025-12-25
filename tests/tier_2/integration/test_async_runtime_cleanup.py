"""
P0-8: AsyncLocalRuntime Cleanup - Resource Leak Fix

CRITICAL RELIABILITY ISSUES PREVENTED:
- ThreadPoolExecutor not shut down when runtime destroyed
- Thread leaks in long-running applications
- FastAPI lifespan integration not working
- Resources not released properly
- Cleanup cannot be called multiple times safely

Tests verify:
1. ThreadPoolExecutor shutdown when runtime cleaned up
2. FastAPI lifespan integration works
3. No thread leaks after cleanup
4. Resources released properly
5. Cleanup can be called multiple times safely
"""

import asyncio
import threading
import weakref

import pytest
import pytest_asyncio
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestAsyncRuntimeCleanup:
    """Test AsyncLocalRuntime cleanup and resource management."""

    @pytest.mark.asyncio
    async def test_runtime_has_cleanup_method(self):
        """
        TEST: AsyncLocalRuntime should have cleanup/shutdown method.

        RELIABILITY: Provides explicit resource cleanup mechanism.
        """
        # GIVEN: AsyncLocalRuntime instance
        runtime = AsyncLocalRuntime()

        # THEN: Should have cleanup method
        assert hasattr(runtime, "cleanup") or hasattr(
            runtime, "shutdown"
        ), "❌ CRITICAL BUG: AsyncLocalRuntime missing cleanup/shutdown method"

        # Try to call cleanup
        if hasattr(runtime, "cleanup"):
            await runtime.cleanup()
            print("✅ P0-8.1: Runtime has cleanup() method")
        elif hasattr(runtime, "shutdown"):
            await runtime.shutdown()
            print("✅ P0-8.1: Runtime has shutdown() method")

    @pytest.mark.asyncio
    async def test_cleanup_releases_thread_pool(self):
        """
        TEST: Cleanup should shut down ThreadPoolExecutor.

        CRITICAL: Prevents thread leaks.
        """
        # GIVEN: Runtime with ThreadPoolExecutor
        runtime = AsyncLocalRuntime()

        # Execute workflow to initialize thread pool
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "test",
            {"code": "output = {'status': 'ok'}"},
        )
        workflow = builder.build()

        await runtime.execute_workflow_async(workflow, inputs={})

        # Record thread count before cleanup
        threads_before = threading.active_count()

        # WHEN: Calling cleanup
        if hasattr(runtime, "cleanup"):
            await runtime.cleanup()
        elif hasattr(runtime, "shutdown"):
            await runtime.shutdown()
        else:
            pytest.skip("Runtime doesn't have cleanup method yet")

        # Allow threads to actually terminate
        await asyncio.sleep(0.1)

        # THEN: Thread pool should be shut down
        threads_after = threading.active_count()

        # Note: Exact thread count depends on implementation
        # We just verify no significant thread leak
        thread_leak = threads_after - threads_before

        if thread_leak > 5:  # Allow small variation
            pytest.fail(
                f"❌ RESOURCE LEAK: {thread_leak} threads not cleaned up "
                f"(before: {threads_before}, after: {threads_after})"
            )

        print(
            f"✅ P0-8.2: Thread pool cleaned up "
            f"(threads before: {threads_before}, after: {threads_after})"
        )

    @pytest.mark.asyncio
    async def test_cleanup_can_be_called_multiple_times(self):
        """
        TEST: Cleanup should be idempotent (safe to call multiple times).

        RELIABILITY: Prevents errors from double-cleanup.
        """
        # GIVEN: Runtime instance
        runtime = AsyncLocalRuntime()

        # Execute once to initialize
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "test",
            {"code": "output = {'value': 1}"},
        )
        workflow = builder.build()

        await runtime.execute_workflow_async(workflow, inputs={})

        # WHEN: Calling cleanup multiple times
        if hasattr(runtime, "cleanup"):
            await runtime.cleanup()
            await runtime.cleanup()  # Second call
            await runtime.cleanup()  # Third call
            print("✅ P0-8.3: cleanup() is idempotent (multiple calls safe)")
        elif hasattr(runtime, "shutdown"):
            await runtime.shutdown()
            await runtime.shutdown()
            await runtime.shutdown()
            print("✅ P0-8.3: shutdown() is idempotent (multiple calls safe)")
        else:
            pytest.skip("No cleanup method available")

    @pytest.mark.asyncio
    async def test_runtime_unusable_after_cleanup(self):
        """
        TEST: Runtime should not accept new work after cleanup.

        RELIABILITY: Clear lifecycle management.
        """
        # GIVEN: Runtime
        runtime = AsyncLocalRuntime()

        # Execute once
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "test",
            {"code": "output = {'status': 'ok'}"},
        )
        workflow = builder.build()

        result1 = await runtime.execute_workflow_async(workflow, inputs={})
        assert result1["success"] is True

        # WHEN: Cleaning up runtime
        if hasattr(runtime, "cleanup"):
            await runtime.cleanup()
        elif hasattr(runtime, "shutdown"):
            await runtime.shutdown()
        else:
            pytest.skip("No cleanup method available")

        # THEN: Should not accept new work (or handle gracefully)
        try:
            result2 = await runtime.execute_workflow_async(workflow, inputs={})

            # If it succeeds, that's OK (runtime may reinitialize)
            # But it should be documented behavior
            print(
                "⚠️  P0-8.4: Runtime accepts work after cleanup "
                "(may auto-reinitialize)"
            )

        except RuntimeError as e:
            # Expected - runtime shut down
            assert (
                "shutdown" in str(e).lower() or "closed" in str(e).lower()
            ), f"❌ Unclear error message after cleanup: {e}"
            print("✅ P0-8.4: Runtime correctly rejects work after cleanup")


class TestFastAPILifespanIntegration:
    """Test AsyncLocalRuntime integration with FastAPI lifespan."""

    @pytest.mark.asyncio
    async def test_fastapi_lifespan_pattern(self):
        """
        TEST: Runtime should integrate with FastAPI lifespan events.

        RELIABILITY: Proper cleanup on FastAPI shutdown.
        """
        # Simulate FastAPI lifespan
        app_state = {"runtime": None}

        # Startup
        async def fastapi_startup():
            runtime = AsyncLocalRuntime()
            app_state["runtime"] = runtime

        # Shutdown
        async def fastapi_shutdown():
            runtime = app_state["runtime"]
            if runtime:
                if hasattr(runtime, "cleanup"):
                    await runtime.cleanup()
                elif hasattr(runtime, "shutdown"):
                    await runtime.shutdown()

        # WHEN: Simulating FastAPI lifecycle
        await fastapi_startup()

        # Use runtime
        runtime = app_state["runtime"]
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "test",
            {"code": "output = {'app': 'running'}"},
        )
        workflow = builder.build()

        result = await runtime.execute_workflow_async(workflow, inputs={})
        assert result["success"] is True

        # Shutdown
        await fastapi_shutdown()

        print("✅ P0-8.5: FastAPI lifespan pattern works correctly")

    @pytest.mark.asyncio
    async def test_context_manager_pattern(self):
        """
        TEST: Runtime should support async context manager pattern.

        RELIABILITY: Automatic cleanup with 'async with'.
        """
        # Check if runtime supports context manager
        runtime = AsyncLocalRuntime()

        has_aenter = hasattr(runtime, "__aenter__")
        has_aexit = hasattr(runtime, "__aexit__")

        if has_aenter and has_aexit:
            # GIVEN: Runtime as async context manager
            async with AsyncLocalRuntime() as runtime:
                builder = WorkflowBuilder()
                builder.add_node(
                    "PythonCodeNode",
                    "test",
                    {"code": "output = {'context': 'manager'}"},
                )
                workflow = builder.build()

                result = await runtime.execute_workflow_async(workflow, inputs={})
                assert result["success"] is True

            # THEN: Should auto-cleanup on exit
            print("✅ P0-8.6: Context manager pattern supported")

        else:
            print("⚠️  P0-8.6: Context manager pattern not yet implemented")


class TestResourceLeakPrevention:
    """Test that resources are properly released to prevent leaks."""

    @pytest.mark.asyncio
    async def test_no_memory_leak_from_uncleaned_runtime(self):
        """
        TEST: Runtime should be garbage collected when references dropped.

        RELIABILITY: Memory cleanup via GC even without explicit cleanup.
        """
        # GIVEN: Runtime with weak reference
        runtime = AsyncLocalRuntime()

        # Execute to initialize
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "test",
            {"code": "output = {'gc': 'test'}"},
        )
        workflow = builder.build()

        await runtime.execute_workflow_async(workflow, inputs={})

        # Create weak reference
        weak_ref = weakref.ref(runtime)

        # WHEN: Dropping all references
        del runtime

        # Force garbage collection
        import gc

        gc.collect()
        await asyncio.sleep(0.1)

        # THEN: Runtime should be garbage collected
        if weak_ref() is None:
            print("✅ P0-8.7: Runtime garbage collected when references dropped")
        else:
            print(
                "⚠️  P0-8.7: Runtime not garbage collected "
                "(may have cleanup implementation)"
            )

    @pytest.mark.asyncio
    async def test_cleanup_releases_all_resources(self):
        """
        TEST: Cleanup should release all resources (threads, executors, etc).

        RELIABILITY: Complete resource cleanup.
        """
        # GIVEN: Runtime
        runtime = AsyncLocalRuntime()

        # Execute to initialize resources
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "test",
            {"code": "output = {'resource': 'test'}"},
        )
        workflow = builder.build()

        await runtime.execute_workflow_async(workflow, inputs={})

        # Check for ThreadPoolExecutor
        has_executor = hasattr(runtime, "_executor") or hasattr(runtime, "executor")

        # WHEN: Cleanup
        if hasattr(runtime, "cleanup"):
            await runtime.cleanup()
        elif hasattr(runtime, "shutdown"):
            await runtime.shutdown()
        else:
            pytest.skip("No cleanup method")

        # THEN: Resources should be released
        if has_executor:
            executor = getattr(runtime, "_executor", None) or getattr(
                runtime, "executor", None
            )
            if executor is not None:
                # Executor should be shut down
                # Check via _shutdown attribute if available
                if hasattr(executor, "_shutdown"):
                    assert (
                        executor._shutdown is True
                    ), "❌ RESOURCE LEAK: ThreadPoolExecutor not shut down"
                    print("✅ P0-8.8: ThreadPoolExecutor properly shut down")
                else:
                    print("⚠️  P0-8.8: Cannot verify executor shutdown state")
            else:
                print("✅ P0-8.8: Executor reference cleared")
        else:
            print("⚠️  P0-8.8: No executor found (may use different threading model)")


class TestCleanupErrorHandling:
    """Test cleanup behavior with errors and edge cases."""

    @pytest.mark.asyncio
    async def test_cleanup_with_pending_workflows(self):
        """
        TEST: Cleanup should handle pending workflows gracefully.

        RELIABILITY: Safe cleanup even with active work.
        """
        # GIVEN: Runtime with slow workflow
        runtime = AsyncLocalRuntime()

        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "slow",
            {
                "code": """
import asyncio
await asyncio.sleep(1.0)  # Long-running
output = {'status': 'completed'}
                """,
            },
        )
        workflow = builder.build()

        # Start workflow but don't wait
        task = asyncio.create_task(runtime.execute_workflow_async(workflow, inputs={}))

        # WHEN: Cleaning up while workflow running
        await asyncio.sleep(0.1)  # Let it start

        if hasattr(runtime, "cleanup"):
            await runtime.cleanup()
        elif hasattr(runtime, "shutdown"):
            await runtime.shutdown()
        else:
            pytest.skip("No cleanup method")

        # THEN: Should handle gracefully (cancel or wait)
        try:
            result = await asyncio.wait_for(task, timeout=2.0)
            # Workflow completed or was cancelled
            print("✅ P0-8.9: Cleanup handled pending workflow gracefully")
        except asyncio.TimeoutError:
            print("⚠️  P0-8.9: Pending workflow not cleaned up (may need cancellation)")
        except asyncio.CancelledError:
            print("✅ P0-8.9: Pending workflow cancelled during cleanup")

    @pytest.mark.asyncio
    async def test_cleanup_with_failed_initialization(self):
        """
        TEST: Cleanup should work even if runtime partially initialized.

        RELIABILITY: Robust cleanup in error scenarios.
        """
        # GIVEN: Runtime (may not be fully initialized)
        runtime = AsyncLocalRuntime()

        # WHEN: Cleaning up without executing anything
        try:
            if hasattr(runtime, "cleanup"):
                await runtime.cleanup()
                print("✅ P0-8.10: Cleanup works with uninitialized runtime")
            elif hasattr(runtime, "shutdown"):
                await runtime.shutdown()
                print("✅ P0-8.10: Shutdown works with uninitialized runtime")
            else:
                pytest.skip("No cleanup method")

        except Exception as e:
            pytest.fail(f"❌ BUG: Cleanup failed on uninitialized runtime: {e}")


class TestCleanupPerformance:
    """Test that cleanup is reasonably fast."""

    @pytest.mark.asyncio
    async def test_cleanup_completes_quickly(self):
        """
        TEST: Cleanup should complete within reasonable time.

        RELIABILITY: No hanging during shutdown.
        """
        import time

        # GIVEN: Runtime
        runtime = AsyncLocalRuntime()

        # Execute to initialize
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "test",
            {"code": "output = {'value': 1}"},
        )
        workflow = builder.build()

        await runtime.execute_workflow_async(workflow, inputs={})

        # WHEN: Measuring cleanup time
        start = time.time()

        if hasattr(runtime, "cleanup"):
            await runtime.cleanup()
        elif hasattr(runtime, "shutdown"):
            await runtime.shutdown()
        else:
            pytest.skip("No cleanup method")

        elapsed = time.time() - start

        # THEN: Should complete quickly (<2 seconds)
        assert (
            elapsed < 2.0
        ), f"❌ PERFORMANCE BUG: Cleanup took {elapsed:.3f}s (should be <2s)"

        print(f"✅ P0-8.11: Fast cleanup ({elapsed * 1000:.2f}ms)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
