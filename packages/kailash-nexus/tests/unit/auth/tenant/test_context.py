"""Unit tests for TenantContext (TODO-310E).

Tier 1 tests - mocking allowed.
Tests context switching, registration, validation, and helpers.
"""

import pytest
from nexus.auth.tenant.context import (
    TenantContext,
    TenantInfo,
    get_current_tenant,
    get_current_tenant_id,
    require_tenant,
)
from nexus.auth.tenant.exceptions import (
    TenantContextError,
    TenantInactiveError,
    TenantNotFoundError,
)

# =============================================================================
# Tests: TenantInfo Dataclass
# =============================================================================


class TestTenantInfo:
    """Test TenantInfo dataclass."""

    def test_minimal_creation(self):
        """Create with just tenant_id."""
        info = TenantInfo(tenant_id="tenant-1")
        assert info.tenant_id == "tenant-1"
        assert info.name is None
        assert info.active is True
        assert info.metadata == {}
        assert info.created_at is not None

    def test_full_creation(self):
        """Create with all fields."""
        info = TenantInfo(
            tenant_id="tenant-1",
            name="Acme Corp",
            active=True,
            metadata={"plan": "enterprise"},
        )
        assert info.name == "Acme Corp"
        assert info.metadata["plan"] == "enterprise"


# =============================================================================
# Tests: Registration
# =============================================================================


class TestTenantContextRegistration:
    """Test tenant registration."""

    def test_register_tenant(self):
        """Register a tenant."""
        ctx = TenantContext()
        tenant = ctx.register("tenant-1", name="Test Tenant")
        assert tenant.tenant_id == "tenant-1"
        assert tenant.name == "Test Tenant"

    def test_register_with_metadata(self):
        """Register a tenant with metadata."""
        ctx = TenantContext()
        tenant = ctx.register(
            "tenant-1",
            name="Test",
            metadata={"plan": "pro"},
        )
        assert tenant.metadata["plan"] == "pro"

    def test_register_inactive(self):
        """Register an inactive tenant."""
        ctx = TenantContext()
        tenant = ctx.register("tenant-1", active=False)
        assert tenant.active is False

    def test_duplicate_registration_raises(self):
        """Duplicate registration raises ValueError."""
        ctx = TenantContext()
        ctx.register("tenant-1")
        with pytest.raises(ValueError, match="already registered"):
            ctx.register("tenant-1")

    def test_empty_id_raises(self):
        """Empty tenant_id raises ValueError."""
        ctx = TenantContext()
        with pytest.raises(ValueError, match="non-empty string"):
            ctx.register("")

    def test_get_tenant(self):
        """Get registered tenant by ID."""
        ctx = TenantContext()
        ctx.register("tenant-1", name="Test")
        tenant = ctx.get("tenant-1")
        assert tenant is not None
        assert tenant.name == "Test"

    def test_get_nonexistent_returns_none(self):
        """Get nonexistent tenant returns None."""
        ctx = TenantContext()
        assert ctx.get("nonexistent") is None

    def test_list_tenants(self):
        """List all registered tenants."""
        ctx = TenantContext()
        ctx.register("tenant-1")
        ctx.register("tenant-2")
        tenants = ctx.list_tenants()
        assert len(tenants) == 2

    def test_unregister(self):
        """Unregister a tenant."""
        ctx = TenantContext()
        ctx.register("tenant-1")
        ctx.unregister("tenant-1")
        assert ctx.get("tenant-1") is None

    def test_unregister_nonexistent_raises(self):
        """Unregister nonexistent raises ValueError."""
        ctx = TenantContext()
        with pytest.raises(ValueError, match="not registered"):
            ctx.unregister("nonexistent")

    def test_unregister_active_raises(self):
        """Cannot unregister active tenant."""
        ctx = TenantContext()
        ctx.register("tenant-1")
        with ctx.switch("tenant-1"):
            with pytest.raises(ValueError, match="while it is active"):
                ctx.unregister("tenant-1")


# =============================================================================
# Tests: Synchronous Context Switching
# =============================================================================


class TestTenantContextSwitch:
    """Test synchronous context switching."""

    def test_switch_sets_context(self):
        """switch() sets current tenant."""
        ctx = TenantContext()
        ctx.register("tenant-1")

        assert ctx.current() is None

        with ctx.switch("tenant-1") as tenant:
            assert ctx.current().tenant_id == "tenant-1"
            assert tenant.tenant_id == "tenant-1"

        assert ctx.current() is None

    def test_nested_switch(self):
        """Nested switch restores previous context."""
        ctx = TenantContext()
        ctx.register("tenant-1")
        ctx.register("tenant-2")

        with ctx.switch("tenant-1"):
            assert ctx.current().tenant_id == "tenant-1"

            with ctx.switch("tenant-2"):
                assert ctx.current().tenant_id == "tenant-2"

            assert ctx.current().tenant_id == "tenant-1"

        assert ctx.current() is None

    def test_switch_unregistered_raises(self):
        """switch() to unregistered tenant raises."""
        ctx = TenantContext()
        with pytest.raises(TenantNotFoundError) as exc_info:
            with ctx.switch("unknown"):
                pass
        assert exc_info.value.tenant_id == "unknown"

    def test_switch_inactive_raises(self):
        """switch() to inactive tenant raises."""
        ctx = TenantContext()
        ctx.register("tenant-1", active=False)
        with pytest.raises(TenantInactiveError):
            with ctx.switch("tenant-1"):
                pass

    def test_switch_restores_on_exception(self):
        """Context is restored even when exception occurs."""
        ctx = TenantContext()
        ctx.register("tenant-1")

        try:
            with ctx.switch("tenant-1"):
                raise RuntimeError("test error")
        except RuntimeError:
            pass

        assert ctx.current() is None


# =============================================================================
# Tests: Async Context Switching
# =============================================================================


class TestTenantContextAsyncSwitch:
    """Test asynchronous context switching."""

    @pytest.mark.asyncio
    async def test_aswitch_sets_context(self):
        """aswitch() sets current tenant."""
        ctx = TenantContext()
        ctx.register("tenant-1")

        assert ctx.current() is None

        async with ctx.aswitch("tenant-1") as tenant:
            assert ctx.current().tenant_id == "tenant-1"
            assert tenant.tenant_id == "tenant-1"

        assert ctx.current() is None

    @pytest.mark.asyncio
    async def test_nested_aswitch(self):
        """Nested aswitch restores context."""
        ctx = TenantContext()
        ctx.register("tenant-1")
        ctx.register("tenant-2")

        async with ctx.aswitch("tenant-1"):
            assert ctx.current().tenant_id == "tenant-1"

            async with ctx.aswitch("tenant-2"):
                assert ctx.current().tenant_id == "tenant-2"

            assert ctx.current().tenant_id == "tenant-1"

        assert ctx.current() is None

    @pytest.mark.asyncio
    async def test_aswitch_restores_on_exception(self):
        """Async context restored even on exception."""
        ctx = TenantContext()
        ctx.register("tenant-1")

        try:
            async with ctx.aswitch("tenant-1"):
                raise RuntimeError("test error")
        except RuntimeError:
            pass

        assert ctx.current() is None


# =============================================================================
# Tests: require() and helpers
# =============================================================================


class TestTenantContextRequire:
    """Test require() and helper functions."""

    def test_require_raises_when_no_context(self):
        """require() raises when no tenant context."""
        ctx = TenantContext()
        ctx.register("tenant-1")
        with pytest.raises(TenantContextError, match="No tenant context"):
            ctx.require()

    def test_require_returns_tenant(self):
        """require() returns tenant when context is active."""
        ctx = TenantContext()
        ctx.register("tenant-1")
        with ctx.switch("tenant-1"):
            tenant = ctx.require()
            assert tenant.tenant_id == "tenant-1"

    def test_get_current_tenant_none(self):
        """get_current_tenant() returns None without context."""
        assert get_current_tenant() is None

    def test_get_current_tenant_id_none(self):
        """get_current_tenant_id() returns None without context."""
        assert get_current_tenant_id() is None

    def test_require_tenant_raises(self):
        """require_tenant() raises without context."""
        with pytest.raises(TenantContextError):
            require_tenant()

    def test_helpers_with_context(self):
        """Helper functions work with active context."""
        ctx = TenantContext()
        ctx.register("tenant-1")
        with ctx.switch("tenant-1"):
            assert get_current_tenant().tenant_id == "tenant-1"
            assert get_current_tenant_id() == "tenant-1"
            assert require_tenant().tenant_id == "tenant-1"


# =============================================================================
# Tests: Deactivate/Activate
# =============================================================================


class TestTenantContextActivation:
    """Test deactivation and activation."""

    def test_deactivate(self):
        """Deactivate prevents switching."""
        ctx = TenantContext()
        ctx.register("tenant-1")
        ctx.deactivate("tenant-1")

        with pytest.raises(TenantInactiveError):
            with ctx.switch("tenant-1"):
                pass

    def test_activate(self):
        """Activate allows switching again."""
        ctx = TenantContext()
        ctx.register("tenant-1")
        ctx.deactivate("tenant-1")
        ctx.activate("tenant-1")

        with ctx.switch("tenant-1"):
            assert ctx.current().tenant_id == "tenant-1"

    def test_deactivate_nonexistent_raises(self):
        """Deactivate nonexistent tenant raises."""
        ctx = TenantContext()
        with pytest.raises(ValueError, match="not registered"):
            ctx.deactivate("nonexistent")


# =============================================================================
# Tests: Statistics
# =============================================================================


class TestTenantContextStats:
    """Test context statistics."""

    def test_stats_empty(self):
        """Stats for empty context."""
        ctx = TenantContext()
        stats = ctx.get_stats()
        assert stats["total_tenants"] == 0
        assert stats["active_tenants"] == 0
        assert stats["total_switches"] == 0
        assert stats["current_tenant"] is None

    def test_stats_after_registration(self):
        """Stats after registration."""
        ctx = TenantContext()
        ctx.register("tenant-1")
        ctx.register("tenant-2", active=False)
        stats = ctx.get_stats()
        assert stats["total_tenants"] == 2
        assert stats["active_tenants"] == 1

    def test_stats_after_switch(self):
        """Stats after context switch."""
        ctx = TenantContext()
        ctx.register("tenant-1")
        with ctx.switch("tenant-1"):
            stats = ctx.get_stats()
            assert stats["total_switches"] == 1
            assert stats["active_switches"] == 1
            assert stats["current_tenant"] == "tenant-1"


# =============================================================================
# Tests: Validation Disabled
# =============================================================================


class TestTenantContextNoValidation:
    """Test context with validation disabled."""

    def test_switch_without_registration(self):
        """switch() works without registration when validation disabled."""
        ctx = TenantContext(validate_registered=False)
        with ctx.switch("any-tenant") as tenant:
            assert tenant.tenant_id == "any-tenant"

    @pytest.mark.asyncio
    async def test_aswitch_without_registration(self):
        """aswitch() works without registration when validation disabled."""
        ctx = TenantContext(validate_registered=False)
        async with ctx.aswitch("any-tenant") as tenant:
            assert tenant.tenant_id == "any-tenant"
