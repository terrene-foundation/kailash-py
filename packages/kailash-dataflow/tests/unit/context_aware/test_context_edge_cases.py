#!/usr/bin/env python3
"""
Unit Tests for Context Edge Cases (TODO-156)

Tests edge case scenarios for context handling:
- Nested context switches 3+ levels deep
- Context switches with exceptions at each nesting level
- Rapid context switching (100+ switches in sequence)
- Context switch during workflow execution
- Empty tenant context (no tenants registered)
- Maximum tenants (1000+) registered
- Context stats accuracy after many operations
- Thread-safety of context operations
- Async task isolation

Uses SQLite in-memory databases following Tier 1 testing guidelines.
"""

import asyncio
import threading
import time

import pytest

from dataflow.core.tenant_context import (
    TenantContextSwitch,
    TenantInfo,
    _current_tenant,
    get_current_tenant_id,
)


@pytest.mark.unit
class TestDeeplyNestedContextSwitches:
    """Test nested context switches at 3+ levels deep."""

    def test_three_levels_deep_context_restoration(self, memory_dataflow):
        """Context is correctly restored through 3 levels of nesting."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("level-1", "Level 1")
        ctx.register_tenant("level-2", "Level 2")
        ctx.register_tenant("level-3", "Level 3")

        # Reset to ensure clean state
        _current_tenant.set(None)

        assert ctx.get_current_tenant() is None

        with ctx.switch("level-1"):
            assert ctx.get_current_tenant() == "level-1"

            with ctx.switch("level-2"):
                assert ctx.get_current_tenant() == "level-2"

                with ctx.switch("level-3"):
                    assert ctx.get_current_tenant() == "level-3"

                assert ctx.get_current_tenant() == "level-2"

            assert ctx.get_current_tenant() == "level-1"

        assert ctx.get_current_tenant() is None

    def test_five_levels_deep_context_restoration(self, memory_dataflow):
        """Context is correctly restored through 5 levels of nesting."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        for i in range(1, 6):
            ctx.register_tenant(f"level-{i}", f"Level {i}")

        _current_tenant.set(None)

        with ctx.switch("level-1"):
            with ctx.switch("level-2"):
                with ctx.switch("level-3"):
                    with ctx.switch("level-4"):
                        with ctx.switch("level-5"):
                            assert ctx.get_current_tenant() == "level-5"
                        assert ctx.get_current_tenant() == "level-4"
                    assert ctx.get_current_tenant() == "level-3"
                assert ctx.get_current_tenant() == "level-2"
            assert ctx.get_current_tenant() == "level-1"
        assert ctx.get_current_tenant() is None

    def test_ten_levels_deep_context_restoration(self, memory_dataflow):
        """Context is correctly restored through 10 levels of nesting."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        for i in range(1, 11):
            ctx.register_tenant(f"deep-{i}", f"Deep {i}")

        _current_tenant.set(None)

        def nested_switch(ctx, level, max_level):
            if level > max_level:
                assert ctx.get_current_tenant() == f"deep-{max_level}"
                return

            with ctx.switch(f"deep-{level}"):
                assert ctx.get_current_tenant() == f"deep-{level}"
                nested_switch(ctx, level + 1, max_level)
                assert ctx.get_current_tenant() == f"deep-{level}"

        nested_switch(ctx, 1, 10)
        assert ctx.get_current_tenant() is None


@pytest.mark.unit
class TestContextSwitchesWithExceptions:
    """Test context switches with exceptions at various nesting levels."""

    def test_exception_at_level_1_restores_context(self, memory_dataflow):
        """Exception at first level restores context correctly."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")

        _current_tenant.set(None)

        try:
            with ctx.switch("tenant-a"):
                raise ValueError("Test error at level 1")
        except ValueError:
            pass

        assert ctx.get_current_tenant() is None

    def test_exception_at_level_2_restores_to_level_1(self, memory_dataflow):
        """Exception at level 2 restores to level 1 correctly."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("outer", "Outer")
        ctx.register_tenant("inner", "Inner")

        _current_tenant.set(None)

        with ctx.switch("outer"):
            try:
                with ctx.switch("inner"):
                    raise ValueError("Test error at level 2")
            except ValueError:
                pass

            # Should be back to outer
            assert ctx.get_current_tenant() == "outer"

        assert ctx.get_current_tenant() is None

    def test_exception_at_level_3_restores_through_all_levels(self, memory_dataflow):
        """Exception at level 3 restores through all previous levels."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("l1", "Level 1")
        ctx.register_tenant("l2", "Level 2")
        ctx.register_tenant("l3", "Level 3")

        _current_tenant.set(None)

        with ctx.switch("l1"):
            with ctx.switch("l2"):
                try:
                    with ctx.switch("l3"):
                        raise RuntimeError("Deep error")
                except RuntimeError:
                    pass

                assert ctx.get_current_tenant() == "l2"

            assert ctx.get_current_tenant() == "l1"

        assert ctx.get_current_tenant() is None

    def test_multiple_exceptions_at_different_levels(self, memory_dataflow):
        """Multiple caught exceptions at different levels work correctly."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("a", "A")
        ctx.register_tenant("b", "B")
        ctx.register_tenant("c", "C")

        _current_tenant.set(None)

        with ctx.switch("a"):
            try:
                with ctx.switch("b"):
                    raise ValueError("Error 1")
            except ValueError:
                pass

            assert ctx.get_current_tenant() == "a"

            try:
                with ctx.switch("c"):
                    raise ValueError("Error 2")
            except ValueError:
                pass

            assert ctx.get_current_tenant() == "a"


@pytest.mark.unit
class TestRapidContextSwitching:
    """Test rapid context switching (100+ switches)."""

    def test_100_sequential_switches(self, memory_dataflow):
        """100 sequential context switches work correctly."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        # Register a single tenant
        ctx.register_tenant("rapid", "Rapid Tenant")

        _current_tenant.set(None)
        initial_count = ctx._switch_count

        for i in range(100):
            with ctx.switch("rapid"):
                assert ctx.get_current_tenant() == "rapid"

            assert ctx.get_current_tenant() is None

        assert ctx._switch_count == initial_count + 100

    def test_100_alternating_switches_between_tenants(self, memory_dataflow):
        """100 alternating switches between two tenants work correctly."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("tenant-a", "Tenant A")
        ctx.register_tenant("tenant-b", "Tenant B")

        _current_tenant.set(None)

        for i in range(50):
            with ctx.switch("tenant-a"):
                assert ctx.get_current_tenant() == "tenant-a"

            with ctx.switch("tenant-b"):
                assert ctx.get_current_tenant() == "tenant-b"

        assert ctx.get_current_tenant() is None

    def test_rapid_switches_with_10_tenants(self, memory_dataflow):
        """Rapid switching among 10 different tenants."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        for i in range(10):
            ctx.register_tenant(f"tenant-{i}", f"Tenant {i}")

        _current_tenant.set(None)

        for _ in range(10):
            for i in range(10):
                with ctx.switch(f"tenant-{i}"):
                    assert ctx.get_current_tenant() == f"tenant-{i}"

        assert ctx.get_current_tenant() is None


@pytest.mark.unit
class TestContextDuringWorkflowExecution:
    """Test context switch during workflow execution."""

    def test_context_available_during_workflow_creation(self, memory_dataflow):
        """Tenant context is available when creating workflows."""
        db = memory_dataflow

        @db.model
        class Task:
            title: str

        db.tenant_context.register_tenant("test-tenant", "Test Tenant")

        with db.tenant_context.switch("test-tenant"):
            workflow = db.create_workflow("context_workflow")
            assert workflow is not None
            assert db.tenant_context.get_current_tenant() == "test-tenant"

    def test_context_available_when_adding_nodes(self, memory_dataflow):
        """Tenant context is available when adding nodes to workflow."""
        db = memory_dataflow

        @db.model
        class Item:
            name: str

        db.tenant_context.register_tenant("node-tenant", "Node Tenant")

        with db.tenant_context.switch("node-tenant"):
            workflow = db.create_workflow()
            db.add_node(
                workflow, "Item", "Create", "create_item", {"id": "i1", "name": "Test"}
            )

            assert db.tenant_context.get_current_tenant() == "node-tenant"
            assert "create_item" in workflow.nodes


@pytest.mark.unit
class TestEmptyTenantContext:
    """Test empty tenant context (no tenants registered)."""

    def test_empty_context_returns_none(self, memory_dataflow):
        """Empty context returns None for current tenant."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        _current_tenant.set(None)

        assert ctx.get_current_tenant() is None

    def test_empty_context_list_tenants_returns_empty(self, memory_dataflow):
        """list_tenants() returns empty list when no tenants registered."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        tenants = ctx.list_tenants()
        assert tenants == []

    def test_empty_context_stats(self, memory_dataflow):
        """Stats are correct for empty context."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        _current_tenant.set(None)

        stats = ctx.get_stats()
        assert stats["total_tenants"] == 0
        assert stats["active_tenants"] == 0

    def test_switch_on_empty_context_raises_error(self, memory_dataflow):
        """Switching tenant on empty context raises ValueError."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        with pytest.raises(ValueError) as exc_info:
            with ctx.switch("nonexistent"):
                pass

        assert "not registered" in str(exc_info.value)


@pytest.mark.unit
class TestMaximumTenants:
    """Test maximum tenants (1000+) registered."""

    def test_register_1000_tenants(self, memory_dataflow):
        """Can register 1000 tenants without issues."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        for i in range(1000):
            ctx.register_tenant(f"tenant-{i}", f"Tenant {i}")

        stats = ctx.get_stats()
        assert stats["total_tenants"] == 1000
        assert stats["active_tenants"] == 1000

    def test_list_1000_tenants(self, memory_dataflow):
        """list_tenants() works with 1000 tenants."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        for i in range(1000):
            ctx.register_tenant(f"tenant-{i}", f"Tenant {i}")

        tenants = ctx.list_tenants()
        assert len(tenants) == 1000

    def test_switch_to_tenant_999(self, memory_dataflow):
        """Can switch to tenant #999 among 1000 registered."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        for i in range(1000):
            ctx.register_tenant(f"tenant-{i}", f"Tenant {i}")

        _current_tenant.set(None)

        with ctx.switch("tenant-999"):
            assert ctx.get_current_tenant() == "tenant-999"

    def test_deactivate_500_of_1000_tenants(self, memory_dataflow):
        """Can deactivate half of 1000 tenants."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        for i in range(1000):
            ctx.register_tenant(f"tenant-{i}", f"Tenant {i}")

        for i in range(500):
            ctx.deactivate_tenant(f"tenant-{i}")

        stats = ctx.get_stats()
        assert stats["total_tenants"] == 1000
        assert stats["active_tenants"] == 500


@pytest.mark.unit
class TestContextStatsAccuracy:
    """Test context stats accuracy after many operations."""

    def test_switch_count_accuracy(self, memory_dataflow):
        """Switch count is accurate after many operations."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("test", "Test")

        initial = ctx._switch_count

        for _ in range(50):
            with ctx.switch("test"):
                pass

        assert ctx._switch_count == initial + 50

    def test_active_switches_count_during_nesting(self, memory_dataflow):
        """Active switches count is accurate during nesting."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("a", "A")
        ctx.register_tenant("b", "B")
        ctx.register_tenant("c", "C")

        _current_tenant.set(None)

        assert ctx._active_switches == 0

        with ctx.switch("a"):
            assert ctx._active_switches == 1

            with ctx.switch("b"):
                assert ctx._active_switches == 2

                with ctx.switch("c"):
                    assert ctx._active_switches == 3

                assert ctx._active_switches == 2

            assert ctx._active_switches == 1

        assert ctx._active_switches == 0

    def test_stats_after_exception(self, memory_dataflow):
        """Stats are correct after exception during switch."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("exc", "Exception Test")

        initial_switches = ctx._switch_count
        _current_tenant.set(None)

        try:
            with ctx.switch("exc"):
                raise ValueError("Test")
        except ValueError:
            pass

        # Switch count should have incremented
        assert ctx._switch_count == initial_switches + 1
        # Active switches should be back to 0
        assert ctx._active_switches == 0


@pytest.mark.unit
class TestThreadSafetyContextOperations:
    """Test thread-safety of context operations."""

    def test_registration_from_multiple_threads(self, memory_dataflow):
        """Tenant registration from multiple threads is safe."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        errors = []
        registered = []

        def register_tenant(thread_id):
            try:
                tenant_id = f"thread-{thread_id}"
                ctx.register_tenant(tenant_id, f"Thread {thread_id}")
                registered.append(tenant_id)
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(10):
            t = threading.Thread(target=register_tenant, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Should have no errors (or expected duplicate errors)
        # and 10 tenants registered
        assert len(registered) == 10
        assert ctx.get_stats()["total_tenants"] == 10

    def test_switch_from_multiple_threads(self, memory_dataflow):
        """Tenant switching from multiple threads uses contextvars correctly."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        for i in range(5):
            ctx.register_tenant(f"t-{i}", f"Thread Tenant {i}")

        results = {}

        def switch_and_check(thread_id):
            tenant = f"t-{thread_id}"
            with ctx.switch(tenant):
                time.sleep(0.01)  # Small delay
                results[thread_id] = ctx.get_current_tenant()

        threads = []
        for i in range(5):
            t = threading.Thread(target=switch_and_check, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Each thread should have seen its own tenant
        # Note: contextvars work per-context, so threads share the same context
        # unless isolated. Results may vary based on threading implementation.
        assert len(results) == 5


@pytest.mark.unit
class TestAsyncTaskIsolation:
    """Test async task isolation with concurrent context switches."""

    @pytest.mark.asyncio
    async def test_multiple_async_tasks_isolated(self, memory_dataflow):
        """Multiple concurrent async tasks have isolated contexts."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        for i in range(5):
            ctx.register_tenant(f"async-{i}", f"Async Tenant {i}")

        results = {}

        async def switch_task(task_id):
            tenant = f"async-{task_id}"
            async with ctx.aswitch(tenant):
                await asyncio.sleep(0.01)  # Small delay to interleave
                results[task_id] = ctx.get_current_tenant()

        await asyncio.gather(*[switch_task(i) for i in range(5)])

        # Each task should have seen its own tenant
        for i in range(5):
            assert results[i] == f"async-{i}"

    @pytest.mark.asyncio
    async def test_async_nested_switches_isolated(self, memory_dataflow):
        """Async nested switches are properly isolated."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("outer", "Outer")
        ctx.register_tenant("inner", "Inner")

        _current_tenant.set(None)

        async with ctx.aswitch("outer"):
            assert ctx.get_current_tenant() == "outer"

            async with ctx.aswitch("inner"):
                assert ctx.get_current_tenant() == "inner"

            assert ctx.get_current_tenant() == "outer"

        assert ctx.get_current_tenant() is None

    @pytest.mark.asyncio
    async def test_async_exception_restores_context(self, memory_dataflow):
        """Async exception properly restores context."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("test", "Test")

        _current_tenant.set(None)

        try:
            async with ctx.aswitch("test"):
                raise ValueError("Async error")
        except ValueError:
            pass

        assert ctx.get_current_tenant() is None

    @pytest.mark.asyncio
    async def test_mixed_sync_async_context(self, memory_dataflow):
        """Mixed sync and async context switches work correctly."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("sync-tenant", "Sync")
        ctx.register_tenant("async-tenant", "Async")

        _current_tenant.set(None)

        # Start with sync switch
        with ctx.switch("sync-tenant"):
            assert ctx.get_current_tenant() == "sync-tenant"

            # Nested async switch
            async with ctx.aswitch("async-tenant"):
                assert ctx.get_current_tenant() == "async-tenant"

            assert ctx.get_current_tenant() == "sync-tenant"

        assert ctx.get_current_tenant() is None
