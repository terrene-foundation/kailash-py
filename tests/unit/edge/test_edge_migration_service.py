"""Unit tests for EdgeMigrationService singleton class.

This test suite follows TDD principles and tests the EdgeMigrationService
singleton that manages shared migration state across EdgeMigrationNode instances.
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from kailash.edge.migration.edge_migrator import (
    MigrationPhase,
    MigrationPlan,
    MigrationProgress,
    MigrationStrategy,
)


class TestEdgeMigrationServiceSingleton:
    """Test EdgeMigrationService singleton behavior and shared state management."""

    @pytest.fixture
    def migration_config(self):
        """Create migration configuration for testing."""
        return {
            "checkpoint_interval": 30,
            "sync_batch_size": 500,
            "bandwidth_limit_mbps": 100.0,
            "enable_compression": True,
            "max_concurrent_migrations": 5,
            "cleanup_completed_after": 3600,  # 1 hour
        }

    @pytest.fixture
    def sample_migration_plan(self):
        """Create sample migration plan for testing."""
        return MigrationPlan(
            migration_id="test-migration-123",
            source_edge="edge-west-1",
            target_edge="edge-east-1",
            strategy=MigrationStrategy.LIVE,
            workloads=["api-service", "cache-layer"],
            data_size_estimate=1024 * 1024 * 100,  # 100MB
            priority=7,
        )

    def test_singleton_behavior(self, migration_config):
        """Test that EdgeMigrationService follows singleton pattern."""
        from kailash.edge.migration.edge_migration_service import EdgeMigrationService

        # Clear any existing instance
        EdgeMigrationService._instance = None
        EdgeMigrationService._lock = threading.Lock()

        # Create multiple instances
        service1 = EdgeMigrationService(migration_config)
        service2 = EdgeMigrationService(migration_config)
        service3 = EdgeMigrationService()  # With no config

        # All should be the same instance
        assert service1 is service2
        assert service2 is service3
        assert id(service1) == id(service2) == id(service3)

        # Config should be from first initialization
        assert (
            service1._config["checkpoint_interval"]
            == migration_config["checkpoint_interval"]
        )
        assert (
            service1._config["max_concurrent_migrations"]
            == migration_config["max_concurrent_migrations"]
        )

    def test_thread_safe_singleton_creation(self, migration_config):
        """Test thread-safe singleton creation."""
        from kailash.edge.migration.edge_migration_service import EdgeMigrationService

        # Clear any existing instance
        EdgeMigrationService._instance = None
        EdgeMigrationService._lock = threading.Lock()

        instances = []
        errors = []

        def create_instance(config):
            try:
                instance = EdgeMigrationService(config)
                instances.append(instance)
            except Exception as e:
                errors.append(e)

        # Create instances from multiple threads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(create_instance, migration_config) for _ in range(10)
            ]

            # Wait for all threads to complete
            for future in as_completed(futures):
                future.result()

        # No errors should occur
        assert len(errors) == 0

        # All instances should be the same
        assert len(instances) == 10
        first_instance = instances[0]
        for instance in instances[1:]:
            assert instance is first_instance

    def test_shared_migration_state(self, migration_config, sample_migration_plan):
        """Test that migration state is shared across service instances."""
        from kailash.edge.migration.edge_migration_service import EdgeMigrationService

        # Clear any existing instance
        EdgeMigrationService._instance = None
        EdgeMigrationService._lock = threading.Lock()

        # Create two service instances
        service1 = EdgeMigrationService(migration_config)
        service2 = EdgeMigrationService()

        # Add migration plan through first instance
        service1.store_migration_plan(sample_migration_plan)

        # Should be accessible through second instance (shared state)
        retrieved_plan = service2.get_migration_plan("test-migration-123")
        assert retrieved_plan is not None
        assert retrieved_plan.migration_id == "test-migration-123"
        assert retrieved_plan.source_edge == "edge-west-1"
        assert retrieved_plan.target_edge == "edge-east-1"

    def test_migration_id_collision_detection(self, migration_config):
        """Test detection and handling of migration ID collisions."""
        from kailash.edge.migration.edge_migration_service import EdgeMigrationService

        # Clear any existing instance
        EdgeMigrationService._instance = None
        EdgeMigrationService._lock = threading.Lock()

        service = EdgeMigrationService(migration_config)

        # Reserve a migration ID
        reserved_id = service.reserve_migration_id("edge-1", "edge-2", ["workload-1"])
        assert reserved_id is not None
        assert len(reserved_id) > 0

        # Different parameters should generate different ID
        different_id = service.reserve_migration_id("edge-1", "edge-3", ["workload-1"])
        assert different_id != reserved_id

    def test_thread_safe_state_access(self, migration_config, sample_migration_plan):
        """Test thread-safe access to shared migration state."""
        from kailash.edge.migration.edge_migration_service import EdgeMigrationService

        # Clear any existing instance
        EdgeMigrationService._instance = None
        EdgeMigrationService._lock = threading.Lock()

        service = EdgeMigrationService(migration_config)
        results = []
        errors = []

        def concurrent_migration_access(plan_id):
            try:
                # Store migration plan
                service.store_migration_plan(sample_migration_plan)

                # Create progress entry
                progress = MigrationProgress(
                    migration_id=plan_id,
                    phase=MigrationPhase.PLANNING,
                    progress_percent=0.0,
                    data_transferred=0,
                    workloads_migrated=[],
                    start_time=datetime.now(),
                )
                service.update_migration_progress(progress)

                # Retrieve and verify
                retrieved_plan = service.get_migration_plan(plan_id)
                retrieved_progress = service.get_migration_progress(plan_id)

                results.append(
                    {
                        "plan_found": retrieved_plan is not None,
                        "progress_found": retrieved_progress is not None,
                        "thread_id": threading.current_thread().ident,
                    }
                )
            except Exception as e:
                errors.append(e)

        # Access from multiple threads concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(concurrent_migration_access, "test-migration-123")
                for _ in range(5)
            ]

            for future in as_completed(futures):
                future.result()

        # No errors should occur
        assert len(errors) == 0

        # All threads should successfully access shared state
        assert len(results) == 5
        for result in results:
            assert result["plan_found"] is True
            assert result["progress_found"] is True

    def test_memory_management_and_cleanup(self, migration_config):
        """Test memory management and cleanup of completed migrations."""
        from kailash.edge.migration.edge_migration_service import EdgeMigrationService

        # Clear any existing instance
        EdgeMigrationService._instance = None
        EdgeMigrationService._lock = threading.Lock()

        service = EdgeMigrationService(migration_config)

        # Create multiple completed migrations
        for i in range(10):
            plan = MigrationPlan(
                migration_id=f"completed-migration-{i}",
                source_edge="edge-1",
                target_edge="edge-2",
                strategy=MigrationStrategy.BULK,
                workloads=[f"workload-{i}"],
                data_size_estimate=1024,
            )
            service.store_migration_plan(plan)
            service.mark_migration_completed(plan.migration_id)

        # Before cleanup - should have all migrations
        active_count = service.get_active_migration_count()
        completed_count = service.get_completed_migration_count()
        assert completed_count == 10
        assert active_count == 0  # All marked as completed

        # Trigger cleanup
        service.cleanup_old_migrations()

        # After cleanup - completed migrations should be reduced or same
        new_completed_count = service.get_completed_migration_count()
        assert new_completed_count <= completed_count

    def test_migration_metrics_collection(self, migration_config):
        """Test metrics collection for migration operations."""
        from kailash.edge.migration.edge_migration_service import EdgeMigrationService

        # Clear any existing instance
        EdgeMigrationService._instance = None
        EdgeMigrationService._lock = threading.Lock()

        service = EdgeMigrationService(migration_config)

        # Initial metrics
        metrics = service.get_migration_metrics()
        assert metrics["total_migrations"] == 0
        assert metrics["active_migrations"] == 0
        assert metrics["completed_migrations"] == 0
        assert metrics["success_rate"] == 100.0  # No failures yet

        # Add some migrations
        for i in range(3):
            plan = MigrationPlan(
                migration_id=f"metrics-migration-{i}",
                source_edge="edge-1",
                target_edge="edge-2",
                strategy=MigrationStrategy.LIVE,
                workloads=[f"workload-{i}"],
                data_size_estimate=1024,
            )
            service.store_migration_plan(plan)

        # Complete 2, fail 1
        service.mark_migration_completed("metrics-migration-0")
        service.mark_migration_completed("metrics-migration-1")
        service.mark_migration_failed("metrics-migration-2", "Test failure")

        # Check updated metrics
        updated_metrics = service.get_migration_metrics()
        assert updated_metrics["total_migrations"] == 3
        assert updated_metrics["completed_migrations"] == 2
        assert updated_metrics["failed_migrations"] == 1
        assert updated_metrics["success_rate"] == 66.67  # 2/3 success rate

    @pytest.mark.asyncio
    async def test_async_migration_operations(
        self, migration_config, sample_migration_plan
    ):
        """Test async migration operations in shared service."""
        from kailash.edge.migration.edge_migration_service import EdgeMigrationService

        # Clear any existing instance
        EdgeMigrationService._instance = None
        EdgeMigrationService._lock = threading.Lock()

        service = EdgeMigrationService(migration_config)

        # Async migration planning
        planned_migration = await service.plan_migration_async(
            source_edge="edge-west-1",
            target_edge="edge-east-1",
            workloads=["async-service"],
            strategy=MigrationStrategy.LIVE,
        )

        assert planned_migration is not None
        assert planned_migration.migration_id is not None
        assert planned_migration.source_edge == "edge-west-1"

        # Should be retrievable through sync methods
        retrieved = service.get_migration_plan(planned_migration.migration_id)
        assert retrieved is not None
        assert retrieved.migration_id == planned_migration.migration_id

    def test_service_configuration_management(self):
        """Test configuration management and defaults."""
        from kailash.edge.migration.edge_migration_service import EdgeMigrationService

        # Clear any existing instance
        EdgeMigrationService._instance = None
        EdgeMigrationService._lock = threading.Lock()

        # Test with custom config
        custom_config = {
            "checkpoint_interval": 45,
            "max_concurrent_migrations": 10,
        }
        service = EdgeMigrationService(custom_config)

        # Should merge with defaults
        config = service.get_configuration()
        assert config["checkpoint_interval"] == 45
        assert config["max_concurrent_migrations"] == 10
        assert "sync_batch_size" in config  # Default value
        assert "enable_compression" in config  # Default value

    def test_edge_migration_node_integration(self, migration_config):
        """Test getting migrator instances with different configurations."""
        from kailash.edge.migration.edge_migration_service import EdgeMigrationService

        # Clear any existing instance
        EdgeMigrationService._instance = None
        EdgeMigrationService._lock = threading.Lock()

        service = EdgeMigrationService(migration_config)

        # Get migrator for node1 with custom config
        node1_config = {"checkpoint_interval": 30, "bandwidth_limit_mbps": 50.0}
        migrator1 = service.get_migrator_for_node("node1", node1_config)

        # Get migrator for node2 with different config
        node2_config = {"checkpoint_interval": 60, "sync_batch_size": 2000}
        migrator2 = service.get_migrator_for_node("node2", node2_config)

        # Both migrators should share the same state dictionaries
        assert migrator1.active_migrations is migrator2.active_migrations
        assert migrator1.migration_progress is migrator2.migration_progress

        # But have different configurations
        assert migrator1.checkpoint_interval == 30
        assert migrator2.checkpoint_interval == 60
