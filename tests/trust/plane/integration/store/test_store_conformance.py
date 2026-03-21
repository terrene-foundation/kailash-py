# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-package store conformance tests.

Parametrized test suite that runs identical behavioral tests against
both ``FileSystemTrustPlaneStore`` and ``SqliteTrustPlaneStore``,
verifying that both backends satisfy the ``TrustPlaneStore`` protocol
with consistent semantics.

Test categories:
1. Protocol conformance (isinstance checks)
2. Round-trip for all 7 record types
3. Update operations (holds, delegates)
4. Pagination (limit parameter)
5. Empty store behavior
6. Input validation (Store Security Contract)
7. Bounded results
8. WAL operations
9. Close and reopen persistence
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from kailash.trust.plane.delegation import Delegate, DelegateStatus, ReviewResolution
from kailash.trust.plane.holds import HoldRecord
from kailash.trust.plane.models import (
    DecisionRecord,
    DecisionType,
    MilestoneRecord,
    ProjectManifest,
)
from kailash.trust.plane.store import TrustPlaneStore
from kailash.trust.plane.store.filesystem import FileSystemTrustPlaneStore
from kailash.trust.plane.store.sqlite import SqliteTrustPlaneStore

logger = logging.getLogger(__name__)

# Conditionally import PostgreSQL backend
_HAS_PSYCOPG = False
_PG_AVAILABLE = False
_PG_DSN_ENV = "TRUSTPLANE_TEST_POSTGRES_DSN"

try:
    import psycopg  # noqa: F401

    _HAS_PSYCOPG = True

    import os as _os

    _pg_dsn = _os.environ.get(_PG_DSN_ENV)
    if _pg_dsn:
        try:
            _conn = psycopg.connect(_pg_dsn)
            _conn.close()
            _PG_AVAILABLE = True
        except Exception:
            pass
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Parametrized store fixture
# ---------------------------------------------------------------------------


def _conformance_params():
    """Build the list of backend params, including postgres if available."""
    params = ["filesystem", "sqlite"]
    if _PG_AVAILABLE:
        params.append("postgres")
    return params


def _clean_pg_tables(dsn: str) -> None:
    """Drop all trust-plane tables to ensure a clean state for conformance tests."""
    tables = [
        "decisions",
        "milestones",
        "holds",
        "delegates",
        "reviews",
        "anchors",
        "manifest",
        "delegates_wal",
        "meta",
    ]
    conn = psycopg.connect(dsn)
    for table in tables:
        conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    conn.commit()
    conn.close()


@pytest.fixture(params=_conformance_params())
def store(request, tmp_path):
    """Create an initialized store for all available backends."""
    if request.param == "filesystem":
        s = FileSystemTrustPlaneStore(tmp_path / "trust")
        s.initialize()
        yield s
        s.close()
    elif request.param == "sqlite":
        s = SqliteTrustPlaneStore(tmp_path / "trust.db")
        s.initialize()
        yield s
        s.close()
    elif request.param == "postgres":
        from kailash.trust.plane.store.postgres import PostgresTrustPlaneStore

        dsn = _os.environ[_PG_DSN_ENV]
        _clean_pg_tables(dsn)
        s = PostgresTrustPlaneStore(dsn, pool_size=5)
        s.initialize()
        yield s
        s.close()
        _clean_pg_tables(dsn)


@pytest.fixture(params=_conformance_params())
def store_factory(request, tmp_path):
    """Return a factory callable that creates stores at a fixed path.

    Used for close-and-reopen tests where the same path must be reused.
    Returns ``(create_store, path)`` where ``create_store()`` returns a
    new initialized store instance at ``path``.
    """
    if request.param == "filesystem":
        path = tmp_path / "trust"

        def create():
            s = FileSystemTrustPlaneStore(path)
            s.initialize()
            return s

        yield create, path
    elif request.param == "sqlite":
        path = tmp_path / "trust.db"

        def create():
            s = SqliteTrustPlaneStore(path)
            s.initialize()
            return s

        yield create, path
    elif request.param == "postgres":
        from kailash.trust.plane.store.postgres import PostgresTrustPlaneStore

        dsn = _os.environ[_PG_DSN_ENV]
        _clean_pg_tables(dsn)

        def create():
            s = PostgresTrustPlaneStore(dsn, pool_size=5)
            s.initialize()
            return s

        yield create, dsn
        _clean_pg_tables(dsn)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


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


def _make_delegate(**kwargs) -> Delegate:
    defaults = dict(
        delegate_id="del-abc123def456",
        name="Alice",
        dimensions=["operational", "data_access"],
        delegated_by="owner",
    )
    defaults.update(kwargs)
    return Delegate(**defaults)


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
# 1. Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """Both backends must satisfy the TrustPlaneStore protocol."""

    def test_isinstance_check(self, store):
        assert isinstance(store, TrustPlaneStore)

    def test_non_conforming_object_rejected(self):
        class NotAStore:
            pass

        assert not isinstance(NotAStore(), TrustPlaneStore)


# ---------------------------------------------------------------------------
# 2. Round-trip for all 7 record types
# ---------------------------------------------------------------------------


class TestDecisionRoundTrip:
    def test_store_and_get(self, store):
        decision = _make_decision()
        store.store_decision(decision)
        retrieved = store.get_decision(decision.decision_id)
        assert retrieved.decision_id == decision.decision_id
        assert retrieved.decision == decision.decision
        assert retrieved.rationale == decision.rationale
        assert retrieved.confidence == decision.confidence

    def test_get_not_found(self, store):
        with pytest.raises(KeyError, match="not found"):
            store.get_decision("dec-nonexistent12")

    def test_list_returns_stored(self, store):
        d1 = _make_decision(decision="First")
        d2 = _make_decision(decision="Second")
        store.store_decision(d1)
        store.store_decision(d2)
        result = store.list_decisions()
        assert len(result) == 2

    def test_roundtrip_fidelity(self, store):
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


class TestMilestoneRoundTrip:
    def test_store_and_get(self, store):
        ms = _make_milestone()
        store.store_milestone(ms)
        retrieved = store.get_milestone(ms.milestone_id)
        assert retrieved.milestone_id == ms.milestone_id
        assert retrieved.version == ms.version

    def test_get_not_found(self, store):
        with pytest.raises(KeyError, match="not found"):
            store.get_milestone("ms-nonexistent12")

    def test_list_returns_stored(self, store):
        m1 = _make_milestone(version="v0.1")
        m2 = _make_milestone(version="v0.2")
        store.store_milestone(m1)
        store.store_milestone(m2)
        result = store.list_milestones()
        assert len(result) == 2


class TestHoldRoundTrip:
    def test_store_and_get(self, store):
        hold = _make_hold()
        store.store_hold(hold)
        retrieved = store.get_hold(hold.hold_id)
        assert retrieved.hold_id == hold.hold_id
        assert retrieved.action == hold.action
        assert retrieved.status == "pending"

    def test_get_not_found(self, store):
        with pytest.raises(KeyError, match="not found"):
            store.get_hold("hold-nonexistent1")

    def test_list_returns_stored(self, store):
        h1 = _make_hold(hold_id="hold-aaa111222333")
        h2 = _make_hold(hold_id="hold-bbb111222333")
        store.store_hold(h1)
        store.store_hold(h2)
        result = store.list_holds()
        assert len(result) == 2

    def test_list_by_status(self, store):
        h1 = _make_hold(hold_id="hold-aaa111222333")
        h2 = _make_hold(hold_id="hold-bbb111222333", status="approved")
        store.store_hold(h1)
        store.store_hold(h2)
        pending = store.list_holds(status="pending")
        assert len(pending) == 1
        assert pending[0].hold_id == "hold-aaa111222333"


class TestDelegateRoundTrip:
    def test_store_and_get(self, store):
        delegate = _make_delegate()
        store.store_delegate(delegate)
        retrieved = store.get_delegate(delegate.delegate_id)
        assert retrieved.delegate_id == delegate.delegate_id
        assert retrieved.name == delegate.name
        assert retrieved.dimensions == delegate.dimensions

    def test_get_not_found(self, store):
        with pytest.raises(KeyError, match="not found"):
            store.get_delegate("del-nonexistent1")

    def test_list_active_only(self, store):
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

    def test_list_all(self, store):
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


class TestReviewRoundTrip:
    def test_store_and_list(self, store):
        review = _make_review()
        store.store_review(review)
        reviews = store.list_reviews()
        assert len(reviews) == 1
        assert reviews[0].hold_id == review.hold_id
        assert reviews[0].approved is True

    def test_list_filtered_by_hold(self, store):
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


class TestAnchorRoundTrip:
    def test_store_and_get(self, store):
        data = {"anchor_id": "anc-abc123", "action": "test", "result": "success"}
        store.store_anchor("anc-abc123", data)
        retrieved = store.get_anchor("anc-abc123")
        assert retrieved["anchor_id"] == "anc-abc123"
        assert retrieved["action"] == "test"

    def test_get_not_found(self, store):
        with pytest.raises(KeyError, match="not found"):
            store.get_anchor("anc-nonexistent1")

    def test_list_returns_stored(self, store):
        store.store_anchor("anc-aaa111222333", {"anchor_id": "anc-aaa111222333"})
        store.store_anchor("anc-bbb111222333", {"anchor_id": "anc-bbb111222333"})
        result = store.list_anchors()
        assert len(result) == 2


class TestManifestRoundTrip:
    def test_store_and_get(self, store):
        manifest = _make_manifest()
        store.store_manifest(manifest)
        retrieved = store.get_manifest()
        assert retrieved.project_id == manifest.project_id
        assert retrieved.project_name == manifest.project_name
        assert retrieved.author == manifest.author

    def test_get_not_found(self, store):
        with pytest.raises(KeyError, match="[Mm]anifest"):
            store.get_manifest()

    def test_manifest_overwrite(self, store):
        manifest = _make_manifest()
        store.store_manifest(manifest)
        manifest.total_decisions = 5
        store.store_manifest(manifest)
        retrieved = store.get_manifest()
        assert retrieved.total_decisions == 5


# ---------------------------------------------------------------------------
# 3. Update operations
# ---------------------------------------------------------------------------


class TestUpdateOperations:
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

    def test_update_delegate(self, store):
        delegate = _make_delegate()
        store.store_delegate(delegate)
        delegate.status = DelegateStatus.REVOKED
        delegate.revoked_at = datetime.now(timezone.utc)
        store.update_delegate(delegate)
        retrieved = store.get_delegate(delegate.delegate_id)
        assert retrieved.status == DelegateStatus.REVOKED


# ---------------------------------------------------------------------------
# 4. Pagination (limit parameter)
# ---------------------------------------------------------------------------


class TestPagination:
    def test_list_decisions_bounded(self, store):
        for i in range(5):
            store.store_decision(_make_decision(decision=f"Decision {i}"))
        result = store.list_decisions(limit=3)
        assert len(result) == 3

    def test_list_milestones_bounded(self, store):
        for i in range(5):
            store.store_milestone(_make_milestone(version=f"v{i}"))
        result = store.list_milestones(limit=2)
        assert len(result) == 2

    def test_list_holds_bounded(self, store):
        for i in range(5):
            store.store_hold(_make_hold(hold_id=f"hold-item{i:010d}"))
        result = store.list_holds(limit=3)
        assert len(result) == 3

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

    def test_list_anchors_bounded(self, store):
        for i in range(5):
            aid = f"anc-item{i:010d}"
            store.store_anchor(aid, {"anchor_id": aid})
        result = store.list_anchors(limit=3)
        assert len(result) == 3

    def test_limit_of_one(self, store):
        """Limit=1 must return exactly one record when multiple exist."""
        for i in range(3):
            store.store_decision(_make_decision(decision=f"D{i}"))
        assert len(store.list_decisions(limit=1)) == 1


# ---------------------------------------------------------------------------
# 5. Empty store behavior
# ---------------------------------------------------------------------------


class TestEmptyStore:
    def test_list_decisions_empty(self, store):
        assert store.list_decisions() == []

    def test_list_milestones_empty(self, store):
        assert store.list_milestones() == []

    def test_list_holds_empty(self, store):
        assert store.list_holds() == []

    def test_list_delegates_empty(self, store):
        assert store.list_delegates() == []

    def test_list_reviews_empty(self, store):
        assert store.list_reviews() == []

    def test_list_anchors_empty(self, store):
        assert store.list_anchors() == []


# ---------------------------------------------------------------------------
# 6. Input validation (Store Security Contract)
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_path_traversal_decision_store(self, store):
        decision = _make_decision()
        decision.decision_id = "../../../etc/passwd"
        with pytest.raises(ValueError):
            store.store_decision(decision)

    def test_path_traversal_decision_get(self, store):
        with pytest.raises(ValueError):
            store.get_decision("../../../etc/passwd")

    def test_path_traversal_hold_store(self, store):
        hold = _make_hold(hold_id="../../../etc/passwd")
        with pytest.raises(ValueError):
            store.store_hold(hold)

    def test_path_traversal_hold_get(self, store):
        with pytest.raises(ValueError):
            store.get_hold("../bad")

    def test_path_traversal_delegate_store(self, store):
        delegate = _make_delegate(delegate_id="../../../etc/passwd")
        with pytest.raises(ValueError):
            store.store_delegate(delegate)

    def test_path_traversal_delegate_get(self, store):
        with pytest.raises(ValueError):
            store.get_delegate("../bad")

    def test_path_traversal_anchor_store(self, store):
        with pytest.raises(ValueError):
            store.store_anchor("../../../etc/passwd", {"bad": True})

    def test_path_traversal_anchor_get(self, store):
        with pytest.raises(ValueError):
            store.get_anchor("../bad")

    def test_null_byte_injection(self, store):
        hold = _make_hold(hold_id="hold-abc\x00injected")
        with pytest.raises(ValueError):
            store.store_hold(hold)

    def test_path_traversal_milestone_store(self, store):
        ms = _make_milestone()
        ms.milestone_id = "../../../etc/passwd"
        with pytest.raises(ValueError):
            store.store_milestone(ms)

    def test_path_traversal_milestone_get(self, store):
        with pytest.raises(ValueError):
            store.get_milestone("../bad")


# ---------------------------------------------------------------------------
# 7. Bounded results verification
# ---------------------------------------------------------------------------


class TestBoundedResults:
    def test_default_limit_not_exceeded(self, store):
        """Even with many records, default limit caps the result set."""
        # Store a modest number and confirm list respects limit=2
        for i in range(4):
            store.store_decision(_make_decision(decision=f"Decision {i}"))
        result = store.list_decisions(limit=2)
        assert len(result) <= 2

    def test_limit_zero_returns_empty(self, store):
        """Limit=0 should return no results."""
        store.store_decision(_make_decision())
        result = store.list_decisions(limit=0)
        assert len(result) == 0

    def test_limit_greater_than_count(self, store):
        """Limit larger than total records returns all records."""
        store.store_decision(_make_decision(decision="Only one"))
        result = store.list_decisions(limit=100)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# 8. WAL operations
# ---------------------------------------------------------------------------


class TestWALOperations:
    def test_store_and_get_wal(self, store):
        wal_data = {
            "root_delegate_id": "del-abc",
            "planned_revocations": ["del-abc", "del-def"],
            "reason": "cascade test",
        }
        store.store_wal(wal_data)
        retrieved = store.get_wal()
        assert retrieved is not None
        assert retrieved["root_delegate_id"] == "del-abc"
        assert len(retrieved["planned_revocations"]) == 2

    def test_get_wal_returns_none_when_empty(self, store):
        assert store.get_wal() is None

    def test_delete_wal(self, store):
        store.store_wal({"test": True})
        store.delete_wal()
        assert store.get_wal() is None

    def test_delete_wal_noop_when_absent(self, store):
        """delete_wal() when no WAL exists must not raise."""
        store.delete_wal()

    def test_wal_overwrite(self, store):
        """Storing WAL twice overwrites the previous data."""
        store.store_wal({"version": 1})
        store.store_wal({"version": 2})
        retrieved = store.get_wal()
        assert retrieved is not None
        assert retrieved["version"] == 2


# ---------------------------------------------------------------------------
# 9. Close and reopen persistence
# ---------------------------------------------------------------------------


class TestCloseAndReopen:
    def test_data_persists_after_close_and_reopen(self, store_factory):
        """Data stored before close must be retrievable after reopen."""
        create_store, path = store_factory

        s1 = create_store()
        decision = _make_decision()
        s1.store_decision(decision)
        s1.close()

        s2 = create_store()
        retrieved = s2.get_decision(decision.decision_id)
        assert retrieved.decision_id == decision.decision_id
        assert retrieved.decision == decision.decision
        s2.close()

    def test_multiple_record_types_persist(self, store_factory):
        """All record types must survive close/reopen cycle."""
        create_store, path = store_factory

        s1 = create_store()
        decision = _make_decision()
        hold = _make_hold()
        manifest = _make_manifest()
        s1.store_decision(decision)
        s1.store_hold(hold)
        s1.store_manifest(manifest)
        s1.close()

        s2 = create_store()
        assert s2.get_decision(decision.decision_id).decision == decision.decision
        assert s2.get_hold(hold.hold_id).hold_id == hold.hold_id
        assert s2.get_manifest().project_id == manifest.project_id
        s2.close()
