"""
P0-6: MCP Channel AsyncLocalRuntime - Performance and Reliability Fix

RELIABILITY/PERFORMANCE ISSUES PREVENTED:
- MCP channel uses sync LocalRuntime instead of AsyncLocalRuntime
- Concurrent MCP requests block each other
- Event loop blocked during MCP execution
- Poor performance compared to API channel (10-100x slower)

Tests verify:
1. MCP channel uses AsyncLocalRuntime (not LocalRuntime)
2. Concurrent MCP requests execute in parallel
3. Event loop not blocked during execution
4. Performance improvement vs old sync approach
"""

import asyncio
import time

import pytest
import pytest_asyncio
from kailash.runtime import AsyncLocalRuntime, LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestMCPAsyncRuntime:
    """Test MCP channel uses AsyncLocalRuntime for performance."""

    @pytest_asyncio.fixture
    async def test_workflow(self):
        """Create a workflow that takes noticeable time to execute."""
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "slow_task",
            {
                "code": """
import time
time.sleep(0.1)  # 100ms delay
output = {'status': 'completed', 'duration': 0.1}
                """,
                "imports": ["time"],
            },
        )
        return builder.build()

    # Removed: test_mcp_channel_uses_async_runtime — was a
    # `pytest.mark.skip` stub with no assertions. Per
    # zero-tolerance.md Rule 2, stub tests are BLOCKED. Real coverage
    # of "MCP channel uses AsyncLocalRuntime" comes from
    # test_mcp_channel_runtime_type_verification below when wired to
    # an actual Nexus fixture (see the full-Nexus integration suite).

    @pytest.mark.asyncio
    async def test_async_runtime_executes_concurrently(self, test_workflow):
        """
        TEST: AsyncLocalRuntime should execute multiple workflows concurrently.

        PERFORMANCE: Verifies async runtime performance benefit.
        """
        # GIVEN: AsyncLocalRuntime
        runtime = AsyncLocalRuntime()

        # WHEN: Executing 5 workflows concurrently (each takes 100ms)
        start_time = time.time()

        tasks = [
            runtime.execute_workflow_async(test_workflow, inputs={}) for _ in range(5)
        ]

        results = await asyncio.gather(*tasks)

        elapsed = time.time() - start_time

        # THEN: Should complete in ~100ms (concurrent) not ~500ms (sequential)
        # Allow some overhead: should be < 300ms (well below sequential 500ms)
        assert elapsed < 0.3, (
            f"❌ PERFORMANCE BUG: 5 concurrent 100ms tasks took {elapsed:.3f}s "
            f"(expected <0.3s, sequential would be ~0.5s)"
        )

        # All should succeed
        assert all(
            r["success"] for r in results
        ), "❌ BUG: Some concurrent executions failed"

        print(
            f"✅ P0-6.2: AsyncLocalRuntime executes concurrently "
            f"(5×100ms tasks in {elapsed:.3f}s)"
        )

    @pytest.mark.asyncio
    async def test_sync_runtime_executes_sequentially(self, test_workflow):
        """
        TEST: LocalRuntime executes sequentially (baseline comparison).

        PERFORMANCE: Demonstrates why async runtime is needed for MCP.
        """
        # GIVEN: LocalRuntime (sync)
        runtime = LocalRuntime()

        # WHEN: Executing 5 workflows sequentially
        start_time = time.time()

        results = []
        for _ in range(5):
            result, _ = runtime.execute(test_workflow)
            results.append(result)

        elapsed = time.time() - start_time

        # THEN: Should take ~500ms (sequential: 5 × 100ms)
        assert (
            elapsed >= 0.4
        ), f"⚠️  Sequential execution unexpectedly fast: {elapsed:.3f}s"

        assert (
            elapsed < 0.8
        ), f"⚠️  Sequential execution too slow: {elapsed:.3f}s (expected ~0.5s)"

        print(
            f"✅ P0-6.3: LocalRuntime executes sequentially "
            f"(5×100ms tasks in {elapsed:.3f}s - baseline)"
        )

    # Removed: test_concurrent_mcp_requests_dont_block — was a
    # `pytest.mark.skip` stub. No MCP requests are actually sent,
    # just a print(). BLOCKED per zero-tolerance.md Rule 2.

    @pytest.mark.asyncio
    async def test_event_loop_not_blocked_during_async_execution(self, test_workflow):
        """
        TEST: Event loop should remain responsive during async execution.

        RELIABILITY: Ensures non-blocking behavior.
        """
        # GIVEN: AsyncLocalRuntime
        runtime = AsyncLocalRuntime()

        # WHEN: Starting workflow execution
        execution_task = asyncio.create_task(
            runtime.execute_workflow_async(test_workflow, inputs={})
        )

        # AND: Performing other async operations concurrently
        async def other_async_work():
            """Simulates other event loop work."""
            await asyncio.sleep(0.05)
            return "other work completed"

        other_task = asyncio.create_task(other_async_work())

        # THEN: Both should complete successfully
        results = await asyncio.gather(execution_task, other_task)

        assert results[0]["success"] is True, "❌ Workflow execution failed"
        assert results[1] == "other work completed", "❌ Other async work blocked"

        print("✅ P0-6.5: Event loop remains responsive during async execution")


class TestAsyncRuntimePerformance:
    """Test AsyncLocalRuntime performance characteristics."""

    @pytest_asyncio.fixture
    async def fast_workflow(self):
        """Create a fast-executing workflow."""
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "fast",
            {"code": "output = {'result': 'fast'}"},
        )
        return builder.build()

    @pytest.mark.asyncio
    async def test_async_runtime_overhead_minimal(self, fast_workflow):
        """
        TEST: AsyncLocalRuntime should have minimal overhead.

        PERFORMANCE: Async runtime shouldn't be significantly slower for single tasks.
        """
        # GIVEN: AsyncLocalRuntime
        runtime = AsyncLocalRuntime()

        # WHEN: Executing simple workflow 100 times
        start_time = time.time()

        for _ in range(100):
            result = await runtime.execute_workflow_async(fast_workflow, inputs={})
            assert result["success"]

        elapsed = time.time() - start_time

        # THEN: Should complete quickly (< 1 second for 100 simple executions)
        assert elapsed < 1.0, (
            f"❌ PERFORMANCE BUG: 100 simple executions took {elapsed:.3f}s "
            f"(expected <1.0s)"
        )

        avg_time = elapsed / 100 * 1000  # Convert to ms
        print(
            f"✅ P0-6.6: AsyncLocalRuntime low overhead "
            f"({avg_time:.2f}ms per execution)"
        )

    @pytest.mark.asyncio
    async def test_async_runtime_scales_with_concurrency(self, fast_workflow):
        """
        TEST: AsyncLocalRuntime should scale with concurrent load.

        PERFORMANCE: More concurrency shouldn't cause linear slowdown.
        """
        runtime = AsyncLocalRuntime()

        # Test different concurrency levels
        concurrency_levels = [1, 5, 10, 20]
        timings = []

        for concurrency in concurrency_levels:
            start = time.time()

            tasks = [
                runtime.execute_workflow_async(fast_workflow, inputs={})
                for _ in range(concurrency)
            ]
            results = await asyncio.gather(*tasks)

            elapsed = time.time() - start
            timings.append((concurrency, elapsed))

            assert all(r["success"] for r in results)

        # Print scaling behavior
        print("✅ P0-6.7: AsyncLocalRuntime concurrency scaling:")
        for concurrency, elapsed in timings:
            print(f"  - {concurrency:2d} concurrent: {elapsed * 1000:.2f}ms")

        # Should not scale linearly (that would indicate blocking)
        # E.g., 20 concurrent shouldn't take 20x longer than 1
        ratio = timings[-1][1] / timings[0][1]
        assert ratio < 10, (
            f"❌ SCALING BUG: 20x concurrency caused {ratio:.1f}x slowdown "
            f"(expected <10x due to async execution)"
        )


class TestAsyncRuntimeCorrectness:
    """Test AsyncLocalRuntime executes workflows correctly."""

    @pytest_asyncio.fixture
    async def multi_node_workflow(self):
        """Create a workflow with multiple nodes."""
        builder = WorkflowBuilder()

        # Node 1: Generate data
        builder.add_node(
            "PythonCodeNode",
            "generate",
            {"code": "output = {'numbers': [1, 2, 3, 4, 5]}"},
        )

        # Node 2: Process data
        builder.add_node(
            "PythonCodeNode",
            "process",
            {"code": "output = {'sum': sum(inputs['numbers'])}"},
        )

        # Connect nodes
        builder.add_connection("generate", "numbers", "process", "numbers")

        return builder.build()

    @pytest.mark.asyncio
    async def test_async_runtime_executes_workflow_correctly(self, multi_node_workflow):
        """
        TEST: AsyncLocalRuntime should execute multi-node workflows correctly.

        RELIABILITY: Async execution doesn't break workflow logic.
        """
        # GIVEN: AsyncLocalRuntime
        runtime = AsyncLocalRuntime()

        # WHEN: Executing multi-node workflow
        result = await runtime.execute_workflow_async(multi_node_workflow, inputs={})

        # THEN: Should execute correctly
        assert result["success"] is True, f"❌ Execution failed: {result.get('error')}"

        # Verify results
        assert "process" in result["results"]
        assert (
            result["results"]["process"]["sum"] == 15
        ), f"❌ Wrong result: {result['results']['process']}"

        print("✅ P0-6.8: AsyncLocalRuntime executes multi-node workflows correctly")

    @pytest.mark.asyncio
    async def test_async_runtime_handles_errors_gracefully(self):
        """
        TEST: AsyncLocalRuntime should handle workflow errors gracefully.

        RELIABILITY: Error handling works correctly in async context.
        """
        # GIVEN: Workflow that raises error
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "error_node",
            {"code": "raise ValueError('Test error')"},
        )
        error_workflow = builder.build()

        runtime = AsyncLocalRuntime()

        # WHEN: Executing error workflow
        result = await runtime.execute_workflow_async(error_workflow, inputs={})

        # THEN: Should report error gracefully (not crash)
        assert result["success"] is False, "❌ Error not caught"
        assert "error" in result or "error" in result.get("results", {}).get(
            "error_node", {}
        ), "❌ Error not reported in result"

        print("✅ P0-6.9: AsyncLocalRuntime handles errors gracefully")


class TestMCPChannelIntegration:
    """Test MCP channel integration with AsyncLocalRuntime."""

    @pytest.mark.asyncio
    async def test_mcp_channel_runtime_type_verification(self):
        """
        TEST: Verify MCP channel actually uses AsyncLocalRuntime.

        CRITICAL: Direct verification of the fix. Skip only when the
        ``nexus`` package is not installed in the current environment
        (genuine "cannot execute" gate per test-skip-discipline).
        """
        # GIVEN: Nexus with MCP channel (requires the optional `nexus` pkg)
        nexus_module = pytest.importorskip("nexus", reason="requires `nexus` package")
        nexus = nexus_module.Nexus(
            enable_http_transport=True, auto_discovery=False, enable_durability=False
        )

        # WHEN: MCP channel is wired on this Nexus build
        mcp_channel = getattr(nexus, "_mcp_channel", None)
        if mcp_channel is None:
            pytest.skip(
                "Nexus build does not expose `_mcp_channel` — "
                "MCP transport not enabled in this environment"
            )

        runtime = getattr(mcp_channel, "runtime", None)

        # THEN: Runtime MUST be AsyncLocalRuntime. A mismatch is the exact
        # bug this Tier 2 test exists to catch — never skip-around it.
        assert isinstance(
            runtime, AsyncLocalRuntime
        ), f"MCP channel uses {type(runtime).__name__}, expected AsyncLocalRuntime"

    # Removed: test_mcp_performance_vs_api_channel — was a
    # `pytest.mark.skip` stub. The function performed no MCP vs API
    # comparison; it only printed a placeholder. BLOCKED per
    # zero-tolerance.md Rule 2. A real perf comparison belongs in
    # packages/kailash-nexus/tests/performance/ with both channels
    # stood up against a shared workflow fixture.


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
