# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for dialect-portable IdempotencyStore backend.

Tests cover:
- Table/index creation via initialize()
- get: SELECT by key with TTL expiry enforcement
- set: INSERT (first-writer-wins via conflict ignore)
- try_claim: Atomic claim with placeholder response
- store_result: UPDATE with actual response data
- release_claim: DELETE to allow retry
- cleanup: DELETE expired entries
- TTL enforcement: expired entries are not returned by get
- Edge cases: missing keys, duplicate claims, JSON round-trip
- Connection lifecycle (initialize / close)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import pytest

from kailash.db.connection import ConnectionManager

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
async def idempotency_store(conn_manager):
    """Provide an initialized DBIdempotencyStore backend."""
    from kailash.infrastructure.idempotency_store import DBIdempotencyStore

    store = DBIdempotencyStore(conn_manager)
    await store.initialize()
    yield store
    await store.close()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
class TestIdempotencyStoreLifecycle:
    async def test_initialize_creates_table(self, conn_manager):
        """initialize() should create the kailash_idempotency table."""
        from kailash.infrastructure.idempotency_store import DBIdempotencyStore

        store = DBIdempotencyStore(conn_manager)
        await store.initialize()

        rows = await conn_manager.fetch(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='kailash_idempotency'"
        )
        assert len(rows) == 1
        assert rows[0]["name"] == "kailash_idempotency"
        await store.close()

    async def test_initialize_creates_expires_index(self, conn_manager):
        """initialize() should create the expires_at index."""
        from kailash.infrastructure.idempotency_store import DBIdempotencyStore

        store = DBIdempotencyStore(conn_manager)
        await store.initialize()

        rows = await conn_manager.fetch(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_idempotency_expires'"
        )
        assert len(rows) == 1
        assert rows[0]["name"] == "idx_idempotency_expires"
        await store.close()

    async def test_double_initialize_is_safe(self, conn_manager):
        """Calling initialize() twice should not raise."""
        from kailash.infrastructure.idempotency_store import DBIdempotencyStore

        store = DBIdempotencyStore(conn_manager)
        await store.initialize()
        await store.initialize()  # Should be idempotent
        await store.close()

    async def test_close_is_safe_multiple_times(self, conn_manager):
        """Calling close() multiple times should not raise."""
        from kailash.infrastructure.idempotency_store import DBIdempotencyStore

        store = DBIdempotencyStore(conn_manager)
        await store.initialize()
        await store.close()
        await store.close()

    async def test_requires_connection_manager(self):
        """Constructor must require a ConnectionManager."""
        from kailash.infrastructure.idempotency_store import DBIdempotencyStore

        with pytest.raises(TypeError):
            DBIdempotencyStore()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# set and get
# ---------------------------------------------------------------------------
class TestIdempotencyStoreSetAndGet:
    async def test_set_then_get_returns_stored_data(self, idempotency_store):
        """Setting a key and getting it should return the stored data."""
        await idempotency_store.set(
            key="req-001",
            fingerprint="fp-abc",
            response_data={"result": "ok"},
            status_code=200,
            headers={"Content-Type": "application/json"},
            ttl_seconds=3600,
        )

        result = await idempotency_store.get("req-001")
        assert result is not None
        assert result["idempotency_key"] == "req-001"
        assert result["fingerprint"] == "fp-abc"
        assert result["status_code"] == 200

    async def test_get_returns_response_data_as_json(self, idempotency_store):
        """Response data should be stored as JSON and retrievable."""
        response = {"items": [1, 2, 3], "total": 3}
        await idempotency_store.set(
            key="req-json",
            fingerprint="fp-json",
            response_data=response,
            status_code=200,
            headers={},
            ttl_seconds=3600,
        )

        result = await idempotency_store.get("req-json")
        assert result is not None
        stored_data = json.loads(result["response_data"])
        assert stored_data == response

    async def test_get_returns_headers_as_json(self, idempotency_store):
        """Headers should be stored as JSON and retrievable."""
        headers = {"X-Custom": "value", "Content-Type": "text/plain"}
        await idempotency_store.set(
            key="req-headers",
            fingerprint="fp-hdrs",
            response_data={"ok": True},
            status_code=201,
            headers=headers,
            ttl_seconds=3600,
        )

        result = await idempotency_store.get("req-headers")
        assert result is not None
        stored_headers = json.loads(result["headers"])
        assert stored_headers == headers

    async def test_get_nonexistent_key_returns_none(self, idempotency_store):
        """Getting a key that does not exist should return None."""
        result = await idempotency_store.get("nonexistent-key")
        assert result is None

    async def test_set_first_writer_wins(self, idempotency_store):
        """Setting the same key twice should keep the first value (INSERT OR IGNORE)."""
        await idempotency_store.set(
            key="req-dup",
            fingerprint="fp-first",
            response_data={"version": 1},
            status_code=200,
            headers={},
            ttl_seconds=3600,
        )
        await idempotency_store.set(
            key="req-dup",
            fingerprint="fp-second",
            response_data={"version": 2},
            status_code=201,
            headers={},
            ttl_seconds=3600,
        )

        result = await idempotency_store.get("req-dup")
        assert result is not None
        # First writer should win
        assert result["fingerprint"] == "fp-first"
        assert result["status_code"] == 200


# ---------------------------------------------------------------------------
# TTL / expiry
# ---------------------------------------------------------------------------
class TestIdempotencyStoreTTL:
    async def test_expired_key_returns_none(self, idempotency_store, conn_manager):
        """get should return None for expired keys."""
        # Insert with a past expires_at by manipulating the DB directly
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        await conn_manager.execute(
            "INSERT INTO kailash_idempotency "
            "(idempotency_key, fingerprint, response_data, status_code, headers, "
            "created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            "expired-key",
            "fp-exp",
            '{"expired": true}',
            200,
            "{}",
            now,
            past,
        )

        result = await idempotency_store.get("expired-key")
        assert result is None

    async def test_non_expired_key_is_returned(self, idempotency_store):
        """get should return a key that has not expired."""
        await idempotency_store.set(
            key="fresh-key",
            fingerprint="fp-fresh",
            response_data={"fresh": True},
            status_code=200,
            headers={},
            ttl_seconds=3600,  # 1 hour from now
        )

        result = await idempotency_store.get("fresh-key")
        assert result is not None
        assert result["idempotency_key"] == "fresh-key"

    async def test_set_computes_expires_at_from_ttl(
        self, idempotency_store, conn_manager
    ):
        """set should compute expires_at = now + ttl_seconds."""
        before = datetime.now(timezone.utc)
        await idempotency_store.set(
            key="ttl-check",
            fingerprint="fp-ttl",
            response_data={},
            status_code=200,
            headers={},
            ttl_seconds=7200,  # 2 hours
        )
        after = datetime.now(timezone.utc)

        row = await conn_manager.fetchone(
            "SELECT expires_at FROM kailash_idempotency WHERE idempotency_key = ?",
            "ttl-check",
        )
        assert row is not None
        expires_at = datetime.fromisoformat(row["expires_at"])

        # expires_at should be roughly before + 7200s to after + 7200s
        expected_min = before + timedelta(seconds=7200)
        expected_max = after + timedelta(seconds=7200)
        assert expected_min <= expires_at <= expected_max


# ---------------------------------------------------------------------------
# try_claim and store_result
# ---------------------------------------------------------------------------
class TestIdempotencyStoreClaim:
    async def test_try_claim_returns_true_on_first_call(self, idempotency_store):
        """try_claim should return True when the key is not yet claimed."""
        claimed = await idempotency_store.try_claim(
            key="claim-001",
            fingerprint="fp-claim",
        )
        assert claimed is True

    async def test_try_claim_returns_false_on_second_call(self, idempotency_store):
        """try_claim should return False when the key is already claimed."""
        await idempotency_store.try_claim(key="claim-002", fingerprint="fp-claim")
        claimed_again = await idempotency_store.try_claim(
            key="claim-002", fingerprint="fp-claim-2"
        )
        assert claimed_again is False

    async def test_try_claim_sets_placeholder_response(self, idempotency_store):
        """try_claim should insert a row with status_code=0 and empty response."""
        await idempotency_store.try_claim(key="claim-ph", fingerprint="fp-ph")

        result = await idempotency_store.get("claim-ph")
        assert result is not None
        assert result["status_code"] == 0

    async def test_store_result_updates_claimed_entry(self, idempotency_store):
        """store_result should update the placeholder with actual data."""
        await idempotency_store.try_claim(key="claim-res", fingerprint="fp-res")
        await idempotency_store.store_result(
            key="claim-res",
            response_data={"result": "computed"},
            status_code=200,
            headers={"X-Req-Id": "abc"},
        )

        result = await idempotency_store.get("claim-res")
        assert result is not None
        assert result["status_code"] == 200
        stored_data = json.loads(result["response_data"])
        assert stored_data == {"result": "computed"}
        stored_headers = json.loads(result["headers"])
        assert stored_headers == {"X-Req-Id": "abc"}


# ---------------------------------------------------------------------------
# release_claim
# ---------------------------------------------------------------------------
class TestIdempotencyStoreReleaseClaim:
    async def test_release_claim_deletes_entry(self, idempotency_store):
        """release_claim should delete the entry so it can be retried."""
        await idempotency_store.try_claim(key="release-001", fingerprint="fp-rel")

        # Verify it exists
        result = await idempotency_store.get("release-001")
        assert result is not None

        # Release
        await idempotency_store.release_claim("release-001")

        # Should be gone
        result = await idempotency_store.get("release-001")
        assert result is None

    async def test_release_claim_allows_reclaim(self, idempotency_store):
        """After release_claim, the same key should be claimable again."""
        await idempotency_store.try_claim(key="reclaim-001", fingerprint="fp-1")
        await idempotency_store.release_claim("reclaim-001")

        reclaimed = await idempotency_store.try_claim(
            key="reclaim-001", fingerprint="fp-2"
        )
        assert reclaimed is True

    async def test_release_claim_nonexistent_does_not_raise(self, idempotency_store):
        """Releasing a non-existent claim should not raise."""
        await idempotency_store.release_claim("nonexistent-claim")


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------
class TestIdempotencyStoreCleanup:
    async def test_cleanup_removes_expired_entries(
        self, idempotency_store, conn_manager
    ):
        """cleanup should delete entries whose expires_at is before the threshold."""
        # Insert one expired and one fresh entry directly
        past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        now = datetime.now(timezone.utc).isoformat()

        await conn_manager.execute(
            "INSERT INTO kailash_idempotency "
            "(idempotency_key, fingerprint, response_data, status_code, headers, "
            "created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            "expired-cleanup",
            "fp-exp",
            "{}",
            200,
            "{}",
            now,
            past,
        )
        await conn_manager.execute(
            "INSERT INTO kailash_idempotency "
            "(idempotency_key, fingerprint, response_data, status_code, headers, "
            "created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            "fresh-cleanup",
            "fp-fresh",
            "{}",
            200,
            "{}",
            now,
            future,
        )

        await idempotency_store.cleanup()

        # Expired should be gone
        expired = await conn_manager.fetchone(
            "SELECT * FROM kailash_idempotency WHERE idempotency_key = ?",
            "expired-cleanup",
        )
        assert expired is None

        # Fresh should still exist
        fresh = await conn_manager.fetchone(
            "SELECT * FROM kailash_idempotency WHERE idempotency_key = ?",
            "fresh-cleanup",
        )
        assert fresh is not None

    async def test_cleanup_with_explicit_before_timestamp(
        self, idempotency_store, conn_manager
    ):
        """cleanup(before=...) should use the provided timestamp as threshold."""
        now = datetime.now(timezone.utc).isoformat()
        future_1h = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        future_3h = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()

        # Entry that expires in 1 hour
        await conn_manager.execute(
            "INSERT INTO kailash_idempotency "
            "(idempotency_key, fingerprint, response_data, status_code, headers, "
            "created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            "soon-expire",
            "fp-soon",
            "{}",
            200,
            "{}",
            now,
            future_1h,
        )
        # Entry that expires in 3 hours
        await conn_manager.execute(
            "INSERT INTO kailash_idempotency "
            "(idempotency_key, fingerprint, response_data, status_code, headers, "
            "created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            "later-expire",
            "fp-later",
            "{}",
            200,
            "{}",
            now,
            future_3h,
        )

        # Cleanup with a threshold of 2 hours from now
        threshold = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        await idempotency_store.cleanup(before=threshold)

        # soon-expire (1h) should be removed because 1h < 2h threshold
        soon = await conn_manager.fetchone(
            "SELECT * FROM kailash_idempotency WHERE idempotency_key = ?",
            "soon-expire",
        )
        assert soon is None

        # later-expire (3h) should remain because 3h > 2h threshold
        later = await conn_manager.fetchone(
            "SELECT * FROM kailash_idempotency WHERE idempotency_key = ?",
            "later-expire",
        )
        assert later is not None

    async def test_cleanup_empty_table_does_not_raise(self, idempotency_store):
        """cleanup on empty table should not raise."""
        await idempotency_store.cleanup()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
class TestIdempotencyStoreEdgeCases:
    async def test_complex_response_data_roundtrip(self, idempotency_store):
        """Complex nested response data should survive JSON round-trip."""
        response = {
            "data": {"users": [{"id": 1, "name": "Alice"}]},
            "pagination": {"page": 1, "total": 100},
            "null_field": None,
        }
        await idempotency_store.set(
            key="complex-resp",
            fingerprint="fp-complex",
            response_data=response,
            status_code=200,
            headers={},
            ttl_seconds=3600,
        )

        result = await idempotency_store.get("complex-resp")
        assert result is not None
        assert json.loads(result["response_data"]) == response

    async def test_multiple_keys_are_isolated(self, idempotency_store):
        """Different keys must store independent data."""
        await idempotency_store.set(
            key="iso-1",
            fingerprint="fp-1",
            response_data={"id": 1},
            status_code=200,
            headers={},
            ttl_seconds=3600,
        )
        await idempotency_store.set(
            key="iso-2",
            fingerprint="fp-2",
            response_data={"id": 2},
            status_code=201,
            headers={},
            ttl_seconds=3600,
        )

        r1 = await idempotency_store.get("iso-1")
        r2 = await idempotency_store.get("iso-2")
        assert r1 is not None and r2 is not None
        assert r1["fingerprint"] == "fp-1"
        assert r2["fingerprint"] == "fp-2"
        assert r1["status_code"] == 200
        assert r2["status_code"] == 201

    async def test_unicode_in_response_data(self, idempotency_store):
        """Unicode characters in response data should survive storage."""
        response = {"message": "Hello \u00e9\u00e8\u00ea \u2603 \U0001f600"}
        await idempotency_store.set(
            key="unicode-resp",
            fingerprint="fp-uni",
            response_data=response,
            status_code=200,
            headers={},
            ttl_seconds=3600,
        )

        result = await idempotency_store.get("unicode-resp")
        assert result is not None
        assert json.loads(result["response_data"]) == response
