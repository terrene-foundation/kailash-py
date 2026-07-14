"""
Unit tests: credential_provider WIRING on the three remaining asyncpg pools
extended by issue #1741 (follow-up to #1737):

  1. ``DatabaseRegistry.get_connection``            (multi-database registry pool)
  2. ``StagingEnvironmentManager._get_connection_pool`` (migration staging pool)
  3. ``SyncTransactionManager`` via ``_open_connection_for_url`` (single connect)

These assert the WIRING (the pool/connection passes the ``connect=`` hook — or,
for the single-connection sync path, mints the token as the ``password=`` kwarg)
and the error-hygiene (a failing create_pool routes through ``sanitize_db_error``
and severs the cause chain). The shared helper's own fail-closed contract is
covered by tests/unit/adapters/test_postgresql_credential_provider.py; real-
Postgres end-to-end by tests/integration/database/test_credential_provider*.py.

Uses a deterministic Protocol-satisfying recorder for asyncpg — NEVER a
MagicMock (rules/testing.md "Protocol-Satisfying Deterministic Adapters").
"""

from __future__ import annotations

from typing import List

import pytest

# asyncpg is a hard DataFlow dependency; gate per unit-tier import rule.
asyncpg = pytest.importorskip("asyncpg")


class RotatingTokenProvider:
    def __init__(self, token: str):
        self._token = token
        self.call_count = 0

    def __call__(self) -> str:
        self.call_count += 1
        return self._token


class _RecordingPool:
    async def close(self):
        pass


class _CreatePoolRecorder:
    """Records asyncpg.create_pool kwargs; returns a trivial pool."""

    def __init__(self, *, raise_exc: Exception | None = None):
        self.calls: List[dict] = []
        self._raise = raise_exc

    async def __call__(self, *args, **kwargs):
        self.calls.append(dict(kwargs))
        if self._raise is not None:
            raise self._raise
        return _RecordingPool()


class _ConnectRecorder:
    """Records asyncpg.connect args/kwargs; returns a trivial connection."""

    def __init__(self):
        self.calls: List[dict] = []
        self.args: List[tuple] = []

    async def __call__(self, *args, **kwargs):
        self.args.append(args)
        self.calls.append(dict(kwargs))
        return object()


# ---------------------------------------------------------------------------
# 1. DatabaseRegistry
# ---------------------------------------------------------------------------
class TestDatabaseRegistryCredentialProvider:
    def _registry_with(self, credential_provider):
        from dataflow.core.database_registry import DatabaseConfig, DatabaseRegistry

        reg = DatabaseRegistry()
        reg.register_database(
            DatabaseConfig(
                name="db1",
                database_url="postgresql://u:static_pw@localhost:5432/appdb",
                database_type="postgresql",
                credential_provider=credential_provider,
            )
        )
        return reg

    @pytest.mark.asyncio
    async def test_connect_hook_injected_when_provider_set(self, monkeypatch):
        recorder = _CreatePoolRecorder()
        monkeypatch.setattr(asyncpg, "create_pool", recorder)
        provider = RotatingTokenProvider("token-v1")
        reg = self._registry_with(provider)

        await reg.get_connection("db1")

        assert len(recorder.calls) == 1
        assert "connect" in recorder.calls[0]
        assert callable(recorder.calls[0]["connect"])

    @pytest.mark.asyncio
    async def test_connect_hook_absent_when_provider_none(self, monkeypatch):
        recorder = _CreatePoolRecorder()
        monkeypatch.setattr(asyncpg, "create_pool", recorder)
        reg = self._registry_with(None)

        await reg.get_connection("db1")

        assert len(recorder.calls) == 1
        assert "connect" not in recorder.calls[0]

    @pytest.mark.asyncio
    async def test_create_pool_failure_is_sanitized_and_cause_severed(
        self, monkeypatch
    ):
        secret_pw = "s3cr3t-PASSWORD-should-not-leak"
        raiser = _CreatePoolRecorder(
            raise_exc=RuntimeError(f"auth failed for password={secret_pw}")
        )
        monkeypatch.setattr(asyncpg, "create_pool", raiser)
        reg = self._registry_with(RotatingTokenProvider("token-v1"))

        with pytest.raises(ConnectionError) as exc_info:
            await reg.get_connection("db1")

        # sanitize_db_error scrubs; ``from None`` severs the cause chain so the
        # raw (credential-bearing) exception cannot render in a traceback.
        assert exc_info.value.__cause__ is None
        assert exc_info.value.__suppress_context__ is True


# ---------------------------------------------------------------------------
# 2. StagingEnvironmentManager
# ---------------------------------------------------------------------------
class TestStagingEnvironmentManagerCredentialProvider:
    def _db_config(self):
        from dataflow.migrations.staging_environment_manager import ProductionDatabase

        return ProductionDatabase(
            host="localhost",
            port=5432,
            database="appdb",
            user="u",
            password="static_pw",
        )

    @pytest.mark.asyncio
    async def test_connect_hook_injected_when_provider_set(self, monkeypatch):
        from dataflow.migrations.staging_environment_manager import (
            StagingEnvironmentManager,
        )

        recorder = _CreatePoolRecorder()
        monkeypatch.setattr(asyncpg, "create_pool", recorder)
        provider = RotatingTokenProvider("token-v1")
        mgr = StagingEnvironmentManager(credential_provider=provider)

        await mgr._get_connection_pool(self._db_config())

        assert len(recorder.calls) == 1
        assert "connect" in recorder.calls[0]
        assert callable(recorder.calls[0]["connect"])

    @pytest.mark.asyncio
    async def test_connect_hook_absent_when_provider_none(self, monkeypatch):
        from dataflow.migrations.staging_environment_manager import (
            StagingEnvironmentManager,
        )

        recorder = _CreatePoolRecorder()
        monkeypatch.setattr(asyncpg, "create_pool", recorder)
        mgr = StagingEnvironmentManager()  # credential_provider defaults None
        assert mgr.credential_provider is None

        await mgr._get_connection_pool(self._db_config())

        assert len(recorder.calls) == 1
        assert "connect" not in recorder.calls[0]

    @pytest.mark.asyncio
    async def test_create_pool_failure_is_sanitized_and_cause_severed(
        self, monkeypatch
    ):
        from dataflow.migrations.staging_environment_manager import (
            StagingEnvironmentManager,
        )

        raiser = _CreatePoolRecorder(
            raise_exc=RuntimeError("auth failed for password=leak-me")
        )
        monkeypatch.setattr(asyncpg, "create_pool", raiser)
        mgr = StagingEnvironmentManager(
            credential_provider=RotatingTokenProvider("token-v1")
        )

        with pytest.raises(ConnectionError) as exc_info:
            await mgr._get_connection_pool(self._db_config())

        assert exc_info.value.__cause__ is None
        assert exc_info.value.__suppress_context__ is True


# ---------------------------------------------------------------------------
# 3. SyncTransactionManager — single-connection path
# ---------------------------------------------------------------------------
class TestSyncTransactionOpenConnectionCredentialProvider:
    @pytest.mark.asyncio
    async def test_provider_token_overrides_dsn_password(self, monkeypatch):
        from dataflow.features.transactions import _open_connection_for_url

        recorder = _ConnectRecorder()
        monkeypatch.setattr(asyncpg, "connect", recorder)
        provider = RotatingTokenProvider("token-v1")

        await _open_connection_for_url(
            "postgresql://u:STALE-DSN-PW@localhost:5432/appdb", provider
        )

        assert provider.call_count == 1
        # The minted token is injected as the ``password=`` kwarg (overrides
        # the stale DSN password); the DSN is still passed positionally.
        assert recorder.calls[0]["password"] == "token-v1"
        assert recorder.args[0][0].startswith("postgresql://")

    @pytest.mark.asyncio
    async def test_absent_provider_plain_connect_no_password_override(
        self, monkeypatch
    ):
        from dataflow.features.transactions import _open_connection_for_url

        recorder = _ConnectRecorder()
        monkeypatch.setattr(asyncpg, "connect", recorder)

        await _open_connection_for_url("postgresql://u:static_pw@localhost:5432/appdb")

        # None path is unchanged: plain asyncpg.connect(url), no password kwarg.
        assert recorder.args[0] == ("postgresql://u:static_pw@localhost:5432/appdb",)
        assert "password" not in recorder.calls[0]
