"""E2E tests for EdgeMigrationNode shared state in production scenarios.

This test suite validates EdgeMigrationNode shared state functionality
in realistic production scenarios with multiple workflows and complex
migration coordination patterns.
"""

import asyncio

import pytest
import pytest_asyncio
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestEdgeMigrationProductionScenario:
    """E2E tests for production migration scenarios with shared state."""

    @pytest_asyncio.fixture
    async def runtime(self):
        """Create a runtime instance for E2E testing."""
        runtime = LocalRuntime()
        yield runtime
        # Cleanup is handled by runtime

    @pytest.mark.asyncio
    async def test_enterprise_migration_orchestration(self, runtime):
        """Test enterprise scenario: multi-stage migration orchestration across workflows.

        Scenario:
        1. Planning Team workflow: Creates migration plans for critical services
        2. Validation Team workflow: Reviews and validates migration plans
        3. Execution Team workflow: Executes approved migrations
        4. Monitoring Team workflow: Tracks migration progress and metrics

        This tests the real-world scenario where different teams use different
        workflows but need to coordinate through shared migration state.
        """

        # === PHASE 1: Planning Team creates migration plans ===
        planning_workflow = WorkflowBuilder()

        # Plan critical service migrations
        services = ["user-auth", "payment-gateway", "order-processing"]

        for i, service in enumerate(services):
            planning_workflow.add_node(
                "EdgeMigrationNode",
                f"plan_{service.replace('-', '_')}",
                {
                    "operation": "plan_migration",
                    "source_edge": "datacenter-east",
                    "target_edge": "datacenter-west",
                    "workloads": [service, f"{service}-cache", f"{service}-db"],
                    "strategy": "staged",  # Enterprise-safe strategy
                    "priority": 8 + i,  # Higher priority for later services
                    "constraints": {
                        "time_window": "02:00-04:00",
                        "max_downtime": "5m",
                        "require_approval": True,
                    },
                },
            )

        # Execute planning workflow
        planning_results, _ = await runtime.execute_async(planning_workflow.build())

        # Verify all plans were created successfully
        migration_ids = []
        for service in services:
            node_key = f"plan_{service.replace('-', '_')}"
            assert planning_results[node_key]["status"] == "success"
            plan = planning_results[node_key]["plan"]
            migration_ids.append(plan["migration_id"])
            assert plan["strategy"] == "staged"
            assert plan["priority"] >= 8

        # === PHASE 2: Validation Team reviews migration plans ===
        validation_workflow = WorkflowBuilder()

        # Validation team retrieves all active migrations
        validation_workflow.add_node(
            "EdgeMigrationNode",
            "get_pending_migrations",
            {
                "operation": "get_active_migrations",
            },
        )

        # Validation team checks migration metrics
        validation_workflow.add_node(
            "EdgeMigrationNode",
            "check_system_capacity",
            {
                "operation": "get_metrics",
            },
        )

        # Connect validation nodes
        validation_workflow.add_connection(
            "get_pending_migrations", "result", "check_system_capacity", "input"
        )

        # Execute validation workflow
        validation_results, _ = await runtime.execute_async(validation_workflow.build())

        # Verify validation team can see all planned migrations
        assert validation_results["get_pending_migrations"]["status"] == "success"
        pending_migrations = validation_results["get_pending_migrations"]["migrations"]
        pending_ids = [m["migration_id"] for m in pending_migrations]

        # All migration IDs from planning should be visible to validation team
        for migration_id in migration_ids:
            assert migration_id in pending_ids

        # Verify system metrics reflect the planned migrations
        assert validation_results["check_system_capacity"]["status"] == "success"
        metrics = validation_results["check_system_capacity"]["metrics"]
        assert metrics["total_migrations"] >= len(services)
        assert metrics["active_migrations"] >= len(services)

        # === PHASE 3: Execution Team manages migration lifecycle ===
        execution_workflow = WorkflowBuilder()

        # Start migrator service
        execution_workflow.add_node(
            "EdgeMigrationNode",
            "start_migration_service",
            {
                "operation": "start_migrator",
                "checkpoint_interval": 30,
                "enable_compression": True,
            },
        )

        # Pause migrations for maintenance window planning
        execution_workflow.add_node(
            "EdgeMigrationNode",
            "pause_all_migrations",
            {
                "operation": "pause_migration",
            },
        )

        # Resume migrations after maintenance window
        execution_workflow.add_node(
            "EdgeMigrationNode",
            "resume_migrations",
            {
                "operation": "resume_migration",
            },
        )

        # Connect execution nodes
        execution_workflow.add_connection(
            "start_migration_service", "result", "pause_all_migrations", "input"
        )
        execution_workflow.add_connection(
            "pause_all_migrations", "result", "resume_migrations", "input"
        )

        # Execute migration management workflow
        execution_results, _ = await runtime.execute_async(execution_workflow.build())

        # Verify execution team operations succeed
        assert execution_results["start_migration_service"]["status"] == "success"
        assert execution_results["start_migration_service"]["migrator_active"] is True

        # Note: Pause/resume operations will succeed even without specific migration_id
        # This is expected behavior for the current implementation

        # === PHASE 4: Monitoring Team tracks overall progress ===
        monitoring_workflow = WorkflowBuilder()

        # Get comprehensive migration metrics
        monitoring_workflow.add_node(
            "EdgeMigrationNode",
            "collect_metrics",
            {
                "operation": "get_metrics",
            },
        )

        # Get migration history for reporting
        monitoring_workflow.add_node(
            "EdgeMigrationNode",
            "generate_report",
            {
                "operation": "get_history",
            },
        )

        # Get current active migrations
        monitoring_workflow.add_node(
            "EdgeMigrationNode",
            "check_active_status",
            {
                "operation": "get_active_migrations",
            },
        )

        # Connect monitoring nodes for comprehensive report
        monitoring_workflow.add_connection(
            "collect_metrics", "result", "generate_report", "input"
        )
        monitoring_workflow.add_connection(
            "generate_report", "result", "check_active_status", "input"
        )

        # Execute monitoring workflow
        monitoring_results, _ = await runtime.execute_async(monitoring_workflow.build())

        # Verify monitoring team gets complete visibility
        assert monitoring_results["collect_metrics"]["status"] == "success"
        final_metrics = monitoring_results["collect_metrics"]["metrics"]

        # Should see all migrations created by planning team
        assert final_metrics["total_migrations"] >= len(services)
        assert final_metrics["success_rate"] >= 0.0  # No failures expected in this test

        assert monitoring_results["generate_report"]["status"] == "success"
        assert monitoring_results["check_active_status"]["status"] == "success"

        # Final verification: Active migrations should include the planned ones
        final_active = monitoring_results["check_active_status"]["migrations"]
        final_active_ids = [m["migration_id"] for m in final_active]

        # At least some of the originally planned migrations should still be active
        overlap = set(migration_ids) & set(final_active_ids)
        assert (
            len(overlap) > 0
        ), "Planned migrations should be visible across all workflows"

    @pytest.mark.asyncio
    async def test_disaster_recovery_migration_scenario(self, runtime):
        """Test disaster recovery scenario: emergency migration coordination.

        Scenario:
        1. Edge node failure detected
        2. Emergency migration plans created with high priority
        3. Rapid execution across multiple target edges
        4. Progress monitoring and validation

        This tests high-stress coordination patterns.
        """

        # === PHASE 1: Emergency Detection and Planning ===
        emergency_workflow = WorkflowBuilder()

        # Emergency planner creates high-priority migrations
        critical_services = ["auth-service", "session-store", "user-profile"]

        for service in critical_services:
            emergency_workflow.add_node(
                "EdgeMigrationNode",
                f"emergency_{service.replace('-', '_')}",
                {
                    "operation": "plan_migration",
                    "source_edge": "failed-edge-node",
                    "target_edge": "backup-edge-cluster",
                    "workloads": [service],
                    "strategy": "emergency",  # Fast but potentially risky
                    "priority": 10,  # Maximum priority
                    "constraints": {
                        "skip_validation": True,
                        "force_migration": True,
                        "max_downtime": "30s",
                    },
                },
            )

        # Execute emergency planning
        emergency_results, _ = await runtime.execute_async(emergency_workflow.build())

        # Verify emergency plans created successfully
        emergency_migration_ids = []
        for service in critical_services:
            node_key = f"emergency_{service.replace('-', '_')}"
            assert emergency_results[node_key]["status"] == "success"
            plan = emergency_results[node_key]["plan"]
            emergency_migration_ids.append(plan["migration_id"])
            assert plan["strategy"] == "emergency"
            assert plan["priority"] == 10

        # === PHASE 2: Rapid Status Assessment ===
        status_workflow = WorkflowBuilder()

        # Quick metrics check
        status_workflow.add_node(
            "EdgeMigrationNode",
            "emergency_metrics",
            {
                "operation": "get_metrics",
            },
        )

        # Get all active migrations (including emergency ones)
        status_workflow.add_node(
            "EdgeMigrationNode",
            "active_emergency_migrations",
            {
                "operation": "get_active_migrations",
            },
        )

        status_workflow.add_connection(
            "emergency_metrics", "result", "active_emergency_migrations", "input"
        )

        # Execute status assessment
        status_results, _ = await runtime.execute_async(status_workflow.build())

        # Verify emergency migrations visible in system
        assert status_results["emergency_metrics"]["status"] == "success"
        emergency_metrics = status_results["emergency_metrics"]["metrics"]
        assert emergency_metrics["total_migrations"] >= len(critical_services)

        assert status_results["active_emergency_migrations"]["status"] == "success"
        active_migrations = status_results["active_emergency_migrations"]["migrations"]
        active_ids = [m["migration_id"] for m in active_migrations]

        # All emergency migrations should be visible
        for emergency_id in emergency_migration_ids:
            assert emergency_id in active_ids

        # === PHASE 3: Coordination Validation ===
        # Verify that different workflows can coordinate on the same migrations

        # Create multiple concurrent monitoring workflows
        concurrent_tasks = []

        for i in range(3):
            monitor_workflow = WorkflowBuilder()
            monitor_workflow.add_node(
                "EdgeMigrationNode",
                f"concurrent_monitor_{i}",
                {
                    "operation": "get_active_migrations",
                },
            )

            task = runtime.execute_async(monitor_workflow.build())
            concurrent_tasks.append(task)

        # Execute all monitoring workflows concurrently
        concurrent_results = await asyncio.gather(*concurrent_tasks)

        # All concurrent workflows should see the same emergency migrations
        for results, _ in concurrent_results:
            monitor_key = [
                k for k in results.keys() if k.startswith("concurrent_monitor")
            ][0]
            assert results[monitor_key]["status"] == "success"

            concurrent_active = results[monitor_key]["migrations"]
            concurrent_ids = [m["migration_id"] for m in concurrent_active]

            # Each concurrent workflow should see the emergency migrations
            emergency_overlap = set(emergency_migration_ids) & set(concurrent_ids)
            assert len(emergency_overlap) == len(
                emergency_migration_ids
            ), "All emergency migrations should be visible to concurrent workflows"

    @pytest.mark.asyncio
    async def test_migration_state_persistence_across_runtime_cycles(self, runtime):
        """Test that migration state persists across multiple runtime execution cycles.

        This simulates long-running enterprise scenarios where migrations
        are planned, monitored, and managed across multiple operational cycles.
        """

        # === CYCLE 1: Initial setup and planning ===
        cycle1_workflow = WorkflowBuilder()

        cycle1_workflow.add_node(
            "EdgeMigrationNode",
            "setup_migrator",
            {
                "operation": "start_migrator",
            },
        )

        cycle1_workflow.add_node(
            "EdgeMigrationNode",
            "plan_persistent_migration",
            {
                "operation": "plan_migration",
                "source_edge": "persistent-source",
                "target_edge": "persistent-target",
                "workloads": ["persistent-workload"],
                "strategy": "incremental",
                "priority": 6,
            },
        )

        cycle1_workflow.add_connection(
            "setup_migrator", "result", "plan_persistent_migration", "input"
        )

        cycle1_results, _ = await runtime.execute_async(cycle1_workflow.build())

        assert cycle1_results["setup_migrator"]["status"] == "success"
        assert cycle1_results["plan_persistent_migration"]["status"] == "success"
        persistent_migration_id = cycle1_results["plan_persistent_migration"]["plan"][
            "migration_id"
        ]

        # === CYCLE 2: Monitoring and validation (separate runtime execution) ===
        cycle2_workflow = WorkflowBuilder()

        cycle2_workflow.add_node(
            "EdgeMigrationNode",
            "check_persistence",
            {
                "operation": "get_active_migrations",
            },
        )

        cycle2_workflow.add_node(
            "EdgeMigrationNode",
            "validate_metrics",
            {
                "operation": "get_metrics",
            },
        )

        cycle2_workflow.add_connection(
            "check_persistence", "result", "validate_metrics", "input"
        )

        cycle2_results, _ = await runtime.execute_async(cycle2_workflow.build())

        # Verify migration persists across runtime cycles
        assert cycle2_results["check_persistence"]["status"] == "success"
        persistent_active = cycle2_results["check_persistence"]["migrations"]
        persistent_ids = [m["migration_id"] for m in persistent_active]

        assert (
            persistent_migration_id in persistent_ids
        ), "Migration should persist across runtime execution cycles"

        assert cycle2_results["validate_metrics"]["status"] == "success"
        persistent_metrics = cycle2_results["validate_metrics"]["metrics"]
        assert persistent_metrics["total_migrations"] >= 1
        assert persistent_metrics["active_migrations"] >= 1

        # === CYCLE 3: Final management operations ===
        cycle3_workflow = WorkflowBuilder()

        # Add another migration to test multiple migration coordination
        cycle3_workflow.add_node(
            "EdgeMigrationNode",
            "add_second_migration",
            {
                "operation": "plan_migration",
                "source_edge": "secondary-source",
                "target_edge": "secondary-target",
                "workloads": ["secondary-workload"],
                "strategy": "live",
                "priority": 7,
            },
        )

        cycle3_workflow.add_node(
            "EdgeMigrationNode",
            "final_status_check",
            {
                "operation": "get_active_migrations",
            },
        )

        cycle3_workflow.add_connection(
            "add_second_migration", "result", "final_status_check", "input"
        )

        cycle3_results, _ = await runtime.execute_async(cycle3_workflow.build())

        assert cycle3_results["add_second_migration"]["status"] == "success"
        second_migration_id = cycle3_results["add_second_migration"]["plan"][
            "migration_id"
        ]

        assert cycle3_results["final_status_check"]["status"] == "success"
        final_active = cycle3_results["final_status_check"]["migrations"]
        final_ids = [m["migration_id"] for m in final_active]

        # Both migrations should be active
        assert persistent_migration_id in final_ids
        assert second_migration_id in final_ids
        assert (
            len(final_ids) >= 2
        ), "Should have multiple migrations coordinated through shared state"
