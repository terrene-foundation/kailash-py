"""Unit tests for edge migration."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kailash.edge.migration.edge_migrator import (
    EdgeMigrator,
    MigrationCheckpoint,
    MigrationPhase,
    MigrationPlan,
    MigrationProgress,
    MigrationStrategy,
)


class TestEdgeMigrator:
    """Test edge migrator functionality."""

    @pytest.fixture
    def migrator(self):
        """Create an edge migrator instance."""
        return EdgeMigrator(
            checkpoint_interval=30,
            sync_batch_size=100,
            bandwidth_limit_mbps=100,
            enable_compression=True,
        )

    @pytest.fixture
    def sample_plan(self):
        """Create a sample migration plan."""
        return MigrationPlan(
            migration_id="test_migration_123",
            source_edge="edge-west-1",
            target_edge="edge-east-1",
            strategy=MigrationStrategy.LIVE,
            workloads=["api-service", "cache-layer", "db-proxy"],
            data_size_estimate=1024 * 1024 * 500,  # 500MB
            priority=7,
            constraints={"time_window": "maintenance"},
        )

    @pytest.mark.asyncio
    async def test_plan_creation(self, migrator):
        """Test migration plan creation."""
        # Create plan
        plan = await migrator.plan_migration(
            source_edge="edge-1",
            target_edge="edge-2",
            workloads=["workload-1", "workload-2"],
            strategy=MigrationStrategy.LIVE,
            constraints={"bandwidth": "50mbps"},
        )

        # Verify plan
        assert plan.source_edge == "edge-1"
        assert plan.target_edge == "edge-2"
        assert len(plan.workloads) == 2
        assert plan.strategy == MigrationStrategy.LIVE
        assert "bandwidth" in plan.constraints

        # Verify plan is tracked
        assert plan.migration_id in migrator.active_migrations
        assert plan.migration_id in migrator.migration_progress

    @pytest.mark.asyncio
    async def test_plan_validation(self, migrator):
        """Test migration plan validation."""
        # Try to create invalid plan (same source and target)
        with pytest.raises(ValueError) as exc_info:
            await migrator.plan_migration(
                source_edge="edge-1", target_edge="edge-1", workloads=["workload-1"]
            )

        assert "Invalid migration plan" in str(exc_info.value)

        # Try with no workloads
        with pytest.raises(ValueError) as exc_info:
            await migrator.plan_migration(
                source_edge="edge-1", target_edge="edge-2", workloads=[]
            )

        assert "Invalid migration plan" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_migration_strategies(self, migrator):
        """Test different migration strategies."""
        strategies = [
            MigrationStrategy.LIVE,
            MigrationStrategy.STAGED,
            MigrationStrategy.BULK,
            MigrationStrategy.INCREMENTAL,
            MigrationStrategy.EMERGENCY,
        ]

        for strategy in strategies:
            plan = await migrator.plan_migration(
                source_edge="edge-1",
                target_edge="edge-2",
                workloads=["test-workload"],
                strategy=strategy,
            )

            assert plan.strategy == strategy

    @pytest.mark.asyncio
    async def test_progress_tracking(self, migrator, sample_plan):
        """Test migration progress tracking."""
        # Add plan to migrator
        migrator.active_migrations[sample_plan.migration_id] = sample_plan
        migrator.migration_progress[sample_plan.migration_id] = MigrationProgress(
            migration_id=sample_plan.migration_id,
            phase=MigrationPhase.PLANNING,
            progress_percent=0.0,
            data_transferred=0,
            workloads_migrated=[],
            start_time=datetime.now(),
        )

        # Get progress
        progress = await migrator.get_progress(sample_plan.migration_id)

        assert progress.migration_id == sample_plan.migration_id
        assert progress.phase == MigrationPhase.PLANNING
        assert progress.progress_percent == 0.0
        assert len(progress.workloads_migrated) == 0

    @pytest.mark.asyncio
    async def test_phase_transitions(self, migrator, sample_plan):
        """Test migration phase transitions."""
        # Set up migration
        migrator.active_migrations[sample_plan.migration_id] = sample_plan
        progress = MigrationProgress(
            migration_id=sample_plan.migration_id,
            phase=MigrationPhase.PLANNING,
            progress_percent=0.0,
            data_transferred=0,
            workloads_migrated=[],
            start_time=datetime.now(),
        )
        migrator.migration_progress[sample_plan.migration_id] = progress

        # Mock methods
        migrator._check_edge_capacity = AsyncMock(return_value=1000.0)
        migrator._calculate_required_capacity = AsyncMock(return_value=100.0)
        migrator._prepare_target_environment = AsyncMock()
        migrator._create_checkpoint = AsyncMock()

        # Execute pre-sync phase
        await migrator._execute_pre_sync(sample_plan, progress)

        assert progress.phase == MigrationPhase.PRE_SYNC
        assert progress.progress_percent == 10.0
        assert migrator._prepare_target_environment.called

    @pytest.mark.asyncio
    async def test_checkpoint_creation(self, migrator, sample_plan):
        """Test checkpoint creation."""
        # Set up migration
        migrator.active_migrations[sample_plan.migration_id] = sample_plan
        migrator._capture_state_snapshot = AsyncMock(return_value={"test": "snapshot"})

        # Create checkpoint
        checkpoint = await migrator._create_checkpoint(
            sample_plan.migration_id, MigrationPhase.SYNC
        )

        assert checkpoint.migration_id == sample_plan.migration_id
        assert checkpoint.phase == MigrationPhase.SYNC
        assert checkpoint.can_rollback is True
        assert len(migrator.checkpoints[sample_plan.migration_id]) == 1

    @pytest.mark.asyncio
    async def test_pause_resume(self, migrator, sample_plan):
        """Test pause and resume functionality."""
        # Set up active migration
        migrator.active_migrations[sample_plan.migration_id] = sample_plan
        progress = MigrationProgress(
            migration_id=sample_plan.migration_id,
            phase=MigrationPhase.SYNC,
            progress_percent=50.0,
            data_transferred=1024 * 1024 * 250,
            workloads_migrated=["api-service"],
            start_time=datetime.now(),
        )
        migrator.migration_progress[sample_plan.migration_id] = progress
        migrator._create_checkpoint = AsyncMock()

        # Pause migration
        pause_result = await migrator.pause_migration(sample_plan.migration_id)

        assert pause_result["status"] == "paused"
        assert progress.metrics.get("paused") == 1
        assert migrator._create_checkpoint.called

        # Resume migration
        migrator.execute_migration = AsyncMock()
        resume_result = await migrator.resume_migration(sample_plan.migration_id)

        assert resume_result["status"] == "resumed"
        assert "paused" not in progress.metrics

    @pytest.mark.asyncio
    async def test_rollback(self, migrator, sample_plan):
        """Test rollback functionality."""
        # Set up migration with checkpoint
        migrator.active_migrations[sample_plan.migration_id] = sample_plan
        progress = MigrationProgress(
            migration_id=sample_plan.migration_id,
            phase=MigrationPhase.CUTOVER,
            progress_percent=75.0,
            data_transferred=1024 * 1024 * 400,
            workloads_migrated=["api-service", "cache-layer"],
            start_time=datetime.now(),
        )
        migrator.migration_progress[sample_plan.migration_id] = progress

        # Add checkpoint
        checkpoint = MigrationCheckpoint(
            checkpoint_id="test_checkpoint",
            migration_id=sample_plan.migration_id,
            phase=MigrationPhase.SYNC,
            timestamp=datetime.now(),
            state_snapshot={"test": "state"},
            can_rollback=True,
        )
        migrator.checkpoints[sample_plan.migration_id].append(checkpoint)

        # Mock rollback methods
        migrator._restore_from_checkpoint = AsyncMock()
        migrator._switch_traffic = AsyncMock()
        migrator._cleanup_workload = AsyncMock()

        # Execute rollback
        await migrator._execute_rollback(sample_plan, progress)

        assert progress.phase == MigrationPhase.ROLLBACK
        assert migrator._restore_from_checkpoint.called
        assert migrator._switch_traffic.called

    @pytest.mark.asyncio
    async def test_bandwidth_limiting(self, migrator):
        """Test bandwidth limiting."""
        # Set bandwidth limit
        migrator.bandwidth_limit_mbps = 10  # 10 Mbps

        # Test apply bandwidth limit
        data_size = 1024 * 1024  # 1MB

        start_time = asyncio.get_event_loop().time()
        await migrator._apply_bandwidth_limit(data_size)
        elapsed = asyncio.get_event_loop().time() - start_time

        # Should be capped at 0.1 seconds for tests
        expected_time = 0.1  # Capped in _apply_bandwidth_limit for tests
        assert abs(elapsed - expected_time) < 0.05  # Allow 50ms tolerance

    def test_transfer_rate_calculation(self, migrator):
        """Test transfer rate calculation."""
        # Test rate calculation
        bytes_transferred = 1024 * 1024 * 100  # 100MB
        elapsed_seconds = 10.0  # 10 seconds

        rate = migrator._calculate_transfer_rate(bytes_transferred, elapsed_seconds)

        # Should be 80 Mbps (100MB * 8 bits / 10 seconds)
        expected_rate = 80.0
        assert abs(rate - expected_rate) < 0.1

    def test_migration_id_generation(self, migrator):
        """Test migration ID generation."""
        # Generate IDs
        id1 = migrator._generate_migration_id(
            "edge-1", "edge-2", ["workload-1", "workload-2"]
        )
        id2 = migrator._generate_migration_id(
            "edge-1", "edge-2", ["workload-1", "workload-2"]
        )
        id3 = migrator._generate_migration_id(
            "edge-1", "edge-2", ["workload-2", "workload-1"]  # Different order
        )

        # Should be unique due to timestamp
        assert id1 != id2

        # Should handle workload order
        assert len(id3) == 16  # Truncated hash

    def test_migration_metrics(self, migrator):
        """Test migration metrics collection."""
        # Add some completed migrations
        migrator.completed_migrations = ["migration_1", "migration_2"]

        # Add progress for completed
        for i, mid in enumerate(migrator.completed_migrations):
            migrator.migration_progress[mid] = MigrationProgress(
                migration_id=mid,
                phase=MigrationPhase.COMPLETED,
                progress_percent=100.0,
                data_transferred=1024 * 1024 * 100 * (i + 1),
                workloads_migrated=["workload"],
                start_time=datetime.now() - timedelta(hours=i + 1),
            )

        # Add active migration
        migrator.active_migrations["migration_3"] = Mock()
        migrator.migration_progress["migration_3"] = MigrationProgress(
            migration_id="migration_3",
            phase=MigrationPhase.SYNC,
            progress_percent=50.0,
            data_transferred=1024 * 1024 * 50,
            workloads_migrated=[],
            start_time=datetime.now(),
        )

        # Get metrics
        metrics = migrator.get_migration_metrics()

        assert metrics["total_migrations"] == 3
        assert metrics["active_migrations"] == 1
        assert metrics["completed_migrations"] == 2
        assert metrics["failed_migrations"] == 0
        assert metrics["total_data_transferred"] == (1024 * 1024 * 100) + (
            1024 * 1024 * 200
        ) + (
            1024 * 1024 * 50
        )  # 100MB + 200MB + 50MB = 350MB
        assert metrics["success_rate"] == 2 / 3

    def test_migration_history(self, migrator):
        """Test migration history tracking."""
        # Add completed migrations
        for i in range(3):
            migration_id = f"migration_{i}"
            migrator.completed_migrations.append(migration_id)
            migrator.migration_progress[migration_id] = MigrationProgress(
                migration_id=migration_id,
                phase=MigrationPhase.COMPLETED,
                progress_percent=100.0,
                data_transferred=1024 * 1024 * 100,
                workloads_migrated=[f"workload_{i}"],
                start_time=datetime.now() - timedelta(hours=i + 1),
            )

        # Get history
        history = migrator.get_migration_history()

        assert len(history) == 3
        for entry in history:
            assert "migration_id" in entry
            assert "completed_at" in entry
            assert "duration" in entry
            assert "data_transferred" in entry
            assert "workloads" in entry

    @pytest.mark.asyncio
    async def test_background_tasks(self, migrator):
        """Test background task lifecycle."""
        # Start migrator
        await migrator.start()

        assert migrator._running is True
        assert migrator._monitor_task is not None
        assert migrator._checkpoint_task is not None

        # Let tasks run briefly
        await asyncio.sleep(0.1)

        # Stop migrator
        await migrator.stop()

        assert migrator._running is False

    def test_plan_serialization(self, sample_plan):
        """Test plan serialization."""
        # Convert to dict
        plan_dict = sample_plan.to_dict()

        assert plan_dict["migration_id"] == sample_plan.migration_id
        assert plan_dict["source_edge"] == sample_plan.source_edge
        assert plan_dict["target_edge"] == sample_plan.target_edge
        assert plan_dict["strategy"] == sample_plan.strategy.value
        assert plan_dict["workloads"] == sample_plan.workloads
        assert plan_dict["data_size_estimate"] == sample_plan.data_size_estimate
        assert plan_dict["priority"] == sample_plan.priority
        assert "created_at" in plan_dict

    def test_progress_serialization(self):
        """Test progress serialization."""
        progress = MigrationProgress(
            migration_id="test_123",
            phase=MigrationPhase.SYNC,
            progress_percent=50.0,
            data_transferred=1024 * 1024,
            workloads_migrated=["workload-1"],
            start_time=datetime.now(),
            estimated_completion=datetime.now() + timedelta(hours=1),
            errors=["test error"],
            metrics={"rate": 10.5},
        )

        # Convert to dict
        progress_dict = progress.to_dict()

        assert progress_dict["migration_id"] == progress.migration_id
        assert progress_dict["phase"] == progress.phase.value
        assert progress_dict["progress_percent"] == progress.progress_percent
        assert progress_dict["data_transferred"] == progress.data_transferred
        assert progress_dict["workloads_migrated"] == progress.workloads_migrated
        assert "start_time" in progress_dict
        assert "estimated_completion" in progress_dict
        assert progress_dict["errors"] == progress.errors
        assert progress_dict["metrics"] == progress.metrics
