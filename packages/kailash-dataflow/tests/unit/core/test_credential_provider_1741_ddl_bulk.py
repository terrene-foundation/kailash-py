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

import types

import pytest

from dataflow.core.credential_provider import (
    credential_provider_scope,
    get_active_credential_provider,
    open_credentialed_connection,
    resolve_fresh_credential,
)
from dataflow.exceptions import DataFlowConnectionError

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


class _RaisingProvider:
    def __init__(self, secret: str):
        self._secret = secret

    def __call__(self) -> str:
        raise RuntimeError(f"token endpoint down secret={self._secret}")


class TestResolveFreshCredential:
    """The SYNC fail-closed mint (for drivers with no per-connection callback,
    e.g. psycopg2)."""

    def test_returns_fresh_token(self):
        assert resolve_fresh_credential(_provider("tok-v1")) == "tok-v1"

    def test_raising_provider_fails_closed_no_secret(self):
        with pytest.raises(DataFlowConnectionError) as exc:
            resolve_fresh_credential(_RaisingProvider("LEAK-9f3a"))
        msg = str(exc.value)
        assert "LEAK-9f3a" not in msg  # provider secret never surfaces
        assert "RuntimeError" in msg
        assert exc.value.__cause__ is None  # from None — chain severed

    @pytest.mark.parametrize("bad", [None, "", 123, b"x"])
    def test_non_str_or_empty_fails_closed(self, bad):
        with pytest.raises(DataFlowConnectionError, match="non-empty str"):
            resolve_fresh_credential(lambda: bad)


def _fake_dataflow(url: str, credential_provider=None):
    return types.SimpleNamespace(
        _memory_db_uri=None,
        config=types.SimpleNamespace(
            database=types.SimpleNamespace(
                url=url, credential_provider=credential_provider
            )
        ),
    )


class TestMigrationConnectionManagerPsycopg2:
    """The psycopg2 sibling connect path (sync) must honor token auth AND its
    fail-closed error must NOT be swallowed into the :memory: SQLite fallback."""

    def _mgr(self, credential_provider):
        from dataflow.migrations.migration_connection_manager import (
            ConnectionPoolConfig,
            MigrationConnectionManager,
        )

        df = _fake_dataflow(
            "postgresql://u:static@localhost:5432/appdb", credential_provider
        )
        return MigrationConnectionManager(df, ConnectionPoolConfig())

    def test_psycopg2_uses_fresh_token_when_provider_set(self, monkeypatch):
        psycopg2 = pytest.importorskip("psycopg2")
        captured = {}

        def _fake_connect(**kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(autocommit=False, close=lambda: None)

        monkeypatch.setattr(psycopg2, "connect", _fake_connect)
        mgr = self._mgr(_provider("tok-v1"))

        mgr._create_new_connection()

        # Fresh minted token used as the password (static URL password overridden).
        assert captured["password"] == "tok-v1"

    def test_psycopg2_none_provider_uses_static_password(self, monkeypatch):
        psycopg2 = pytest.importorskip("psycopg2")
        captured = {}

        def _fake_connect(**kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(autocommit=False, close=lambda: None)

        monkeypatch.setattr(psycopg2, "connect", _fake_connect)
        mgr = self._mgr(None)

        mgr._create_new_connection()

        assert captured["password"] == "static"  # unchanged behavior

    def test_raising_provider_not_swallowed_into_memory_sqlite(self):
        pytest.importorskip("psycopg2")
        mgr = self._mgr(_RaisingProvider("LEAK-x"))

        # A fail-closed credential error MUST propagate — NOT be caught by the
        # broad except and returned as a silent :memory: SQLite connection.
        with pytest.raises(DataFlowConnectionError):
            mgr._create_new_connection()


class TestRealRuntimePropagation:
    """The load-bearing invariant: a provider bound via credential_provider_scope
    is visible inside a node dispatched by the REAL Kailash runtime (proves the
    runtime's copy_context propagation the standalone bulk nodes depend on)."""

    @pytest.mark.asyncio
    async def test_scope_visible_inside_runtime_dispatched_node(self):
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        try:
            from kailash.nodes.base import Node, register_node

            @register_node(alias="_Cred1741ProbeNode")
            class _Cred1741ProbeNode(Node):
                def get_parameters(self):
                    return {}

                def run(self, **kwargs):
                    return {
                        "has_provider": get_active_credential_provider() is not None
                    }

        except Exception:  # pragma: no cover - registration collision on re-run
            pass

        wf = WorkflowBuilder()
        wf.add_node("_Cred1741ProbeNode", "probe", {})

        with LocalRuntime() as runtime:
            with credential_provider_scope(_provider("tok")):
                results, _ = runtime.execute(wf.build())

            # The provider bound before runtime.execute is visible inside the
            # node's run() — across the runtime's context-snapshot dispatch.
            assert results["probe"]["has_provider"] is True

            # And outside a scope the same node sees None (no leak).
            results2, _ = runtime.execute(wf.build())
            assert results2["probe"]["has_provider"] is False
