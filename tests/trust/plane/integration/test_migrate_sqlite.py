# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for filesystem-to-SQLite store migration.

Validates:
- Happy path: all record types migrate correctly
- Dry run: no database created, counts reported
- Idempotent: second run does not duplicate records
- Manifest metadata updated after migration
- confirm_delete removes filesystem data
- Already-sqlite projects are detected
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from kailash.trust._locking import safe_read_json
from kailash.trust.plane.delegation import DelegationRecipient, DelegateStatus, ReviewResolution
from kailash.trust.plane.holds import HoldRecord
from kailash.trust.plane.migrate import migrate_to_sqlite
from kailash.trust.plane.models import (
    DecisionRecord,
    DecisionType,
    MilestoneRecord,
    ProjectManifest,
)
from kailash.trust.plane.store.filesystem import FileSystemTrustPlaneStore
from kailash.trust.plane.store.sqlite import SqliteTrustPlaneStore


# ---------------------------------------------------------------------------
# Helpers
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


def _seed_filesystem_store(trust_dir: Path) -> dict[str, int]:
    """Populate a filesystem store with test records. Returns expected counts."""
    store = FileSystemTrustPlaneStore(trust_dir)
    store.initialize()

    # Decisions
    d1 = _make_decision(decision="First decision")
    d2 = _make_decision(decision="Second decision")
    store.store_decision(d1)
    store.store_decision(d2)

    # Milestones
    m1 = _make_milestone(version="v0.1")
    store.store_milestone(m1)

    # Holds
    h1 = _make_hold(hold_id="hold-aaa111222333")
    store.store_hold(h1)

    # Delegates
    del1 = _make_delegate(delegate_id="del-aaa111222333")
    store.store_delegate(del1)

    # Reviews
    r1 = _make_review(
        hold_id="hold-aaa111222333",
        delegate_id="del-aaa111222333",
    )
    store.store_review(r1)

    # Anchors
    store.store_anchor(
        "anc-aaa111222333", {"anchor_id": "anc-aaa111222333", "action": "test"}
    )

    # WAL
    store.store_wal({"root_delegate_id": "del-aaa111222333", "reason": "test"})

    # Manifest
    manifest = _make_manifest()
    store.store_manifest(manifest)

    # Also write manifest.json at trust_dir root (required by migrate_to_sqlite)
    from kailash.trust._locking import atomic_write

    atomic_write(trust_dir / "manifest.json", manifest.to_dict())

    store.close()

    return {
        "decisions": 2,
        "milestones": 1,
        "holds": 1,
        "delegates": 1,
        "reviews": 1,
        "anchors": 1,
        "manifest": 1,
        "wal": 1,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def trust_dir(tmp_path):
    """Create a temporary trust directory."""
    d = tmp_path / "trust-plane"
    d.mkdir()
    return d


@pytest.fixture
def seeded_trust_dir(trust_dir):
    """A trust directory pre-populated with filesystem records."""
    _seed_filesystem_store(trust_dir)
    return trust_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMigrateToSqliteHappyPath:
    """Happy path: all record types migrate correctly."""

    def test_all_records_migrated(self, seeded_trust_dir):
        result = migrate_to_sqlite(seeded_trust_dir)

        assert result["status"] == "migrated"
        assert result["counts"]["decisions"] == 2
        assert result["counts"]["milestones"] == 1
        assert result["counts"]["holds"] == 1
        assert result["counts"]["delegates"] == 1
        assert result["counts"]["reviews"] == 1
        assert result["counts"]["anchors"] == 1
        assert result["counts"]["manifest"] == 1
        assert result["counts"]["wal"] == 1

    def test_sqlite_db_created(self, seeded_trust_dir):
        migrate_to_sqlite(seeded_trust_dir)
        assert (seeded_trust_dir / "trust.db").exists()

    def test_records_readable_from_sqlite(self, seeded_trust_dir):
        migrate_to_sqlite(seeded_trust_dir)

        sqlite_store = SqliteTrustPlaneStore(seeded_trust_dir / "trust.db")
        sqlite_store.initialize()

        assert len(sqlite_store.list_decisions()) == 2
        assert len(sqlite_store.list_milestones()) == 1
        assert len(sqlite_store.list_holds()) == 1
        assert len(sqlite_store.list_delegates(active_only=False)) == 1
        assert len(sqlite_store.list_reviews()) == 1
        assert len(sqlite_store.list_anchors()) == 1

        manifest = sqlite_store.get_manifest()
        assert manifest.project_id == "proj-abc123"

        wal = sqlite_store.get_wal()
        assert wal is not None
        assert wal["root_delegate_id"] == "del-aaa111222333"

        sqlite_store.close()

    def test_decision_content_preserved(self, seeded_trust_dir):
        migrate_to_sqlite(seeded_trust_dir)

        sqlite_store = SqliteTrustPlaneStore(seeded_trust_dir / "trust.db")
        sqlite_store.initialize()

        decisions = sqlite_store.list_decisions()
        decision_texts = {d.decision for d in decisions}
        assert "First decision" in decision_texts
        assert "Second decision" in decision_texts

        sqlite_store.close()


class TestMigrateToSqliteDryRun:
    """Dry run: no database created, correct counts reported."""

    def test_dry_run_no_db_created(self, seeded_trust_dir):
        result = migrate_to_sqlite(seeded_trust_dir, dry_run=True)

        assert result["status"] == "dry_run"
        assert not (seeded_trust_dir / "trust.db").exists()

    def test_dry_run_reports_counts(self, seeded_trust_dir):
        result = migrate_to_sqlite(seeded_trust_dir, dry_run=True)

        assert result["counts"]["decisions"] == 2
        assert result["counts"]["milestones"] == 1
        assert result["counts"]["holds"] == 1
        assert result["counts"]["delegates"] == 1
        assert result["counts"]["reviews"] == 1
        assert result["counts"]["anchors"] == 1
        assert result["counts"]["manifest"] == 1
        assert result["counts"]["wal"] == 1

    def test_dry_run_manifest_unchanged(self, seeded_trust_dir):
        manifest_before = safe_read_json(seeded_trust_dir / "manifest.json")
        migrate_to_sqlite(seeded_trust_dir, dry_run=True)
        manifest_after = safe_read_json(seeded_trust_dir / "manifest.json")
        assert manifest_before == manifest_after


class TestMigrateToSqliteIdempotent:
    """Second run does not duplicate records."""

    def test_second_run_detected(self, seeded_trust_dir):
        first = migrate_to_sqlite(seeded_trust_dir)
        assert first["status"] == "migrated"

        second = migrate_to_sqlite(seeded_trust_dir)
        assert second["status"] == "already_sqlite"

    def test_records_not_duplicated(self, seeded_trust_dir):
        migrate_to_sqlite(seeded_trust_dir)

        sqlite_store = SqliteTrustPlaneStore(seeded_trust_dir / "trust.db")
        sqlite_store.initialize()
        decisions_after_first = len(sqlite_store.list_decisions())
        sqlite_store.close()

        # Second call returns already_sqlite, so no writes happen
        migrate_to_sqlite(seeded_trust_dir)

        sqlite_store = SqliteTrustPlaneStore(seeded_trust_dir / "trust.db")
        sqlite_store.initialize()
        decisions_after_second = len(sqlite_store.list_decisions())
        sqlite_store.close()

        assert decisions_after_first == decisions_after_second


class TestMigrateToSqliteManifest:
    """Manifest metadata is updated after successful migration."""

    def test_manifest_store_field_set(self, seeded_trust_dir):
        migrate_to_sqlite(seeded_trust_dir)

        manifest_data = safe_read_json(seeded_trust_dir / "manifest.json")
        assert manifest_data["metadata"]["store"] == "sqlite"

    def test_manifest_not_updated_on_dry_run(self, seeded_trust_dir):
        migrate_to_sqlite(seeded_trust_dir, dry_run=True)

        manifest_data = safe_read_json(seeded_trust_dir / "manifest.json")
        assert manifest_data.get("metadata", {}).get("store") is None


class TestMigrateToSqliteConfirmDelete:
    """confirm_delete removes filesystem data after migration."""

    def test_confirm_delete_removes_subdirs(self, seeded_trust_dir):
        migrate_to_sqlite(seeded_trust_dir, confirm_delete=True)

        for subdir in (
            "decisions",
            "milestones",
            "holds",
            "delegates",
            "reviews",
            "anchors",
        ):
            assert not (seeded_trust_dir / subdir).exists(), (
                f"{subdir}/ should be deleted after confirm_delete"
            )

    def test_confirm_delete_preserves_db(self, seeded_trust_dir):
        migrate_to_sqlite(seeded_trust_dir, confirm_delete=True)
        assert (seeded_trust_dir / "trust.db").exists()

    def test_confirm_delete_preserves_manifest(self, seeded_trust_dir):
        migrate_to_sqlite(seeded_trust_dir, confirm_delete=True)
        assert (seeded_trust_dir / "manifest.json").exists()

    def test_data_accessible_after_delete(self, seeded_trust_dir):
        migrate_to_sqlite(seeded_trust_dir, confirm_delete=True)

        sqlite_store = SqliteTrustPlaneStore(seeded_trust_dir / "trust.db")
        sqlite_store.initialize()
        assert len(sqlite_store.list_decisions()) == 2
        sqlite_store.close()


class TestMigrateToSqliteEdgeCases:
    """Edge cases and error handling."""

    def test_nonexistent_project_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            migrate_to_sqlite(tmp_path / "nonexistent")

    def test_empty_project_migrates(self, trust_dir):
        """A project with manifest but no records migrates cleanly."""
        store = FileSystemTrustPlaneStore(trust_dir)
        store.initialize()

        manifest = _make_manifest()
        store.store_manifest(manifest)

        from kailash.trust._locking import atomic_write

        atomic_write(trust_dir / "manifest.json", manifest.to_dict())
        store.close()

        result = migrate_to_sqlite(trust_dir)
        assert result["status"] == "migrated"
        assert result["counts"]["decisions"] == 0
        assert result["counts"]["milestones"] == 0

    def test_no_wal_migrates(self, trust_dir):
        """Project without WAL data migrates without error."""
        store = FileSystemTrustPlaneStore(trust_dir)
        store.initialize()

        d1 = _make_decision()
        store.store_decision(d1)

        manifest = _make_manifest()
        store.store_manifest(manifest)

        from kailash.trust._locking import atomic_write

        atomic_write(trust_dir / "manifest.json", manifest.to_dict())
        store.close()

        result = migrate_to_sqlite(trust_dir)
        assert result["status"] == "migrated"
        assert result["counts"]["wal"] == 0
