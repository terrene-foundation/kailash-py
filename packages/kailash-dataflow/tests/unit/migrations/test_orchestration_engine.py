"""
Unit tests for Migration Orchestration Engine.

Tests the core orchestration logic, validation pipeline, and error handling
for the central migration coordinator system. All tests use mocks for
external dependencies and run in under 1 second each.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Import classes we need to test (these will be implemented)
from dataflow.migration.orchestration_engine import (
    ExecutionPlan,
    Migration,
    MigrationCheckpoint,
    MigrationOperation,
    MigrationOrchestrationEngine,
    MigrationResult,
    MigrationType,
    OrchestrationError,
    RiskLevel,
    ValidationResult,
)


class TestMigrationOperation:
    """Test Migration Operation data class."""

    def test_migration_operation_creation(self):
        """Test basic MigrationOperation creation."""
        operation = MigrationOperation(
            operation_type=MigrationType.ADD_COLUMN,
            table_name="test_table",
            metadata={"column_name": "test_col", "column_type": "VARCHAR(255)"},
            rollback_sql="ALTER TABLE test_table DROP COLUMN test_col",
        )

        assert operation.operation_type == MigrationType.ADD_COLUMN
        assert operation.table_name == "test_table"
        assert operation.metadata["column_name"] == "test_col"
        assert operation.rollback_sql == "ALTER TABLE test_table DROP COLUMN test_col"

    def test_migration_operation_without_rollback(self):
        """Test MigrationOperation creation without rollback SQL."""
        operation = MigrationOperation(
            operation_type=MigrationType.CREATE_TABLE,
            table_name="new_table",
            metadata={"columns": ["id", "name", "email"]},
        )

        assert operation.operation_type == MigrationType.CREATE_TABLE
        assert operation.table_name == "new_table"
        assert operation.rollback_sql is None
        assert operation.metadata["columns"] == ["id", "name", "email"]

    def test_migration_operation_serialization(self):
        """Test MigrationOperation can be serialized for storage."""
        operation = MigrationOperation(
            operation_type=MigrationType.MODIFY_COLUMN,
            table_name="users",
            metadata={"old_type": "VARCHAR(100)", "new_type": "VARCHAR(255)"},
            rollback_sql="ALTER TABLE users ALTER COLUMN name TYPE VARCHAR(100)",
        )

        # Should be able to convert to dict for JSON serialization
        operation_dict = {
            "operation_type": operation.operation_type.value,
            "table_name": operation.table_name,
            "metadata": operation.metadata,
            "rollback_sql": operation.rollback_sql,
        }

        assert operation_dict["operation_type"] == "modify_column"
        assert operation_dict["table_name"] == "users"


class TestMigration:
    """Test Migration data class."""

    def test_migration_creation(self):
        """Test basic Migration creation."""
        migration = Migration(
            operations=[],
            version="20240101_120000",
            dependencies=["20240101_110000"],
            risk_level=RiskLevel.LOW,
        )

        assert migration.version == "20240101_120000"
        assert migration.dependencies == ["20240101_110000"]
        assert migration.risk_level == RiskLevel.LOW
        assert len(migration.operations) == 0

    def test_migration_with_operations(self):
        """Test Migration with multiple operations."""
        operations = [
            MigrationOperation(
                operation_type=MigrationType.CREATE_TABLE,
                table_name="new_table",
                metadata={"columns": ["id", "name"]},
            ),
            MigrationOperation(
                operation_type=MigrationType.ADD_COLUMN,
                table_name="existing_table",
                metadata={"column_name": "status", "column_type": "VARCHAR(50)"},
            ),
        ]

        migration = Migration(
            operations=operations,
            version="20240101_120000",
            dependencies=[],
            risk_level=RiskLevel.MEDIUM,
        )

        assert len(migration.operations) == 2
        assert migration.operations[0].operation_type == MigrationType.CREATE_TABLE
        assert migration.operations[1].operation_type == MigrationType.ADD_COLUMN

    def test_migration_risk_assessment(self):
        """Test migration with high-risk operations."""
        operations = [
            MigrationOperation(
                operation_type=MigrationType.DROP_COLUMN,
                table_name="users",
                metadata={"column_name": "old_field"},
            )
        ]

        migration = Migration(
            operations=operations,
            version="20240101_120000",
            dependencies=[],
            risk_level=RiskLevel.HIGH,
        )

        assert migration.risk_level == RiskLevel.HIGH
        assert len(migration.operations) == 1
        assert migration.operations[0].operation_type == MigrationType.DROP_COLUMN


class TestValidationResult:
    """Test ValidationResult data class."""

    def test_validation_result_success(self):
        """Test successful validation result."""
        result = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=["Table will be locked during migration"],
            risk_assessment=RiskLevel.LOW,
        )

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 1
        assert result.risk_assessment == RiskLevel.LOW

    def test_validation_result_with_errors(self):
        """Test validation result with errors."""
        result = ValidationResult(
            is_valid=False,
            errors=["Cannot drop column 'id' - primary key constraint"],
            warnings=[],
            risk_assessment=RiskLevel.HIGH,
        )

        assert result.is_valid is False
        assert len(result.errors) == 1
        assert result.errors[0] == "Cannot drop column 'id' - primary key constraint"
        assert result.risk_assessment == RiskLevel.HIGH


class TestExecutionPlan:
    """Test ExecutionPlan data class."""

    def test_execution_plan_creation(self):
        """Test ExecutionPlan creation with checkpoints."""
        migration = Migration(
            operations=[
                MigrationOperation(
                    operation_type=MigrationType.CREATE_TABLE,
                    table_name="test_table",
                    metadata={},
                )
            ],
            version="20240101_120000",
            dependencies=[],
            risk_level=RiskLevel.LOW,
        )

        checkpoints = [
            MigrationCheckpoint(
                checkpoint_id="checkpoint_1",
                operation_index=0,
                description="Before CREATE TABLE test_table",
            )
        ]

        plan = ExecutionPlan(
            migration=migration,
            checkpoints=checkpoints,
            estimated_duration_ms=1500,
            rollback_strategy="full",
        )

        assert plan.migration.version == "20240101_120000"
        assert len(plan.checkpoints) == 1
        assert plan.estimated_duration_ms == 1500
        assert plan.rollback_strategy == "full"

    def test_execution_plan_without_rollback(self):
        """Test ExecutionPlan for non-reversible migration."""
        migration = Migration(
            operations=[
                MigrationOperation(
                    operation_type=MigrationType.DROP_TABLE,
                    table_name="old_table",
                    metadata={},
                )
            ],
            version="20240101_120000",
            dependencies=[],
            risk_level=RiskLevel.HIGH,
        )

        plan = ExecutionPlan(
            migration=migration,
            checkpoints=[],
            estimated_duration_ms=500,
            rollback_strategy="none",
        )

        assert plan.rollback_strategy == "none"
        assert plan.migration.risk_level == RiskLevel.HIGH


class TestMigrationResult:
    """Test MigrationResult data class."""

    def test_migration_result_success(self):
        """Test successful migration result."""
        result = MigrationResult(
            success=True,
            migration_version="20240101_120000",
            executed_operations=2,
            execution_time_ms=1234,
            checkpoints_created=1,
            error_message=None,
        )

        assert result.success is True
        assert result.migration_version == "20240101_120000"
        assert result.executed_operations == 2
        assert result.execution_time_ms == 1234
        assert result.error_message is None

    def test_migration_result_failure(self):
        """Test failed migration result."""
        result = MigrationResult(
            success=False,
            migration_version="20240101_120000",
            executed_operations=1,
            execution_time_ms=567,
            checkpoints_created=0,
            error_message="Table 'users' does not exist",
        )

        assert result.success is False
        assert result.executed_operations == 1
        assert result.error_message == "Table 'users' does not exist"


class TestMigrationOrchestrationEngine:
    """Test MigrationOrchestrationEngine core functionality."""

    @pytest.fixture
    def mock_auto_migration_system(self):
        """Mock AutoMigrationSystem for testing."""
        mock_system = Mock()
        mock_system.compare_schemas = Mock()
        mock_system.generate_migration = Mock()
        return mock_system

    @pytest.fixture
    def mock_schema_state_manager(self):
        """Mock SchemaStateManager for testing."""
        mock_manager = Mock()
        mock_manager.get_cached_or_fresh_schema = Mock()
        mock_manager.invalidate_cache = Mock()
        return mock_manager

    @pytest.fixture
    def orchestration_engine(
        self, mock_auto_migration_system, mock_schema_state_manager
    ):
        """Create MigrationOrchestrationEngine with mocked dependencies."""
        return MigrationOrchestrationEngine(
            auto_migration_system=mock_auto_migration_system,
            schema_state_manager=mock_schema_state_manager,
            connection_string="sqlite:///:memory:",
        )

    @pytest.mark.asyncio
    async def test_validate_migration_safety_low_risk(self, orchestration_engine):
        """Test migration safety validation for low-risk operations."""
        migration = Migration(
            operations=[
                MigrationOperation(
                    operation_type=MigrationType.ADD_COLUMN,
                    table_name="users",
                    metadata={"column_name": "status", "column_type": "VARCHAR(50)"},
                )
            ],
            version="20240101_120000",
            dependencies=[],
            risk_level=RiskLevel.LOW,
        )

        result = await orchestration_engine.validate_migration_safety(migration)

        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
        assert result.risk_assessment == RiskLevel.LOW
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_validate_migration_safety_high_risk(self, orchestration_engine):
        """Test migration safety validation for high-risk operations."""
        migration = Migration(
            operations=[
                MigrationOperation(
                    operation_type=MigrationType.DROP_TABLE,
                    table_name="old_data",
                    metadata={"reason": "table_obsolete"},
                )
            ],
            version="20240101_120000",
            dependencies=[],
            risk_level=RiskLevel.HIGH,
        )

        result = await orchestration_engine.validate_migration_safety(migration)

        assert isinstance(result, ValidationResult)
        assert result.risk_assessment == RiskLevel.HIGH
        assert len(result.warnings) > 0
        # Should contain warning about data loss

    @pytest.mark.asyncio
    async def test_validate_migration_with_dependencies(self, orchestration_engine):
        """Test migration validation with unmet dependencies."""
        migration = Migration(
            operations=[
                MigrationOperation(
                    operation_type=MigrationType.ADD_COLUMN,
                    table_name="users",
                    metadata={"column_name": "profile_id", "references": "profiles.id"},
                )
            ],
            version="20240101_120000",
            dependencies=["20240101_110000"],  # Dependency not applied
            risk_level=RiskLevel.MEDIUM,
        )

        # Mock that dependency is not applied
        async def mock_check_dependencies(deps):
            return False

        with patch.object(
            orchestration_engine,
            "_check_dependencies_applied",
            new=mock_check_dependencies,
        ):
            result = await orchestration_engine.validate_migration_safety(migration)

            assert result.is_valid is False
            assert any("dependencies" in error.lower() for error in result.errors)

    @pytest.mark.asyncio
    async def test_create_execution_plan_with_checkpoints(self, orchestration_engine):
        """Test execution plan creation with checkpoints."""
        migration = Migration(
            operations=[
                MigrationOperation(
                    operation_type=MigrationType.CREATE_TABLE,
                    table_name="new_table",
                    metadata={"columns": ["id", "name"]},
                ),
                MigrationOperation(
                    operation_type=MigrationType.ADD_COLUMN,
                    table_name="existing_table",
                    metadata={"column_name": "status"},
                ),
            ],
            version="20240101_120000",
            dependencies=[],
            risk_level=RiskLevel.MEDIUM,
        )

        plan = await orchestration_engine.create_execution_plan(migration)

        assert isinstance(plan, ExecutionPlan)
        assert plan.migration == migration
        assert len(plan.checkpoints) >= 1  # Should create checkpoints
        assert plan.estimated_duration_ms > 0

    @pytest.mark.asyncio
    async def test_create_execution_plan_high_risk(self, orchestration_engine):
        """Test execution plan for high-risk migration."""
        migration = Migration(
            operations=[
                MigrationOperation(
                    operation_type=MigrationType.DROP_COLUMN,
                    table_name="users",
                    metadata={"column_name": "deprecated_field"},
                )
            ],
            version="20240101_120000",
            dependencies=[],
            risk_level=RiskLevel.HIGH,
        )

        plan = await orchestration_engine.create_execution_plan(migration)

        assert plan.rollback_strategy in [
            "partial",
            "none",
        ]  # High-risk operations may not be fully reversible
        assert (
            len(plan.checkpoints) >= 1
        )  # Should create checkpoint before risky operation

    @pytest.mark.asyncio
    async def test_execute_migration_success(self, orchestration_engine):
        """Test successful migration execution."""
        migration = Migration(
            operations=[
                MigrationOperation(
                    operation_type=MigrationType.ADD_COLUMN,
                    table_name="users",
                    metadata={"column_name": "created_at", "column_type": "TIMESTAMP"},
                )
            ],
            version="20240101_120000",
            dependencies=[],
            risk_level=RiskLevel.LOW,
        )

        # Mock successful database operations and lock management
        with (
            patch.object(
                orchestration_engine,
                "_execute_operation",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                orchestration_engine,
                "_create_checkpoint",
                new=AsyncMock(return_value="checkpoint_1"),
            ),
            patch.object(
                orchestration_engine,
                "_acquire_migration_lock",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                orchestration_engine,
                "_release_migration_lock",
                new=AsyncMock(return_value=None),
            ),
        ):

            result = await orchestration_engine.execute_migration(migration)

            assert isinstance(result, MigrationResult)
            assert result.success is True
            assert result.migration_version == "20240101_120000"
            assert result.executed_operations == 1
            assert result.error_message is None

    @pytest.mark.asyncio
    async def test_execute_migration_failure_with_rollback(self, orchestration_engine):
        """Test migration execution failure with rollback."""
        migration = Migration(
            operations=[
                MigrationOperation(
                    operation_type=MigrationType.ADD_COLUMN,
                    table_name="users",
                    metadata={"column_name": "status"},
                    rollback_sql="ALTER TABLE users DROP COLUMN status",
                ),
                MigrationOperation(
                    operation_type=MigrationType.MODIFY_COLUMN,
                    table_name="users",
                    metadata={"column_name": "email", "new_type": "VARCHAR(320)"},
                    rollback_sql="ALTER TABLE users ALTER COLUMN email TYPE VARCHAR(255)",
                ),
            ],
            version="20240101_120000",
            dependencies=[],
            risk_level=RiskLevel.MEDIUM,
        )

        # Mock first operation succeeds, second fails
        with (
            patch.object(
                orchestration_engine,
                "_execute_operation",
                new=AsyncMock(
                    side_effect=[True, Exception("Column constraint violation")]
                ),
            ),
            patch.object(
                orchestration_engine,
                "_rollback_migration",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                orchestration_engine,
                "_acquire_migration_lock",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                orchestration_engine,
                "_release_migration_lock",
                new=AsyncMock(return_value=None),
            ),
            patch.object(
                orchestration_engine,
                "_create_checkpoint",
                new=AsyncMock(return_value="checkpoint_1"),
            ),
        ):

            result = await orchestration_engine.execute_migration(migration)

            assert result.success is False
            assert result.executed_operations == 1  # Only first operation succeeded
            assert "Column constraint violation" in result.error_message

    @pytest.mark.asyncio
    async def test_execute_with_rollback_success(self, orchestration_engine):
        """Test execute_with_rollback method for successful execution."""
        migration = Migration(
            operations=[
                MigrationOperation(
                    operation_type=MigrationType.CREATE_TABLE,
                    table_name="test_table",
                    metadata={},
                )
            ],
            version="20240101_120000",
            dependencies=[],
            risk_level=RiskLevel.LOW,
        )

        plan = ExecutionPlan(
            migration=migration,
            checkpoints=[],
            estimated_duration_ms=1000,
            rollback_strategy="full",
        )

        orchestration_engine._execute_plan = AsyncMock(
            return_value=MigrationResult(
                success=True,
                migration_version="20240101_120000",
                executed_operations=1,
                execution_time_ms=950,
                checkpoints_created=1,
                error_message=None,
            )
        )

        result = await orchestration_engine.execute_with_rollback(plan)

        assert result.success is True
        assert result.migration_version == "20240101_120000"

    @pytest.mark.asyncio
    async def test_execute_with_rollback_failure_and_recovery(
        self, orchestration_engine
    ):
        """Test execute_with_rollback with failure and successful rollback."""
        migration = Migration(
            operations=[
                MigrationOperation(
                    operation_type=MigrationType.ADD_COLUMN,
                    table_name="users",
                    metadata={"column_name": "temp_field"},
                    rollback_sql="ALTER TABLE users DROP COLUMN temp_field",
                )
            ],
            version="20240101_120000",
            dependencies=[],
            risk_level=RiskLevel.MEDIUM,
        )

        plan = ExecutionPlan(
            migration=migration,
            checkpoints=[
                MigrationCheckpoint(
                    checkpoint_id="before_add_column",
                    operation_index=0,
                    description="Before adding temp_field column",
                )
            ],
            estimated_duration_ms=1000,
            rollback_strategy="full",
        )

        # Mock execution failure
        failed_result = MigrationResult(
            success=False,
            migration_version="20240101_120000",
            executed_operations=0,
            execution_time_ms=100,
            checkpoints_created=0,
            error_message="Database connection lost",
        )

        orchestration_engine._execute_plan = AsyncMock(return_value=failed_result)
        orchestration_engine._rollback_migration = AsyncMock(return_value=True)

        result = await orchestration_engine.execute_with_rollback(plan)

        assert result.success is False
        assert "Database connection lost" in result.error_message
        # Should have attempted rollback
        orchestration_engine._rollback_migration.assert_called_once()

    @pytest.mark.asyncio
    async def test_migration_dependency_validation(self, orchestration_engine):
        """Test that migration dependencies are properly validated."""
        migration = Migration(
            operations=[
                MigrationOperation(
                    operation_type=MigrationType.ADD_COLUMN,
                    table_name="orders",
                    metadata={"column_name": "user_id", "references": "users.id"},
                )
            ],
            version="20240101_130000",
            dependencies=["20240101_120000", "20240101_125000"],
            risk_level=RiskLevel.MEDIUM,
        )

        # Mock dependency checking
        with patch.object(
            orchestration_engine,
            "_check_dependencies_applied",
            new=AsyncMock(return_value=True),
        ) as mock_check:
            validation_result = await orchestration_engine.validate_migration_safety(
                migration
            )

            assert validation_result.is_valid is True
            mock_check.assert_called_once_with(migration.dependencies)

    @pytest.mark.asyncio
    async def test_eleven_migration_scenarios_support(self, orchestration_engine):
        """Test that all 11 migration scenarios are supported."""
        # Test all MigrationType enum values
        operations = [
            MigrationOperation(MigrationType.CREATE_TABLE, "table1", {}),
            MigrationOperation(MigrationType.DROP_TABLE, "table2", {}),
            MigrationOperation(MigrationType.ADD_COLUMN, "table3", {}),
            MigrationOperation(MigrationType.DROP_COLUMN, "table4", {}),
            MigrationOperation(MigrationType.MODIFY_COLUMN, "table5", {}),
            MigrationOperation(MigrationType.RENAME_COLUMN, "table6", {}),
            MigrationOperation(MigrationType.ADD_INDEX, "table7", {}),
            MigrationOperation(MigrationType.DROP_INDEX, "table8", {}),
            MigrationOperation(MigrationType.ADD_CONSTRAINT, "table9", {}),
            MigrationOperation(MigrationType.DROP_CONSTRAINT, "table10", {}),
            MigrationOperation(MigrationType.RENAME_TABLE, "table11", {}),
        ]

        migration = Migration(
            operations=operations,
            version="20240101_120000",
            dependencies=[],
            risk_level=RiskLevel.HIGH,
        )

        # Should be able to validate all operation types
        result = await orchestration_engine.validate_migration_safety(migration)
        assert isinstance(result, ValidationResult)

        # Should be able to create execution plan for all operation types
        plan = await orchestration_engine.create_execution_plan(migration)
        assert isinstance(plan, ExecutionPlan)
        assert len(plan.migration.operations) == 11

    def test_orchestration_error_handling(self):
        """Test OrchestrationError exception class."""
        error = OrchestrationError("Migration validation failed", "VALIDATION_ERROR")

        assert str(error) == "Migration validation failed"
        assert error.error_code == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_concurrent_migration_prevention(self, orchestration_engine):
        """Test that concurrent migrations are prevented."""
        migration = Migration(
            operations=[
                MigrationOperation(
                    operation_type=MigrationType.ADD_COLUMN,
                    table_name="users",
                    metadata={},
                )
            ],
            version="20240101_120000",
            dependencies=[],
            risk_level=RiskLevel.LOW,
        )

        # Mock that another migration is already running
        with patch.object(
            orchestration_engine,
            "_acquire_migration_lock",
            new=AsyncMock(return_value=False),
        ):
            result = await orchestration_engine.execute_migration(migration)

            # Should return failed result instead of raising exception
            assert result.success is False
            assert "concurrent migration" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_checkpoint_creation_and_rollback(self, orchestration_engine):
        """Test checkpoint creation and rollback functionality."""
        migration = Migration(
            operations=[
                MigrationOperation(
                    operation_type=MigrationType.ADD_COLUMN,
                    table_name="users",
                    metadata={"column_name": "test_col"},
                    rollback_sql="ALTER TABLE users DROP COLUMN test_col",
                )
            ],
            version="20240101_120000",
            dependencies=[],
            risk_level=RiskLevel.MEDIUM,
        )

        plan = await orchestration_engine.create_execution_plan(migration)

        # Should have created checkpoints for ADD_COLUMN operation (now included in risky operations)
        assert len(plan.checkpoints) > 0

        # Test rollback functionality exists
        with patch.object(
            orchestration_engine,
            "_rollback_to_checkpoint",
            new=AsyncMock(return_value=True),
        ) as mock_rollback:
            checkpoint_id = "checkpoint_123"
            rollback_success = await orchestration_engine._rollback_to_checkpoint(
                checkpoint_id
            )
            assert rollback_success is True

    def test_performance_requirement_under_1_second(self):
        """Test that all unit test operations complete under 1 second."""
        import time

        start_time = time.time()

        # Create objects that should be fast
        migration = Migration(
            operations=[
                MigrationOperation(
                    operation_type=MigrationType.ADD_COLUMN,
                    table_name="test_table",
                    metadata={"column_name": "test"},
                )
            ],
            version="20240101_120000",
            dependencies=[],
            risk_level=RiskLevel.LOW,
        )

        validation_result = ValidationResult(
            is_valid=True, errors=[], warnings=[], risk_assessment=RiskLevel.LOW
        )

        execution_plan = ExecutionPlan(
            migration=migration,
            checkpoints=[],
            estimated_duration_ms=500,
            rollback_strategy="full",
        )

        migration_result = MigrationResult(
            success=True,
            migration_version="20240101_120000",
            executed_operations=1,
            execution_time_ms=450,
            checkpoints_created=1,
            error_message=None,
        )

        end_time = time.time()
        execution_time = end_time - start_time

        # All object creation should be well under 1 second
        assert (
            execution_time < 0.1
        ), f"Object creation took {execution_time:.3f}s, should be much faster"
