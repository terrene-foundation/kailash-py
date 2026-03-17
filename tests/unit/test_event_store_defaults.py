"""Tests for EventStore default backend resolution (TODO-032).

Verifies:
- No env var, no backend arg -> in-memory (storage_backend is None)
- KAILASH_EVENT_STORE_PATH env var set -> auto-creates SqliteEventStoreBackend
- Explicit backend= object passed -> uses that object
- Explicit backend="memory" -> forces in-memory (storage_backend is None)
- Env var is ignored when explicit backend is provided
"""

import os
import tempfile

import pytest

from kailash.middleware.gateway.event_store import EventStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cancel_flush_task(store: EventStore) -> None:
    """Cancel the background flush task to avoid resource warnings."""
    if store._flush_task is not None:
        store._flush_task.cancel()


# ---------------------------------------------------------------------------
# Default (no env var, no backend)
# ---------------------------------------------------------------------------


class TestDefaultInMemory:
    """When no backend is specified and no env var is set."""

    def test_storage_backend_is_none(self, monkeypatch):
        monkeypatch.delenv("KAILASH_EVENT_STORE_PATH", raising=False)
        store = EventStore()
        try:
            assert store.storage_backend is None
        finally:
            _cancel_flush_task(store)


# ---------------------------------------------------------------------------
# Env var triggers SQLite
# ---------------------------------------------------------------------------


class TestEnvVarSqlite:
    """KAILASH_EVENT_STORE_PATH triggers SqliteEventStoreBackend."""

    def test_env_var_creates_sqlite_backend(self, monkeypatch, tmp_path):
        db_path = str(tmp_path / "events.db")
        monkeypatch.setenv("KAILASH_EVENT_STORE_PATH", db_path)

        store = EventStore()
        try:
            assert store.storage_backend is not None

            from kailash.middleware.gateway.event_store_sqlite import (
                SqliteEventStoreBackend,
            )

            assert isinstance(store.storage_backend, SqliteEventStoreBackend)
            assert store.storage_backend.db_path == db_path
        finally:
            _cancel_flush_task(store)

    def test_env_var_creates_db_file(self, monkeypatch, tmp_path):
        db_path = str(tmp_path / "subdir" / "events.db")
        monkeypatch.setenv("KAILASH_EVENT_STORE_PATH", db_path)

        store = EventStore()
        try:
            assert os.path.exists(db_path)
        finally:
            _cancel_flush_task(store)

    def test_env_var_empty_string_stays_in_memory(self, monkeypatch):
        """Empty string is falsy, so no SQLite backend is created."""
        monkeypatch.setenv("KAILASH_EVENT_STORE_PATH", "")
        store = EventStore()
        try:
            assert store.storage_backend is None
        finally:
            _cancel_flush_task(store)


# ---------------------------------------------------------------------------
# Explicit backend object
# ---------------------------------------------------------------------------


class TestExplicitBackend:
    """When a backend instance is explicitly passed."""

    def test_explicit_backend_used_as_is(self, monkeypatch):
        monkeypatch.delenv("KAILASH_EVENT_STORE_PATH", raising=False)

        class FakeBackend:
            pass

        backend = FakeBackend()
        store = EventStore(storage_backend=backend)
        try:
            assert store.storage_backend is backend
        finally:
            _cancel_flush_task(store)

    def test_explicit_backend_ignores_env_var(self, monkeypatch, tmp_path):
        """Even if env var is set, explicit backend takes precedence."""
        db_path = str(tmp_path / "should_not_create.db")
        monkeypatch.setenv("KAILASH_EVENT_STORE_PATH", db_path)

        class FakeBackend:
            pass

        backend = FakeBackend()
        store = EventStore(storage_backend=backend)
        try:
            assert store.storage_backend is backend
            assert not os.path.exists(db_path)
        finally:
            _cancel_flush_task(store)


# ---------------------------------------------------------------------------
# Explicit "memory" string
# ---------------------------------------------------------------------------


class TestExplicitMemory:
    """When storage_backend="memory" is passed explicitly."""

    def test_memory_string_forces_in_memory(self, monkeypatch):
        monkeypatch.delenv("KAILASH_EVENT_STORE_PATH", raising=False)
        store = EventStore(storage_backend="memory")
        try:
            assert store.storage_backend is None
        finally:
            _cancel_flush_task(store)

    def test_memory_string_overrides_env_var(self, monkeypatch, tmp_path):
        """Explicit 'memory' wins even if env var is set."""
        db_path = str(tmp_path / "should_not_create.db")
        monkeypatch.setenv("KAILASH_EVENT_STORE_PATH", db_path)

        store = EventStore(storage_backend="memory")
        try:
            assert store.storage_backend is None
            assert not os.path.exists(db_path)
        finally:
            _cancel_flush_task(store)


# ---------------------------------------------------------------------------
# _resolve_backend unit tests
# ---------------------------------------------------------------------------


class TestResolveBackend:
    """Direct tests of the static _resolve_backend method."""

    def test_none_no_env(self, monkeypatch):
        monkeypatch.delenv("KAILASH_EVENT_STORE_PATH", raising=False)
        assert EventStore._resolve_backend(None) is None

    def test_none_with_env(self, monkeypatch, tmp_path):
        db_path = str(tmp_path / "resolve.db")
        monkeypatch.setenv("KAILASH_EVENT_STORE_PATH", db_path)

        from kailash.middleware.gateway.event_store_sqlite import (
            SqliteEventStoreBackend,
        )

        result = EventStore._resolve_backend(None)
        assert isinstance(result, SqliteEventStoreBackend)

    def test_memory_string(self, monkeypatch):
        monkeypatch.delenv("KAILASH_EVENT_STORE_PATH", raising=False)
        assert EventStore._resolve_backend("memory") is None

    def test_memory_string_with_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KAILASH_EVENT_STORE_PATH", str(tmp_path / "x.db"))
        assert EventStore._resolve_backend("memory") is None

    def test_explicit_object(self):
        sentinel = object()
        assert EventStore._resolve_backend(sentinel) is sentinel
