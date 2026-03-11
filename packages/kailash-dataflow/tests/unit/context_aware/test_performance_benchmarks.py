#!/usr/bin/env python3
"""
Unit Tests for Performance Benchmarks (TODO-156)

Performance benchmarks for context-aware features:
- Tenant registration overhead (1000 tenants)
- Context switch latency (avg over 1000 switches)
- Context propagation through nested switches
- DataFlow initialization with tenant context
- Workflow creation with context binding
- Concurrent context switches
- Memory usage with many registered tenants
- Stats collection overhead

Uses SQLite in-memory databases following Tier 1 testing guidelines.
Uses time.time() with generous thresholds (10s+) to avoid flaky tests.
"""

import asyncio
import time

import pytest

from dataflow import DataFlow
from dataflow.core.tenant_context import TenantContextSwitch, _current_tenant


@pytest.mark.unit
class TestTenantRegistrationOverhead:
    """Test tenant registration performance."""

    def test_register_1000_tenants_under_10_seconds(self, memory_dataflow):
        """Registering 1000 tenants completes in under 10 seconds."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        start = time.time()

        for i in range(1000):
            ctx.register_tenant(f"perf-tenant-{i}", f"Performance Tenant {i}")

        elapsed = time.time() - start

        assert elapsed < 10.0, f"Registration took {elapsed:.2f}s, expected < 10s"
        assert ctx.get_stats()["total_tenants"] == 1000

    def test_register_with_metadata_overhead(self, memory_dataflow):
        """Registering tenants with metadata has acceptable overhead."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        start = time.time()

        for i in range(500):
            metadata = {
                "plan": "enterprise",
                "region": "us-east-1",
                "features": ["feature1", "feature2", "feature3"],
                "config": {"key1": "value1", "key2": "value2"},
            }
            ctx.register_tenant(
                f"meta-tenant-{i}", f"Meta Tenant {i}", metadata=metadata
            )

        elapsed = time.time() - start

        assert elapsed < 10.0, f"Registration with metadata took {elapsed:.2f}s"
        assert ctx.get_stats()["total_tenants"] == 500


@pytest.mark.unit
class TestContextSwitchLatency:
    """Test context switch latency."""

    def test_1000_switches_avg_latency(self, memory_dataflow):
        """Average latency for 1000 context switches is acceptable."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("latency-test", "Latency Test")

        _current_tenant.set(None)

        start = time.time()

        for _ in range(1000):
            with ctx.switch("latency-test"):
                pass  # Minimal work inside switch

        elapsed = time.time() - start
        avg_latency_ms = (elapsed / 1000) * 1000  # Convert to milliseconds

        assert elapsed < 10.0, f"1000 switches took {elapsed:.2f}s, expected < 10s"
        # Log average latency for reference (not failing assertion)
        assert (
            avg_latency_ms < 100
        ), f"Avg latency {avg_latency_ms:.3f}ms seems too high"

    def test_switch_latency_consistent(self, memory_dataflow):
        """Switch latency is consistent across iterations."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("consistent", "Consistent")

        _current_tenant.set(None)
        latencies = []

        for _ in range(100):
            start = time.time()
            with ctx.switch("consistent"):
                pass
            latencies.append(time.time() - start)

        # Calculate variance (should be low for consistent performance)
        avg = sum(latencies) / len(latencies)
        variance = sum((lat - avg) ** 2 for lat in latencies) / len(latencies)

        # Variance should be low (no random spikes)
        assert variance < 0.01, f"High variance in switch latency: {variance}"


@pytest.mark.unit
class TestContextPropagationPerformance:
    """Test context propagation through nested switches."""

    def test_deep_nesting_performance(self, memory_dataflow):
        """Deep nesting (10 levels) has acceptable performance."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        for i in range(10):
            ctx.register_tenant(f"nest-{i}", f"Nested {i}")

        _current_tenant.set(None)

        def nested_switch(level):
            if level >= 10:
                return
            with ctx.switch(f"nest-{level}"):
                nested_switch(level + 1)

        start = time.time()

        for _ in range(100):
            nested_switch(0)

        elapsed = time.time() - start

        assert elapsed < 10.0, f"Deep nesting took {elapsed:.2f}s"

    def test_rapid_nested_alternation(self, memory_dataflow):
        """Rapidly alternating between nested levels is performant."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("outer", "Outer")
        ctx.register_tenant("inner", "Inner")

        _current_tenant.set(None)

        start = time.time()

        for _ in range(500):
            with ctx.switch("outer"):
                with ctx.switch("inner"):
                    pass

        elapsed = time.time() - start

        assert elapsed < 10.0, f"Nested alternation took {elapsed:.2f}s"


@pytest.mark.unit
class TestDataFlowInitializationPerformance:
    """Test DataFlow initialization with tenant context."""

    def test_dataflow_init_with_multi_tenant_flag(self):
        """DataFlow initialization with multi_tenant=True is fast."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
            start = time.time()

            db = DataFlow(f"sqlite:///{tmp.name}", multi_tenant=True)

            elapsed = time.time() - start

            try:
                assert elapsed < 10.0, f"Init took {elapsed:.2f}s"
                assert db.tenant_context is not None
            finally:
                db.close()

    def test_tenant_context_access_after_init(self):
        """Accessing tenant_context after init is fast."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
            db = DataFlow(f"sqlite:///{tmp.name}", multi_tenant=True)

            try:
                start = time.time()

                for _ in range(1000):
                    _ = db.tenant_context

                elapsed = time.time() - start

                assert elapsed < 10.0, f"1000 accesses took {elapsed:.2f}s"
            finally:
                db.close()


@pytest.mark.unit
class TestWorkflowCreationPerformance:
    """Test workflow creation with context binding."""

    def test_workflow_creation_overhead(self, memory_dataflow):
        """Workflow creation with tenant context has minimal overhead."""
        db = memory_dataflow

        @db.model
        class Item:
            name: str

        db.tenant_context.register_tenant("wf-tenant", "Workflow Tenant")

        start = time.time()

        with db.tenant_context.switch("wf-tenant"):
            for i in range(100):
                wf = db.create_workflow(f"workflow-{i}")
                assert wf is not None

        elapsed = time.time() - start

        assert elapsed < 10.0, f"100 workflow creations took {elapsed:.2f}s"

    def test_node_addition_with_context(self, memory_dataflow):
        """Adding nodes with active tenant context is performant."""
        db = memory_dataflow

        @db.model
        class Task:
            title: str

        db.tenant_context.register_tenant("node-tenant", "Node Tenant")

        start = time.time()

        with db.tenant_context.switch("node-tenant"):
            for i in range(100):
                wf = db.create_workflow()
                db.add_node(
                    wf,
                    "Task",
                    "Create",
                    f"create-{i}",
                    {"id": f"t-{i}", "title": f"Task {i}"},
                )

        elapsed = time.time() - start

        assert elapsed < 10.0, f"100 node additions took {elapsed:.2f}s"


@pytest.mark.unit
class TestConcurrentContextSwitchPerformance:
    """Test concurrent context switch performance."""

    @pytest.mark.asyncio
    async def test_concurrent_async_switches(self, memory_dataflow):
        """Concurrent async switches are performant."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        for i in range(10):
            ctx.register_tenant(f"concurrent-{i}", f"Concurrent {i}")

        async def switch_task(tenant_id):
            for _ in range(100):
                async with ctx.aswitch(tenant_id):
                    await asyncio.sleep(0)  # Yield control

        start = time.time()

        await asyncio.gather(*[switch_task(f"concurrent-{i}") for i in range(10)])

        elapsed = time.time() - start

        assert elapsed < 10.0, f"Concurrent switches took {elapsed:.2f}s"

    @pytest.mark.asyncio
    async def test_high_concurrency_isolation(self, memory_dataflow):
        """High concurrency maintains proper isolation."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        for i in range(50):
            ctx.register_tenant(f"iso-{i}", f"Isolation {i}")

        results = {}
        errors = []

        async def isolation_check(task_id):
            tenant = f"iso-{task_id}"
            try:
                async with ctx.aswitch(tenant):
                    await asyncio.sleep(0.001)  # Small delay
                    results[task_id] = ctx.get_current_tenant()
            except Exception as e:
                errors.append(e)

        start = time.time()

        await asyncio.gather(*[isolation_check(i) for i in range(50)])

        elapsed = time.time() - start

        assert elapsed < 10.0, f"High concurrency took {elapsed:.2f}s"
        assert len(errors) == 0
        assert len(results) == 50
        for i in range(50):
            assert results[i] == f"iso-{i}"


@pytest.mark.unit
class TestMemoryUsageWithManyTenants:
    """Test memory usage with many registered tenants."""

    def test_1000_tenants_memory_usage(self, memory_dataflow):
        """Memory usage with 1000 tenants is reasonable."""
        import sys

        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        # Get baseline size
        initial_size = sys.getsizeof(ctx._tenants)

        for i in range(1000):
            ctx.register_tenant(f"mem-{i}", f"Memory Test {i}")

        final_size = sys.getsizeof(ctx._tenants)
        growth = final_size - initial_size

        # Size should grow, but not excessively
        # This is a sanity check, not a strict memory limit
        assert ctx.get_stats()["total_tenants"] == 1000

        # Each TenantInfo should be relatively small
        # Just verify the test completes (no memory errors)
        assert growth >= 0

    def test_tenant_with_large_metadata(self, memory_dataflow):
        """Tenants with large metadata don't cause issues."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        # Create large metadata
        large_metadata = {f"key-{i}": f"value-{i}" * 100 for i in range(100)}

        start = time.time()

        for i in range(100):
            ctx.register_tenant(
                f"large-{i}", f"Large {i}", metadata=large_metadata.copy()
            )

        elapsed = time.time() - start

        assert elapsed < 10.0, f"Large metadata registration took {elapsed:.2f}s"
        assert ctx.get_stats()["total_tenants"] == 100


@pytest.mark.unit
class TestStatsCollectionOverhead:
    """Test stats collection overhead."""

    def test_stats_collection_overhead(self, memory_dataflow):
        """Stats collection has minimal overhead."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        for i in range(100):
            ctx.register_tenant(f"stats-{i}", f"Stats {i}")

        start = time.time()

        for _ in range(10000):
            _ = ctx.get_stats()

        elapsed = time.time() - start

        assert elapsed < 10.0, f"10000 stats collections took {elapsed:.2f}s"

    def test_stats_during_active_switches(self, memory_dataflow):
        """Stats collection during active switches is fast."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        ctx.register_tenant("active", "Active")

        _current_tenant.set(None)

        start = time.time()

        with ctx.switch("active"):
            for _ in range(10000):
                stats = ctx.get_stats()
                assert stats["active_switches"] >= 1

        elapsed = time.time() - start

        assert elapsed < 10.0, f"Stats during switches took {elapsed:.2f}s"

    def test_is_tenant_registered_performance(self, memory_dataflow):
        """is_tenant_registered() check is fast with many tenants."""
        db = memory_dataflow
        ctx = TenantContextSwitch(db)

        for i in range(1000):
            ctx.register_tenant(f"check-{i}", f"Check {i}")

        start = time.time()

        for _ in range(10000):
            # Check various tenant IDs
            _ = ctx.is_tenant_registered("check-500")
            _ = ctx.is_tenant_registered("nonexistent")
            _ = ctx.is_tenant_registered("check-999")

        elapsed = time.time() - start

        assert elapsed < 10.0, f"30000 checks took {elapsed:.2f}s"
