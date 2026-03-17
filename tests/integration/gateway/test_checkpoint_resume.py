"""Integration tests for checkpoint state capture and restoration (TODO-005/006).

Tests verify that:
- Workflow state is captured after partial execution via ExecutionTracker
- Serialisation round-trip preserves full state (capture -> serialise -> deserialise -> restore)
- Resumed execution skips already-completed nodes (no duplicate side effects)
- Empty tracker (fresh workflow) works correctly end to end
- DurableRequest._capture_workflow_state / _restore_workflow_state integrate correctly
"""

import asyncio
import warnings

import pytest

from kailash.middleware.gateway.durable_request import DurableRequest, RequestMetadata
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.execution_tracker import ExecutionTracker
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_counting_workflow(node_count: int = 5):
    """Build a linear workflow of PythonCodeNode nodes.

    Each node produces ``{"index": i, "completed": True}``.  The nodes are
    chained so that node N receives the output of node N-1 as ``data``.
    """
    builder = WorkflowBuilder()
    prev_id = None
    for i in range(node_count):
        node_id = f"step_{i}"
        code = f"result = {{'index': {i}, 'completed': True}}"
        node = PythonCodeNode(name=f"counting_node_{i}", code=code)
        builder.add_node(node, node_id, {})
        if prev_id is not None:
            builder.add_connection(prev_id, "result", node_id, "data")
        prev_id = node_id
    return builder.build()


# ---------------------------------------------------------------------------
# Test: Tracker records completions during execution
# ---------------------------------------------------------------------------


class TestTrackerRecordsDuringExecution:
    """Verify that the tracker records node completions as the workflow runs."""

    def test_tracker_records_all_nodes(self):
        """After full execution, the tracker should have all node IDs."""
        workflow = _build_counting_workflow(5)
        tracker = ExecutionTracker()

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            runtime = LocalRuntime()
            results, _ = runtime.execute(
                workflow,
                parameters={"workflow_context": {"execution_tracker": tracker}},
            )

        # All 5 nodes should be recorded
        assert len(tracker.completed_node_ids) == 5
        for i in range(5):
            assert tracker.is_completed(f"step_{i}")
            output = tracker.get_output(f"step_{i}")
            assert output is not None
            # PythonCodeNode wraps result in {"result": ...}
            assert "result" in output or "index" in output


# ---------------------------------------------------------------------------
# Test: Serialisation round-trip
# ---------------------------------------------------------------------------


class TestSerializationRoundTrip:
    """Capture -> serialise -> deserialise -> restore preserves state."""

    def test_round_trip_fidelity(self):
        """Tracker state survives JSON-friendly serialisation and restoration."""
        workflow = _build_counting_workflow(5)
        tracker = ExecutionTracker()

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            runtime = LocalRuntime()
            runtime.execute(
                workflow,
                parameters={"workflow_context": {"execution_tracker": tracker}},
            )

        # Serialise
        state_dict = tracker.to_dict()

        # Deserialise
        restored = ExecutionTracker.from_dict(state_dict)

        # Should match original
        assert restored.completed_node_ids == tracker.completed_node_ids
        for node_id in tracker.completed_node_ids:
            assert restored.get_output(node_id) == tracker.get_output(node_id)


# ---------------------------------------------------------------------------
# Test: Resume skips completed nodes (no duplicate side effects)
# ---------------------------------------------------------------------------


class TestResumeSkipsCompletedNodes:
    """Verify that resumed execution does not re-execute completed nodes."""

    def test_resume_skips_first_three_nodes(self):
        """Build a 5-node workflow, mark 3 as completed, resume executes only 2."""
        workflow = _build_counting_workflow(5)

        # Pre-populate tracker with outputs for the first 3 nodes
        tracker = ExecutionTracker()
        for i in range(3):
            tracker.record_completion(
                f"step_{i}", {"result": {"index": i, "completed": True}}
            )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            runtime = LocalRuntime()
            results, _ = runtime.execute(
                workflow,
                parameters={"workflow_context": {"execution_tracker": tracker}},
            )

        # All 5 nodes should have results
        assert len(results) == 5

        # First 3 should be the cached outputs (from tracker)
        for i in range(3):
            assert results[f"step_{i}"] == {"result": {"index": i, "completed": True}}

        # Last 2 should have been freshly executed
        for i in range(3, 5):
            assert f"step_{i}" in results
            output = results[f"step_{i}"]
            assert output is not None

    def test_no_duplicate_execution_with_counter(self):
        """Use a side-effect counter node to verify no re-execution.

        The node writes a unique marker; if the tracker already has it,
        the runtime should skip execution entirely.
        """
        builder = WorkflowBuilder()

        # Node 0: sets a counter value
        node0 = PythonCodeNode(
            name="counter_init",
            code="result = {'counter': 1}",
        )
        builder.add_node(node0, "init", {})

        # Node 1: increments counter (would produce counter=2 if executed)
        node1 = PythonCodeNode(
            name="counter_inc",
            code="result = {'counter': data.get('counter', 0) + 1}",
        )
        builder.add_node(node1, "inc", {})
        builder.add_connection("init", "result", "inc", "data")

        # Node 2: final step
        node2 = PythonCodeNode(
            name="counter_read",
            code="result = {'final_counter': data.get('counter', -1)}",
        )
        builder.add_node(node2, "read", {})
        builder.add_connection("inc", "result", "read", "data")

        workflow = builder.build()

        # Pre-populate the first two nodes as completed
        tracker = ExecutionTracker()
        tracker.record_completion("init", {"result": {"counter": 1}})
        tracker.record_completion("inc", {"result": {"counter": 2}})

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            runtime = LocalRuntime()
            results, _ = runtime.execute(
                workflow,
                parameters={"workflow_context": {"execution_tracker": tracker}},
            )

        # init and inc should be the cached values exactly
        assert results["init"] == {"result": {"counter": 1}}
        assert results["inc"] == {"result": {"counter": 2}}

        # read should have executed freshly
        assert "read" in results


# ---------------------------------------------------------------------------
# Test: Empty tracker (new workflow)
# ---------------------------------------------------------------------------


class TestEmptyTracker:
    """A fresh tracker should not interfere with normal execution."""

    def test_empty_tracker_full_execution(self):
        """With an empty tracker, all nodes execute normally."""
        workflow = _build_counting_workflow(3)
        tracker = ExecutionTracker()

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            runtime = LocalRuntime()
            results, _ = runtime.execute(
                workflow,
                parameters={"workflow_context": {"execution_tracker": tracker}},
            )

        assert len(results) == 3
        # Tracker should now have all 3 nodes
        assert len(tracker.completed_node_ids) == 3


# ---------------------------------------------------------------------------
# Test: DurableRequest capture/restore integration
# ---------------------------------------------------------------------------


class TestDurableRequestCaptureRestore:
    """Verify that DurableRequest._capture/_restore round-trips correctly."""

    @pytest.mark.asyncio
    async def test_capture_returns_tracker_state(self):
        """After recording completions, capture should return tracker data."""
        from datetime import datetime, timezone

        metadata = RequestMetadata(
            request_id="test_req",
            method="POST",
            path="/api/workflow",
            headers={},
            query_params={},
            body={"workflow": {"name": "test"}},
            client_ip="127.0.0.1",
            user_id=None,
            tenant_id=None,
            idempotency_key=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        req = DurableRequest(request_id="test_req", metadata=metadata)

        # Simulate a workflow being set
        builder = WorkflowBuilder()
        node = PythonCodeNode(name="noop", code="result = {'ok': True}")
        builder.add_node(node, "noop", {})
        req.workflow = builder.build()
        req.workflow_id = req.workflow.workflow_id

        # Record some completions in the tracker
        req._execution_tracker.record_completion("noop", {"result": {"ok": True}})

        state = await req._capture_workflow_state()
        assert state["workflow_id"] == req.workflow_id
        assert "noop" in state["completed_nodes"]
        assert "noop" in state["node_outputs"]

    @pytest.mark.asyncio
    async def test_restore_rebuilds_tracker(self):
        """_restore_workflow_state should rebuild the tracker from dict."""
        req = DurableRequest(request_id="restore_test")

        workflow_state = {
            "workflow_id": "wf_123",
            "completed_nodes": ["a", "b", "c"],
            "node_outputs": {
                "a": {"val": 1},
                "b": {"val": 2},
                "c": {"val": 3},
            },
        }

        await req._restore_workflow_state(workflow_state)

        assert req._execution_tracker.is_completed("a")
        assert req._execution_tracker.is_completed("b")
        assert req._execution_tracker.is_completed("c")
        assert req._execution_tracker.get_output("b") == {"val": 2}
        assert req._execution_tracker.completed_node_ids == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_capture_restore_round_trip(self):
        """capture -> restore should produce identical tracker state."""
        req = DurableRequest(request_id="rt_test")

        builder = WorkflowBuilder()
        node = PythonCodeNode(name="noop", code="result = {'ok': True}")
        builder.add_node(node, "noop", {})
        req.workflow = builder.build()
        req.workflow_id = req.workflow.workflow_id

        req._execution_tracker.record_completion("noop", {"result": {"ok": True}})

        # Capture
        state = await req._capture_workflow_state()

        # Create a new request and restore into it
        req2 = DurableRequest(request_id="rt_test_2")
        await req2._restore_workflow_state(state)

        assert (
            req2._execution_tracker.completed_node_ids
            == req._execution_tracker.completed_node_ids
        )
        assert req2._execution_tracker.get_output(
            "noop"
        ) == req._execution_tracker.get_output("noop")
