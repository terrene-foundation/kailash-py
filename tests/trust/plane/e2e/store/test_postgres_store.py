# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""PostgreSQL-specific store tests.

Tests that exercise PostgreSQL-specific behavior beyond the conformance
suite, including connection pooling, concurrent writes, schema
versioning, and JSONB column usage.

These tests require a running PostgreSQL instance. Set the environment
variable ``TRUSTPLANE_TEST_POSTGRES_DSN`` to a valid connection string:

    export TRUSTPLANE_TEST_POSTGRES_DSN="postgresql://user:pass@localhost:5432/trustplane_test"

Tests are skipped if:
- ``psycopg`` is not installed
- ``TRUSTPLANE_TEST_POSTGRES_DSN`` is not set
- The PostgreSQL server is unreachable
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone

import pytest

psycopg = pytest.importorskip(
    "psycopg", reason="psycopg not installed", exc_type=ImportError
)

from kailash.trust.plane.delegation import DelegationRecipient, DelegateStatus, ReviewResolution
from kailash.trust.plane.holds import HoldRecord
from kailash.trust.plane.models import (
    DecisionRecord,
    DecisionType,
    MilestoneRecord,
    ProjectManifest,
)
from kailash.trust.plane.store.postgres import SCHEMA_VERSION, PostgresTrustPlaneStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PG_DSN_ENV = "TRUSTPLANE_TEST_POSTGRES_DSN"


def _get_dsn() -> str | None:
    """Return the test DSN or None if not configured."""
    return os.environ.get(_PG_DSN_ENV)


def _pg_available() -> bool:
    """Check if PostgreSQL is available for testing."""
    dsn = _get_dsn()
    if dsn is None:
        return False
    try:
        conn = psycopg.connect(dsn)
        conn.close()
        return True
    except Exception:
        return False


# Skip entire module if PostgreSQL is not available
pytestmark = pytest.mark.skipif(
    not _pg_available(),
    reason=f"PostgreSQL not available (set {_PG_DSN_ENV})",
)


def _clean_tables(dsn: str) -> None:
    """Drop all trust-plane tables to ensure a clean state."""
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
    with psycopg.connect(dsn) as conn:
        for table in tables:
            conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        conn.commit()


@pytest.fixture
def pg_store():
    """Create a PostgresTrustPlaneStore connected to the test database."""
    dsn = _get_dsn()
    _clean_tables(dsn)
    store = PostgresTrustPlaneStore(dsn, pool_size=5)
    store.initialize()
    yield store
    store.close()
    _clean_tables(dsn)


@pytest.fixture
def pg_dsn():
    """Return the PostgreSQL DSN for tests that need raw connections."""
    return _get_dsn()


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
# 1. Basic CRUD (smoke tests beyond conformance)
# ---------------------------------------------------------------------------


class TestBasicCRUD:
    """Quick smoke tests for all record types."""

    def test_decision_roundtrip(self, pg_store):
        decision = _make_decision()
        pg_store.store_decision(decision)
        retrieved = pg_store.get_decision(decision.decision_id)
        assert retrieved.decision_id == decision.decision_id
        assert retrieved.decision == decision.decision

    def test_milestone_roundtrip(self, pg_store):
        ms = _make_milestone()
        pg_store.store_milestone(ms)
        retrieved = pg_store.get_milestone(ms.milestone_id)
        assert retrieved.milestone_id == ms.milestone_id

    def test_hold_roundtrip(self, pg_store):
        hold = _make_hold()
        pg_store.store_hold(hold)
        retrieved = pg_store.get_hold(hold.hold_id)
        assert retrieved.hold_id == hold.hold_id

    def test_delegate_roundtrip(self, pg_store):
        delegate = _make_delegate()
        pg_store.store_delegate(delegate)
        retrieved = pg_store.get_delegate(delegate.delegate_id)
        assert retrieved.delegate_id == delegate.delegate_id

    def test_review_roundtrip(self, pg_store):
        review = _make_review()
        pg_store.store_review(review)
        reviews = pg_store.list_reviews()
        assert len(reviews) == 1
        assert reviews[0].hold_id == review.hold_id

    def test_manifest_roundtrip(self, pg_store):
        manifest = _make_manifest()
        pg_store.store_manifest(manifest)
        retrieved = pg_store.get_manifest()
        assert retrieved.project_id == manifest.project_id

    def test_anchor_roundtrip(self, pg_store):
        data = {"anchor_id": "anc-abc123", "action": "test"}
        pg_store.store_anchor("anc-abc123", data)
        retrieved = pg_store.get_anchor("anc-abc123")
        assert retrieved["anchor_id"] == "anc-abc123"

    def test_wal_roundtrip(self, pg_store):
        wal_data = {"root_delegate_id": "del-abc", "planned_revocations": ["del-abc"]}
        pg_store.store_wal(wal_data)
        retrieved = pg_store.get_wal()
        assert retrieved is not None
        assert retrieved["root_delegate_id"] == "del-abc"


# ---------------------------------------------------------------------------
# 2. Connection pooling
# ---------------------------------------------------------------------------


class TestConnectionPooling:
    """Verify connection pool behavior."""

    def test_pool_is_created_on_initialize(self, pg_store):
        assert pg_store._pool is not None

    def test_pool_is_closed_on_close(self, pg_dsn):
        _clean_tables(pg_dsn)
        store = PostgresTrustPlaneStore(pg_dsn, pool_size=3)
        store.initialize()
        assert store._pool is not None
        store.close()
        assert store._pool is None

    def test_close_is_idempotent(self, pg_store):
        pg_store.close()
        pg_store.close()  # should not raise

    def test_operations_after_close_raise(self, pg_dsn):
        from kailash.trust.plane.exceptions import StoreConnectionError

        _clean_tables(pg_dsn)
        store = PostgresTrustPlaneStore(pg_dsn, pool_size=3)
        store.initialize()
        store.close()
        with pytest.raises(StoreConnectionError, match="not initialized"):
            store.store_decision(_make_decision())

    def test_reinitialize_after_close(self, pg_dsn):
        _clean_tables(pg_dsn)
        store = PostgresTrustPlaneStore(pg_dsn, pool_size=3)
        store.initialize()
        decision = _make_decision()
        store.store_decision(decision)
        store.close()

        # Re-initialize and verify data persists
        store.initialize()
        retrieved = store.get_decision(decision.decision_id)
        assert retrieved.decision_id == decision.decision_id
        store.close()
        _clean_tables(pg_dsn)


# ---------------------------------------------------------------------------
# 3. Concurrent writes
# ---------------------------------------------------------------------------


class TestConcurrentWrites:
    """Verify thread-safety via connection pool."""

    def test_concurrent_decision_writes(self, pg_store):
        """Multiple threads writing decisions concurrently must not lose data."""
        errors: list[Exception] = []
        count = 20

        def writer(index: int) -> None:
            try:
                decision = _make_decision(decision=f"Decision-{index}")
                pg_store.store_decision(decision)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrent write errors: {errors}"
        results = pg_store.list_decisions(limit=count + 10)
        assert len(results) == count

    def test_concurrent_mixed_operations(self, pg_store):
        """Mixed reads and writes from multiple threads."""
        errors: list[Exception] = []

        def write_hold(index: int) -> None:
            try:
                hold = _make_hold(hold_id=f"hold-conc{index:010d}")
                pg_store.store_hold(hold)
            except Exception as e:
                errors.append(e)

        def read_holds() -> None:
            try:
                pg_store.list_holds(limit=100)
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(10):
            threads.append(threading.Thread(target=write_hold, args=(i,)))
            threads.append(threading.Thread(target=read_holds))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrent operation errors: {errors}"
        results = pg_store.list_holds(limit=100)
        assert len(results) == 10


# ---------------------------------------------------------------------------
# 4. Schema versioning
# ---------------------------------------------------------------------------


class TestSchemaVersioning:
    """Verify schema version management."""

    def test_fresh_database_gets_current_version(self, pg_dsn):
        _clean_tables(pg_dsn)
        store = PostgresTrustPlaneStore(pg_dsn, pool_size=2)
        store.initialize()

        with store._pool.connection() as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
            assert row is not None
            assert int(row["value"]) == SCHEMA_VERSION

        store.close()
        _clean_tables(pg_dsn)

    def test_reinitialize_is_idempotent(self, pg_dsn):
        _clean_tables(pg_dsn)
        store = PostgresTrustPlaneStore(pg_dsn, pool_size=2)
        store.initialize()
        store.close()

        # Second initialize should not raise
        store2 = PostgresTrustPlaneStore(pg_dsn, pool_size=2)
        store2.initialize()

        with store2._pool.connection() as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
            assert int(row["value"]) == SCHEMA_VERSION

        store2.close()
        _clean_tables(pg_dsn)

    def test_schema_too_new_raises(self, pg_dsn):
        """Database with a higher schema version must raise SchemaTooNewError."""
        from kailash.trust.plane.exceptions import SchemaTooNewError

        _clean_tables(pg_dsn)
        # First, initialize normally
        store = PostgresTrustPlaneStore(pg_dsn, pool_size=2)
        store.initialize()

        # Manually bump the version beyond current
        with store._pool.connection() as conn:
            conn.execute(
                "UPDATE meta SET value = %s WHERE key = 'schema_version'",
                (str(SCHEMA_VERSION + 10),),
            )
            conn.commit()
        store.close()

        # Now re-initialize should raise
        store2 = PostgresTrustPlaneStore(pg_dsn, pool_size=2)
        with pytest.raises(SchemaTooNewError):
            store2.initialize()
        store2.close()
        _clean_tables(pg_dsn)


# ---------------------------------------------------------------------------
# 5. JSONB-specific behavior
# ---------------------------------------------------------------------------


class TestJSONBColumns:
    """Verify that JSONB storage works correctly."""

    def test_anchor_data_returned_as_dict(self, pg_store):
        """JSONB data should be returned as a Python dict, not a string."""
        data = {"anchor_id": "anc-jsonb1", "nested": {"key": "value"}, "count": 42}
        pg_store.store_anchor("anc-jsonb1", data)
        retrieved = pg_store.get_anchor("anc-jsonb1")
        assert isinstance(retrieved, dict)
        assert retrieved["nested"]["key"] == "value"
        assert retrieved["count"] == 42

    def test_wal_data_returned_as_dict(self, pg_store):
        """WAL data should be returned as a Python dict from JSONB."""
        wal = {"root_delegate_id": "del-abc", "items": [1, 2, 3]}
        pg_store.store_wal(wal)
        retrieved = pg_store.get_wal()
        assert isinstance(retrieved, dict)
        assert retrieved["items"] == [1, 2, 3]


# ---------------------------------------------------------------------------
# 6. Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    """Verify ID validation on all methods."""

    def test_path_traversal_decision(self, pg_store):
        decision = _make_decision()
        decision.decision_id = "../../../etc/passwd"
        with pytest.raises(ValueError):
            pg_store.store_decision(decision)

    def test_path_traversal_hold(self, pg_store):
        with pytest.raises(ValueError):
            pg_store.store_hold(_make_hold(hold_id="../../../etc/passwd"))

    def test_path_traversal_delegate(self, pg_store):
        with pytest.raises(ValueError):
            pg_store.store_delegate(_make_delegate(delegate_id="../bad"))

    def test_path_traversal_anchor(self, pg_store):
        with pytest.raises(ValueError):
            pg_store.store_anchor("../bad", {"test": True})

    def test_null_byte_injection(self, pg_store):
        with pytest.raises(ValueError):
            pg_store.store_hold(_make_hold(hold_id="hold-abc\x00injected"))


# ---------------------------------------------------------------------------
# 7. Bounded results
# ---------------------------------------------------------------------------


class TestBoundedResults:
    """Verify limit parameter behavior."""

    def test_negative_limit_returns_empty(self, pg_store):
        pg_store.store_decision(_make_decision())
        result = pg_store.list_decisions(limit=-1)
        assert len(result) == 0

    def test_limit_zero_returns_empty(self, pg_store):
        pg_store.store_decision(_make_decision())
        result = pg_store.list_decisions(limit=0)
        assert len(result) == 0

    def test_limit_bounds_results(self, pg_store):
        for i in range(5):
            pg_store.store_decision(_make_decision(decision=f"D{i}"))
        result = pg_store.list_decisions(limit=3)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# 8. WAL operations
# ---------------------------------------------------------------------------


class TestWALOperations:
    def test_delete_wal_noop_when_absent(self, pg_store):
        pg_store.delete_wal()  # should not raise

    def test_wal_overwrite(self, pg_store):
        pg_store.store_wal({"version": 1})
        pg_store.store_wal({"version": 2})
        retrieved = pg_store.get_wal()
        assert retrieved["version"] == 2

    def test_get_wal_returns_none_when_empty(self, pg_store):
        assert pg_store.get_wal() is None


# ---------------------------------------------------------------------------
# 9. Exception wrapping (_safe_connection)
# ---------------------------------------------------------------------------


class TestExceptionWrapping:
    """Verify that psycopg errors are wrapped in store-specific exceptions."""

    def test_uninitialized_store_raises_store_connection_error(self):
        from kailash.trust.plane.exceptions import StoreConnectionError

        store = PostgresTrustPlaneStore("postgresql://localhost/unused", pool_size=1)
        # Pool is None — should raise StoreConnectionError
        with pytest.raises(StoreConnectionError, match="not initialized"):
            store.store_decision(_make_decision())

    def test_uninitialized_get_raises_store_connection_error(self):
        from kailash.trust.plane.exceptions import StoreConnectionError

        store = PostgresTrustPlaneStore("postgresql://localhost/unused", pool_size=1)
        with pytest.raises(StoreConnectionError, match="not initialized"):
            store.get_decision("dec-abc123")

    def test_bad_dsn_raises_store_connection_error(self):
        from kailash.trust.plane.exceptions import StoreConnectionError

        store = PostgresTrustPlaneStore(
            "postgresql://invalid:9999/nonexistent", pool_size=1
        )
        with pytest.raises((StoreConnectionError, psycopg.OperationalError)):
            store.initialize()

    def test_sanitize_conninfo_strips_password(self):
        store = PostgresTrustPlaneStore(
            "postgresql://user:secret@localhost/db", pool_size=1
        )
        result = store._sanitize_conninfo(
            "connection failed: host=localhost password=mysecretpass port=5432"
        )
        assert "mysecretpass" not in result
        assert "password=***" in result

    def test_sanitize_conninfo_no_password(self):
        store = PostgresTrustPlaneStore("postgresql://localhost/db", pool_size=1)
        result = store._sanitize_conninfo(
            "connection refused: host=localhost port=5432"
        )
        assert result == "connection refused: host=localhost port=5432"

    def test_safe_connection_reraises_store_errors(self, pg_store):
        """StoreConnectionError/StoreQueryError raised inside a _safe_connection
        block are re-raised without double-wrapping."""
        from kailash.trust.plane.exceptions import StoreConnectionError, StoreQueryError

        # Monkey-patch pool.connection to raise our own error
        original = pg_store._pool.connection

        from contextlib import contextmanager

        @contextmanager
        def _raise_store_error():
            raise StoreQueryError("inner query error")
            yield  # noqa: unreachable

        pg_store._pool.connection = _raise_store_error
        try:
            with pytest.raises(StoreQueryError, match="inner query error"):
                pg_store.list_decisions()
        finally:
            pg_store._pool.connection = original
