"""Log-only sanitization preserves authenticated dispatch and event identities.

These unit regressions use real HTTP/ASGI dispatch and SQLite. The failing MCP
collaborator exercises the gateway's call_tool boundary, not the MCP wire protocol.
"""

import io
import logging
from contextlib import contextmanager
from urllib.parse import quote

import pytest
from starlette.testclient import TestClient

from kailash.api import gateway as gateway_module
from kailash.middleware.gateway import event_store as store_module
from kailash.middleware.gateway.event_store_sqlite import SqliteEventStoreBackend
from kailash.trust.auth.jwt import JWTConfig, JWTValidator
from kailash.workflow.builder import WorkflowBuilder
from pact.governance.api import events as pact_events

IDENTIFIER = "probe\nINFO:root:forged audit approval\r\x1b\u2028\u202e"
SECRET = "csq14-synthetic-secret"
FAILURE = (
    f"backend postgresql://probe:{SECRET}@db.example.test/app"
    "\nINFO:root:forged exception record"
)


@contextmanager
def captured_logs(name):
    logger = logging.getLogger(name)
    stream = io.StringIO()
    records = []

    class RecordingHandler(logging.StreamHandler):
        def emit(self, record):
            records.append(record)
            super().emit(record)

    handler = RecordingHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    old_level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        yield stream, records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
        handler.close()


def assert_safe_logs(capture, expected_message, level):
    stream, records = capture
    selected = [r for r in records if expected_message in r.getMessage()]
    assert selected, stream.getvalue()
    assert all(r.levelno == level for r in selected)
    for record in records:
        assert record.exc_info is None
        assert record.exc_text is None
        for value in (record.getMessage(), *record.args):
            text = str(value)
            assert not any(c in text for c in "\r\n\x1b\u2028\u202e")
            assert SECRET not in text
    rendered = stream.getvalue()
    assert len(rendered.splitlines()) == len(records)
    assert SECRET not in rendered
    assert "\nINFO:root:forged" not in rendered


@pytest.fixture
def gateway(monkeypatch):
    monkeypatch.setenv(
        "KAILASH_JWT_SECRET", "log-regression-secret-key-at-least-32-characters"
    )
    instance = gateway_module.WorkflowAPIGateway(title="log-regression")
    try:
        yield instance
    finally:
        instance.close()
        instance.executor.shutdown(wait=True)


def test_workflow_registration_keeps_name_but_sanitizes_diagnostic(gateway):
    builder = WorkflowBuilder()
    builder.add_node(
        "DataTransformer", "n", {"data": {"ran": True}, "transformations": []}
    )
    with captured_logs(gateway_module.__name__) as capture:
        gateway.register_workflow(IDENTIFIER, builder.build())
    assert IDENTIFIER in gateway.workflows
    assert_safe_logs(capture, "Registered embedded workflow:", logging.INFO)
    assert "probe" in capture[0].getvalue()


def test_mcp_failure_preserves_auth_and_hides_exception_message(gateway):
    calls = []

    class FailingTool:
        def call_tool(self, name, body):
            calls.append((name, body))
            raise RuntimeError(FAILURE)

    with captured_logs(gateway_module.__name__) as registered:
        gateway.register_mcp_server(IDENTIFIER, FailingTool())
    assert_safe_logs(registered, "Registered MCP server:", logging.INFO)
    token = JWTValidator(
        JWTConfig(secret="log-regression-secret-key-at-least-32-characters")
    ).create_access_token(user_id="log-probe")
    path = f"/mcp/{quote(IDENTIFIER, safe='')}/tools/{quote(IDENTIFIER, safe='')}"
    with TestClient(gateway.app) as client:
        with captured_logs(gateway_module.__name__) as capture:
            denied = client.post(path, json={"value": 1})
            assert denied.status_code == 401
            assert calls == []
            failed = client.post(
                path, json={"value": 1}, headers={"Authorization": f"Bearer {token}"}
            )
    assert calls == [(IDENTIFIER, {"value": 1})]
    assert failed.status_code == 500
    assert failed.json() == {"error": "Tool execution failed"}
    assert_safe_logs(capture, "MCP tool", logging.ERROR)
    assert "RuntimeError" in capture[0].getvalue()


@pytest.mark.asyncio
async def test_event_append_keeps_request_and_data_but_sanitizes_log():
    store = store_module.EventStore(storage_backend="memory")
    try:
        with captured_logs(store_module.__name__) as capture:
            event = await store.append(
                store_module.EventType.REQUEST_CREATED, IDENTIFIER, {"raw": IDENTIFIER}
            )
            loaded = await store.get_events(IDENTIFIER)
        assert loaded == [event]
        assert event.request_id == IDENTIFIER
        assert event.data == {"raw": IDENTIFIER}
        assert_safe_logs(capture, "Appended event", logging.DEBUG)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_real_closed_sqlite_error_has_safe_request_diagnostic(tmp_path):
    backend = SqliteEventStoreBackend(str(tmp_path / "events.db"))
    store = store_module.EventStore(storage_backend=backend)
    try:
        await backend.close()
        with captured_logs(store_module.__name__) as capture:
            assert await store.get_events(IDENTIFIER) == []
        assert_safe_logs(capture, "Failed to load events for", logging.ERROR)
        assert "RuntimeError" in capture[0].getvalue()
        assert "SQLiteEventStore connection is closed" not in capture[0].getvalue()
    finally:
        await store.close()
        await backend.close()


@pytest.mark.asyncio
async def test_projection_exception_cannot_leak_credentials():
    store = store_module.EventStore(storage_backend="memory")
    calls = []

    def projection(event, state):
        calls.append(event)
        raise RuntimeError(FAILURE)

    try:
        with captured_logs(store_module.__name__) as capture:
            store.register_projection(IDENTIFIER, projection)
            event = await store.append(
                store_module.EventType.REQUEST_CREATED, IDENTIFIER, {}
            )
        assert calls == [event]
        assert store.get_projection(IDENTIFIER) == {}
        assert_safe_logs(capture, "Projection", logging.ERROR)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_governance_emit_retains_role_and_delivers_original_payload(monkeypatch):
    bus = pact_events.EventBus()
    monkeypatch.setattr(pact_events, "event_bus", bus)
    queue = await bus.subscribe()
    try:
        with captured_logs(pact_events.__name__) as capture:
            event = await pact_events.emit_governance_event(
                pact_events.GovernanceEventType.ACCESS_CHECKED,
                {"allowed": False, "raw": IDENTIFIER},
                source_role_address=IDENTIFIER,
            )
        assert queue.get_nowait() is event
        assert event.source_agent_id == IDENTIFIER
        assert event.data == {
            "governance_event_type": "governance.access_checked",
            "allowed": False,
            "raw": IDENTIFIER,
        }
        assert_safe_logs(capture, "Emitted governance event:", logging.DEBUG)
    finally:
        await bus.unsubscribe(queue)


@pytest.mark.asyncio
async def test_governance_failed_publication_omits_exception_message(monkeypatch):
    calls = []

    async def fail_publish(self, event):
        calls.append(event)
        raise RuntimeError(FAILURE)

    monkeypatch.setattr(pact_events.EventBus, "publish", fail_publish)
    with captured_logs(pact_events.__name__) as capture:
        result = await pact_events.emit_governance_event(
            pact_events.GovernanceEventType.ACCESS_CHECKED,
            {"allowed": False},
            source_role_address=IDENTIFIER,
        )
    assert result is None
    assert len(calls) == 1
    assert calls[0].source_agent_id == IDENTIFIER
    assert_safe_logs(capture, "Failed to emit governance event:", logging.ERROR)
    assert "RuntimeError" in capture[0].getvalue()


@pytest.mark.asyncio
async def test_mcp_health_exception_is_safe_and_still_unhealthy(gateway):
    class UnhealthyServer:
        async def ping(self):
            raise RuntimeError(FAILURE)

    with captured_logs(gateway_module.__name__) as capture:
        status = await gateway._check_mcp_health(IDENTIFIER, UnhealthyServer())
    assert status == "unhealthy"
    assert_safe_logs(capture, "MCP health check failed", logging.WARNING)
    assert "RuntimeError" in capture[0].getvalue()


def test_external_auth_reason_is_preserved_but_structured_log_is_safe(gateway):
    with captured_logs(gateway_module.__name__) as capture:
        gateway.declare_external_auth(IDENTIFIER)
    assert gateway._external_auth_reason == IDENTIFIER.strip()
    assert_safe_logs(capture, "gateway.external_auth_declared", logging.WARNING)
    record = capture[1][0]
    assert not any(c in record.reason for c in "\r\n\x1b\u2028\u202e")
    assert "probe" in record.reason


@pytest.mark.asyncio
async def test_full_governance_queue_sanitizes_event_id_and_keeps_backpressure():
    bus = pact_events.EventBus()
    queue = await bus.subscribe()
    event = pact_events.PlatformEvent(pact_events.EventType.AUDIT_ANCHOR, {})
    event.event_id = IDENTIFIER
    try:
        for _ in range(queue.maxsize):
            queue.put_nowait(event)
        with captured_logs(pact_events.__name__) as capture:
            assert await bus.publish(event) == 0
        assert queue.qsize() == queue.maxsize
        assert event.event_id == IDENTIFIER
        assert_safe_logs(capture, "Dropping event", logging.WARNING)
    finally:
        await bus.unsubscribe(queue)
