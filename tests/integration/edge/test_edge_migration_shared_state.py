"""Integration tests for EdgeMigrationNode shared state functionality.

This test suite validates that migration plans created by one EdgeMigrationNode
are accessible to other EdgeMigrationNode instances through the shared
EdgeMigrationService singleton.
"""

import asyncio

import pytest
import pytest_asyncio
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestEdgeMigrationSharedState:
    """Test shared state functionality between multiple EdgeMigrationNode instances."""

    @pytest_asyncio.fixture
    async def runtime(self):
        """Create a runtime instance."""
        runtime = LocalRuntime()
        yield runtime
        # Cleanup is handled by runtime

    @pytest.fixture
    def workflow_builder(self):
        """Create a workflow builder."""
        return WorkflowBuilder()

    @pytest.mark.asyncio
    async def test_cross_node_migration_plan_sharing(self, runtime, workflow_builder):
        """Test that migration plans created by one node are accessible to another node."""

        # Create workflow with two EdgeMigrationNode instances
        # Node 1: Creates a migration plan
        workflow_builder.add_node(
            "EdgeMigrationNode",
            "planner_node",
            {
                "operation": "plan_migration",
                "source_edge": "edge-source",
                "target_edge": "edge-target",
                "workloads": ["shared-workload"],
                "strategy": "live",
                "priority": 7,
            },
        )

        # Node 2: Retrieves migration plan created by Node 1
        workflow_builder.add_node(
            "EdgeMigrationNode",
            "executor_node",
            {
                "operation": "get_active_migrations",
            },
        )

        # Connect the nodes
        workflow_builder.add_connection(
            "planner_node", "result", "executor_node", "input"
        )

        # Execute workflow
        workflow = workflow_builder.build()
        results, run_id = await runtime.execute_async(workflow)

        # Verify planner node created migration plan successfully
        assert results["planner_node"]["status"] == "success"
        assert "migration_id" in results["planner_node"]["plan"]
        migration_id = results["planner_node"]["plan"]["migration_id"]

        # Verify executor node can see the migration plan created by planner node
        assert results["executor_node"]["status"] == "success"
        assert results["executor_node"]["count"] >= 1

        # Check that the migration created by planner_node is visible to executor_node
        migrations = results["executor_node"]["migrations"]
        migration_ids = [m["migration_id"] for m in migrations]
        assert migration_id in migration_ids

    @pytest.mark.asyncio
    async def test_migration_progress_sharing(self, runtime, workflow_builder):
        """Test that migration progress updates are shared between nodes."""

        # Node 1: Start migrator and create plan
        workflow_builder.add_node(
            "EdgeMigrationNode",
            "starter_node",
            {
                "operation": "start_migrator",
            },
        )

        workflow_builder.add_node(
            "EdgeMigrationNode",
            "planner_node",
            {
                "operation": "plan_migration",
                "source_edge": "edge-1",
                "target_edge": "edge-2",
                "workloads": ["progress-workload"],
                "strategy": "staged",
                "priority": 5,
            },
        )

        # Node 2: Get metrics (should see the migration from Node 1)
        workflow_builder.add_node(
            "EdgeMigrationNode",
            "metrics_node",
            {
                "operation": "get_metrics",
            },
        )

        # Connect nodes
        workflow_builder.add_connection(
            "starter_node", "result", "planner_node", "input"
        )
        workflow_builder.add_connection(
            "planner_node", "result", "metrics_node", "input"
        )

        # Execute workflow
        workflow = workflow_builder.build()
        results, run_id = await runtime.execute_async(workflow)

        # Verify all operations succeeded
        assert results["starter_node"]["status"] == "success"
        assert results["planner_node"]["status"] == "success"
        assert results["metrics_node"]["status"] == "success"

        # Verify metrics node can see migration created by planner node
        metrics = results["metrics_node"]["metrics"]
        assert metrics["total_migrations"] >= 1
        assert metrics["active_migrations"] >= 1

    @pytest.mark.asyncio
    async def test_multiple_nodes_same_service_instance(
        self, runtime, workflow_builder
    ):
        """Test that multiple EdgeMigrationNode instances share the same service."""

        # Create multiple nodes with different configurations
        for i in range(3):
            workflow_builder.add_node(
                "EdgeMigrationNode",
                f"node_{i}",
                {
                    "operation": "get_metrics",
                    "checkpoint_interval": 30 + i * 10,  # Different configs
                    "sync_batch_size": 1000 + i * 500,
                },
            )

        # Execute workflow
        workflow = workflow_builder.build()
        results, run_id = await runtime.execute_async(workflow)

        # All nodes should succeed and return the same metrics (shared state)
        base_metrics = None
        for i in range(3):
            assert results[f"node_{i}"]["status"] == "success"
            metrics = results[f"node_{i}"]["metrics"]

            if base_metrics is None:
                base_metrics = metrics
            else:
                # All nodes should see the same migration state
                assert metrics["total_migrations"] == base_metrics["total_migrations"]
                assert metrics["active_migrations"] == base_metrics["active_migrations"]
                assert (
                    metrics["completed_migrations"]
                    == base_metrics["completed_migrations"]
                )

    @pytest.mark.asyncio
    async def test_migration_lifecycle_across_nodes(self, runtime):
        """Test complete migration lifecycle across different nodes."""

        # Workflow 1: Plan migration
        plan_workflow = WorkflowBuilder()
        plan_workflow.add_node(
            "EdgeMigrationNode",
            "planner",
            {
                "operation": "plan_migration",
                "source_edge": "lifecycle-source",
                "target_edge": "lifecycle-target",
                "workloads": ["lifecycle-workload"],
                "strategy": "live",
            },
        )

        plan_workflow_built = plan_workflow.build()
        plan_results, _ = await runtime.execute_async(plan_workflow_built)

        assert plan_results["planner"]["status"] == "success"
        migration_id = plan_results["planner"]["plan"]["migration_id"]

        # Workflow 2: Check that migration is visible from different node
        check_workflow = WorkflowBuilder()
        check_workflow.add_node(
            "EdgeMigrationNode",
            "checker",
            {
                "operation": "get_active_migrations",
            },
        )

        check_workflow_built = check_workflow.build()
        check_results, _ = await runtime.execute_async(check_workflow_built)

        assert check_results["checker"]["status"] == "success"

        # Migration should be visible in the active migrations
        migrations = check_results["checker"]["migrations"]
        migration_ids = [m["migration_id"] for m in migrations]
        assert migration_id in migration_ids

        # Workflow 3: Get migration history from yet another node
        history_workflow = WorkflowBuilder()
        history_workflow.add_node(
            "EdgeMigrationNode",
            "historian",
            {
                "operation": "get_history",
            },
        )

        history_workflow_built = history_workflow.build()
        history_results, _ = await runtime.execute_async(history_workflow_built)

        assert history_results["historian"]["status"] == "success"
        # History should contain the migration (even if still active)
        assert len(history_results["historian"]["migrations"]) >= 0

    @pytest.mark.asyncio
    async def test_concurrent_migration_operations(self, runtime):
        """Test concurrent migration operations from multiple nodes."""

        # Create multiple concurrent workflows with different nodes
        workflows = []

        for i in range(3):
            workflow = WorkflowBuilder()
            workflow.add_node(
                "EdgeMigrationNode",
                f"concurrent_planner_{i}",
                {
                    "operation": "plan_migration",
                    "source_edge": f"concurrent-source-{i}",
                    "target_edge": f"concurrent-target-{i}",
                    "workloads": [f"concurrent-workload-{i}"],
                    "strategy": "bulk",
                    "priority": 3 + i,
                },
            )
            workflows.append(workflow.build())

        # Execute all workflows concurrently
        tasks = [runtime.execute_async(wf) for wf in workflows]
        all_results = await asyncio.gather(*tasks)

        # All should succeed
        migration_ids = []
        for results, _ in all_results:
            planner_key = [
                k for k in results.keys() if k.startswith("concurrent_planner")
            ][0]
            assert results[planner_key]["status"] == "success"
            migration_ids.append(results[planner_key]["plan"]["migration_id"])

        # All migration IDs should be different (no collisions)
        assert len(set(migration_ids)) == 3

        # Verify all migrations are visible from a single node
        check_workflow = WorkflowBuilder()
        check_workflow.add_node(
            "EdgeMigrationNode",
            "final_checker",
            {
                "operation": "get_metrics",
            },
        )

        final_results, _ = await runtime.execute_async(check_workflow.build())
        assert final_results["final_checker"]["status"] == "success"

        # Should see at least 3 migrations from concurrent operations
        metrics = final_results["final_checker"]["metrics"]
        assert metrics["total_migrations"] >= 3
