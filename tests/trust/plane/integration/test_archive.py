# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for store archival/cleanup (TODO-52)."""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from kailash.trust.plane.archive import (
    ArchiveBundle,
    ArchiveError,
    create_archive,
    list_archives,
    restore_archive,
)
from kailash.trust.plane.cli import main
from kailash.trust.plane.holds import HoldRecord
from kailash.trust.plane.models import DecisionRecord, DecisionType, MilestoneRecord
from kailash.trust.plane.store.filesystem import FileSystemTrustPlaneStore
from kailash.trust.plane.store.sqlite import SqliteTrustPlaneStore


def _make_old_decision(days_old: int) -> DecisionRecord:
    """Create a decision record with a timestamp *days_old* days in the past."""
    ts = datetime.now(timezone.utc) - timedelta(days=days_old)
    return DecisionRecord(
        decision_type=DecisionType.SCOPE,
        decision=f"Decision from {days_old} days ago",
        rationale="Historical rationale",
        timestamp=ts,
    )


def _make_old_milestone(days_old: int) -> MilestoneRecord:
    """Create a milestone record with a timestamp *days_old* days in the past."""
    ts = datetime.now(timezone.utc) - timedelta(days=days_old)
    return MilestoneRecord(
        version=f"v0.{days_old}",
        description=f"Milestone from {days_old} days ago",
        timestamp=ts,
    )


def _make_old_hold(days_old: int, status: str = "approved") -> HoldRecord:
    """Create a hold record with a timestamp *days_old* days in the past."""
    ts = datetime.now(timezone.utc) - timedelta(days=days_old)
    return HoldRecord(
        hold_id=f"hold-test{days_old:04d}",
        action="write_file",
        resource="/src/test.py",
        context={},
        reason="Test hold",
        status=status,
        created_at=ts,
    )


def _init_sqlite_store(tmp_path):
    """Create and initialize a SQLite store in tmp_path."""
    db_path = tmp_path / "trust.db"
    store = SqliteTrustPlaneStore(db_path)
    store.initialize()
    return store


def _init_fs_store(tmp_path):
    """Create and initialize a filesystem store in tmp_path."""
    store = FileSystemTrustPlaneStore(tmp_path)
    store.initialize()
    return store


class TestArchiveBundle:
    """Tests for ArchiveBundle dataclass serialization."""

    def test_to_dict_roundtrip(self):
        bundle = ArchiveBundle(
            bundle_id="archive-20250101-120000",
            created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            record_counts={"decisions": 5, "milestones": 2, "holds": 1},
            date_range=("2024-01-01T00:00:00+00:00", "2024-12-31T23:59:59+00:00"),
            sha256_hash="abc123def456",
        )
        d = bundle.to_dict()
        restored = ArchiveBundle.from_dict(d)
        assert restored.bundle_id == bundle.bundle_id
        assert restored.created_at == bundle.created_at
        assert restored.record_counts == bundle.record_counts
        assert restored.date_range == bundle.date_range
        assert restored.sha256_hash == bundle.sha256_hash

    def test_from_dict_missing_field(self):
        with pytest.raises(ValueError, match="missing required field"):
            ArchiveBundle.from_dict({"bundle_id": "test"})

    def test_from_dict_bad_date_range(self):
        with pytest.raises(ValueError, match="date_range"):
            ArchiveBundle.from_dict(
                {
                    "bundle_id": "test",
                    "created_at": "2025-01-01T00:00:00+00:00",
                    "record_counts": {},
                    "date_range": ["only-one"],
                    "sha256_hash": "abc",
                }
            )


class TestCreateArchiveSQLite:
    """Tests for create_archive() with SQLite backend."""

    def test_archive_old_decisions(self, tmp_path):
        store = _init_sqlite_store(tmp_path)
        for days in [400, 500, 600]:
            store.store_decision(_make_old_decision(days))
        store.store_decision(_make_old_decision(10))  # recent

        bundle = create_archive(store, tmp_path, max_age_days=365)

        assert bundle.record_counts["decisions"] == 3
        assert bundle.record_counts["milestones"] == 0
        assert bundle.record_counts["holds"] == 0

        remaining = store.list_decisions()
        assert len(remaining) == 1

        zip_path = tmp_path / "archives" / f"{bundle.bundle_id}.zip"
        assert zip_path.exists()

        store.close()

    def test_archive_milestones(self, tmp_path):
        store = _init_sqlite_store(tmp_path)
        store.store_milestone(_make_old_milestone(400))
        store.store_milestone(_make_old_milestone(10))

        bundle = create_archive(store, tmp_path, max_age_days=365)

        assert bundle.record_counts["milestones"] == 1
        remaining = store.list_milestones()
        assert len(remaining) == 1
        store.close()

    def test_archive_resolved_holds_only(self, tmp_path):
        store = _init_sqlite_store(tmp_path)
        store.store_hold(_make_old_hold(400, status="approved"))
        store.store_hold(_make_old_hold(500, status="denied"))
        store.store_hold(_make_old_hold(600, status="pending"))

        bundle = create_archive(store, tmp_path, max_age_days=365)

        assert bundle.record_counts["holds"] == 2
        remaining = store.list_holds()
        assert len(remaining) == 1
        assert remaining[0].status == "pending"
        store.close()

    def test_archive_no_old_records_raises(self, tmp_path):
        store = _init_sqlite_store(tmp_path)
        store.store_decision(_make_old_decision(10))

        with pytest.raises(ArchiveError, match="No records older than"):
            create_archive(store, tmp_path, max_age_days=365)
        store.close()

    def test_archive_invalid_max_age(self, tmp_path):
        store = _init_sqlite_store(tmp_path)
        with pytest.raises(ArchiveError, match="max_age_days must be at least 1"):
            create_archive(store, tmp_path, max_age_days=0)
        store.close()

    def test_archive_zip_contents(self, tmp_path):
        store = _init_sqlite_store(tmp_path)
        store.store_decision(_make_old_decision(400))
        store.store_milestone(_make_old_milestone(500))

        bundle = create_archive(store, tmp_path, max_age_days=365)

        zip_path = tmp_path / "archives" / f"{bundle.bundle_id}.zip"
        with zipfile.ZipFile(str(zip_path), "r") as zf:
            names = zf.namelist()
            assert "manifest.json" in names
            assert "decisions.json" in names
            assert "milestones.json" in names
            assert "holds.json" in names

            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["bundle_id"] == bundle.bundle_id
            assert manifest["sha256_hash"] == bundle.sha256_hash
            assert manifest["record_counts"]["decisions"] == 1
            assert manifest["record_counts"]["milestones"] == 1

        store.close()


class TestCreateArchiveFilesystem:
    """Tests for create_archive() with filesystem backend."""

    def test_archive_and_delete_fs(self, tmp_path):
        store = _init_fs_store(tmp_path)
        for days in [400, 500]:
            store.store_decision(_make_old_decision(days))
        store.store_decision(_make_old_decision(10))

        bundle = create_archive(store, tmp_path, max_age_days=365)

        assert bundle.record_counts["decisions"] == 2
        remaining = store.list_decisions()
        assert len(remaining) == 1

    def test_roundtrip_fs(self, tmp_path):
        store = _init_fs_store(tmp_path)
        old_dec = _make_old_decision(400)
        store.store_decision(old_dec)

        bundle = create_archive(store, tmp_path, max_age_days=365)
        assert len(store.list_decisions()) == 0

        count = restore_archive(store, tmp_path, bundle.bundle_id)
        assert count == 1

        decisions = store.list_decisions()
        assert len(decisions) == 1
        assert decisions[0].decision_id == old_dec.decision_id


class TestListArchives:
    """Tests for list_archives()."""

    def test_list_empty(self, tmp_path):
        bundles = list_archives(tmp_path)
        assert bundles == []

    def test_list_after_create(self, tmp_path):
        store = _init_sqlite_store(tmp_path)
        store.store_decision(_make_old_decision(400))
        create_archive(store, tmp_path, max_age_days=365)
        store.close()

        bundles = list_archives(tmp_path)
        assert len(bundles) == 1
        assert bundles[0].record_counts["decisions"] == 1


class TestRestoreArchive:
    """Tests for restore_archive()."""

    def test_roundtrip_archive_restore(self, tmp_path):
        """The core roundtrip: archive records, then restore them."""
        store = _init_sqlite_store(tmp_path)

        old_dec = _make_old_decision(400)
        old_ms = _make_old_milestone(500)
        old_hold = _make_old_hold(600, status="approved")
        store.store_decision(old_dec)
        store.store_milestone(old_ms)
        store.store_hold(old_hold)

        bundle = create_archive(store, tmp_path, max_age_days=365)
        assert len(store.list_decisions()) == 0
        assert len(store.list_milestones()) == 0
        assert len(store.list_holds()) == 0

        count = restore_archive(store, tmp_path, bundle.bundle_id)
        assert count == 3

        decisions = store.list_decisions()
        assert len(decisions) == 1
        assert decisions[0].decision_id == old_dec.decision_id

        milestones = store.list_milestones()
        assert len(milestones) == 1
        assert milestones[0].milestone_id == old_ms.milestone_id

        holds = store.list_holds()
        assert len(holds) == 1
        assert holds[0].hold_id == old_hold.hold_id

        zip_path = tmp_path / "archives" / f"{bundle.bundle_id}.zip"
        assert not zip_path.exists()

        store.close()

    def test_restore_nonexistent_bundle(self, tmp_path):
        store = _init_sqlite_store(tmp_path)
        with pytest.raises(ArchiveError, match="not found"):
            restore_archive(store, tmp_path, "archive-99999999-000000")
        store.close()

    def test_restore_invalid_bundle_id(self, tmp_path):
        store = _init_sqlite_store(tmp_path)
        with pytest.raises(ValueError, match="unsafe characters"):
            restore_archive(store, tmp_path, "../evil-path")
        store.close()

    def test_restore_tampered_archive(self, tmp_path):
        """Restoring an archive with modified content should fail integrity check."""
        store = _init_sqlite_store(tmp_path)
        store.store_decision(_make_old_decision(400))
        bundle = create_archive(store, tmp_path, max_age_days=365)

        zip_path = tmp_path / "archives" / f"{bundle.bundle_id}.zip"
        with zipfile.ZipFile(str(zip_path), "r") as zf:
            manifest = zf.read("manifest.json")
            milestones = zf.read("milestones.json")
            holds = zf.read("holds.json")

        import os
        import tempfile

        fd, tmp_zip = tempfile.mkstemp(dir=str(tmp_path / "archives"))
        os.close(fd)
        with zipfile.ZipFile(tmp_zip, "w") as zf:
            zf.writestr("manifest.json", manifest)
            zf.writestr("decisions.json", "[]")
            zf.writestr("milestones.json", milestones)
            zf.writestr("holds.json", holds)
        os.replace(tmp_zip, str(zip_path))

        with pytest.raises(ArchiveError, match="Integrity verification failed"):
            restore_archive(store, tmp_path, bundle.bundle_id)

        store.close()


class TestArchiveCLI:
    """Tests for the CLI archive commands."""

    def _init_project(self, runner, trust_dir):
        result = runner.invoke(
            main,
            ["--dir", trust_dir, "init", "--name", "ArchiveTest", "--author", "Alice"],
        )
        assert result.exit_code == 0

    def test_archive_list_empty(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        self._init_project(runner, trust_dir)

        result = runner.invoke(main, ["--dir", trust_dir, "archive", "list"])
        assert result.exit_code == 0
        assert "No archives found" in result.output

    def test_archive_create_no_old_records(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        self._init_project(runner, trust_dir)

        result = runner.invoke(main, ["--dir", trust_dir, "archive", "create"])
        assert result.exit_code == 1
        assert "No records older than" in result.output

    def test_archive_restore_nonexistent(self, tmp_path):
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        self._init_project(runner, trust_dir)

        result = runner.invoke(
            main, ["--dir", trust_dir, "archive", "restore", "archive-nonexistent"]
        )
        assert result.exit_code == 1
        assert "not found" in result.output
