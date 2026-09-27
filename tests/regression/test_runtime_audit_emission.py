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
