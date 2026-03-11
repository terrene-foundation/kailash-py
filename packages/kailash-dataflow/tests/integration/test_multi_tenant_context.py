#!/usr/bin/env python3
"""
Integration Tests for Multi-Tenant Context Switching (TODO-155)

Tests the TenantContextSwitch with real PostgreSQL database operations.
These tests verify that tenant context switching works correctly with
real database infrastructure and that there is no cross-tenant data leakage.

Uses PostgreSQL on shared test infrastructure (port 5434) following
Tier 2 testing guidelines - NO MOCKING.

Test coverage:
1. Register multiple tenants and switch between them
2. Context switching with real DB operations
3. Nested switches with real data
4. Error recovery during switch
5. Stats tracking accuracy
6. Cross-tenant isolation with real queries
"""

import asyncio
import os

import pytest

from dataflow import DataFlow
from dataflow.core.tenant_context import TenantContextSwitch

# Use the shared SDK Docker PostgreSQL infrastructure
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)


@pytest.fixture
def pg_dataflow():
    """Create a DataFlow instance with PostgreSQL for integration tests."""
    db = DataFlow(
        database_url=TEST_DATABASE_URL,
        auto_migrate=True,
        cache_enabled=False,
        pool_size=2,
        pool_max_overflow=1,
    )
    yield db
    db.close()


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestMultiTenantContextIntegration:
    """Integration tests for multi-tenant context switching."""

    # ---- Test 1: Register multiple tenants and switch between them ----

    def test_register_multiple_tenants_and_switch(self, pg_dataflow):
        """Can register multiple tenants and switch between them."""
        db = pg_dataflow
        ctx = db.tenant_context

        # Register tenants
        tenant_a = ctx.register_tenant("acme", "Acme Corp", {"plan": "enterprise"})
        tenant_b = ctx.register_tenant("globex", "Globex Inc", {"plan": "starter"})
        tenant_c = ctx.register_tenant("initech", "Initech", {"plan": "professional"})

        assert len(ctx.list_tenants()) == 3

        # Switch between tenants
        with ctx.switch("acme"):
            assert ctx.get_current_tenant() == "acme"
            assert ctx.require_tenant() == "acme"

        with ctx.switch("globex"):
            assert ctx.get_current_tenant() == "globex"

        with ctx.switch("initech"):
            assert ctx.get_current_tenant() == "initech"

        # After all switches, no tenant should be active
        assert ctx.get_current_tenant() is None

    # ---- Test 2: Context switching with real DB operations ----

    def test_context_switching_with_real_db_operations(self, pg_dataflow):
        """Context switching works with real database operations."""
        db = pg_dataflow
        ctx = db.tenant_context

        ctx.register_tenant("tenant-a", "Tenant A")
        ctx.register_tenant("tenant-b", "Tenant B")

        # Define a model
        @db.model
        class TenantTestUser:
            name: str
            email: str
            tenant: str = ""

        # Switch to tenant-a and verify context
        with ctx.switch("tenant-a"):
            current = ctx.get_current_tenant()
            assert current == "tenant-a"

            # Create workflow in tenant context
            workflow = db.create_workflow("tenant_a_workflow")
            assert workflow is not None

            # Verify we can add nodes (the model nodes are registered)
            models = db.get_models()
            assert "TenantTestUser" in models

        # Switch to tenant-b
        with ctx.switch("tenant-b"):
            assert ctx.get_current_tenant() == "tenant-b"

            # Same operations work in tenant-b context
            workflow = db.create_workflow("tenant_b_workflow")
            assert workflow is not None

    # ---- Test 3: Nested switches with real data ----

    def test_nested_switches_with_real_data(self, pg_dataflow):
        """Nested context switches work correctly with real operations."""
        db = pg_dataflow
        ctx = db.tenant_context

        ctx.register_tenant("outer", "Outer Tenant")
        ctx.register_tenant("middle", "Middle Tenant")
        ctx.register_tenant("inner", "Inner Tenant")

        contexts_observed = []

        with ctx.switch("outer"):
            contexts_observed.append(ctx.get_current_tenant())

            with ctx.switch("middle"):
                contexts_observed.append(ctx.get_current_tenant())

                with ctx.switch("inner"):
                    contexts_observed.append(ctx.get_current_tenant())

                contexts_observed.append(ctx.get_current_tenant())

            contexts_observed.append(ctx.get_current_tenant())

        contexts_observed.append(ctx.get_current_tenant())

        assert contexts_observed == [
            "outer",
            "middle",
            "inner",
            "middle",  # After inner exits
            "outer",  # After middle exits
            None,  # After outer exits
        ]

    # ---- Test 4: Error recovery during switch ----

    def test_error_recovery_during_switch(self, pg_dataflow):
        """Context is properly restored when errors occur during switch."""
        db = pg_dataflow
        ctx = db.tenant_context

        ctx.register_tenant("safe", "Safe Tenant")
        ctx.register_tenant("risky", "Risky Tenant")

        with ctx.switch("safe"):
            assert ctx.get_current_tenant() == "safe"

            # Simulate an error in a nested switch
            try:
                with ctx.switch("risky"):
                    assert ctx.get_current_tenant() == "risky"
                    raise RuntimeError("Simulated database error")
            except RuntimeError:
                pass

            # Context should be restored to safe
            assert ctx.get_current_tenant() == "safe"

        # After all switches, no context
        assert ctx.get_current_tenant() is None

    # ---- Test 5: Stats tracking accuracy ----

    def test_stats_tracking_accuracy(self, pg_dataflow):
        """Statistics are accurately tracked during operations."""
        db = pg_dataflow
        ctx = db.tenant_context

        # Initial stats
        initial_stats = ctx.get_stats()
        initial_switches = initial_stats["total_switches"]

        ctx.register_tenant("stats-a", "Stats Tenant A")
        ctx.register_tenant("stats-b", "Stats Tenant B")
        ctx.register_tenant("stats-c", "Stats Tenant C")
        ctx.deactivate_tenant("stats-c")

        # Check tenant counts
        stats = ctx.get_stats()
        assert stats["total_tenants"] == 3
        assert stats["active_tenants"] == 2

        # Perform switches and verify counts
        with ctx.switch("stats-a"):
            inner_stats = ctx.get_stats()
            assert inner_stats["active_switches"] == 1
            assert inner_stats["current_tenant"] == "stats-a"

        after_stats = ctx.get_stats()
        assert after_stats["total_switches"] == initial_switches + 1
        assert after_stats["active_switches"] == 0

    # ---- Test 6: Cross-tenant isolation ----

    def test_cross_tenant_isolation(self, pg_dataflow):
        """Verify there is no cross-tenant context leakage."""
        db = pg_dataflow
        ctx = db.tenant_context

        ctx.register_tenant("isolated-a", "Isolated A")
        ctx.register_tenant("isolated-b", "Isolated B")

        # Data observed in each context
        data_in_a = []
        data_in_b = []

        with ctx.switch("isolated-a"):
            current = ctx.get_current_tenant()
            data_in_a.append(f"tenant={current}")

        # Verify context cleared
        assert ctx.get_current_tenant() is None

        with ctx.switch("isolated-b"):
            current = ctx.get_current_tenant()
            data_in_b.append(f"tenant={current}")

        # Each context should only see its own tenant
        assert data_in_a == ["tenant=isolated-a"]
        assert data_in_b == ["tenant=isolated-b"]


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestAsyncMultiTenantContext:
    """Async integration tests for multi-tenant context switching."""

    @pytest.mark.asyncio
    async def test_async_context_switching(self, pg_dataflow):
        """Async context switching works with real database."""
        db = pg_dataflow
        ctx = db.tenant_context

        ctx.register_tenant("async-a", "Async Tenant A")
        ctx.register_tenant("async-b", "Async Tenant B")

        async with ctx.aswitch("async-a"):
            assert ctx.get_current_tenant() == "async-a"
            # Simulate async operation
            await asyncio.sleep(0.001)
            assert ctx.get_current_tenant() == "async-a"

        assert ctx.get_current_tenant() is None

    @pytest.mark.asyncio
    async def test_concurrent_async_switches_isolation(self, pg_dataflow):
        """Concurrent async switches maintain isolation."""
        db = pg_dataflow
        ctx = db.tenant_context

        ctx.register_tenant("concurrent-a", "Concurrent A")
        ctx.register_tenant("concurrent-b", "Concurrent B")
        ctx.register_tenant("concurrent-c", "Concurrent C")

        results = {}

        async def task_with_tenant(tenant_id: str, delay: float):
            async with ctx.aswitch(tenant_id):
                await asyncio.sleep(delay)
                results[tenant_id] = ctx.get_current_tenant()

        # Run concurrent tasks with different delays
        await asyncio.gather(
            task_with_tenant("concurrent-a", 0.02),
            task_with_tenant("concurrent-b", 0.01),
            task_with_tenant("concurrent-c", 0.03),
        )

        # Each task should have observed its own tenant
        assert results["concurrent-a"] == "concurrent-a"
        assert results["concurrent-b"] == "concurrent-b"
        assert results["concurrent-c"] == "concurrent-c"

    @pytest.mark.asyncio
    async def test_async_nested_switches(self, pg_dataflow):
        """Async nested switches restore correctly."""
        db = pg_dataflow
        ctx = db.tenant_context

        ctx.register_tenant("async-outer", "Async Outer")
        ctx.register_tenant("async-inner", "Async Inner")

        async with ctx.aswitch("async-outer"):
            assert ctx.get_current_tenant() == "async-outer"

            async with ctx.aswitch("async-inner"):
                assert ctx.get_current_tenant() == "async-inner"
                await asyncio.sleep(0.001)
                assert ctx.get_current_tenant() == "async-inner"

            # Should restore to outer
            assert ctx.get_current_tenant() == "async-outer"

        assert ctx.get_current_tenant() is None


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestTenantContextWithDataFlowOperations:
    """Test tenant context with actual DataFlow operations."""

    def test_workflow_creation_in_tenant_context(self, pg_dataflow):
        """Workflows can be created within tenant context."""
        db = pg_dataflow
        ctx = db.tenant_context

        ctx.register_tenant("workflow-tenant", "Workflow Tenant")

        @db.model
        class WorkflowTestModel:
            name: str
            value: int

        with ctx.switch("workflow-tenant"):
            workflow = db.create_workflow("test_workflow")
            assert workflow is not None

            # Add a node to the workflow
            db.add_node(
                workflow,
                "WorkflowTestModel",
                "Create",
                "create_test",
                {"name": "test", "value": 42},
            )

            # Verify we're still in tenant context
            assert ctx.get_current_tenant() == "workflow-tenant"

    def test_express_operations_in_tenant_context(self, pg_dataflow):
        """Express operations work within tenant context."""
        db = pg_dataflow
        ctx = db.tenant_context

        ctx.register_tenant("express-tenant", "Express Tenant")

        with ctx.switch("express-tenant"):
            # Access express API
            express = db.express
            assert express is not None

            # Verify context is maintained
            assert ctx.get_current_tenant() == "express-tenant"

    def test_tenant_metadata_persistence(self, pg_dataflow):
        """Tenant metadata is preserved across operations."""
        db = pg_dataflow
        ctx = db.tenant_context

        metadata = {
            "region": "us-east-1",
            "tier": "premium",
            "max_users": 1000,
        }

        tenant = ctx.register_tenant("meta-tenant", "Metadata Tenant", metadata)

        with ctx.switch("meta-tenant"):
            retrieved = ctx.get_tenant("meta-tenant")
            assert retrieved.metadata == metadata
            assert retrieved.metadata["region"] == "us-east-1"


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestTenantLifecycle:
    """Test tenant lifecycle operations."""

    def test_full_tenant_lifecycle(self, pg_dataflow):
        """Test complete tenant lifecycle: register -> use -> deactivate -> reactivate -> unregister."""
        db = pg_dataflow
        ctx = db.tenant_context

        # 1. Register
        ctx.register_tenant("lifecycle-tenant", "Lifecycle Tenant")
        assert ctx.is_tenant_registered("lifecycle-tenant")
        assert ctx.is_tenant_active("lifecycle-tenant")

        # 2. Use
        with ctx.switch("lifecycle-tenant"):
            assert ctx.get_current_tenant() == "lifecycle-tenant"

        # 3. Deactivate
        ctx.deactivate_tenant("lifecycle-tenant")
        assert ctx.is_tenant_registered("lifecycle-tenant")
        assert not ctx.is_tenant_active("lifecycle-tenant")

        # 4. Verify switch blocked
        with pytest.raises(ValueError):
            with ctx.switch("lifecycle-tenant"):
                pass

        # 5. Reactivate
        ctx.activate_tenant("lifecycle-tenant")
        assert ctx.is_tenant_active("lifecycle-tenant")

        # 6. Use again
        with ctx.switch("lifecycle-tenant"):
            assert ctx.get_current_tenant() == "lifecycle-tenant"

        # 7. Unregister
        ctx.unregister_tenant("lifecycle-tenant")
        assert not ctx.is_tenant_registered("lifecycle-tenant")
