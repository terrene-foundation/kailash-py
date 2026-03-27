# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for SqliteTrustPlaneStore.

Validates:
- Protocol conformance (isinstance check)
- Round-trip CRUD for all record types (decisions, milestones, holds,
  delegates, reviews, anchors, WAL, manifest)
- Pagination (limit parameter)
- WAL mode enabled
- Close and reopen (data persists)
- Concurrent reads (two connections to same DB)
- Input validation (path traversal rejection)
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from kailash.trust.plane.delegation import DelegationRecipient, DelegateStatus, ReviewResolution
from kailash.trust.plane.holds import HoldRecord
from kailash.trust.plane.models import (
    DecisionRecord,
    DecisionType,
    MilestoneRecord,
    ProjectManifest,
)
from kailash.trust.plane.store import TrustPlaneStore
from kailash.trust.plane.store.sqlite import SqliteTrustPlaneStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path):
    """Return a path for a temporary SQLite database."""
    return tmp_path / "trust.db"


@pytest.fixture
def store(db_path):
    """Create an initialized SqliteTrustPlaneStore."""
    s = SqliteTrustPlaneStore(db_path)
    s.initialize()
    yield s
    s.close()


def _make_decision(**kwargs) -> DecisionRecord:
    defaults = dict(
        decision_type=DecisionType.SCOPE,
        decision="Test decision",
        rationale="Test rationale",
        confidence=0.9,
    )
    defaults.update(kwargs)
    return DecisionRecord(**defaults)


def _make_milestone(**kwargs) -> MilestoneRecord:
    defaults = dict(
        version="v0.1",
        description="Test milestone",
    )
    defaults.update(kwargs)
    return MilestoneRecord(**defaults)


def _make_hold(**kwargs) -> HoldRecord:
    defaults = dict(
        hold_id="hold-abc123def456",
        action="publish_paper",
        resource="docs/paper.md",
        context={"decision_type": "scope"},
        reason="Requires human review",
    )
    defaults.update(kwargs)
    return HoldRecord(**defaults)


def _make_delegate(**kwargs) -> DelegationRecipient:
    defaults = dict(
        delegate_id="del-abc123def456",
        name="Alice",
        dimensions=["operational", "data_access"],
        delegated_by="owner",
    )
    defaults.update(kwargs)
    return DelegationRecipient(**defaults)


def _make_review(**kwargs) -> ReviewResolution:
    defaults = dict(
        hold_id="hold-abc123def456",
        delegate_id="del-abc123def456",
        approved=True,
        reason="Reviewed and approved",
        dimension="operational",
    )
    defaults.update(kwargs)
    return ReviewResolution(**defaults)


def _make_manifest(**kwargs) -> ProjectManifest:
    defaults = dict(
        project_id="proj-abc123",
        project_name="Test Project",
        author="Test Author",
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return ProjectManifest(**defaults)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """Verify SqliteTrustPlaneStore satisfies TrustPlaneStore protocol."""

    def test_is_runtime_checkable(self, store):
        """SqliteTrustPlaneStore must satisfy @runtime_checkable protocol."""
        assert isinstance(store, TrustPlaneStore)

    def test_not_a_store(self):
        """Non-conforming objects must NOT satisfy the protocol."""

        class NotAStore:
            pass

        assert not isinstance(NotAStore(), TrustPlaneStore)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_initialize_idempotent(self, db_path):
        """Calling initialize() twice must not raise."""
        s = SqliteTrustPlaneStore(db_path)
        s.initialize()
        s.initialize()
        s.close()

    def test_close_is_safe(self, store):
        """close() must not raise, even if called twice."""
        store.close()
        store.close()


# ---------------------------------------------------------------------------
# WAL mode
# ---------------------------------------------------------------------------


class TestWALMode:
    def test_wal_mode_enabled(self, db_path):
        """The database must use WAL journal mode."""
        s = SqliteTrustPlaneStore(db_path)
        s.initialize()
        conn = sqlite3.connect(str(db_path))
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        s.close()
        assert mode == "wal"


# ---------------------------------------------------------------------------
# Decision Records
# ---------------------------------------------------------------------------


class TestDecisionRecords:
    def test_store_and_get_decision(self, store):
        decision = _make_decision()
        store.store_decision(decision)
        retrieved = store.get_decision(decision.decision_id)
        assert retrieved.decision_id == decision.decision_id
        assert retrieved.decision == decision.decision
        assert retrieved.rationale == decision.rationale

    def test_get_decision_not_found(self, store):
        with pytest.raises(KeyError, match="not found"):
            store.get_decision("dec-nonexistent12")

    def test_list_decisions_empty(self, store):
        assert store.list_decisions() == []

    def test_list_decisions_returns_all(self, store):
        d1 = _make_decision(decision="First")
        d2 = _make_decision(decision="Second")
        store.store_decision(d1)
        store.store_decision(d2)
        result = store.list_decisions()
        assert len(result) == 2

    def test_list_decisions_bounded(self, store):
        for i in range(5):
            store.store_decision(_make_decision(decision=f"Decision {i}"))
        result = store.list_decisions(limit=3)
        assert len(result) == 3

    def test_decision_roundtrip_fidelity(self, store):
        decision = _make_decision(
            alternatives=["alt1", "alt2"],
            risks=["risk1"],
            confidence=0.75,
        )
        store.store_decision(decision)
        retrieved = store.get_decision(decision.decision_id)
        assert retrieved.alternatives == decision.alternatives
        assert retrieved.risks == decision.risks
        assert retrieved.confidence == decision.confidence


# ---------------------------------------------------------------------------
# Milestone Records
# ---------------------------------------------------------------------------


class TestMilestoneRecords:
    def test_store_and_get_milestone(self, store):
        ms = _make_milestone()
        store.store_milestone(ms)
        retrieved = store.get_milestone(ms.milestone_id)
        assert retrieved.milestone_id == ms.milestone_id
        assert retrieved.version == ms.version

    def test_get_milestone_not_found(self, store):
        with pytest.raises(KeyError, match="not found"):
            store.get_milestone("ms-nonexistent12")

    def test_list_milestones(self, store):
        m1 = _make_milestone(version="v0.1")
        m2 = _make_milestone(version="v0.2")
        store.store_milestone(m1)
        store.store_milestone(m2)
        result = store.list_milestones()
        assert len(result) == 2

    def test_list_milestones_bounded(self, store):
        for i in range(5):
            store.store_milestone(_make_milestone(version=f"v{i}"))
        result = store.list_milestones(limit=2)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Hold Records
# ---------------------------------------------------------------------------


class TestHoldRecords:
    def test_store_and_get_hold(self, store):
        hold = _make_hold()
        store.store_hold(hold)
        retrieved = store.get_hold(hold.hold_id)
        assert retrieved.hold_id == hold.hold_id
        assert retrieved.action == hold.action
        assert retrieved.status == "pending"

    def test_get_hold_not_found(self, store):
        with pytest.raises(KeyError, match="not found"):
            store.get_hold("hold-nonexistent1")

    def test_update_hold(self, store):
        hold = _make_hold()
        store.store_hold(hold)
        hold.status = "approved"
        hold.resolved_by = "Alice"
        hold.resolved_at = datetime.now(timezone.utc)
        store.update_hold(hold)
        retrieved = store.get_hold(hold.hold_id)
        assert retrieved.status == "approved"
        assert retrieved.resolved_by == "Alice"

    def test_list_holds_all(self, store):
        h1 = _make_hold(hold_id="hold-aaa111222333")
        h2 = _make_hold(hold_id="hold-bbb111222333")
        store.store_hold(h1)
        store.store_hold(h2)
        result = store.list_holds()
        assert len(result) == 2

    def test_list_holds_by_status(self, store):
        h1 = _make_hold(hold_id="hold-aaa111222333")
        h2 = _make_hold(hold_id="hold-bbb111222333", status="approved")
        store.store_hold(h1)
        store.store_hold(h2)
        pending = store.list_holds(status="pending")
        assert len(pending) == 1
        assert pending[0].hold_id == "hold-aaa111222333"

    def test_list_holds_bounded(self, store):
        for i in range(5):
            store.store_hold(_make_hold(hold_id=f"hold-item{i:010d}"))
        result = store.list_holds(limit=3)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Delegate Records
# ---------------------------------------------------------------------------


class TestDelegateRecords:
    def test_store_and_get_delegate(self, store):
        delegate = _make_delegate()
        store.store_delegate(delegate)
        retrieved = store.get_delegate(delegate.delegate_id)
        assert retrieved.delegate_id == delegate.delegate_id
        assert retrieved.name == delegate.name
        assert retrieved.dimensions == delegate.dimensions

    def test_get_delegate_not_found(self, store):
        with pytest.raises(KeyError, match="not found"):
            store.get_delegate("del-nonexistent1")

    def test_update_delegate(self, store):
        delegate = _make_delegate()
        store.store_delegate(delegate)
        delegate.status = DelegateStatus.REVOKED
        delegate.revoked_at = datetime.now(timezone.utc)
        store.update_delegate(delegate)
        retrieved = store.get_delegate(delegate.delegate_id)
        assert retrieved.status == DelegateStatus.REVOKED

    def test_list_delegates_active_only(self, store):
        d1 = _make_delegate(delegate_id="del-aaa111222333")
        d2 = _make_delegate(
            delegate_id="del-bbb111222333",
            name="Bob",
            status=DelegateStatus.REVOKED,
        )
        store.store_delegate(d1)
        store.store_delegate(d2)
        active = store.list_delegates(active_only=True)
        assert len(active) == 1
        assert active[0].delegate_id == "del-aaa111222333"

    def test_list_delegates_all(self, store):
        d1 = _make_delegate(delegate_id="del-aaa111222333")
        d2 = _make_delegate(
            delegate_id="del-bbb111222333",
            name="Bob",
            status=DelegateStatus.REVOKED,
        )
        store.store_delegate(d1)
        store.store_delegate(d2)
        all_delegates = store.list_delegates(active_only=False)
        assert len(all_delegates) == 2

    def test_list_delegates_bounded(self, store):
        for i in range(5):
            store.store_delegate(
                _make_delegate(
                    delegate_id=f"del-item{i:010d}",
                    name=f"Delegate-{i}",
                )
            )
        result = store.list_delegates(active_only=False, limit=2)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Review Records
# ---------------------------------------------------------------------------


class TestReviewRecords:
    def test_store_and_list_reviews(self, store):
        review = _make_review()
        store.store_review(review)
        reviews = store.list_reviews()
        assert len(reviews) == 1
        assert reviews[0].hold_id == review.hold_id
        assert reviews[0].approved is True

    def test_list_reviews_filtered_by_hold(self, store):
        r1 = _make_review(hold_id="hold-aaa111222333")
        r2 = _make_review(
            hold_id="hold-bbb111222333",
            delegate_id="del-bbb111222333",
        )
        store.store_review(r1)
        store.store_review(r2)
        filtered = store.list_reviews(hold_id="hold-aaa111222333")
        assert len(filtered) == 1
        assert filtered[0].hold_id == "hold-aaa111222333"

    def test_list_reviews_bounded(self, store):
        for i in range(5):
            store.store_review(
                _make_review(
                    hold_id=f"hold-item{i:010d}",
                    delegate_id=f"del-item{i:010d}",
                )
            )
        result = store.list_reviews(limit=3)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


class TestManifest:
    def test_store_and_get_manifest(self, store):
        manifest = _make_manifest()
        store.store_manifest(manifest)
        retrieved = store.get_manifest()
        assert retrieved.project_id == manifest.project_id
        assert retrieved.project_name == manifest.project_name
        assert retrieved.author == manifest.author

    def test_get_manifest_not_found(self, store):
        with pytest.raises(KeyError, match="[Mm]anifest"):
            store.get_manifest()

    def test_manifest_update(self, store):
        manifest = _make_manifest()
        store.store_manifest(manifest)
        manifest.total_decisions = 5
        store.store_manifest(manifest)
        retrieved = store.get_manifest()
        assert retrieved.total_decisions == 5


# ---------------------------------------------------------------------------
# Anchors
# ---------------------------------------------------------------------------


class TestAnchors:
    def test_store_and_get_anchor(self, store):
        data = {"anchor_id": "anc-abc123", "action": "test", "result": "success"}
        store.store_anchor("anc-abc123", data)
        retrieved = store.get_anchor("anc-abc123")
        assert retrieved["anchor_id"] == "anc-abc123"

    def test_get_anchor_not_found(self, store):
        with pytest.raises(KeyError, match="not found"):
            store.get_anchor("anc-nonexistent1")

    def test_list_anchors(self, store):
        store.store_anchor("anc-aaa111222333", {"anchor_id": "anc-aaa111222333"})
        store.store_anchor("anc-bbb111222333", {"anchor_id": "anc-bbb111222333"})
        result = store.list_anchors()
        assert len(result) == 2

    def test_list_anchors_bounded(self, store):
        for i in range(5):
            aid = f"anc-item{i:010d}"
            store.store_anchor(aid, {"anchor_id": aid})
        result = store.list_anchors(limit=3)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# WAL
# ---------------------------------------------------------------------------


class TestWAL:
    def test_store_and_get_wal(self, store):
        wal_data = {
            "root_delegate_id": "del-abc",
            "planned_revocations": ["del-abc", "del-def"],
            "reason": "test",
        }
        store.store_wal(wal_data)
        retrieved = store.get_wal()
        assert retrieved is not None
        assert retrieved["root_delegate_id"] == "del-abc"

    def test_get_wal_when_none(self, store):
        assert store.get_wal() is None

    def test_delete_wal(self, store):
        store.store_wal({"test": True})
        store.delete_wal()
        assert store.get_wal() is None

    def test_delete_wal_when_none_is_noop(self, store):
        """delete_wal() when no WAL exists must not raise."""
        store.delete_wal()


# ---------------------------------------------------------------------------
# Persistence (close and reopen)
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_close_and_reopen(self, db_path):
        """Data must persist after close and reopen."""
        s1 = SqliteTrustPlaneStore(db_path)
        s1.initialize()
        decision = _make_decision()
        s1.store_decision(decision)
        s1.close()

        s2 = SqliteTrustPlaneStore(db_path)
        s2.initialize()
        retrieved = s2.get_decision(decision.decision_id)
        assert retrieved.decision_id == decision.decision_id
        assert retrieved.decision == decision.decision
        s2.close()


# ---------------------------------------------------------------------------
# Concurrent reads
# ---------------------------------------------------------------------------


class TestConcurrency:
    def test_concurrent_reads(self, db_path):
        """Two threads reading the same DB must not corrupt data."""
        s = SqliteTrustPlaneStore(db_path)
        s.initialize()
        decision = _make_decision()
        s.store_decision(decision)

        results: list[DecisionRecord] = []
        errors: list[Exception] = []

        def reader():
            try:
                # Each thread gets its own connection via threading.local
                r = SqliteTrustPlaneStore(db_path)
                r.initialize()
                rec = r.get_decision(decision.decision_id)
                results.append(rec)
                r.close()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        s.close()

        assert not errors, f"Concurrent reads produced errors: {errors}"
        assert len(results) == 4
        for r in results:
            assert r.decision_id == decision.decision_id


# ---------------------------------------------------------------------------
# Input validation (path traversal rejection)
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_path_traversal_decision_id(self, store):
        decision = _make_decision()
        decision.decision_id = "../../../etc/passwd"
        with pytest.raises(ValueError):
            store.store_decision(decision)

    def test_path_traversal_hold_id(self, store):
        hold = _make_hold(hold_id="../../../etc/passwd")
        with pytest.raises(ValueError):
            store.store_hold(hold)

    def test_path_traversal_delegate_id(self, store):
        delegate = _make_delegate(delegate_id="../../../etc/passwd")
        with pytest.raises(ValueError):
            store.store_delegate(delegate)

    def test_null_byte_injection(self, store):
        hold = _make_hold(hold_id="hold-abc\x00injected")
        with pytest.raises(ValueError):
            store.store_hold(hold)

    def test_anchor_invalid_id_rejected(self, store):
        with pytest.raises(ValueError):
            store.store_anchor("../../../etc/passwd", {"bad": True})

    def test_get_decision_invalid_id(self, store):
        with pytest.raises(ValueError):
            store.get_decision("../../../etc/passwd")

    def test_get_hold_invalid_id(self, store):
        with pytest.raises(ValueError):
            store.get_hold("../bad")

    def test_get_delegate_invalid_id(self, store):
        with pytest.raises(ValueError):
            store.get_delegate("../bad")

    def test_get_anchor_invalid_id(self, store):
        with pytest.raises(ValueError):
            store.get_anchor("../bad")
