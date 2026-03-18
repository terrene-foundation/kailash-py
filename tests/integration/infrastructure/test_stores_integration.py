# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Level 1 integration tests: all 5 infrastructure stores against real databases.

Each test class exercises one store's full API against every configured
dialect (SQLite, PostgreSQL, MySQL) via the parameterized ``conn`` fixture
defined in conftest.py.

NO MOCKING -- all operations hit a real database connection.

Markers:
    @pytest.mark.integration  -- Tier 2 integration test
    @pytest.mark.asyncio      -- async test (auto mode configured in pytest.ini)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from kailash.db.connection import ConnectionManager
from kailash.infrastructure.checkpoint_store import DBCheckpointStore
from kailash.infrastructure.dlq import DBDeadLetterQueue
from kailash.infrastructure.event_store import DBEventStoreBackend
from kailash.infrastructure.execution_store import DBExecutionStore
from kailash.infrastructure.idempotency_store import DBIdempotencyStore

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ===================================================================
# EventStore
# ===================================================================
class TestEventStoreIntegration:
    """Validate DBEventStoreBackend round-trip against all 3 dialects."""

    async def _make_store(self, conn: ConnectionManager) -> DBEventStoreBackend:
        store = DBEventStoreBackend(conn)
        await store.initialize()
        return store

    # -- append and get --------------------------------------------------

    async def test_append_and_get_basic(self, conn: ConnectionManager) -> None:
        """Append 5 events to a stream and retrieve them in sequence order."""
        store = await self._make_store(conn)
        key = "events:test-basic"
        events = [{"type": "request.started", "data": {"step": i}} for i in range(5)]
        await store.append(key, events)

        retrieved = await store.get(key)
        assert len(retrieved) == 5, f"Expected 5 events, got {len(retrieved)}"
        for i, evt in enumerate(retrieved):
            assert evt["type"] == "request.started"
            assert evt["data"]["step"] == i

    async def test_append_100_events_round_trip(self, conn: ConnectionManager) -> None:
        """Append 100 events in batches and verify all are returned in order."""
        store = await self._make_store(conn)
        key = "events:bulk-100"

        # Append in 10 batches of 10
        for batch in range(10):
            events = [
                {"type": f"batch.{batch}", "data": {"seq": batch * 10 + i}}
                for i in range(10)
            ]
            await store.append(key, events)

        all_events = await store.get(key)
        assert len(all_events) == 100, f"Expected 100, got {len(all_events)}"

        # Verify monotonic data.seq
        for i, evt in enumerate(all_events):
            assert (
                evt["data"]["seq"] == i
            ), f"Event at position {i} has seq={evt['data']['seq']}"

    async def test_get_empty_stream_returns_empty(
        self, conn: ConnectionManager
    ) -> None:
        """Querying a non-existent stream returns an empty list, not an error."""
        store = await self._make_store(conn)
        result = await store.get("events:nonexistent-stream")
        assert result == [], f"Expected [], got {result!r}"

    async def test_append_empty_list_is_noop(self, conn: ConnectionManager) -> None:
        """Appending an empty list must not create any rows."""
        store = await self._make_store(conn)
        key = "events:empty-append"
        await store.append(key, [])
        assert await store.count(key) == 0

    # -- get_after -------------------------------------------------------

    async def test_get_after_returns_tail(self, conn: ConnectionManager) -> None:
        """get_after(key, n) returns events with sequence > n."""
        store = await self._make_store(conn)
        key = "events:get-after"
        events = [{"type": "step", "data": {"i": i}} for i in range(10)]
        await store.append(key, events)

        tail = await store.get_after(key, after_sequence=5)
        # Sequences are 1..10 internally; after_sequence=5 yields 6..10
        assert len(tail) == 5, f"Expected 5 tail events, got {len(tail)}"
        # Verify the first tail event is what we expect
        assert tail[0]["data"]["i"] == 5  # 0-indexed data, seq 6

    async def test_get_after_beyond_max_returns_empty(
        self, conn: ConnectionManager
    ) -> None:
        """get_after with a sequence past the end returns nothing."""
        store = await self._make_store(conn)
        key = "events:get-after-past"
        await store.append(key, [{"type": "single", "data": {}}])
        result = await store.get_after(key, after_sequence=9999)
        assert result == []

    # -- delete_before ---------------------------------------------------

    async def test_delete_before_removes_old_events(
        self, conn: ConnectionManager
    ) -> None:
        """Events with timestamps before the cutoff are deleted."""
        store = await self._make_store(conn)
        key = "events:gc"

        # Insert events with old timestamp directly via the store's conn
        old_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        recent_ts = datetime.now(timezone.utc).isoformat()

        # Manually insert with controlled timestamps
        for seq, ts in [(1, old_ts), (2, old_ts), (3, recent_ts)]:
            data_json = json.dumps({"type": "gc-event", "data": {"seq": seq}})
            await conn.execute(
                "INSERT INTO kailash_events "
                "(stream_key, sequence, event_type, data, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                key,
                seq,
                "gc-event",
                data_json,
                ts,
            )

        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        deleted = await store.delete_before(cutoff)
        assert deleted == 2, f"Expected 2 deleted, got {deleted}"

        remaining = await store.get(key)
        assert len(remaining) == 1
        assert remaining[0]["data"]["seq"] == 3

    async def test_delete_before_no_match(self, conn: ConnectionManager) -> None:
        """delete_before returns 0 when no events match the cutoff."""
        store = await self._make_store(conn)
        key = "events:gc-none"
        await store.append(key, [{"type": "fresh", "data": {}}])
        deleted = await store.delete_before("2000-01-01T00:00:00+00:00")
        assert deleted == 0

    # -- count and stream_keys -------------------------------------------

    async def test_count(self, conn: ConnectionManager) -> None:
        """count() returns correct event count per stream."""
        store = await self._make_store(conn)
        await store.append("events:cnt-a", [{"type": "x"} for _ in range(3)])
        await store.append("events:cnt-b", [{"type": "x"} for _ in range(7)])

        assert await store.count("events:cnt-a") == 3
        assert await store.count("events:cnt-b") == 7
        assert await store.count("events:cnt-missing") == 0

    async def test_stream_keys(self, conn: ConnectionManager) -> None:
        """stream_keys() returns all distinct keys in sorted order."""
        store = await self._make_store(conn)
        await store.append("events:gamma", [{"type": "x"}])
        await store.append("events:alpha", [{"type": "x"}])
        await store.append("events:beta", [{"type": "x"}])

        keys = await store.stream_keys()
        assert keys == ["events:alpha", "events:beta", "events:gamma"]


# ===================================================================
# CheckpointStore
# ===================================================================
class TestCheckpointStoreIntegration:
    """Validate DBCheckpointStore with binary data against all dialects."""

    async def _make_store(self, conn: ConnectionManager) -> DBCheckpointStore:
        store = DBCheckpointStore(conn)
        await store.initialize()
        return store

    async def test_save_and_load_small_blob(self, conn: ConnectionManager) -> None:
        """Save and load a small binary payload."""
        store = await self._make_store(conn)
        payload = b"hello world checkpoint"
        await store.save("cp:small", payload)

        loaded = await store.load("cp:small")
        assert loaded is not None, "load returned None for existing key"
        assert loaded == payload, "Loaded data does not match saved data"

    async def test_save_and_load_1mb_binary_blob(self, conn: ConnectionManager) -> None:
        """Save a 1 MB binary blob, reload, and verify byte-for-byte identity."""
        store = await self._make_store(conn)
        # Generate 1 MB of pseudo-random data (deterministic seed via bytes range)
        one_mb = bytes(range(256)) * 4096  # 256 * 4096 = 1,048,576 = 1 MB
        assert len(one_mb) == 1_048_576

        await store.save("cp:1mb", one_mb)
        loaded = await store.load("cp:1mb")

        assert loaded is not None, "load returned None for 1 MB checkpoint"
        assert len(loaded) == 1_048_576, f"Loaded size: {len(loaded)}"
        assert loaded == one_mb, "1 MB blob content mismatch"

    async def test_load_nonexistent_returns_none(self, conn: ConnectionManager) -> None:
        """Loading a key that does not exist returns None."""
        store = await self._make_store(conn)
        assert await store.load("cp:does-not-exist") is None

    async def test_save_overwrites_existing(self, conn: ConnectionManager) -> None:
        """Saving to the same key overwrites the previous data."""
        store = await self._make_store(conn)
        await store.save("cp:overwrite", b"original")
        await store.save("cp:overwrite", b"updated")

        loaded = await store.load("cp:overwrite")
        assert loaded == b"updated"

    async def test_delete_removes_checkpoint(self, conn: ConnectionManager) -> None:
        """delete() removes the key; subsequent load returns None."""
        store = await self._make_store(conn)
        await store.save("cp:delete-me", b"data")
        await store.delete("cp:delete-me")
        assert await store.load("cp:delete-me") is None

    async def test_delete_nonexistent_is_noop(self, conn: ConnectionManager) -> None:
        """delete() on a missing key does not raise."""
        store = await self._make_store(conn)
        await store.delete("cp:never-existed")  # Must not raise

    async def test_list_keys_with_prefix(self, conn: ConnectionManager) -> None:
        """list_keys() filters by prefix and returns sorted keys."""
        store = await self._make_store(conn)
        await store.save("cp:run-001:node-a", b"a")
        await store.save("cp:run-001:node-b", b"b")
        await store.save("cp:run-002:node-a", b"c")

        keys_001 = await store.list_keys("cp:run-001")
        assert keys_001 == ["cp:run-001:node-a", "cp:run-001:node-b"]

        keys_all = await store.list_keys("cp:")
        assert len(keys_all) == 3

    async def test_gzip_data_detected_as_compressed(
        self, conn: ConnectionManager
    ) -> None:
        """Data starting with gzip magic bytes is flagged as compressed."""
        store = await self._make_store(conn)
        import gzip

        raw = b"checkpoint data to compress" * 100
        compressed = gzip.compress(raw)
        await store.save("cp:gzip", compressed)

        loaded = await store.load("cp:gzip")
        assert loaded is not None
        assert gzip.decompress(loaded) == raw


# ===================================================================
# Dead Letter Queue
# ===================================================================
class TestDLQIntegration:
    """Validate DBDeadLetterQueue lifecycle against all dialects."""

    async def _make_store(self, conn: ConnectionManager) -> DBDeadLetterQueue:
        store = DBDeadLetterQueue(conn, base_delay=0.01)
        await store.initialize()
        return store

    async def test_enqueue_and_dequeue_ready(self, conn: ConnectionManager) -> None:
        """Enqueued items with next_retry_at=now should be immediately dequeue-able."""
        dlq = await self._make_store(conn)
        item_id = await dlq.enqueue("wf-1", "boom", {"key": "value"})
        assert item_id, "enqueue must return a non-empty item ID"

        ready = await dlq.dequeue_ready()
        assert len(ready) >= 1, "Newly enqueued item should be immediately ready"
        found = any(item["id"] == item_id for item in ready)
        assert found, f"Item {item_id} not found in dequeue_ready results"

    async def test_mark_retrying_then_success(self, conn: ConnectionManager) -> None:
        """Full lifecycle: enqueue -> mark_retrying -> mark_success."""
        dlq = await self._make_store(conn)
        item_id = await dlq.enqueue("wf-lifecycle", "error msg", "payload")

        await dlq.mark_retrying(item_id)
        # After mark_retrying, dequeue_ready should not return it
        ready = await dlq.dequeue_ready()
        retrying_ids = [r["id"] for r in ready if r["status"] == "retrying"]
        assert item_id not in retrying_ids

        await dlq.mark_success(item_id)
        stats = await dlq.get_stats()
        assert stats["succeeded"] >= 1

    async def test_mark_failure_escalates_to_permanent(
        self, conn: ConnectionManager
    ) -> None:
        """After max_retries failures, status becomes permanent_failure."""
        dlq = await self._make_store(conn)
        item_id = await dlq.enqueue("wf-fail", "err", "data", max_retries=3)

        # Fail 3 times
        for i in range(3):
            await dlq.mark_failure(item_id)

        stats = await dlq.get_stats()
        assert (
            stats["permanent_failure"] >= 1
        ), f"Expected at least 1 permanent_failure, got stats: {stats}"

    async def test_mark_failure_below_max_stays_pending(
        self, conn: ConnectionManager
    ) -> None:
        """Failures below max_retries keep the item in pending status."""
        dlq = await self._make_store(conn)
        item_id = await dlq.enqueue("wf-retry", "err", "data", max_retries=5)

        await dlq.mark_failure(item_id)
        await dlq.mark_failure(item_id)

        # Item should still be pending (retry_count=2, max_retries=5)
        stats = await dlq.get_stats()
        assert stats["pending"] >= 1

    async def test_get_stats_empty(self, conn: ConnectionManager) -> None:
        """Stats on an empty DLQ return all zeroes."""
        dlq = await self._make_store(conn)
        stats = await dlq.get_stats()
        assert stats["total"] == 0
        assert stats["pending"] == 0
        assert stats["retrying"] == 0
        assert stats["succeeded"] == 0
        assert stats["permanent_failure"] == 0

    async def test_clear_removes_all(self, conn: ConnectionManager) -> None:
        """clear() deletes all items from the queue."""
        dlq = await self._make_store(conn)
        for i in range(5):
            await dlq.enqueue(f"wf-{i}", f"err-{i}", f"payload-{i}")

        stats = await dlq.get_stats()
        assert stats["total"] == 5

        await dlq.clear()

        stats_after = await dlq.get_stats()
        assert stats_after["total"] == 0

    async def test_enqueue_json_serializable_payload(
        self, conn: ConnectionManager
    ) -> None:
        """Non-string payloads are JSON-serialized on enqueue."""
        dlq = await self._make_store(conn)
        payload = {"nested": {"list": [1, 2, 3], "flag": True}}
        item_id = await dlq.enqueue("wf-json", "error", payload)

        ready = await dlq.dequeue_ready()
        item = next(r for r in ready if r["id"] == item_id)
        # payload is stored as JSON string
        parsed = json.loads(item["payload"])
        assert parsed == payload


# ===================================================================
# ExecutionStore
# ===================================================================
class TestExecutionStoreIntegration:
    """Validate DBExecutionStore tracking against all dialects."""

    async def _make_store(self, conn: ConnectionManager) -> DBExecutionStore:
        store = DBExecutionStore(conn)
        await store.initialize()
        return store

    async def test_record_start_and_get(self, conn: ConnectionManager) -> None:
        """Record a workflow start and retrieve the execution record."""
        store = await self._make_store(conn)
        run_id = "run-001"
        await store.record_start(
            run_id=run_id,
            workflow_id="wf-hello",
            parameters={"input": "world"},
            worker_id="worker-A",
        )

        record = await store.get_execution(run_id)
        assert record is not None, f"get_execution returned None for {run_id}"
        assert record["run_id"] == run_id
        assert record["workflow_id"] == "wf-hello"
        assert record["status"] == "pending"
        assert record["worker_id"] == "worker-A"
        assert record["started_at"] is not None

    async def test_record_completion(self, conn: ConnectionManager) -> None:
        """Record start then completion; status should be 'completed'."""
        store = await self._make_store(conn)
        run_id = "run-complete-001"
        await store.record_start(run_id=run_id, workflow_id="wf-complete")
        await store.record_completion(run_id=run_id, results={"output": 42})

        record = await store.get_execution(run_id)
        assert record is not None
        assert record["status"] == "completed"
        assert record["completed_at"] is not None
        result_data = json.loads(record["result"])
        assert result_data["output"] == 42

    async def test_record_failure(self, conn: ConnectionManager) -> None:
        """Record start then failure; status should be 'failed'."""
        store = await self._make_store(conn)
        run_id = "run-fail-001"
        await store.record_start(run_id=run_id, workflow_id="wf-fail")
        await store.record_failure(run_id=run_id, error="Something broke")

        record = await store.get_execution(run_id)
        assert record is not None
        assert record["status"] == "failed"
        assert record["error"] == "Something broke"
        assert record["completed_at"] is not None

    async def test_get_nonexistent_returns_none(self, conn: ConnectionManager) -> None:
        """Fetching a non-existent run_id returns None."""
        store = await self._make_store(conn)
        assert await store.get_execution("run-does-not-exist") is None

    async def test_list_executions_filter_by_status(
        self, conn: ConnectionManager
    ) -> None:
        """list_executions with status filter returns correct subset."""
        store = await self._make_store(conn)
        await store.record_start(run_id="run-s1", workflow_id="wf-list")
        await store.record_start(run_id="run-s2", workflow_id="wf-list")
        await store.record_start(run_id="run-s3", workflow_id="wf-list")
        await store.record_completion(run_id="run-s1", results={"ok": True})
        await store.record_failure(run_id="run-s2", error="fail")

        pending = await store.list_executions(status="pending")
        assert len(pending) == 1
        assert pending[0]["run_id"] == "run-s3"

        completed = await store.list_executions(status="completed")
        assert len(completed) == 1
        assert completed[0]["run_id"] == "run-s1"

        failed = await store.list_executions(status="failed")
        assert len(failed) == 1
        assert failed[0]["run_id"] == "run-s2"

    async def test_list_executions_filter_by_workflow_id(
        self, conn: ConnectionManager
    ) -> None:
        """list_executions with workflow_id filter returns correct subset."""
        store = await self._make_store(conn)
        await store.record_start(run_id="run-w1", workflow_id="wf-alpha")
        await store.record_start(run_id="run-w2", workflow_id="wf-beta")
        await store.record_start(run_id="run-w3", workflow_id="wf-alpha")

        alpha_runs = await store.list_executions(workflow_id="wf-alpha")
        assert len(alpha_runs) == 2
        run_ids = {r["run_id"] for r in alpha_runs}
        assert run_ids == {"run-w1", "run-w3"}

    async def test_list_executions_respects_limit(
        self, conn: ConnectionManager
    ) -> None:
        """list_executions limit parameter caps result count."""
        store = await self._make_store(conn)
        for i in range(20):
            await store.record_start(run_id=f"run-lim-{i:03d}", workflow_id="wf-limit")

        results = await store.list_executions(limit=5)
        assert len(results) == 5

    async def test_record_start_with_parameters(self, conn: ConnectionManager) -> None:
        """Parameters dict is stored as JSON and retrievable."""
        store = await self._make_store(conn)
        params = {"model": "llama-3", "temperature": 0.7, "tags": ["a", "b"]}
        await store.record_start(
            run_id="run-params", workflow_id="wf-params", parameters=params
        )

        record = await store.get_execution("run-params")
        assert record is not None
        stored_params = json.loads(record["parameters"])
        assert stored_params == params


# ===================================================================
# IdempotencyStore
# ===================================================================
class TestIdempotencyStoreIntegration:
    """Validate DBIdempotencyStore claim/store/TTL against all dialects."""

    async def _make_store(self, conn: ConnectionManager) -> DBIdempotencyStore:
        store = DBIdempotencyStore(conn)
        await store.initialize()
        return store

    async def test_try_claim_succeeds_first_time(self, conn: ConnectionManager) -> None:
        """First try_claim for a key returns True."""
        store = await self._make_store(conn)
        claimed = await store.try_claim("idem-001", "fp-abc")
        assert claimed is True, "First claim should succeed"

    async def test_try_claim_fails_duplicate(self, conn: ConnectionManager) -> None:
        """Second try_claim for the same key returns False."""
        store = await self._make_store(conn)
        first = await store.try_claim("idem-dup", "fp-1")
        assert first is True
        second = await store.try_claim("idem-dup", "fp-2")
        assert second is False, "Duplicate claim should be rejected"

    async def test_store_result_and_get(self, conn: ConnectionManager) -> None:
        """After claiming and storing a result, get() returns the entry."""
        store = await self._make_store(conn)
        key = "idem-result"
        await store.try_claim(key, "fp-result")
        await store.store_result(
            key=key,
            response_data={"message": "success"},
            status_code=200,
            headers={"X-Request-Id": "abc-123"},
        )

        entry = await store.get(key)
        assert entry is not None, "get() returned None after store_result"
        assert entry["idempotency_key"] == key
        assert entry["status_code"] == 200
        response = json.loads(entry["response_data"])
        assert response["message"] == "success"
        headers = json.loads(entry["headers"])
        assert headers["X-Request-Id"] == "abc-123"

    async def test_get_returns_none_for_missing(self, conn: ConnectionManager) -> None:
        """get() for a non-existent key returns None."""
        store = await self._make_store(conn)
        assert await store.get("idem-nonexistent") is None

    async def test_release_claim_allows_reclaim(self, conn: ConnectionManager) -> None:
        """After release_claim, the key can be claimed again."""
        store = await self._make_store(conn)
        key = "idem-release"
        await store.try_claim(key, "fp-a")
        await store.release_claim(key)

        # Now reclaim should succeed
        reclaimed = await store.try_claim(key, "fp-b")
        assert reclaimed is True, "Reclaim after release should succeed"

    async def test_set_with_ttl(self, conn: ConnectionManager) -> None:
        """set() stores an entry that is retrievable before TTL expiry."""
        store = await self._make_store(conn)
        key = "idem-ttl"
        await store.set(
            key=key,
            fingerprint="fp-ttl",
            response_data={"cached": True},
            status_code=200,
            headers={},
            ttl_seconds=3600,
        )

        entry = await store.get(key)
        assert entry is not None
        assert entry["fingerprint"] == "fp-ttl"

    async def test_cleanup_removes_expired(self, conn: ConnectionManager) -> None:
        """cleanup() deletes entries whose expires_at is in the past."""
        store = await self._make_store(conn)

        # Insert an entry with expires_at in the past via direct SQL
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        await conn.execute(
            "INSERT INTO kailash_idempotency "
            "(idempotency_key, fingerprint, response_data, status_code, "
            "headers, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            "idem-expired",
            "fp-old",
            '{"old": true}',
            200,
            "{}",
            past,
            past,
        )

        # Also insert a fresh entry
        await store.set(
            key="idem-fresh",
            fingerprint="fp-new",
            response_data={"fresh": True},
            status_code=200,
            headers={},
            ttl_seconds=3600,
        )

        await store.cleanup()

        # Expired entry should be gone
        expired = await conn.fetchone(
            "SELECT * FROM kailash_idempotency WHERE idempotency_key = ?",
            "idem-expired",
        )
        assert expired is None, "Expired entry should have been cleaned up"

        # Fresh entry should remain
        fresh = await store.get("idem-fresh")
        assert fresh is not None, "Fresh entry should survive cleanup"

    async def test_set_first_writer_wins(self, conn: ConnectionManager) -> None:
        """set() uses INSERT OR IGNORE -- first write wins, second is silent no-op."""
        store = await self._make_store(conn)
        key = "idem-first-wins"

        await store.set(
            key=key,
            fingerprint="fp-first",
            response_data={"writer": 1},
            status_code=200,
            headers={},
            ttl_seconds=3600,
        )
        await store.set(
            key=key,
            fingerprint="fp-second",
            response_data={"writer": 2},
            status_code=201,
            headers={},
            ttl_seconds=3600,
        )

        entry = await store.get(key)
        assert entry is not None
        # First writer should have won
        assert entry["fingerprint"] == "fp-first"
        assert entry["status_code"] == 200
