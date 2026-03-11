#!/usr/bin/env python3
"""
Unit tests for ValidationCheckpoints system - Phase 2

Tests the validation checkpoint manager and individual checkpoint implementations.
Focuses on checkpoint execution, status management, and validation logic.

TIER 1 REQUIREMENTS:
- Fast execution (<1 second per test)
- Mock database connections and external dependencies
- Test all checkpoint types and edge cases
- Focus on checkpoint orchestration and validation logic
- Uses standardized unit test fixtures following Tier 1 testing policy
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Import existing components to mock
from dataflow.migrations.dependency_analyzer import DependencyAnalyzer, DependencyReport
from dataflow.migrations.risk_assessment_engine import RiskAssessmentEngine
from dataflow.migrations.staging_environment_manager import (
    ProductionDatabase,
    StagingDatabase,
    StagingEnvironment,
)

# Import the components we'll be testing (to be implemented)
from dataflow.migrations.validation_checkpoints import (
    BaseValidationCheckpoint,
    CheckpointResult,
    CheckpointStatus,
    CheckpointType,
    DataIntegrityCheckpoint,
    DependencyAnalysisCheckpoint,
    PerformanceValidationCheckpoint,
    RollbackValidationCheckpoint,
    SchemaConsistencyCheckpoint,
    ValidationCheckpointManager,
)


def create_mock_staging_environment():
    """Create a properly structured mock staging environment following Tier 1 policy."""
    from dataflow.migrations.staging_environment_manager import (
        ProductionDatabase,
        StagingDatabase,
    )

    # Create mock staging database object - using SQLite for unit tests
    mock_staging_db = Mock(spec=StagingDatabase)
    mock_staging_db.url = ":memory:"
    mock_staging_db.host = "localhost"
    mock_staging_db.port = None  # SQLite doesn't use ports
    mock_staging_db.database = ":memory:"
    mock_staging_db.user = None
    mock_staging_db.password = None
    mock_staging_db.connection_timeout = 30
    mock_staging_db.dialect = "sqlite"

    # Create mock production database object - using SQLite for unit tests
    mock_production_db = Mock(spec=ProductionDatabase)
    mock_production_db.url = ":memory:"
    mock_production_db.host = "localhost"
    mock_production_db.port = None  # SQLite doesn't use ports
    mock_production_db.database = ":memory:"
    mock_production_db.user = None
    mock_production_db.password = None
    mock_production_db.connection_timeout = 30
    mock_production_db.dialect = "sqlite"

    # Create staging environment with proper structure
    staging_env = Mock(spec=StagingEnvironment)
    staging_env.staging_id = "test_staging_001"
    staging_env.staging_db = mock_staging_db
    staging_env.production_db = mock_production_db

    return staging_env


class TestValidationCheckpointManager:
    """Test suite for ValidationCheckpointManager."""

    @pytest.fixture
    def checkpoint_manager(self):
        """Create ValidationCheckpointManager instance."""
        return ValidationCheckpointManager()

    @pytest.fixture
    def mock_staging_environment(self):
        """Mock staging environment."""
        return create_mock_staging_environment()

    def test_checkpoint_manager_initialization(self, checkpoint_manager):
        """Test checkpoint manager initialization."""
        assert checkpoint_manager is not None
        assert hasattr(checkpoint_manager, "checkpoints")
        assert isinstance(checkpoint_manager.checkpoints, dict)

    def test_register_checkpoint(self, checkpoint_manager):
        """Test checkpoint registration."""
        mock_checkpoint = Mock(spec=BaseValidationCheckpoint)
        mock_checkpoint.checkpoint_type = CheckpointType.DEPENDENCY_ANALYSIS

        checkpoint_manager.register_checkpoint(
            CheckpointType.DEPENDENCY_ANALYSIS, mock_checkpoint
        )

        assert CheckpointType.DEPENDENCY_ANALYSIS in checkpoint_manager.checkpoints
        assert (
            checkpoint_manager.checkpoints[CheckpointType.DEPENDENCY_ANALYSIS]
            == mock_checkpoint
        )

    def test_register_checkpoint_duplicate(self, checkpoint_manager):
        """Test registering duplicate checkpoint type."""
        mock_checkpoint1 = Mock(spec=BaseValidationCheckpoint)
        mock_checkpoint2 = Mock(spec=BaseValidationCheckpoint)

        checkpoint_manager.register_checkpoint(
            CheckpointType.DEPENDENCY_ANALYSIS, mock_checkpoint1
        )

        with pytest.raises(ValueError, match="Checkpoint type .* already registered"):
            checkpoint_manager.register_checkpoint(
                CheckpointType.DEPENDENCY_ANALYSIS, mock_checkpoint2
            )

    @pytest.mark.asyncio
    async def test_execute_checkpoint_success(
        self, checkpoint_manager, mock_staging_environment
    ):
        """Test successful checkpoint execution."""
        mock_checkpoint = AsyncMock(spec=BaseValidationCheckpoint)
        mock_result = CheckpointResult(
            checkpoint_type=CheckpointType.DEPENDENCY_ANALYSIS,
            status=CheckpointStatus.PASSED,
            message="No critical dependencies found",
            execution_time_seconds=0.5,
        )
        mock_checkpoint.execute = AsyncMock(return_value=mock_result)

        checkpoint_manager.register_checkpoint(
            CheckpointType.DEPENDENCY_ANALYSIS, mock_checkpoint
        )

        migration_info = {"table_name": "users", "column_name": "test_field"}

        result = await checkpoint_manager.execute_checkpoint(
            CheckpointType.DEPENDENCY_ANALYSIS,
            staging_environment=mock_staging_environment,
            migration_info=migration_info,
        )

        assert result == mock_result
        assert result.status == CheckpointStatus.PASSED
        mock_checkpoint.execute.assert_called_once_with(
            mock_staging_environment, migration_info
        )

    @pytest.mark.asyncio
    async def test_execute_checkpoint_not_registered(
        self, checkpoint_manager, mock_staging_environment
    ):
        """Test executing unregistered checkpoint type."""
        migration_info = {"table_name": "users", "column_name": "test_field"}

        with pytest.raises(ValueError, match="Checkpoint type .* not registered"):
            await checkpoint_manager.execute_checkpoint(
                CheckpointType.PERFORMANCE_VALIDATION,
                staging_environment=mock_staging_environment,
                migration_info=migration_info,
            )

    @pytest.mark.asyncio
    async def test_execute_checkpoint_failure(
        self, checkpoint_manager, mock_staging_environment
    ):
        """Test checkpoint execution failure handling."""
        mock_checkpoint = AsyncMock(spec=BaseValidationCheckpoint)
        mock_checkpoint.execute = AsyncMock(
            side_effect=Exception("Database connection failed")
        )

        checkpoint_manager.register_checkpoint(
            CheckpointType.DEPENDENCY_ANALYSIS, mock_checkpoint
        )

        migration_info = {"table_name": "users", "column_name": "test_field"}

        result = await checkpoint_manager.execute_checkpoint(
            CheckpointType.DEPENDENCY_ANALYSIS,
            staging_environment=mock_staging_environment,
            migration_info=migration_info,
        )

        assert result.status == CheckpointStatus.FAILED
        assert "Database connection failed" in result.message

    @pytest.mark.asyncio
    async def test_execute_all_checkpoints(
        self, checkpoint_manager, mock_staging_environment
    ):
        """Test executing all registered checkpoints."""
        # Register multiple checkpoints
        checkpoints = [
            (CheckpointType.DEPENDENCY_ANALYSIS, CheckpointStatus.PASSED),
            (CheckpointType.PERFORMANCE_VALIDATION, CheckpointStatus.PASSED),
            (CheckpointType.ROLLBACK_VALIDATION, CheckpointStatus.FAILED),
        ]

        for checkpoint_type, status in checkpoints:
            mock_checkpoint = AsyncMock(spec=BaseValidationCheckpoint)
            mock_result = CheckpointResult(
                checkpoint_type=checkpoint_type,
                status=status,
                message=f"Checkpoint {checkpoint_type.value} executed",
            )
            mock_checkpoint.execute = AsyncMock(return_value=mock_result)
            checkpoint_manager.register_checkpoint(checkpoint_type, mock_checkpoint)

        migration_info = {"table_name": "users", "column_name": "test_field"}

        results = await checkpoint_manager.execute_all_checkpoints(
            staging_environment=mock_staging_environment, migration_info=migration_info
        )

        assert len(results) == 3
        passed_count = len([r for r in results if r.status == CheckpointStatus.PASSED])
        failed_count = len([r for r in results if r.status == CheckpointStatus.FAILED])

        assert passed_count == 2
        assert failed_count == 1

    @pytest.mark.asyncio
    async def test_execute_checkpoints_parallel(
        self, checkpoint_manager, mock_staging_environment
    ):
        """Test parallel checkpoint execution."""
        # Register checkpoints with delays to test parallelism
        import asyncio

        async def delayed_execution(*args, **kwargs):
            await asyncio.sleep(0.1)
            return CheckpointResult(
                checkpoint_type=CheckpointType.DEPENDENCY_ANALYSIS,
                status=CheckpointStatus.PASSED,
                message="Delayed checkpoint completed",
            )

        mock_checkpoint1 = AsyncMock(spec=BaseValidationCheckpoint)
        mock_checkpoint2 = AsyncMock(spec=BaseValidationCheckpoint)
        mock_checkpoint1.execute = delayed_execution
        mock_checkpoint2.execute = delayed_execution

        checkpoint_manager.register_checkpoint(
            CheckpointType.DEPENDENCY_ANALYSIS, mock_checkpoint1
        )
        checkpoint_manager.register_checkpoint(
            CheckpointType.PERFORMANCE_VALIDATION, mock_checkpoint2
        )

        migration_info = {"table_name": "users", "column_name": "test_field"}

        start_time = datetime.now()
        results = await checkpoint_manager.execute_all_checkpoints(
            staging_environment=mock_staging_environment,
            migration_info=migration_info,
            parallel_execution=True,
        )
        execution_time = (datetime.now() - start_time).total_seconds()

        # Parallel execution should be faster than sequential
        assert (
            execution_time < 0.15
        )  # Should be ~0.1s for parallel vs ~0.2s for sequential
        assert len(results) == 2


class TestBaseValidationCheckpoint:
    """Test suite for BaseValidationCheckpoint."""

    @pytest.fixture
    def base_checkpoint(self):
        """Create BaseValidationCheckpoint instance."""

        class TestCheckpoint(BaseValidationCheckpoint):
            checkpoint_type = CheckpointType.DEPENDENCY_ANALYSIS

            async def execute(self, staging_environment, migration_info):
                return CheckpointResult(
                    checkpoint_type=self.checkpoint_type,
                    status=CheckpointStatus.PASSED,
                    message="Test checkpoint executed",
                )

        return TestCheckpoint()

    @pytest.mark.asyncio
    async def test_base_checkpoint_execution(self, base_checkpoint):
        """Test base checkpoint execution."""
        staging_env = create_mock_staging_environment()
        migration_info = {"table_name": "users", "column_name": "test_field"}

        result = await base_checkpoint.execute(staging_env, migration_info)

        assert isinstance(result, CheckpointResult)
        assert result.checkpoint_type == CheckpointType.DEPENDENCY_ANALYSIS
        assert result.status == CheckpointStatus.PASSED

    def test_base_checkpoint_validation(self):
        """Test base checkpoint validation methods."""

        # Test concrete implementation
        class ValidCheckpoint(BaseValidationCheckpoint):
            checkpoint_type = CheckpointType.DEPENDENCY_ANALYSIS

            async def execute(self, staging_environment, migration_info):
                pass

        checkpoint = ValidCheckpoint()
        assert checkpoint.checkpoint_type == CheckpointType.DEPENDENCY_ANALYSIS

        # Test abstract implementation fails
        with pytest.raises(TypeError):
            BaseValidationCheckpoint()


class TestDependencyAnalysisCheckpoint:
    """Test suite for DependencyAnalysisCheckpoint."""

    @pytest.fixture
    def mock_dependency_analyzer(self):
        """Mock DependencyAnalyzer."""
        analyzer = Mock(spec=DependencyAnalyzer)

        mock_report = Mock(spec=DependencyReport)
        mock_report.has_dependencies.return_value = False
        mock_report.get_critical_dependencies.return_value = []
        mock_report.get_total_dependency_count.return_value = 0
        mock_report.get_removal_recommendation.return_value = "SAFE"

        analyzer.analyze_column_dependencies = AsyncMock(return_value=mock_report)
        return analyzer

    @pytest.fixture
    def dependency_checkpoint(self, mock_dependency_analyzer):
        """Create DependencyAnalysisCheckpoint instance."""
        return DependencyAnalysisCheckpoint(
            dependency_analyzer=mock_dependency_analyzer
        )

    @pytest.mark.asyncio
    async def test_dependency_analysis_no_dependencies(self, dependency_checkpoint):
        """Test dependency analysis with no dependencies found."""
        staging_env = create_mock_staging_environment()
        migration_info = {"table_name": "users", "column_name": "unused_field"}

        # Mock the database connection to prevent real connections in unit tests
        with patch("asyncpg.connect") as mock_connect:
            mock_connection = AsyncMock()
            mock_connect.return_value = mock_connection

            result = await dependency_checkpoint.execute(staging_env, migration_info)

        assert result.status == CheckpointStatus.PASSED
        assert "no critical dependencies" in result.message.lower()
        assert result.checkpoint_type == CheckpointType.DEPENDENCY_ANALYSIS

    @pytest.mark.asyncio
    async def test_dependency_analysis_critical_dependencies(
        self, dependency_checkpoint, mock_dependency_analyzer
    ):
        """Test dependency analysis with critical dependencies."""
        # Mock critical dependencies
        mock_report = Mock(spec=DependencyReport)
        mock_report.has_dependencies.return_value = True
        mock_report.get_critical_dependencies.return_value = [
            Mock()
        ]  # Critical dependency
        mock_report.get_total_dependency_count.return_value = 1
        mock_report.get_removal_recommendation.return_value = "DANGEROUS"

        mock_dependency_analyzer.analyze_column_dependencies = AsyncMock(
            return_value=mock_report
        )

        staging_env = create_mock_staging_environment()
        migration_info = {
            "table_name": "users",
            "column_name": "id",  # Critical primary key column
        }

        # Mock the staging connection to avoid real database connection
        with patch.object(
            dependency_checkpoint, "_get_staging_connection"
        ) as mock_get_conn:
            mock_get_conn.return_value = AsyncMock()
            result = await dependency_checkpoint.execute(staging_env, migration_info)

        assert result.status == CheckpointStatus.FAILED
        assert "critical dependencies" in result.message.lower()
        assert result.details["critical_dependency_count"] == 1

    @pytest.mark.asyncio
    async def test_dependency_analysis_analyzer_failure(
        self, dependency_checkpoint, mock_dependency_analyzer
    ):
        """Test dependency analysis with analyzer failure."""
        mock_dependency_analyzer.analyze_column_dependencies = AsyncMock(
            side_effect=Exception("Database connection failed")
        )

        staging_env = create_mock_staging_environment()
        migration_info = {"table_name": "users", "column_name": "test_field"}

        result = await dependency_checkpoint.execute(staging_env, migration_info)

        assert result.status == CheckpointStatus.FAILED
        assert "dependency analysis failed" in result.message.lower()


class TestPerformanceValidationCheckpoint:
    """Test suite for PerformanceValidationCheckpoint."""

    @pytest.fixture
    def performance_checkpoint(self):
        """Create PerformanceValidationCheckpoint instance."""
        return PerformanceValidationCheckpoint(
            baseline_queries=[
                "SELECT COUNT(*) FROM users",
                "SELECT * FROM users LIMIT 100",
            ],
            performance_threshold=0.20,  # 20% degradation threshold
        )

    @pytest.mark.asyncio
    async def test_performance_validation_acceptable(self, performance_checkpoint):
        """Test performance validation with acceptable performance."""
        staging_env = create_mock_staging_environment()
        migration_info = {"table_name": "users", "column_name": "non_indexed_field"}

        # Mock the performance validator methods with proper object types
        from dataflow.migrations.performance_validator import (
            PerformanceBaseline,
            PerformanceBenchmark,
            PerformanceComparison,
            PerformanceMetrics,
        )

        # Create proper PerformanceBaseline object
        query_baselines = {
            "SELECT COUNT(*) FROM users": PerformanceMetrics(
                avg_execution_time=0.095,
                max_execution_time=0.1,
                min_execution_time=0.09,
                avg_memory_mb=10.5,
                avg_cpu_percent=15.2,
                sample_count=3,
            ),
            "SELECT * FROM users LIMIT 100": PerformanceMetrics(
                avg_execution_time=0.048,
                max_execution_time=0.05,
                min_execution_time=0.045,
                avg_memory_mb=8.3,
                avg_cpu_percent=12.1,
                sample_count=3,
            ),
        }

        mock_baseline = PerformanceBaseline(
            staging_environment_id="test_staging_001", query_baselines=query_baselines
        )

        # Create proper PerformanceBenchmark object
        query_benchmarks = {
            "SELECT COUNT(*) FROM users": PerformanceMetrics(
                avg_execution_time=0.1,
                max_execution_time=0.105,
                min_execution_time=0.095,
                avg_memory_mb=11.0,
                avg_cpu_percent=16.0,
                sample_count=3,
            ),
            "SELECT * FROM users LIMIT 100": PerformanceMetrics(
                avg_execution_time=0.05,
                max_execution_time=0.052,
                min_execution_time=0.048,
                avg_memory_mb=8.5,
                avg_cpu_percent=12.5,
                sample_count=3,
            ),
        }

        mock_benchmark = PerformanceBenchmark(
            staging_environment_id="test_staging_001", query_benchmarks=query_benchmarks
        )

        mock_validation_result = PerformanceComparison(
            baseline_environment_id="test_staging_001",
            benchmark_environment_id="test_staging_001",
            overall_degradation_percent=4.9,  # Small acceptable degradation
            worst_degradation_percent=5.2,
            is_acceptable_performance=True,
            degraded_queries=[],
            query_comparisons={
                "SELECT COUNT(*) FROM users": {"degradation": 5.2},
                "SELECT * FROM users LIMIT 100": {"degradation": 4.1},
            },
        )

        with patch.object(
            performance_checkpoint.performance_validator, "establish_baseline"
        ) as mock_establish:
            mock_establish.return_value = mock_baseline

            with patch.object(
                performance_checkpoint.performance_validator, "run_benchmark"
            ) as mock_run:
                mock_run.return_value = mock_benchmark

                with patch.object(
                    performance_checkpoint.performance_validator, "compare_performance"
                ) as mock_compare:
                    mock_compare.return_value = mock_validation_result

                    result = await performance_checkpoint.execute(
                        staging_env, migration_info
                    )

        assert result.status == CheckpointStatus.PASSED
        assert (
            "acceptable" in result.message.lower() or "passed" in result.message.lower()
        )

    @pytest.mark.asyncio
    async def test_performance_validation_degradation(self, performance_checkpoint):
        """Test performance validation with significant degradation."""
        staging_env = create_mock_staging_environment()
        migration_info = {
            "table_name": "users",
            "column_name": "indexed_field",  # Removing indexed field
        }

        # Mock the performance validator methods with proper object types
        from dataflow.migrations.performance_validator import (
            PerformanceBaseline,
            PerformanceBenchmark,
            PerformanceComparison,
            PerformanceMetrics,
        )

        # Create proper PerformanceBaseline object
        query_baselines = {
            "SELECT COUNT(*) FROM users": PerformanceMetrics(
                avg_execution_time=0.1,
                max_execution_time=0.11,
                min_execution_time=0.09,
                avg_memory_mb=10.0,
                avg_cpu_percent=15.0,
                sample_count=3,
            ),
            "SELECT * FROM users LIMIT 100": PerformanceMetrics(
                avg_execution_time=0.05,
                max_execution_time=0.055,
                min_execution_time=0.045,
                avg_memory_mb=8.0,
                avg_cpu_percent=12.0,
                sample_count=3,
            ),
        }

        mock_baseline = PerformanceBaseline(
            staging_environment_id="test_staging_001", query_baselines=query_baselines
        )

        # Create proper PerformanceBenchmark object showing significant degradation
        query_benchmarks = {
            "SELECT COUNT(*) FROM users": PerformanceMetrics(
                avg_execution_time=0.15,  # 50% slower
                max_execution_time=0.16,
                min_execution_time=0.14,
                avg_memory_mb=15.0,
                avg_cpu_percent=22.0,
                sample_count=3,
            ),
            "SELECT * FROM users LIMIT 100": PerformanceMetrics(
                avg_execution_time=0.08,  # 60% slower
                max_execution_time=0.085,
                min_execution_time=0.075,
                avg_memory_mb=12.0,
                avg_cpu_percent=18.0,
                sample_count=3,
            ),
        }

        mock_benchmark = PerformanceBenchmark(
            staging_environment_id="test_staging_001", query_benchmarks=query_benchmarks
        )

        # Mock validation result
        mock_validation_result = PerformanceComparison(
            baseline_environment_id="test_staging_001",
            benchmark_environment_id="test_staging_001",
            overall_degradation_percent=53.0,  # Average degradation
            worst_degradation_percent=60.0,
            is_acceptable_performance=False,
            degraded_queries=[
                "SELECT COUNT(*) FROM users",
                "SELECT * FROM users LIMIT 100",
            ],
            query_comparisons={
                "SELECT COUNT(*) FROM users": {"degradation": 50.0},
                "SELECT * FROM users LIMIT 100": {"degradation": 60.0},
            },
        )

        with patch.object(
            performance_checkpoint.performance_validator, "establish_baseline"
        ) as mock_establish:
            mock_establish.return_value = mock_baseline

            with patch.object(
                performance_checkpoint.performance_validator, "run_benchmark"
            ) as mock_run:
                mock_run.return_value = mock_benchmark

                with patch.object(
                    performance_checkpoint.performance_validator, "compare_performance"
                ) as mock_compare:
                    mock_compare.return_value = mock_validation_result

                    result = await performance_checkpoint.execute(
                        staging_env, migration_info
                    )

        assert result.status == CheckpointStatus.FAILED
        assert "performance degradation" in result.message.lower()


class TestRollbackValidationCheckpoint:
    """Test suite for RollbackValidationCheckpoint."""

    @pytest.fixture
    def rollback_checkpoint(self):
        """Create RollbackValidationCheckpoint instance."""
        return RollbackValidationCheckpoint()

    @pytest.mark.asyncio
    async def test_rollback_validation_success(self, rollback_checkpoint):
        """Test successful rollback validation."""
        staging_env = create_mock_staging_environment()
        migration_info = {
            "table_name": "users",
            "column_name": "test_field",
            "migration_sql": "ALTER TABLE users DROP COLUMN test_field",
            "rollback_sql": "ALTER TABLE users ADD COLUMN test_field VARCHAR(255)",
        }

        # Mock asyncpg.connect to avoid real database connection
        mock_connection = AsyncMock()
        mock_connection.execute = AsyncMock(return_value="OK")
        mock_connection.close = AsyncMock()
        # Mock fetch to return table structure showing column exists after rollback
        mock_connection.fetch = AsyncMock(
            return_value=[{"column_name": "test_field", "data_type": "varchar"}]
        )

        with patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_connection

            result = await rollback_checkpoint.execute(staging_env, migration_info)

        assert result.status == CheckpointStatus.PASSED
        assert (
            "rollback" in result.message.lower()
            and "successful" in result.message.lower()
        )

        # Verify both migration and rollback were executed
        assert mock_connection.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_rollback_validation_empty_rollback_sql(self, rollback_checkpoint):
        """Test rollback validation with empty rollback SQL."""
        staging_env = create_mock_staging_environment()
        migration_info = {
            "table_name": "users",
            "column_name": "test_field",
            "migration_sql": "ALTER TABLE users DROP COLUMN test_field",
            "rollback_sql": "",  # Empty rollback SQL
        }

        result = await rollback_checkpoint.execute(staging_env, migration_info)

        assert result.status == CheckpointStatus.FAILED
        assert "rollback sql is empty" in result.message.lower()

    @pytest.mark.asyncio
    async def test_rollback_validation_rollback_failure(self, rollback_checkpoint):
        """Test rollback validation with rollback execution failure."""
        staging_env = create_mock_staging_environment()
        migration_info = {
            "table_name": "users",
            "column_name": "test_field",
            "migration_sql": "ALTER TABLE users DROP COLUMN test_field",
            "rollback_sql": "ALTER TABLE users ADD COLUMN test_field VARCHAR(255)",
        }

        # Mock asyncpg.connect to simulate rollback failure
        mock_connection = AsyncMock()
        mock_connection.execute = AsyncMock()
        # First call (migration) succeeds, second call (rollback) fails
        mock_connection.execute.side_effect = [
            "OK",  # Migration succeeds
            Exception("Column already exists"),  # Rollback fails
        ]
        mock_connection.close = AsyncMock()

        with patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_connection

            result = await rollback_checkpoint.execute(staging_env, migration_info)

        assert result.status == CheckpointStatus.FAILED
        assert (
            "rollback" in result.message.lower() and "failed" in result.message.lower()
        )


class TestDataIntegrityCheckpoint:
    """Test suite for DataIntegrityCheckpoint."""

    @pytest.fixture
    def data_integrity_checkpoint(self):
        """Create DataIntegrityCheckpoint instance."""
        return DataIntegrityCheckpoint()

    @pytest.mark.asyncio
    async def test_data_integrity_validation_success(self, data_integrity_checkpoint):
        """Test successful data integrity validation."""
        staging_env = create_mock_staging_environment()
        migration_info = {"table_name": "users", "column_name": "optional_field"}

        # Mock all database operations to prevent real connections
        with (
            patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect,
            patch("aiosqlite.connect", new_callable=AsyncMock) as mock_sqlite_connect,
            patch.object(
                data_integrity_checkpoint, "_check_referential_integrity"
            ) as mock_ref_check,
            patch.object(
                data_integrity_checkpoint, "_check_constraint_violations"
            ) as mock_constraint_check,
        ):

            # Mock successful validation responses
            mock_ref_check.return_value = {"valid": True, "violations": []}
            mock_constraint_check.return_value = {"valid": True, "violations": []}

            # Mock database connections
            mock_conn = AsyncMock()
            mock_connect.return_value = mock_conn
            mock_sqlite_connect.return_value = mock_conn

            result = await data_integrity_checkpoint.execute(
                staging_env, migration_info
            )

        assert result.status == CheckpointStatus.PASSED
        assert "data integrity" in result.message.lower()
        assert "passed" in result.message.lower()

    @pytest.mark.asyncio
    async def test_data_integrity_validation_referential_violations(
        self, data_integrity_checkpoint
    ):
        """Test data integrity validation with referential integrity violations."""
        staging_env = create_mock_staging_environment()
        migration_info = {
            "table_name": "users",
            "column_name": "id",  # Primary key referenced by foreign keys
        }

        # Mock referential integrity violations with comprehensive database mocking
        with (
            patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect,
            patch("aiosqlite.connect", new_callable=AsyncMock) as mock_sqlite_connect,
            patch.object(
                data_integrity_checkpoint, "_check_referential_integrity"
            ) as mock_ref_check,
            patch.object(
                data_integrity_checkpoint, "_check_constraint_violations"
            ) as mock_constraint_check,
        ):

            # Mock referential integrity violations
            mock_ref_check.return_value = {
                "valid": False,
                "violations": [
                    "Foreign key constraint fk_orders_users would be violated"
                ],
            }
            mock_constraint_check.return_value = {"valid": True, "violations": []}

            # Mock database connections
            mock_conn = AsyncMock()
            mock_connect.return_value = mock_conn
            mock_sqlite_connect.return_value = mock_conn

            result = await data_integrity_checkpoint.execute(
                staging_env, migration_info
            )

        assert result.status == CheckpointStatus.FAILED
        assert "violations" in result.message.lower()
        assert len(result.details["violations"]) == 1


class TestCheckpointTypeEnum:
    """Test CheckpointType enumeration."""

    def test_checkpoint_type_values(self):
        """Test all CheckpointType enum values."""
        assert CheckpointType.DEPENDENCY_ANALYSIS.value == "dependency_analysis"
        assert CheckpointType.PERFORMANCE_VALIDATION.value == "performance_validation"
        assert CheckpointType.ROLLBACK_VALIDATION.value == "rollback_validation"
        assert CheckpointType.DATA_INTEGRITY.value == "data_integrity"
        assert CheckpointType.SCHEMA_CONSISTENCY.value == "schema_consistency"

    def test_checkpoint_type_uniqueness(self):
        """Test that all CheckpointType values are unique."""
        checkpoint_values = [ct.value for ct in CheckpointType]
        assert len(checkpoint_values) == len(set(checkpoint_values))


class TestCheckpointStatusEnum:
    """Test CheckpointStatus enumeration."""

    def test_checkpoint_status_values(self):
        """Test all CheckpointStatus enum values."""
        assert CheckpointStatus.PENDING.value == "pending"
        assert CheckpointStatus.IN_PROGRESS.value == "in_progress"
        assert CheckpointStatus.PASSED.value == "passed"
        assert CheckpointStatus.FAILED.value == "failed"
        assert CheckpointStatus.SKIPPED.value == "skipped"

    def test_checkpoint_status_final_states(self):
        """Test identification of final checkpoint states."""
        final_states = [
            CheckpointStatus.PASSED,
            CheckpointStatus.FAILED,
            CheckpointStatus.SKIPPED,
        ]
        intermediate_states = [CheckpointStatus.PENDING, CheckpointStatus.IN_PROGRESS]

        for status in final_states:
            assert status in [
                CheckpointStatus.PASSED,
                CheckpointStatus.FAILED,
                CheckpointStatus.SKIPPED,
            ]

        for status in intermediate_states:
            assert status not in final_states


class TestCheckpointResult:
    """Test CheckpointResult data structure."""

    def test_checkpoint_result_creation(self):
        """Test CheckpointResult creation with all fields."""
        result = CheckpointResult(
            checkpoint_type=CheckpointType.DEPENDENCY_ANALYSIS,
            status=CheckpointStatus.PASSED,
            message="No dependencies found",
            details={"dependency_count": 0},
            execution_time_seconds=1.5,
            timestamp=datetime.now(),
        )

        assert result.checkpoint_type == CheckpointType.DEPENDENCY_ANALYSIS
        assert result.status == CheckpointStatus.PASSED
        assert result.message == "No dependencies found"
        assert result.details["dependency_count"] == 0
        assert result.execution_time_seconds == 1.5

    def test_checkpoint_result_minimal_creation(self):
        """Test CheckpointResult creation with minimal fields."""
        result = CheckpointResult(
            checkpoint_type=CheckpointType.PERFORMANCE_VALIDATION,
            status=CheckpointStatus.FAILED,
            message="Performance threshold exceeded",
        )

        assert result.checkpoint_type == CheckpointType.PERFORMANCE_VALIDATION
        assert result.status == CheckpointStatus.FAILED
        assert result.message == "Performance threshold exceeded"
        assert result.details == {}  # Should default to empty dict
        assert result.execution_time_seconds == 0.0  # Should default to 0.0

    def test_checkpoint_result_is_successful(self):
        """Test checkpoint result success determination."""
        passed_result = CheckpointResult(
            checkpoint_type=CheckpointType.DEPENDENCY_ANALYSIS,
            status=CheckpointStatus.PASSED,
            message="Success",
        )

        failed_result = CheckpointResult(
            checkpoint_type=CheckpointType.DEPENDENCY_ANALYSIS,
            status=CheckpointStatus.FAILED,
            message="Failure",
        )

        # Test success identification
        assert passed_result.status == CheckpointStatus.PASSED
        assert failed_result.status == CheckpointStatus.FAILED
