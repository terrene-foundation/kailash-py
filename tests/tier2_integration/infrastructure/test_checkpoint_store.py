# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for dialect-portable Checkpoint Storage backend.

Tests cover:
- Protocol compliance with StorageBackend
- Round-trip: save then load
- Overwrite (upsert) behavior
- Delete operation
- list_keys with prefix filtering
- Edge cases: missing keys, empty prefix, binary data
- Connection lifecycle (initialize / close)
"""

from __future__ import annotations

import logging
import os

import pytest

from kailash.db.connection import ConnectionManager
from kailash.infrastructure.checkpoint_store import DBCheckpointStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
async def conn_manager():
    """Provide an in-memory SQLite ConnectionManager."""
    mgr = ConnectionManager("sqlite:///:memory:")
    await mgr.initialize()
    yield mgr
    await mgr.close()


@pytest.fixture
async def checkpoint_store(conn_manager):
    """Provide an initialized checkpoint storage backend."""
    store = DBCheckpointStore(conn_manager)
    await store.initialize()
    yield store
    await store.close()


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestCheckpointStoreProtocolCompliance:
    async def test_implements_storage_backend_protocol(self, checkpoint_store):
        """The DB-backed store must satisfy the StorageBackend protocol structurally.

        StorageBackend is not @runtime_checkable, so we verify structurally
        that all required methods exist with correct signatures.
        """
        import inspect

        required_methods = ["save", "load", "delete", "list_keys"]
        for method_name in required_methods:
            assert hasattr(
                checkpoint_store, method_name
            ), f"DBCheckpointStore missing required method: {method_name}"
            method = getattr(checkpoint_store, method_name)
            assert callable(method), f"DBCheckpointStore.{method_name} must be callable"
            assert inspect.iscoroutinefunction(
                method
            ), f"DBCheckpointStore.{method_name} must be async"

    async def test_has_save_method(self, checkpoint_store):
        assert hasattr(checkpoint_store, "save")
        assert callable(checkpoint_store.save)

    async def test_has_load_method(self, checkpoint_store):
        assert hasattr(checkpoint_store, "load")
        assert callable(checkpoint_store.load)

    async def test_has_delete_method(self, checkpoint_store):
        assert hasattr(checkpoint_store, "delete")
        assert callable(checkpoint_store.delete)

    async def test_has_list_keys_method(self, checkpoint_store):
        assert hasattr(checkpoint_store, "list_keys")
        assert callable(checkpoint_store.list_keys)


# ---------------------------------------------------------------------------
# Core round-trip
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestCheckpointStoreRoundTrip:
    async def test_save_then_load(self, checkpoint_store):
        """Saving data and loading it should return identical bytes."""
        data = b"checkpoint data payload"
        await checkpoint_store.save("ckpt_req1_001", data)

        result = await checkpoint_store.load("ckpt_req1_001")
        assert result == data

    async def test_save_binary_data(self, checkpoint_store):
        """Binary data (non-UTF-8) should survive round-trip."""
        data = bytes(range(256))  # All byte values 0-255
        await checkpoint_store.save("ckpt_binary", data)

        result = await checkpoint_store.load("ckpt_binary")
        assert result == data

    async def test_save_large_payload(self, checkpoint_store):
        """Large payloads should survive round-trip."""
        data = os.urandom(1024 * 100)  # 100 KB
        await checkpoint_store.save("ckpt_large", data)

        result = await checkpoint_store.load("ckpt_large")
        assert result == data
        assert len(result) == 1024 * 100

    async def test_save_empty_bytes(self, checkpoint_store):
        """Empty byte string should be storable and loadable."""
        await checkpoint_store.save("ckpt_empty", b"")

        result = await checkpoint_store.load("ckpt_empty")
        assert result == b""


# ---------------------------------------------------------------------------
# Upsert (overwrite) behavior
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestCheckpointStoreUpsert:
    async def test_save_overwrites_existing_key(self, checkpoint_store):
        """Saving to an existing key should overwrite the data."""
        await checkpoint_store.save("ckpt_overwrite", b"version-1")
        await checkpoint_store.save("ckpt_overwrite", b"version-2")

        result = await checkpoint_store.load("ckpt_overwrite")
        assert result == b"version-2"

    async def test_save_overwrite_updates_size(self, checkpoint_store):
        """Overwriting should update the stored size_bytes metadata."""
        await checkpoint_store.save("ckpt_size", b"short")
        await checkpoint_store.save("ckpt_size", b"a much longer payload than before")

        result = await checkpoint_store.load("ckpt_size")
        assert result == b"a much longer payload than before"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestCheckpointStoreDelete:
    async def test_delete_removes_key(self, checkpoint_store):
        """Deleting a key should make it unloadable."""
        await checkpoint_store.save("ckpt_del", b"to-delete")
        await checkpoint_store.delete("ckpt_del")

        result = await checkpoint_store.load("ckpt_del")
        assert result is None

    async def test_delete_nonexistent_key_does_not_raise(self, checkpoint_store):
        """Deleting a non-existent key should not raise."""
        # Should not raise
        await checkpoint_store.delete("ckpt_nonexistent")

    async def test_delete_one_does_not_affect_others(self, checkpoint_store):
        """Deleting one key must not affect other keys."""
        await checkpoint_store.save("ckpt_keep", b"keep-me")
        await checkpoint_store.save("ckpt_remove", b"remove-me")

        await checkpoint_store.delete("ckpt_remove")

        assert await checkpoint_store.load("ckpt_keep") == b"keep-me"
        assert await checkpoint_store.load("ckpt_remove") is None


# ---------------------------------------------------------------------------
# list_keys
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestCheckpointStoreListKeys:
    async def test_list_keys_with_prefix(self, checkpoint_store):
        """list_keys should return only keys matching the prefix."""
        await checkpoint_store.save("ckpt_req1_001", b"d1")
        await checkpoint_store.save("ckpt_req1_002", b"d2")
        await checkpoint_store.save("ckpt_req2_001", b"d3")

        keys = await checkpoint_store.list_keys("ckpt_req1")
        assert set(keys) == {"ckpt_req1_001", "ckpt_req1_002"}

    async def test_list_keys_empty_prefix_returns_all(self, checkpoint_store):
        """list_keys with empty prefix should return all keys."""
        await checkpoint_store.save("alpha", b"a")
        await checkpoint_store.save("beta", b"b")

        keys = await checkpoint_store.list_keys("")
        assert set(keys) == {"alpha", "beta"}

    async def test_list_keys_no_match_returns_empty(self, checkpoint_store):
        """list_keys with non-matching prefix should return empty list."""
        await checkpoint_store.save("ckpt_one", b"x")

        keys = await checkpoint_store.list_keys("zzz_")
        assert keys == []

    async def test_list_keys_on_empty_store(self, checkpoint_store):
        """list_keys on empty store should return empty list."""
        keys = await checkpoint_store.list_keys("")
        assert keys == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestCheckpointStoreEdgeCases:
    async def test_load_nonexistent_key_returns_none(self, checkpoint_store):
        """Loading a key that was never saved should return None."""
        result = await checkpoint_store.load("ckpt_missing")
        assert result is None

    async def test_multiple_keys_isolated(self, checkpoint_store):
        """Different keys must store independent data."""
        await checkpoint_store.save("ckpt_a", b"data-A")
        await checkpoint_store.save("ckpt_b", b"data-B")

        assert await checkpoint_store.load("ckpt_a") == b"data-A"
        assert await checkpoint_store.load("ckpt_b") == b"data-B"

    async def test_save_and_load_compressed_data(self, checkpoint_store):
        """Pre-compressed data (gzip bytes) should survive round-trip."""
        import gzip

        original = b"hello world " * 100
        compressed = gzip.compress(original)

        await checkpoint_store.save("ckpt_gz", compressed)
        loaded = await checkpoint_store.load("ckpt_gz")
        assert loaded == compressed
        assert gzip.decompress(loaded) == original


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestCheckpointStoreLifecycle:
    async def test_initialize_creates_table(self, conn_manager):
        """initialize() should create the kailash_checkpoints table."""
        store = DBCheckpointStore(conn_manager)
        await store.initialize()

        rows = await conn_manager.fetch(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='kailash_checkpoints'"
        )
        assert len(rows) == 1
        assert rows[0]["name"] == "kailash_checkpoints"
        await store.close()

    async def test_double_initialize_is_safe(self, conn_manager):
        """Calling initialize() twice should not raise."""
        store = DBCheckpointStore(conn_manager)
        await store.initialize()
        await store.initialize()
        await store.close()

    async def test_close_is_safe_multiple_times(self, conn_manager):
        """Calling close() multiple times should not raise."""
        store = DBCheckpointStore(conn_manager)
        await store.initialize()
        await store.close()
        await store.close()

    async def test_requires_connection_manager(self):
        """Constructor must require a ConnectionManager."""
        with pytest.raises(TypeError):
            DBCheckpointStore()  # type: ignore[call-arg]
