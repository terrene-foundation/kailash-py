"""Integration tests for PersistentDLQ.

Validates persistence across restarts, retry logic with exponential backoff,
bounded capacity enforcement, and status-based statistics.
"""

import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from kailash.workflow.dlq import (
    DEFAULT_BASE_DELAY,
    MAX_DLQ_ITEMS,
    DLQItem,
    PersistentDLQ,
)


@pytest.fixture()
def dlq_path(tmp_path: Path) -> str:
    """Return a temporary database path for each test."""
    return str(tmp_path / "test_dlq.db")


@pytest.fixture()
def dlq(dlq_path: str) -> PersistentDLQ:
    """Return a PersistentDLQ instance with a very short base delay."""
    q = PersistentDLQ(db_path=dlq_path, base_delay=0.01)
    yield q
    q.close()


# ------------------------------------------------------------------
# Persistence across restarts
# ------------------------------------------------------------------


class TestPersistenceAcrossRestart:
    """Items survive when the DLQ object is destroyed and re-created."""

    def test_enqueue_survives_restart(self, dlq_path: str) -> None:
        # First "process" -- enqueue an item then close.
        dlq1 = PersistentDLQ(db_path=dlq_path, base_delay=0.01)
        item_id = dlq1.enqueue("wf-1", "boom", {"key": "value"})
        assert len(dlq1) == 1
        dlq1.close()

        # Second "process" -- open the same DB and verify data.
        dlq2 = PersistentDLQ(db_path=dlq_path, base_delay=0.01)
        items = dlq2.get_all()
        assert len(items) == 1
        assert items[0]["id"] == item_id
        assert items[0]["workflow_id"] == "wf-1"
        assert items[0]["error"] == "boom"
        assert json.loads(items[0]["payload"]) == {"key": "value"}
        dlq2.close()

    def test_clear_survives_restart(self, dlq_path: str) -> None:
        dlq1 = PersistentDLQ(db_path=dlq_path, base_delay=0.01)
        dlq1.enqueue("wf-1", "err", "payload")
        dlq1.clear()
        dlq1.close()

        dlq2 = PersistentDLQ(db_path=dlq_path, base_delay=0.01)
        assert len(dlq2) == 0
        dlq2.close()


# ------------------------------------------------------------------
# Dequeue ready
# ------------------------------------------------------------------


class TestDequeueReady:
    """Items are returned by dequeue_ready only when next_retry_at <= now."""

    def test_newly_enqueued_is_immediately_ready(self, dlq: PersistentDLQ) -> None:
        """Enqueue sets next_retry_at to 'now', so it should be immediately dequeue-able."""
        dlq.enqueue("wf-1", "err", "data")
        ready = dlq.dequeue_ready()
        assert len(ready) == 1
        assert ready[0].workflow_id == "wf-1"

    def test_future_retry_not_returned(self, dlq_path: str) -> None:
        """An item with next_retry_at far in the future should not be dequeued."""
        dlq = PersistentDLQ(db_path=dlq_path, base_delay=3600)  # 1 hour base
        item_id = dlq.enqueue("wf-1", "err", "data")

        # Manually push next_retry_at into the future.
        future = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
        with dlq._lock:
            dlq._conn.execute(
                "UPDATE dlq SET next_retry_at = ? WHERE id = ?",
                (future, item_id),
            )
            dlq._conn.commit()

        ready = dlq.dequeue_ready()
        assert len(ready) == 0
        dlq.close()

    def test_dequeue_returns_items_in_retry_order(self, dlq: PersistentDLQ) -> None:
        """Oldest next_retry_at should come first."""
        id1 = dlq.enqueue("wf-a", "err", "first")
        id2 = dlq.enqueue("wf-b", "err", "second")
        ready = dlq.dequeue_ready()
        assert len(ready) >= 2
        # First enqueued should be first (or equal)
        ids = [item.id for item in ready]
        assert ids.index(id1) < ids.index(id2)


# ------------------------------------------------------------------
# Retry logic and exponential backoff
# ------------------------------------------------------------------


class TestRetryLogic:
    """Mark failure increments retry_count and eventually marks permanent_failure."""

    def test_three_failures_become_permanent(self, dlq: PersistentDLQ) -> None:
        item_id = dlq.enqueue("wf-retry", "err", "data", max_retries=3)

        # Failure 1 -- still pending
        dlq.mark_failure(item_id)
        items = dlq.get_all()
        item = next(i for i in items if i["id"] == item_id)
        assert item["retry_count"] == 1
        assert item["status"] == "pending"

        # Failure 2 -- still pending
        dlq.mark_failure(item_id)
        items = dlq.get_all()
        item = next(i for i in items if i["id"] == item_id)
        assert item["retry_count"] == 2
        assert item["status"] == "pending"

        # Failure 3 -- permanent_failure (retry_count == max_retries)
        dlq.mark_failure(item_id)
        items = dlq.get_all()
        item = next(i for i in items if i["id"] == item_id)
        assert item["retry_count"] == 3
        assert item["status"] == "permanent_failure"

    def test_mark_retrying_then_success(self, dlq: PersistentDLQ) -> None:
        item_id = dlq.enqueue("wf-ok", "err", "data")
        dlq.mark_retrying(item_id)

        items = dlq.get_all()
        item = next(i for i in items if i["id"] == item_id)
        assert item["status"] == "retrying"

        dlq.mark_success(item_id)
        items = dlq.get_all()
        item = next(i for i in items if i["id"] == item_id)
        assert item["status"] == "succeeded"

    def test_backoff_delay_increases(self, dlq_path: str) -> None:
        """Verify that next_retry_at moves further into the future with each failure."""
        dlq = PersistentDLQ(db_path=dlq_path, base_delay=1.0)
        item_id = dlq.enqueue("wf-backoff", "err", "data", max_retries=5)

        previous_retry_at = None
        previous_gap = None

        for i in range(4):
            dlq.mark_failure(item_id)
            items = dlq.get_all()
            item = next(it for it in items if it["id"] == item_id)
            current_retry_at = item["next_retry_at"]

            if previous_retry_at is not None:
                # Parse times; later failures should have later next_retry_at values.
                prev = datetime.fromisoformat(previous_retry_at)
                curr = datetime.fromisoformat(current_retry_at)
                assert curr > prev, (
                    f"Retry {i}: next_retry_at did not advance "
                    f"(prev={previous_retry_at}, curr={current_retry_at})"
                )

            previous_retry_at = current_retry_at

        dlq.close()

    def test_mark_failure_unknown_item(self, dlq: PersistentDLQ) -> None:
        """Calling mark_failure on a nonexistent id should not raise."""
        dlq.mark_failure("nonexistent-id")  # Should log warning, not crash.


# ------------------------------------------------------------------
# Bounded capacity
# ------------------------------------------------------------------


class TestBoundedCapacity:
    def test_oldest_evicted_at_capacity(self, dlq_path: str) -> None:
        """When DLQ is at MAX_DLQ_ITEMS, enqueuing evicts the oldest 10%."""
        dlq = PersistentDLQ(db_path=dlq_path, base_delay=0.01)

        # Use a smaller capacity for this test by patching the constant.
        small_max = 100
        with patch("kailash.workflow.dlq.MAX_DLQ_ITEMS", small_max):
            # Fill to capacity.
            first_ids = []
            for i in range(small_max):
                item_id = dlq.enqueue(f"wf-{i}", f"err-{i}", f"payload-{i}")
                first_ids.append(item_id)

            assert len(dlq) == small_max

            # Enqueue one more -- should trigger eviction of oldest 10%.
            dlq.enqueue("wf-overflow", "err-overflow", "payload-overflow")

            evicted_count = small_max // 10  # 10
            expected_count = small_max - evicted_count + 1
            assert len(dlq) == expected_count

            # Verify the oldest items were evicted.
            remaining = dlq.get_all()
            remaining_ids = {item["id"] for item in remaining}
            for old_id in first_ids[:evicted_count]:
                assert (
                    old_id not in remaining_ids
                ), f"Oldest item {old_id} should have been evicted"

        dlq.close()

    def test_enqueue_10001_items_full_scale(self, dlq_path: str) -> None:
        """Enqueue MAX_DLQ_ITEMS + 1 items and verify oldest were evicted."""
        dlq = PersistentDLQ(db_path=dlq_path, base_delay=0.01)

        # Use batch inserts for speed (bypass enqueue to avoid capacity check,
        # then add the overflow through enqueue).
        import sqlite3

        with dlq._lock:
            cursor = dlq._conn.cursor()
            now = datetime.now(UTC).isoformat()
            batch = [
                (
                    f"batch-{i}",
                    f"wf-{i}",
                    f"err-{i}",
                    f"payload-{i}",
                    now,
                    0,
                    3,
                    now,
                    "pending",
                )
                for i in range(MAX_DLQ_ITEMS)
            ]
            cursor.executemany(
                "INSERT INTO dlq (id, workflow_id, error, payload, created_at, "
                "retry_count, max_retries, next_retry_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                batch,
            )
            dlq._conn.commit()

        assert len(dlq) == MAX_DLQ_ITEMS

        # Enqueue one more through the public API.
        overflow_id = dlq.enqueue("wf-overflow", "err", "data")

        # Capacity should be MAX_DLQ_ITEMS - evicted + 1
        evicted = MAX_DLQ_ITEMS // 10
        assert len(dlq) == MAX_DLQ_ITEMS - evicted + 1

        # The overflow item should exist.
        remaining = dlq.get_all()
        remaining_ids = {item["id"] for item in remaining}
        assert overflow_id in remaining_ids

        dlq.close()


# ------------------------------------------------------------------
# Statistics
# ------------------------------------------------------------------


class TestGetStats:
    def test_stats_empty(self, dlq: PersistentDLQ) -> None:
        stats = dlq.get_stats()
        assert stats["total"] == 0
        assert stats["pending"] == 0
        assert stats["retrying"] == 0
        assert stats["succeeded"] == 0
        assert stats["permanent_failure"] == 0

    def test_stats_mixed_statuses(self, dlq: PersistentDLQ) -> None:
        id1 = dlq.enqueue("wf-1", "err", "data", max_retries=1)
        id2 = dlq.enqueue("wf-2", "err", "data")
        id3 = dlq.enqueue("wf-3", "err", "data")
        id4 = dlq.enqueue("wf-4", "err", "data")

        dlq.mark_retrying(id2)
        dlq.mark_success(id3)
        dlq.mark_failure(id4)  # retry_count 1, max_retries 3 -> still pending

        # id1: pending, id2: retrying, id3: succeeded, id4: pending (failed once)
        stats = dlq.get_stats()
        assert stats["pending"] == 2  # id1 + id4
        assert stats["retrying"] == 1  # id2
        assert stats["succeeded"] == 1  # id3
        assert stats["permanent_failure"] == 0
        assert stats["total"] == 4

    def test_stats_permanent_failure(self, dlq: PersistentDLQ) -> None:
        item_id = dlq.enqueue("wf-pf", "err", "data", max_retries=1)
        dlq.mark_failure(item_id)  # retry_count 1 >= max_retries 1 -> permanent

        stats = dlq.get_stats()
        assert stats["permanent_failure"] == 1
        assert stats["total"] == 1


# ------------------------------------------------------------------
# DLQItem dataclass
# ------------------------------------------------------------------


class TestDLQItem:
    def test_to_dict_roundtrip(self) -> None:
        item = DLQItem(
            id="test-id",
            workflow_id="wf-1",
            error="something broke",
            payload='{"key": "val"}',
            created_at="2026-01-01T00:00:00+00:00",
            retry_count=2,
            max_retries=5,
            next_retry_at="2026-01-01T00:01:00+00:00",
            status="pending",
        )
        d = item.to_dict()
        assert d["id"] == "test-id"
        assert d["status"] == "pending"
        assert d["retry_count"] == 2

    def test_from_row(self) -> None:
        row = {
            "id": "r-1",
            "workflow_id": "wf-x",
            "error": "oops",
            "payload": "{}",
            "created_at": "2026-01-01T00:00:00+00:00",
            "retry_count": 0,
            "max_retries": 3,
            "next_retry_at": None,
            "status": "pending",
        }
        item = DLQItem.from_row(row)
        assert item.id == "r-1"
        assert item.status == "pending"


# ------------------------------------------------------------------
# File permissions (POSIX only)
# ------------------------------------------------------------------


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only test")
class TestFilePermissions:
    def test_db_file_is_owner_only(self, dlq_path: str) -> None:
        dlq = PersistentDLQ(db_path=dlq_path, base_delay=0.01)
        import stat

        mode = os.stat(dlq_path).st_mode
        assert mode & stat.S_IRWXG == 0, "Group should have no permissions"
        assert mode & stat.S_IRWXO == 0, "Others should have no permissions"
        assert mode & stat.S_IRUSR != 0, "Owner should have read"
        assert mode & stat.S_IWUSR != 0, "Owner should have write"
        dlq.close()


# ------------------------------------------------------------------
# Context manager
# ------------------------------------------------------------------


class TestContextManager:
    def test_context_manager(self, dlq_path: str) -> None:
        with PersistentDLQ(db_path=dlq_path, base_delay=0.01) as dlq:
            dlq.enqueue("wf-cm", "err", "data")
            assert len(dlq) == 1
        # Connection closed after exit -- re-open to verify persistence.
        dlq2 = PersistentDLQ(db_path=dlq_path, base_delay=0.01)
        assert len(dlq2) == 1
        dlq2.close()


# ------------------------------------------------------------------
# WorkflowResilience integration
# ------------------------------------------------------------------


class TestWorkflowResilienceIntegration:
    """Verify that WorkflowResilience uses PersistentDLQ correctly."""

    def test_resilience_uses_persistent_dlq(self, dlq_path: str) -> None:
        from kailash.workflow.resilience import WorkflowResilience

        r = WorkflowResilience(dlq_path=dlq_path)
        assert isinstance(r._dead_letter_queue, PersistentDLQ)

    def test_get_dead_letter_queue_returns_list(self, dlq_path: str) -> None:
        from kailash.workflow.resilience import WorkflowResilience

        r = WorkflowResilience(dlq_path=dlq_path)
        r._dead_letter_queue.enqueue("wf-1", "err", "data")
        result = r.get_dead_letter_queue()
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["workflow_id"] == "wf-1"

    def test_clear_dead_letter_queue(self, dlq_path: str) -> None:
        from kailash.workflow.resilience import WorkflowResilience

        r = WorkflowResilience(dlq_path=dlq_path)
        r._dead_letter_queue.enqueue("wf-1", "err", "data")
        r.clear_dead_letter_queue()
        assert len(r.get_dead_letter_queue()) == 0

    def test_resilience_metrics_include_dlq_stats(self, dlq_path: str) -> None:
        from kailash.workflow.resilience import WorkflowResilience

        r = WorkflowResilience(dlq_path=dlq_path)
        r._dead_letter_queue.enqueue("wf-1", "err", "data")
        metrics = r.get_resilience_metrics()
        assert metrics["dead_letter_queue_size"] == 1
        assert "dead_letter_queue_stats" in metrics
        assert metrics["dead_letter_queue_stats"]["pending"] == 1
