"""Integration tests for edge migration functionality."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from kailash.edge.migration.edge_migrator import (
    EdgeMigrator,
    MigrationPhase,
    MigrationPlan,
    MigrationProgress,
    MigrationStrategy,
)
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestEdgeMigrationIntegration:
    """Test edge migration integration with workflows."""

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
    async def test_migration_workflow(self, runtime, workflow_builder):
        """Test migration workflow operations."""

        # Test migrator start
        workflow_builder.add_node(
            "EdgeMigrationNode",
            "migrator_start",
            {
                "operation": "start_migrator",
                "checkpoint_interval": 30,
                "bandwidth_limit_mbps": 100,
            },
        )

        workflow = workflow_builder.build()
        results, run_id = await runtime.execute_async(workflow)

        # Verify migrator start
        assert results["migrator_start"]["status"] == "success"
        assert results["migrator_start"]["migrator_active"] is True

        # Test plan creation in a separate workflow
        plan_workflow_builder = WorkflowBuilder()
        plan_workflow_builder.add_node(
            "EdgeMigrationNode",
            "plan",
            {
                "operation": "plan_migration",
                "source_edge": "edge-west-1",
                "target_edge": "edge-east-1",
                "workloads": ["api-service", "cache-layer"],
                "strategy": "live",
                "priority": 8,
            },
        )

        plan_workflow = plan_workflow_builder.build()
        plan_results, plan_run_id = await runtime.execute_async(plan_workflow)

        # Verify plan creation
        assert plan_results["plan"]["status"] == "success"
        assert "migration_id" in plan_results["plan"]["plan"]
        assert plan_results["plan"]["plan"]["source_edge"] == "edge-west-1"
        assert plan_results["plan"]["plan"]["target_edge"] == "edge-east-1"
        assert plan_results["plan"]["plan"]["strategy"] == "live"
        assert plan_results["plan"]["plan"]["priority"] == 8

    @pytest.mark.asyncio
    async def test_migration_strategies(self, runtime, workflow_builder):
        """Test different migration strategies."""
        strategies = ["live", "staged", "bulk", "incremental", "emergency"]

        for strategy in strategies:
            # Clear workflow
            workflow_builder = WorkflowBuilder()

            workflow_builder.add_node(
                "EdgeMigrationNode",
                "plan",
                {
                    "operation": "plan_migration",
                    "source_edge": f"edge-{strategy}-source",
                    "target_edge": f"edge-{strategy}-target",
                    "workloads": [f"workload-{strategy}"],
                    "strategy": strategy,
                },
            )

            # Execute
            workflow = workflow_builder.build()
            results, run_id = await runtime.execute_async(workflow)

            assert results["plan"]["status"] == "success"
            assert results["plan"]["plan"]["strategy"] == strategy

    @pytest.mark.asyncio
    async def test_migration_with_constraints(self, runtime, workflow_builder):
        """Test migration with constraints."""
        workflow_builder.add_node(
            "EdgeMigrationNode",
            "plan",
            {
                "operation": "plan_migration",
                "source_edge": "edge-1",
                "target_edge": "edge-2",
                "workloads": ["db-service", "api-gateway"],
                "strategy": "staged",
                "constraints": {
                    "time_window": "02:00-04:00",
                    "bandwidth": "50mbps",
                    "max_downtime": "5m",
                },
            },
        )

        # Execute
        workflow = workflow_builder.build()
        results, run_id = await runtime.execute_async(workflow)

        assert results["plan"]["status"] == "success"
        assert results["plan"]["plan"]["constraints"]["time_window"] == "02:00-04:00"
        assert results["plan"]["plan"]["constraints"]["bandwidth"] == "50mbps"

    @pytest.mark.asyncio
    async def test_migration_pause_resume(self, runtime, workflow_builder):
        """Test pause and resume functionality using shared state."""
        # This test demonstrates the shared state functionality where
        # migration operations can coordinate across separate workflows

        # === Workflow 1: Start migrator and create migration plan ===
        workflow_builder.add_node(
            "EdgeMigrationNode", "start", {"operation": "start_migrator"}
        )

        workflow_builder.add_node(
            "EdgeMigrationNode",
            "plan",
            {
                "operation": "plan_migration",
                "source_edge": "edge-source",
                "target_edge": "edge-target",
                "workloads": ["service-1"],
                "strategy": "live",
            },
        )

        # Connect with correct output parameters
        workflow_builder.add_connection("start", "status", "plan", "input")

        # Execute first workflow
        workflow = workflow_builder.build()
        results, run_id = await runtime.execute_async(workflow)

        # Verify plan creation
        assert results["start"]["status"] == "success"
        assert results["start"]["migrator_active"] is True
        assert results["plan"]["status"] == "success"
        migration_id = results["plan"]["plan"]["migration_id"]

        # === Workflow 2: Use shared state to pause/resume migration ===
        # This demonstrates that another workflow can operate on the same migration
        pause_resume_builder = WorkflowBuilder()

        # Pause migration (using migration_id from previous workflow)
        pause_resume_builder.add_node(
            "EdgeMigrationNode",
            "pause",
            {
                "operation": "pause_migration",
                "migration_id": migration_id,
            },
        )

        # Resume migration
        pause_resume_builder.add_node(
            "EdgeMigrationNode",
            "resume",
            {
                "operation": "resume_migration",
                "migration_id": migration_id,
            },
        )

        # Connect pause and resume
        pause_resume_builder.add_connection("pause", "status", "resume", "input")

        # Execute pause/resume workflow
        pause_resume_workflow = pause_resume_builder.build()
        pause_resume_results, _ = await runtime.execute_async(pause_resume_workflow)

        # Verify operations succeed (even though actual pause/resume logic may be minimal)
        assert pause_resume_results["pause"]["status"] == "success"
        assert pause_resume_results["resume"]["status"] == "success"

    @pytest.mark.asyncio
    async def test_migration_metrics(self, runtime, workflow_builder):
        """Test migration metrics collection."""
        # Get metrics
        workflow_builder.add_node(
            "EdgeMigrationNode", "metrics", {"operation": "get_metrics"}
        )

        # Get history
        workflow_builder.add_node(
            "EdgeMigrationNode", "history", {"operation": "get_history"}
        )

        # Connect
        workflow_builder.add_connection("metrics", "result", "history", "input")

        # Execute
        workflow = workflow_builder.build()
        results, run_id = await runtime.execute_async(workflow)

        assert results["metrics"]["status"] == "success"
        assert "metrics" in results["metrics"]
        assert "total_migrations" in results["metrics"]["metrics"]
        assert "active_migrations" in results["metrics"]["metrics"]
        assert "success_rate" in results["metrics"]["metrics"]

        assert results["history"]["status"] == "success"
        assert "migrations" in results["history"]
        assert isinstance(results["history"]["migrations"], list)

    @pytest.mark.asyncio
    async def test_multi_workload_migration(self, runtime, workflow_builder):
        """Test migration with multiple workloads."""
        workloads = [
            "frontend-app",
            "api-gateway",
            "auth-service",
            "database-proxy",
            "cache-layer",
        ]

        workflow_builder.add_node(
            "EdgeMigrationNode",
            "plan",
            {
                "operation": "plan_migration",
                "source_edge": "datacenter-west",
                "target_edge": "datacenter-east",
                "workloads": workloads,
                "strategy": "staged",
                "priority": 9,
            },
        )

        # Execute
        workflow = workflow_builder.build()
        results, run_id = await runtime.execute_async(workflow)

        assert results["plan"]["status"] == "success"
        assert len(results["plan"]["plan"]["workloads"]) == 5
        assert results["plan"]["plan"]["priority"] == 9
        assert "estimated_duration" in results["plan"]

    @pytest.mark.asyncio
    async def test_migration_error_handling(self, runtime, workflow_builder):
        """Test migration error handling."""
        # Try invalid migration (same source and target)
        workflow_builder.add_node(
            "EdgeMigrationNode",
            "invalid_plan",
            {
                "operation": "plan_migration",
                "source_edge": "edge-1",
                "target_edge": "edge-1",  # Same as source
                "workloads": ["service-1"],
            },
        )

        # Execute
        workflow = workflow_builder.build()
        results, run_id = await runtime.execute_async(workflow)

        assert results["invalid_plan"]["status"] == "error"
        assert "Invalid migration plan" in results["invalid_plan"]["error"]

    @pytest.mark.asyncio
    async def test_migration_with_monitoring(self, runtime, workflow_builder):
        """Test migration integrated with monitoring."""
        # Start monitoring
        workflow_builder.add_node(
            "EdgeMonitoringNode",
            "monitor_start",
            {
                "operation": "start_monitor",
                "edge_nodes": ["edge-west", "edge-east"],
                "collect_interval": 5,
                "anomaly_detection": True,
            },
        )

        # Plan migration
        workflow_builder.add_node(
            "EdgeMigrationNode",
            "migrate",
            {
                "operation": "plan_migration",
                "source_edge": "edge-west",
                "target_edge": "edge-east",
                "workloads": ["monitored-service"],
                "strategy": "live",
            },
        )

        # Get analytics after migration
        workflow_builder.add_node(
            "EdgeMonitoringNode",
            "analytics",
            {"operation": "get_analytics", "edge_nodes": ["edge-west", "edge-east"]},
        )

        # Connect nodes
        workflow_builder.add_connection("monitor_start", "result", "migrate", "input")
        workflow_builder.add_connection("migrate", "result", "analytics", "input")

        # Execute
        workflow = workflow_builder.build()
        results, run_id = await runtime.execute_async(workflow)

        assert results["monitor_start"]["status"] == "success"
        assert results["migrate"]["status"] == "success"
        assert results["analytics"]["status"] == "success"
        assert "analytics" in results["analytics"]

    @pytest.mark.asyncio
    async def test_emergency_migration(self, runtime, workflow_builder):
        """Test emergency migration scenario."""
        # Simulate edge failure and emergency migration
        workflow_builder.add_node(
            "EdgeMigrationNode",
            "emergency",
            {
                "operation": "plan_migration",
                "source_edge": "failing-edge",
                "target_edge": "backup-edge",
                "workloads": ["critical-service-1", "critical-service-2"],
                "strategy": "emergency",
                "priority": 10,  # Maximum priority
                "constraints": {"skip_validation": True, "force_migration": True},
            },
        )

        # Execute
        workflow = workflow_builder.build()
        results, run_id = await runtime.execute_async(workflow)

        assert results["emergency"]["status"] == "success"
        assert results["emergency"]["plan"]["strategy"] == "emergency"
        assert results["emergency"]["plan"]["priority"] == 10
        assert results["emergency"]["plan"]["constraints"]["force_migration"] is True

    @pytest.mark.asyncio
    async def test_incremental_migration(self, runtime, workflow_builder):
        """Test incremental migration with data updates."""
        workflow_builder.add_node(
            "EdgeMigrationNode",
            "start_migrator",
            {
                "operation": "start_migrator",
                "sync_batch_size": 100,
                "enable_compression": True,
            },
        )

        workflow_builder.add_node(
            "EdgeMigrationNode",
            "incremental",
            {
                "operation": "plan_migration",
                "source_edge": "primary-edge",
                "target_edge": "secondary-edge",
                "workloads": ["large-database", "file-storage"],
                "strategy": "incremental",
                "constraints": {"sync_interval": "5m", "delta_threshold": "100MB"},
            },
        )

        # Connect
        workflow_builder.add_connection(
            "start_migrator", "result", "incremental", "input"
        )

        # Execute
        workflow = workflow_builder.build()
        results, run_id = await runtime.execute_async(workflow)

        assert results["incremental"]["status"] == "success"
        assert results["incremental"]["plan"]["strategy"] == "incremental"
        assert results["incremental"]["plan"]["constraints"]["sync_interval"] == "5m"
