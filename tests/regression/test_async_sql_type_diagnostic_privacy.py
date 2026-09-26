"""Automatic SQL diagnostics sanitize type names while retaining branch behavior."""

import io
import logging
import sys
from contextlib import asynccontextmanager

import pytest

import kailash.nodes.data.async_sql as subject
from kailash.utils.secure_logging import safe_type_name

MARKER = "review-person@example.invalid\nFORGED"
HostileError = type(MARKER, (RuntimeError,), {})


@pytest.fixture
def records_and_stream(caplog):
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    logger = subject.logger
    logger.addHandler(handler)
    try:
        with caplog.at_level(logging.DEBUG, logger=logger.name):
            yield caplog, output
    finally:
        logger.removeHandler(handler)
        handler.close()


def assert_safe_diagnostic(capture, event, value):
    caplog, output = capture
    records = [r for r in caplog.records if event in r.getMessage()]
    assert len(records) == 1
    record = records[0]
    assert record.exc_info is None
    assert MARKER not in str(record.__dict__)
    assert MARKER not in output.getvalue()
    assert safe_type_name(value) in record.getMessage() or safe_type_name(value) in (
        record.__dict__.get("handle_type"),
        record.__dict__.get("adapter_type"),
        record.__dict__.get("error_type"),
        record.__dict__.get("trigger"),
    )


@pytest.mark.parametrize("path", ["terminate", "raw_close", "unsupported"])
def test_sync_disposal_type_diagnostics_are_safe(path, records_and_stream):
    error = HostileError("private driver details")

    def fail(*_args):
        raise error

    if path == "terminate":
        handle = type("Handle", (), {"terminate": fail})()
        event, value = "pool_sync_terminate_failed", error
    elif path == "raw_close":
        raw = type("Raw", (), {"close": fail})()
        handle = type("Handle", (), {"_conn": raw})()
        event, value = "sqlite_sync_close_failed", error
    else:
        handle = type(MARKER, (), {})()
        event, value = "pool_sync_dispose_unsupported", handle
    assert subject._terminate_driver_handle_sync(handle, label="owned") is False
    assert_safe_diagnostic(records_and_stream, event, value)


def test_unstampable_adapter_type_is_safe(records_and_stream):
    adapter = type(MARKER, (), {"__slots__": ()})()
    assert subject._stamp_pool_loop(adapter) is None
    assert_safe_diagnostic(records_and_stream, "pool_loop_stamp_failed", adapter)


def test_registry_iteration_failure_type_is_safe(monkeypatch, records_and_stream):
    error = HostileError("private registry details")

    class FailingRegistry:
        def items(self):
            raise error

    monkeypatch.setattr(subject, "_PROCESS_POOL_REGISTRY", FailingRegistry())
    assert subject._unregister_pool(object()) == 0
    assert_safe_diagnostic(records_and_stream, "pool_unregister_sweep_skipped", error)


def test_environment_probe_failure_type_is_safe(monkeypatch, records_and_stream):
    error = HostileError("private inspection details")

    def fail():
        raise error

    with monkeypatch.context() as patch:
        patch.delitem(sys.modules, "pytest", raising=False)
        patch.delitem(sys.modules, "unittest", raising=False)
        patch.delenv("PYTEST_CURRENT_TEST", raising=False)
        patch.delenv("KAILASH_TEST_ENV", raising=False)
        patch.setattr(subject.AsyncSQLDatabaseNode, "_test_env_cache", None)
        patch.setattr(subject.inspect, "stack", fail)
        assert subject.AsyncSQLDatabaseNode._is_test_environment() is False
    assert_safe_diagnostic(records_and_stream, "Stack inspection failed", error)


@pytest.mark.asyncio
async def test_stack_object_type_is_safe(records_and_stream):
    node = subject.AsyncSQLDatabaseNode(
        name="diagnostic_probe", database_type="sqlite", database=":memory:"
    )

    async def inspect_from_hostile_type(self):
        return await node._get_runtime_pool_adapter()

    caller = type(MARKER, (), {"inspect": inspect_from_hostile_type})()
    assert await caller.inspect() is None
    caplog, output = records_and_stream
    matches = [
        r
        for r in caplog.records
        if r.getMessage() == f"Checking call stack object: {safe_type_name(caller)}"
    ]
    assert len(matches) == 1
    assert MARKER not in str([r.__dict__ for r in caplog.records])
    assert MARKER not in output.getvalue()


@pytest.mark.asyncio
async def test_fallback_trigger_type_is_safe(monkeypatch, records_and_stream):
    node = subject.AsyncSQLDatabaseNode(
        name="fallback_probe", database_type="sqlite", database=":memory:"
    )
    error = HostileError("private pool failure")
    registered = []
    adapter = object()

    async def no_runtime_pool():
        return None

    @asynccontextmanager
    async def failed_lock(*_args, **_kwargs):
        raise error
        yield

    async def create_adapter():
        return adapter

    monkeypatch.setattr(node, "_get_runtime_pool_adapter", no_runtime_pool)
    monkeypatch.setattr(node, "_acquire_pool_lock_with_timeout", failed_lock)
    monkeypatch.setattr(node, "_create_adapter", create_adapter)
    monkeypatch.setattr(
        subject, "_register_pool", lambda key, value: registered.append(value)
    )
    try:
        assert await node._get_adapter() is adapter
        assert registered == [adapter]
        assert node._share_pool is False
        assert_safe_diagnostic(records_and_stream, "fallback_pool_created", error)
    finally:
        node._adapter = None
