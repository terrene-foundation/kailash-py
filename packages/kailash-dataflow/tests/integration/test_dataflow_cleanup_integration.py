"""Integration tests for DataFlow cleanup methods (ADR-017).

This test file covers:
1. cleanup_stale_pools() with real database operations
2. cleanup_all_pools() with real database operations
3. get_cleanup_metrics() with real pools
4. Pool lifecycle across multiple operations
5. Sequential test isolation

Test Strategy:
- Tier 2 (Integration): Real database (SQLite), NO MOCKING
- Tests actual pool creation and cleanup
- Verifies cleanup doesn't interfere with operations
- Tests written BEFORE implementation (TDD)
"""

import pytest
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow


@pytest.fixture(scope="function")
async def db_with_cleanup():
    """Function-scoped database fixture with cleanup.

    This fixture demonstrates the recommended pattern from ADR-017.
    """
    db = DataFlow(":memory:", test_mode=True, test_mode_aggressive_cleanup=True)

    yield db

    # Cleanup after test
    metrics = await db.cleanup_all_pools()
    assert (
        metrics["cleanup_failures"] == 0
    ), f"Pool cleanup failed: {metrics['cleanup_errors']}"


@pytest.mark.asyncio
class TestDataFlowCleanupIntegration:
    """Integration tests for cleanup methods with real database."""

    async def test_cleanup_stale_pools_with_real_operations(self, db_with_cleanup):
        """Test cleanup_stale_pools() after real database operations."""
        db = db_with_cleanup

        # Define model
        @db.model
        class User:
            id: str
            name: str

        # Perform some operations
        workflow = WorkflowBuilder()
        workflow.add_node("UserCreateNode", "create", {"id": "user-1", "name": "Alice"})

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

        assert results["create"]["name"] == "Alice"

        # Check for stale pools
        metrics = await db.cleanup_stale_pools()

        # Should have valid metrics
        assert "stale_pools_found" in metrics
        assert "cleanup_duration_ms" in metrics
        assert metrics["cleanup_failures"] == 0

    async def test_cleanup_all_pools_with_real_operations(self, db_with_cleanup):
        """Test cleanup_all_pools() after real database operations."""
        db = db_with_cleanup

        # Define model
        @db.model
        class Product:
            id: str
            name: str
            price: float

        # Perform operations
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ProductCreateNode",
            "create",
            {"id": "prod-1", "name": "Widget", "price": 99.99},
        )

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

        assert results["create"]["price"] == 99.99

        # Get initial metrics
        initial_metrics = db.get_cleanup_metrics()
        initial_pools = initial_metrics["active_pools"]

        # Cleanup all pools
        cleanup_metrics = await db.cleanup_all_pools()

        # Should have cleaned pools
        assert cleanup_metrics["cleanup_failures"] == 0
        assert len(cleanup_metrics["cleanup_errors"]) == 0

        # Verify pools were cleaned
        final_metrics = db.get_cleanup_metrics()
        assert final_metrics["active_pools"] <= initial_pools

    async def test_get_cleanup_metrics_with_real_pools(self, db_with_cleanup):
        """Test get_cleanup_metrics() reports real pool state."""
        db = db_with_cleanup

        # Get metrics before any operations
        initial_metrics = db.get_cleanup_metrics()
        assert initial_metrics["test_mode_enabled"] is True
        assert initial_metrics["aggressive_cleanup_enabled"] is True

        # Define model and perform operation
        @db.model
        class Order:
            id: str
            total: float

        workflow = WorkflowBuilder()
        workflow.add_node(
            "OrderCreateNode", "create", {"id": "order-1", "total": 150.00}
        )

        runtime = AsyncLocalRuntime()
        await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Get metrics after operations
        final_metrics = db.get_cleanup_metrics()

        # Should report pool state
        assert "active_pools" in final_metrics
        assert "total_pools_created" in final_metrics
        assert isinstance(final_metrics["pool_keys"], list)


@pytest.mark.asyncio
class TestDataFlowSequentialIsolation:
    """Test sequential test isolation with cleanup."""

    async def test_sequential_1_create_data(self, db_with_cleanup):
        """Test 1: Create data in isolated environment."""
        db = db_with_cleanup

        @db.model
        class Session:
            id: str
            user_id: str

        workflow = WorkflowBuilder()
        workflow.add_node(
            "SessionCreateNode",
            "create",
            {"id": "session-seq-1", "user_id": "user-123"},
        )

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

        assert results["create"]["id"] == "session-seq-1"

    async def test_sequential_2_independent_data(self, db_with_cleanup):
        """Test 2: Should have independent environment from test 1."""
        db = db_with_cleanup

        @db.model
        class Session:
            id: str
            user_id: str

        # Create different data - should not conflict with test 1
        workflow = WorkflowBuilder()
        workflow.add_node(
            "SessionCreateNode",
            "create",
            {"id": "session-seq-2", "user_id": "user-456"},
        )

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

        assert results["create"]["id"] == "session-seq-2"


@pytest.mark.asyncio
class TestDataFlowPoolLifecycle:
    """Test pool lifecycle across multiple operations."""

    async def test_pool_reuse_within_test(self, db_with_cleanup):
        """Test pools are reused within same test."""
        db = db_with_cleanup

        @db.model
        class Item:
            id: str
            name: str

        # Get initial metrics
        initial_metrics = db.get_cleanup_metrics()
        initial_pools = initial_metrics["active_pools"]

        # Perform multiple operations
        runtime = AsyncLocalRuntime()

        for i in range(5):
            workflow = WorkflowBuilder()
            workflow.add_node(
                "ItemCreateNode",
                f"create_{i}",
                {"id": f"item-{i}", "name": f"Item {i}"},
            )

            await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Get final metrics
        final_metrics = db.get_cleanup_metrics()

        # Pools should not grow unbounded
        assert final_metrics["active_pools"] <= initial_pools + 5

    async def test_cleanup_doesnt_break_subsequent_operations(self, db_with_cleanup):
        """Test cleanup doesn't break subsequent database operations."""
        db = db_with_cleanup

        @db.model
        class Task:
            id: str
            title: str

        # Perform operation
        workflow1 = WorkflowBuilder()
        workflow1.add_node(
            "TaskCreateNode", "create1", {"id": "task-1", "title": "First Task"}
        )

        runtime = AsyncLocalRuntime()
        results1, _ = await runtime.execute_workflow_async(workflow1.build(), inputs={})
        assert results1["create1"]["title"] == "First Task"

        # Cleanup stale pools
        await db.cleanup_stale_pools()

        # Subsequent operation should still work
        workflow2 = WorkflowBuilder()
        workflow2.add_node(
            "TaskCreateNode", "create2", {"id": "task-2", "title": "Second Task"}
        )

        results2, _ = await runtime.execute_workflow_async(workflow2.build(), inputs={})
        assert results2["create2"]["title"] == "Second Task"


@pytest.mark.asyncio
class TestDataFlowCleanupMetrics:
    """Test cleanup metrics accuracy."""

    async def test_cleanup_metrics_track_operations(self, db_with_cleanup):
        """Test cleanup metrics accurately track operations."""
        db = db_with_cleanup

        @db.model
        class Record:
            id: str
            value: str

        # Get initial state
        initial_metrics = db.get_cleanup_metrics()
        initial_pools = initial_metrics["active_pools"]

        # Perform operations
        workflow = WorkflowBuilder()
        workflow.add_node(
            "RecordCreateNode", "create", {"id": "rec-1", "value": "test"}
        )

        runtime = AsyncLocalRuntime()
        await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Check metrics changed
        mid_metrics = db.get_cleanup_metrics()
        # Pools may have been created
        assert mid_metrics["active_pools"] >= initial_pools

        # Cleanup
        cleanup_result = await db.cleanup_all_pools()

        # Verify cleanup metrics
        assert cleanup_result["total_pools"] >= 0
        assert cleanup_result["pools_cleaned"] >= 0
        assert cleanup_result["cleanup_failures"] == 0

    async def test_cleanup_duration_is_reasonable(self, db_with_cleanup):
        """Test cleanup operations complete in reasonable time."""
        db = db_with_cleanup

        # Cleanup should be fast (<100ms typically)
        metrics = await db.cleanup_stale_pools()

        # Duration should be reasonable
        assert metrics["cleanup_duration_ms"] < 1000  # Less than 1 second

    async def test_cleanup_errors_are_reported(self, db_with_cleanup):
        """Test cleanup errors are properly reported in metrics."""
        db = db_with_cleanup

        # Normal cleanup should have no errors
        metrics = await db.cleanup_all_pools()

        # Should report no errors
        assert len(metrics["cleanup_errors"]) == 0
        assert metrics["cleanup_failures"] == 0


@pytest.mark.asyncio
class TestDataFlowCleanupGracefulDegradation:
    """Test graceful error handling in real scenarios."""

    async def test_cleanup_handles_empty_pools(self, db_with_cleanup):
        """Test cleanup handles case of no pools gracefully."""
        db = db_with_cleanup

        # Cleanup when no pools exist
        metrics = await db.cleanup_all_pools()

        # Should succeed
        assert metrics["cleanup_failures"] == 0
        assert metrics["total_pools"] >= 0

    async def test_multiple_cleanups_are_safe(self, db_with_cleanup):
        """Test multiple cleanup calls are safe."""
        db = db_with_cleanup

        # Multiple cleanups should be safe
        await db.cleanup_all_pools()
        await db.cleanup_all_pools()
        await db.cleanup_stale_pools()
        await db.cleanup_stale_pools()

        # Should not cause issues
        assert True


@pytest.mark.asyncio
class TestDataFlowTestModeIntegration:
    """Test test mode integration with real workflows."""

    async def test_test_mode_doesnt_affect_operations(self):
        """Test test_mode=True doesn't affect normal operations."""
        db_test = DataFlow(":memory:", test_mode=True)

        @db_test.model
        class Data:
            id: str
            value: str

        workflow = WorkflowBuilder()
        workflow.add_node("DataCreateNode", "create", {"id": "data-1", "value": "test"})

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Should work normally
        assert results["create"]["value"] == "test"

        # Cleanup
        await db_test.cleanup_all_pools()

    async def test_production_mode_still_works(self):
        """Test test_mode=False (production mode) still works."""
        db_prod = DataFlow(":memory:", test_mode=False)

        @db_prod.model
        class Data:
            id: str
            value: str

        workflow = WorkflowBuilder()
        workflow.add_node(
            "DataCreateNode", "create", {"id": "data-1", "value": "production"}
        )

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Should work normally
        assert results["create"]["value"] == "production"

        # Cleanup methods should still exist
        await db_prod.cleanup_all_pools()
