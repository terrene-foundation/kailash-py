# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for ShadowStore protocol, MemoryShadowStore, and SqliteShadowStore.

Issue #206: ShadowEnforcer persistent storage.

Covers:
- MemoryShadowStore: append, retrieve, metrics, bounded eviction, thread safety
- SqliteShadowStore: append, retrieve, metrics, persistence, bounded eviction
- ShadowEnforcer integration with store parameter
"""

from __future__ import annotations

import concurrent.futures
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone

import pytest

from kailash.trust.chain import VerificationResult
from kailash.trust.enforce.shadow import ShadowEnforcer
from kailash.trust.enforce.shadow_store import (
    MemoryShadowStore,
    ShadowStore,
    SqliteShadowStore,
)
from kailash.trust.enforce.strict import EnforcementRecord, Verdict


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_record(
    agent_id: str = "agent-001",
    action: str = "read_data",
    verdict: Verdict = Verdict.AUTO_APPROVED,
    ts_offset_seconds: int = 0,
) -> EnforcementRecord:
    """Create a test EnforcementRecord."""
    now = datetime.now(timezone.utc) + timedelta(seconds=ts_offset_seconds)
    return EnforcementRecord(
        agent_id=agent_id,
        action=action,
        verdict=verdict,
        verification_result=VerificationResult(
            valid=verdict != Verdict.BLOCKED,
            reason=f"Test: {verdict.value}",
            violations=[],
        ),
        timestamp=now,
        metadata={"test": True},
    )


def _make_verification_result(
    is_valid: bool = True,
    reason: str = "test",
) -> VerificationResult:
    """Create a VerificationResult for ShadowEnforcer.check()."""
    return VerificationResult(
        valid=is_valid,
        reason=reason,
        violations=[{"field": "test", "message": "violation"}] if not is_valid else [],
    )


# ---------------------------------------------------------------------------
# MemoryShadowStore Tests
# ---------------------------------------------------------------------------


class TestMemoryShadowStore:
    """MemoryShadowStore: in-memory bounded storage."""

    def test_protocol_conformance(self) -> None:
        """MemoryShadowStore must satisfy the ShadowStore protocol."""
        store = MemoryShadowStore()
        assert isinstance(store, ShadowStore)

    def test_append_and_retrieve(self) -> None:
        """Records appended can be retrieved."""
        store = MemoryShadowStore()
        record = _make_record()
        store.append_record(record)

        records = store.get_records()
        assert len(records) == 1
        assert records[0].agent_id == "agent-001"

    def test_retrieval_newest_first(self) -> None:
        """Records are returned newest first."""
        store = MemoryShadowStore()
        store.append_record(_make_record(agent_id="first", ts_offset_seconds=-10))
        store.append_record(_make_record(agent_id="second", ts_offset_seconds=0))

        records = store.get_records()
        assert records[0].agent_id == "second"
        assert records[1].agent_id == "first"

    def test_filter_by_agent_id(self) -> None:
        """Filtering by agent_id returns only matching records."""
        store = MemoryShadowStore()
        store.append_record(_make_record(agent_id="agent-A"))
        store.append_record(_make_record(agent_id="agent-B"))
        store.append_record(_make_record(agent_id="agent-A"))

        records = store.get_records(agent_id="agent-A")
        assert len(records) == 2
        assert all(r.agent_id == "agent-A" for r in records)

    def test_filter_by_since(self) -> None:
        """Filtering by since returns only records after the timestamp."""
        store = MemoryShadowStore()
        old = _make_record(agent_id="old", ts_offset_seconds=-3600)
        new = _make_record(agent_id="new", ts_offset_seconds=0)
        store.append_record(old)
        store.append_record(new)

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
        records = store.get_records(since=cutoff)
        assert len(records) == 1
        assert records[0].agent_id == "new"

    def test_limit(self) -> None:
        """Limit controls max returned records."""
        store = MemoryShadowStore()
        for i in range(10):
            store.append_record(_make_record(agent_id=f"agent-{i}"))
        records = store.get_records(limit=3)
        assert len(records) == 3

    def test_bounded_eviction(self) -> None:
        """Exceeding maxlen evicts oldest records."""
        store = MemoryShadowStore(maxlen=5)
        for i in range(10):
            store.append_record(_make_record(agent_id=f"agent-{i}"))
        records = store.get_records(limit=100)
        assert len(records) == 5

    def test_metrics_aggregation(self) -> None:
        """Metrics correctly aggregate verdict counts."""
        store = MemoryShadowStore()
        store.append_record(_make_record(verdict=Verdict.AUTO_APPROVED))
        store.append_record(_make_record(verdict=Verdict.AUTO_APPROVED))
        store.append_record(_make_record(verdict=Verdict.FLAGGED))
        store.append_record(_make_record(verdict=Verdict.BLOCKED))

        metrics = store.get_metrics()
        assert metrics["total_checks"] == 4
        assert metrics["auto_approved_count"] == 2
        assert metrics["flagged_count"] == 1
        assert metrics["blocked_count"] == 1
        assert metrics["held_count"] == 0

    def test_metrics_with_time_window(self) -> None:
        """Metrics respect the since parameter."""
        store = MemoryShadowStore()
        store.append_record(
            _make_record(verdict=Verdict.BLOCKED, ts_offset_seconds=-3600)
        )
        store.append_record(
            _make_record(verdict=Verdict.AUTO_APPROVED, ts_offset_seconds=0)
        )

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
        metrics = store.get_metrics(since=cutoff)
        assert metrics["total_checks"] == 1
        assert metrics["auto_approved_count"] == 1
        assert metrics["blocked_count"] == 0

    def test_clear(self) -> None:
        """Clear removes all records."""
        store = MemoryShadowStore()
        store.append_record(_make_record())
        store.clear()
        assert store.get_records() == []
        assert store.get_metrics()["total_checks"] == 0

    def test_thread_safety(self) -> None:
        """Concurrent writes should not corrupt the store."""
        store = MemoryShadowStore()

        def writer(n: int) -> None:
            for i in range(50):
                store.append_record(_make_record(agent_id=f"thread-{n}-{i}"))

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(writer, n) for n in range(4)]
            for f in futures:
                f.result()

        metrics = store.get_metrics()
        assert metrics["total_checks"] == 200


# ---------------------------------------------------------------------------
# SqliteShadowStore Tests
# ---------------------------------------------------------------------------


class TestSqliteShadowStore:
    """SqliteShadowStore: SQLite-backed persistent storage."""

    @pytest.fixture
    def db_path(self, tmp_path) -> str:
        """Temporary SQLite database path."""
        return str(tmp_path / "shadow_test.db")

    def test_protocol_conformance(self, db_path: str) -> None:
        """SqliteShadowStore must satisfy the ShadowStore protocol."""
        store = SqliteShadowStore(db_path)
        assert isinstance(store, ShadowStore)
        store.close()

    def test_append_and_retrieve(self, db_path: str) -> None:
        """Records persist to SQLite and can be retrieved."""
        store = SqliteShadowStore(db_path)
        record = _make_record()
        store.append_record(record)

        records = store.get_records()
        assert len(records) == 1
        assert records[0].agent_id == "agent-001"
        assert records[0].verdict == Verdict.AUTO_APPROVED
        store.close()

    def test_persistence_across_instances(self, db_path: str) -> None:
        """Records survive closing and reopening the store."""
        store1 = SqliteShadowStore(db_path)
        store1.append_record(_make_record(agent_id="persist-test"))
        store1.close()

        store2 = SqliteShadowStore(db_path)
        records = store2.get_records()
        assert len(records) == 1
        assert records[0].agent_id == "persist-test"
        store2.close()

    def test_retrieval_newest_first(self, db_path: str) -> None:
        """Records returned newest first."""
        store = SqliteShadowStore(db_path)
        store.append_record(_make_record(agent_id="old", ts_offset_seconds=-10))
        store.append_record(_make_record(agent_id="new", ts_offset_seconds=0))

        records = store.get_records()
        assert records[0].agent_id == "new"
        store.close()

    def test_filter_by_agent_id(self, db_path: str) -> None:
        """Filter by agent_id works in SQL."""
        store = SqliteShadowStore(db_path)
        store.append_record(_make_record(agent_id="A"))
        store.append_record(_make_record(agent_id="B"))
        store.append_record(_make_record(agent_id="A"))

        records = store.get_records(agent_id="A")
        assert len(records) == 2
        store.close()

    def test_filter_by_since(self, db_path: str) -> None:
        """Filter by since works in SQL."""
        store = SqliteShadowStore(db_path)
        store.append_record(_make_record(ts_offset_seconds=-3600))
        store.append_record(_make_record(ts_offset_seconds=0))

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
        records = store.get_records(since=cutoff)
        assert len(records) == 1
        store.close()

    def test_bounded_eviction(self, db_path: str) -> None:
        """Exceeding max_records trims oldest."""
        store = SqliteShadowStore(db_path, max_records=5)
        for i in range(10):
            store.append_record(_make_record(agent_id=f"agent-{i}"))

        records = store.get_records(limit=100)
        assert len(records) == 5
        store.close()

    def test_metrics_aggregation(self, db_path: str) -> None:
        """SQL-based metrics aggregation."""
        store = SqliteShadowStore(db_path)
        store.append_record(_make_record(verdict=Verdict.AUTO_APPROVED))
        store.append_record(_make_record(verdict=Verdict.FLAGGED))
        store.append_record(_make_record(verdict=Verdict.HELD))
        store.append_record(_make_record(verdict=Verdict.BLOCKED))

        metrics = store.get_metrics()
        assert metrics["total_checks"] == 4
        assert metrics["auto_approved_count"] == 1
        assert metrics["flagged_count"] == 1
        assert metrics["held_count"] == 1
        assert metrics["blocked_count"] == 1
        store.close()

    def test_metrics_with_time_window(self, db_path: str) -> None:
        """SQL-based time-windowed metrics."""
        store = SqliteShadowStore(db_path)
        store.append_record(
            _make_record(verdict=Verdict.BLOCKED, ts_offset_seconds=-3600)
        )
        store.append_record(
            _make_record(verdict=Verdict.AUTO_APPROVED, ts_offset_seconds=0)
        )

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
        metrics = store.get_metrics(since=cutoff)
        assert metrics["total_checks"] == 1
        assert metrics["auto_approved_count"] == 1
        store.close()

    def test_clear(self, db_path: str) -> None:
        """Clear deletes all records from SQLite."""
        store = SqliteShadowStore(db_path)
        store.append_record(_make_record())
        store.clear()

        assert store.get_records() == []
        assert store.get_metrics()["total_checks"] == 0
        store.close()

    def test_file_permissions(self, db_path: str) -> None:
        """SQLite file should have 0o600 permissions on POSIX."""
        store = SqliteShadowStore(db_path)
        store.close()

        if os.name == "posix":
            mode = os.stat(db_path).st_mode & 0o777
            assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"


# ---------------------------------------------------------------------------
# ShadowEnforcer Integration with Store
# ---------------------------------------------------------------------------


class TestShadowEnforcerStoreIntegration:
    """ShadowEnforcer with store parameter wires through correctly."""

    def test_enforcer_without_store_works(self) -> None:
        """Default behavior (no store) still works."""
        enforcer = ShadowEnforcer()
        result = _make_verification_result(is_valid=True)
        verdict = enforcer.check("agent-001", "read", result)
        assert verdict == Verdict.AUTO_APPROVED

    def test_enforcer_with_memory_store(self) -> None:
        """Records are persisted to MemoryShadowStore."""
        store = MemoryShadowStore()
        enforcer = ShadowEnforcer(store=store)

        result = _make_verification_result(is_valid=True)
        enforcer.check("agent-001", "read", result)
        enforcer.check("agent-002", "write", result)

        records = store.get_records()
        assert len(records) == 2

    def test_enforcer_with_sqlite_store(self, tmp_path) -> None:
        """Records are persisted to SqliteShadowStore."""
        db_path = str(tmp_path / "shadow_enforcer.db")
        store = SqliteShadowStore(db_path)
        enforcer = ShadowEnforcer(store=store)

        result = _make_verification_result(is_valid=True)
        enforcer.check("agent-001", "read", result)

        # Verify in store
        records = store.get_records()
        assert len(records) == 1
        assert records[0].agent_id == "agent-001"

        # Also verify in-memory metrics still work
        assert enforcer.metrics.total_checks == 1
        store.close()

    def test_enforcer_store_failure_does_not_block(self, tmp_path) -> None:
        """If the store raises, the enforcer still returns a verdict."""

        class BrokenStore:
            def append_record(self, record: EnforcementRecord) -> None:
                raise RuntimeError("store is broken")

        enforcer = ShadowEnforcer(store=BrokenStore())
        result = _make_verification_result(is_valid=True)

        # Should not raise -- store failure is logged but not propagated
        verdict = enforcer.check("agent-001", "read", result)
        assert verdict == Verdict.AUTO_APPROVED
        assert enforcer.metrics.total_checks == 1
