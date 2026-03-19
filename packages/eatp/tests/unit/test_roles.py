# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for EATP TrustRole enum and role-based access control (Phase 6, VA4).

Covers:
    1. TrustRole enum values and membership
    2. ROLE_PERMISSIONS mapping completeness
    3. ADMIN role: all operations permitted
    4. OPERATOR role: delegate, verify, read permitted; establish, audit denied
    5. OBSERVER role: read permitted; establish, delegate, verify, audit denied
    6. AUDITOR role: audit, read permitted; establish, delegate, verify denied
    7. check_permission function for each role
    8. require_permission function raises PermissionError on denial
    9. require_permission function succeeds on allowed operations
    10. None role = all-access (backward compatibility)
    11. Role escalation prevention: no role has more permissions than ADMIN
    12. Invalid role values are rejected by the enum
    13. TrustRole is str enum (for serialization)
    14. check_permission with unknown operation returns False for non-None roles
"""

from __future__ import annotations

import pytest

from eatp.roles import (
    ROLE_PERMISSIONS,
    TrustRole,
    check_permission,
    require_permission,
)


# ---------------------------------------------------------------------------
# 1. TrustRole enum basics
# ---------------------------------------------------------------------------


class TestTrustRoleEnum:
    """TrustRole enum must have exactly four values as str members."""

    def test_has_admin(self):
        assert TrustRole.ADMIN.value == "admin"

    def test_has_operator(self):
        assert TrustRole.OPERATOR.value == "operator"

    def test_has_observer(self):
        assert TrustRole.OBSERVER.value == "observer"

    def test_has_auditor(self):
        assert TrustRole.AUDITOR.value == "auditor"

    def test_exactly_four_members(self):
        assert len(TrustRole) == 4

    def test_is_str_enum(self):
        """TrustRole must be a str enum for JSON serialization."""
        for role in TrustRole:
            assert isinstance(role, str)
            assert role == role.value

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            TrustRole("nonexistent_role")


# ---------------------------------------------------------------------------
# 2. ROLE_PERMISSIONS mapping
# ---------------------------------------------------------------------------


class TestRolePermissions:
    """ROLE_PERMISSIONS must map every TrustRole to a set of operations."""

    def test_all_roles_have_permissions(self):
        """Every TrustRole must have an entry in ROLE_PERMISSIONS."""
        for role in TrustRole:
            assert role in ROLE_PERMISSIONS, f"Missing permissions for {role.value}"

    def test_no_extra_roles_in_permissions(self):
        """ROLE_PERMISSIONS must not contain keys that are not TrustRole members."""
        for key in ROLE_PERMISSIONS:
            assert isinstance(key, TrustRole), f"Unexpected key {key!r} in ROLE_PERMISSIONS"

    def test_admin_has_all_operations(self):
        admin_perms = ROLE_PERMISSIONS[TrustRole.ADMIN]
        expected = {"establish", "delegate", "verify", "audit", "read"}
        assert admin_perms == expected

    def test_operator_permissions(self):
        operator_perms = ROLE_PERMISSIONS[TrustRole.OPERATOR]
        assert "delegate" in operator_perms
        assert "verify" in operator_perms
        assert "read" in operator_perms
        assert "establish" not in operator_perms
        assert "audit" not in operator_perms

    def test_observer_permissions(self):
        observer_perms = ROLE_PERMISSIONS[TrustRole.OBSERVER]
        assert observer_perms == {"read"}

    def test_auditor_permissions(self):
        auditor_perms = ROLE_PERMISSIONS[TrustRole.AUDITOR]
        assert "audit" in auditor_perms
        assert "read" in auditor_perms
        assert "establish" not in auditor_perms
        assert "delegate" not in auditor_perms
        assert "verify" not in auditor_perms

    def test_permissions_are_frozensets_or_sets(self):
        """All permission values must be sets (or frozensets) of strings."""
        for role, perms in ROLE_PERMISSIONS.items():
            assert isinstance(perms, (set, frozenset)), f"Permissions for {role.value} must be a set, got {type(perms)}"
            for perm in perms:
                assert isinstance(perm, str), f"Permission {perm!r} for {role.value} must be a string"


# ---------------------------------------------------------------------------
# 3. check_permission function
# ---------------------------------------------------------------------------


class TestCheckPermission:
    """check_permission must validate role against operation."""

    # --- ADMIN: all operations permitted ---
    @pytest.mark.parametrize("operation", ["establish", "delegate", "verify", "audit", "read"])
    def test_admin_allowed_all(self, operation: str):
        assert check_permission(TrustRole.ADMIN, operation) is True

    # --- OPERATOR: delegate, verify, read permitted ---
    @pytest.mark.parametrize("operation", ["delegate", "verify", "read"])
    def test_operator_allowed(self, operation: str):
        assert check_permission(TrustRole.OPERATOR, operation) is True

    @pytest.mark.parametrize("operation", ["establish", "audit"])
    def test_operator_denied(self, operation: str):
        assert check_permission(TrustRole.OPERATOR, operation) is False

    # --- OBSERVER: read only ---
    def test_observer_allowed_read(self):
        assert check_permission(TrustRole.OBSERVER, "read") is True

    @pytest.mark.parametrize("operation", ["establish", "delegate", "verify", "audit"])
    def test_observer_denied(self, operation: str):
        assert check_permission(TrustRole.OBSERVER, operation) is False

    # --- AUDITOR: audit + read ---
    @pytest.mark.parametrize("operation", ["audit", "read"])
    def test_auditor_allowed(self, operation: str):
        assert check_permission(TrustRole.AUDITOR, operation) is True

    @pytest.mark.parametrize("operation", ["establish", "delegate", "verify"])
    def test_auditor_denied(self, operation: str):
        assert check_permission(TrustRole.AUDITOR, operation) is False

    # --- None role: backward-compatible all-access ---
    @pytest.mark.parametrize("operation", ["establish", "delegate", "verify", "audit", "read"])
    def test_none_role_allows_all(self, operation: str):
        """None role means no RBAC enforcement (backward compatibility)."""
        assert check_permission(None, operation) is True

    # --- Unknown operation ---
    def test_unknown_operation_denied_for_roles(self):
        """An operation not in any permission set must be denied."""
        assert check_permission(TrustRole.ADMIN, "unknown_op") is False
        assert check_permission(TrustRole.OPERATOR, "unknown_op") is False
        assert check_permission(TrustRole.OBSERVER, "unknown_op") is False
        assert check_permission(TrustRole.AUDITOR, "unknown_op") is False

    def test_unknown_operation_allowed_for_none_role(self):
        """None role permits everything, even unknown operations."""
        assert check_permission(None, "unknown_op") is True


# ---------------------------------------------------------------------------
# 4. require_permission function
# ---------------------------------------------------------------------------


class TestRequirePermission:
    """require_permission must raise PermissionError on denial, pass silently on success."""

    # --- Successful calls (no exception) ---
    @pytest.mark.parametrize("operation", ["establish", "delegate", "verify", "audit", "read"])
    def test_admin_does_not_raise(self, operation: str):
        require_permission(TrustRole.ADMIN, operation)  # should not raise

    def test_none_role_does_not_raise(self):
        require_permission(None, "establish")  # should not raise

    def test_operator_delegate_does_not_raise(self):
        require_permission(TrustRole.OPERATOR, "delegate")  # should not raise

    def test_auditor_audit_does_not_raise(self):
        require_permission(TrustRole.AUDITOR, "audit")  # should not raise

    # --- PermissionError cases ---
    def test_operator_establish_raises(self):
        with pytest.raises(PermissionError, match="operator.*establish"):
            require_permission(TrustRole.OPERATOR, "establish")

    def test_observer_verify_raises(self):
        with pytest.raises(PermissionError, match="observer.*verify"):
            require_permission(TrustRole.OBSERVER, "verify")

    def test_auditor_delegate_raises(self):
        with pytest.raises(PermissionError, match="auditor.*delegate"):
            require_permission(TrustRole.AUDITOR, "delegate")

    def test_observer_establish_raises(self):
        with pytest.raises(PermissionError, match="observer.*establish"):
            require_permission(TrustRole.OBSERVER, "establish")

    def test_error_message_includes_role_and_operation(self):
        """The PermissionError message must include both role and operation for debugging."""
        with pytest.raises(PermissionError) as exc_info:
            require_permission(TrustRole.OBSERVER, "audit")
        message = str(exc_info.value)
        assert "observer" in message
        assert "audit" in message


# ---------------------------------------------------------------------------
# 5. Role escalation prevention
# ---------------------------------------------------------------------------


class TestRoleEscalationPrevention:
    """No role may have permissions that exceed ADMIN."""

    def test_no_role_exceeds_admin(self):
        admin_perms = ROLE_PERMISSIONS[TrustRole.ADMIN]
        for role in TrustRole:
            role_perms = ROLE_PERMISSIONS[role]
            assert role_perms.issubset(admin_perms), (
                f"Role {role.value} has permissions {role_perms - admin_perms} not present in ADMIN"
            )

    def test_observer_is_subset_of_operator(self):
        """OBSERVER permissions must be a subset of OPERATOR permissions."""
        observer_perms = ROLE_PERMISSIONS[TrustRole.OBSERVER]
        operator_perms = ROLE_PERMISSIONS[TrustRole.OPERATOR]
        assert observer_perms.issubset(operator_perms)

    def test_all_roles_have_read(self):
        """Every role must have at least read permission."""
        for role in TrustRole:
            assert "read" in ROLE_PERMISSIONS[role], f"Role {role.value} must have read permission"
