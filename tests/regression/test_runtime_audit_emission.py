"""Runtime audit producers must emit records through the real audit node."""

import asyncio
import json
import logging

import pytest

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize(
    "event_type,level",
    [("info", logging.INFO), ("warning", logging.WARNING), ("error", logging.ERROR)],
)
def test_runtime_audit_helpers_emit_real_records(
    caplog, asynchronous, event_type, level
):
    data = {"action": "read", "nested": {"count": 3}}
    with LocalRuntime(enable_audit=True, enable_monitoring=False) as runtime:
        with caplog.at_level(logging.INFO):
            if asynchronous:
                asyncio.run(runtime._log_audit_event_async(event_type, data))
            else:
                runtime._log_audit_event(event_type, data)
    records = [
        record for record in caplog.records if record.name == "audit.runtime_audit"
    ]
    assert len(records) == 1
    assert records[0].levelno == level
    entry = json.loads(records[0].getMessage())
    assert entry["event_type"] == event_type
    assert entry["data"] == data == {"action": "read", "nested": {"count": 3}}
    assert not any(
        "Audit logging failed" in record.getMessage() for record in caplog.records
    )


@pytest.mark.parametrize("asynchronous", [False, True])
def test_runtime_audit_helpers_honor_disabled_audit(caplog, asynchronous):
    with LocalRuntime(enable_audit=False, enable_monitoring=False) as runtime:
        with caplog.at_level(logging.INFO):
            if asynchronous:
                asyncio.run(runtime._log_audit_event_async("info", {"action": "read"}))
            else:
                runtime._log_audit_event("info", {"action": "read"})
    assert not any(record.name.startswith("audit.") for record in caplog.records)
    assert not any(
        "Audit logging failed" in record.getMessage() for record in caplog.records
    )


def test_real_async_workflow_emits_start_and_completion(caplog):
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "answer", {"code": "result = 42"})
    with LocalRuntime(enable_audit=True, enable_monitoring=False) as runtime:
        with caplog.at_level(logging.INFO):
            results, _ = asyncio.run(runtime.execute_async(workflow.build()))
    assert results["answer"]["result"] == 42
    records = [
        record for record in caplog.records if record.name == "audit.runtime_audit"
    ]
    entries = [json.loads(record.getMessage()) for record in records]
    assert [entry["event_type"] for entry in entries] == [
        "workflow_execution_start",
        "workflow_execution_completed",
    ]
    assert all(record.levelno == logging.INFO for record in records)
    assert entries[0]["data"]["workflow_id"] == entries[1]["data"]["workflow_id"]
    assert entries[1]["data"]["result_summary"] == {"answer": "dict"}
    assert not any(
        "Audit logging failed" in record.getMessage() for record in caplog.records
    )


@pytest.mark.parametrize("asynchronous", [False, True])
def test_audit_import_fallback_retains_event_without_secret_payload(
    caplog, monkeypatch, asynchronous
):
    import builtins

    original_import = builtins.__import__
    secret = "runtime-audit-fallback-canary-419"
    event_type = '{"password":"' + secret + '"}'
    data = {"opaque_payload": secret, "nested": {"token": secret}}
    hits = []

    def unavailable(name, *args, **kwargs):
        if name == "kailash.nodes.security.audit_log":
            hits.append(name)
            raise ImportError("intentional audit dependency absence")
        return original_import(name, *args, **kwargs)

    with LocalRuntime(enable_audit=True, enable_monitoring=False) as runtime:
        monkeypatch.setattr(builtins, "__import__", unavailable)
        with caplog.at_level(logging.INFO):
            if asynchronous:
                asyncio.run(runtime._log_audit_event_async(event_type, data))
            else:
                runtime._log_audit_event(event_type, data)
    records = [
        record for record in caplog.records if record.getMessage().startswith("AUDIT:")
    ]
    assert len(hits) == len(records) == 1
    assert records[0].levelno == logging.INFO
    assert secret not in records[0].getMessage()
    assert "data_fields=2" in records[0].getMessage()
    assert records[0].getMessage().isprintable()
    assert data == {"opaque_payload": secret, "nested": {"token": secret}}


@pytest.mark.parametrize(
    "route",
    ["local_sync", "local_async", "native_sync", "native_async", "native_direct"],
)
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("failing", [False, True])
def test_public_execution_audit_outcome_and_exception_privacy(
    caplog, route, enabled, failing
):
    from kailash.runtime.async_local import AsyncLocalRuntime
    from kailash.sdk_exceptions import RuntimeExecutionError, WorkflowExecutionError

    secret = "opaque-runtime-audit-outcome-canary-7351"
    workflow = WorkflowBuilder()
    workflow.add_node(
        "PythonCodeNode",
        "first",
        {
            "code": (
                "raise RuntimeError(" + repr(secret) + ")" if failing else "result = 42"
            )
        },
    )
    workflow.add_node(
        "PythonCodeNode",
        "last",
        {"code": "result = value", "input_types": {"value": int}},
    )
    workflow.add_connection("first", "result", "last", "value")
    native = route.startswith("native")
    runtime = (AsyncLocalRuntime if native else LocalRuntime)(
        enable_audit=enabled, enable_monitoring=False
    )

    async def run_async():
        if native:
            async with runtime:
                if route == "native_direct":
                    return await runtime.execute_workflow_async(
                        workflow.build(), inputs={}
                    )
                return await runtime.execute_async(workflow.build())
        with runtime:
            return await runtime.execute_async(workflow.build())

    def execute():
        if route.endswith("_sync"):
            with runtime:
                return runtime.execute(workflow.build())
        return asyncio.run(run_async())

    with caplog.at_level(logging.INFO):
        if failing:
            with pytest.raises(
                WorkflowExecutionError if native else RuntimeExecutionError,
                match=secret,
            ):
                execute()
        else:
            results, _ = execute()
            assert results["first"]["result"] == 42
    records = [
        record for record in caplog.records if record.name == "audit.runtime_audit"
    ]
    if not enabled:
        assert records == []
        return
    entries = [json.loads(record.getMessage()) for record in records]
    terminal = (
        "workflow_execution_failed" if failing else "workflow_execution_completed"
    )
    assert [entry["event_type"] for entry in entries] == [
        "workflow_execution_start",
        terminal,
    ]
    assert all(record.levelno == logging.INFO for record in records)
    assert all(secret not in record.getMessage() for record in records)
    if failing:
        assert "WorkflowExecutionError" in entries[-1]["data"]["error"]
    else:
        assert entries[-1]["data"]["result_summary"] == {
            "first": "dict",
            "last": "dict",
        }


@pytest.mark.parametrize("route", ["native_async", "native_direct"])
@pytest.mark.parametrize("terminal", ["cancel", "timeout"])
def test_native_audit_records_cancel_and_timeout(caplog, route, terminal):
    from kailash.nodes.base_async import AsyncNode
    from kailash.runtime.async_local import AsyncLocalRuntime
    from kailash.workflow.graph import Workflow

    async def exercise():
        entered = asyncio.Event()
        stopped = asyncio.Event()

        class WaitingNode(AsyncNode):
            def get_parameters(self):
                return {}

            async def async_run(self, **kwargs):
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    stopped.set()

        workflow = Workflow("audit-cancellation", name="audit-cancellation")
        workflow.add_node("waiting", WaitingNode())
        async with AsyncLocalRuntime(
            enable_audit=True,
            enable_monitoring=False,
            execution_timeout=0.1 if terminal == "timeout" else 0,
        ) as runtime:
            operation = (
                runtime.execute_async(workflow)
                if route == "native_async"
                else runtime.execute_workflow_async(workflow, inputs={})
            )
            task = asyncio.create_task(operation)
            if terminal == "cancel":
                await asyncio.wait_for(entered.wait(), timeout=5)
                task.cancel()
            with pytest.raises(
                asyncio.CancelledError if terminal == "cancel" else TimeoutError
            ):
                await task
        assert not entered.is_set() or stopped.is_set()

    with caplog.at_level(logging.INFO):
        asyncio.run(exercise())
    records = [
        record for record in caplog.records if record.name == "audit.runtime_audit"
    ]
    entries = [json.loads(record.getMessage()) for record in records]
    assert [entry["event_type"] for entry in entries] == [
        "workflow_execution_start",
        "workflow_execution_failed",
    ]
    assert ("CancelledError" if terminal == "cancel" else "TimeoutError") in entries[
        -1
    ]["data"]["error"]


def test_local_access_denial_audit_preserves_public_error_and_uses_frames(caplog):
    from kailash.access_control import AccessControlManager, UserContext

    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "answer", {"code": "result = 42"})
    user = UserContext(
        user_id="audit-user", tenant_id="audit-tenant", email="audit@example.invalid"
    )
    with LocalRuntime(
        enable_audit=True,
        enable_security=True,
        enable_monitoring=False,
        user_context=user,
    ) as runtime:
        runtime._access_control_manager = AccessControlManager(enabled=True)
        with caplog.at_level(logging.INFO):
            with pytest.raises(PermissionError, match="Access denied to workflow"):
                asyncio.run(runtime.execute_async(workflow.build()))
    entries = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "audit.runtime_audit"
    ]
    assert [entry["event_type"] for entry in entries] == ["workflow_access_denied"]
    error = entries[0]["data"]["error"]
    assert "PermissionError@" in error
    assert "Access denied to workflow" not in error
