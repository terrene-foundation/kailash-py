#!/usr/bin/env python3
"""
Unit Tests for Security Isolation (TODO-156)

Security and isolation tests for context-aware features:
- Tenant data cannot be accessed without proper context
- Context switch enforces registered-only tenants
- Deactivated tenants cannot be switched to
- Unregistered tenants raise clear errors
- Context restoration after security violations
- Stats track failed switch attempts
- Cannot unregister active tenant

Uses SQLite in-memory databases following Tier 1 testing guidelines.
"""

import pytest

from dataflow.core.tenant_context import (
    TenantContextSwitch,
    TenantInfo,
    _current_tenant,
    get_current_tenant_id,
)


@pytest.mark.unit
class TestTenantDataAccessControl:
    """Test that tenant data requires proper context."""

    def test_require_tenant_without_context_raises_error(self, memory_dataflow):
        """require_tenant() raises error when no context is set."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        _current_tenant.set(None)

        with pytest.raises(RuntimeError) as exc_info:
            ctx.require_tenant()

        assert "No tenant context" in str(exc_info.value)

    def test_require_tenant_with_context_succeeds(self, memory_dataflow):
        """require_tenant() succeeds when context is active."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("valid", "Valid Tenant")

        with ctx.switch("valid"):
            tenant_id = ctx.require_tenant()
            assert tenant_id == "valid"

    def test_get_current_tenant_returns_none_without_context(self, memory_dataflow):
        """get_current_tenant() returns None without active context."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        _current_tenant.set(None)

        assert ctx.get_current_tenant() is None


@pytest.mark.unit
class TestRegisteredOnlyEnforcement:
    """Test that only registered tenants can be switched to."""

    def test_switch_to_unregistered_tenant_raises_error(self, memory_dataflow):
        """Switching to unregistered tenant raises ValueError."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        with pytest.raises(ValueError) as exc_info:
            with ctx.switch("unregistered-tenant"):
                pass

        assert "not registered" in str(exc_info.value)

    def test_error_message_includes_available_tenants(self, memory_dataflow):
        """Error message lists available tenants when switch fails."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("available-1", "Available 1")
        ctx.register_tenant("available-2", "Available 2")

        with pytest.raises(ValueError) as exc_info:
            with ctx.switch("not-available"):
                pass

        error_msg = str(exc_info.value)
        assert "not-available" in error_msg
        assert "available-1" in error_msg or "Available tenants" in error_msg

    def test_error_message_suggests_register_tenant(self, memory_dataflow):
        """Error message suggests using register_tenant()."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        with pytest.raises(ValueError) as exc_info:
            with ctx.switch("new-tenant"):
                pass

        assert "register_tenant" in str(exc_info.value)


@pytest.mark.unit
class TestDeactivatedTenantEnforcement:
    """Test that deactivated tenants cannot be switched to."""

    def test_switch_to_deactivated_tenant_raises_error(self, memory_dataflow):
        """Switching to deactivated tenant raises ValueError."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-x", "Tenant X")
        ctx.deactivate_tenant("tenant-x")

        with pytest.raises(ValueError) as exc_info:
            with ctx.switch("tenant-x"):
                pass

        assert "not active" in str(exc_info.value)

    def test_deactivated_tenant_still_registered(self, memory_dataflow):
        """Deactivated tenant remains in registry."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("deactivated", "Deactivated")
        ctx.deactivate_tenant("deactivated")

        assert ctx.is_tenant_registered("deactivated")
        assert not ctx.is_tenant_active("deactivated")

    def test_reactivated_tenant_can_be_switched_to(self, memory_dataflow):
        """Reactivated tenant can be switched to."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("toggle", "Toggle")
        ctx.deactivate_tenant("toggle")

        # Should fail while deactivated
        with pytest.raises(ValueError):
            with ctx.switch("toggle"):
                pass

        ctx.activate_tenant("toggle")

        # Should succeed after reactivation
        with ctx.switch("toggle"):
            assert ctx.get_current_tenant() == "toggle"

    def test_error_message_suggests_activate_tenant(self, memory_dataflow):
        """Error message suggests using activate_tenant()."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("inactive", "Inactive")
        ctx.deactivate_tenant("inactive")

        with pytest.raises(ValueError) as exc_info:
            with ctx.switch("inactive"):
                pass

        assert "activate_tenant" in str(exc_info.value)


@pytest.mark.unit
class TestClearErrorMessages:
    """Test that error messages are clear and actionable."""

    def test_unregistered_tenant_error_is_clear(self, memory_dataflow):
        """Unregistered tenant error is clear and actionable."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        with pytest.raises(ValueError) as exc_info:
            with ctx.switch("mystery-tenant"):
                pass

        error_msg = str(exc_info.value)
        # Should mention the problematic tenant
        assert "mystery-tenant" in error_msg
        # Should indicate it's not registered
        assert "not registered" in error_msg

    def test_empty_tenant_id_error_is_clear(self, memory_dataflow):
        """Empty tenant ID error is clear."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        with pytest.raises(ValueError) as exc_info:
            ctx.register_tenant("", "Empty ID Tenant")

        assert "non-empty string" in str(exc_info.value)

    def test_none_tenant_id_error_is_clear(self, memory_dataflow):
        """None tenant ID error is clear."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        with pytest.raises(ValueError) as exc_info:
            ctx.register_tenant(None, "None ID Tenant")

        assert "non-empty string" in str(exc_info.value)

    def test_duplicate_registration_error_is_clear(self, memory_dataflow):
        """Duplicate registration error is clear."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("unique", "Unique Tenant")

        with pytest.raises(ValueError) as exc_info:
            ctx.register_tenant("unique", "Duplicate")

        assert "already registered" in str(exc_info.value)


@pytest.mark.unit
class TestContextRestorationAfterViolations:
    """Test context restoration after security violations."""

    def test_context_restored_after_unregistered_switch_attempt(self, memory_dataflow):
        """Context is restored after attempting to switch to unregistered tenant."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("safe", "Safe Tenant")

        _current_tenant.set(None)

        with ctx.switch("safe"):
            try:
                with ctx.switch("unsafe"):
                    pass
            except ValueError:
                pass

            # Should still be in "safe" context
            assert ctx.get_current_tenant() == "safe"

        assert ctx.get_current_tenant() is None

    def test_context_restored_after_deactivated_switch_attempt(self, memory_dataflow):
        """Context is restored after attempting to switch to deactivated tenant."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("active", "Active")
        ctx.register_tenant("inactive", "Inactive")
        ctx.deactivate_tenant("inactive")

        _current_tenant.set(None)

        with ctx.switch("active"):
            try:
                with ctx.switch("inactive"):
                    pass
            except ValueError:
                pass

            assert ctx.get_current_tenant() == "active"

        assert ctx.get_current_tenant() is None

    def test_multiple_violation_attempts_dont_corrupt_context(self, memory_dataflow):
        """Multiple violation attempts don't corrupt the context."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("valid", "Valid")

        _current_tenant.set(None)

        with ctx.switch("valid"):
            for i in range(5):
                try:
                    with ctx.switch(f"invalid-{i}"):
                        pass
                except ValueError:
                    pass

                assert ctx.get_current_tenant() == "valid"

        assert ctx.get_current_tenant() is None


@pytest.mark.unit
class TestStatsTrackFailedAttempts:
    """Test that stats track context switch statistics."""

    def test_stats_reflect_successful_switches(self, memory_dataflow):
        """Stats count successful switches."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tracked", "Tracked")

        initial_count = ctx._switch_count

        for _ in range(5):
            with ctx.switch("tracked"):
                pass

        assert ctx._switch_count == initial_count + 5

    def test_failed_switches_dont_increment_count(self, memory_dataflow):
        """Failed switch attempts don't increment switch count."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        initial_count = ctx._switch_count

        for _ in range(3):
            try:
                with ctx.switch("nonexistent"):
                    pass
            except ValueError:
                pass

        # Count should not have changed
        assert ctx._switch_count == initial_count

    def test_active_switches_not_affected_by_failed_attempts(self, memory_dataflow):
        """Failed attempts don't affect active switches count."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("active", "Active")

        _current_tenant.set(None)

        with ctx.switch("active"):
            assert ctx._active_switches == 1

            try:
                with ctx.switch("invalid"):
                    pass
            except ValueError:
                pass

            # Active switches should still be 1
            assert ctx._active_switches == 1


@pytest.mark.unit
class TestCannotUnregisterActiveTenant:
    """Test that active tenant cannot be unregistered."""

    def test_unregister_active_tenant_raises_error(self, memory_dataflow):
        """Unregistering active tenant raises ValueError."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("active", "Active Tenant")

        with ctx.switch("active"):
            with pytest.raises(ValueError) as exc_info:
                ctx.unregister_tenant("active")

            assert "active context" in str(exc_info.value)

    def test_can_unregister_after_switch_exits(self, memory_dataflow):
        """Can unregister tenant after context switch exits."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("temp", "Temporary")

        with ctx.switch("temp"):
            pass  # Use the context

        # Now should be able to unregister
        ctx.unregister_tenant("temp")
        assert not ctx.is_tenant_registered("temp")

    def test_unregister_inactive_tenant_succeeds(self, memory_dataflow):
        """Unregistering inactive tenant succeeds."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("other", "Other")
        ctx.register_tenant("target", "Target")

        _current_tenant.set(None)

        with ctx.switch("other"):
            # "target" is not active, so can be unregistered
            ctx.unregister_tenant("target")

            assert ctx.is_tenant_registered("other")
            assert not ctx.is_tenant_registered("target")

    def test_unregister_nonexistent_tenant_raises_error(self, memory_dataflow):
        """Unregistering nonexistent tenant raises error."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        with pytest.raises(ValueError) as exc_info:
            ctx.unregister_tenant("never-existed")

        assert "not registered" in str(exc_info.value)
