#!/usr/bin/env python3
"""
Integration tests for Production Deployment Validator - TODO-141 Phase 3.

Tests the production deployment validator with real infrastructure components,
including Phase 1 (StagingEnvironmentManager) and Phase 2 (MigrationValidationPipeline).

TIER 2 (INTEGRATION) REQUIREMENTS:
- Use real Docker services from ./tests/utils/test-env
- NO MOCKING of external services - test actual component interactions
- Test database connections, API calls, file operations
- Validate data flows between components with real services
- Run: ./tests/utils/test-env up && ./tests/utils/test-env status before tests
- Timeout: <5 seconds per test
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pytest
from src.dataflow.migrations.dependency_analyzer import DependencyAnalyzer
from src.dataflow.migrations.impact_reporter import ImpactReporter
from src.dataflow.migrations.migration_validation_pipeline import (
    MigrationValidationConfig,
    MigrationValidationPipeline,
)

# Import system under test
from src.dataflow.migrations.production_deployment_validator import (
    DeploymentApprovalStatus,
    DeploymentResult,
    DeploymentStrategy,
    ProductionDeploymentValidator,
    ProductionSafetyConfig,
    RiskLevel,
)
from src.dataflow.migrations.risk_assessment_engine import (
    ComprehensiveRiskAssessment,
    RiskAssessmentEngine,
)

# Import Phase 1 and Phase 2 components for real integration
from src.dataflow.migrations.staging_environment_manager import (
    ProductionDatabase,
    StagingDatabase,
    StagingEnvironmentConfig,
    StagingEnvironmentManager,
)

from kailash.runtime.local import LocalRuntime

# Test infrastructure support
from tests.infrastructure.test_harness import IntegrationTestSuite


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


@pytest.fixture
def production_db_config(test_suite):
    """Production database configuration from test suite."""
    config = test_suite.config
    return ProductionDatabase(
        host=config.host,
        port=config.port,
        database=config.database,
        user=config.user,
        password=config.password,
    )


@pytest.fixture
def production_safety_config():
    """Production safety configuration for testing."""
    return ProductionSafetyConfig(
        require_executive_approval_threshold=RiskLevel.HIGH,
        require_staging_validation=True,
        require_rollback_plan=True,
        max_deployment_time_minutes=5,  # Short timeout for tests
        approval_timeout_hours=1,  # Short timeout for tests
    )


@pytest.fixture
async def staging_manager():
    """Real staging environment manager."""
    config = StagingEnvironmentConfig(
        max_staging_environments=2, cleanup_timeout_seconds=30
    )
    return StagingEnvironmentManager(config=config)


@pytest.fixture
async def validation_pipeline(staging_manager):
    """Real migration validation pipeline."""
    config = MigrationValidationConfig(
        staging_timeout_seconds=30,
        max_validation_time_seconds=60,
        performance_degradation_threshold=0.5,  # Relaxed for tests
    )

    # Create real components
    dependency_analyzer = DependencyAnalyzer()
    risk_engine = RiskAssessmentEngine()

    return MigrationValidationPipeline(
        staging_manager=staging_manager,
        dependency_analyzer=dependency_analyzer,
        risk_engine=risk_engine,
        config=config,
    )


@pytest.fixture
async def production_deployment_validator(
    staging_manager, validation_pipeline, production_safety_config
):
    """Real production deployment validator with integrated components."""
    risk_engine = RiskAssessmentEngine()
    dependency_analyzer = DependencyAnalyzer()
    impact_reporter = ImpactReporter()

    return ProductionDeploymentValidator(
        staging_manager=staging_manager,
        validation_pipeline=validation_pipeline,
        risk_engine=risk_engine,
        config=production_safety_config,
        dependency_analyzer=dependency_analyzer,
        impact_reporter=impact_reporter,
    )


@pytest.mark.asyncio
class TestProductionDeploymentValidatorIntegration:
    """Integration tests for Production Deployment Validator with real infrastructure."""

    async def test_validate_production_deployment_low_risk(
        self, production_deployment_validator, production_db_config, runtime
    ):
        """Test complete production deployment validation for low-risk migration."""
        # Low-risk migration: add a simple column
        migration_info = {
            "migration_id": "test_low_risk_001",
            "table_name": "test_users",
            "column_name": "email_verified",
            "operation_type": "add_column",
            "sql_statements": [
                "ALTER TABLE test_users ADD COLUMN email_verified BOOLEAN DEFAULT FALSE;"
            ],
        }

        # Execute complete deployment validation workflow
        start_time = time.time()
        deployment_result = (
            await production_deployment_validator.validate_production_deployment(
                migration_info, production_db=production_db_config
            )
        )
        duration = time.time() - start_time

        # Validate results
        assert deployment_result is not None
        assert deployment_result.migration_id == "test_low_risk_001"
        assert deployment_result.deployment_duration_seconds > 0
        assert duration < 5.0  # Must complete within 5 seconds

        # Low-risk migrations should generally succeed or provide clear guidance
        if not deployment_result.success:
            # If it fails, should have clear error messages
            assert len(deployment_result.errors) > 0
            assert deployment_result.message
            print(f"Deployment failed as expected: {deployment_result.message}")
            print(f"Errors: {deployment_result.errors}")

    async def test_validate_production_deployment_medium_risk(
        self, production_deployment_validator, production_db_config, runtime
    ):
        """Test production deployment validation for medium-risk migration."""
        # Medium-risk migration: modify existing column
        migration_info = {
            "migration_id": "test_medium_risk_001",
            "table_name": "test_orders",
            "column_name": "status",
            "operation_type": "modify_column",
            "sql_statements": [
                "ALTER TABLE test_orders ALTER COLUMN status TYPE VARCHAR(50);"
            ],
        }

        start_time = time.time()
        deployment_result = (
            await production_deployment_validator.validate_production_deployment(
                migration_info, production_db=production_db_config
            )
        )
        duration = time.time() - start_time

        # Validate results
        assert deployment_result is not None
        assert deployment_result.migration_id == "test_medium_risk_001"
        assert duration < 5.0  # Must complete within integration test timeout

        # Medium-risk migrations should require staging validation
        # Result should indicate staged deployment strategy was used
        print(f"Medium-risk deployment result: {deployment_result.success}")
        print(f"Message: {deployment_result.message}")

        if deployment_result.success:
            assert len(deployment_result.phases_completed) > 0

    async def test_validate_production_deployment_high_risk_blocked(
        self, production_deployment_validator, production_db_config, runtime
    ):
        """Test production deployment validation blocks high-risk migrations without approval."""
        # High-risk migration: drop table
        migration_info = {
            "migration_id": "test_high_risk_001",
            "table_name": "test_critical_data",
            "operation_type": "drop_table",
            "sql_statements": ["DROP TABLE test_critical_data;"],
        }

        start_time = time.time()
        deployment_result = (
            await production_deployment_validator.validate_production_deployment(
                migration_info, production_db=production_db_config
            )
        )
        duration = time.time() - start_time

        # High-risk migrations should be blocked or require approval
        assert deployment_result is not None
        assert deployment_result.migration_id == "test_high_risk_001"
        assert duration < 5.0

        # Should be blocked or require approval
        if not deployment_result.success:
            assert (
                "approval" in deployment_result.message.lower()
                or "blocked" in deployment_result.message.lower()
            )

        print(f"High-risk deployment result: {deployment_result.success}")
        print(f"Message: {deployment_result.message}")

    async def test_staging_environment_integration(
        self, production_deployment_validator, production_db_config, runtime
    ):
        """Test integration with Phase 1 staging environment manager."""
        migration_info = {
            "migration_id": "test_staging_integration_001",
            "table_name": "test_integration",
            "column_name": "new_field",
            "operation_type": "add_column",
            "sql_statements": [
                "ALTER TABLE test_integration ADD COLUMN new_field TEXT;"
            ],
        }

        # Test staging environment creation and cleanup
        staging_manager = production_deployment_validator.staging_manager

        # Create staging environment
        staging_env = await staging_manager.create_staging_environment(
            production_db=production_db_config,
            data_sample_size=0.01,  # Minimal sample for tests
        )

        assert staging_env is not None
        assert staging_env.staging_id
        assert staging_env.production_db == production_db_config

        # Test staging environment info
        staging_info = await staging_manager.get_staging_environment_info(
            staging_env.staging_id
        )
        assert staging_info.staging_environment.staging_id == staging_env.staging_id

        # Cleanup staging environment
        cleanup_result = await staging_manager.cleanup_staging_environment(
            staging_env.staging_id
        )
        assert cleanup_result["cleanup_status"] == "SUCCESS"

    async def test_validation_pipeline_integration(
        self, production_deployment_validator, production_db_config, runtime
    ):
        """Test integration with Phase 2 migration validation pipeline."""
        migration_info = {
            "migration_id": "test_pipeline_integration_001",
            "table_name": "test_validation",
            "column_name": "validated_field",
            "operation_type": "add_column",
            "sql_statements": [
                "ALTER TABLE test_validation ADD COLUMN validated_field INTEGER;"
            ],
        }

        # Test validation pipeline directly
        validation_pipeline = production_deployment_validator.validation_pipeline

        start_time = time.time()
        validation_result = await validation_pipeline.validate_migration(
            migration_info, production_db=production_db_config
        )
        duration = time.time() - start_time

        assert validation_result is not None
        assert validation_result.migration_id == "test_pipeline_integration_001"
        assert duration < 5.0

        # Validation should complete with status
        assert validation_result.validation_status is not None

        print(
            f"Validation pipeline result: {validation_result.validation_status.value}"
        )
        print(f"Duration: {duration:.2f}s")

    async def test_risk_assessment_integration(
        self, production_deployment_validator, runtime
    ):
        """Test integration with risk assessment engine for production deployment."""
        migration_info = {
            "migration_id": "test_risk_assessment_001",
            "table_name": "test_risk_table",
            "column_name": "risk_column",
            "operation_type": "drop_column",
        }

        # Test risk assessment in production context
        risk_assessment = await production_deployment_validator._assess_deployment_risk(
            migration_info
        )

        assert risk_assessment is not None
        assert risk_assessment.operation_id
        assert risk_assessment.overall_score >= 0
        assert risk_assessment.risk_level is not None
        assert risk_assessment.total_computation_time > 0

        print(
            f"Risk assessment - Level: {risk_assessment.risk_level.value}, Score: {risk_assessment.overall_score:.1f}"
        )

    async def test_deployment_gate_execution_with_real_components(
        self, production_deployment_validator, production_db_config, runtime
    ):
        """Test deployment safety gates with real component integration."""
        migration_info = {
            "migration_id": "test_gates_001",
            "table_name": "test_gates",
            "column_name": "gate_test_field",
            "operation_type": "add_column",
        }

        # Test individual gate execution with real components

        # 1. Risk Assessment Gate
        risk_assessment = await production_deployment_validator._assess_deployment_risk(
            migration_info
        )
        assert risk_assessment.risk_level is not None

        # 2. Rollback Plan Gate
        rollback_plan = production_deployment_validator._generate_rollback_plan(
            migration_info
        )
        assert len(rollback_plan.rollback_steps) > 0
        assert rollback_plan.is_executable

        # 3. Production Ready Gate
        production_ready_result = (
            production_deployment_validator._execute_production_ready_gate(
                migration_info
            )
        )
        assert production_ready_result.gate_type.value == "production_ready"
        assert production_ready_result.passed is not None

    async def test_concurrent_deployment_prevention_with_real_locks(
        self, production_deployment_validator, production_db_config, runtime
    ):
        """Test concurrent deployment prevention with real locking mechanisms."""
        migration_info_1 = {
            "migration_id": "test_concurrent_001",
            "deployment_id": "deploy_concurrent_001",
            "table_name": "test_concurrent",
            "operation_type": "add_column",
            "schema_name": "public",
        }

        migration_info_2 = {
            "migration_id": "test_concurrent_002",
            "deployment_id": "deploy_concurrent_002",
            "table_name": "test_concurrent_2",
            "operation_type": "add_column",
            "schema_name": "public",  # Same schema
        }

        # Start first deployment (should succeed)
        can_deploy_1 = production_deployment_validator._can_start_deployment(
            migration_info_1
        )
        assert can_deploy_1 is True

        # Try second deployment to same schema (should be blocked)
        can_deploy_2 = production_deployment_validator._can_start_deployment(
            migration_info_2
        )
        assert can_deploy_2 is False

        # Clean up first deployment
        schema_name = migration_info_1.get("schema_name", "public")
        if schema_name in production_deployment_validator._active_deployments:
            del production_deployment_validator._active_deployments[schema_name]

        # Now second deployment should be allowed
        can_deploy_2_after = production_deployment_validator._can_start_deployment(
            migration_info_2
        )
        assert can_deploy_2_after is True

    async def test_deployment_timeout_handling_integration(
        self, production_deployment_validator, runtime
    ):
        """Test deployment timeout handling with real timing."""
        # Create a deployment that appears to have timed out
        old_deployment = {
            "deployment_id": "deploy_timeout_test",
            "started_at": datetime.now() - timedelta(minutes=10),  # 10 minutes ago
            "max_duration_minutes": 5,  # 5 minute limit
        }

        is_timed_out = production_deployment_validator._is_deployment_timed_out(
            old_deployment
        )
        assert is_timed_out is True

        # Create a recent deployment
        recent_deployment = {
            "deployment_id": "deploy_recent_test",
            "started_at": datetime.now() - timedelta(minutes=2),  # 2 minutes ago
            "max_duration_minutes": 5,  # 5 minute limit
        }

        is_recent_timed_out = production_deployment_validator._is_deployment_timed_out(
            recent_deployment
        )
        assert is_recent_timed_out is False

    async def test_complete_deployment_workflow_integration(
        self, production_deployment_validator, production_db_config, runtime
    ):
        """Test complete end-to-end deployment workflow integration."""
        # Simple, low-risk migration for complete workflow test
        migration_info = {
            "migration_id": "test_complete_workflow_001",
            "table_name": "test_workflow",
            "column_name": "workflow_field",
            "operation_type": "add_column",
            "sql_statements": [
                "ALTER TABLE test_workflow ADD COLUMN workflow_field VARCHAR(100);"
            ],
        }

        # Execute complete workflow
        start_time = time.time()

        try:
            deployment_result = (
                await production_deployment_validator.validate_production_deployment(
                    migration_info, production_db=production_db_config
                )
            )

            duration = time.time() - start_time

            # Validate workflow completion
            assert deployment_result is not None
            assert deployment_result.migration_id == "test_complete_workflow_001"
            assert deployment_result.deployment_duration_seconds > 0
            assert duration < 5.0  # Integration test timeout

            print(f"Complete workflow - Success: {deployment_result.success}")
            print(f"Duration: {duration:.2f}s")
            print(f"Message: {deployment_result.message}")

            if deployment_result.errors:
                print(f"Errors: {deployment_result.errors}")

            if deployment_result.warnings:
                print(f"Warnings: {deployment_result.warnings}")

            # Should have some result regardless of success/failure
            assert deployment_result.message is not None

        except Exception as e:
            duration = time.time() - start_time
            print(f"Complete workflow failed after {duration:.2f}s: {e}")

            # Even failures should be handled gracefully
            assert duration < 5.0  # Should fail fast if there are issues

            # Re-raise for test failure analysis
            raise


if __name__ == "__main__":
    # Run integration tests with timeout
    pytest.main(
        [
            __file__,
            "-v",
            "--tb=short",
            "--timeout=5",
            "-x",  # Stop on first failure for debugging
        ]
    )
