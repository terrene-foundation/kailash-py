# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Tier 2 integration tests for SQLiteBudgetStore.

Tests use a real SQLite database (NO mocking). Cover:
- Create tracker with store, reserve, record -- snapshot persisted
- New tracker from same store -- budget state recovered
- Pending reservations lost on restart (documented, safe direction)
- File permissions are 0o600 on POSIX
- Reject path with '..' components
- Bounded history (limit parameter respected)
- Transaction log records persisted and queryable
- Concurrent store operations are safe
"""

from __future__ import annotations

import os
import platform
import sqlite3
import stat
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

from eatp.constraints.budget_store import BudgetStoreError, SQLiteBudgetStore
from eatp.constraints.budget_tracker import (
    BudgetSnapshot,
    BudgetTracker,
    BudgetTrackerError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> str:
    """Return a temporary path for a fresh SQLite database."""
    return str(tmp_path / "test_budget.db")


@pytest.fixture
def store(tmp_db_path: str) -> SQLiteBudgetStore:
    """Create and initialize a SQLiteBudgetStore."""
    s = SQLiteBudgetStore(tmp_db_path)
    s.initialize()
    return s


# ---------------------------------------------------------------------------
# 1. Snapshot persistence: reserve, record, verify snapshot is saved
# ---------------------------------------------------------------------------
class TestSnapshotPersistence:
    """Create tracker with store, reserve, record -- snapshot persisted."""

    def test_save_and_load_snapshot(self, store: SQLiteBudgetStore) -> None:
        tracker_id = "agent-budget-001"
        snap = BudgetSnapshot(allocated=100_000_000, committed=25_000_000)

        store.save_snapshot(tracker_id, snap)
        loaded = store.get_snapshot(tracker_id)

        assert loaded is not None
        assert loaded.allocated == 100_000_000
        assert loaded.committed == 25_000_000

    def test_overwrite_snapshot(self, store: SQLiteBudgetStore) -> None:
        tracker_id = "agent-budget-002"

        snap1 = BudgetSnapshot(allocated=100_000_000, committed=10_000_000)
        store.save_snapshot(tracker_id, snap1)

        snap2 = BudgetSnapshot(allocated=100_000_000, committed=50_000_000)
        store.save_snapshot(tracker_id, snap2)

        loaded = store.get_snapshot(tracker_id)
        assert loaded is not None
        assert loaded.committed == 50_000_000

    def test_get_nonexistent_snapshot_returns_none(
        self, store: SQLiteBudgetStore
    ) -> None:
        result = store.get_snapshot("does-not-exist")
        assert result is None

    def test_tracker_with_store_auto_saves(self, store: SQLiteBudgetStore) -> None:
        """BudgetTracker with store= parameter auto-saves after record()."""
        tracker = BudgetTracker(
            allocated_microdollars=100_000_000,
            store=store,
            tracker_id="auto-save-test",
        )

        # Reserve and record
        assert tracker.reserve(30_000_000) is True
        tracker.record(reserved_microdollars=30_000_000, actual_microdollars=25_000_000)

        # Snapshot should be persisted
        snap = store.get_snapshot("auto-save-test")
        assert snap is not None
        assert snap.allocated == 100_000_000
        assert snap.committed == 25_000_000


# ---------------------------------------------------------------------------
# 2. State recovery from same store
# ---------------------------------------------------------------------------
class TestStateRecovery:
    """New tracker from same store -- budget state recovered."""

    def test_recover_state_from_store(self, tmp_db_path: str) -> None:
        # First tracker: spend some budget
        store1 = SQLiteBudgetStore(tmp_db_path)
        store1.initialize()

        tracker1 = BudgetTracker(
            allocated_microdollars=100_000_000,
            store=store1,
            tracker_id="recovery-test",
        )
        tracker1.reserve(40_000_000)
        tracker1.record(
            reserved_microdollars=40_000_000, actual_microdollars=35_000_000
        )
        # committed=35M now

        # Second tracker: same store, same ID -- should recover
        store2 = SQLiteBudgetStore(tmp_db_path)
        store2.initialize()

        tracker2 = BudgetTracker(
            allocated_microdollars=100_000_000,
            store=store2,
            tracker_id="recovery-test",
        )

        # Recovered: committed=35M, remaining=65M
        assert tracker2.remaining_microdollars() == 65_000_000
        snap = tracker2.snapshot()
        assert snap.committed == 35_000_000
        assert snap.allocated == 100_000_000

    def test_multiple_records_recovery(self, tmp_db_path: str) -> None:
        """Multiple record() calls accumulate, then recover."""
        store = SQLiteBudgetStore(tmp_db_path)
        store.initialize()

        tracker = BudgetTracker(
            allocated_microdollars=100_000_000,
            store=store,
            tracker_id="multi-record",
        )

        # Two reserve/record cycles
        tracker.reserve(20_000_000)
        tracker.record(reserved_microdollars=20_000_000, actual_microdollars=15_000_000)
        tracker.reserve(30_000_000)
        tracker.record(reserved_microdollars=30_000_000, actual_microdollars=28_000_000)

        # Total committed: 15M + 28M = 43M

        # Recover from fresh store
        store2 = SQLiteBudgetStore(tmp_db_path)
        store2.initialize()

        tracker2 = BudgetTracker(
            allocated_microdollars=100_000_000,
            store=store2,
            tracker_id="multi-record",
        )
        assert tracker2.remaining_microdollars() == 57_000_000  # 100M - 43M


# ---------------------------------------------------------------------------
# 3. Reservations lost on restart (documented, safe direction)
# ---------------------------------------------------------------------------
class TestReservationsLostOnRestart:
    """Pending reservations are lost on restart -- this is the safe direction."""

    def test_reservations_not_persisted(self, tmp_db_path: str) -> None:
        store = SQLiteBudgetStore(tmp_db_path)
        store.initialize()

        tracker = BudgetTracker(
            allocated_microdollars=100_000_000,
            store=store,
            tracker_id="reservation-loss",
        )

        # Reserve but do NOT record
        tracker.reserve(50_000_000)
        assert tracker.remaining_microdollars() == 50_000_000  # 100M - 50M reserved

        # Recover from store -- reservation should be gone
        store2 = SQLiteBudgetStore(tmp_db_path)
        store2.initialize()

        tracker2 = BudgetTracker(
            allocated_microdollars=100_000_000,
            store=store2,
            tracker_id="reservation-loss",
        )

        # Reservation is gone -- full budget available minus committed (0)
        assert tracker2.remaining_microdollars() == 100_000_000


# ---------------------------------------------------------------------------
# 4. File permissions on POSIX
# ---------------------------------------------------------------------------
class TestFilePermissions:
    """File permissions are 0o600 on POSIX systems."""

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="File permissions are not enforced on Windows",
    )
    def test_db_file_has_0o600_permissions(self, tmp_db_path: str) -> None:
        store = SQLiteBudgetStore(tmp_db_path)
        store.initialize()

        # Force a write so the file definitely exists
        store.save_snapshot("perm-test", BudgetSnapshot(allocated=100, committed=0))

        st = os.stat(tmp_db_path)
        mode = stat.S_IMODE(st.st_mode)
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"


# ---------------------------------------------------------------------------
# 5. Reject path with '..' components
# ---------------------------------------------------------------------------
class TestPathTraversalRejection:
    """Reject database path containing '..' components."""

    def test_reject_dotdot_in_path(self, tmp_path: Path) -> None:
        bad_path = str(tmp_path / ".." / "escape" / "budget.db")
        with pytest.raises((BudgetStoreError, ValueError)):
            SQLiteBudgetStore(bad_path)

    def test_reject_null_byte_in_path(self, tmp_path: Path) -> None:
        bad_path = str(tmp_path / "budget\x00evil.db")
        with pytest.raises((BudgetStoreError, ValueError)):
            SQLiteBudgetStore(bad_path)


# ---------------------------------------------------------------------------
# 6. Bounded history (limit parameter)
# ---------------------------------------------------------------------------
class TestTransactionLog:
    """Transaction log persistence and bounded queries."""

    def test_transaction_log_persisted(self, store: SQLiteBudgetStore) -> None:
        tracker_id = "log-test"
        snap = BudgetSnapshot(allocated=100_000_000, committed=0)
        store.save_snapshot(tracker_id, snap)

        # Log some transactions
        store.log_transaction(tracker_id, "record", 10_000_000)
        store.log_transaction(tracker_id, "record", 15_000_000)
        store.log_transaction(tracker_id, "record", 20_000_000)

        log = store.get_transaction_log(tracker_id)
        assert len(log) == 3

    def test_limit_parameter_respected(self, store: SQLiteBudgetStore) -> None:
        tracker_id = "limit-test"

        for i in range(20):
            store.log_transaction(tracker_id, "record", (i + 1) * 1_000_000)

        # Request only 5
        log = store.get_transaction_log(tracker_id, limit=5)
        assert len(log) == 5

    def test_default_limit_is_100(self, store: SQLiteBudgetStore) -> None:
        tracker_id = "default-limit-test"

        for i in range(150):
            store.log_transaction(tracker_id, "record", 1_000)

        log = store.get_transaction_log(tracker_id)
        assert len(log) == 100

    def test_empty_log_returns_empty_list(self, store: SQLiteBudgetStore) -> None:
        log = store.get_transaction_log("nonexistent-tracker")
        assert log == []

    def test_log_entries_ordered_by_timestamp(self, store: SQLiteBudgetStore) -> None:
        tracker_id = "order-test"

        store.log_transaction(tracker_id, "record", 100)
        store.log_transaction(tracker_id, "record", 200)
        store.log_transaction(tracker_id, "record", 300)

        log = store.get_transaction_log(tracker_id)
        assert len(log) == 3
        # Most recent last (ascending order by ID/timestamp)
        assert log[0]["amount"] == 100
        assert log[1]["amount"] == 200
        assert log[2]["amount"] == 300


# ---------------------------------------------------------------------------
# 7. Tracker ID validation
# ---------------------------------------------------------------------------
class TestTrackerIdValidation:
    """Tracker IDs must be safe identifiers."""

    def test_reject_dotdot_in_tracker_id(self, store: SQLiteBudgetStore) -> None:
        with pytest.raises((BudgetStoreError, ValueError)):
            store.save_snapshot("../escape", BudgetSnapshot(allocated=100, committed=0))

    def test_reject_slash_in_tracker_id(self, store: SQLiteBudgetStore) -> None:
        with pytest.raises((BudgetStoreError, ValueError)):
            store.save_snapshot(
                "path/traversal", BudgetSnapshot(allocated=100, committed=0)
            )

    def test_reject_null_byte_in_tracker_id(self, store: SQLiteBudgetStore) -> None:
        with pytest.raises((BudgetStoreError, ValueError)):
            store.save_snapshot(
                "evil\x00id", BudgetSnapshot(allocated=100, committed=0)
            )

    def test_valid_tracker_ids_accepted(self, store: SQLiteBudgetStore) -> None:
        """Alphanumeric, hyphens, underscores are all valid."""
        for valid_id in ["agent-001", "budget_tracker_1", "ABC123", "a"]:
            store.save_snapshot(valid_id, BudgetSnapshot(allocated=100, committed=0))
            snap = store.get_snapshot(valid_id)
            assert snap is not None


# ---------------------------------------------------------------------------
# 8. WAL mode enabled
# ---------------------------------------------------------------------------
class TestWalMode:
    """Verify WAL journal mode is set on the database."""

    def test_wal_mode_enabled(self, tmp_db_path: str) -> None:
        store = SQLiteBudgetStore(tmp_db_path)
        store.initialize()

        conn = sqlite3.connect(tmp_db_path)
        try:
            result = conn.execute("PRAGMA journal_mode").fetchone()
            assert result[0] == "wal"
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 9. Initialize before use
# ---------------------------------------------------------------------------
class TestInitializationRequired:
    """Operations fail with clear error if store is not initialized."""

    def test_save_before_init_raises(self, tmp_db_path: str) -> None:
        store = SQLiteBudgetStore(tmp_db_path)
        with pytest.raises(RuntimeError, match="not initialized"):
            store.save_snapshot("test", BudgetSnapshot(allocated=100, committed=0))

    def test_get_before_init_raises(self, tmp_db_path: str) -> None:
        store = SQLiteBudgetStore(tmp_db_path)
        with pytest.raises(RuntimeError, match="not initialized"):
            store.get_snapshot("test")

    def test_log_before_init_raises(self, tmp_db_path: str) -> None:
        store = SQLiteBudgetStore(tmp_db_path)
        with pytest.raises(RuntimeError, match="not initialized"):
            store.log_transaction("test", "record", 100)

    def test_get_log_before_init_raises(self, tmp_db_path: str) -> None:
        store = SQLiteBudgetStore(tmp_db_path)
        with pytest.raises(RuntimeError, match="not initialized"):
            store.get_transaction_log("test")


# ---------------------------------------------------------------------------
# 10. BudgetStore protocol compliance
# ---------------------------------------------------------------------------
class TestBudgetStoreProtocol:
    """SQLiteBudgetStore implements the BudgetStore protocol."""

    def test_has_get_snapshot(self, store: SQLiteBudgetStore) -> None:
        assert hasattr(store, "get_snapshot")
        assert callable(store.get_snapshot)

    def test_has_save_snapshot(self, store: SQLiteBudgetStore) -> None:
        assert hasattr(store, "save_snapshot")
        assert callable(store.save_snapshot)

    def test_has_get_transaction_log(self, store: SQLiteBudgetStore) -> None:
        assert hasattr(store, "get_transaction_log")
        assert callable(store.get_transaction_log)


# ---------------------------------------------------------------------------
# RT-02: Operations after close()
# ---------------------------------------------------------------------------
class TestOperationsAfterClose:
    """Operations on a closed store should fail cleanly."""

    def test_save_after_close_raises(self, tmp_db_path: str) -> None:
        store = SQLiteBudgetStore(tmp_db_path)
        store.initialize()
        store.close()
        with pytest.raises(RuntimeError, match="not initialized"):
            store.save_snapshot("test", BudgetSnapshot(allocated=100, committed=0))

    def test_get_after_close_raises(self, tmp_db_path: str) -> None:
        store = SQLiteBudgetStore(tmp_db_path)
        store.initialize()
        store.close()
        with pytest.raises(RuntimeError, match="not initialized"):
            store.get_snapshot("test")

    def test_log_after_close_raises(self, tmp_db_path: str) -> None:
        store = SQLiteBudgetStore(tmp_db_path)
        store.initialize()
        store.close()
        with pytest.raises(RuntimeError, match="not initialized"):
            store.log_transaction("test", "record", 100)


# ---------------------------------------------------------------------------
# RT-03: Invalid limit parameter
# ---------------------------------------------------------------------------
class TestInvalidLimit:
    """Invalid limit values should be rejected."""

    def test_zero_limit_raises(self, store: SQLiteBudgetStore) -> None:
        with pytest.raises(BudgetStoreError):
            store.get_transaction_log("test", limit=0)

    def test_negative_limit_raises(self, store: SQLiteBudgetStore) -> None:
        with pytest.raises(BudgetStoreError):
            store.get_transaction_log("test", limit=-5)

    def test_large_limit_capped(self, store: SQLiteBudgetStore) -> None:
        """Limits above 10,000 should be silently capped."""
        result = store.get_transaction_log("test", limit=999_999)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# RT-05: Concurrent access
# ---------------------------------------------------------------------------
class TestConcurrentAccess:
    """Concurrent store operations must not corrupt data."""

    def test_concurrent_save_get(self, tmp_db_path: str) -> None:
        import threading

        store = SQLiteBudgetStore(tmp_db_path)
        store.initialize()
        errors: list = []

        def writer(tid: int) -> None:
            try:
                for i in range(50):
                    store.save_snapshot(
                        f"t-{tid}",
                        BudgetSnapshot(allocated=1_000_000, committed=tid * 10 + i),
                    )
            except Exception as e:
                errors.append(f"Thread {tid}: {e}")

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrent errors: {errors}"

        for i in range(5):
            snap = store.get_snapshot(f"t-{i}")
            assert snap is not None
            assert snap.allocated == 1_000_000

        store.close()
