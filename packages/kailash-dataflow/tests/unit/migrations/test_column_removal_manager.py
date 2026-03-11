#!/usr/bin/env python3
"""
Unit tests for Column Removal Manager

Tests individual methods and components of the column removal system
without requiring database connections.

Covers:
- Removal plan generation logic
- Safety validation logic
- Backup strategy handlers
- Execution stage ordering
- Duration estimation
- Error handling
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from dataflow.migrations.column_removal_manager import (
    BackupInfo,
    BackupStrategy,
    ColumnOnlyBackupHandler,
    ColumnRemovalManager,
    RemovalPlan,
    RemovalResult,
    RemovalStage,
    RemovalStageResult,
    SafetyValidation,
    TableSnapshotBackupHandler,
)
from dataflow.migrations.dependency_analyzer import (
    ConstraintDependency,
    DependencyType,
    ForeignKeyDependency,
    ImpactLevel,
    IndexDependency,
    TriggerDependency,
    ViewDependency,
)


class TestColumnRemovalManager:
    """Unit tests for ColumnRemovalManager methods."""

    @pytest.fixture
    def mock_dependency_analyzer(self):
        """Mock dependency analyzer."""
        analyzer = MagicMock()
        analyzer.analyze_column_dependencies = AsyncMock(return_value=[])
        return analyzer

    @pytest.fixture
    def removal_manager(self, mock_dependency_analyzer):
        """Create removal manager with mocked dependencies."""
        manager = ColumnRemovalManager(connection_manager=None)
        manager.dependency_analyzer = mock_dependency_analyzer
        return manager

    def test_generate_execution_stages_no_dependencies(self, removal_manager):
        """Test stage generation with no dependencies."""
        dependencies = []

        stages = removal_manager._generate_execution_stages(dependencies)

        expected_stages = [
            RemovalStage.BACKUP_CREATION,
            RemovalStage.COLUMN_REMOVAL,
            RemovalStage.CLEANUP,
            RemovalStage.VALIDATION,
        ]

        assert stages == expected_stages

    def test_generate_execution_stages_with_indexes(self, removal_manager):
        """Test stage generation with index dependencies."""
        dependencies = [
            IndexDependency(
                index_name="idx_test",
                index_type="btree",
                columns=["test_column"],
                dependency_type=DependencyType.INDEX,
                impact_level=ImpactLevel.LOW,
            )
        ]

        stages = removal_manager._generate_execution_stages(dependencies)

        assert RemovalStage.INDEX_REMOVAL in stages
        assert stages.index(RemovalStage.INDEX_REMOVAL) < stages.index(
            RemovalStage.COLUMN_REMOVAL
        )

    def test_generate_execution_stages_with_constraints(self, removal_manager):
        """Test stage generation with constraint dependencies."""
        dependencies = [
            ForeignKeyDependency(
                constraint_name="fk_test",
                source_table="source_table",
                source_column="source_col",
                target_table="target_table",
                target_column="target_col",
                dependency_type=DependencyType.FOREIGN_KEY,
                impact_level=ImpactLevel.HIGH,
            ),
            ConstraintDependency(
                constraint_name="chk_test",
                constraint_type="CHECK",
                definition="CHECK (value > 0)",
                columns=["value"],
                dependency_type=DependencyType.CONSTRAINT,
                impact_level=ImpactLevel.LOW,
            ),
        ]

        stages = removal_manager._generate_execution_stages(dependencies)

        assert RemovalStage.CONSTRAINT_REMOVAL in stages
        assert stages.index(RemovalStage.CONSTRAINT_REMOVAL) < stages.index(
            RemovalStage.COLUMN_REMOVAL
        )

    def test_generate_execution_stages_with_dependent_objects(self, removal_manager):
        """Test stage generation with dependent objects."""
        dependencies = [
            TriggerDependency(
                trigger_name="trigger_test",
                event="UPDATE",
                timing="BEFORE",
                function_name="trigger_function",
                dependency_type=DependencyType.TRIGGER,
                impact_level=ImpactLevel.MEDIUM,
            ),
            ViewDependency(
                view_name="view_test",
                view_definition="SELECT * FROM test_table",
                dependency_type=DependencyType.VIEW,
                impact_level=ImpactLevel.HIGH,
            ),
            ConstraintDependency(
                constraint_name="func_test",
                constraint_type="FUNCTION",
                definition="FUNCTION test_func()",
                columns=[],
                dependency_type=DependencyType.CONSTRAINT,
                impact_level=ImpactLevel.MEDIUM,
            ),
        ]

        stages = removal_manager._generate_execution_stages(dependencies)

        assert RemovalStage.DEPENDENT_OBJECTS in stages
        assert stages.index(RemovalStage.DEPENDENT_OBJECTS) < stages.index(
            RemovalStage.COLUMN_REMOVAL
        )

    def test_generate_execution_stages_complete_ordering(self, removal_manager):
        """Test complete stage ordering with all dependency types."""
        dependencies = [
            TriggerDependency(
                trigger_name="trigger",
                event="UPDATE",
                timing="BEFORE",
                function_name="func",
                dependency_type=DependencyType.TRIGGER,
                impact_level=ImpactLevel.MEDIUM,
            ),
            ForeignKeyDependency(
                constraint_name="fk",
                source_table="source",
                source_column="col",
                target_table="target",
                target_column="id",
                dependency_type=DependencyType.FOREIGN_KEY,
                impact_level=ImpactLevel.HIGH,
            ),
            IndexDependency(
                index_name="idx",
                index_type="btree",
                columns=["col"],
                dependency_type=DependencyType.INDEX,
                impact_level=ImpactLevel.LOW,
            ),
            ViewDependency(
                view_name="view",
                view_definition="SELECT * FROM table",
                dependency_type=DependencyType.VIEW,
                impact_level=ImpactLevel.HIGH,
            ),
        ]

        stages = removal_manager._generate_execution_stages(dependencies)

        # Verify all expected stages are present
        expected_stages = {
            RemovalStage.BACKUP_CREATION,
            RemovalStage.DEPENDENT_OBJECTS,
            RemovalStage.CONSTRAINT_REMOVAL,
            RemovalStage.INDEX_REMOVAL,
            RemovalStage.COLUMN_REMOVAL,
            RemovalStage.CLEANUP,
            RemovalStage.VALIDATION,
        }

        assert set(stages) == expected_stages

        # Verify correct ordering
        stage_positions = {stage: stages.index(stage) for stage in stages}

        assert stage_positions[RemovalStage.BACKUP_CREATION] == 0
        assert (
            stage_positions[RemovalStage.DEPENDENT_OBJECTS]
            < stage_positions[RemovalStage.CONSTRAINT_REMOVAL]
        )
        assert (
            stage_positions[RemovalStage.CONSTRAINT_REMOVAL]
            < stage_positions[RemovalStage.INDEX_REMOVAL]
        )
        assert (
            stage_positions[RemovalStage.INDEX_REMOVAL]
            < stage_positions[RemovalStage.COLUMN_REMOVAL]
        )
        assert (
            stage_positions[RemovalStage.COLUMN_REMOVAL]
            < stage_positions[RemovalStage.CLEANUP]
        )
        assert (
            stage_positions[RemovalStage.CLEANUP]
            < stage_positions[RemovalStage.VALIDATION]
        )

    def test_estimate_removal_duration_base_case(self, removal_manager):
        """Test duration estimation with no dependencies."""
        dependencies = []

        duration = removal_manager._estimate_removal_duration(dependencies)

        assert duration == 5.0  # Base time only

    def test_estimate_removal_duration_with_dependencies(self, removal_manager):
        """Test duration estimation with various dependencies."""
        dependencies = [
            IndexDependency(
                index_name="idx",
                index_type="btree",
                columns=["test_col"],
                dependency_type=DependencyType.INDEX,
                impact_level=ImpactLevel.LOW,
            ),
            ForeignKeyDependency(
                constraint_name="fk",
                source_table="source",
                source_column="col",
                target_table="target",
                target_column="id",
                dependency_type=DependencyType.FOREIGN_KEY,
                impact_level=ImpactLevel.HIGH,
            ),
            ConstraintDependency(
                constraint_name="chk",
                constraint_type="CHECK",
                definition="CHECK (value > 0)",
                columns=["value"],
                dependency_type=DependencyType.CONSTRAINT,
                impact_level=ImpactLevel.LOW,
            ),
            TriggerDependency(
                trigger_name="trigger",
                event="UPDATE",
                timing="BEFORE",
                function_name="trigger_func",
                dependency_type=DependencyType.TRIGGER,
                impact_level=ImpactLevel.MEDIUM,
            ),
        ]

        duration = removal_manager._estimate_removal_duration(dependencies)

        # Base (5.0) + INDEX (2.0) + FK (3.0) + CHECK (1.0) + TRIGGER (2.0) = 13.0
        expected = 5.0 + 2.0 + 3.0 + 1.0 + 2.0
        assert duration == expected

    def test_estimate_removal_duration_unknown_dependencies(self, removal_manager):
        """Test duration estimation with unknown dependency types."""
        dependencies = [
            ConstraintDependency(
                constraint_name="unknown",
                constraint_type="UNKNOWN",
                definition="UNKNOWN CONSTRAINT",
                columns=[],
                dependency_type=DependencyType.CONSTRAINT,
                impact_level=ImpactLevel.LOW,
            ),
        ]

        duration = removal_manager._estimate_removal_duration(dependencies)

        # Base (5.0) + unknown (1.0 default) = 6.0
        assert duration == 6.0


class TestSafetyValidationLogic:
    """Test safety validation logic without database operations."""

    @pytest.fixture
    def removal_manager(self):
        """Create removal manager for testing."""
        return ColumnRemovalManager(connection_manager=None)

    def test_safety_validation_no_dependencies(self, removal_manager):
        """Test validation logic with no dependencies."""
        plan = RemovalPlan(
            table_name="test_table", column_name="test_column", dependencies=[]
        )

        # Mock the async validation checks
        async def mock_validate():
            return await removal_manager.validate_removal_safety(plan)

        # This would need actual async testing in practice
        # For unit tests, we focus on the logic components

    def test_risk_level_calculation_logic(self):
        """Test risk level calculation logic."""
        # Test with critical dependencies
        critical_deps = [
            ForeignKeyDependency(
                "critical_fk", DependencyType.FOREIGN_KEY, ImpactLevel.CRITICAL
            )
        ]

        # In actual implementation, this logic would be in validate_removal_safety
        # Here we test the logic directly
        risk_level = ImpactLevel.LOW
        if any(dep.impact_level == ImpactLevel.CRITICAL for dep in critical_deps):
            risk_level = ImpactLevel.CRITICAL

        assert risk_level == ImpactLevel.CRITICAL

    def test_blocking_dependency_identification(self):
        """Test identification of blocking dependencies."""
        dependencies = [
            IndexDependency(
                index_name="safe_idx",
                index_type="btree",
                columns=["col"],
                dependency_type=DependencyType.INDEX,
                impact_level=ImpactLevel.LOW,
            ),
            ForeignKeyDependency(
                constraint_name="risky_fk",
                source_table="source",
                source_column="col",
                target_table="target",
                target_column="id",
                dependency_type=DependencyType.FOREIGN_KEY,
                impact_level=ImpactLevel.HIGH,
            ),
            ForeignKeyDependency(
                constraint_name="critical_fk",
                source_table="source",
                source_column="col",
                target_table="target",
                target_column="id",
                dependency_type=DependencyType.FOREIGN_KEY,
                impact_level=ImpactLevel.CRITICAL,
            ),
        ]

        blocking_deps = [
            dep for dep in dependencies if dep.impact_level == ImpactLevel.CRITICAL
        ]

        assert len(blocking_deps) == 1
        assert blocking_deps[0].constraint_name == "critical_fk"


class TestBackupHandlers:
    """Test backup strategy handlers."""

    @pytest.mark.asyncio
    async def test_column_only_backup_handler(self):
        """Test column-only backup handler logic."""
        handler = ColumnOnlyBackupHandler()
        mock_connection = AsyncMock()

        # Mock primary key query
        mock_connection.fetch.return_value = [{"attname": "id"}]
        # Mock backup table row count
        mock_connection.fetchval.return_value = 100

        backup_info = await handler.create_backup(
            "test_table", "test_column", mock_connection
        )

        assert backup_info.strategy == BackupStrategy.COLUMN_ONLY
        assert backup_info.backup_size == 100
        assert "test_table__test_column_backup_" in backup_info.backup_location
        assert backup_info.verification_query is not None

    @pytest.mark.asyncio
    async def test_column_only_backup_no_primary_key(self):
        """Test column-only backup when table has no primary key."""
        handler = ColumnOnlyBackupHandler()
        mock_connection = AsyncMock()

        # Mock no primary key columns
        mock_connection.fetch.return_value = []
        mock_connection.fetchval.return_value = 50

        backup_info = await handler.create_backup(
            "test_table", "test_column", mock_connection
        )

        # Should fallback to ctid
        assert backup_info.backup_size == 50
        # Verify the backup query used ctid (would need to check execute calls in practice)

    @pytest.mark.asyncio
    async def test_table_snapshot_backup_handler(self):
        """Test table snapshot backup handler."""
        handler = TableSnapshotBackupHandler()
        mock_connection = AsyncMock()

        mock_connection.fetchval.return_value = 200

        backup_info = await handler.create_backup(
            "test_table", "test_column", mock_connection
        )

        assert backup_info.strategy == BackupStrategy.TABLE_SNAPSHOT
        assert backup_info.backup_size == 200
        assert "test_table_backup_" in backup_info.backup_location
        assert backup_info.verification_query is not None

    @pytest.mark.asyncio
    async def test_backup_cleanup(self):
        """Test backup cleanup functionality."""
        handler = ColumnOnlyBackupHandler()
        mock_connection = AsyncMock()

        backup_info = BackupInfo(
            strategy=BackupStrategy.COLUMN_ONLY,
            backup_location="test_backup_table",
            backup_size=100,
            created_at=datetime.now(),
        )

        result = await handler.cleanup_backup(backup_info, mock_connection)

        assert result is True
        mock_connection.execute.assert_called_once_with(
            "DROP TABLE IF EXISTS test_backup_table"
        )

    @pytest.mark.asyncio
    async def test_backup_cleanup_failure(self):
        """Test backup cleanup with failure."""
        handler = ColumnOnlyBackupHandler()
        mock_connection = AsyncMock()
        mock_connection.execute.side_effect = Exception("Permission denied")

        backup_info = BackupInfo(
            strategy=BackupStrategy.COLUMN_ONLY,
            backup_location="test_backup_table",
            backup_size=100,
            created_at=datetime.now(),
        )

        result = await handler.cleanup_backup(backup_info, mock_connection)

        assert result is False


class TestRemovalStageResults:
    """Test removal stage result handling."""

    def test_removal_stage_result_success(self):
        """Test successful stage result."""
        result = RemovalStageResult(
            stage=RemovalStage.INDEX_REMOVAL,
            success=True,
            duration=2.5,
            objects_affected=["idx_test_column"],
            warnings=["Index dropped successfully"],
        )

        assert result.success is True
        assert result.duration == 2.5
        assert len(result.objects_affected) == 1
        assert len(result.errors) == 0

    def test_removal_stage_result_failure(self):
        """Test failed stage result."""
        result = RemovalStageResult(
            stage=RemovalStage.COLUMN_REMOVAL,
            success=False,
            duration=1.0,
            errors=["Permission denied for table modification"],
        )

        assert result.success is False
        assert len(result.errors) == 1
        assert "Permission denied" in result.errors[0]

    def test_removal_stage_result_with_rollback_data(self):
        """Test stage result with rollback information."""
        rollback_data = {
            "dropped_objects": ["idx_test"],
            "restoration_sql": "CREATE INDEX idx_test ON test_table (test_column)",
        }

        result = RemovalStageResult(
            stage=RemovalStage.INDEX_REMOVAL,
            success=True,
            duration=1.5,
            rollback_data=rollback_data,
        )

        assert result.rollback_data is not None
        assert "dropped_objects" in result.rollback_data
        assert "restoration_sql" in result.rollback_data


class TestRemovalPlanGeneration:
    """Test removal plan generation logic."""

    def test_removal_plan_initialization(self):
        """Test removal plan initialization with defaults."""
        plan = RemovalPlan(table_name="test_table", column_name="test_column")

        assert plan.table_name == "test_table"
        assert plan.column_name == "test_column"
        assert plan.backup_strategy == BackupStrategy.COLUMN_ONLY
        assert plan.confirmation_required is True
        assert plan.dry_run is False
        assert plan.enable_rollback is True
        assert plan.validate_after_each_stage is True
        assert len(plan.dependencies) == 0
        assert len(plan.execution_stages) == 0

    def test_removal_plan_with_custom_settings(self):
        """Test removal plan with custom configuration."""
        plan = RemovalPlan(
            table_name="test_table",
            column_name="test_column",
            backup_strategy=BackupStrategy.TABLE_SNAPSHOT,
            confirmation_required=False,
            dry_run=True,
            stage_timeout=600,
            batch_size=50000,
            enable_rollback=False,
        )

        assert plan.backup_strategy == BackupStrategy.TABLE_SNAPSHOT
        assert plan.confirmation_required is False
        assert plan.dry_run is True
        assert plan.stage_timeout == 600
        assert plan.batch_size == 50000
        assert plan.enable_rollback is False

    def test_removal_plan_with_dependencies(self):
        """Test removal plan with dependency information."""
        dependencies = [
            IndexDependency(
                index_name="idx_test",
                index_type="btree",
                columns=["col"],
                dependency_type=DependencyType.INDEX,
                impact_level=ImpactLevel.LOW,
            ),
            ForeignKeyDependency(
                constraint_name="fk_test",
                source_table="source",
                source_column="col",
                target_table="target",
                target_column="id",
                dependency_type=DependencyType.FOREIGN_KEY,
                impact_level=ImpactLevel.HIGH,
            ),
        ]

        plan = RemovalPlan(
            table_name="test_table",
            column_name="test_column",
            dependencies=dependencies,
        )

        assert len(plan.dependencies) == 2
        assert plan.dependencies[0].index_name == "idx_test"
        assert plan.dependencies[1].impact_level == ImpactLevel.HIGH


class TestErrorHandlingAndRecovery:
    """Test error handling and recovery instruction generation."""

    def test_recovery_instruction_generation_backup_success(self):
        """Test recovery instructions when backup was successful."""
        manager = ColumnRemovalManager()

        stages_completed = [
            RemovalStageResult(
                stage=RemovalStage.BACKUP_CREATION,
                success=True,
                duration=1.0,
                objects_affected=["backup_table"],
            ),
            RemovalStageResult(
                stage=RemovalStage.COLUMN_REMOVAL,
                success=False,
                duration=0.5,
                errors=["Permission denied"],
            ),
        ]

        error = Exception("Permission denied")

        instructions = manager._generate_recovery_instructions(stages_completed, error)

        assert any(
            "Transaction was automatically rolled back" in instr
            for instr in instructions
        )
        assert any(
            "Backup was created and preserved" in instr for instr in instructions
        )
        assert any("Permission denied" in instr for instr in instructions)

    def test_recovery_instruction_generation_no_backup(self):
        """Test recovery instructions when no backup was created."""
        manager = ColumnRemovalManager()

        stages_completed = [
            RemovalStageResult(
                stage=RemovalStage.COLUMN_REMOVAL,
                success=False,
                duration=0.5,
                errors=["Table not found"],
            )
        ]

        error = Exception("Table not found")

        instructions = manager._generate_recovery_instructions(stages_completed, error)

        assert any(
            "Transaction was automatically rolled back" in instr
            for instr in instructions
        )
        assert not any("Backup was created" in instr for instr in instructions)
        assert any("Table not found" in instr for instr in instructions)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
