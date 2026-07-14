"""
Unit tests for CORE-SDK credential_provider WIRING through the CRUD hot-path
pool (issue #1741).

Two wiring links are proven here WITHOUT a live database, using a
Protocol-satisfying deterministic fake for ``asyncpg.create_pool`` (never a
MagicMock — rules/testing.md "Protocol-Satisfying Deterministic Adapters"):

1. ``AsyncSQLDatabaseNode(**config)`` -> ``_create_adapter()`` threads
   ``credential_provider`` into the core ``DatabaseConfig`` so the adapter
   carries it (the DataFlow engine rides the callable in via this kwarg — see
   dataflow/core/engine.py::_get_or_create_async_sql_node).
2. ``PostgreSQLAdapter.connect()`` injects the asyncpg ``connect=`` hook into
   ``create_pool`` kwargs ONLY when ``credential_provider`` is set — the
   None-path stays byte-identical (behavior unchanged, AC of #1737/#1741).

The wrapper's own fail-closed contract is covered in test_credential_provider.py;
real-Postgres end-to-end lives in the DataFlow integration suite.
"""

from __future__ import annotations

from typing import List

import pytest

from kailash.nodes.data.async_sql import (
    DatabaseConfig,
    DatabaseType,
    PostgreSQLAdapter,
)


class RotatingTokenProvider:
    """Deterministic Protocol-satisfying provider — NOT a MagicMock."""

    def __init__(self, token: str):
        self._token = token
        self.call_count = 0

    def __call__(self) -> str:
        self.call_count += 1
        return self._token


class _RecordingPool:
    async def close(self):  # PostgreSQLAdapter.disconnect() calls this
        pass


class _RecordingAsyncpg:
    """Records create_pool kwargs; returns a trivial pool. Deterministic."""

    def __init__(self):
        self.create_pool_kwargs: List[dict] = []
        self.create_pool_args: List[tuple] = []

    async def create_pool(self, *args, **kwargs):
        self.create_pool_args.append(args)
        self.create_pool_kwargs.append(dict(kwargs))
        return _RecordingPool()

    # build_asyncpg_credential_connect only touches .connect (unused here
    # because create_pool is faked and never actually fills the pool).
    async def connect(self, *args, **kwargs):  # pragma: no cover - defensive
        return object()


def _pg_config(credential_provider=None) -> DatabaseConfig:
    return DatabaseConfig(
        type=DatabaseType.POSTGRESQL,
        connection_string="postgresql://u:static_pw@localhost:5432/testdb",
        credential_provider=credential_provider,
    )


@pytest.fixture
def faked_asyncpg(monkeypatch):
    """Patch the ``asyncpg`` module + the loop-drain gate so PostgreSQLAdapter.
    connect() (and _create_adapter's connect+retry) run offline against the
    deterministic recorder — no live database, no MagicMock."""
    import sys

    import kailash.nodes.data.async_sql as async_sql_mod

    fake = _RecordingAsyncpg()
    monkeypatch.setitem(sys.modules, "asyncpg", fake)
    monkeypatch.setattr(
        async_sql_mod,
        "register_pool_drain_on_current_loop",
        lambda *a, **k: None,
    )
    return fake


class TestCoreDatabaseConfigField:
    def test_credential_provider_defaults_to_none(self):
        assert _pg_config().credential_provider is None

    def test_credential_provider_stored_when_provided(self):
        provider = RotatingTokenProvider("token-v1")
        assert _pg_config(provider).credential_provider is provider


class TestCreateAdapterThreadsCredentialProvider:
    """Link 1: AsyncSQLDatabaseNode(**config) -> _create_adapter()."""

    @pytest.mark.asyncio
    async def test_create_adapter_carries_credential_provider(self, faked_asyncpg):
        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        provider = RotatingTokenProvider("token-v1")
        node = AsyncSQLDatabaseNode(
            connection_string="postgresql://u:static_pw@localhost:5432/testdb",
            database_type="postgresql",
            credential_provider=provider,
        )
        adapter = await node._create_adapter()
        assert adapter.config.credential_provider is provider
        # And the wired connect() actually injected the per-connection hook.
        assert "connect" in faked_asyncpg.create_pool_kwargs[0]

    @pytest.mark.asyncio
    async def test_create_adapter_defaults_credential_provider_none(
        self, faked_asyncpg
    ):
        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        node = AsyncSQLDatabaseNode(
            connection_string="postgresql://u:static_pw@localhost:5432/testdb",
            database_type="postgresql",
        )
        adapter = await node._create_adapter()
        assert adapter.config.credential_provider is None
        assert "connect" not in faked_asyncpg.create_pool_kwargs[0]


class TestConnectInjectsHookOnlyWhenProviderSet:
    """Link 2: PostgreSQLAdapter.connect() create_pool kwargs."""

    @pytest.mark.asyncio
    async def test_connect_injects_connect_hook_when_provider_set(self, monkeypatch):
        import kailash.nodes.data.async_sql as async_sql_mod

        fake_asyncpg = _RecordingAsyncpg()
        # connect() does `import asyncpg` at function scope; patch the module
        # object it resolves so create_pool is our recorder.
        monkeypatch.setitem(__import__("sys").modules, "asyncpg", fake_asyncpg)
        # register_pool_drain_on_current_loop is a no-op gate off the app loop.
        monkeypatch.setattr(
            async_sql_mod, "register_pool_drain_on_current_loop", lambda *a, **k: None
        )

        provider = RotatingTokenProvider("token-v1")
        adapter = PostgreSQLAdapter(_pg_config(provider))
        await adapter.connect()

        assert len(fake_asyncpg.create_pool_kwargs) == 1
        assert "connect" in fake_asyncpg.create_pool_kwargs[0]
        assert callable(fake_asyncpg.create_pool_kwargs[0]["connect"])

    @pytest.mark.asyncio
    async def test_connect_omits_hook_when_provider_absent(self, monkeypatch):
        import kailash.nodes.data.async_sql as async_sql_mod

        fake_asyncpg = _RecordingAsyncpg()
        monkeypatch.setitem(__import__("sys").modules, "asyncpg", fake_asyncpg)
        monkeypatch.setattr(
            async_sql_mod, "register_pool_drain_on_current_loop", lambda *a, **k: None
        )

        adapter = PostgreSQLAdapter(_pg_config(credential_provider=None))
        await adapter.connect()

        assert len(fake_asyncpg.create_pool_kwargs) == 1
        # None path is byte-identical to pre-#1741: no connect override.
        assert "connect" not in fake_asyncpg.create_pool_kwargs[0]
