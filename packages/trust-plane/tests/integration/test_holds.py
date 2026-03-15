# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for Hold/Approve workflow."""

import pytest

from trustplane.holds import HoldManager, HoldRecord


@pytest.fixture
def holds_dir(tmp_path):
    return tmp_path / "trust-plane"


@pytest.fixture
def manager(holds_dir):
    return HoldManager(holds_dir)


class TestHoldRecord:
    def test_create(self):
        hold = HoldRecord(
            hold_id="hold-abc123",
            action="publish_paper",
            resource="docs/paper.md",
            context={"decision_type": "scope"},
            reason="Requires human review before publishing",
        )
        assert hold.status == "pending"
        assert hold.resolved_at is None

    def test_roundtrip(self):
        hold = HoldRecord(
            hold_id="hold-def456",
            action="delete_file",
            resource="keys/private.pem",
            context={},
            reason="Blocked by data access constraints",
        )
        data = hold.to_dict()
        restored = HoldRecord.from_dict(data)
        assert restored.hold_id == "hold-def456"
        assert restored.status == "pending"
        assert restored.action == "delete_file"


class TestHoldManager:
    def test_create_hold(self, manager):
        hold = manager.create_hold(
            action="publish_paper",
            resource="docs/paper.md",
            reason="Requires review",
        )
        assert hold.hold_id.startswith("hold-")
        assert hold.status == "pending"

    def test_get_hold(self, manager):
        hold = manager.create_hold(action="test", resource="test.md", reason="testing")
        retrieved = manager.get(hold.hold_id)
        assert retrieved.action == "test"
        assert retrieved.status == "pending"

    def test_get_nonexistent_raises(self, manager):
        with pytest.raises(KeyError, match="not found"):
            manager.get("hold-nonexistent")

    def test_approve_hold(self, manager):
        hold = manager.create_hold(
            action="publish", resource="paper.md", reason="review needed"
        )
        resolved = manager.resolve(
            hold.hold_id,
            approved=True,
            resolved_by="Alice",
            reason="Reviewed and approved",
        )
        assert resolved.status == "approved"
        assert resolved.resolved_by == "Alice"
        assert resolved.resolved_at is not None

    def test_deny_hold(self, manager):
        hold = manager.create_hold(
            action="delete", resource="keys/", reason="dangerous"
        )
        resolved = manager.resolve(
            hold.hold_id,
            approved=False,
            resolved_by="Bob",
            reason="Not appropriate",
        )
        assert resolved.status == "denied"

    def test_double_resolve_raises(self, manager):
        hold = manager.create_hold(action="test", resource="test.md", reason="testing")
        manager.resolve(hold.hold_id, True, "Alice", "ok")
        with pytest.raises(ValueError, match="already approved"):
            manager.resolve(hold.hold_id, True, "Bob", "again")

    def test_list_pending(self, manager):
        h1 = manager.create_hold(action="a1", resource="r1", reason="r")
        h2 = manager.create_hold(action="a2", resource="r2", reason="r")
        manager.resolve(h1.hold_id, True, "Alice", "ok")

        pending = manager.list_pending()
        assert len(pending) == 1
        assert pending[0].hold_id == h2.hold_id

    def test_list_all(self, manager):
        manager.create_hold(action="a1", resource="r1", reason="r")
        h2 = manager.create_hold(action="a2", resource="r2", reason="r")
        manager.resolve(h2.hold_id, False, "Bob", "no")

        all_holds = manager.list_all()
        assert len(all_holds) == 2

    def test_resolved_hold_persists(self, manager, holds_dir):
        hold = manager.create_hold(action="test", resource="test.md", reason="testing")
        manager.resolve(hold.hold_id, True, "Carol", "approved")

        # New manager loads from disk
        manager2 = HoldManager(holds_dir)
        retrieved = manager2.get(hold.hold_id)
        assert retrieved.status == "approved"
        assert retrieved.resolved_by == "Carol"
