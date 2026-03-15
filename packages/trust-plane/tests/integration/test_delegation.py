# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for multi-stakeholder delegation (M9-01, M9-02).

Tests delegate management, dimension scoping, cascade revocation,
hold resolution by delegates, and EATP constraint enforcement.
"""

from datetime import datetime, timedelta, timezone

import pytest

from trustplane.delegation import (
    DEFAULT_MAX_DELEGATION_DEPTH,
    VALID_DIMENSIONS,
    Delegate,
    DelegateStatus,
    DelegationManager,
    ReviewResolution,
)
from trustplane.holds import HoldManager, HoldRecord


@pytest.fixture
def trust_dir(tmp_path):
    trust = tmp_path / "trust-plane"
    trust.mkdir()
    return trust


@pytest.fixture
def mgr(trust_dir):
    return DelegationManager(trust_dir)


@pytest.fixture
def hold_mgr(trust_dir):
    return HoldManager(trust_dir)


class TestDelegateModel:
    def test_create_delegate(self):
        d = Delegate(
            delegate_id="del-abc",
            name="Alice",
            dimensions=["operational", "data_access"],
            delegated_by="owner",
        )
        assert d.is_active()
        assert d.can_review("operational")
        assert d.can_review("data_access")
        assert not d.can_review("financial")

    def test_roundtrip(self):
        d = Delegate(
            delegate_id="del-abc",
            name="Alice",
            dimensions=["operational"],
            delegated_by="owner",
        )
        data = d.to_dict()
        restored = Delegate.from_dict(data)
        assert restored.delegate_id == d.delegate_id
        assert restored.name == d.name
        assert restored.dimensions == d.dimensions

    def test_expired_delegate_not_active(self):
        d = Delegate(
            delegate_id="del-abc",
            name="Bob",
            dimensions=["operational"],
            delegated_by="owner",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        assert not d.is_active()
        assert not d.can_review("operational")

    def test_revoked_delegate_not_active(self):
        d = Delegate(
            delegate_id="del-abc",
            name="Charlie",
            dimensions=["operational"],
            delegated_by="owner",
            status=DelegateStatus.REVOKED,
        )
        assert not d.is_active()


class TestDelegationManager:
    def test_add_delegate(self, mgr):
        d = mgr.add_delegate("Alice", ["operational", "data_access"])
        assert d.name == "Alice"
        assert d.delegate_id.startswith("del-")
        assert d.dimensions == ["operational", "data_access"]
        assert d.depth == 0

    def test_add_delegate_invalid_dimension(self, mgr):
        with pytest.raises(ValueError, match="Invalid dimensions"):
            mgr.add_delegate("Alice", ["not_a_dimension"])

    def test_add_delegate_empty_dimensions(self, mgr):
        with pytest.raises(ValueError, match="At least one dimension"):
            mgr.add_delegate("Alice", [])

    def test_get_delegate(self, mgr):
        d = mgr.add_delegate("Alice", ["operational"])
        loaded = mgr.get_delegate(d.delegate_id)
        assert loaded.name == "Alice"

    def test_get_delegate_not_found(self, mgr):
        with pytest.raises(KeyError, match="not found"):
            mgr.get_delegate("del-nonexistent")

    def test_list_delegates(self, mgr):
        mgr.add_delegate("Alice", ["operational"])
        mgr.add_delegate("Bob", ["communication"])
        delegates = mgr.list_delegates()
        assert len(delegates) == 2

    def test_list_active_only(self, mgr):
        d = mgr.add_delegate("Alice", ["operational"])
        mgr.add_delegate("Bob", ["communication"])
        mgr.revoke_delegate(d.delegate_id)
        active = mgr.list_delegates(active_only=True)
        assert len(active) == 1
        assert active[0].name == "Bob"

    def test_find_reviewers(self, mgr):
        mgr.add_delegate("Alice", ["operational", "data_access"])
        mgr.add_delegate("Bob", ["communication"])
        mgr.add_delegate("Charlie", ["operational"])

        op_reviewers = mgr.find_reviewers("operational")
        assert len(op_reviewers) == 2
        names = {r.name for r in op_reviewers}
        assert names == {"Alice", "Charlie"}

        comm_reviewers = mgr.find_reviewers("communication")
        assert len(comm_reviewers) == 1
        assert comm_reviewers[0].name == "Bob"

    def test_find_reviewers_empty(self, mgr):
        mgr.add_delegate("Alice", ["operational"])
        assert mgr.find_reviewers("financial") == []

    def test_delegate_with_expiry(self, mgr):
        future = datetime.now(timezone.utc) + timedelta(hours=24)
        d = mgr.add_delegate("Alice", ["operational"], expires_at=future)
        assert d.expires_at is not None
        assert d.is_active()


class TestSubDelegation:
    def test_sub_delegate(self, mgr):
        parent = mgr.add_delegate("Alice", ["operational", "data_access"])
        child = mgr.add_delegate(
            "Bob",
            ["operational"],
            parent_delegate_id=parent.delegate_id,
        )
        assert child.depth == 1
        assert child.can_review("operational")
        assert not child.can_review("data_access")

    def test_sub_delegate_cannot_expand(self, mgr):
        parent = mgr.add_delegate("Alice", ["operational"])
        with pytest.raises(ValueError, match="not in parent delegate's scope"):
            mgr.add_delegate(
                "Bob",
                ["operational", "data_access"],
                parent_delegate_id=parent.delegate_id,
            )

    def test_sub_delegate_depth_limit(self, mgr):
        """Cannot exceed DEFAULT_MAX_DELEGATION_DEPTH."""
        delegates = []
        d = mgr.add_delegate("Level-0", ["operational"])
        delegates.append(d)

        for i in range(1, DEFAULT_MAX_DELEGATION_DEPTH):
            d = mgr.add_delegate(
                f"Level-{i}",
                ["operational"],
                parent_delegate_id=d.delegate_id,
            )
            delegates.append(d)

        # Next one should fail
        with pytest.raises(ValueError, match="exceeds maximum"):
            mgr.add_delegate(
                f"Level-{DEFAULT_MAX_DELEGATION_DEPTH}",
                ["operational"],
                parent_delegate_id=d.delegate_id,
            )

    def test_sub_delegate_of_inactive_fails(self, mgr):
        parent = mgr.add_delegate("Alice", ["operational"])
        mgr.revoke_delegate(parent.delegate_id)
        with pytest.raises(ValueError, match="not active"):
            mgr.add_delegate(
                "Bob",
                ["operational"],
                parent_delegate_id=parent.delegate_id,
            )

    def test_sub_delegate_of_expired_fails(self, mgr):
        """Cannot sub-delegate from an expired parent."""
        parent = mgr.add_delegate(
            "Alice",
            ["operational", "data_access"],
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        # Parent is expired — is_active() returns False
        assert not mgr.get_delegate(parent.delegate_id).is_active()
        with pytest.raises(ValueError, match="not active"):
            mgr.add_delegate(
                "Bob",
                ["operational"],
                parent_delegate_id=parent.delegate_id,
            )

    def test_configurable_max_depth(self, tmp_path):
        """DelegationManager accepts custom max_depth parameter."""
        dm = DelegationManager(tmp_path, max_depth=3)
        d0 = dm.add_delegate("L0", ["operational"])
        d1 = dm.add_delegate("L1", ["operational"], parent_delegate_id=d0.delegate_id)
        d2 = dm.add_delegate("L2", ["operational"], parent_delegate_id=d1.delegate_id)
        # depth 3 should fail (max_depth=3 means depths 0,1,2 allowed)
        with pytest.raises(ValueError, match="exceeds maximum"):
            dm.add_delegate("L3", ["operational"], parent_delegate_id=d2.delegate_id)


class TestCascadeRevocation:
    def test_revoke_single(self, mgr):
        d = mgr.add_delegate("Alice", ["operational"])
        revoked = mgr.revoke_delegate(d.delegate_id)
        assert d.delegate_id in revoked
        assert not mgr.get_delegate(d.delegate_id).is_active()

    def test_cascade_revoke(self, mgr):
        parent = mgr.add_delegate("Alice", ["operational", "data_access"])
        child1 = mgr.add_delegate(
            "Bob",
            ["operational"],
            parent_delegate_id=parent.delegate_id,
        )
        child2 = mgr.add_delegate(
            "Charlie",
            ["data_access"],
            parent_delegate_id=parent.delegate_id,
        )

        revoked = mgr.revoke_delegate(parent.delegate_id)
        assert len(revoked) == 3
        assert parent.delegate_id in revoked
        assert child1.delegate_id in revoked
        assert child2.delegate_id in revoked

        # All should be revoked
        assert not mgr.get_delegate(parent.delegate_id).is_active()
        assert not mgr.get_delegate(child1.delegate_id).is_active()
        assert not mgr.get_delegate(child2.delegate_id).is_active()

    def test_cascade_revoke_multi_level(self, mgr):
        root = mgr.add_delegate("Root", ["operational"])
        mid = mgr.add_delegate(
            "Mid",
            ["operational"],
            parent_delegate_id=root.delegate_id,
        )
        leaf = mgr.add_delegate(
            "Leaf",
            ["operational"],
            parent_delegate_id=mid.delegate_id,
        )

        revoked = mgr.revoke_delegate(root.delegate_id)
        assert len(revoked) == 3

    def test_revoke_already_revoked(self, mgr):
        d = mgr.add_delegate("Alice", ["operational"])
        mgr.revoke_delegate(d.delegate_id)
        # Second revoke should be idempotent
        revoked = mgr.revoke_delegate(d.delegate_id)
        assert len(revoked) == 0

    def test_revoke_child_preserves_parent(self, mgr):
        parent = mgr.add_delegate("Alice", ["operational", "data_access"])
        child = mgr.add_delegate(
            "Bob",
            ["operational"],
            parent_delegate_id=parent.delegate_id,
        )
        mgr.revoke_delegate(child.delegate_id)

        assert mgr.get_delegate(parent.delegate_id).is_active()
        assert not mgr.get_delegate(child.delegate_id).is_active()


class TestHoldResolution:
    def test_delegate_resolves_hold(self, mgr, hold_mgr):
        delegate = mgr.add_delegate("Alice", ["operational"])
        hold = hold_mgr.create_hold(
            action="merge_to_main",
            resource="src/main.py",
            reason="Blocked by constraint",
        )

        resolution = mgr.resolve_hold(
            hold=hold,
            delegate_id=delegate.delegate_id,
            approved=True,
            reason="Reviewed, within scope",
            dimension="operational",
        )
        assert resolution.approved is True
        assert resolution.delegate_id == delegate.delegate_id
        assert resolution.hold_id == hold.hold_id

    def test_delegate_denies_hold(self, mgr, hold_mgr):
        delegate = mgr.add_delegate("Alice", ["operational"])
        hold = hold_mgr.create_hold(
            action="delete_all",
            resource="/",
            reason="Blocked",
        )

        resolution = mgr.resolve_hold(
            hold=hold,
            delegate_id=delegate.delegate_id,
            approved=False,
            reason="Too dangerous",
            dimension="operational",
        )
        assert resolution.approved is False

    def test_delegate_cannot_resolve_outside_scope(self, mgr, hold_mgr):
        delegate = mgr.add_delegate("Alice", ["operational"])
        hold = hold_mgr.create_hold(
            action="send_email",
            resource="external",
            reason="Blocked by communication constraint",
        )

        with pytest.raises(ValueError, match="cannot review dimension"):
            mgr.resolve_hold(
                hold=hold,
                delegate_id=delegate.delegate_id,
                approved=True,
                reason="Approved",
                dimension="communication",
            )

    def test_revoked_delegate_cannot_resolve(self, mgr, hold_mgr):
        delegate = mgr.add_delegate("Alice", ["operational"])
        hold = hold_mgr.create_hold(action="test", resource="test", reason="test")
        mgr.revoke_delegate(delegate.delegate_id)

        with pytest.raises(ValueError, match="not active"):
            mgr.resolve_hold(
                hold=hold,
                delegate_id=delegate.delegate_id,
                approved=True,
                reason="Approved",
                dimension="operational",
            )

    def test_get_reviews(self, mgr, hold_mgr):
        delegate = mgr.add_delegate("Alice", ["operational", "data_access"])
        hold1 = hold_mgr.create_hold("action1", "res1", "reason1")
        hold2 = hold_mgr.create_hold("action2", "res2", "reason2")

        mgr.resolve_hold(hold1, delegate.delegate_id, True, "ok", "operational")
        mgr.resolve_hold(hold2, delegate.delegate_id, False, "no", "data_access")

        all_reviews = mgr.get_reviews()
        assert len(all_reviews) == 2

        filtered = mgr.get_reviews(hold_id=hold1.hold_id)
        assert len(filtered) == 1
        assert filtered[0].approved is True


class TestAuditCallback:
    """Tests for the audit callback pattern during delegation revocation."""

    def test_callback_invoked_on_revocation(self, trust_dir):
        calls = []
        mgr = DelegationManager(
            trust_dir, audit_callback=lambda a, r, c: calls.append((a, r, c))
        )
        d = mgr.add_delegate("Alice", ["operational"])
        mgr.revoke_delegate(d.delegate_id)

        assert len(calls) == 1
        action, resource, context = calls[0]
        assert action == "revoke_delegate"
        assert resource == f"delegate/{d.delegate_id}"
        assert context["delegate_name"] == "Alice"
        assert context["cascade"] is False

    def test_callback_cascade_invocations(self, trust_dir):
        calls = []
        mgr = DelegationManager(
            trust_dir, audit_callback=lambda a, r, c: calls.append((a, r, c))
        )
        parent = mgr.add_delegate("Alice", ["operational", "data_access"])
        mgr.add_delegate(
            "Bob",
            ["operational"],
            parent_delegate_id=parent.delegate_id,
        )
        mgr.add_delegate(
            "Carol",
            ["data_access"],
            parent_delegate_id=parent.delegate_id,
        )
        mgr.revoke_delegate(parent.delegate_id)

        assert len(calls) == 3
        # First call is the root — cascade should be False
        assert calls[0][2]["cascade"] is False
        assert calls[0][2]["delegate_name"] == "Alice"
        # Subsequent calls are cascaded — cascade should be True
        cascaded_names = {calls[1][2]["delegate_name"], calls[2][2]["delegate_name"]}
        assert cascaded_names == {"Bob", "Carol"}
        assert calls[1][2]["cascade"] is True
        assert calls[2][2]["cascade"] is True

    def test_no_callback_revocation_still_works(self, trust_dir):
        mgr = DelegationManager(trust_dir)  # No callback
        d = mgr.add_delegate("Alice", ["operational"])
        revoked = mgr.revoke_delegate(d.delegate_id)
        assert d.delegate_id in revoked
        assert not mgr.get_delegate(d.delegate_id).is_active()

    def test_callback_exception_does_not_abort_cascade(self, trust_dir):
        def failing_callback(_action, _resource, _context):
            raise RuntimeError("Audit infrastructure down")

        mgr = DelegationManager(trust_dir, audit_callback=failing_callback)
        parent = mgr.add_delegate("Alice", ["operational"])
        child = mgr.add_delegate(
            "Bob",
            ["operational"],
            parent_delegate_id=parent.delegate_id,
        )
        # Should not raise — callback failure is caught and logged
        revoked = mgr.revoke_delegate(parent.delegate_id)
        assert len(revoked) == 2
        assert not mgr.get_delegate(parent.delegate_id).is_active()
        assert not mgr.get_delegate(child.delegate_id).is_active()


class TestDelegationPersistence:
    def test_delegates_survive_reload(self, trust_dir):
        mgr1 = DelegationManager(trust_dir)
        d = mgr1.add_delegate("Alice", ["operational"])

        mgr2 = DelegationManager(trust_dir)
        loaded = mgr2.get_delegate(d.delegate_id)
        assert loaded.name == "Alice"
        assert loaded.dimensions == ["operational"]

    def test_revocation_survives_reload(self, trust_dir):
        mgr1 = DelegationManager(trust_dir)
        d = mgr1.add_delegate("Alice", ["operational"])
        mgr1.revoke_delegate(d.delegate_id)

        mgr2 = DelegationManager(trust_dir)
        loaded = mgr2.get_delegate(d.delegate_id)
        assert not loaded.is_active()
        assert loaded.status == DelegateStatus.REVOKED
