#!/usr/bin/env python3
"""
Integration tests for MigrationValidationPipeline - Phase 2

Tests the migration validation pipeline with real PostgreSQL staging environments.
Focuses on real database operations, actual staging validation, and component integration.

TIER 2 REQUIREMENTS:
- Real PostgreSQL database operations (NO MOCKING)
- Docker test environment: ./tests/utils/test-env up && ./tests/utils/test-env status
- Real staging environment management
- Actual migration execution and validation
- Complete validation checkpoints with real database testing
- Integration with Phase 1 StagingEnvironmentManager
- Timeout: <5 seconds per test
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest

from kailash.runtime.local import LocalRuntime
from tests.infrastructure.test_harness import IntegrationTestSuite

# Set up logging for integration tests
logging.basicConfig(level=logging.INFO)

# Import real components (NO MOCKS)
from dataflow.migrations.migration_validation_pipeline import (
    MigrationValidationConfig,
    MigrationValidationPipeline,
    MigrationValidationResult,
    ValidationError,
    ValidationStatus,
)
from dataflow.migrations.performance_validator import (
    PerformanceValidationConfig,
    PerformanceValidator,
)
from dataflow.migrations.staging_environment_manager import (
    ProductionDatabase,
    StagingDatabase,
    StagingEnvironmentConfig,
    StagingEnvironmentManager,
)
from dataflow.migrations.validation_checkpoints import (
    CheckpointResult,
    CheckpointStatus,
    CheckpointType,
    ValidationCheckpointManager,
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


from dataflow.migrations.dependency_analyzer import DependencyAnalyzer, DependencyReport
from dataflow.migrations.risk_assessment_engine import RiskAssessmentEngine, RiskLevel

# Test database configuration
TEST_DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "database": "dataflow_test",
    "user": "dataflow_test",
    "password": "dataflow_test_password",
}


@pytest.fixture
async def real_staging_manager():
    """Create real StagingEnvironmentManager with test database configuration."""
    config = StagingEnvironmentConfig(
        default_data_sample_size=0.01,  # 1% for fast testing
        max_staging_environments=2,
        cleanup_timeout_seconds=60,
        auto_cleanup_hours=1,  # Quick cleanup for tests
    )

    manager = StagingEnvironmentManager(config=config)
    yield manager

    # Cleanup any remaining staging environments
    try:
        for staging_id in list(manager.active_environments.keys()):
            await manager.cleanup_staging_environment(staging_id)
    except Exception as e:
        logging.warning(f"Cleanup warning: {e}")


@pytest.fixture
def real_production_db():
    """Real production database configuration for testing."""
    return ProductionDatabase(
        host=TEST_DB_CONFIG["host"],
        port=TEST_DB_CONFIG["port"],
        database=TEST_DB_CONFIG["database"],
        user=TEST_DB_CONFIG["user"],
        password=TEST_DB_CONFIG["password"],
    )


@pytest.fixture
async def real_validation_pipeline(real_staging_manager):
    """Create real MigrationValidationPipeline with actual database components."""
    config = MigrationValidationConfig(
        staging_timeout_seconds=120,
        performance_baseline_queries=[
            "SELECT COUNT(*) FROM users",
            "SELECT id, name FROM users LIMIT 10",
        ],
        rollback_validation_enabled=True,
        data_integrity_checks_enabled=True,
        parallel_validation_enabled=False,  # Sequential for more predictable testing
        max_validation_time_seconds=300,
        performance_degradation_threshold=0.50,  # 50% threshold for testing
    )

    # Create real components
    dependency_analyzer = DependencyAnalyzer()
    risk_engine = RiskAssessmentEngine()

    pipeline = MigrationValidationPipeline(
        staging_manager=real_staging_manager,
        dependency_analyzer=dependency_analyzer,
        risk_engine=risk_engine,
        config=config,
    )

    return pipeline


@pytest.fixture
async def test_table_setup():
    """Set up test tables in the database."""
    import asyncpg

    conn = await asyncpg.connect(
        host=TEST_DB_CONFIG["host"],
        port=TEST_DB_CONFIG["port"],
        database=TEST_DB_CONFIG["database"],
        user=TEST_DB_CONFIG["user"],
        password=TEST_DB_CONFIG["password"],
    )

    try:
        # Create test tables for migration validation
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(255) UNIQUE,
                deprecated_field VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                amount DECIMAL(10,2),
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Insert test data
        await conn.execute(
            """
            INSERT INTO users (name, email, deprecated_field) VALUES
            ('John Doe', 'john@example.com', 'old_value_1'),
            ('Jane Smith', 'jane@example.com', 'old_value_2'),
            ('Bob Wilson', 'bob@example.com', 'old_value_3')
            ON CONFLICT (email) DO NOTHING
        """
        )

        await conn.execute(
            """
            INSERT INTO orders (user_id, amount, status)
            SELECT u.id, 100.00 * random() + 10,
                   CASE WHEN random() < 0.5 THEN 'completed' ELSE 'pending' END
            FROM users u
            WHERE NOT EXISTS (SELECT 1 FROM orders WHERE user_id = u.id)
        """
        )

        yield

    finally:
        # Cleanup test tables
        try:
            await conn.execute("DROP TABLE IF EXISTS orders CASCADE")
            await conn.execute("DROP TABLE IF EXISTS users CASCADE")
        except Exception as e:
            logging.warning(f"Cleanup warning: {e}")
        finally:
            await conn.close()


class TestMigrationValidationPipelineIntegration:
    """Integration tests for MigrationValidationPipeline with real database."""

    @pytest.mark.asyncio
    async def test_complete_validation_workflow_safe_column_removal(
        self, real_validation_pipeline, real_production_db, test_table_setup
    ):
        """Test complete validation workflow for safe column removal."""
        migration_info = {
            "migration_id": "integration_test_001",
            "table_name": "users",
            "column_name": "deprecated_field",  # Safe to remove
            "migration_sql": "ALTER TABLE users DROP COLUMN deprecated_field",
            "rollback_sql": "ALTER TABLE users ADD COLUMN deprecated_field VARCHAR(50)",
        }

        result = await real_validation_pipeline.validate_migration(
            migration_info=migration_info, production_db=real_production_db
        )

        # Verify successful validation
        assert isinstance(result, MigrationValidationResult)
        assert result.validation_status == ValidationStatus.PASSED
        assert result.migration_id == "integration_test_001"
        assert result.staging_environment_id is not None
        assert len(result.checkpoints) > 0
        assert result.validation_duration_seconds > 0

        # Verify individual checkpoints passed
        passed_checkpoints = [
            cp for cp in result.checkpoints if cp.status == CheckpointStatus.PASSED
        ]
        assert len(passed_checkpoints) > 0

        # Verify no critical errors
        critical_errors = [
            err for err in result.validation_errors if "critical" in err.message.lower()
        ]
        assert len(critical_errors) == 0

    @pytest.mark.asyncio
    async def test_validation_workflow_with_dependencies(
        self, real_validation_pipeline, real_production_db, test_table_setup
    ):
        """Test validation workflow with foreign key dependencies."""
        migration_info = {
            "migration_id": "integration_test_002",
            "table_name": "users",
            "column_name": "id",  # Has foreign key references
            "migration_sql": "ALTER TABLE users DROP COLUMN id",
            "rollback_sql": "-- Cannot rollback primary key drop",
        }

        result = await real_validation_pipeline.validate_migration(
            migration_info=migration_info, production_db=real_production_db
        )

        # Should fail due to foreign key dependencies
        assert result.validation_status == ValidationStatus.FAILED
        assert result.migration_id == "integration_test_002"

        # Should detect dependency issues
        dependency_errors = [
            err
            for err in result.validation_errors
            if "dependencies" in err.message.lower() or "foreign" in err.message.lower()
        ]
        assert len(dependency_errors) > 0

    @pytest.mark.asyncio
    async def test_rollback_validation_with_real_database(
        self, real_validation_pipeline, real_production_db, test_table_setup
    ):
        """Test rollback validation with real database operations."""
        migration_info = {
            "migration_id": "integration_test_003",
            "table_name": "users",
            "column_name": "deprecated_field",
            "migration_sql": "ALTER TABLE users DROP COLUMN deprecated_field",
            "rollback_sql": "ALTER TABLE users ADD COLUMN deprecated_field VARCHAR(50) DEFAULT 'restored'",
        }

        result = await real_validation_pipeline.validate_migration(
            migration_info=migration_info, production_db=real_production_db
        )

        # Should pass validation including rollback test
        assert result.validation_status == ValidationStatus.PASSED

        # Find rollback validation checkpoint
        rollback_checkpoint = next(
            (
                cp
                for cp in result.checkpoints
                if cp.checkpoint_type == CheckpointType.ROLLBACK_VALIDATION
            ),
            None,
        )
        assert rollback_checkpoint is not None
        assert rollback_checkpoint.status == CheckpointStatus.PASSED

    @pytest.mark.asyncio
    async def test_performance_validation_with_real_queries(
        self, real_validation_pipeline, real_production_db, test_table_setup
    ):
        """Test performance validation with real query execution."""
        migration_info = {
            "migration_id": "integration_test_004",
            "table_name": "users",
            "column_name": "deprecated_field",  # Non-indexed field
            "migration_sql": "ALTER TABLE users DROP COLUMN deprecated_field",
            "rollback_sql": "ALTER TABLE users ADD COLUMN deprecated_field VARCHAR(50)",
        }

        result = await real_validation_pipeline.validate_migration(
            migration_info=migration_info, production_db=real_production_db
        )

        # Should pass validation with acceptable performance
        assert result.validation_status == ValidationStatus.PASSED

        # Find performance validation checkpoint
        perf_checkpoint = next(
            (
                cp
                for cp in result.checkpoints
                if cp.checkpoint_type == CheckpointType.PERFORMANCE_VALIDATION
            ),
            None,
        )
        assert perf_checkpoint is not None

        # Performance should be acceptable for this simple migration
        if perf_checkpoint.status == CheckpointStatus.PASSED:
            assert "acceptable" in perf_checkpoint.message.lower()

    @pytest.mark.asyncio
    async def test_data_integrity_validation_real_checks(
        self, real_validation_pipeline, real_production_db, test_table_setup
    ):
        """Test data integrity validation with real database checks."""
        migration_info = {
            "migration_id": "integration_test_005",
            "table_name": "users",
            "column_name": "deprecated_field",
            "migration_sql": "ALTER TABLE users DROP COLUMN deprecated_field",
            "rollback_sql": "ALTER TABLE users ADD COLUMN deprecated_field VARCHAR(50)",
        }

        result = await real_validation_pipeline.validate_migration(
            migration_info=migration_info, production_db=real_production_db
        )

        # Should pass validation with data integrity checks
        assert result.validation_status == ValidationStatus.PASSED

        # Find data integrity checkpoint
        integrity_checkpoint = next(
            (
                cp
                for cp in result.checkpoints
                if cp.checkpoint_type == CheckpointType.DATA_INTEGRITY
            ),
            None,
        )
        assert integrity_checkpoint is not None

        # Data integrity should pass for this migration
        if integrity_checkpoint.status == CheckpointStatus.PASSED:
            assert "integrity" in integrity_checkpoint.message.lower()

    @pytest.mark.asyncio
    async def test_staging_environment_lifecycle(
        self, real_staging_manager, real_production_db, test_table_setup
    ):
        """Test complete staging environment lifecycle."""
        # Create staging environment
        staging_env = await real_staging_manager.create_staging_environment(
            production_db=real_production_db, data_sample_size=0.01  # 1% sample
        )

        assert staging_env is not None
        assert staging_env.staging_id is not None
        assert staging_env.staging_id in real_staging_manager.active_environments

        # Replicate schema
        replication_result = await real_staging_manager.replicate_production_schema(
            staging_id=staging_env.staging_id, include_data=True
        )

        assert replication_result.tables_replicated > 0
        assert replication_result.data_sampling_completed is True

        # Get environment info
        env_info = await real_staging_manager.get_staging_environment_info(
            staging_env.staging_id
        )

        assert env_info.staging_environment.staging_id == staging_env.staging_id

        # Cleanup
        cleanup_result = await real_staging_manager.cleanup_staging_environment(
            staging_env.staging_id
        )

        assert cleanup_result["cleanup_status"] == "SUCCESS"
        assert staging_env.staging_id not in real_staging_manager.active_environments

    @pytest.mark.asyncio
    async def test_validation_pipeline_error_handling(
        self, real_validation_pipeline, real_production_db
    ):
        """Test validation pipeline error handling with invalid migration."""
        migration_info = {
            "migration_id": "integration_test_error",
            "table_name": "nonexistent_table",
            "column_name": "nonexistent_column",
            "migration_sql": "ALTER TABLE nonexistent_table DROP COLUMN nonexistent_column",
            "rollback_sql": "ALTER TABLE nonexistent_table ADD COLUMN nonexistent_column VARCHAR(50)",
        }

        result = await real_validation_pipeline.validate_migration(
            migration_info=migration_info, production_db=real_production_db
        )

        # Should fail validation due to missing table
        assert result.validation_status == ValidationStatus.FAILED
        assert len(result.validation_errors) > 0

        # Should still have attempted some checkpoints
        assert len(result.checkpoints) > 0

    @pytest.mark.asyncio
    async def test_parallel_vs_sequential_checkpoint_execution(
        self, real_staging_manager, real_production_db, test_table_setup
    ):
        """Test both parallel and sequential checkpoint execution modes."""
        # Test sequential execution
        config_sequential = MigrationValidationConfig(
            parallel_validation_enabled=False, max_validation_time_seconds=180
        )

        pipeline_sequential = MigrationValidationPipeline(
            staging_manager=real_staging_manager,
            dependency_analyzer=DependencyAnalyzer(),
            risk_engine=RiskAssessmentEngine(),
            config=config_sequential,
        )

        migration_info = {
            "migration_id": "integration_test_sequential",
            "table_name": "users",
            "column_name": "deprecated_field",
            "migration_sql": "ALTER TABLE users DROP COLUMN deprecated_field",
            "rollback_sql": "ALTER TABLE users ADD COLUMN deprecated_field VARCHAR(50)",
        }

        # Sequential execution
        start_time = datetime.now()
        result_sequential = await pipeline_sequential.validate_migration(
            migration_info=migration_info, production_db=real_production_db
        )
        sequential_time = (datetime.now() - start_time).total_seconds()

        # Should complete successfully
        assert result_sequential.validation_status == ValidationStatus.PASSED

        # Test parallel execution
        config_parallel = MigrationValidationConfig(
            parallel_validation_enabled=True, max_validation_time_seconds=180
        )

        pipeline_parallel = MigrationValidationPipeline(
            staging_manager=real_staging_manager,
            dependency_analyzer=DependencyAnalyzer(),
            risk_engine=RiskAssessmentEngine(),
            config=config_parallel,
        )

        migration_info["migration_id"] = "integration_test_parallel"

        # Parallel execution
        start_time = datetime.now()
        result_parallel = await pipeline_parallel.validate_migration(
            migration_info=migration_info, production_db=real_production_db
        )
        parallel_time = (datetime.now() - start_time).total_seconds()

        # Should also complete successfully
        assert result_parallel.validation_status == ValidationStatus.PASSED

        # Both should have similar checkpoint counts
        assert len(result_sequential.checkpoints) == len(result_parallel.checkpoints)

        # Performance difference may vary, but both should be reasonable
        assert sequential_time < 180  # Should complete within timeout
        assert parallel_time < 180  # Should complete within timeout

    @pytest.mark.asyncio
    async def test_risk_assessment_integration_with_staging_results(
        self, real_validation_pipeline, real_production_db, test_table_setup
    ):
        """Test risk assessment updates based on staging validation results."""
        # Safe migration - should result in LOW risk
        migration_info = {
            "migration_id": "integration_test_low_risk",
            "table_name": "users",
            "column_name": "deprecated_field",
            "migration_sql": "ALTER TABLE users DROP COLUMN deprecated_field",
            "rollback_sql": "ALTER TABLE users ADD COLUMN deprecated_field VARCHAR(50)",
        }

        result = await real_validation_pipeline.validate_migration(
            migration_info=migration_info, production_db=real_production_db
        )

        # Should pass validation
        assert result.validation_status == ValidationStatus.PASSED

        # Risk assessment should be updated
        assert result.risk_assessment is not None
        assert result.overall_risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]

        # Risky migration - should result in higher risk
        migration_info_risky = {
            "migration_id": "integration_test_high_risk",
            "table_name": "users",
            "column_name": "id",  # Primary key - very risky
            "migration_sql": "ALTER TABLE users DROP COLUMN id",
            "rollback_sql": "-- Cannot rollback primary key drop",
        }

        result_risky = await real_validation_pipeline.validate_migration(
            migration_info=migration_info_risky, production_db=real_production_db
        )

        # Should fail validation
        assert result_risky.validation_status == ValidationStatus.FAILED

        # Risk level should be higher than the safe migration
        assert result_risky.overall_risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]


class TestValidationCheckpointIntegration:
    """Integration tests for individual validation checkpoints."""

    @pytest.mark.asyncio
    async def test_dependency_analysis_checkpoint_real_database(
        self, real_staging_manager, real_production_db, test_table_setup
    ):
        """Test dependency analysis checkpoint with real database."""
        # Create staging environment
        staging_env = await real_staging_manager.create_staging_environment(
            production_db=real_production_db
        )

        try:
            # Replicate schema
            await real_staging_manager.replicate_production_schema(
                staging_id=staging_env.staging_id, include_data=True
            )

            # Test dependency analysis
            checkpoint_manager = ValidationCheckpointManager()
            dependency_analyzer = DependencyAnalyzer()

            from dataflow.migrations.validation_checkpoints import (
                DependencyAnalysisCheckpoint,
            )

            checkpoint_manager.register_checkpoint(
                CheckpointType.DEPENDENCY_ANALYSIS,
                DependencyAnalysisCheckpoint(dependency_analyzer=dependency_analyzer),
            )

            migration_info = {
                "table_name": "users",
                "column_name": "id",  # Has foreign key references
            }

            result = await checkpoint_manager.execute_checkpoint(
                CheckpointType.DEPENDENCY_ANALYSIS,
                staging_environment=staging_env,
                migration_info=migration_info,
            )

            # Should detect foreign key dependencies
            assert result.checkpoint_type == CheckpointType.DEPENDENCY_ANALYSIS
            assert result.status == CheckpointStatus.FAILED  # Due to FK dependencies
            assert "dependencies" in result.message.lower()

        finally:
            await real_staging_manager.cleanup_staging_environment(
                staging_env.staging_id
            )

    @pytest.mark.asyncio
    async def test_performance_validation_checkpoint_real_queries(
        self, real_staging_manager, real_production_db, test_table_setup
    ):
        """Test performance validation checkpoint with real query execution."""
        # Create staging environment
        staging_env = await real_staging_manager.create_staging_environment(
            production_db=real_production_db
        )

        try:
            # Replicate schema
            await real_staging_manager.replicate_production_schema(
                staging_id=staging_env.staging_id, include_data=True
            )

            # Test performance validation
            checkpoint_manager = ValidationCheckpointManager()

            from dataflow.migrations.validation_checkpoints import (
                PerformanceValidationCheckpoint,
            )

            checkpoint_manager.register_checkpoint(
                CheckpointType.PERFORMANCE_VALIDATION,
                PerformanceValidationCheckpoint(
                    baseline_queries=["SELECT COUNT(*) FROM users"],
                    performance_threshold=0.50,  # 50% threshold
                ),
            )

            migration_info = {
                "table_name": "users",
                "column_name": "deprecated_field",
                "migration_sql": "ALTER TABLE users DROP COLUMN deprecated_field",
                "rollback_sql": "ALTER TABLE users ADD COLUMN deprecated_field VARCHAR(50)",
            }

            result = await checkpoint_manager.execute_checkpoint(
                CheckpointType.PERFORMANCE_VALIDATION,
                staging_environment=staging_env,
                migration_info=migration_info,
            )

            # Should complete performance validation
            assert result.checkpoint_type == CheckpointType.PERFORMANCE_VALIDATION
            assert result.status in [CheckpointStatus.PASSED, CheckpointStatus.FAILED]
            assert result.execution_time_seconds > 0

        finally:
            await real_staging_manager.cleanup_staging_environment(
                staging_env.staging_id
            )


class TestPerformanceValidatorIntegration:
    """Integration tests for PerformanceValidator with real database."""

    @pytest.mark.asyncio
    async def test_complete_performance_validation_workflow(
        self, real_staging_manager, real_production_db, test_table_setup
    ):
        """Test complete performance validation workflow with real database."""
        # Create staging environment
        staging_env = await real_staging_manager.create_staging_environment(
            production_db=real_production_db
        )

        try:
            # Replicate schema
            await real_staging_manager.replicate_production_schema(
                staging_id=staging_env.staging_id, include_data=True
            )

            # Create performance validator
            config = PerformanceValidationConfig(
                baseline_queries=[
                    "SELECT COUNT(*) FROM users",
                    "SELECT id, name FROM users LIMIT 5",
                ],
                performance_degradation_threshold=0.30,
                baseline_execution_runs=2,
                benchmark_execution_runs=2,
                timeout_seconds=10,
            )

            validator = PerformanceValidator(config=config)

            # Establish baseline
            baseline = await validator.establish_baseline(
                staging_environment=staging_env, queries=config.baseline_queries
            )

            assert baseline is not None
            assert len(baseline.query_baselines) == 2

            # Run benchmark (simulated post-migration)
            benchmark = await validator.run_benchmark(
                staging_environment=staging_env, baseline=baseline
            )

            assert benchmark is not None
            assert len(benchmark.query_benchmarks) == 2

            # Compare performance
            comparison = validator.compare_performance(baseline, benchmark)

            assert comparison is not None
            assert comparison.overall_degradation_percent >= 0
            assert comparison.is_acceptable_performance in [True, False]

        finally:
            await real_staging_manager.cleanup_staging_environment(
                staging_env.staging_id
            )
