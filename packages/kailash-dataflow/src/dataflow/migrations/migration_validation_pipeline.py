#!/usr/bin/env python3
"""
Migration Validation Pipeline - TODO-141 Phase 2

Comprehensive migration validation system that runs migrations in staging before production deployment.
Integrates with existing Phase 1 StagingEnvironmentManager and provides complete validation workflows.

CORE FEATURES:
- Complete migration workflows in staging environment first
- Performance validation against production baselines
- Rollback testing and validation in staging
- Data integrity verification across migration stages
- Risk assessment integration with staging results
- Dependency validation in staging environment

VALIDATION PIPELINE:
1. Create staging environment with production-like schema
2. Execute dependency analysis in staging context
3. Establish performance baselines pre-migration
4. Execute migration in staging with validation checkpoints
5. Run performance benchmarks post-migration
6. Execute and validate rollback procedures
7. Verify data integrity throughout process
8. Update risk assessments based on staging results
9. Clean up staging resources

INTEGRATION POINTS:
- Phase 1 StagingEnvironmentManager for environment lifecycle
- TODO-137 DependencyAnalyzer for staging dependency validation
- TODO-138 ForeignKeyAnalyzer for FK validation in staging
- TODO-140 RiskAssessmentEngine for risk score updates
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from .dependency_analyzer import (
    DependencyAnalyzer,
    DependencyReport,
    DependencyType,
    ImpactLevel,
)
from .performance_validator import (
    PerformanceBaseline,
    PerformanceBenchmark,
    PerformanceComparison,
    PerformanceValidationConfig,
    PerformanceValidator,
)
from .risk_assessment_engine import (
    ComprehensiveRiskAssessment,
    RiskAssessmentEngine,
    RiskCategory,
    RiskLevel,
)
from .staging_environment_manager import (
    ProductionDatabase,
    StagingDatabase,
    StagingEnvironment,
    StagingEnvironmentManager,
    StagingEnvironmentStatus,
)
from .validation_checkpoints import (
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

logger = logging.getLogger(__name__)


class ValidationStatus(Enum):
    """Status of migration validation process."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ValidationError:
    """Represents a validation error encountered during pipeline execution."""

    message: str
    error_type: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def __str__(self) -> str:
        return f"[{self.error_type}] {self.message}"


@dataclass
class MigrationValidationConfig:
    """Configuration for migration validation pipeline."""

    staging_timeout_seconds: int = 300
    performance_baseline_queries: List[str] = field(
        default_factory=lambda: [
            "SELECT COUNT(*) FROM {table_name}",
            "SELECT * FROM {table_name} LIMIT 100",
            "SELECT * FROM {table_name} WHERE {column_name} IS NOT NULL LIMIT 10",
        ]
    )
    rollback_validation_enabled: bool = True
    data_integrity_checks_enabled: bool = True
    parallel_validation_enabled: bool = True
    max_validation_time_seconds: int = 600
    performance_degradation_threshold: float = 0.20  # 20% threshold
    cleanup_on_failure: bool = True
    preserve_staging_on_failure: bool = False  # For debugging

    def __post_init__(self):
        """Validate configuration parameters."""
        if self.staging_timeout_seconds <= 0:
            raise ValueError("Staging timeout must be positive")
        if not 0 < self.performance_degradation_threshold <= 1.0:
            raise ValueError(
                "Performance degradation threshold must be between 0 and 1.0"
            )
        if self.max_validation_time_seconds <= 0:
            raise ValueError("Max validation time must be positive")


@dataclass
class MigrationValidationResult:
    """Comprehensive result of migration validation pipeline."""

    migration_id: str
    validation_status: ValidationStatus
    overall_risk_level: RiskLevel = RiskLevel.MEDIUM
    checkpoints: List[CheckpointResult] = field(default_factory=list)
    validation_errors: List[ValidationError] = field(default_factory=list)
    staging_environment_id: Optional[str] = None
    validation_duration_seconds: float = 0.0
    performance_impact_summary: str = ""
    risk_assessment: Optional[ComprehensiveRiskAssessment] = None
    dependency_report: Optional[DependencyReport] = None
    performance_comparison: Optional[PerformanceComparison] = None
    rollback_validation_result: Optional[CheckpointResult] = None
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    def is_successful(self) -> bool:
        """Check if validation was successful."""
        return self.validation_status == ValidationStatus.PASSED

    def get_failed_checkpoints(self) -> List[CheckpointResult]:
        """Get all failed validation checkpoints."""
        return [cp for cp in self.checkpoints if cp.status == CheckpointStatus.FAILED]

    def get_validation_summary(self) -> Dict[str, Any]:
        """Generate validation summary for reporting."""
        return {
            "migration_id": self.migration_id,
            "status": self.validation_status.value,
            "overall_risk": self.overall_risk_level.value,
            "duration_seconds": self.validation_duration_seconds,
            "checkpoints_passed": len(
                [cp for cp in self.checkpoints if cp.status == CheckpointStatus.PASSED]
            ),
            "checkpoints_failed": len(
                [cp for cp in self.checkpoints if cp.status == CheckpointStatus.FAILED]
            ),
            "validation_errors": len(self.validation_errors),
            "performance_acceptable": (
                self.performance_comparison.is_acceptable_performance
                if self.performance_comparison
                else None
            ),
            "staging_environment_id": self.staging_environment_id,
        }


class MigrationValidationPipeline:
    """
    Comprehensive migration validation system that runs migrations in staging before production.

    Provides complete validation workflows including performance validation, rollback testing,
    data integrity verification, and risk assessment integration.
    """

    def __init__(
        self,
        staging_manager: StagingEnvironmentManager,
        dependency_analyzer: DependencyAnalyzer,
        risk_engine: RiskAssessmentEngine,
        config: Optional[MigrationValidationConfig] = None,
    ):
        """
        Initialize the migration validation pipeline.

        Args:
            staging_manager: StagingEnvironmentManager for staging environments
            dependency_analyzer: DependencyAnalyzer for dependency analysis
            risk_engine: RiskAssessmentEngine for risk assessment
            config: Optional configuration for validation pipeline
        """
        if config is None:
            raise ValueError("Configuration cannot be None")

        self.config = config
        self.staging_manager = staging_manager
        self.dependency_analyzer = dependency_analyzer
        self.risk_engine = risk_engine

        # Initialize validation components
        self.checkpoint_manager = ValidationCheckpointManager()
        self.performance_validator = PerformanceValidator(
            config=PerformanceValidationConfig(
                baseline_queries=self.config.performance_baseline_queries,
                performance_degradation_threshold=self.config.performance_degradation_threshold,
            )
        )

        # Register validation checkpoints
        self._register_checkpoints()

        # Track active validations
        self._active_validations: Dict[str, asyncio.Task] = {}

        logger.info(
            f"MigrationValidationPipeline initialized with config: {self.config}"
        )

    def _register_checkpoints(self) -> None:
        """Register all validation checkpoints."""
        self.checkpoint_manager.register_checkpoint(
            CheckpointType.DEPENDENCY_ANALYSIS,
            DependencyAnalysisCheckpoint(dependency_analyzer=self.dependency_analyzer),
        )

        self.checkpoint_manager.register_checkpoint(
            CheckpointType.PERFORMANCE_VALIDATION,
            PerformanceValidationCheckpoint(
                baseline_queries=self.config.performance_baseline_queries,
                performance_threshold=self.config.performance_degradation_threshold,
            ),
        )

        if self.config.rollback_validation_enabled:
            self.checkpoint_manager.register_checkpoint(
                CheckpointType.ROLLBACK_VALIDATION, RollbackValidationCheckpoint()
            )

        if self.config.data_integrity_checks_enabled:
            self.checkpoint_manager.register_checkpoint(
                CheckpointType.DATA_INTEGRITY, DataIntegrityCheckpoint()
            )

        self.checkpoint_manager.register_checkpoint(
            CheckpointType.SCHEMA_CONSISTENCY, SchemaConsistencyCheckpoint()
        )

    async def validate_migration(
        self,
        migration_info: Dict[str, Any],
        production_db: Optional[ProductionDatabase] = None,
    ) -> MigrationValidationResult:
        """
        Execute complete migration validation pipeline in staging environment.

        Args:
            migration_info: Migration information including SQL, table, column details
            production_db: Optional production database configuration

        Returns:
            MigrationValidationResult: Comprehensive validation results
        """
        # Generate validation ID
        validation_id = (
            f"validation_{uuid.uuid4().hex[:8]}_{int(datetime.now().timestamp())}"
        )
        migration_info["validation_id"] = validation_id

        # Initialize validation result
        result = MigrationValidationResult(
            migration_id=migration_info.get("migration_id", validation_id),
            validation_status=ValidationStatus.IN_PROGRESS,
            started_at=datetime.now(),
        )

        # Start validation task
        validation_task = asyncio.create_task(
            self._execute_validation_pipeline(migration_info, production_db, result)
        )
        self._active_validations[validation_id] = validation_task

        try:
            # Execute validation with timeout
            result = await asyncio.wait_for(
                validation_task, timeout=self.config.max_validation_time_seconds
            )

        except asyncio.TimeoutError:
            result.validation_status = ValidationStatus.FAILED
            result.validation_errors.append(
                ValidationError(
                    message=f"Validation timed out after {self.config.max_validation_time_seconds} seconds",
                    error_type="VALIDATION_TIMEOUT",
                )
            )
            logger.error(f"Migration validation timed out for {result.migration_id}")

        except Exception as e:
            result.validation_status = ValidationStatus.FAILED
            result.validation_errors.append(
                ValidationError(
                    message=f"Validation failed with error: {str(e)}",
                    error_type="VALIDATION_ERROR",
                    details={"exception": str(e)},
                )
            )
            logger.error(f"Migration validation failed for {result.migration_id}: {e}")

        finally:
            # Clean up active validation tracking
            if validation_id in self._active_validations:
                del self._active_validations[validation_id]

            # Calculate final duration
            result.completed_at = datetime.now()
            result.validation_duration_seconds = (
                result.completed_at - result.started_at
            ).total_seconds()

        logger.info(
            f"Migration validation completed for {result.migration_id}: "
            f"Status={result.validation_status.value}, Duration={result.validation_duration_seconds:.2f}s"
        )

        return result

    async def _execute_validation_pipeline(
        self,
        migration_info: Dict[str, Any],
        production_db: Optional[ProductionDatabase],
        result: MigrationValidationResult,
    ) -> MigrationValidationResult:
        """
        Execute the complete validation pipeline workflow.

        This is the core pipeline that orchestrates all validation steps.
        """
        staging_environment: Optional[StagingEnvironment] = None

        try:
            # Step 1: Create staging environment
            logger.info(
                f"Creating staging environment for {migration_info['migration_id']}"
            )
            staging_environment = await self._create_staging_environment(
                migration_info, production_db
            )
            result.staging_environment_id = staging_environment.staging_id

            # Step 2: Replicate production schema to staging
            logger.info(
                f"Replicating production schema to staging {staging_environment.staging_id}"
            )
            await self._replicate_production_schema(staging_environment, migration_info)

            # Step 3: Execute validation checkpoints
            logger.info(
                f"Executing validation checkpoints for {migration_info['migration_id']}"
            )
            checkpoint_results = await self._execute_validation_checkpoints(
                staging_environment, migration_info
            )
            result.checkpoints = checkpoint_results

            # Step 4: Analyze checkpoint results
            validation_successful = self._analyze_checkpoint_results(
                checkpoint_results, result
            )

            # Step 5: Update risk assessment based on staging results
            logger.info("Updating risk assessment based on staging validation")
            await self._update_risk_assessment(migration_info, result)

            # Step 6: Determine final validation status
            if validation_successful and len(result.validation_errors) == 0:
                result.validation_status = ValidationStatus.PASSED
                logger.info(
                    f"Migration validation PASSED for {migration_info['migration_id']}"
                )
            else:
                result.validation_status = ValidationStatus.FAILED
                logger.warning(
                    f"Migration validation FAILED for {migration_info['migration_id']}"
                )

        except Exception as e:
            result.validation_status = ValidationStatus.FAILED
            result.validation_errors.append(
                ValidationError(
                    message=f"Pipeline execution failed: {str(e)}",
                    error_type="PIPELINE_ERROR",
                    details={"exception": str(e)},
                )
            )
            logger.error(
                f"Validation pipeline failed for {migration_info['migration_id']}: {e}"
            )

        finally:
            # Step 7: Clean up staging environment (unless preservation is requested)
            if staging_environment is not None:
                await self._cleanup_staging_environment(staging_environment, result)

        return result

    async def _create_staging_environment(
        self,
        migration_info: Dict[str, Any],
        production_db: Optional[ProductionDatabase],
    ) -> StagingEnvironment:
        """Create staging environment for validation."""
        if production_db is None:
            # Use default production database configuration
            production_db = ProductionDatabase(
                host=migration_info.get("prod_host", "localhost"),
                port=migration_info.get("prod_port", 5432),
                database=migration_info.get("prod_database", "production"),
                user=migration_info.get("prod_user", "postgres"),
                password=migration_info.get("prod_password", "password"),
            )

        try:
            staging_env = await asyncio.wait_for(
                self.staging_manager.create_staging_environment(
                    production_db=production_db,
                    data_sample_size=migration_info.get("data_sample_size", 0.1),
                ),
                timeout=self.config.staging_timeout_seconds,
            )

            logger.info(f"Created staging environment: {staging_env.staging_id}")
            return staging_env

        except Exception as e:
            logger.error(f"Failed to create staging environment: {e}")
            raise

    async def _replicate_production_schema(
        self, staging_environment: StagingEnvironment, migration_info: Dict[str, Any]
    ) -> None:
        """Replicate production schema to staging environment."""
        try:
            # Get tables related to migration
            tables_filter = migration_info.get("related_tables")
            if not tables_filter and "table_name" in migration_info:
                tables_filter = [migration_info["table_name"]]

            replication_result = await self.staging_manager.replicate_production_schema(
                staging_id=staging_environment.staging_id,
                include_data=True,
                tables_filter=tables_filter,
            )

            logger.info(
                f"Schema replication completed: {replication_result.tables_replicated} tables, "
                f"{replication_result.total_rows_sampled} rows sampled"
            )

        except Exception as e:
            logger.error(f"Schema replication failed: {e}")
            raise

    async def _execute_validation_checkpoints(
        self, staging_environment: StagingEnvironment, migration_info: Dict[str, Any]
    ) -> List[CheckpointResult]:
        """Execute all validation checkpoints."""
        if self.config.parallel_validation_enabled:
            return await self._execute_checkpoints_parallel(
                staging_environment, migration_info
            )
        else:
            return await self._execute_checkpoints_sequential(
                staging_environment, migration_info
            )

    async def _execute_checkpoints_parallel(
        self, staging_environment: StagingEnvironment, migration_info: Dict[str, Any]
    ) -> List[CheckpointResult]:
        """Execute validation checkpoints in parallel."""
        checkpoint_tasks = []

        # Create tasks for independent checkpoints
        independent_checkpoints = [
            CheckpointType.DEPENDENCY_ANALYSIS,
            CheckpointType.SCHEMA_CONSISTENCY,
        ]

        for checkpoint_type in independent_checkpoints:
            if checkpoint_type in self.checkpoint_manager.checkpoints:
                task = self.checkpoint_manager.execute_checkpoint(
                    checkpoint_type, staging_environment, migration_info
                )
                checkpoint_tasks.append(task)

        # Execute independent checkpoints in parallel
        independent_results = await asyncio.gather(
            *checkpoint_tasks, return_exceptions=True
        )

        # Convert exceptions to failed checkpoint results
        checkpoint_results = []
        for i, result in enumerate(independent_results):
            if isinstance(result, Exception):
                checkpoint_type = independent_checkpoints[i]
                checkpoint_results.append(
                    CheckpointResult(
                        checkpoint_type=checkpoint_type,
                        status=CheckpointStatus.FAILED,
                        message=f"Checkpoint failed with exception: {str(result)}",
                    )
                )
            else:
                checkpoint_results.append(result)

        # Execute dependent checkpoints sequentially
        dependent_checkpoints = [
            CheckpointType.PERFORMANCE_VALIDATION,
            CheckpointType.ROLLBACK_VALIDATION,
            CheckpointType.DATA_INTEGRITY,
        ]

        for checkpoint_type in dependent_checkpoints:
            if checkpoint_type in self.checkpoint_manager.checkpoints:
                try:
                    result = await self.checkpoint_manager.execute_checkpoint(
                        checkpoint_type, staging_environment, migration_info
                    )
                    checkpoint_results.append(result)
                except Exception as e:
                    checkpoint_results.append(
                        CheckpointResult(
                            checkpoint_type=checkpoint_type,
                            status=CheckpointStatus.FAILED,
                            message=f"Checkpoint failed with exception: {str(e)}",
                        )
                    )

        return checkpoint_results

    async def _execute_checkpoints_sequential(
        self, staging_environment: StagingEnvironment, migration_info: Dict[str, Any]
    ) -> List[CheckpointResult]:
        """Execute validation checkpoints sequentially."""
        checkpoint_results = []

        # Define checkpoint execution order
        checkpoint_order = [
            CheckpointType.DEPENDENCY_ANALYSIS,
            CheckpointType.SCHEMA_CONSISTENCY,
            CheckpointType.PERFORMANCE_VALIDATION,
            CheckpointType.ROLLBACK_VALIDATION,
            CheckpointType.DATA_INTEGRITY,
        ]

        for checkpoint_type in checkpoint_order:
            if checkpoint_type in self.checkpoint_manager.checkpoints:
                try:
                    result = await self.checkpoint_manager.execute_checkpoint(
                        checkpoint_type, staging_environment, migration_info
                    )
                    checkpoint_results.append(result)

                    # Stop on critical failures if configured
                    if (
                        result.status == CheckpointStatus.FAILED
                        and checkpoint_type == CheckpointType.DEPENDENCY_ANALYSIS
                    ):
                        logger.warning(
                            f"Critical checkpoint {checkpoint_type.value} failed, stopping validation"
                        )
                        break

                except Exception as e:
                    failed_result = CheckpointResult(
                        checkpoint_type=checkpoint_type,
                        status=CheckpointStatus.FAILED,
                        message=f"Checkpoint failed with exception: {str(e)}",
                    )
                    checkpoint_results.append(failed_result)

        return checkpoint_results

    def _analyze_checkpoint_results(
        self,
        checkpoint_results: List[CheckpointResult],
        result: MigrationValidationResult,
    ) -> bool:
        """Analyze checkpoint results and update validation result."""
        validation_successful = True

        for checkpoint_result in checkpoint_results:
            if checkpoint_result.status == CheckpointStatus.FAILED:
                validation_successful = False

                # Add validation error for failed checkpoint
                result.validation_errors.append(
                    ValidationError(
                        message=f"Checkpoint {checkpoint_result.checkpoint_type.value} failed: {checkpoint_result.message}",
                        error_type=f"CHECKPOINT_{checkpoint_result.checkpoint_type.value.upper()}_FAILED",
                        details=checkpoint_result.details,
                    )
                )

                # Handle specific checkpoint failures
                if (
                    checkpoint_result.checkpoint_type
                    == CheckpointType.DEPENDENCY_ANALYSIS
                ):
                    # Critical dependency failures
                    critical_deps = checkpoint_result.details.get(
                        "critical_dependency_count", 0
                    )
                    if critical_deps > 0:
                        result.validation_errors.append(
                            ValidationError(
                                message=f"Found {critical_deps} critical dependencies that would be broken",
                                error_type="CRITICAL_DEPENDENCIES_FOUND",
                                details={"critical_dependency_count": critical_deps},
                            )
                        )

                elif (
                    checkpoint_result.checkpoint_type
                    == CheckpointType.PERFORMANCE_VALIDATION
                ):
                    # Performance degradation failures
                    degradation = checkpoint_result.details.get(
                        "degradation_percent", 0
                    )
                    result.validation_errors.append(
                        ValidationError(
                            message=f"Performance degradation ({degradation}%) exceeds threshold ({self.config.performance_degradation_threshold * 100}%)",
                            error_type="PERFORMANCE_DEGRADATION_EXCEEDED",
                            details={"degradation_percent": degradation},
                        )
                    )

                elif (
                    checkpoint_result.checkpoint_type
                    == CheckpointType.ROLLBACK_VALIDATION
                ):
                    # Rollback validation failures
                    result.validation_errors.append(
                        ValidationError(
                            message="Rollback validation failed - migration may not be safely reversible",
                            error_type="ROLLBACK_VALIDATION_FAILED",
                            details=checkpoint_result.details,
                        )
                    )

        return validation_successful

    async def _update_risk_assessment(
        self, migration_info: Dict[str, Any], result: MigrationValidationResult
    ) -> None:
        """Update risk assessment based on staging validation results."""
        try:
            # Gather risk factors from validation results
            risk_factors = self._extract_risk_factors_from_validation(result)

            # Update risk assessment with staging validation data
            updated_assessment = await self.risk_engine.assess_migration_risk(
                operation_id=migration_info["migration_id"],
                table_name=migration_info.get("table_name", ""),
                column_name=migration_info.get("column_name", ""),
                additional_factors=risk_factors,
            )

            result.risk_assessment = updated_assessment
            result.overall_risk_level = updated_assessment.risk_level

            logger.info(
                f"Updated risk assessment: {updated_assessment.risk_level.value} "
                f"(score: {updated_assessment.overall_score})"
            )

        except Exception as e:
            logger.warning(f"Failed to update risk assessment: {e}")
            # Don't fail validation due to risk assessment issues

    def _extract_risk_factors_from_validation(
        self, result: MigrationValidationResult
    ) -> Dict[str, Any]:
        """Extract risk factors from validation results."""
        risk_factors = {
            "staging_validation_completed": True,
            "validation_errors_count": len(result.validation_errors),
            "failed_checkpoints_count": len(result.get_failed_checkpoints()),
        }

        # Add checkpoint-specific risk factors
        for checkpoint in result.checkpoints:
            if checkpoint.checkpoint_type == CheckpointType.DEPENDENCY_ANALYSIS:
                critical_deps = checkpoint.details.get("critical_dependency_count", 0)
                risk_factors["critical_dependencies_found"] = critical_deps > 0
                risk_factors["critical_dependency_count"] = critical_deps

            elif checkpoint.checkpoint_type == CheckpointType.PERFORMANCE_VALIDATION:
                degradation = checkpoint.details.get("degradation_percent", 0)
                risk_factors["performance_degradation_percent"] = degradation
                risk_factors["performance_acceptable"] = (
                    checkpoint.status == CheckpointStatus.PASSED
                )

        return risk_factors

    async def _cleanup_staging_environment(
        self, staging_environment: StagingEnvironment, result: MigrationValidationResult
    ) -> None:
        """Clean up staging environment after validation."""
        should_cleanup = (
            self.config.cleanup_on_failure
            or result.validation_status == ValidationStatus.PASSED
            or not self.config.preserve_staging_on_failure
        )

        if should_cleanup:
            try:
                cleanup_result = await self.staging_manager.cleanup_staging_environment(
                    staging_environment.staging_id
                )
                logger.info(
                    f"Cleaned up staging environment: {staging_environment.staging_id}"
                )

            except Exception as e:
                logger.warning(
                    f"Failed to cleanup staging environment {staging_environment.staging_id}: {e}"
                )
                # Don't fail validation due to cleanup issues
        else:
            logger.info(
                f"Preserving staging environment for debugging: {staging_environment.staging_id}"
            )

    async def get_validation_status(
        self, validation_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get status of ongoing validation."""
        if validation_id in self._active_validations:
            task = self._active_validations[validation_id]
            return {
                "validation_id": validation_id,
                "status": "in_progress",
                "done": task.done(),
                "cancelled": task.cancelled(),
            }
        return None

    async def cancel_validation(self, validation_id: str) -> bool:
        """Cancel ongoing validation."""
        if validation_id in self._active_validations:
            task = self._active_validations[validation_id]
            task.cancel()
            return True
        return False

    def get_active_validations(self) -> List[str]:
        """Get list of active validation IDs."""
        return list(self._active_validations.keys())
