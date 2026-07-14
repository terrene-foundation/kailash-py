"""
Unit tests for the #1741 follow-up wiring: the shared single-connection helper
(``open_credentialed_connection``), the context-scoped provider side-channel
(``credential_provider_scope`` / ``get_active_credential_provider``) used by the
standalone WorkflowBuilder bulk nodes, and the end-to-end proof that a bulk node
picks up the scoped provider.

The engine DDL / verify / migration connects all route through
``open_credentialed_connection`` (tested here for the mint-vs-plain contract);
the standalone ``DataFlowBulkUpsertNode`` reads the context-bound provider
because it holds no DataFlow instance (a live Callable cannot ride the
workflow-parameter channel).

Deterministic Protocol-satisfying recorders only — NEVER a MagicMock
(rules/testing.md "Protocol-Satisfying Deterministic Adapters").
"""

from __future__ import annotations

import contextvars
from typing import List

import pytest

from dataflow.core.credential_provider import (
    credential_provider_scope,
    get_active_credential_provider,
    open_credentialed_connection,
)

asyncpg = pytest.importorskip("asyncpg")


class _ConnectRecorder:
    def __init__(self):
        self.calls: List[dict] = []
        self.args: List[tuple] = []

    async def __call__(self, *args, **kwargs):
        self.args.append(args)
        self.calls.append(dict(kwargs))
        return object()


def _provider(token: str):
    def _p() -> str:
        return token

    return _p


class TestOpenCredentialedConnection:
    """The single shared single-connection entry point (engine DDL / verify /
    migration-lock / staging connects all route through this)."""

    @pytest.mark.asyncio
    async def test_mints_token_as_password_when_provider_set(self, monkeypatch):
        rec = _ConnectRecorder()
        monkeypatch.setattr(asyncpg, "connect", rec)

        await open_credentialed_connection(
            asyncpg,
            "postgresql://u:STALE@h:5432/d",
            credential_provider=_provider("tok-v1"),
            context="PostgreSQL DDL",
            timeout=5,
        )

        # DSN forwarded positionally; minted token injected as password=;
        # other kwargs preserved.
        assert rec.args[0][0] == "postgresql://u:STALE@h:5432/d"
        assert rec.calls[0]["password"] == "tok-v1"
        assert rec.calls[0]["timeout"] == 5

    @pytest.mark.asyncio
    async def test_plain_connect_when_provider_none(self, monkeypatch):
        rec = _ConnectRecorder()
        monkeypatch.setattr(asyncpg, "connect", rec)

        await open_credentialed_connection(
            asyncpg, "postgresql://u:static@h:5432/d", timeout=5
        )

        assert rec.args[0] == ("postgresql://u:static@h:5432/d",)
        assert "password" not in rec.calls[0]
        assert rec.calls[0]["timeout"] == 5


class TestCredentialProviderScope:
    def test_default_unbound_is_none(self):
        assert get_active_credential_provider() is None

    def test_bind_get_reset(self):
        p = _provider("x")
        assert get_active_credential_provider() is None
        with credential_provider_scope(p):
            assert get_active_credential_provider() is p
        # reset on exit — never leaks across instances/tests
        assert get_active_credential_provider() is None

    def test_nested_scopes_restore_outer(self):
        p1, p2 = _provider("1"), _provider("2")
        with credential_provider_scope(p1):
            assert get_active_credential_provider() is p1
            with credential_provider_scope(p2):
                assert get_active_credential_provider() is p2
            assert get_active_credential_provider() is p1
        assert get_active_credential_provider() is None

    def test_propagates_across_copy_context_dispatch(self):
        """The Kailash runtime snapshots ``copy_context()`` and runs the node
        inside it at every thread-boundary dispatch — the bound provider MUST
        be visible in that copied context (this is why the side-channel works
        for the standalone bulk nodes)."""
        p = _provider("tok")
        seen = {}
        with credential_provider_scope(p):
            ctx = contextvars.copy_context()

        def _reader():
            seen["provider"] = get_active_credential_provider()

        # Running the snapshot AFTER leaving the scope still sees the value
        # captured at snapshot time — exactly the runtime's dispatch shape.
        ctx.run(_reader)
        assert seen["provider"] is p


class _RecordingAsyncSQLNode:
    """Records the credential_provider kwarg the bulk node passes; satisfies
    the async_run / cleanup surface the bulk node invokes."""

    instances: List["_RecordingAsyncSQLNode"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        _RecordingAsyncSQLNode.instances.append(self)

    async def async_run(self, **inputs):
        return {"result": {"data": [], "rows_affected": 0}}

    async def cleanup(self):
        pass


class TestBulkUpsertNodeScopedProvider:
    """End-to-end: the standalone DataFlowBulkUpsertNode (no DataFlow instance)
    picks up the context-scoped provider and forwards it to its fresh
    AsyncSQLDatabaseNode."""

    @pytest.mark.asyncio
    async def test_bulk_node_forwards_scoped_provider(self, monkeypatch):
        import kailash.nodes.data.async_sql as async_sql_mod
        from dataflow.nodes.bulk_upsert import DataFlowBulkUpsertNode

        _RecordingAsyncSQLNode.instances.clear()
        # bulk_upsert does `from kailash.nodes.data.async_sql import
        # AsyncSQLDatabaseNode` at call time → patch on that module.
        monkeypatch.setattr(
            async_sql_mod, "AsyncSQLDatabaseNode", _RecordingAsyncSQLNode
        )

        node = DataFlowBulkUpsertNode(
            connection_string="postgresql://u:static@h:5432/d",
            table_name="widgets",
        )
        node.database_type = "postgresql"

        provider = _provider("tok-v1")
        with credential_provider_scope(provider):
            await node._execute_query("UPDATE widgets SET x=1", [])

        assert len(_RecordingAsyncSQLNode.instances) == 1
        assert (
            _RecordingAsyncSQLNode.instances[0].kwargs["credential_provider"]
            is provider
        )

    @pytest.mark.asyncio
    async def test_bulk_node_provider_none_outside_scope(self, monkeypatch):
        import kailash.nodes.data.async_sql as async_sql_mod
        from dataflow.nodes.bulk_upsert import DataFlowBulkUpsertNode

        _RecordingAsyncSQLNode.instances.clear()
        monkeypatch.setattr(
            async_sql_mod, "AsyncSQLDatabaseNode", _RecordingAsyncSQLNode
        )

        node = DataFlowBulkUpsertNode(
            connection_string="postgresql://u:static@h:5432/d",
            table_name="widgets",
        )
        node.database_type = "postgresql"

        # No scope → None → behavior unchanged (static password path).
        await node._execute_query("UPDATE widgets SET x=1", [])

        assert _RecordingAsyncSQLNode.instances[0].kwargs["credential_provider"] is None
