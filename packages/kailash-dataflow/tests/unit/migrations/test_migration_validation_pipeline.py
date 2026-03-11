#!/usr/bin/env python3
"""
Unit tests for MigrationValidationPipeline - Phase 2

Tests the core migration validation pipeline functionality with mocked dependencies.
Focuses on pipeline orchestration, validation checkpoints, and integration logic.

TIER 1 REQUIREMENTS:
- Fast execution (<1 second per test)
- Mock external dependencies (StagingEnvironmentManager, database connections)
- Test all public methods and edge cases
- Focus on pipeline orchestration and validation logic
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from dataflow.migrations.dependency_analyzer import DependencyAnalyzer, DependencyReport

# Import the components we'll be testing (to be implemented)
from dataflow.migrations.migration_validation_pipeline import (
    MigrationValidationConfig,
    MigrationValidationPipeline,
    MigrationValidationResult,
    ValidationError,
    ValidationStatus,
)
from dataflow.migrations.performance_validator import (
    PerformanceBaseline,
    PerformanceBenchmark,
    PerformanceComparison,
    PerformanceValidator,
)
from dataflow.migrations.risk_assessment_engine import (
    ComprehensiveRiskAssessment,
    RiskAssessmentEngine,
    RiskLevel,
)

# Import existing components to mock
from dataflow.migrations.staging_environment_manager import (
    StagingEnvironment,
    StagingEnvironmentManager,
    StagingEnvironmentStatus,
)
from dataflow.migrations.validation_checkpoints import (
    CheckpointResult,
    CheckpointStatus,
    CheckpointType,
    ValidationCheckpointManager,
)


class TestMigrationValidationPipeline:
    """Test suite for MigrationValidationPipeline core functionality."""

    @pytest.fixture
    def mock_staging_manager(self):
        """Mock StagingEnvironmentManager."""
        staging_manager = Mock(spec=StagingEnvironmentManager)

        # Mock staging environment with proper attributes
        mock_staging_env = Mock(spec=StagingEnvironment)
        mock_staging_env.staging_id = "test_staging_001"
        mock_staging_env.status = StagingEnvironmentStatus.ACTIVE
        mock_staging_env.created_at = datetime.now()

        # Mock staging_db attribute with required fields
        mock_staging_db = Mock()
        mock_staging_db.host = "localhost"
        mock_staging_db.port = 5433
        mock_staging_db.database = "test_staging_db"
        mock_staging_db.user = "postgres"
        mock_staging_db.password = "password"
        mock_staging_db.connection_timeout = 30
        mock_staging_env.staging_db = mock_staging_db

        staging_manager.create_staging_environment = AsyncMock(
            return_value=mock_staging_env
        )
        staging_manager.replicate_production_schema = AsyncMock(return_value=Mock())
        staging_manager.cleanup_staging_environment = AsyncMock(
            return_value={"status": "SUCCESS"}
        )

        return staging_manager

    @pytest.fixture
    def mock_dependency_analyzer(self):
        """Mock DependencyAnalyzer."""
        analyzer = Mock(spec=DependencyAnalyzer)

        mock_report = Mock(spec=DependencyReport)
        mock_report.has_dependencies.return_value = False
        mock_report.get_critical_dependencies.return_value = []
        mock_report.get_total_dependency_count.return_value = 0

        analyzer.analyze_column_dependencies = AsyncMock(return_value=mock_report)
        return analyzer

    @pytest.fixture
    def mock_risk_engine(self):
        """Mock RiskAssessmentEngine."""
        risk_engine = Mock(spec=RiskAssessmentEngine)

        mock_assessment = Mock(spec=ComprehensiveRiskAssessment)
        mock_assessment.overall_score = 15.0
        mock_assessment.risk_level = RiskLevel.LOW
        mock_assessment.recommendations = []

        risk_engine.assess_migration_risk = AsyncMock(return_value=mock_assessment)
        return risk_engine

    @pytest.fixture
    def pipeline_config(self):
        """Standard pipeline configuration for tests."""
        return MigrationValidationConfig(
            staging_timeout_seconds=300,
            performance_baseline_queries=["SELECT COUNT(*) FROM users"],
            rollback_validation_enabled=True,
            data_integrity_checks_enabled=True,
            parallel_validation_enabled=True,
            max_validation_time_seconds=600,
            performance_degradation_threshold=0.20,  # 20% threshold
        )

    @pytest.fixture
    def validation_pipeline(
        self,
        mock_staging_manager,
        mock_dependency_analyzer,
        mock_risk_engine,
        pipeline_config,
    ):
        """Create MigrationValidationPipeline instance with mocked dependencies."""
        return MigrationValidationPipeline(
            staging_manager=mock_staging_manager,
            dependency_analyzer=mock_dependency_analyzer,
            risk_engine=mock_risk_engine,
            config=pipeline_config,
        )

    def test_pipeline_initialization(self, validation_pipeline, pipeline_config):
        """Test pipeline initialization with valid configuration."""
        assert validation_pipeline.config == pipeline_config
        assert validation_pipeline.staging_manager is not None
        assert validation_pipeline.dependency_analyzer is not None
        assert validation_pipeline.risk_engine is not None

    def test_pipeline_initialization_invalid_config(self):
        """Test pipeline initialization with invalid configuration."""
        with pytest.raises(ValueError, match="Configuration cannot be None"):
            MigrationValidationPipeline(
                staging_manager=Mock(),
                dependency_analyzer=Mock(),
                risk_engine=Mock(),
                config=None,
            )

    @pytest.mark.asyncio
    async def test_validate_migration_successful(
        self, validation_pipeline, mock_staging_manager
    ):
        """Test successful migration validation workflow."""
        # Setup migration info
        migration_info = {
            "migration_id": "test_migration_001",
            "table_name": "users",
            "column_name": "deprecated_field",
            "migration_sql": "ALTER TABLE users DROP COLUMN deprecated_field",
            "rollback_sql": "ALTER TABLE users ADD COLUMN deprecated_field VARCHAR(255)",
        }

        # Mock database connections for checkpoints
        with patch("asyncpg.connect") as mock_connect:
            mock_connection = AsyncMock()

            # Mock fetch to return table exists and column exists for schema consistency
            def fetch_side_effect(sql, *args):
                if "information_schema.tables" in sql:
                    # Table exists check
                    return [{"table_name": "users"}]
                elif "information_schema.columns" in sql:
                    # Column exists check - return deprecated_field exists
                    return [
                        {
                            "column_name": "deprecated_field",
                            "data_type": "character varying",
                        }
                    ]
                else:
                    return []

            mock_connection.fetch = AsyncMock(side_effect=fetch_side_effect)
            mock_connection.fetchval = AsyncMock(return_value=0)
            mock_connection.execute = AsyncMock(return_value="Command completed")
            mock_connection.close = AsyncMock()
            mock_connect.return_value = mock_connection

            # Mock psutil for performance metrics
            with patch("psutil.Process") as mock_process_class:
                mock_process = Mock()
                mock_process.memory_info.return_value.rss = 1024 * 1024 * 100  # 100MB
                mock_process_class.return_value = mock_process

                with patch("psutil.cpu_percent", return_value=15.0):
                    # Provide more time values to avoid StopIteration
                    time_values = [1000.0 + i * 0.1 for i in range(50)]
                    with patch(
                        "time.time",
                        side_effect=time_values,
                    ):
                        # Run validation
                        result = await validation_pipeline.validate_migration(
                            migration_info
                        )

        # Verify result
        assert isinstance(result, MigrationValidationResult)
        assert result.validation_status == ValidationStatus.PASSED
        assert result.migration_id == "test_migration_001"
        assert len(result.checkpoints) > 0
        assert result.overall_risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]
        assert result.staging_environment_id is not None

        # Verify staging manager was called
        mock_staging_manager.create_staging_environment.assert_called_once()
        mock_staging_manager.replicate_production_schema.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_migration_with_critical_dependencies(
        self, validation_pipeline, mock_dependency_analyzer
    ):
        """Test migration validation with critical dependencies."""
        # Setup critical dependency
        mock_report = Mock(spec=DependencyReport)
        mock_report.has_dependencies.return_value = True
        mock_report.get_critical_dependencies.return_value = [
            Mock()
        ]  # Has critical dependency
        mock_report.get_total_dependency_count.return_value = 1

        mock_dependency_analyzer.analyze_column_dependencies = AsyncMock(
            return_value=mock_report
        )

        migration_info = {
            "migration_id": "test_migration_002",
            "table_name": "users",
            "column_name": "id",  # Critical column with FK references
            "migration_sql": "ALTER TABLE users DROP COLUMN id",
            "rollback_sql": "-- Cannot rollback primary key drop",
        }

        # Mock database connections for checkpoints
        with patch("asyncpg.connect") as mock_connect:
            mock_connection = AsyncMock()
            mock_connection.fetch = AsyncMock(return_value=[{"table_name": "users"}])
            mock_connection.fetchval = AsyncMock(return_value=0)
            mock_connection.execute = AsyncMock(return_value="Command completed")
            mock_connection.close = AsyncMock()
            mock_connect.return_value = mock_connection

            # Run validation
            result = await validation_pipeline.validate_migration(migration_info)

        # Should fail validation due to critical dependencies or other issues
        assert result.validation_status == ValidationStatus.FAILED
        assert len(result.validation_errors) > 0
        # Check for various possible error messages
        assert any(
            "critical" in error.message.lower()
            or "dependencies" in error.message.lower()
            or "rollback" in error.message.lower()
            for error in result.validation_errors
        )

    @pytest.mark.asyncio
    async def test_validate_migration_performance_degradation(
        self, validation_pipeline
    ):
        """Test migration validation with performance degradation detection."""
        migration_info = {
            "migration_id": "test_migration_003",
            "table_name": "large_table",
            "column_name": "indexed_field",
            "migration_sql": "ALTER TABLE large_table DROP COLUMN indexed_field",
            "rollback_sql": "ALTER TABLE large_table ADD COLUMN indexed_field INTEGER",
        }

        # Mock database connections and performance checkpoint
        with patch("asyncpg.connect") as mock_connect:
            mock_connection = AsyncMock()
            mock_connection.fetch = AsyncMock(
                return_value=[{"table_name": "large_table"}]
            )
            mock_connection.fetchval = AsyncMock(return_value=0)
            mock_connection.execute = AsyncMock(return_value="Command completed")
            mock_connection.close = AsyncMock()
            mock_connect.return_value = mock_connection

            # Mock checkpoint manager to return performance degradation
            with patch.object(
                validation_pipeline.checkpoint_manager, "execute_checkpoint"
            ) as mock_exec_checkpoint:

                async def checkpoint_side_effect(checkpoint_type, *args):
                    if checkpoint_type == CheckpointType.PERFORMANCE_VALIDATION:
                        return CheckpointResult(
                            checkpoint_type=CheckpointType.PERFORMANCE_VALIDATION,
                            status=CheckpointStatus.FAILED,
                            message="Performance degradation exceeds threshold: 35%",
                            details={"degradation_percent": 35.0},
                            execution_time_seconds=0.1,
                            timestamp=datetime.now(),
                        )
                    else:
                        # Return passing result for other checkpoints
                        return CheckpointResult(
                            checkpoint_type=checkpoint_type,
                            status=CheckpointStatus.PASSED,
                            message="Checkpoint passed",
                            details={},
                            execution_time_seconds=0.1,
                            timestamp=datetime.now(),
                        )

                mock_exec_checkpoint.side_effect = checkpoint_side_effect

                # Run validation
                result = await validation_pipeline.validate_migration(migration_info)

                # Should fail due to performance degradation
                assert result.validation_status == ValidationStatus.FAILED
                assert any(
                    "performance" in error.message.lower()
                    or "degradation" in error.message.lower()
                    or "threshold" in error.message.lower()
                    for error in result.validation_errors
                )

    @pytest.mark.asyncio
    async def test_validate_migration_rollback_failure(self, validation_pipeline):
        """Test migration validation with rollback validation failure."""
        migration_info = {
            "migration_id": "test_migration_004",
            "table_name": "users",
            "column_name": "critical_field",
            "migration_sql": "ALTER TABLE users DROP COLUMN critical_field",
            "rollback_sql": "",  # Empty rollback SQL - should fail validation
        }

        # Run validation
        result = await validation_pipeline.validate_migration(migration_info)

        # Should fail due to invalid rollback
        assert result.validation_status == ValidationStatus.FAILED
        assert any(
            "rollback" in error.message.lower() for error in result.validation_errors
        )

    @pytest.mark.asyncio
    async def test_validate_migration_timeout(
        self, validation_pipeline, mock_staging_manager
    ):
        """Test migration validation timeout handling."""
        # Mock staging environment creation to take too long
        mock_staging_manager.create_staging_environment = AsyncMock(
            side_effect=asyncio.TimeoutError("Staging environment creation timed out")
        )

        migration_info = {
            "migration_id": "test_migration_005",
            "table_name": "users",
            "column_name": "test_field",
            "migration_sql": "ALTER TABLE users DROP COLUMN test_field",
            "rollback_sql": "ALTER TABLE users ADD COLUMN test_field VARCHAR(255)",
        }

        # Run validation
        result = await validation_pipeline.validate_migration(migration_info)

        # Should fail due to timeout
        assert result.validation_status == ValidationStatus.FAILED
        assert any(
            "timeout" in error.message.lower() or "timed out" in error.message.lower()
            for error in result.validation_errors
        )

    @pytest.mark.asyncio
    async def test_validate_migration_cleanup_on_failure(
        self, validation_pipeline, mock_staging_manager
    ):
        """Test that staging environment is cleaned up on validation failure."""
        # Mock staging creation success but later failure
        mock_staging_env = Mock(spec=StagingEnvironment)
        mock_staging_env.staging_id = "test_staging_cleanup"

        mock_staging_manager.create_staging_environment = AsyncMock(
            return_value=mock_staging_env
        )
        mock_staging_manager.replicate_production_schema = AsyncMock(
            side_effect=Exception("Schema replication failed")
        )

        migration_info = {
            "migration_id": "test_migration_006",
            "table_name": "users",
            "column_name": "test_field",
            "migration_sql": "ALTER TABLE users DROP COLUMN test_field",
            "rollback_sql": "ALTER TABLE users ADD COLUMN test_field VARCHAR(255)",
        }

        # Run validation
        result = await validation_pipeline.validate_migration(migration_info)

        # Should fail and cleanup staging environment
        assert result.validation_status == ValidationStatus.FAILED
        mock_staging_manager.cleanup_staging_environment.assert_called_once_with(
            "test_staging_cleanup"
        )

    @pytest.mark.asyncio
    async def test_get_validation_status(self, validation_pipeline):
        """Test getting validation status for ongoing migration."""
        # Mock ongoing validation
        validation_id = "test_validation_001"

        # Should return None for non-existent validation
        status = await validation_pipeline.get_validation_status(validation_id)
        assert status is None

        # Test with mocked active validation
        with patch.object(
            validation_pipeline, "_active_validations", {validation_id: Mock()}
        ):
            status = await validation_pipeline.get_validation_status(validation_id)
            assert status is not None

    @pytest.mark.asyncio
    async def test_cancel_validation(self, validation_pipeline):
        """Test cancellation of ongoing validation."""
        validation_id = "test_validation_cancel"

        # Should return False for non-existent validation
        cancelled = await validation_pipeline.cancel_validation(validation_id)
        assert cancelled is False

        # Test with mocked active validation
        mock_validation_task = Mock()
        mock_validation_task.cancel = Mock()

        with patch.object(
            validation_pipeline,
            "_active_validations",
            {validation_id: mock_validation_task},
        ):
            cancelled = await validation_pipeline.cancel_validation(validation_id)
            assert cancelled is True
            mock_validation_task.cancel.assert_called_once()

    def test_migration_validation_config_validation(self):
        """Test MigrationValidationConfig parameter validation."""
        # Test valid config
        config = MigrationValidationConfig(
            staging_timeout_seconds=300,
            performance_baseline_queries=["SELECT 1"],
            rollback_validation_enabled=True,
        )
        assert config.staging_timeout_seconds == 300

        # Test invalid timeout
        with pytest.raises(ValueError):
            MigrationValidationConfig(staging_timeout_seconds=-1)

        # Test invalid performance threshold
        with pytest.raises(ValueError):
            MigrationValidationConfig(performance_degradation_threshold=1.5)  # > 100%

    @pytest.mark.asyncio
    async def test_parallel_validation_checkpoints(self, validation_pipeline):
        """Test parallel execution of validation checkpoints."""
        migration_info = {
            "migration_id": "test_migration_parallel",
            "table_name": "users",
            "column_name": "test_field",
            "migration_sql": "ALTER TABLE users DROP COLUMN test_field",
            "rollback_sql": "ALTER TABLE users ADD COLUMN test_field VARCHAR(255)",
        }

        # Mock parallel checkpoint execution
        with patch.object(
            validation_pipeline, "_execute_checkpoints_parallel"
        ) as mock_parallel:
            mock_parallel.return_value = [
                CheckpointResult(
                    checkpoint_type=CheckpointType.DEPENDENCY_ANALYSIS,
                    status=CheckpointStatus.PASSED,
                    message="Dependency analysis passed",
                    details={},
                    execution_time_seconds=0.1,
                    timestamp=datetime.now(),
                ),
                CheckpointResult(
                    checkpoint_type=CheckpointType.PERFORMANCE_VALIDATION,
                    status=CheckpointStatus.PASSED,
                    message="Performance validation passed",
                    details={},
                    execution_time_seconds=0.1,
                    timestamp=datetime.now(),
                ),
                CheckpointResult(
                    checkpoint_type=CheckpointType.DATA_INTEGRITY,
                    status=CheckpointStatus.PASSED,
                    message="Data integrity passed",
                    details={},
                    execution_time_seconds=0.1,
                    timestamp=datetime.now(),
                ),
            ]

            result = await validation_pipeline.validate_migration(migration_info)

            # Should execute checkpoints in parallel when enabled
            mock_parallel.assert_called_once()
            assert result.validation_status == ValidationStatus.PASSED


class TestValidationStatusEnum:
    """Test ValidationStatus enumeration."""

    def test_validation_status_values(self):
        """Test all ValidationStatus enum values."""
        assert ValidationStatus.PENDING.value == "pending"
        assert ValidationStatus.IN_PROGRESS.value == "in_progress"
        assert ValidationStatus.PASSED.value == "passed"
        assert ValidationStatus.FAILED.value == "failed"
        assert ValidationStatus.CANCELLED.value == "cancelled"

    def test_validation_status_ordering(self):
        """Test ValidationStatus comparison for workflow ordering."""
        # Test logical ordering of validation states
        pending = ValidationStatus.PENDING
        in_progress = ValidationStatus.IN_PROGRESS
        passed = ValidationStatus.PASSED
        failed = ValidationStatus.FAILED
        cancelled = ValidationStatus.CANCELLED

        # Basic state validation
        assert pending != in_progress
        assert passed != failed
        assert failed != cancelled


class TestMigrationValidationResult:
    """Test MigrationValidationResult data structure."""

    def test_validation_result_creation(self):
        """Test creation of validation result with all fields."""
        result = MigrationValidationResult(
            migration_id="test_001",
            validation_status=ValidationStatus.PASSED,
            overall_risk_level=RiskLevel.LOW,
            checkpoints=[],
            validation_errors=[],
            staging_environment_id="staging_001",
            validation_duration_seconds=45.5,
            performance_impact_summary="No significant performance impact",
        )

        assert result.migration_id == "test_001"
        assert result.validation_status == ValidationStatus.PASSED
        assert result.overall_risk_level == RiskLevel.LOW
        assert result.validation_duration_seconds == 45.5

    def test_validation_result_with_errors(self):
        """Test validation result with validation errors."""
        errors = [
            ValidationError("Critical dependency found", "DEPENDENCY_ERROR"),
            ValidationError("Performance threshold exceeded", "PERFORMANCE_ERROR"),
        ]

        result = MigrationValidationResult(
            migration_id="test_002",
            validation_status=ValidationStatus.FAILED,
            validation_errors=errors,
        )

        assert len(result.validation_errors) == 2
        assert result.validation_status == ValidationStatus.FAILED
        assert any("critical dependency" in error.message.lower() for error in errors)

    def test_validation_result_summary_generation(self):
        """Test generation of validation result summary."""
        checkpoints = [
            CheckpointResult(
                checkpoint_type=CheckpointType.DEPENDENCY_ANALYSIS,
                status=CheckpointStatus.PASSED,
                message="Dependency analysis passed",
                details={},
                execution_time_seconds=0.1,
                timestamp=datetime.now(),
            ),
            CheckpointResult(
                checkpoint_type=CheckpointType.PERFORMANCE_VALIDATION,
                status=CheckpointStatus.FAILED,
                message="Performance validation failed",
                details={},
                execution_time_seconds=0.2,
                timestamp=datetime.now(),
            ),
            CheckpointResult(
                checkpoint_type=CheckpointType.ROLLBACK_VALIDATION,
                status=CheckpointStatus.PASSED,
                message="Rollback validation passed",
                details={},
                execution_time_seconds=0.1,
                timestamp=datetime.now(),
            ),
        ]

        result = MigrationValidationResult(
            migration_id="test_003",
            validation_status=ValidationStatus.FAILED,
            checkpoints=checkpoints,
        )

        # Should be able to analyze checkpoint results
        passed_checkpoints = [
            c for c in result.checkpoints if c.status == CheckpointStatus.PASSED
        ]
        failed_checkpoints = [
            c for c in result.checkpoints if c.status == CheckpointStatus.FAILED
        ]

        assert len(passed_checkpoints) == 2
        assert len(failed_checkpoints) == 1


class TestValidationError:
    """Test ValidationError data structure."""

    def test_validation_error_creation(self):
        """Test ValidationError creation and attributes."""
        error = ValidationError(
            message="Critical foreign key dependency detected",
            error_type="DEPENDENCY_ERROR",
            details={"constraint_name": "fk_users_orders", "impact": "critical"},
        )

        assert error.message == "Critical foreign key dependency detected"
        assert error.error_type == "DEPENDENCY_ERROR"
        assert error.details["constraint_name"] == "fk_users_orders"

    def test_validation_error_string_representation(self):
        """Test ValidationError string representation."""
        error = ValidationError("Test error", "TEST_ERROR")
        error_str = str(error)

        assert "Test error" in error_str
        assert "TEST_ERROR" in error_str
