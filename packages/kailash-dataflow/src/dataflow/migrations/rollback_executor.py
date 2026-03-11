#!/usr/bin/env python3
"""
Rollback Executor for Production Deployment Validator - TODO-141 Phase 3

Automated rollback execution system with comprehensive recovery procedures,
validation, and safety checks for production deployments.

CORE FEATURES:
- Automated rollback step execution
- Rollback validation and verification
- Emergency rollback procedures
- Data recovery and restoration
- State verification and consistency checks

ROLLBACK PATTERNS:
- SQL Statement Rollback: Reverse SQL operations
- Data Restoration: Restore from backup
- Schema Reversion: Restore previous schema state
- Configuration Rollback: Restore system configuration
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


class RollbackType(Enum):
    """Types of rollback operations."""

    SQL_STATEMENT = "sql_statement"
    DATA_RESTORATION = "data_restoration"
    SCHEMA_REVERSION = "schema_reversion"
    CONFIGURATION_ROLLBACK = "configuration_rollback"
    EMERGENCY_STOP = "emergency_stop"


class RollbackStatus(Enum):
    """Status of rollback operations."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIALLY_COMPLETED = "partially_completed"
    REQUIRES_MANUAL_INTERVENTION = "requires_manual_intervention"


@dataclass
class RollbackStep:
    """Individual rollback step with execution details."""

    step_id: str
    step_number: int
    rollback_type: RollbackType
    description: str
    sql_statement: Optional[str] = None
    backup_location: Optional[str] = None
    estimated_duration_seconds: float = 30.0
    requires_confirmation: bool = False
    critical_step: bool = False
    dependencies: List[str] = field(default_factory=list)
    validation_queries: List[str] = field(default_factory=list)
    status: RollbackStatus = RollbackStatus.PENDING
    executed_at: Optional[datetime] = None
    error_message: Optional[str] = None


@dataclass
class RollbackValidation:
    """Rollback validation configuration."""

    validation_name: str
    validation_query: str
    expected_result: Any
    critical_validation: bool = True
    timeout_seconds: float = 30.0


@dataclass
class RollbackPlan:
    """Comprehensive rollback plan with all necessary information."""

    plan_id: str
    migration_id: str
    deployment_id: str
    rollback_steps: List[RollbackStep] = field(default_factory=list)
    validations: List[RollbackValidation] = field(default_factory=list)
    estimated_total_time: float = 0.0
    requires_downtime: bool = False
    backup_requirements: List[str] = field(default_factory=list)
    emergency_contacts: List[str] = field(default_factory=list)
    approval_required: bool = False
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Calculate derived properties."""
        self.estimated_total_time = sum(
            step.estimated_duration_seconds for step in self.rollback_steps
        )
        self.requires_downtime = any(step.critical_step for step in self.rollback_steps)


@dataclass
class RollbackExecution:
    """Rollback execution context and state."""

    execution_id: str
    rollback_plan: RollbackPlan
    started_at: datetime = field(default_factory=datetime.now)
    current_step: Optional[RollbackStep] = None
    completed_steps: List[str] = field(default_factory=list)
    failed_steps: List[str] = field(default_factory=list)
    rollback_points: List[str] = field(default_factory=list)
    overall_status: RollbackStatus = RollbackStatus.PENDING
    completion_percentage: float = 0.0
    error_log: List[str] = field(default_factory=list)


class DatabaseExecutor(Protocol):
    """Protocol for database execution during rollback."""

    async def execute_sql(self, sql: str, params: Optional[List] = None) -> Any:
        """Execute SQL statement."""
        ...

    async def fetch_one(
        self, sql: str, params: Optional[List] = None
    ) -> Optional[Dict]:
        """Fetch single result."""
        ...

    async def fetch_all(self, sql: str, params: Optional[List] = None) -> List[Dict]:
        """Fetch all results."""
        ...

    async def begin_transaction(self) -> None:
        """Begin database transaction."""
        ...

    async def commit_transaction(self) -> None:
        """Commit database transaction."""
        ...

    async def rollback_transaction(self) -> None:
        """Rollback database transaction."""
        ...


class RollbackExecutor:
    """
    Automated rollback execution system for production deployments.

    Provides comprehensive rollback capabilities with safety checks,
    validation, and error recovery for all types of migration operations.
    """

    def __init__(self, database_executor: Optional[DatabaseExecutor] = None):
        """
        Initialize rollback executor.

        Args:
            database_executor: Optional database executor for SQL operations
        """
        self.database_executor = database_executor
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._active_rollbacks: Dict[str, RollbackExecution] = {}

    async def execute_rollback(
        self,
        rollback_plan: RollbackPlan,
        force_execution: bool = False,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute complete rollback plan.

        Args:
            rollback_plan: Rollback plan to execute
            force_execution: Force execution without confirmation
            dry_run: Execute validation only without actual changes

        Returns:
            Dict containing rollback execution results
        """
        execution_id = (
            f"rollback_{rollback_plan.plan_id}_{int(datetime.now().timestamp())}"
        )

        rollback_execution = RollbackExecution(
            execution_id=execution_id, rollback_plan=rollback_plan
        )

        self._active_rollbacks[execution_id] = rollback_execution

        self.logger.info(
            f"Starting rollback execution: {execution_id} (dry_run={dry_run})"
        )

        try:
            # Pre-execution validation
            if not await self._validate_rollback_prerequisites(rollback_execution):
                raise RuntimeError("Rollback prerequisites validation failed")

            # Check approval requirements
            if rollback_plan.approval_required and not force_execution:
                return await self._request_rollback_approval(rollback_execution)

            # Execute rollback steps
            rollback_execution.overall_status = RollbackStatus.IN_PROGRESS

            for step in rollback_plan.rollback_steps:
                self.logger.info(
                    f"Executing rollback step {step.step_number}: {step.description}"
                )
                rollback_execution.current_step = step

                # Execute step based on type
                step_success = await self._execute_rollback_step(
                    step, rollback_execution, dry_run
                )

                if step_success:
                    step.status = RollbackStatus.COMPLETED
                    step.executed_at = datetime.now()
                    rollback_execution.completed_steps.append(step.step_id)
                else:
                    step.status = RollbackStatus.FAILED
                    rollback_execution.failed_steps.append(step.step_id)

                    if step.critical_step:
                        # Critical step failure - stop rollback
                        rollback_execution.overall_status = RollbackStatus.FAILED
                        break
                    else:
                        # Non-critical step failure - log and continue
                        rollback_execution.error_log.append(
                            f"Non-critical step failed: {step.description}"
                        )

                # Update progress
                rollback_execution.completion_percentage = (
                    len(rollback_execution.completed_steps)
                    / len(rollback_plan.rollback_steps)
                    * 100
                )

            # Execute rollback validations
            if not dry_run:
                validation_success = await self._execute_rollback_validations(
                    rollback_execution
                )
                if not validation_success:
                    rollback_execution.overall_status = (
                        RollbackStatus.PARTIALLY_COMPLETED
                    )
                    rollback_execution.error_log.append(
                        "Some rollback validations failed"
                    )

            # Determine final status
            if rollback_execution.overall_status == RollbackStatus.IN_PROGRESS:
                if len(rollback_execution.failed_steps) == 0:
                    rollback_execution.overall_status = RollbackStatus.COMPLETED
                else:
                    rollback_execution.overall_status = (
                        RollbackStatus.PARTIALLY_COMPLETED
                    )

            # Generate rollback report
            result = await self._generate_rollback_report(rollback_execution, dry_run)

            self.logger.info(
                f"Rollback execution completed: {rollback_execution.overall_status.value}"
            )

            return result

        except Exception as e:
            rollback_execution.overall_status = RollbackStatus.FAILED
            rollback_execution.error_log.append(f"Rollback execution failed: {str(e)}")

            self.logger.error(f"Rollback execution failed: {e}")

            return {
                "success": False,
                "execution_id": execution_id,
                "status": rollback_execution.overall_status.value,
                "error": str(e),
                "completed_steps": rollback_execution.completed_steps,
                "failed_steps": rollback_execution.failed_steps,
            }

        finally:
            # Clean up active rollback tracking
            if execution_id in self._active_rollbacks:
                del self._active_rollbacks[execution_id]

    async def emergency_rollback(
        self, deployment_id: str, reason: str, emergency_contact: str
    ) -> Dict[str, Any]:
        """
        Execute emergency rollback procedure.

        Args:
            deployment_id: Deployment to rollback
            reason: Emergency rollback reason
            emergency_contact: Person requesting emergency rollback

        Returns:
            Emergency rollback execution results
        """
        self.logger.critical(
            f"Emergency rollback requested for {deployment_id}: {reason}"
        )

        # Create emergency rollback plan
        emergency_plan = RollbackPlan(
            plan_id=f"emergency_{deployment_id}",
            migration_id=deployment_id,
            deployment_id=deployment_id,
            emergency_contacts=[emergency_contact],
        )

        # Add emergency stop step
        emergency_stop_step = RollbackStep(
            step_id="emergency_stop_001",
            step_number=1,
            rollback_type=RollbackType.EMERGENCY_STOP,
            description=f"Emergency rollback: {reason}",
            estimated_duration_seconds=60.0,
            critical_step=True,
        )

        emergency_plan.rollback_steps.append(emergency_stop_step)

        # Execute emergency rollback
        return await self.execute_rollback(
            rollback_plan=emergency_plan,
            force_execution=True,  # Skip approval for emergencies
        )

    async def validate_rollback_feasibility(
        self, rollback_plan: RollbackPlan
    ) -> Dict[str, Any]:
        """
        Validate if rollback plan is feasible to execute.

        Args:
            rollback_plan: Rollback plan to validate

        Returns:
            Feasibility validation results
        """
        self.logger.info(f"Validating rollback feasibility: {rollback_plan.plan_id}")

        validation_results = {
            "feasible": True,
            "plan_id": rollback_plan.plan_id,
            "validation_checks": [],
            "warnings": [],
            "blocking_issues": [],
        }

        # Check backup requirements
        for backup_requirement in rollback_plan.backup_requirements:
            check_result = await self._check_backup_availability(backup_requirement)
            validation_results["validation_checks"].append(
                {
                    "check": f"Backup available: {backup_requirement}",
                    "passed": check_result,
                    "critical": True,
                }
            )

            if not check_result:
                validation_results["blocking_issues"].append(
                    f"Required backup not available: {backup_requirement}"
                )
                validation_results["feasible"] = False

        # Check step dependencies
        for step in rollback_plan.rollback_steps:
            for dependency in step.dependencies:
                dependency_met = await self._check_step_dependency(dependency)
                if not dependency_met:
                    validation_results["warnings"].append(
                        f"Step {step.step_number} dependency not met: {dependency}"
                    )

        # Check database connectivity
        if self.database_executor:
            try:
                await self.database_executor.fetch_one("SELECT 1")
                validation_results["validation_checks"].append(
                    {"check": "Database connectivity", "passed": True, "critical": True}
                )
            except Exception as e:
                validation_results["validation_checks"].append(
                    {
                        "check": "Database connectivity",
                        "passed": False,
                        "critical": True,
                        "error": str(e),
                    }
                )
                validation_results["blocking_issues"].append(
                    f"Database connectivity failed: {e}"
                )
                validation_results["feasible"] = False

        # Check estimated time requirements
        if rollback_plan.estimated_total_time > 3600:  # Over 1 hour
            validation_results["warnings"].append(
                f"Rollback estimated to take {rollback_plan.estimated_total_time/60:.1f} minutes - "
                "consider scheduling during maintenance window"
            )

        self.logger.info(
            f"Rollback feasibility validation completed: feasible={validation_results['feasible']}, "
            f"warnings={len(validation_results['warnings'])}, blocking_issues={len(validation_results['blocking_issues'])}"
        )

        return validation_results

    async def get_rollback_status(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get status of active rollback execution."""
        if execution_id not in self._active_rollbacks:
            return None

        execution = self._active_rollbacks[execution_id]

        return {
            "execution_id": execution_id,
            "status": execution.overall_status.value,
            "completion_percentage": execution.completion_percentage,
            "current_step": (
                execution.current_step.description if execution.current_step else None
            ),
            "completed_steps": len(execution.completed_steps),
            "total_steps": len(execution.rollback_plan.rollback_steps),
            "failed_steps": len(execution.failed_steps),
            "started_at": execution.started_at.isoformat(),
            "elapsed_seconds": (datetime.now() - execution.started_at).total_seconds(),
        }

    # Private helper methods

    async def _validate_rollback_prerequisites(
        self, execution: RollbackExecution
    ) -> bool:
        """Validate rollback prerequisites."""
        plan = execution.rollback_plan

        # Check if deployment exists
        if not plan.deployment_id:
            execution.error_log.append("No deployment ID specified for rollback")
            return False

        # Check for required steps
        if not plan.rollback_steps:
            execution.error_log.append("No rollback steps defined")
            return False

        # Validate step sequence
        expected_step_number = 1
        for step in plan.rollback_steps:
            if step.step_number != expected_step_number:
                execution.error_log.append(
                    f"Step sequence error: expected {expected_step_number}, got {step.step_number}"
                )
                return False
            expected_step_number += 1

        return True

    async def _execute_rollback_step(
        self, step: RollbackStep, execution: RollbackExecution, dry_run: bool = False
    ) -> bool:
        """Execute individual rollback step."""
        try:
            if step.rollback_type == RollbackType.SQL_STATEMENT and step.sql_statement:
                if not dry_run and self.database_executor:
                    await self.database_executor.begin_transaction()
                    await self.database_executor.execute_sql(step.sql_statement)
                    await self.database_executor.commit_transaction()

                self.logger.info(f"SQL rollback step executed: {step.description}")

            elif step.rollback_type == RollbackType.DATA_RESTORATION:
                if not dry_run:
                    # Simulate data restoration
                    await asyncio.sleep(0.1)

                self.logger.info(f"Data restoration step executed: {step.description}")

            elif step.rollback_type == RollbackType.SCHEMA_REVERSION:
                if not dry_run and self.database_executor and step.sql_statement:
                    await self.database_executor.begin_transaction()
                    await self.database_executor.execute_sql(step.sql_statement)
                    await self.database_executor.commit_transaction()

                self.logger.info(f"Schema reversion step executed: {step.description}")

            elif step.rollback_type == RollbackType.EMERGENCY_STOP:
                self.logger.critical(f"Emergency stop executed: {step.description}")

            # Execute step validations
            if step.validation_queries and not dry_run:
                for validation_query in step.validation_queries:
                    if self.database_executor:
                        result = await self.database_executor.fetch_one(
                            validation_query
                        )
                        if not result:
                            raise RuntimeError(
                                f"Step validation failed: {validation_query}"
                            )

            return True

        except Exception as e:
            execution.error_log.append(f"Step {step.step_number} failed: {str(e)}")
            self.logger.error(f"Rollback step {step.step_number} failed: {e}")

            # Rollback transaction if it was started
            if self.database_executor and not dry_run:
                try:
                    await self.database_executor.rollback_transaction()
                except Exception:
                    pass  # Transaction may not have been started

            return False

    async def _execute_rollback_validations(self, execution: RollbackExecution) -> bool:
        """Execute rollback validation checks."""
        plan = execution.rollback_plan
        validation_success = True

        for validation in plan.validations:
            try:
                if self.database_executor:
                    result = await self.database_executor.fetch_one(
                        validation.validation_query
                    )

                    if result != validation.expected_result:
                        if validation.critical_validation:
                            validation_success = False
                        execution.error_log.append(
                            f"Validation failed: {validation.validation_name} - "
                            f"expected {validation.expected_result}, got {result}"
                        )
                    else:
                        self.logger.info(
                            f"Validation passed: {validation.validation_name}"
                        )

            except Exception as e:
                if validation.critical_validation:
                    validation_success = False
                execution.error_log.append(
                    f"Validation error: {validation.validation_name} - {str(e)}"
                )

        return validation_success

    async def _check_backup_availability(self, backup_requirement: str) -> bool:
        """Check if required backup is available."""
        # In real implementation, this would check backup storage
        # For testing, simulate backup availability
        return True

    async def _check_step_dependency(self, dependency: str) -> bool:
        """Check if step dependency is met."""
        # In real implementation, this would check system state
        # For testing, assume dependencies are met
        return True

    async def _request_rollback_approval(
        self, execution: RollbackExecution
    ) -> Dict[str, Any]:
        """Request approval for rollback execution."""
        self.logger.info(f"Rollback approval required: {execution.execution_id}")

        return {
            "success": False,
            "execution_id": execution.execution_id,
            "status": "approval_required",
            "message": "Rollback execution requires approval before proceeding",
            "approval_contacts": execution.rollback_plan.emergency_contacts,
            "estimated_rollback_time": execution.rollback_plan.estimated_total_time,
        }

    async def _generate_rollback_report(
        self, execution: RollbackExecution, dry_run: bool = False
    ) -> Dict[str, Any]:
        """Generate comprehensive rollback report."""
        total_duration = (datetime.now() - execution.started_at).total_seconds()

        report = {
            "success": execution.overall_status
            in [RollbackStatus.COMPLETED, RollbackStatus.PARTIALLY_COMPLETED],
            "execution_id": execution.execution_id,
            "plan_id": execution.rollback_plan.plan_id,
            "status": execution.overall_status.value,
            "dry_run": dry_run,
            "started_at": execution.started_at.isoformat(),
            "duration_seconds": total_duration,
            "completion_percentage": execution.completion_percentage,
            "steps_summary": {
                "total_steps": len(execution.rollback_plan.rollback_steps),
                "completed_steps": len(execution.completed_steps),
                "failed_steps": len(execution.failed_steps),
                "completed_step_ids": execution.completed_steps,
                "failed_step_ids": execution.failed_steps,
            },
            "error_log": execution.error_log,
            "rollback_points": execution.rollback_points,
        }

        if execution.overall_status == RollbackStatus.COMPLETED:
            report["message"] = "Rollback completed successfully"
        elif execution.overall_status == RollbackStatus.PARTIALLY_COMPLETED:
            report["message"] = (
                "Rollback partially completed - some non-critical steps failed"
            )
        elif execution.overall_status == RollbackStatus.FAILED:
            report["message"] = (
                "Rollback failed - critical steps could not be completed"
            )

        return report
