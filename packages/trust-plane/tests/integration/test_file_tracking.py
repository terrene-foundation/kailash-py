# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for file change tracking during sessions."""

import json

import pytest

from trustplane.project import TrustProject
from trustplane.session import AuditSession, _snapshot_files, compute_diff


@pytest.fixture
def trust_dir(tmp_path):
    return tmp_path / "trust-plane"


@pytest.fixture
def tracked_dir(tmp_path):
    """A directory with some files to track."""
    d = tmp_path / "docs"
    d.mkdir()
    (d / "readme.md").write_text("# Hello")
    (d / "guide.md").write_text("# Guide")
    return d


class TestSnapshotAndDiff:
    def test_snapshot_captures_files(self, tracked_dir):
        snap = _snapshot_files([tracked_dir])
        assert len(snap) == 2
        assert any("readme.md" in k for k in snap)

    def test_snapshot_deterministic(self, tracked_dir):
        snap1 = _snapshot_files([tracked_dir])
        snap2 = _snapshot_files([tracked_dir])
        assert snap1 == snap2

    def test_diff_detects_added(self, tracked_dir):
        start = _snapshot_files([tracked_dir])
        (tracked_dir / "new.md").write_text("new file")
        end = _snapshot_files([tracked_dir])
        diff = compute_diff(start, end)
        assert len(diff["added"]) == 1
        assert any("new.md" in f for f in diff["added"])
        assert diff["modified"] == []
        assert diff["deleted"] == []

    def test_diff_detects_modified(self, tracked_dir):
        start = _snapshot_files([tracked_dir])
        (tracked_dir / "readme.md").write_text("# Changed")
        end = _snapshot_files([tracked_dir])
        diff = compute_diff(start, end)
        assert len(diff["modified"]) == 1
        assert diff["added"] == []

    def test_diff_detects_deleted(self, tracked_dir):
        start = _snapshot_files([tracked_dir])
        (tracked_dir / "guide.md").unlink()
        end = _snapshot_files([tracked_dir])
        diff = compute_diff(start, end)
        assert len(diff["deleted"]) == 1
        assert diff["added"] == []

    def test_diff_no_changes(self, tracked_dir):
        start = _snapshot_files([tracked_dir])
        end = _snapshot_files([tracked_dir])
        diff = compute_diff(start, end)
        assert diff == {"added": [], "modified": [], "deleted": []}

    def test_snapshot_nonexistent_dir(self, tmp_path):
        snap = _snapshot_files([tmp_path / "nonexistent"])
        assert snap == {}


class TestSessionFileTracking:
    def test_session_captures_snapshot_on_init(self, tracked_dir):
        session = AuditSession(tracked_paths=[tracked_dir])
        assert len(session._start_snapshot) == 2

    def test_session_computes_diff_on_end(self, tracked_dir):
        session = AuditSession(tracked_paths=[tracked_dir])
        (tracked_dir / "new.md").write_text("added during session")
        session.end()
        assert session.files_changed is not None
        assert len(session.files_changed["added"]) == 1

    def test_session_summary_includes_files(self, tracked_dir):
        session = AuditSession(tracked_paths=[tracked_dir])
        (tracked_dir / "readme.md").write_text("# Modified")
        session.end()
        summary = session.summary()
        assert "files_changed" in summary
        assert len(summary["files_changed"]["modified"]) == 1

    def test_session_without_tracking_no_files(self):
        session = AuditSession()
        session.end()
        summary = session.summary()
        assert "files_changed" not in summary

    def test_session_roundtrip_preserves_snapshot(self, tracked_dir):
        session = AuditSession(tracked_paths=[tracked_dir])
        data = session.to_dict()
        restored = AuditSession.from_dict(data)
        assert len(restored._start_snapshot) == 2
        assert restored._tracked_paths == [tracked_dir]


class TestProjectFileTracking:
    async def test_session_with_tracked_paths(self, trust_dir, tracked_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Track Test",
            author="Alice",
        )
        session = await project.start_session(tracked_paths=[tracked_dir])
        assert len(session._start_snapshot) == 2

        (tracked_dir / "new.md").write_text("new content")
        summary = await project.end_session()
        assert "files_changed" in summary
        assert len(summary["files_changed"]["added"]) == 1

    async def test_file_changes_in_anchor(self, trust_dir, tracked_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Anchor Track Test",
            author="Bob",
        )
        await project.start_session(tracked_paths=[tracked_dir])
        (tracked_dir / "readme.md").write_text("# Modified")
        await project.end_session()

        # session_complete anchor should include files_changed
        anchor_files = sorted((trust_dir / "anchors").glob("*.json"))
        with open(anchor_files[-1]) as f:
            anchor = json.load(f)
        assert anchor["action"] == "session_complete"
        assert "files_changed" in anchor["context"]
