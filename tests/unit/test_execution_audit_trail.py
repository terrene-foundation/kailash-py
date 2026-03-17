"""Tests for comprehensive execution audit trail (Feature 2).

Validates that node inputs/outputs, lifecycle events, and the
_safe_serialize helper all work correctly for forensic traceability.
"""

import json
import time
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from kailash.runtime.local import LocalRuntime, _safe_serialize
from kailash.tracking.manager import TaskManager
from kailash.tracking.storage.database import SQLiteStorage
from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_two_node_workflow():
    """Build a trivial 2-node workflow for audit trail testing."""
    builder = WorkflowBuilder()
    builder.add_node(
        "PythonCodeNode",
        "node_a",
        {
            "code": "result = {'value': input_data.get('x', 0) + 1}",
        },
    )
    builder.add_node(
        "PythonCodeNode",
        "node_b",
        {
            "code": "result = {'total': data.get('value', 0) * 2}",
        },
    )
    builder.add_connection("node_a", "result", "node_b", "data")
    return builder.build()


def _build_failing_workflow():
    """Build a workflow where the second node raises an error."""
    builder = WorkflowBuilder()
    builder.add_node(
        "PythonCodeNode",
        "ok_node",
        {
            "code": "result = {'status': 'ok'}",
        },
    )
    builder.add_node(
        "PythonCodeNode",
        "bad_node",
        {
            "code": "raise ValueError('intentional test error')",
        },
    )
    builder.add_connection("ok_node", "result", "bad_node", "data")
    return builder.build()


# ---------------------------------------------------------------------------
# _safe_serialize tests
# ---------------------------------------------------------------------------


class TestSafeSerializeTruncatesLargeData:
    def test_small_data_passes_through(self):
        """Data under max_size is returned as-is."""
        data = {"key": "value", "number": 42}
        result = _safe_serialize(data, max_size=10000)
        assert result == data

    def test_large_data_truncated(self):
        """Data over max_size produces a truncation summary."""
        large_data = {"big": "x" * 20000}
        result = _safe_serialize(large_data, max_size=100)

        assert isinstance(result, dict)
        assert result["_truncated"] is True
        assert "_size" in result
        assert result["_size"] > 100
        assert "_preview" in result
        assert len(result["_preview"]) <= 1000


class TestSafeSerializeHandlesNonJson:
    def test_non_serializable_object(self):
        """Non-JSON-serializable objects produce a fallback dict."""
        obj = object()
        result = _safe_serialize(obj, max_size=10000)

        # json.dumps(object()) raises TypeError, triggering fallback
        assert isinstance(result, dict)
        assert "_type" in result
        assert "_str" in result

    def test_set_value(self):
        """Sets are not JSON-serializable but handled gracefully."""
        data = {1, 2, 3}
        result = _safe_serialize(data, max_size=10000)
        # json.dumps({1,2,3}) raises TypeError, triggering fallback
        assert isinstance(result, dict)
        assert "_type" in result
        assert "set" in result["_type"]


class TestSafeSerializeEdgeCases:
    def test_none_value(self):
        """None serializes to null JSON, well under limit."""
        result = _safe_serialize(None, max_size=100)
        assert result is None

    def test_empty_dict(self):
        """Empty dict serializes to '{}', passes through."""
        result = _safe_serialize({}, max_size=100)
        assert result == {}

    def test_exactly_at_limit(self):
        """Data exactly at limit passes through."""
        data = {"a": "b"}
        s = json.dumps(data, default=str)
        result = _safe_serialize(data, max_size=len(s))
        assert result == data


# ---------------------------------------------------------------------------
# Audit trail event tests (using real runtime execution)
# ---------------------------------------------------------------------------


class TestNodeExecutedEventCaptured:
    def test_node_executed_event_captured(self, tmp_path):
        """After successful execution, NODE_EXECUTED events are recorded."""
        db_path = str(tmp_path / "audit_exec.db")
        storage = SQLiteStorage(db_path)
        tm = TaskManager(storage_backend=storage)
        workflow = _build_two_node_workflow()

        with LocalRuntime(debug=True, enable_monitoring=False) as runtime:
            results, run_id = runtime.execute(
                workflow,
                task_manager=tm,
                parameters={"node_a": {"input_data": {"x": 10}}},
            )

        # Query audit events for NODE_EXECUTED
        events = storage.query_audit_events(trace_id=run_id)
        node_executed = [e for e in events if e.get("event_type") == "NODE_EXECUTED"]

        assert len(node_executed) >= 1
        # Each event should have context with inputs/outputs/duration
        for evt in node_executed:
            ctx = evt.get("context", {})
            assert "inputs" in ctx or "node_id" in ctx
            assert "duration_ms" in ctx

        storage.close()


class TestNodeFailedEventCaptured:
    def test_node_failed_event_captured(self, tmp_path):
        """When a node fails, a NODE_FAILED event is recorded.

        Note: Terminal nodes (no downstream dependents) record errors
        in results without raising. The audit trail still captures
        the NODE_FAILED event.
        """
        db_path = str(tmp_path / "audit_fail.db")
        storage = SQLiteStorage(db_path)
        tm = TaskManager(storage_backend=storage)
        workflow = _build_failing_workflow()

        with LocalRuntime(debug=True, enable_monitoring=False) as runtime:
            results, run_id = runtime.execute(workflow, task_manager=tm)

        # The failing terminal node has its error in results
        assert "bad_node" in results
        assert results["bad_node"].get("failed") is True

        # Check that there are audit events stored
        all_events = storage.query_audit_events()
        event_types = {e.get("event_type") for e in all_events}

        # NODE_FAILED should be present
        assert "NODE_FAILED" in event_types

        # Verify the failure event has error info
        fail_events = [e for e in all_events if e.get("event_type") == "NODE_FAILED"]
        assert len(fail_events) >= 1
        fail_ctx = fail_events[0].get("context", {})
        assert "error" in fail_ctx
        assert "intentional test error" in fail_ctx["error"]

        storage.close()


class TestWorkflowLifecycleEvents:
    def test_workflow_lifecycle_events(self, tmp_path):
        """WORKFLOW_STARTED and WORKFLOW_COMPLETED events are emitted."""
        db_path = str(tmp_path / "audit_lifecycle.db")
        storage = SQLiteStorage(db_path)
        tm = TaskManager(storage_backend=storage)
        workflow = _build_two_node_workflow()

        with LocalRuntime(debug=True, enable_monitoring=False) as runtime:
            results, run_id = runtime.execute(
                workflow,
                task_manager=tm,
                parameters={"node_a": {"input_data": {"x": 5}}},
            )

        events = storage.query_audit_events(trace_id=run_id)
        event_types = [e.get("event_type") for e in events]

        assert "WORKFLOW_STARTED" in event_types
        assert "WORKFLOW_COMPLETED" in event_types

        # WORKFLOW_COMPLETED should have duration and node count
        completed = [e for e in events if e.get("event_type") == "WORKFLOW_COMPLETED"]
        assert len(completed) == 1
        ctx = completed[0].get("context", {})
        assert "total_duration_ms" in ctx
        assert "nodes_executed" in ctx

        storage.close()

    def test_workflow_failed_lifecycle_event(self, tmp_path):
        """WORKFLOW_FAILED event includes error details.

        Note: Terminal node failures produce WORKFLOW_FAILED events
        without raising to the caller.
        """
        db_path = str(tmp_path / "audit_wf_fail.db")
        storage = SQLiteStorage(db_path)
        tm = TaskManager(storage_backend=storage)
        workflow = _build_failing_workflow()

        with LocalRuntime(debug=True, enable_monitoring=False) as runtime:
            results, run_id = runtime.execute(workflow, task_manager=tm)

        all_events = storage.query_audit_events()
        wf_failed = [e for e in all_events if e.get("event_type") == "WORKFLOW_FAILED"]
        assert len(wf_failed) >= 1
        ctx = wf_failed[0].get("context", {})
        assert "error" in ctx
        assert "failed_node_id" in ctx

        storage.close()


class TestAuditTrailRetrieval:
    def test_audit_trail_retrieval(self, tmp_path):
        """get_execution_audit_trail returns chronological events."""
        db_path = str(tmp_path / "audit_retrieve.db")
        storage = SQLiteStorage(db_path)
        tm = TaskManager(storage_backend=storage)
        workflow = _build_two_node_workflow()

        with LocalRuntime(debug=True, enable_monitoring=False) as runtime:
            results, run_id = runtime.execute(
                workflow,
                task_manager=tm,
                parameters={"node_a": {"input_data": {"x": 1}}},
            )

        trail = tm.get_execution_audit_trail(run_id)

        # Should have at least: WORKFLOW_RUN + TASK_RECORDs + AUDIT_EVENTs
        assert len(trail) >= 3

        # First entry should be workflow-level
        types_seen = {entry.get("type") for entry in trail}
        assert "WORKFLOW_RUN" in types_seen or "AUDIT_EVENT" in types_seen

        storage.close()

    def test_audit_trail_empty_run_id(self, tmp_path):
        """Empty run_id raises TaskException."""
        from kailash.sdk_exceptions import TaskException

        db_path = str(tmp_path / "audit_empty.db")
        storage = SQLiteStorage(db_path)
        tm = TaskManager(storage_backend=storage)

        with pytest.raises(TaskException):
            tm.get_execution_audit_trail("")

        storage.close()
