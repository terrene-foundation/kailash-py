#!/usr/bin/env python3
"""
Unit tests for Production Deployment Validator - TODO-141 Phase 3.

Tests the core deployment validation logic, approval workflows, rollback planning,
and integration with risk assessment without external dependencies.

TIER 1 (UNIT) REQUIREMENTS:
- Fast execution (<1 second per test)
- No external dependencies (databases, APIs, files)
- Can use mocks for staging and production systems
- Test all public methods and edge cases
- Focus on deployment validation logic
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from src.dataflow.migrations.migration_validation_pipeline import (
    MigrationValidationPipeline,
    MigrationValidationResult,
    ValidationStatus,
)

# Import the system under test - will be implemented
from src.dataflow.migrations.production_deployment_validator import (
    ApprovalWorkflow,
    DeploymentApprovalStatus,
    DeploymentGate,
    DeploymentGateResult,
    DeploymentResult,
    DeploymentStrategy,
    ExecutiveApprovalLevel,
    ProductionDeploymentValidator,
    ProductionSafetyConfig,
    RollbackPlan,
)
from src.dataflow.migrations.risk_assessment_engine import (
    ComprehensiveRiskAssessment,
    RiskAssessmentEngine,
    RiskCategory,
    RiskLevel,
)
from src.dataflow.migrations.staging_environment_manager import (
    ProductionDatabase,
    StagingDatabase,
    StagingEnvironment,
    StagingEnvironmentManager,
    StagingEnvironmentStatus,
)


class TestProductionDeploymentValidator:
    """Test suite for ProductionDeploymentValidator core functionality."""

    @pytest.fixture
    def mock_staging_manager(self):
        """Mock staging environment manager."""
        manager = AsyncMock(spec=StagingEnvironmentManager)
        manager.create_staging_environment = AsyncMock()
        manager.replicate_production_schema = AsyncMock()
        manager.cleanup_staging_environment = AsyncMock()
        return manager

    @pytest.fixture
    def mock_validation_pipeline(self):
        """Mock migration validation pipeline."""
        pipeline = AsyncMock(spec=MigrationValidationPipeline)
        pipeline.validate_migration = AsyncMock()
        return pipeline

    @pytest.fixture
    def mock_risk_engine(self):
        """Mock risk assessment engine."""
        engine = Mock(spec=RiskAssessmentEngine)
        engine.calculate_migration_risk_score = Mock()
        return engine

    @pytest.fixture
    def production_config(self):
        """Production deployment configuration."""
        return ProductionSafetyConfig(
            require_executive_approval_threshold=RiskLevel.HIGH,
            require_staging_validation=True,
            require_rollback_plan=True,
            max_deployment_time_minutes=60,
            require_approval_for_production=True,
            zero_downtime_required=True,
            backup_before_deployment=True,
        )

    @pytest.fixture
    def deployment_validator(
        self,
        mock_staging_manager,
        mock_validation_pipeline,
        mock_risk_engine,
        production_config,
    ):
        """Production deployment validator instance."""
        return ProductionDeploymentValidator(
            staging_manager=mock_staging_manager,
            validation_pipeline=mock_validation_pipeline,
            risk_engine=mock_risk_engine,
            config=production_config,
        )

    def test_deployment_validator_initialization(
        self, deployment_validator, production_config
    ):
        """Test deployment validator initializes correctly."""
        assert deployment_validator.config == production_config
        assert deployment_validator.staging_manager is not None
        assert deployment_validator.validation_pipeline is not None
        assert deployment_validator.risk_engine is not None
        assert deployment_validator._active_deployments == {}

    def test_deployment_config_validation(self):
        """Test deployment configuration validation."""
        # Valid configuration
        valid_config = ProductionSafetyConfig(
            require_executive_approval_threshold=RiskLevel.HIGH,
            max_deployment_time_minutes=120,
        )
        assert valid_config.require_executive_approval_threshold == RiskLevel.HIGH

        # Invalid timeout should raise error
        with pytest.raises(ValueError, match="Max deployment time must be positive"):
            ProductionSafetyConfig(max_deployment_time_minutes=0)

    def test_determine_deployment_strategy(self, deployment_validator):
        """Test deployment strategy selection based on risk level."""
        # Low risk - simple deployment
        low_risk_assessment = Mock()
        low_risk_assessment.risk_level = RiskLevel.LOW

        strategy = deployment_validator._determine_deployment_strategy(
            low_risk_assessment
        )
        assert strategy == DeploymentStrategy.DIRECT

        # Medium risk - staged deployment
        medium_risk_assessment = Mock()
        medium_risk_assessment.risk_level = RiskLevel.MEDIUM

        strategy = deployment_validator._determine_deployment_strategy(
            medium_risk_assessment
        )
        assert strategy == DeploymentStrategy.STAGED

        # High risk - zero downtime required
        high_risk_assessment = Mock()
        high_risk_assessment.risk_level = RiskLevel.HIGH

        strategy = deployment_validator._determine_deployment_strategy(
            high_risk_assessment
        )
        assert strategy == DeploymentStrategy.ZERO_DOWNTIME

        # Critical risk - deployment blocked
        critical_risk_assessment = Mock()
        critical_risk_assessment.risk_level = RiskLevel.CRITICAL

        strategy = deployment_validator._determine_deployment_strategy(
            critical_risk_assessment
        )
        assert strategy == DeploymentStrategy.BLOCKED

    def test_generate_rollback_plan(self, deployment_validator):
        """Test rollback plan generation."""
        migration_info = {
            "migration_id": "test_migration_001",
            "table_name": "users",
            "column_name": "email_verified",
            "operation_type": "add_column",
            "sql_statements": [
                "ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT FALSE;"
            ],
        }

        rollback_plan = deployment_validator._generate_rollback_plan(migration_info)

        assert rollback_plan.migration_id == "test_migration_001"
        assert len(rollback_plan.rollback_steps) > 0
        assert rollback_plan.estimated_rollback_time > 0
        assert rollback_plan.requires_data_backup is True

        # Check rollback SQL generation
        assert any(
            "DROP COLUMN" in step.sql_statement for step in rollback_plan.rollback_steps
        )

    def test_executive_approval_requirement(self, deployment_validator):
        """Test executive approval requirement determination."""
        # High risk requires executive approval
        high_risk_assessment = Mock()
        high_risk_assessment.risk_level = RiskLevel.HIGH

        requires_approval = deployment_validator._requires_executive_approval(
            high_risk_assessment
        )
        assert requires_approval is True

        # Medium risk doesn't require executive approval
        medium_risk_assessment = Mock()
        medium_risk_assessment.risk_level = RiskLevel.MEDIUM

        requires_approval = deployment_validator._requires_executive_approval(
            medium_risk_assessment
        )
        assert requires_approval is False

    def test_deployment_safety_gates_configuration(self, deployment_validator):
        """Test deployment safety gates are properly configured."""
        gates = deployment_validator._get_deployment_gates()

        assert len(gates) >= 4  # Should have multiple safety gates

        # Gate types are the enum values themselves
        assert DeploymentGate.STAGING_VALIDATION in gates
        assert DeploymentGate.RISK_ASSESSMENT in gates
        assert DeploymentGate.ROLLBACK_PLAN in gates
        assert DeploymentGate.PRODUCTION_READY in gates

    def test_deployment_gate_execution(self, deployment_validator):
        """Test individual deployment gate execution."""
        # Mock successful staging validation gate
        staging_gate = DeploymentGate.STAGING_VALIDATION

        # Create mock validation result
        mock_validation_result = Mock()
        mock_validation_result.validation_status = ValidationStatus.PASSED
        mock_validation_result.validation_errors = []  # Empty list instead of Mock
        mock_validation_result.is_successful.return_value = True

        gate_result = deployment_validator._execute_deployment_gate(
            staging_gate, mock_validation_result, {}
        )

        assert gate_result.gate_type == staging_gate
        assert gate_result.passed is True
        assert len(gate_result.message) > 0

    def test_deployment_approval_workflow_creation(self, deployment_validator):
        """Test deployment approval workflow creation."""
        migration_info = {
            "migration_id": "test_migration_001",
            "risk_level": RiskLevel.HIGH,
        }

        mock_risk_assessment = Mock()
        mock_risk_assessment.risk_level = RiskLevel.HIGH

        approval_workflow = deployment_validator._create_approval_workflow(
            migration_info, mock_risk_assessment
        )

        assert approval_workflow.migration_id == "test_migration_001"
        assert (
            approval_workflow.required_approval_level
            == ExecutiveApprovalLevel.MANAGEMENT
        )
        assert approval_workflow.approval_status == DeploymentApprovalStatus.PENDING
        assert len(approval_workflow.approval_steps) > 0

    def test_zero_downtime_deployment_planning(self, deployment_validator):
        """Test zero-downtime deployment planning."""
        migration_info = {
            "migration_id": "test_migration_001",
            "deployment_id": "deploy_001",
            "operation_type": "add_column",
            "table_name": "users",
            "estimated_rows": 1000000,
        }

        deployment_plan = deployment_validator._plan_zero_downtime_deployment(
            migration_info
        )

        assert deployment_plan.strategy == DeploymentStrategy.ZERO_DOWNTIME
        assert deployment_plan.estimated_downtime_seconds == 0
        assert len(deployment_plan.deployment_phases) >= 3  # Prepare, Execute, Validate
        assert deployment_plan.requires_connection_management is True

    @pytest.mark.asyncio
    async def test_deployment_risk_assessment_integration(
        self, deployment_validator, mock_risk_engine
    ):
        """Test integration with risk assessment engine."""
        migration_info = {
            "migration_id": "test_001",
            "table_name": "orders",
            "column_name": "status",
            "operation_type": "modify_column",
        }

        # Mock dependency analyzer (since it's None in our test fixture)
        mock_dependency_analyzer = AsyncMock()
        deployment_validator.dependency_analyzer = mock_dependency_analyzer

        # Mock dependency report
        mock_dependency_report = Mock()

        # Set up the async mock to return the dependency report
        async def mock_analyze_dependencies(*args, **kwargs):
            return mock_dependency_report

        mock_dependency_analyzer.analyze_dependencies = mock_analyze_dependencies

        # Mock risk assessment
        mock_assessment = Mock()
        mock_assessment.risk_level = RiskLevel.MEDIUM
        mock_assessment.overall_score = 45.0
        mock_risk_engine.calculate_migration_risk_score.return_value = mock_assessment

        assessment = await deployment_validator._assess_deployment_risk(migration_info)

        assert assessment.risk_level == RiskLevel.MEDIUM
        mock_risk_engine.calculate_migration_risk_score.assert_called_once()

    def test_deployment_result_creation(self, deployment_validator):
        """Test deployment result creation and validation."""
        deployment_info = {
            "deployment_id": "deploy_001",
            "migration_id": "migration_001",
            "started_at": datetime.now(),
        }

        # Successful deployment
        result = deployment_validator._create_deployment_result(
            deployment_info, success=True, message="Deployment completed successfully"
        )

        assert result.deployment_id == "deploy_001"
        assert result.success is True
        assert result.deployment_duration_seconds >= 0
        assert "successful" in result.message.lower()

        # Failed deployment
        failed_result = deployment_validator._create_deployment_result(
            deployment_info,
            success=False,
            message="Deployment failed due to safety gate failure",
        )

        assert failed_result.success is False
        assert "failed" in failed_result.message.lower()

    def test_deployment_performance_requirements(self, deployment_validator):
        """Test deployment performance tracking and requirements."""
        start_time = time.time()

        # Simulate deployment operation
        performance_metrics = deployment_validator._track_deployment_performance(
            operation="staging_validation", start_time=start_time
        )

        assert performance_metrics["operation"] == "staging_validation"
        assert performance_metrics["duration_seconds"] >= 0
        assert (
            performance_metrics["duration_seconds"] < 1.0
        )  # Should be fast for unit tests

    def test_concurrent_deployment_prevention(self, deployment_validator):
        """Test prevention of concurrent deployments for same schema."""
        migration_info_1 = {
            "migration_id": "migration_001",
            "deployment_id": "deploy_001",
            "schema_name": "public",
        }
        migration_info_2 = {
            "migration_id": "migration_002",
            "deployment_id": "deploy_002",
            "schema_name": "public",
        }

        # First deployment should be allowed
        can_deploy_1 = deployment_validator._can_start_deployment(migration_info_1)
        assert can_deploy_1 is True

        # Second deployment to same schema should be blocked
        can_deploy_2 = deployment_validator._can_start_deployment(migration_info_2)
        assert can_deploy_2 is False

    def test_deployment_timeout_handling(self, deployment_validator):
        """Test deployment timeout detection and handling."""
        # Create deployment that started 2 hours ago
        old_deployment = {
            "deployment_id": "deploy_old",
            "started_at": datetime.now() - timedelta(hours=2),
            "max_duration_minutes": 60,
        }

        is_timed_out = deployment_validator._is_deployment_timed_out(old_deployment)
        assert is_timed_out is True

        # Create recent deployment
        recent_deployment = {
            "deployment_id": "deploy_recent",
            "started_at": datetime.now() - timedelta(minutes=30),
            "max_duration_minutes": 60,
        }

        is_timed_out = deployment_validator._is_deployment_timed_out(recent_deployment)
        assert is_timed_out is False

    def test_deployment_validation_error_handling(self, deployment_validator):
        """Test error handling in deployment validation."""
        invalid_migration_info = {}  # Empty migration info

        with pytest.raises(ValueError, match="migration_id is required"):
            deployment_validator._validate_migration_info(invalid_migration_info)

        # Missing required fields
        incomplete_migration_info = {"migration_id": "test_001"}

        with pytest.raises(ValueError, match="table_name is required"):
            deployment_validator._validate_migration_info(incomplete_migration_info)


class TestDeploymentGatesAndApproval:
    """Test suite for deployment gates and approval workflows."""

    def test_staging_validation_gate(self):
        """Test staging validation deployment gate."""
        # Mock successful validation result
        validation_result = Mock()
        validation_result.validation_status = ValidationStatus.PASSED
        validation_result.validation_errors = []

        gate_result = DeploymentGateResult.create_from_validation(
            DeploymentGate.STAGING_VALIDATION, validation_result
        )

        assert gate_result.gate_type == DeploymentGate.STAGING_VALIDATION
        assert gate_result.passed is True
        assert "staging validation passed" in gate_result.message.lower()

    def test_risk_assessment_gate(self):
        """Test risk assessment deployment gate."""
        # Mock medium risk assessment (acceptable for deployment)
        risk_assessment = Mock()
        risk_assessment.risk_level = RiskLevel.MEDIUM
        risk_assessment.overall_score = 40.0

        gate_result = DeploymentGateResult.create_from_risk_assessment(
            DeploymentGate.RISK_ASSESSMENT, risk_assessment
        )

        assert gate_result.gate_type == DeploymentGate.RISK_ASSESSMENT
        assert gate_result.passed is True

        # Test critical risk blocks deployment
        critical_risk_assessment = Mock()
        critical_risk_assessment.risk_level = RiskLevel.CRITICAL
        critical_risk_assessment.overall_score = 85.0

        critical_gate_result = DeploymentGateResult.create_from_risk_assessment(
            DeploymentGate.RISK_ASSESSMENT, critical_risk_assessment
        )

        assert critical_gate_result.passed is False

    def test_rollback_plan_gate(self):
        """Test rollback plan validation gate."""
        # Valid rollback plan
        rollback_plan = Mock()
        rollback_plan.rollback_steps = [Mock(), Mock()]  # Has steps
        rollback_plan.estimated_rollback_time = 30.0
        rollback_plan.is_executable = True

        gate_result = DeploymentGateResult.create_from_rollback_plan(
            DeploymentGate.ROLLBACK_PLAN, rollback_plan
        )

        assert gate_result.passed is True

        # Invalid rollback plan (no steps)
        invalid_rollback_plan = Mock()
        invalid_rollback_plan.rollback_steps = []
        invalid_rollback_plan.is_executable = False

        invalid_gate_result = DeploymentGateResult.create_from_rollback_plan(
            DeploymentGate.ROLLBACK_PLAN, invalid_rollback_plan
        )

        assert invalid_gate_result.passed is False

    def test_approval_workflow_progression(self):
        """Test approval workflow status progression."""
        workflow = ApprovalWorkflow(
            migration_id="test_001",
            required_approval_level=ExecutiveApprovalLevel.MANAGEMENT,
            approval_status=DeploymentApprovalStatus.PENDING,
        )

        # Initial state
        assert workflow.approval_status == DeploymentApprovalStatus.PENDING
        assert not workflow.is_approved()

        # Progress to approved
        workflow.approval_status = DeploymentApprovalStatus.APPROVED
        assert workflow.is_approved()

        # Test rejection
        workflow.approval_status = DeploymentApprovalStatus.REJECTED
        assert not workflow.is_approved()
        assert workflow.is_rejected()


class TestDeploymentStrategies:
    """Test suite for different deployment strategies."""

    def test_direct_deployment_strategy(self):
        """Test direct deployment strategy for low-risk migrations."""
        strategy = DeploymentStrategy.DIRECT

        # Direct deployment should be fast and simple
        assert strategy.value == "direct"
        assert strategy.requires_staging() is False
        assert strategy.estimated_downtime_seconds() == 0

    def test_staged_deployment_strategy(self):
        """Test staged deployment strategy for medium-risk migrations."""
        strategy = DeploymentStrategy.STAGED

        assert strategy.value == "staged"
        assert strategy.requires_staging() is True
        assert strategy.estimated_downtime_seconds() <= 60

    def test_zero_downtime_deployment_strategy(self):
        """Test zero-downtime deployment strategy for high-risk migrations."""
        strategy = DeploymentStrategy.ZERO_DOWNTIME

        assert strategy.value == "zero_downtime"
        assert strategy.requires_staging() is True
        assert strategy.estimated_downtime_seconds() == 0
        assert strategy.requires_connection_management() is True

    def test_blocked_deployment_strategy(self):
        """Test blocked deployment strategy for critical-risk migrations."""
        strategy = DeploymentStrategy.BLOCKED

        assert strategy.value == "blocked"
        assert strategy.allows_deployment() is False
        assert len(strategy.blocking_reasons()) > 0


if __name__ == "__main__":
    # Run tests with performance timing
    start_time = time.time()
    pytest.main([__file__, "-v", "--tb=short", "--timeout=1"])
    duration = time.time() - start_time
    print(f"\nUnit tests completed in {duration:.3f}s")
