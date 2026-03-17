"""Integration tests for workflow cancellation (TODO-031).

Tests verify that:
- A running workflow can be cancelled between node executions
- CancellationToken correctly stops execution with WorkflowCancelledError
- Completed nodes are reported in the error
- DurableRequest.cancel() signals the runtime via the token
- Force-cancel timeout kills a stuck workflow
"""

import asyncio
import threading
import time

import pytest

from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.cancellation import CancellationToken
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import WorkflowCancelledError
from kailash.workflow.builder import WorkflowBuilder


def _build_slow_workflow(node_count: int = 10, sleep_seconds: float = 0.05):
    """Build a workflow with N nodes that each sleep for a short duration.

    Each node writes its index to a shared list via PythonCodeNode code,
    making it easy to verify how many completed before cancellation.

    Args:
        node_count: Number of sequential slow nodes.
        sleep_seconds: How long each node sleeps.

    Returns:
        Built Workflow instance.
    """
    builder = WorkflowBuilder()

    prev_id = None
    for i in range(node_count):
        node_id = f"slow_{i}"
        code = (
            f"import time\n"
            f"time.sleep({sleep_seconds})\n"
            f"result = {{'node_index': {i}, 'completed': True}}"
        )
        node = PythonCodeNode(name=f"slow_node_{i}", code=code)
        builder.add_node(node, node_id, {})
        if prev_id is not None:
            builder.add_connection(prev_id, "result", node_id, "data")
        prev_id = node_id

    return builder.build()


class TestCancellationToken:
    """Unit-level tests for the CancellationToken itself."""

    def test_initial_state_not_cancelled(self):
        token = CancellationToken()
        assert not token.is_cancelled
        assert token.reason is None
        assert token.cancelled_at is None

    def test_cancel_sets_state(self):
        token = CancellationToken()
        token.cancel(reason="test reason")
        assert token.is_cancelled
        assert token.reason == "test reason"
        assert token.cancelled_at is not None

    def test_cancel_is_idempotent(self):
        token = CancellationToken()
        token.cancel(reason="first")
        token.cancel(reason="second")
        assert token.reason == "first"

    def test_check_raises_when_cancelled(self):
        token = CancellationToken()
        token.cancel(reason="stop")
        with pytest.raises(WorkflowCancelledError, match="stop"):
            token.check()

    def test_check_does_not_raise_when_not_cancelled(self):
        token = CancellationToken()
        token.check()  # Should not raise

    def test_reset(self):
        token = CancellationToken()
        token.cancel(reason="stop")
        assert token.is_cancelled
        token.reset()
        assert not token.is_cancelled
        assert token.reason is None

    def test_wait_returns_true_when_cancelled(self):
        token = CancellationToken()
        token.cancel()
        assert token.wait(timeout=0.01) is True

    def test_wait_returns_false_on_timeout(self):
        token = CancellationToken()
        assert token.wait(timeout=0.01) is False

    def test_thread_safety(self):
        """Cancel from another thread while main thread checks."""
        token = CancellationToken()
        results = []

        def cancel_after_delay():
            time.sleep(0.05)
            token.cancel(reason="from thread")

        t = threading.Thread(target=cancel_after_delay)
        t.start()
        # Poll until cancelled or timeout
        for _ in range(100):
            if token.is_cancelled:
                results.append("cancelled")
                break
            time.sleep(0.01)
        t.join()
        assert "cancelled" in results


class TestWorkflowCancellation:
    """Integration tests for runtime cancellation via CancellationToken."""

    def test_cancel_stops_workflow_between_nodes(self):
        """Start a 10-node workflow, cancel after ~3 complete, verify it stops."""
        token = CancellationToken()
        workflow = _build_slow_workflow(node_count=10, sleep_seconds=0.05)

        def cancel_after_delay():
            # Wait enough time for ~3 nodes to complete (3 * 50ms = 150ms)
            # Add a small buffer for overhead
            time.sleep(0.18)
            token.cancel(reason="User requested stop")

        cancel_thread = threading.Thread(target=cancel_after_delay)
        cancel_thread.start()

        with pytest.raises(WorkflowCancelledError) as exc_info:
            with LocalRuntime(enable_monitoring=False) as runtime:
                runtime.execute(workflow, cancellation_token=token)

        cancel_thread.join()

        err = exc_info.value
        # At least 1 node should have completed, but not all 10
        assert len(err.completed_nodes) >= 1
        assert len(err.completed_nodes) < 10
        assert err.cancelled_at_node is not None
        assert "User requested stop" in str(err)

    def test_cancel_before_execution_starts(self):
        """If token is already cancelled, execution should fail immediately."""
        token = CancellationToken()
        token.cancel(reason="Pre-cancelled")

        workflow = _build_slow_workflow(node_count=3, sleep_seconds=0.01)

        with pytest.raises(WorkflowCancelledError) as exc_info:
            with LocalRuntime(enable_monitoring=False) as runtime:
                runtime.execute(workflow, cancellation_token=token)

        err = exc_info.value
        # No nodes should have completed
        assert len(err.completed_nodes) == 0
        assert err.cancelled_at_node is not None
        assert "Pre-cancelled" in str(err)

    def test_no_token_runs_normally(self):
        """Without a cancellation token, workflow runs to completion."""
        workflow = _build_slow_workflow(node_count=3, sleep_seconds=0.01)

        with LocalRuntime(enable_monitoring=False) as runtime:
            results, run_id = runtime.execute(workflow)

        assert "slow_0" in results
        assert "slow_1" in results
        assert "slow_2" in results

    def test_cancelled_state_persisted_correctly(self):
        """Verify the WorkflowCancelledError carries correct metadata."""
        token = CancellationToken()

        # Build a 5-node workflow with longer sleeps
        workflow = _build_slow_workflow(node_count=5, sleep_seconds=0.1)

        def cancel_after_two():
            # Wait for ~2 nodes (2 * 100ms = 200ms + overhead)
            time.sleep(0.25)
            token.cancel(reason="Timeout exceeded")

        t = threading.Thread(target=cancel_after_two)
        t.start()

        with pytest.raises(WorkflowCancelledError) as exc_info:
            with LocalRuntime(enable_monitoring=False) as runtime:
                runtime.execute(workflow, cancellation_token=token)

        t.join()

        err = exc_info.value
        # Verify completed_nodes are real node IDs
        for node_id in err.completed_nodes:
            assert node_id.startswith("slow_")
        # Verify cancelled_at_node is the next node after completed ones
        assert err.cancelled_at_node is not None
        # The cancelled node index should be len(completed_nodes)
        expected_index = len(err.completed_nodes)
        assert err.cancelled_at_node == f"slow_{expected_index}"


class TestWorkflowCancelledError:
    """Tests for the WorkflowCancelledError exception class."""

    def test_default_message(self):
        err = WorkflowCancelledError()
        assert "cancelled" in str(err).lower()
        assert err.completed_nodes == []
        assert err.cancelled_at_node is None

    def test_custom_message_and_metadata(self):
        err = WorkflowCancelledError(
            message="Custom cancel",
            completed_nodes=["a", "b", "c"],
            cancelled_at_node="d",
        )
        assert str(err) == "Custom cancel"
        assert err.completed_nodes == ["a", "b", "c"]
        assert err.cancelled_at_node == "d"

    def test_inherits_from_workflow_execution_error(self):
        from kailash.sdk_exceptions import WorkflowExecutionError

        err = WorkflowCancelledError()
        assert isinstance(err, WorkflowExecutionError)


class TestDurableRequestCancellation:
    """Tests for DurableRequest.cancel() integration."""

    @pytest.mark.asyncio
    async def test_cancel_sets_token_and_state(self):
        """DurableRequest.cancel() should set the cancellation token."""
        from kailash.middleware.gateway.durable_request import (
            DurableRequest,
            RequestState,
        )

        req = DurableRequest()
        assert not req._cancellation_token.is_cancelled
        assert req.state == RequestState.INITIALIZED

        await req.cancel(reason="Test cancel")

        assert req._cancellation_token.is_cancelled
        assert req._cancellation_token.reason == "Test cancel"
        assert req.state == RequestState.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_records_journal_entry(self):
        """DurableRequest.cancel() should write to the execution journal."""
        from kailash.middleware.gateway.durable_request import DurableRequest

        req = DurableRequest()
        await req.cancel(reason="Journal test")

        cancel_events = req.journal.get_events("request_cancelled")
        assert len(cancel_events) == 1
        assert cancel_events[0]["data"]["reason"] == "Journal test"

    @pytest.mark.asyncio
    async def test_cancel_event_is_set(self):
        """DurableRequest.cancel() should set the asyncio cancel event."""
        from kailash.middleware.gateway.durable_request import DurableRequest

        req = DurableRequest()
        assert not req._cancel_event.is_set()
        await req.cancel()
        assert req._cancel_event.is_set()

    @pytest.mark.asyncio
    async def test_force_cancel_after_timeout(self):
        """If execution task doesn't stop within timeout, force-cancel it."""
        from kailash.middleware.gateway.durable_request import DurableRequest

        req = DurableRequest()

        # Create a fake long-running task
        async def long_running():
            await asyncio.sleep(100)  # Simulate a stuck task

        req._execution_task = asyncio.create_task(long_running())
        req.workflow = True  # Truthy to enter the cancellation branch
        req.runtime = True  # Truthy to enter the cancellation branch

        # Cancel with a very short timeout to trigger force-cancel
        await req.cancel(reason="Force cancel test", timeout=0.1)

        # The task should be done (force-cancelled)
        assert req._execution_task.done()
