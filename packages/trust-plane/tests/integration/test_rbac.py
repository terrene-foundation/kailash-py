# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for RBAC (Role-Based Access Control) module.

Tests role assignment, permission checking, persistence, and revocation
for the TrustPlane RBAC system.
"""

from __future__ import annotations

import json

import pytest

from trustplane.rbac import (
    OPERATIONS,
    ROLE_PERMISSIONS,
    RBACManager,
    Role,
    RolePermission,
)


@pytest.fixture
def rbac_dir(tmp_path):
    """Create a temporary directory for RBAC data."""
    d = tmp_path / "trust-plane"
    d.mkdir()
    return d


@pytest.fixture
def rbac_path(rbac_dir):
    """Return the path for rbac.json."""
    return rbac_dir / "rbac.json"


@pytest.fixture
def mgr(rbac_path):
    """Create a fresh RBACManager."""
    return RBACManager(rbac_path)


class TestRole:
    """Test the Role enum."""

    def test_role_values(self):
        assert Role.ADMIN.value == "admin"
        assert Role.AUDITOR.value == "auditor"
        assert Role.DELEGATE.value == "delegate"
        assert Role.OBSERVER.value == "observer"

    def test_role_from_string(self):
        assert Role("admin") is Role.ADMIN
        assert Role("auditor") is Role.AUDITOR
        assert Role("delegate") is Role.DELEGATE
        assert Role("observer") is Role.OBSERVER

    def test_invalid_role_raises(self):
        with pytest.raises(ValueError):
            Role("superuser")

    def test_all_four_roles_exist(self):
        assert len(Role) == 4


class TestRolePermission:
    """Test the RolePermission dataclass."""

    def test_create_permission(self):
        perm = RolePermission(
            role=Role.ADMIN,
            allowed_operations=frozenset(OPERATIONS),
        )
        assert perm.role is Role.ADMIN
        assert len(perm.allowed_operations) == len(OPERATIONS)

    def test_to_dict_roundtrip(self):
        perm = RolePermission(
            role=Role.AUDITOR,
            allowed_operations=frozenset(["verify", "status"]),
        )
        data = perm.to_dict()
        restored = RolePermission.from_dict(data)
        assert restored.role is Role.AUDITOR
        assert restored.allowed_operations == frozenset(["verify", "status"])

    def test_from_dict_missing_role_raises(self):
        with pytest.raises(ValueError, match="role"):
            RolePermission.from_dict({"allowed_operations": ["verify"]})

    def test_from_dict_missing_operations_raises(self):
        with pytest.raises(ValueError, match="allowed_operations"):
            RolePermission.from_dict({"role": "admin"})


class TestDefaultPermissions:
    """Test the default ROLE_PERMISSIONS mapping."""

    def test_admin_has_all_operations(self):
        admin_perm = ROLE_PERMISSIONS[Role.ADMIN]
        for op in OPERATIONS:
            assert (
                op in admin_perm.allowed_operations
            ), f"Admin should have '{op}' permission"

    def test_auditor_read_only(self):
        auditor_perm = ROLE_PERMISSIONS[Role.AUDITOR]
        expected = {"verify", "status", "decisions", "export"}
        assert auditor_perm.allowed_operations == expected

    def test_delegate_can_decide(self):
        delegate_perm = ROLE_PERMISSIONS[Role.DELEGATE]
        expected = {"decide", "milestone", "hold_approve", "hold_deny"}
        assert delegate_perm.allowed_operations == expected

    def test_observer_shadow_only(self):
        observer_perm = ROLE_PERMISSIONS[Role.OBSERVER]
        expected = {"shadow", "status"}
        assert observer_perm.allowed_operations == expected

    def test_auditor_cannot_decide(self):
        auditor_perm = ROLE_PERMISSIONS[Role.AUDITOR]
        assert "decide" not in auditor_perm.allowed_operations

    def test_observer_cannot_export(self):
        observer_perm = ROLE_PERMISSIONS[Role.OBSERVER]
        assert "export" not in observer_perm.allowed_operations

    def test_delegate_cannot_init(self):
        delegate_perm = ROLE_PERMISSIONS[Role.DELEGATE]
        assert "init" not in delegate_perm.allowed_operations

    def test_delegate_cannot_rbac_assign(self):
        delegate_perm = ROLE_PERMISSIONS[Role.DELEGATE]
        assert "rbac_assign" not in delegate_perm.allowed_operations


class TestRBACManagerAssignment:
    """Test role assignment and retrieval."""

    def test_assign_role(self, mgr):
        mgr.assign_role("alice", Role.ADMIN)
        assert mgr.get_role("alice") is Role.ADMIN

    def test_assign_multiple_users(self, mgr):
        mgr.assign_role("alice", Role.ADMIN)
        mgr.assign_role("bob", Role.AUDITOR)
        mgr.assign_role("charlie", Role.DELEGATE)
        assert mgr.get_role("alice") is Role.ADMIN
        assert mgr.get_role("bob") is Role.AUDITOR
        assert mgr.get_role("charlie") is Role.DELEGATE

    def test_reassign_role(self, mgr):
        mgr.assign_role("alice", Role.ADMIN)
        mgr.assign_role("alice", Role.OBSERVER)
        assert mgr.get_role("alice") is Role.OBSERVER

    def test_unknown_user_returns_none(self, mgr):
        assert mgr.get_role("unknown-user") is None

    def test_assign_validates_user_id(self, mgr):
        """User IDs must be safe for file paths (validate_id)."""
        with pytest.raises(ValueError, match="unsafe characters"):
            mgr.assign_role("../etc/passwd", Role.ADMIN)

    def test_assign_validates_user_id_slashes(self, mgr):
        with pytest.raises(ValueError, match="unsafe characters"):
            mgr.assign_role("user/name", Role.ADMIN)

    def test_get_role_validates_user_id(self, mgr):
        with pytest.raises(ValueError, match="unsafe characters"):
            mgr.get_role("../../attack")


class TestRBACManagerRevocation:
    """Test role revocation."""

    def test_revoke_role(self, mgr):
        mgr.assign_role("alice", Role.ADMIN)
        mgr.revoke_role("alice")
        assert mgr.get_role("alice") is None

    def test_revoke_nonexistent_user_raises(self, mgr):
        """Revoking a role for a user that has no role should raise."""
        from trustplane.exceptions import TrustPlaneError

        with pytest.raises(TrustPlaneError, match="no role assigned"):
            mgr.revoke_role("nonexistent")

    def test_revoke_validates_user_id(self, mgr):
        with pytest.raises(ValueError, match="unsafe characters"):
            mgr.revoke_role("../attack")


class TestRBACManagerPermissions:
    """Test permission checking."""

    def test_admin_can_do_anything(self, mgr):
        mgr.assign_role("alice", Role.ADMIN)
        for op in OPERATIONS:
            assert (
                mgr.check_permission("alice", op) is True
            ), f"Admin should have '{op}' permission"

    def test_auditor_can_verify(self, mgr):
        mgr.assign_role("bob", Role.AUDITOR)
        assert mgr.check_permission("bob", "verify") is True

    def test_auditor_cannot_decide(self, mgr):
        mgr.assign_role("bob", Role.AUDITOR)
        assert mgr.check_permission("bob", "decide") is False

    def test_delegate_can_decide(self, mgr):
        mgr.assign_role("charlie", Role.DELEGATE)
        assert mgr.check_permission("charlie", "decide") is True

    def test_delegate_cannot_export(self, mgr):
        mgr.assign_role("charlie", Role.DELEGATE)
        assert mgr.check_permission("charlie", "export") is False

    def test_observer_can_shadow(self, mgr):
        mgr.assign_role("dave", Role.OBSERVER)
        assert mgr.check_permission("dave", "shadow") is True

    def test_observer_cannot_decide(self, mgr):
        mgr.assign_role("dave", Role.OBSERVER)
        assert mgr.check_permission("dave", "decide") is False

    def test_unassigned_user_has_no_permissions(self, mgr):
        """Users without a role should be denied all operations."""
        assert mgr.check_permission("nobody", "verify") is False

    def test_check_permission_validates_user_id(self, mgr):
        with pytest.raises(ValueError, match="unsafe characters"):
            mgr.check_permission("../attack", "verify")

    def test_check_permission_invalid_operation(self, mgr):
        mgr.assign_role("alice", Role.ADMIN)
        assert mgr.check_permission("alice", "nonexistent_op") is False


class TestRBACManagerListing:
    """Test listing role assignments."""

    def test_list_empty(self, mgr):
        assignments = mgr.list_assignments()
        assert assignments == []

    def test_list_assignments(self, mgr):
        mgr.assign_role("alice", Role.ADMIN)
        mgr.assign_role("bob", Role.AUDITOR)
        assignments = mgr.list_assignments()
        assert len(assignments) == 2
        user_ids = {a["user_id"] for a in assignments}
        assert user_ids == {"alice", "bob"}
        roles = {a["role"] for a in assignments}
        assert roles == {"admin", "auditor"}

    def test_list_after_revoke(self, mgr):
        mgr.assign_role("alice", Role.ADMIN)
        mgr.assign_role("bob", Role.AUDITOR)
        mgr.revoke_role("alice")
        assignments = mgr.list_assignments()
        assert len(assignments) == 1
        assert assignments[0]["user_id"] == "bob"


class TestRBACManagerPersistence:
    """Test that RBAC state persists to disk."""

    def test_persist_and_reload(self, rbac_path):
        mgr1 = RBACManager(rbac_path)
        mgr1.assign_role("alice", Role.ADMIN)
        mgr1.assign_role("bob", Role.AUDITOR)

        # Reload from the same path
        mgr2 = RBACManager(rbac_path)
        assert mgr2.get_role("alice") is Role.ADMIN
        assert mgr2.get_role("bob") is Role.AUDITOR

    def test_persist_after_revoke(self, rbac_path):
        mgr1 = RBACManager(rbac_path)
        mgr1.assign_role("alice", Role.ADMIN)
        mgr1.revoke_role("alice")

        mgr2 = RBACManager(rbac_path)
        assert mgr2.get_role("alice") is None

    def test_rbac_json_format(self, rbac_path):
        mgr = RBACManager(rbac_path)
        mgr.assign_role("alice", Role.ADMIN)

        data = json.loads(rbac_path.read_text())
        assert "assignments" in data
        assert isinstance(data["assignments"], dict)
        assert "alice" in data["assignments"]
        assert data["assignments"]["alice"] == "admin"

    def test_creates_parent_directories(self, tmp_path):
        deep_path = tmp_path / "a" / "b" / "c" / "rbac.json"
        mgr = RBACManager(deep_path)
        mgr.assign_role("alice", Role.ADMIN)
        assert deep_path.exists()

    def test_handles_empty_file_gracefully(self, rbac_path):
        """If rbac.json exists but is empty, RBACManager treats it as no data (fresh start)."""
        rbac_path.parent.mkdir(parents=True, exist_ok=True)
        rbac_path.write_text("")
        mgr = RBACManager(rbac_path)
        assert mgr.list_assignments() == []

    def test_handles_corrupt_json(self, rbac_path):
        """If rbac.json contains invalid JSON, RBACManager should raise."""
        rbac_path.parent.mkdir(parents=True, exist_ok=True)
        rbac_path.write_text("{not valid json")
        with pytest.raises(Exception):
            RBACManager(rbac_path)

    def test_cross_process_revocation_detected(self, rbac_path):
        """Revocation by one manager is detected by another via mtime check."""
        mgr1 = RBACManager(rbac_path)
        mgr1.assign_role("alice", Role.ADMIN)

        # Simulate another process loading the same file
        mgr2 = RBACManager(rbac_path)
        assert mgr2.get_role("alice") is Role.ADMIN

        # Process 1 revokes alice
        mgr1.revoke_role("alice")

        # Process 2 should detect the file change and reflect the revocation
        assert mgr2.get_role("alice") is None

    def test_cross_process_assignment_detected(self, rbac_path):
        """New assignment by one manager is detected by another via mtime check."""
        mgr1 = RBACManager(rbac_path)
        mgr2 = RBACManager(rbac_path)

        # Process 1 assigns a role
        mgr1.assign_role("bob", Role.AUDITOR)

        # Process 2 should pick up the change
        assert mgr2.check_permission("bob", "verify") is True
