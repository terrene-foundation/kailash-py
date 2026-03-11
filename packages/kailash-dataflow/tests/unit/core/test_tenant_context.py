#!/usr/bin/env python3
"""
Unit Tests for Tenant Context Switching (TODO-155)

Tests the TenantContextSwitch class and TenantInfo dataclass for multi-tenant
context switching in DataFlow.

Uses SQLite in-memory databases following Tier 1 testing guidelines.

Test coverage:
1. TenantInfo creation - dataclass fields, defaults
2. TenantContextSwitch initialization - with DataFlow instance
3. register_tenant() - success, duplicate, invalid ID
4. unregister_tenant() - success, not found, active context
5. get_tenant() - found, not found
6. list_tenants() - empty, multiple
7. get_current_tenant() - none set, set via switch
8. switch() context manager - basic usage, restores previous, nested switches
9. switch() validation - unregistered tenant, inactive tenant
10. aswitch() async context manager - basic usage, restores context
11. aswitch() validation - same as switch
12. require_tenant() - with context, without context
13. deactivate_tenant() - success, prevents switch
14. activate_tenant() - re-enables switch
15. get_stats() - correct counts
16. Cross-tenant isolation - verify context doesn't leak between switches
17. Nested context switches - inner restores to outer correctly
18. Error during switch - context restored on exception
19. Concurrent switches (using asyncio.gather) - each gets own context
20. DataFlow.tenant_context property - accessible from DataFlow instance
21. Integration with workflow binding - context available during workflow ops
22. is_tenant_registered() - check registration status
23. is_tenant_active() - check activation status
24. get_current_tenant_id() module function - global access
"""

import asyncio
import time

import pytest

from dataflow.core.tenant_context import (
    TenantContextSwitch,
    TenantInfo,
    _current_tenant,
    get_current_tenant_id,
)


@pytest.mark.unit
class TestTenantInfo:
    """Test the TenantInfo dataclass."""

    # ---- Test 1: TenantInfo creation with defaults ----

    def test_tenant_info_creation_with_defaults(self):
        """TenantInfo is created with correct defaults."""
        info = TenantInfo(tenant_id="test-tenant", name="Test Tenant")

        assert info.tenant_id == "test-tenant"
        assert info.name == "Test Tenant"
        assert info.metadata == {}
        assert info.active is True
        assert info.created_at > 0  # Should have a timestamp

    def test_tenant_info_creation_with_metadata(self):
        """TenantInfo stores provided metadata."""
        metadata = {"region": "us-east-1", "tier": "premium"}
        info = TenantInfo(
            tenant_id="meta-tenant",
            name="Meta Tenant",
            metadata=metadata,
        )

        assert info.metadata == metadata
        assert info.metadata["region"] == "us-east-1"

    def test_tenant_info_creation_inactive(self):
        """TenantInfo can be created as inactive."""
        info = TenantInfo(
            tenant_id="inactive-tenant",
            name="Inactive Tenant",
            active=False,
        )

        assert info.active is False

    def test_tenant_info_created_at_is_recent(self):
        """TenantInfo created_at is close to current time."""
        before = time.time()
        info = TenantInfo(tenant_id="time-tenant", name="Time Tenant")
        after = time.time()

        assert before <= info.created_at <= after


@pytest.mark.unit
class TestTenantContextSwitchInitialization:
    """Test TenantContextSwitch initialization."""

    # ---- Test 2: TenantContextSwitch initialization ----

    def test_initialization_with_dataflow_instance(self, memory_dataflow):
        """TenantContextSwitch stores reference to DataFlow instance."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        assert ctx._dataflow is db
        assert ctx.dataflow_instance is db
        assert ctx._tenants == {}
        assert ctx._switch_count == 0
        assert ctx._active_switches == 0


@pytest.mark.unit
class TestRegisterTenant:
    """Test register_tenant() method."""

    # ---- Test 3: register_tenant() ----

    def test_register_tenant_success(self, memory_dataflow):
        """register_tenant() creates and returns TenantInfo."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        tenant = ctx.register_tenant("tenant-a", "Tenant A")

        assert isinstance(tenant, TenantInfo)
        assert tenant.tenant_id == "tenant-a"
        assert tenant.name == "Tenant A"
        assert tenant.active is True

    def test_register_tenant_with_metadata(self, memory_dataflow):
        """register_tenant() stores provided metadata."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        tenant = ctx.register_tenant(
            "meta-tenant",
            "Meta Tenant",
            metadata={"plan": "enterprise"},
        )

        assert tenant.metadata["plan"] == "enterprise"

    def test_register_tenant_duplicate_raises_error(self, memory_dataflow):
        """register_tenant() raises ValueError for duplicate tenant_id."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")

        with pytest.raises(ValueError) as excinfo:
            ctx.register_tenant("tenant-a", "Duplicate A")

        assert "already registered" in str(excinfo.value)

    def test_register_tenant_empty_id_raises_error(self, memory_dataflow):
        """register_tenant() raises ValueError for empty tenant_id."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        with pytest.raises(ValueError) as excinfo:
            ctx.register_tenant("", "Empty Tenant")

        assert "non-empty string" in str(excinfo.value)

    def test_register_tenant_none_id_raises_error(self, memory_dataflow):
        """register_tenant() raises ValueError for None tenant_id."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        with pytest.raises(ValueError) as excinfo:
            ctx.register_tenant(None, "None Tenant")

        assert "non-empty string" in str(excinfo.value)

    def test_register_tenant_non_string_id_raises_error(self, memory_dataflow):
        """register_tenant() raises ValueError for non-string tenant_id."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        with pytest.raises(ValueError) as excinfo:
            ctx.register_tenant(123, "Numeric Tenant")

        assert "non-empty string" in str(excinfo.value)


@pytest.mark.unit
class TestUnregisterTenant:
    """Test unregister_tenant() method."""

    # ---- Test 4: unregister_tenant() ----

    def test_unregister_tenant_success(self, memory_dataflow):
        """unregister_tenant() removes tenant from registry."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")
        assert ctx.get_tenant("tenant-a") is not None

        ctx.unregister_tenant("tenant-a")

        assert ctx.get_tenant("tenant-a") is None

    def test_unregister_tenant_not_found_raises_error(self, memory_dataflow):
        """unregister_tenant() raises ValueError for unregistered tenant."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        with pytest.raises(ValueError) as excinfo:
            ctx.unregister_tenant("nonexistent")

        assert "not registered" in str(excinfo.value)

    def test_unregister_tenant_active_context_raises_error(self, memory_dataflow):
        """unregister_tenant() raises ValueError if tenant is current context."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")

        with ctx.switch("tenant-a"):
            with pytest.raises(ValueError) as excinfo:
                ctx.unregister_tenant("tenant-a")

            assert "active context" in str(excinfo.value)


@pytest.mark.unit
class TestGetTenant:
    """Test get_tenant() method."""

    # ---- Test 5: get_tenant() ----

    def test_get_tenant_found(self, memory_dataflow):
        """get_tenant() returns TenantInfo when found."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")
        tenant = ctx.get_tenant("tenant-a")

        assert tenant is not None
        assert tenant.tenant_id == "tenant-a"

    def test_get_tenant_not_found(self, memory_dataflow):
        """get_tenant() returns None when not found."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        tenant = ctx.get_tenant("nonexistent")

        assert tenant is None


@pytest.mark.unit
class TestListTenants:
    """Test list_tenants() method."""

    # ---- Test 6: list_tenants() ----

    def test_list_tenants_empty(self, memory_dataflow):
        """list_tenants() returns empty list when no tenants."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        tenants = ctx.list_tenants()

        assert tenants == []

    def test_list_tenants_multiple(self, memory_dataflow):
        """list_tenants() returns all registered tenants."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")
        ctx.register_tenant("tenant-b", "Tenant B")
        ctx.register_tenant("tenant-c", "Tenant C")

        tenants = ctx.list_tenants()

        assert len(tenants) == 3
        tenant_ids = [t.tenant_id for t in tenants]
        assert "tenant-a" in tenant_ids
        assert "tenant-b" in tenant_ids
        assert "tenant-c" in tenant_ids


@pytest.mark.unit
class TestGetCurrentTenant:
    """Test get_current_tenant() method."""

    # ---- Test 7: get_current_tenant() ----

    def test_get_current_tenant_none_set(self, memory_dataflow):
        """get_current_tenant() returns None when no context is set."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        # Reset the context variable to ensure clean state
        _current_tenant.set(None)

        current = ctx.get_current_tenant()

        assert current is None

    def test_get_current_tenant_with_switch(self, memory_dataflow):
        """get_current_tenant() returns tenant_id when switch is active."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")

        with ctx.switch("tenant-a"):
            current = ctx.get_current_tenant()
            assert current == "tenant-a"


@pytest.mark.unit
class TestSwitchContextManager:
    """Test switch() context manager."""

    # ---- Test 8: switch() context manager ----

    def test_switch_basic_usage(self, memory_dataflow):
        """switch() sets tenant context for the duration of the block."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")

        # Before switch
        assert ctx.get_current_tenant() is None

        with ctx.switch("tenant-a") as tenant:
            # Inside switch
            assert ctx.get_current_tenant() == "tenant-a"
            assert tenant.tenant_id == "tenant-a"

        # After switch
        assert ctx.get_current_tenant() is None

    def test_switch_restores_previous_context(self, memory_dataflow):
        """switch() restores the previous context on exit."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")
        ctx.register_tenant("tenant-b", "Tenant B")

        with ctx.switch("tenant-a"):
            assert ctx.get_current_tenant() == "tenant-a"

            with ctx.switch("tenant-b"):
                assert ctx.get_current_tenant() == "tenant-b"

            # Inner switch exits, should restore to tenant-a
            assert ctx.get_current_tenant() == "tenant-a"

        # Outer switch exits, should restore to None
        assert ctx.get_current_tenant() is None

    def test_switch_nested_switches(self, memory_dataflow):
        """switch() handles multiple levels of nesting correctly."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")
        ctx.register_tenant("tenant-b", "Tenant B")
        ctx.register_tenant("tenant-c", "Tenant C")

        with ctx.switch("tenant-a"):
            assert ctx.get_current_tenant() == "tenant-a"

            with ctx.switch("tenant-b"):
                assert ctx.get_current_tenant() == "tenant-b"

                with ctx.switch("tenant-c"):
                    assert ctx.get_current_tenant() == "tenant-c"

                assert ctx.get_current_tenant() == "tenant-b"

            assert ctx.get_current_tenant() == "tenant-a"

        assert ctx.get_current_tenant() is None

    # ---- Test 9: switch() validation ----

    def test_switch_unregistered_tenant_raises_error(self, memory_dataflow):
        """switch() raises ValueError for unregistered tenant."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        with pytest.raises(ValueError) as excinfo:
            with ctx.switch("nonexistent"):
                pass

        assert "not registered" in str(excinfo.value)
        assert "nonexistent" in str(excinfo.value)

    def test_switch_inactive_tenant_raises_error(self, memory_dataflow):
        """switch() raises ValueError for inactive tenant."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")
        ctx.deactivate_tenant("tenant-a")

        with pytest.raises(ValueError) as excinfo:
            with ctx.switch("tenant-a"):
                pass

        assert "not active" in str(excinfo.value)


@pytest.mark.unit
class TestAswitchAsyncContextManager:
    """Test aswitch() async context manager."""

    # ---- Test 10: aswitch() async context manager ----

    @pytest.mark.asyncio
    async def test_aswitch_basic_usage(self, memory_dataflow):
        """aswitch() sets tenant context for async block."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")

        # Before switch
        assert ctx.get_current_tenant() is None

        async with ctx.aswitch("tenant-a") as tenant:
            # Inside switch
            assert ctx.get_current_tenant() == "tenant-a"
            assert tenant.tenant_id == "tenant-a"

        # After switch
        assert ctx.get_current_tenant() is None

    @pytest.mark.asyncio
    async def test_aswitch_restores_context(self, memory_dataflow):
        """aswitch() restores context after async block."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")
        ctx.register_tenant("tenant-b", "Tenant B")

        async with ctx.aswitch("tenant-a"):
            assert ctx.get_current_tenant() == "tenant-a"

            async with ctx.aswitch("tenant-b"):
                assert ctx.get_current_tenant() == "tenant-b"

            assert ctx.get_current_tenant() == "tenant-a"

        assert ctx.get_current_tenant() is None

    # ---- Test 11: aswitch() validation ----

    @pytest.mark.asyncio
    async def test_aswitch_unregistered_tenant_raises_error(self, memory_dataflow):
        """aswitch() raises ValueError for unregistered tenant."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        with pytest.raises(ValueError) as excinfo:
            async with ctx.aswitch("nonexistent"):
                pass

        assert "not registered" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_aswitch_inactive_tenant_raises_error(self, memory_dataflow):
        """aswitch() raises ValueError for inactive tenant."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")
        ctx.deactivate_tenant("tenant-a")

        with pytest.raises(ValueError) as excinfo:
            async with ctx.aswitch("tenant-a"):
                pass

        assert "not active" in str(excinfo.value)


@pytest.mark.unit
class TestRequireTenant:
    """Test require_tenant() method."""

    # ---- Test 12: require_tenant() ----

    def test_require_tenant_with_context(self, memory_dataflow):
        """require_tenant() returns tenant_id when context is active."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")

        with ctx.switch("tenant-a"):
            result = ctx.require_tenant()
            assert result == "tenant-a"

    def test_require_tenant_without_context_raises_error(self, memory_dataflow):
        """require_tenant() raises RuntimeError when no context is active."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        # Ensure no context is set
        _current_tenant.set(None)

        with pytest.raises(RuntimeError) as excinfo:
            ctx.require_tenant()

        assert "No tenant context" in str(excinfo.value)


@pytest.mark.unit
class TestDeactivateTenant:
    """Test deactivate_tenant() method."""

    # ---- Test 13: deactivate_tenant() ----

    def test_deactivate_tenant_success(self, memory_dataflow):
        """deactivate_tenant() sets active=False on tenant."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")
        assert ctx.get_tenant("tenant-a").active is True

        ctx.deactivate_tenant("tenant-a")

        assert ctx.get_tenant("tenant-a").active is False

    def test_deactivate_tenant_prevents_switch(self, memory_dataflow):
        """deactivate_tenant() prevents switching to tenant."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")
        ctx.deactivate_tenant("tenant-a")

        with pytest.raises(ValueError) as excinfo:
            with ctx.switch("tenant-a"):
                pass

        assert "not active" in str(excinfo.value)

    def test_deactivate_tenant_not_found_raises_error(self, memory_dataflow):
        """deactivate_tenant() raises ValueError for unregistered tenant."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        with pytest.raises(ValueError) as excinfo:
            ctx.deactivate_tenant("nonexistent")

        assert "not registered" in str(excinfo.value)


@pytest.mark.unit
class TestActivateTenant:
    """Test activate_tenant() method."""

    # ---- Test 14: activate_tenant() ----

    def test_activate_tenant_re_enables_switch(self, memory_dataflow):
        """activate_tenant() re-enables switching to tenant."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")
        ctx.deactivate_tenant("tenant-a")

        # Should fail while inactive
        with pytest.raises(ValueError):
            with ctx.switch("tenant-a"):
                pass

        # Reactivate
        ctx.activate_tenant("tenant-a")

        # Should now succeed
        with ctx.switch("tenant-a") as tenant:
            assert tenant.tenant_id == "tenant-a"
            assert tenant.active is True

    def test_activate_tenant_not_found_raises_error(self, memory_dataflow):
        """activate_tenant() raises ValueError for unregistered tenant."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        with pytest.raises(ValueError) as excinfo:
            ctx.activate_tenant("nonexistent")

        assert "not registered" in str(excinfo.value)


@pytest.mark.unit
class TestGetStats:
    """Test get_stats() method."""

    # ---- Test 15: get_stats() ----

    def test_get_stats_initial(self, memory_dataflow):
        """get_stats() returns correct initial values."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        # Ensure no context is set
        _current_tenant.set(None)

        stats = ctx.get_stats()

        assert stats["total_tenants"] == 0
        assert stats["active_tenants"] == 0
        assert stats["total_switches"] == 0
        assert stats["active_switches"] == 0
        assert stats["current_tenant"] is None

    def test_get_stats_with_tenants(self, memory_dataflow):
        """get_stats() counts registered and active tenants."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")
        ctx.register_tenant("tenant-b", "Tenant B")
        ctx.register_tenant("tenant-c", "Tenant C")
        ctx.deactivate_tenant("tenant-c")

        stats = ctx.get_stats()

        assert stats["total_tenants"] == 3
        assert stats["active_tenants"] == 2

    def test_get_stats_counts_switches(self, memory_dataflow):
        """get_stats() counts total switches."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")

        with ctx.switch("tenant-a"):
            pass

        with ctx.switch("tenant-a"):
            pass

        stats = ctx.get_stats()
        assert stats["total_switches"] == 2

    def test_get_stats_active_switches(self, memory_dataflow):
        """get_stats() shows active switch count during nested switches."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")
        ctx.register_tenant("tenant-b", "Tenant B")

        with ctx.switch("tenant-a"):
            stats_1 = ctx.get_stats()
            assert stats_1["active_switches"] == 1

            with ctx.switch("tenant-b"):
                stats_2 = ctx.get_stats()
                assert stats_2["active_switches"] == 2

            stats_3 = ctx.get_stats()
            assert stats_3["active_switches"] == 1

        stats_4 = ctx.get_stats()
        assert stats_4["active_switches"] == 0


@pytest.mark.unit
class TestCrossTenantIsolation:
    """Test cross-tenant isolation."""

    # ---- Test 16: Cross-tenant isolation ----

    def test_context_does_not_leak(self, memory_dataflow):
        """Context doesn't leak between sequential switches."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")
        ctx.register_tenant("tenant-b", "Tenant B")

        with ctx.switch("tenant-a"):
            assert ctx.get_current_tenant() == "tenant-a"

        assert ctx.get_current_tenant() is None

        with ctx.switch("tenant-b"):
            assert ctx.get_current_tenant() == "tenant-b"

        assert ctx.get_current_tenant() is None


@pytest.mark.unit
class TestNestedContextSwitches:
    """Test nested context switches."""

    # ---- Test 17: Nested context switches ----

    def test_inner_restores_to_outer(self, memory_dataflow):
        """Inner switch restores to outer tenant on exit."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("outer", "Outer Tenant")
        ctx.register_tenant("inner", "Inner Tenant")

        with ctx.switch("outer"):
            assert ctx.get_current_tenant() == "outer"

            with ctx.switch("inner"):
                assert ctx.get_current_tenant() == "inner"

            # Should be back to outer
            assert ctx.get_current_tenant() == "outer"


@pytest.mark.unit
class TestErrorDuringSwitch:
    """Test error handling during switch."""

    # ---- Test 18: Error during switch ----

    def test_context_restored_on_exception(self, memory_dataflow):
        """Context is restored even when exception occurs in switch block."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")
        ctx.register_tenant("tenant-b", "Tenant B")

        with ctx.switch("tenant-a"):
            assert ctx.get_current_tenant() == "tenant-a"

            try:
                with ctx.switch("tenant-b"):
                    assert ctx.get_current_tenant() == "tenant-b"
                    raise ValueError("Simulated error")
            except ValueError:
                pass

            # Should be back to tenant-a despite error
            assert ctx.get_current_tenant() == "tenant-a"

    @pytest.mark.asyncio
    async def test_async_context_restored_on_exception(self, memory_dataflow):
        """Async context is restored even when exception occurs."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")

        try:
            async with ctx.aswitch("tenant-a"):
                assert ctx.get_current_tenant() == "tenant-a"
                raise ValueError("Simulated async error")
        except ValueError:
            pass

        assert ctx.get_current_tenant() is None


@pytest.mark.unit
class TestConcurrentSwitches:
    """Test concurrent context switches."""

    # ---- Test 19: Concurrent switches ----

    @pytest.mark.asyncio
    async def test_concurrent_async_switches_isolated(self, memory_dataflow):
        """Concurrent async switches maintain isolated contexts."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")
        ctx.register_tenant("tenant-b", "Tenant B")
        ctx.register_tenant("tenant-c", "Tenant C")

        results = {}

        async def task_a():
            async with ctx.aswitch("tenant-a"):
                await asyncio.sleep(0.01)  # Small delay to interleave
                results["task_a"] = ctx.get_current_tenant()

        async def task_b():
            async with ctx.aswitch("tenant-b"):
                await asyncio.sleep(0.01)
                results["task_b"] = ctx.get_current_tenant()

        async def task_c():
            async with ctx.aswitch("tenant-c"):
                await asyncio.sleep(0.01)
                results["task_c"] = ctx.get_current_tenant()

        await asyncio.gather(task_a(), task_b(), task_c())

        # Each task should have seen its own tenant
        assert results["task_a"] == "tenant-a"
        assert results["task_b"] == "tenant-b"
        assert results["task_c"] == "tenant-c"


@pytest.mark.unit
class TestDataFlowTenantContextProperty:
    """Test DataFlow.tenant_context property."""

    # ---- Test 20: DataFlow.tenant_context property ----

    def test_tenant_context_accessible(self, memory_dataflow):
        """tenant_context property is accessible from DataFlow instance."""
        db = memory_dataflow

        ctx = db.tenant_context

        assert ctx is not None
        assert isinstance(ctx, TenantContextSwitch)
        assert ctx.dataflow_instance is db

    def test_tenant_context_is_same_instance(self, memory_dataflow):
        """tenant_context property returns same instance each time."""
        db = memory_dataflow

        ctx1 = db.tenant_context
        ctx2 = db.tenant_context

        assert ctx1 is ctx2


@pytest.mark.unit
class TestIntegrationWithWorkflowBinding:
    """Test integration with workflow binding."""

    # ---- Test 21: Integration with workflow binding ----

    def test_tenant_context_available_during_workflow(self, memory_dataflow):
        """Tenant context is available during workflow operations."""
        db = memory_dataflow

        @db.model
        class User:
            name: str
            email: str

        db.tenant_context.register_tenant("tenant-a", "Tenant A")

        with db.tenant_context.switch("tenant-a"):
            # Create workflow while in tenant context
            workflow = db.create_workflow("user_ops")

            # Verify tenant context is set
            assert db.tenant_context.get_current_tenant() == "tenant-a"

            # The workflow builder should work
            assert workflow is not None


@pytest.mark.unit
class TestIsTenantRegistered:
    """Test is_tenant_registered() method."""

    # ---- Test 22: is_tenant_registered() ----

    def test_is_tenant_registered_true(self, memory_dataflow):
        """is_tenant_registered() returns True for registered tenant."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")

        assert ctx.is_tenant_registered("tenant-a") is True

    def test_is_tenant_registered_false(self, memory_dataflow):
        """is_tenant_registered() returns False for unregistered tenant."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        assert ctx.is_tenant_registered("nonexistent") is False


@pytest.mark.unit
class TestIsTenantActive:
    """Test is_tenant_active() method."""

    # ---- Test 23: is_tenant_active() ----

    def test_is_tenant_active_true(self, memory_dataflow):
        """is_tenant_active() returns True for active tenant."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")

        assert ctx.is_tenant_active("tenant-a") is True

    def test_is_tenant_active_false_when_deactivated(self, memory_dataflow):
        """is_tenant_active() returns False for deactivated tenant."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")
        ctx.deactivate_tenant("tenant-a")

        assert ctx.is_tenant_active("tenant-a") is False

    def test_is_tenant_active_false_when_not_registered(self, memory_dataflow):
        """is_tenant_active() returns False for unregistered tenant."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        assert ctx.is_tenant_active("nonexistent") is False


@pytest.mark.unit
class TestGetCurrentTenantIdFunction:
    """Test get_current_tenant_id() module function."""

    # ---- Test 24: get_current_tenant_id() module function ----

    def test_get_current_tenant_id_returns_none(self, memory_dataflow):
        """get_current_tenant_id() returns None when no context set."""
        # Reset context
        _current_tenant.set(None)

        result = get_current_tenant_id()

        assert result is None

    def test_get_current_tenant_id_returns_tenant(self, memory_dataflow):
        """get_current_tenant_id() returns tenant_id when context set."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")

        with ctx.switch("tenant-a"):
            result = get_current_tenant_id()
            assert result == "tenant-a"


@pytest.mark.unit
class TestErrorMessageQuality:
    """Test that error messages are helpful."""

    def test_switch_error_lists_available_tenants(self, memory_dataflow):
        """Error message lists available tenants when switch fails."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")
        ctx.register_tenant("tenant-b", "Tenant B")

        with pytest.raises(ValueError) as excinfo:
            with ctx.switch("nonexistent"):
                pass

        error_msg = str(excinfo.value)
        assert "nonexistent" in error_msg
        assert "tenant-a" in error_msg or "['tenant-a'" in error_msg

    def test_switch_error_suggests_register(self, memory_dataflow):
        """Error message suggests using register_tenant()."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        with pytest.raises(ValueError) as excinfo:
            with ctx.switch("new-tenant"):
                pass

        error_msg = str(excinfo.value)
        assert "register_tenant" in error_msg

    def test_inactive_error_suggests_activate(self, memory_dataflow):
        """Error message suggests using activate_tenant()."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")
        ctx.deactivate_tenant("tenant-a")

        with pytest.raises(ValueError) as excinfo:
            with ctx.switch("tenant-a"):
                pass

        error_msg = str(excinfo.value)
        assert "activate_tenant" in error_msg
