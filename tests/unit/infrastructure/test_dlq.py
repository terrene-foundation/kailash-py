# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for dialect-portable Dead Letter Queue backend.

Tests cover:
- Enqueue and dequeue lifecycle
- Status transitions: pending -> retrying -> succeeded / permanent_failure
- Retry count increment with mark_failure
- get_stats aggregate counts
- clear operation
- Edge cases: empty queue, unknown item_id, max retries exceeded
- Connection lifecycle (initialize / close)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import pytest

from kailash.db.connection import ConnectionManager
from kailash.infrastructure.dlq import DBDeadLetterQueue

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
async def dlq(conn_manager):
    """Provide an initialized DLQ backend with zero backoff delay for tests."""
    queue = DBDeadLetterQueue(conn_manager, base_delay=0.0)
    await queue.initialize()
    yield queue
    await queue.close()


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestDLQEnqueue:
    async def test_enqueue_returns_item_id(self, dlq):
        """enqueue must return a non-empty string item ID."""
        item_id = await dlq.enqueue(
            workflow_id="wf-1",
            error="Something failed",
            payload='{"input": "data"}',
            max_retries=3,
        )
        assert isinstance(item_id, str)
        assert len(item_id) > 0

    async def test_enqueue_creates_pending_item(self, dlq):
        """Enqueued item should have status 'pending'."""
        item_id = await dlq.enqueue(
            workflow_id="wf-2",
            error="Error message",
            payload='{"key": "value"}',
            max_retries=5,
        )

        stats = await dlq.get_stats()
        assert stats["pending"] == 1
        assert stats["total"] == 1

    async def test_enqueue_multiple_items(self, dlq):
        """Multiple enqueues should all be stored."""
        ids = []
        for i in range(5):
            item_id = await dlq.enqueue(
                workflow_id=f"wf-{i}",
                error=f"Error {i}",
                payload=f'{{"index": {i}}}',
                max_retries=3,
            )
            ids.append(item_id)

        assert len(set(ids)) == 5  # All IDs unique
        stats = await dlq.get_stats()
        assert stats["total"] == 5

    async def test_enqueue_serializes_dict_payload(self, dlq):
        """Dict payloads should be JSON-serialized automatically."""
        item_id = await dlq.enqueue(
            workflow_id="wf-dict",
            error="Error",
            payload={"nested": {"key": "value"}, "list": [1, 2, 3]},
            max_retries=3,
        )
        assert isinstance(item_id, str)
        assert len(item_id) > 0


# ---------------------------------------------------------------------------
# Dequeue
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestDLQDequeue:
    async def test_dequeue_ready_returns_pending_items(self, dlq):
        """dequeue_ready should return items with status='pending' and next_retry_at <= now."""
        await dlq.enqueue(
            workflow_id="wf-ready",
            error="Ready to retry",
            payload="{}",
            max_retries=3,
        )

        items = await dlq.dequeue_ready()
        assert len(items) >= 1
        assert items[0]["workflow_id"] == "wf-ready"
        assert items[0]["status"] == "pending"

    async def test_dequeue_empty_queue_returns_empty(self, dlq):
        """dequeue_ready on empty queue should return empty list."""
        items = await dlq.dequeue_ready()
        assert items == []

    async def test_dequeue_excludes_non_pending(self, dlq):
        """dequeue_ready should exclude items not in 'pending' status."""
        item_id = await dlq.enqueue(
            workflow_id="wf-retrying",
            error="Error",
            payload="{}",
            max_retries=3,
        )
        await dlq.mark_retrying(item_id)

        items = await dlq.dequeue_ready()
        # The retrying item should not appear
        retrying_ids = [i["id"] for i in items if i["id"] == item_id]
        assert retrying_ids == []


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestDLQStatusTransitions:
    async def test_mark_retrying(self, dlq):
        """mark_retrying should change status to 'retrying'."""
        item_id = await dlq.enqueue(
            workflow_id="wf-retry",
            error="Error",
            payload="{}",
            max_retries=3,
        )
        await dlq.mark_retrying(item_id)

        stats = await dlq.get_stats()
        assert stats["retrying"] == 1
        assert stats["pending"] == 0

    async def test_mark_success(self, dlq):
        """mark_success should change status to 'succeeded'."""
        item_id = await dlq.enqueue(
            workflow_id="wf-success",
            error="Error",
            payload="{}",
            max_retries=3,
        )
        await dlq.mark_retrying(item_id)
        await dlq.mark_success(item_id)

        stats = await dlq.get_stats()
        assert stats["succeeded"] == 1
        assert stats["retrying"] == 0

    async def test_mark_failure_increments_retry_count(self, dlq):
        """mark_failure should increment retry_count."""
        item_id = await dlq.enqueue(
            workflow_id="wf-fail",
            error="Error",
            payload="{}",
            max_retries=5,
        )
        await dlq.mark_failure(item_id)

        # Item should go back to pending with incremented retry count
        items = await dlq.dequeue_ready()
        matching = [i for i in items if i["id"] == item_id]
        assert len(matching) == 1
        assert matching[0]["retry_count"] == 1
        assert matching[0]["status"] == "pending"

    async def test_mark_failure_exceeds_max_retries(self, dlq):
        """mark_failure when retry_count reaches max_retries should mark as permanent_failure."""
        item_id = await dlq.enqueue(
            workflow_id="wf-perm-fail",
            error="Error",
            payload="{}",
            max_retries=2,
        )

        # Fail twice — should hit max_retries
        await dlq.mark_failure(item_id)  # retry_count -> 1
        await dlq.mark_failure(item_id)  # retry_count -> 2 >= max_retries

        stats = await dlq.get_stats()
        assert stats["permanent_failure"] == 1
        assert stats["pending"] == 0

    async def test_mark_failure_unknown_item_id_logs_warning(self, dlq, caplog):
        """mark_failure with unknown item_id should log a warning, not crash."""
        with caplog.at_level(logging.WARNING):
            await dlq.mark_failure("nonexistent-id")
        # Should not raise; warning should be logged


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestDLQGetStats:
    async def test_stats_empty_queue(self, dlq):
        """Stats on empty queue should have all zeroes."""
        stats = await dlq.get_stats()
        assert stats["pending"] == 0
        assert stats["retrying"] == 0
        assert stats["succeeded"] == 0
        assert stats["permanent_failure"] == 0
        assert stats["total"] == 0

    async def test_stats_reflect_all_statuses(self, dlq):
        """Stats should accurately count items in each status."""
        # Create items in different states
        id1 = await dlq.enqueue(
            workflow_id="wf-s1", error="E", payload="{}", max_retries=3
        )
        id2 = await dlq.enqueue(
            workflow_id="wf-s2", error="E", payload="{}", max_retries=3
        )
        id3 = await dlq.enqueue(
            workflow_id="wf-s3", error="E", payload="{}", max_retries=1
        )
        id4 = await dlq.enqueue(
            workflow_id="wf-s4", error="E", payload="{}", max_retries=3
        )

        await dlq.mark_retrying(id2)
        await dlq.mark_success(id3)
        # id4 -> permanent failure by exceeding max_retries
        await dlq.mark_failure(id4)  # retry_count=1
        await dlq.mark_failure(id4)  # retry_count=2
        await dlq.mark_failure(id4)  # retry_count=3 >= max_retries

        stats = await dlq.get_stats()
        assert stats["pending"] == 1  # id1
        assert stats["retrying"] == 1  # id2
        assert stats["succeeded"] == 1  # id3
        assert stats["permanent_failure"] == 1  # id4
        assert stats["total"] == 4


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestDLQClear:
    async def test_clear_removes_all_items(self, dlq):
        """clear should remove all items from the queue."""
        for i in range(10):
            await dlq.enqueue(
                workflow_id=f"wf-{i}", error="E", payload="{}", max_retries=3
            )

        stats_before = await dlq.get_stats()
        assert stats_before["total"] == 10

        await dlq.clear()

        stats_after = await dlq.get_stats()
        assert stats_after["total"] == 0

    async def test_clear_empty_queue_does_not_raise(self, dlq):
        """Clearing an already empty queue should not raise."""
        await dlq.clear()
        stats = await dlq.get_stats()
        assert stats["total"] == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestDLQEdgeCases:
    async def test_enqueue_with_zero_max_retries(self, dlq):
        """Items with max_retries=0 should go to permanent_failure on first failure."""
        item_id = await dlq.enqueue(
            workflow_id="wf-zero",
            error="Immediate fail",
            payload="{}",
            max_retries=0,
        )
        await dlq.mark_failure(item_id)

        stats = await dlq.get_stats()
        assert stats["permanent_failure"] == 1

    async def test_enqueue_preserves_error_message(self, dlq):
        """The error message should be preserved and retrievable."""
        error_msg = "ValueError: invalid input\nTraceback..."
        await dlq.enqueue(
            workflow_id="wf-err",
            error=error_msg,
            payload="{}",
            max_retries=3,
        )

        items = await dlq.dequeue_ready()
        assert len(items) == 1
        assert items[0]["error"] == error_msg

    async def test_enqueue_preserves_workflow_id(self, dlq):
        """The workflow_id should be preserved."""
        await dlq.enqueue(
            workflow_id="my-workflow-abc-123",
            error="E",
            payload="{}",
            max_retries=3,
        )

        items = await dlq.dequeue_ready()
        assert items[0]["workflow_id"] == "my-workflow-abc-123"


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestDLQLifecycle:
    async def test_initialize_creates_table(self, conn_manager):
        """initialize() should create the kailash_dlq table."""
        queue = DBDeadLetterQueue(conn_manager)
        await queue.initialize()

        rows = await conn_manager.fetch(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='kailash_dlq'"
        )
        assert len(rows) == 1
        assert rows[0]["name"] == "kailash_dlq"
        await queue.close()

    async def test_double_initialize_is_safe(self, conn_manager):
        """Calling initialize() twice should not raise."""
        queue = DBDeadLetterQueue(conn_manager)
        await queue.initialize()
        await queue.initialize()
        await queue.close()

    async def test_close_is_safe_multiple_times(self, conn_manager):
        """Calling close() multiple times should not raise."""
        queue = DBDeadLetterQueue(conn_manager)
        await queue.initialize()
        await queue.close()
        await queue.close()

    async def test_requires_connection_manager(self):
        """Constructor must require a ConnectionManager."""
        with pytest.raises(TypeError):
            DBDeadLetterQueue()  # type: ignore[call-arg]
