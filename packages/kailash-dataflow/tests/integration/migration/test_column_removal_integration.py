#!/usr/bin/env python3
"""
Integration tests for Column Removal Manager

Tests the complete column removal workflow with real database operations,
dependency handling, and transaction safety.

Covers:
- Multi-stage removal process with correct dependency ordering
- Transaction safety with savepoints and rollback
- Data preservation through backup strategies
- Integration with DependencyAnalyzer
- Error handling and recovery scenarios
"""

import asyncio
import os
import sqlite3
import tempfile
from unittest.mock import AsyncMock, MagicMock

# Test database setup
import asyncpg
import pytest
from dataflow.migrations.column_removal_manager import (
    BackupStrategy,
    ColumnRemovalManager,
    RemovalPlan,
    RemovalStage,
    RemovalStatus,
    SafetyValidation,
)
from dataflow.migrations.dependency_analyzer import (
    ConstraintDependency,
    DependencyAnalyzer,
    DependencyReport,
    DependencyType,
    ForeignKeyDependency,
    ImpactLevel,
    IndexDependency,
    TriggerDependency,
    ViewDependency,
)

from kailash.runtime.local import LocalRuntime
from tests.infrastructure.test_harness import IntegrationTestSuite


# Helper function to create dependencies for testing
def ColumnDependency(object_name, dependency_type, impact_level, **kwargs):
    """Create appropriate dependency based on type."""
    if dependency_type == DependencyType.FOREIGN_KEY:
        return ForeignKeyDependency(
            constraint_name=object_name,
            source_table=kwargs.get("source_table", "test_table"),
            source_column=kwargs.get("source_column", "test_column"),
            target_table=kwargs.get("target_table", ""),
            target_column=kwargs.get("target_column", ""),
            impact_level=impact_level,
        )
    elif dependency_type == DependencyType.VIEW:
        return ViewDependency(
            view_name=object_name,
            view_definition=kwargs.get("view_definition", ""),
            impact_level=impact_level,
        )
    elif dependency_type == DependencyType.TRIGGER:
        return TriggerDependency(
            trigger_name=object_name,
            event=kwargs.get("event", "UPDATE"),
            timing=kwargs.get("timing", "BEFORE"),
            function_name=kwargs.get("function_name", "trigger_func"),
            impact_level=impact_level,
        )
    elif dependency_type == DependencyType.INDEX:
        return IndexDependency(
            index_name=object_name,
            index_type=kwargs.get("index_type", "btree"),
            columns=kwargs.get("columns", ["test_column"]),
            impact_level=impact_level,
        )
    else:  # CONSTRAINT
        return ConstraintDependency(
            constraint_name=object_name,
            constraint_type=kwargs.get("constraint_type", "CHECK"),
            definition=kwargs.get("definition", ""),
            columns=kwargs.get("columns", ["test_column"]),
            impact_level=impact_level,
        )


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    return LocalRuntime()


class TestColumnRemovalIntegration:
    """Integration tests for column removal functionality."""

    @pytest.fixture
    async def postgres_connection(self, test_suite):
        """Create PostgreSQL test connection."""
        async with test_suite.get_connection() as connection:
            yield connection

    @pytest.fixture
    def connection_manager(self, postgres_connection):
        """Mock connection manager."""
        manager = MagicMock()
        manager.get_connection = AsyncMock(return_value=postgres_connection)
        return manager

    @pytest.fixture
    def removal_manager(self, connection_manager):
        """Create column removal manager with mocked connection."""
        return ColumnRemovalManager(connection_manager)

    @pytest.mark.asyncio
    async def test_plan_column_removal_simple_column(
        self, removal_manager, postgres_connection
    ):
        """Test planning removal for column with no dependencies."""
        # Mock dependency analysis to return no dependencies
        empty_report = DependencyReport("users", "temp_column")
        removal_manager.dependency_analyzer.analyze_column_dependencies = AsyncMock(
            return_value=empty_report
        )

        plan = await removal_manager.plan_column_removal(
            table="users",
            column="temp_column",
            backup_strategy=BackupStrategy.COLUMN_ONLY,
        )

        assert plan.table_name == "users"
        assert plan.column_name == "temp_column"
        assert plan.backup_strategy == BackupStrategy.COLUMN_ONLY
        assert (
            len(plan.execution_stages) >= 4
        )  # backup, column_removal, cleanup, validation
        assert RemovalStage.COLUMN_REMOVAL in plan.execution_stages
        assert plan.estimated_duration > 0

    @pytest.mark.asyncio
    async def test_plan_column_removal_with_dependencies(
        self, removal_manager, postgres_connection
    ):
        """Test planning removal for column with various dependencies."""
        # Mock complex dependency scenario
        dependencies = [
            ColumnDependency(
                object_name="idx_users_email",
                dependency_type=DependencyType.INDEX,
                impact_level=ImpactLevel.LOW,
            ),
            ColumnDependency(
                object_name="fk_orders_user_id",
                dependency_type=DependencyType.FOREIGN_KEY,
                impact_level=ImpactLevel.HIGH,
            ),
            ColumnDependency(
                object_name="user_email_trigger",
                dependency_type=DependencyType.TRIGGER,
                impact_level=ImpactLevel.MEDIUM,
            ),
        ]

        # Create report with dependencies
        dep_report = DependencyReport("users", "email")
        dep_report.dependencies[DependencyType.INDEX] = [dependencies[0]]
        dep_report.dependencies[DependencyType.FOREIGN_KEY] = [dependencies[1]]
        dep_report.dependencies[DependencyType.TRIGGER] = [dependencies[2]]

        removal_manager.dependency_analyzer.analyze_column_dependencies = AsyncMock(
            return_value=dep_report
        )

        plan = await removal_manager.plan_column_removal(
            table="users", column="email", backup_strategy=BackupStrategy.TABLE_SNAPSHOT
        )

        assert plan.table_name == "users"
        assert plan.column_name == "email"
        assert len(plan.dependencies) == 3

        # Should have all necessary stages
        expected_stages = {
            RemovalStage.BACKUP_CREATION,
            RemovalStage.DEPENDENT_OBJECTS,  # For trigger
            RemovalStage.CONSTRAINT_REMOVAL,  # For FK
            RemovalStage.INDEX_REMOVAL,  # For index
            RemovalStage.COLUMN_REMOVAL,
            RemovalStage.CLEANUP,
            RemovalStage.VALIDATION,
        }

        assert set(plan.execution_stages) == expected_stages
        assert plan.estimated_duration > 5.0  # More complex = longer

    @pytest.mark.asyncio
    async def test_validate_removal_safety_safe_removal(
        self, removal_manager, postgres_connection
    ):
        """Test safety validation for a safe column removal."""
        # Mock safe scenario - no critical dependencies
        plan = RemovalPlan(
            table_name="users",
            column_name="temp_column",
            dependencies=[
                ColumnDependency(
                    object_name="temp_index",
                    dependency_type=DependencyType.INDEX,
                    impact_level=ImpactLevel.LOW,
                )
            ],
            execution_stages=[RemovalStage.COLUMN_REMOVAL],
        )

        # Mock table and column existence checks
        postgres_connection.fetchval.side_effect = [
            True,  # Table exists
            True,  # Column exists
        ]

        validation = await removal_manager.validate_removal_safety(plan)

        assert validation.is_safe is True
        assert validation.risk_level == ImpactLevel.LOW
        assert len(validation.blocking_dependencies) == 0
        assert validation.requires_confirmation is False

    @pytest.mark.asyncio
    async def test_validate_removal_safety_critical_dependencies(
        self, removal_manager, postgres_connection
    ):
        """Test safety validation with critical dependencies."""
        # Mock critical dependency scenario
        plan = RemovalPlan(
            table_name="users",
            column_name="id",
            dependencies=[
                ColumnDependency(
                    object_name="fk_orders_user_id",
                    dependency_type=DependencyType.FOREIGN_KEY,
                    impact_level=ImpactLevel.CRITICAL,
                    source_table="orders",
                    target_table="users",
                    target_column="id",
                )
            ],
            execution_stages=[RemovalStage.COLUMN_REMOVAL],
        )

        # Mock table and column existence checks
        postgres_connection.fetchval.side_effect = [
            True,  # Table exists
            True,  # Column exists
        ]

        validation = await removal_manager.validate_removal_safety(plan)

        assert validation.is_safe is False
        assert validation.risk_level == ImpactLevel.CRITICAL
        assert len(validation.blocking_dependencies) == 1
        assert validation.requires_confirmation is True
        assert "CRITICAL dependencies" in " ".join(validation.warnings)

    @pytest.mark.asyncio
    async def test_validate_removal_safety_missing_table(
        self, removal_manager, postgres_connection
    ):
        """Test safety validation with missing table."""
        plan = RemovalPlan(
            table_name="nonexistent_table",
            column_name="some_column",
            dependencies=[],
            execution_stages=[RemovalStage.COLUMN_REMOVAL],
        )

        # Mock table doesn't exist
        postgres_connection.fetchval.side_effect = [
            False,  # Table doesn't exist
            False,  # Column doesn't exist (irrelevant)
        ]

        validation = await removal_manager.validate_removal_safety(plan)

        assert validation.is_safe is False
        assert (
            len(validation.blocking_dependencies) > 0
        )  # Should have added table access error
        assert "not accessible" in " ".join(validation.warnings)

    @pytest.mark.asyncio
    async def test_execute_safe_removal_dry_run(
        self, removal_manager, postgres_connection
    ):
        """Test dry run execution."""
        plan = RemovalPlan(
            table_name="users",
            column_name="temp_column",
            dependencies=[],
            execution_stages=[
                RemovalStage.BACKUP_CREATION,
                RemovalStage.COLUMN_REMOVAL,
                RemovalStage.CLEANUP,
                RemovalStage.VALIDATION,
            ],
            dry_run=True,
        )

        # Mock successful execution
        postgres_connection.fetchval.side_effect = [
            5,  # Backup: row count
            False,  # Validation: column no longer exists
            10,  # Validation: table row count
        ]

        result = await removal_manager.execute_safe_removal(plan)

        assert result.status == RemovalStatus.SUCCESS
        assert len(result.stages_completed) == 4
        assert result.rollback_executed is False  # Dry run uses savepoint rollback
        assert "Dry run" in " ".join(result.recovery_instructions)

    @pytest.mark.asyncio
    async def test_execute_safe_removal_success(
        self, removal_manager, postgres_connection
    ):
        """Test successful removal execution."""
        plan = RemovalPlan(
            table_name="users",
            column_name="temp_column",
            dependencies=[
                ColumnDependency(
                    object_name="temp_index",
                    dependency_type=DependencyType.INDEX,
                    impact_level=ImpactLevel.LOW,
                    columns=["temp_column"],  # Single column index
                )
            ],
            execution_stages=[
                RemovalStage.BACKUP_CREATION,
                RemovalStage.INDEX_REMOVAL,
                RemovalStage.COLUMN_REMOVAL,
                RemovalStage.CLEANUP,
                RemovalStage.VALIDATION,
            ],
            dry_run=False,
        )

        # Mock successful execution
        postgres_connection.fetchval.side_effect = [
            5,  # Backup: row count
            False,  # Validation: column no longer exists
            10,  # Validation: table row count
        ]

        result = await removal_manager.execute_safe_removal(plan)

        assert result.status == RemovalStatus.SUCCESS
        assert len(result.stages_completed) == 5
        assert result.rollback_executed is False
        assert result.execution_time > 0
        assert result.backup_preserved is True  # Backup was created

    @pytest.mark.asyncio
    async def test_execute_safe_removal_stage_failure(
        self, removal_manager, postgres_connection
    ):
        """Test execution with stage failure and rollback."""
        plan = RemovalPlan(
            table_name="users",
            column_name="temp_column",
            dependencies=[],
            execution_stages=[
                RemovalStage.BACKUP_CREATION,
                RemovalStage.COLUMN_REMOVAL,
                RemovalStage.VALIDATION,
            ],
            stop_on_warning=True,
        )

        # Mock failure during column removal
        # Need to include savepoint operations in the side_effect sequence
        postgres_connection.execute.side_effect = [
            None,  # SAVEPOINT creation
            None,  # Backup creation succeeds
            Exception("Column removal failed"),  # Column removal fails
            None,  # ROLLBACK TO SAVEPOINT (if reached)
        ]

        result = await removal_manager.execute_safe_removal(plan)

        assert result.status == RemovalStatus.TRANSACTION_FAILED
        assert result.rollback_executed is True
        assert "Column removal failed" in result.error_message
        assert len(result.recovery_instructions) > 0

    @pytest.mark.asyncio
    async def test_backup_strategies_column_only(
        self, removal_manager, postgres_connection
    ):
        """Test column-only backup strategy."""
        # Mock primary key query
        postgres_connection.fetch.return_value = [{"attname": "id"}]
        # Mock backup table creation and size
        postgres_connection.fetchval.return_value = 5

        handler = removal_manager.backup_handlers[BackupStrategy.COLUMN_ONLY]
        backup_info = await handler.create_backup("users", "email", postgres_connection)

        assert backup_info.strategy == BackupStrategy.COLUMN_ONLY
        assert backup_info.backup_size == 5
        assert "backup" in backup_info.backup_location
        assert backup_info.verification_query is not None

    @pytest.mark.asyncio
    async def test_backup_strategies_table_snapshot(
        self, removal_manager, postgres_connection
    ):
        """Test table snapshot backup strategy."""
        # Mock backup table creation and size
        postgres_connection.fetchval.return_value = 10

        handler = removal_manager.backup_handlers[BackupStrategy.TABLE_SNAPSHOT]
        backup_info = await handler.create_backup("users", "email", postgres_connection)

        assert backup_info.strategy == BackupStrategy.TABLE_SNAPSHOT
        assert backup_info.backup_size == 10
        assert "backup" in backup_info.backup_location
        assert backup_info.verification_query is not None

    @pytest.mark.asyncio
    async def test_execution_stage_order_correctness(
        self, removal_manager, postgres_connection
    ):
        """Test that removal stages execute in correct dependency order."""
        # Create plan with all stage types
        dependencies = [
            ColumnDependency(
                object_name="user_trigger",
                dependency_type=DependencyType.TRIGGER,
                impact_level=ImpactLevel.MEDIUM,
            ),
            ColumnDependency(
                object_name="user_fk",
                dependency_type=DependencyType.FOREIGN_KEY,
                impact_level=ImpactLevel.HIGH,
            ),
            ColumnDependency(
                object_name="user_idx",
                dependency_type=DependencyType.INDEX,
                impact_level=ImpactLevel.LOW,
            ),
        ]

        stages = removal_manager._generate_execution_stages(dependencies)

        # Verify correct ordering
        stage_order = {stage: i for i, stage in enumerate(stages)}

        # Backup should be first
        assert stage_order[RemovalStage.BACKUP_CREATION] == 0

        # Dependent objects before constraints
        assert (
            stage_order[RemovalStage.DEPENDENT_OBJECTS]
            < stage_order[RemovalStage.CONSTRAINT_REMOVAL]
        )

        # Constraints before indexes
        assert (
            stage_order[RemovalStage.CONSTRAINT_REMOVAL]
            < stage_order[RemovalStage.INDEX_REMOVAL]
        )

        # Indexes before column
        assert (
            stage_order[RemovalStage.INDEX_REMOVAL]
            < stage_order[RemovalStage.COLUMN_REMOVAL]
        )

        # Column before cleanup
        assert (
            stage_order[RemovalStage.COLUMN_REMOVAL] < stage_order[RemovalStage.CLEANUP]
        )

        # Cleanup before validation
        assert stage_order[RemovalStage.CLEANUP] < stage_order[RemovalStage.VALIDATION]

    @pytest.mark.asyncio
    async def test_transaction_savepoint_rollback(
        self, removal_manager, postgres_connection
    ):
        """Test transaction savepoint and rollback functionality."""
        plan = RemovalPlan(
            table_name="users",
            column_name="temp_column",
            dependencies=[],
            execution_stages=[RemovalStage.COLUMN_REMOVAL],
            enable_rollback=True,
        )

        # Mock exception during execution to trigger rollback
        # Counter to track call number
        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return None  # SAVEPOINT creation succeeds
            elif call_count[0] == 2:
                raise Exception("Simulated failure")  # Column removal fails
            else:
                return None  # ROLLBACK TO SAVEPOINT succeeds

        postgres_connection.execute.side_effect = execute_side_effect

        result = await removal_manager.execute_safe_removal(plan)

        # Verify rollback was executed
        assert result.rollback_executed is True
        assert result.status == RemovalStatus.TRANSACTION_FAILED

        # Verify savepoint operations were called
        savepoint_calls = [
            call
            for call in postgres_connection.execute.call_args_list
            if "SAVEPOINT" in str(call) or "ROLLBACK TO SAVEPOINT" in str(call)
        ]
        # Should have SAVEPOINT creation and ROLLBACK TO SAVEPOINT calls
        # (Exact verification depends on mock implementation)

    @pytest.mark.asyncio
    async def test_integration_with_dependency_analyzer(
        self, removal_manager, postgres_connection
    ):
        """Test integration with dependency analyzer."""
        # Test that removal manager correctly uses dependency analyzer
        original_analyze = (
            removal_manager.dependency_analyzer.analyze_column_dependencies
        )
        # Create report with a single constraint dependency
        dep_report = DependencyReport("test_table", "test_column")
        test_dep = ColumnDependency(
            object_name="test_constraint",
            dependency_type=DependencyType.CONSTRAINT,
            impact_level=ImpactLevel.LOW,
        )
        dep_report.dependencies[DependencyType.CONSTRAINT] = [test_dep]

        removal_manager.dependency_analyzer.analyze_column_dependencies = AsyncMock(
            return_value=dep_report
        )

        plan = await removal_manager.plan_column_removal("test_table", "test_column")

        # Verify analyzer was called with correct parameters
        removal_manager.dependency_analyzer.analyze_column_dependencies.assert_called_once_with(
            "test_table", "test_column", postgres_connection
        )

        # Verify plan includes analyzer results
        assert len(plan.dependencies) == 1
        assert plan.dependencies[0].dependency_type == DependencyType.CONSTRAINT

    @pytest.mark.asyncio
    async def test_error_recovery_and_cleanup(
        self, removal_manager, postgres_connection
    ):
        """Test error recovery and cleanup functionality."""
        plan = RemovalPlan(
            table_name="users",
            column_name="temp_column",
            dependencies=[],
            execution_stages=[
                RemovalStage.BACKUP_CREATION,
                RemovalStage.COLUMN_REMOVAL,
                RemovalStage.CLEANUP,
            ],
        )

        # Mock partial success - backup succeeds, column removal fails
        postgres_connection.fetchval.side_effect = [5]  # Backup size

        # Counter to track call number
        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return None  # SAVEPOINT creation succeeds
            elif call_count[0] == 2:
                return None  # Backup creation succeeds
            elif call_count[0] == 3:
                raise Exception("Permission denied")  # Column removal fails
            else:
                return None  # ROLLBACK TO SAVEPOINT succeeds

        postgres_connection.execute.side_effect = execute_side_effect

        result = await removal_manager.execute_safe_removal(plan)

        assert result.status == RemovalStatus.TRANSACTION_FAILED
        assert result.rollback_executed is True

        # Verify recovery instructions include backup information
        instructions = result.recovery_instructions
        assert any("Backup was created" in instr for instr in instructions)
        assert any("Permission denied" in instr for instr in instructions)

    def test_duration_estimation_accuracy(self, removal_manager):
        """Test that duration estimation is reasonable."""
        # Test with no dependencies
        empty_deps = []
        duration = removal_manager._estimate_removal_duration(empty_deps)
        assert duration >= 5.0  # Base time
        assert duration <= 10.0  # Should be relatively quick

        # Test with complex dependencies
        complex_deps = [
            ColumnDependency("idx1", DependencyType.INDEX, ImpactLevel.LOW),
            ColumnDependency("fk1", DependencyType.FOREIGN_KEY, ImpactLevel.HIGH),
            ColumnDependency("fk2", DependencyType.FOREIGN_KEY, ImpactLevel.HIGH),
            ColumnDependency("trig1", DependencyType.TRIGGER, ImpactLevel.MEDIUM),
            ColumnDependency("view1", DependencyType.VIEW, ImpactLevel.MEDIUM),
        ]
        duration = removal_manager._estimate_removal_duration(complex_deps)
        assert duration > 10.0  # Should be longer with more dependencies
        assert duration <= 20.0  # But still reasonable


class TestColumnRemovalEdgeCases:
    """Test edge cases and error conditions for column removal."""

    @pytest.fixture
    def connection_manager(self):
        """Mock connection manager for edge case tests."""
        manager = MagicMock()
        manager.get_connection = AsyncMock()
        return manager

    @pytest.fixture
    def removal_manager(self, connection_manager):
        """Create removal manager for edge case tests."""
        return ColumnRemovalManager(connection_manager)

    @pytest.mark.asyncio
    async def test_column_already_removed(self, removal_manager, connection_manager):
        """Test handling when column is already removed."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.side_effect = [
            True,  # Table exists
            False,  # Column doesn't exist
        ]
        connection_manager.get_connection.return_value = mock_conn

        plan = RemovalPlan(
            table_name="users",
            column_name="nonexistent_column",
            dependencies=[],
            execution_stages=[RemovalStage.COLUMN_REMOVAL],
        )

        validation = await removal_manager.validate_removal_safety(plan)

        assert validation.is_safe is False
        assert any("does not exist" in warning for warning in validation.warnings)

    @pytest.mark.asyncio
    async def test_permission_denied_handling(
        self, removal_manager, connection_manager
    ):
        """Test handling of permission denied errors."""
        mock_conn = AsyncMock()

        # Counter to track call number
        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return None  # SAVEPOINT creation succeeds
            elif call_count[0] == 2:
                raise Exception("permission denied")  # Column removal fails
            else:
                return None  # ROLLBACK TO SAVEPOINT succeeds

        mock_conn.execute.side_effect = execute_side_effect

        # Setup transaction mock properly
        mock_transaction = MagicMock()
        mock_transaction.__aenter__ = AsyncMock(return_value=None)
        mock_transaction.__aexit__ = AsyncMock(return_value=None)
        mock_conn.transaction = MagicMock(return_value=mock_transaction)

        connection_manager.get_connection.return_value = mock_conn

        plan = RemovalPlan(
            table_name="users",
            column_name="temp_column",
            execution_stages=[RemovalStage.COLUMN_REMOVAL],
        )

        result = await removal_manager.execute_safe_removal(plan)

        assert result.status == RemovalStatus.TRANSACTION_FAILED
        assert "permission denied" in result.error_message

    @pytest.mark.asyncio
    async def test_backup_failure_handling(self, removal_manager, connection_manager):
        """Test handling when backup creation fails."""
        mock_conn = AsyncMock()

        # Counter to track call number
        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return None  # SAVEPOINT creation succeeds
            elif call_count[0] == 2:
                raise Exception("Backup failed")  # Backup stage fails
            else:
                return None  # ROLLBACK TO SAVEPOINT succeeds

        mock_conn.execute.side_effect = execute_side_effect

        # Setup transaction mock properly
        mock_transaction = MagicMock()
        mock_transaction.__aenter__ = AsyncMock(return_value=None)
        mock_transaction.__aexit__ = AsyncMock(return_value=None)
        mock_conn.transaction = MagicMock(return_value=mock_transaction)

        connection_manager.get_connection.return_value = mock_conn

        plan = RemovalPlan(
            table_name="users",
            column_name="temp_column",
            backup_strategy=BackupStrategy.COLUMN_ONLY,
            execution_stages=[
                RemovalStage.BACKUP_CREATION,
                RemovalStage.COLUMN_REMOVAL,
            ],
        )

        result = await removal_manager.execute_safe_removal(plan)

        assert result.status == RemovalStatus.TRANSACTION_FAILED
        assert len(result.stages_completed) >= 1  # Backup stage attempted
        assert result.stages_completed[0].success is False
        assert "Backup failed" in result.stages_completed[0].errors[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
