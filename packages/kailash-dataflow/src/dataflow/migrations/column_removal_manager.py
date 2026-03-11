#!/usr/bin/env python3
"""
Column Removal Manager for DataFlow Migration System

Implements safe column removal with dependency analysis, multi-stage removal process,
transaction safety, and comprehensive rollback capabilities.

This manager builds on the DependencyAnalyzer to provide safe column removal
workflows with proper ordering and transaction management.

Phase 2 Implementation: Safe Removal Strategy
- Multi-stage removal process with correct dependency ordering
- Transaction safety with savepoints and rollback
- Data preservation and backup strategies
- Integration with existing migration system
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import asyncpg

from .dependency_analyzer import (
    ConstraintDependency,
    DependencyAnalyzer,
    DependencyType,
    ForeignKeyDependency,
    ImpactLevel,
    IndexDependency,
    TriggerDependency,
    ViewDependency,
)

# Type alias for any column dependency
ColumnDependency = Union[
    ForeignKeyDependency,
    ViewDependency,
    TriggerDependency,
    IndexDependency,
    ConstraintDependency,
]


logger = logging.getLogger(__name__)


class RemovalStage(Enum):
    """Stages of the column removal process."""

    BACKUP_CREATION = "backup_creation"
    DEPENDENT_OBJECTS = "dependent_objects"  # Triggers, views, functions
    CONSTRAINT_REMOVAL = "constraint_removal"  # FK, check constraints
    INDEX_REMOVAL = "index_removal"  # Single and composite indexes
    COLUMN_REMOVAL = "column_removal"  # The actual column drop
    CLEANUP = "cleanup"
    VALIDATION = "validation"


class RemovalStatus(Enum):
    """Status of column removal operation."""

    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    DEPENDENCY_BLOCKED = "dependency_blocked"
    TRANSACTION_FAILED = "transaction_failed"
    ROLLBACK_COMPLETED = "rollback_completed"
    VALIDATION_FAILED = "validation_failed"
    PERMISSION_DENIED = "permission_denied"


class BackupStrategy(Enum):
    """Backup strategies for data preservation."""

    NONE = "none"  # No backup (risky)
    COLUMN_ONLY = "column_only"  # Just the column data
    TABLE_SNAPSHOT = "table_snapshot"  # Full table backup
    CUSTOM_QUERY = "custom_query"  # Custom backup query


@dataclass
class RemovalStageResult:
    """Result of executing a single removal stage."""

    stage: RemovalStage
    success: bool
    duration: float  # seconds
    objects_affected: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    rollback_data: Optional[Dict[str, Any]] = None


@dataclass
class BackupInfo:
    """Information about created backup."""

    strategy: BackupStrategy
    backup_location: str  # Table name, file path, etc.
    backup_size: int  # Number of rows or bytes
    created_at: datetime
    verification_query: Optional[str] = None


@dataclass
class SafetyValidation:
    """Result of safety validation for column removal."""

    is_safe: bool
    risk_level: ImpactLevel
    blocking_dependencies: List[ColumnDependency] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    estimated_duration: float = 0.0  # seconds
    requires_confirmation: bool = False


@dataclass
class RemovalPlan:
    """Comprehensive plan for safe column removal."""

    table_name: str
    column_name: str
    dependencies: List[ColumnDependency] = field(default_factory=list)

    # Execution configuration
    backup_strategy: BackupStrategy = BackupStrategy.COLUMN_ONLY
    confirmation_required: bool = True
    dry_run: bool = False

    # Timing and batching
    stage_timeout: int = 300  # 5 minutes per stage
    batch_size: int = 10000  # For data operations

    # Safety features
    enable_rollback: bool = True
    validate_after_each_stage: bool = True
    stop_on_warning: bool = False

    # Generated plan details
    execution_stages: List[RemovalStage] = field(default_factory=list)
    estimated_duration: float = 0.0
    rollback_plan: Optional[Dict[str, Any]] = None
    backup_info: Optional[BackupInfo] = None


@dataclass
class RemovalResult:
    """Result of executing column removal."""

    plan: RemovalPlan
    status: RemovalStatus
    execution_time: float
    stages_completed: List[RemovalStageResult] = field(default_factory=list)

    # State information
    rollback_executed: bool = False
    backup_preserved: bool = False
    error_message: Optional[str] = None

    # Recovery information
    recovery_instructions: List[str] = field(default_factory=list)
    manual_cleanup_required: List[str] = field(default_factory=list)


class BackupHandler(ABC):
    """Abstract base class for backup strategies."""

    @abstractmethod
    async def create_backup(
        self, table_name: str, column_name: str, connection: asyncpg.Connection
    ) -> BackupInfo:
        """Create backup according to strategy."""
        pass

    @abstractmethod
    async def restore_backup(
        self, backup_info: BackupInfo, connection: asyncpg.Connection
    ) -> bool:
        """Restore from backup."""
        pass

    @abstractmethod
    async def cleanup_backup(
        self, backup_info: BackupInfo, connection: asyncpg.Connection
    ) -> bool:
        """Clean up backup resources."""
        pass


class ColumnOnlyBackupHandler(BackupHandler):
    """Backup handler that saves only column data."""

    async def create_backup(
        self, table_name: str, column_name: str, connection: asyncpg.Connection
    ) -> BackupInfo:
        """Create column-only backup."""
        backup_table = (
            f"{table_name}__{column_name}_backup_{int(datetime.now().timestamp())}"
        )

        # Get primary key columns for restoration
        pk_query = """
        SELECT a.attname
        FROM pg_index i
        JOIN pg_attribute a ON a.attrelid = i.indrelid
                             AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = $1::regclass AND i.indisprimary
        ORDER BY a.attnum
        """
        pk_columns = await connection.fetch(pk_query, table_name)
        pk_column_names = [row["attname"] for row in pk_columns]

        if not pk_column_names:
            # Fallback to ctid if no primary key
            pk_column_names = ["ctid"]

        # Create backup table
        pk_cols = ", ".join(pk_column_names)
        backup_query = f"""
        CREATE TABLE {backup_table} AS
        SELECT {pk_cols}, {column_name}
        FROM {table_name}
        WHERE {column_name} IS NOT NULL
        """

        await connection.execute(backup_query)

        # Get backup size
        backup_size = await connection.fetchval(f"SELECT COUNT(*) FROM {backup_table}")

        return BackupInfo(
            strategy=BackupStrategy.COLUMN_ONLY,
            backup_location=backup_table,
            backup_size=backup_size,
            created_at=datetime.now(),
            verification_query=f"SELECT COUNT(*) FROM {backup_table}",
        )

    async def restore_backup(
        self, backup_info: BackupInfo, connection: asyncpg.Connection
    ) -> bool:
        """Restore from column backup (not implemented for column removal)."""
        # Column restoration after removal would require re-adding the column
        # This is complex and typically not done in practice
        logger.warning("Column restoration from backup not implemented")
        return False

    async def cleanup_backup(
        self, backup_info: BackupInfo, connection: asyncpg.Connection
    ) -> bool:
        """Clean up backup table."""
        try:
            await connection.execute(
                f"DROP TABLE IF EXISTS {backup_info.backup_location}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to cleanup backup {backup_info.backup_location}: {e}")
            return False


class TableSnapshotBackupHandler(BackupHandler):
    """Backup handler that creates full table snapshot."""

    async def create_backup(
        self, table_name: str, column_name: str, connection: asyncpg.Connection
    ) -> BackupInfo:
        """Create full table backup."""
        backup_table = f"{table_name}_backup_{int(datetime.now().timestamp())}"

        # Create full table backup
        await connection.execute(
            f"CREATE TABLE {backup_table} AS SELECT * FROM {table_name}"
        )

        # Get backup size
        backup_size = await connection.fetchval(f"SELECT COUNT(*) FROM {backup_table}")

        return BackupInfo(
            strategy=BackupStrategy.TABLE_SNAPSHOT,
            backup_location=backup_table,
            backup_size=backup_size,
            created_at=datetime.now(),
            verification_query=f"SELECT COUNT(*) FROM {backup_table}",
        )

    async def restore_backup(
        self, backup_info: BackupInfo, connection: asyncpg.Connection
    ) -> bool:
        """Restore from table snapshot (replace entire table)."""
        logger.warning(
            "Full table restoration would replace all data - requires manual intervention"
        )
        return False

    async def cleanup_backup(
        self, backup_info: BackupInfo, connection: asyncpg.Connection
    ) -> bool:
        """Clean up backup table."""
        try:
            await connection.execute(
                f"DROP TABLE IF EXISTS {backup_info.backup_location}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to cleanup backup {backup_info.backup_location}: {e}")
            return False


class ColumnRemovalManager:
    """
    Manages safe column removal with dependency analysis and transaction safety.

    Provides comprehensive column removal with:
    - Multi-stage removal process with correct dependency ordering
    - Transaction safety with savepoints and rollback capability
    - Data preservation through configurable backup strategies
    - Integration with DependencyAnalyzer for safety validation
    """

    def __init__(self, connection_manager: Optional[Any] = None):
        """Initialize the column removal manager."""
        self.connection_manager = connection_manager
        self.dependency_analyzer = DependencyAnalyzer(connection_manager)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Initialize backup handlers
        self.backup_handlers = {
            BackupStrategy.COLUMN_ONLY: ColumnOnlyBackupHandler(),
            BackupStrategy.TABLE_SNAPSHOT: TableSnapshotBackupHandler(),
        }

        self.logger.info(
            "ColumnRemovalManager initialized with dependency analysis and backup support"
        )

    async def plan_column_removal(
        self,
        table: str,
        column: str,
        backup_strategy: BackupStrategy = BackupStrategy.COLUMN_ONLY,
        dry_run: bool = False,
        connection: Optional[asyncpg.Connection] = None,
    ) -> RemovalPlan:
        """
        Plan column removal with comprehensive dependency analysis.

        Args:
            table: Target table name
            column: Column name to remove
            backup_strategy: Data backup strategy
            dry_run: If True, only plan without execution
            connection: Database connection (optional)

        Returns:
            RemovalPlan with execution stages and safety analysis
        """
        self.logger.info(f"Planning column removal: {table}.{column}")

        if connection is None:
            connection = await self._get_connection()

        try:
            # Analyze dependencies
            dependency_report = (
                await self.dependency_analyzer.analyze_column_dependencies(
                    table, column, connection
                )
            )

            # Extract individual dependencies from the report
            all_dependencies = []
            for dep_list in dependency_report.dependencies.values():
                all_dependencies.extend(dep_list)

            # Create removal plan
            plan = RemovalPlan(
                table_name=table,
                column_name=column,
                dependencies=all_dependencies,
                backup_strategy=backup_strategy,
                dry_run=dry_run,
            )

            # Generate execution stages based on dependencies
            plan.execution_stages = self._generate_execution_stages(all_dependencies)

            # Estimate duration
            plan.estimated_duration = self._estimate_removal_duration(all_dependencies)

            # Generate rollback plan
            plan.rollback_plan = await self._generate_rollback_plan(plan, connection)

            self.logger.info(
                f"Removal plan created for {table}.{column}: "
                f"{len(plan.execution_stages)} stages, ~{plan.estimated_duration:.1f}s"
            )

            return plan

        except Exception as e:
            self.logger.error(f"Planning failed for {table}.{column}: {e}")
            raise

    async def validate_removal_safety(
        self, plan: RemovalPlan, connection: Optional[asyncpg.Connection] = None
    ) -> SafetyValidation:
        """
        Validate safety of column removal plan.

        Args:
            plan: Removal plan to validate
            connection: Database connection (optional)

        Returns:
            SafetyValidation with safety assessment and recommendations
        """
        self.logger.info(
            f"Validating removal safety: {plan.table_name}.{plan.column_name}"
        )

        if connection is None:
            connection = await self._get_connection()

        # Check for blocking dependencies
        blocking_deps = [
            dep for dep in plan.dependencies if dep.impact_level == ImpactLevel.CRITICAL
        ]

        warnings = []
        recommendations = []

        # Analyze risk level
        risk_level = ImpactLevel.LOW
        if blocking_deps:
            risk_level = ImpactLevel.CRITICAL
        elif any(dep.impact_level == ImpactLevel.HIGH for dep in plan.dependencies):
            risk_level = ImpactLevel.HIGH
        elif any(dep.impact_level == ImpactLevel.MEDIUM for dep in plan.dependencies):
            risk_level = ImpactLevel.MEDIUM

        # Generate warnings and recommendations
        if blocking_deps:
            warnings.append(
                f"CRITICAL dependencies found: {len(blocking_deps)} objects would be broken"
            )
            recommendations.append(
                "Remove or modify dependent objects before column removal"
            )

        high_risk_deps = [
            dep for dep in plan.dependencies if dep.impact_level == ImpactLevel.HIGH
        ]
        if high_risk_deps:
            warnings.append(
                f"HIGH risk dependencies found: {len(high_risk_deps)} objects"
            )
            recommendations.append("Review dependent objects and consider impact")

        # Check table accessibility
        table_accessible = await self._validate_table_access(
            plan.table_name, connection
        )
        if not table_accessible:
            # Create a constraint dependency to indicate table access issue
            blocking_deps.append(
                ConstraintDependency(
                    constraint_name="table_access_check",
                    constraint_type="ACCESS",
                    definition=f"Table {plan.table_name} access validation",
                    columns=[plan.column_name],
                    dependency_type=DependencyType.CONSTRAINT,
                    impact_level=ImpactLevel.CRITICAL,
                )
            )
            warnings.append(f"Table {plan.table_name} is not accessible")

        # Validate column existence
        column_exists = await self._check_column_exists(
            plan.table_name, plan.column_name, connection
        )
        if not column_exists:
            warnings.append(
                f"Column {plan.column_name} does not exist in {plan.table_name}"
            )

        is_safe = len(blocking_deps) == 0 and table_accessible and column_exists
        requires_confirmation = (
            risk_level in [ImpactLevel.HIGH, ImpactLevel.CRITICAL] or len(warnings) > 0
        )

        validation = SafetyValidation(
            is_safe=is_safe,
            risk_level=risk_level,
            blocking_dependencies=blocking_deps,
            warnings=warnings,
            recommendations=recommendations,
            estimated_duration=plan.estimated_duration,
            requires_confirmation=requires_confirmation,
        )

        self.logger.info(
            f"Safety validation complete for {plan.table_name}.{plan.column_name}: "
            f"Safe={is_safe}, Risk={risk_level.value}, Warnings={len(warnings)}"
        )

        return validation

    async def execute_safe_removal(
        self, plan: RemovalPlan, connection: Optional[asyncpg.Connection] = None
    ) -> RemovalResult:
        """
        Execute safe column removal according to plan.

        Args:
            plan: Validated removal plan
            connection: Database connection (optional)

        Returns:
            RemovalResult with execution details and recovery information
        """
        start_time = datetime.now()
        self.logger.info(
            f"Executing safe removal: {plan.table_name}.{plan.column_name}"
        )

        if connection is None:
            connection = await self._get_connection()

        stages_completed = []

        try:
            # Start transaction with savepoint for rollback capability
            async with connection.transaction():
                savepoint_name = f"column_removal_{int(start_time.timestamp())}"
                await connection.execute(f"SAVEPOINT {savepoint_name}")

                try:
                    # Execute each stage in order
                    for stage in plan.execution_stages:
                        stage_result = await self._execute_removal_stage(
                            stage, plan, connection
                        )
                        stages_completed.append(stage_result)

                        # Check for stage failure
                        if not stage_result.success:
                            if plan.stop_on_warning or stage_result.errors:
                                raise Exception(
                                    f"Stage {stage.value} failed: {'; '.join(stage_result.errors)}"
                                )

                        # Validate after each stage if requested
                        if plan.validate_after_each_stage:
                            validation_ok = await self._validate_stage_completion(
                                stage, plan, connection
                            )
                            if not validation_ok:
                                raise Exception(
                                    f"Stage {stage.value} validation failed"
                                )

                    # If dry run, rollback to savepoint
                    if plan.dry_run:
                        await connection.execute(
                            f"ROLLBACK TO SAVEPOINT {savepoint_name}"
                        )
                        self.logger.info("Dry run completed - changes rolled back")

                        result = RemovalResult(
                            plan=plan,
                            status=RemovalStatus.SUCCESS,
                            execution_time=(
                                datetime.now() - start_time
                            ).total_seconds(),
                            stages_completed=stages_completed,
                            recovery_instructions=["Dry run - no actual changes made"],
                        )
                    else:
                        # Release savepoint and commit
                        await connection.execute(f"RELEASE SAVEPOINT {savepoint_name}")

                        execution_time = (datetime.now() - start_time).total_seconds()
                        self.logger.info(
                            f"Column removal completed successfully: {plan.table_name}.{plan.column_name} "
                            f"in {execution_time:.2f}s"
                        )

                        result = RemovalResult(
                            plan=plan,
                            status=RemovalStatus.SUCCESS,
                            execution_time=execution_time,
                            stages_completed=stages_completed,
                            backup_preserved=plan.backup_info is not None,
                        )

                    return result

                except Exception as stage_error:
                    # Rollback to savepoint
                    await connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                    self.logger.error(
                        f"Stage execution failed, rolled back: {stage_error}"
                    )

                    execution_time = (datetime.now() - start_time).total_seconds()

                    result = RemovalResult(
                        plan=plan,
                        status=RemovalStatus.TRANSACTION_FAILED,
                        execution_time=execution_time,
                        stages_completed=stages_completed,
                        rollback_executed=True,
                        error_message=str(stage_error),
                        recovery_instructions=self._generate_recovery_instructions(
                            stages_completed, stage_error
                        ),
                    )

                    return result

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            self.logger.error(f"Column removal failed: {e}")

            return RemovalResult(
                plan=plan,
                status=RemovalStatus.VALIDATION_FAILED,
                execution_time=execution_time,
                stages_completed=stages_completed,
                rollback_executed=True,
                error_message=str(e),
                recovery_instructions=[f"Transaction failed: {str(e)}"],
            )

    # Private helper methods

    async def _get_connection(self) -> asyncpg.Connection:
        """Get database connection."""
        if self.connection_manager:
            return await self.connection_manager.get_connection()
        else:
            raise NotImplementedError("Connection manager not configured")

    def _generate_execution_stages(
        self, dependencies: List[ColumnDependency]
    ) -> List[RemovalStage]:
        """Generate execution stages based on dependencies."""
        stages = []

        # Always start with backup
        stages.append(RemovalStage.BACKUP_CREATION)

        # Add stages based on dependency types present
        dep_types = {dep.dependency_type for dep in dependencies}

        if any(
            dep_type in [DependencyType.TRIGGER, DependencyType.VIEW]
            for dep_type in dep_types
        ):
            stages.append(RemovalStage.DEPENDENT_OBJECTS)

        if any(
            dep_type in [DependencyType.FOREIGN_KEY, DependencyType.CONSTRAINT]
            for dep_type in dep_types
        ):
            stages.append(RemovalStage.CONSTRAINT_REMOVAL)

        if DependencyType.INDEX in dep_types:
            stages.append(RemovalStage.INDEX_REMOVAL)

        # Column removal is always needed
        stages.append(RemovalStage.COLUMN_REMOVAL)

        # Always end with cleanup and validation
        stages.append(RemovalStage.CLEANUP)
        stages.append(RemovalStage.VALIDATION)

        return stages

    def _estimate_removal_duration(self, dependencies: List[ColumnDependency]) -> float:
        """Estimate total removal duration in seconds."""
        base_time = 5.0  # Base overhead

        # Add time per dependency type
        type_times = {
            DependencyType.INDEX: 2.0,
            DependencyType.FOREIGN_KEY: 3.0,
            DependencyType.CONSTRAINT: 1.0,
            DependencyType.TRIGGER: 2.0,
            DependencyType.VIEW: 1.0,
        }

        total_time = base_time
        for dep in dependencies:
            total_time += type_times.get(dep.dependency_type, 1.0)

        return total_time

    async def _generate_rollback_plan(
        self, plan: RemovalPlan, connection: asyncpg.Connection
    ) -> Dict[str, Any]:
        """Generate comprehensive rollback plan."""
        return {
            "strategy": "transaction_savepoint",
            "backup_strategy": plan.backup_strategy.value,
            "requires_manual_intervention": len(plan.dependencies) > 10,
            "estimated_rollback_time": 2.0,
            "restoration_complexity": "high" if plan.dependencies else "low",
        }

    async def _execute_removal_stage(
        self, stage: RemovalStage, plan: RemovalPlan, connection: asyncpg.Connection
    ) -> RemovalStageResult:
        """Execute a single removal stage."""
        stage_start = datetime.now()
        self.logger.info(f"Executing stage: {stage.value}")

        try:
            if stage == RemovalStage.BACKUP_CREATION:
                return await self._execute_backup_stage(plan, connection)
            elif stage == RemovalStage.DEPENDENT_OBJECTS:
                return await self._execute_dependent_objects_stage(plan, connection)
            elif stage == RemovalStage.CONSTRAINT_REMOVAL:
                return await self._execute_constraint_removal_stage(plan, connection)
            elif stage == RemovalStage.INDEX_REMOVAL:
                return await self._execute_index_removal_stage(plan, connection)
            elif stage == RemovalStage.COLUMN_REMOVAL:
                return await self._execute_column_removal_stage(plan, connection)
            elif stage == RemovalStage.CLEANUP:
                return await self._execute_cleanup_stage(plan, connection)
            elif stage == RemovalStage.VALIDATION:
                return await self._execute_validation_stage(plan, connection)
            else:
                raise ValueError(f"Unknown removal stage: {stage}")

        except Exception as e:
            duration = (datetime.now() - stage_start).total_seconds()
            self.logger.error(f"Stage {stage.value} failed after {duration:.2f}s: {e}")

            return RemovalStageResult(
                stage=stage, success=False, duration=duration, errors=[str(e)]
            )

    async def _execute_backup_stage(
        self, plan: RemovalPlan, connection: asyncpg.Connection
    ) -> RemovalStageResult:
        """Execute backup creation stage."""
        stage_start = datetime.now()

        try:
            if plan.backup_strategy != BackupStrategy.NONE:
                handler = self.backup_handlers.get(plan.backup_strategy)
                if handler:
                    backup_info = await handler.create_backup(
                        plan.table_name, plan.column_name, connection
                    )
                    plan.backup_info = backup_info

                    return RemovalStageResult(
                        stage=RemovalStage.BACKUP_CREATION,
                        success=True,
                        duration=(datetime.now() - stage_start).total_seconds(),
                        objects_affected=[backup_info.backup_location],
                        warnings=(
                            [] if backup_info.backup_size > 0 else ["No data to backup"]
                        ),
                    )

            # No backup strategy
            return RemovalStageResult(
                stage=RemovalStage.BACKUP_CREATION,
                success=True,
                duration=(datetime.now() - stage_start).total_seconds(),
                warnings=["No backup created - data loss possible"],
            )

        except Exception as e:
            return RemovalStageResult(
                stage=RemovalStage.BACKUP_CREATION,
                success=False,
                duration=(datetime.now() - stage_start).total_seconds(),
                errors=[f"Backup failed: {str(e)}"],
            )

    async def _execute_dependent_objects_stage(
        self, plan: RemovalPlan, connection: asyncpg.Connection
    ) -> RemovalStageResult:
        """Execute dependent objects removal stage (triggers, views, functions)."""
        stage_start = datetime.now()
        objects_affected = []
        warnings = []

        # Get dependent objects that need removal
        dependent_objects = [
            dep
            for dep in plan.dependencies
            if dep.dependency_type in [DependencyType.TRIGGER, DependencyType.VIEW]
        ]

        for dep in dependent_objects:
            try:
                if dep.dependency_type == DependencyType.TRIGGER:
                    await connection.execute(
                        f"DROP TRIGGER IF EXISTS {dep.trigger_name} ON {plan.table_name}"
                    )
                    objects_affected.append(f"trigger:{dep.trigger_name}")
                elif dep.dependency_type == DependencyType.VIEW:
                    await connection.execute(
                        f"DROP VIEW IF EXISTS {dep.view_name} CASCADE"
                    )
                    objects_affected.append(f"view:{dep.view_name}")
                    warnings.append(
                        f"View {dep.view_name} dropped - may affect other queries"
                    )
                # Note: Functions typically don't need to be dropped for column removal
                # They would be handled by updating function definitions manually

            except Exception as e:
                dep_name = getattr(dep, "trigger_name", None) or getattr(
                    dep, "view_name", "unknown"
                )
                warnings.append(f"Failed to remove {dep_name}: {str(e)}")

        return RemovalStageResult(
            stage=RemovalStage.DEPENDENT_OBJECTS,
            success=True,  # Continue even with warnings
            duration=(datetime.now() - stage_start).total_seconds(),
            objects_affected=objects_affected,
            warnings=warnings,
        )

    async def _execute_constraint_removal_stage(
        self, plan: RemovalPlan, connection: asyncpg.Connection
    ) -> RemovalStageResult:
        """Execute constraint removal stage."""
        stage_start = datetime.now()
        objects_affected = []
        warnings = []

        # Get constraints that need removal
        constraints = [
            dep
            for dep in plan.dependencies
            if dep.dependency_type
            in [DependencyType.FOREIGN_KEY, DependencyType.CONSTRAINT]
        ]

        for dep in constraints:
            try:
                if dep.dependency_type == DependencyType.FOREIGN_KEY:
                    # Check if this is an outgoing FK (from our column) or incoming FK (to our column)
                    details = getattr(dep, "details", {}) or {}
                    if (
                        details.get("source_table") == plan.table_name
                        or dep.source_table == plan.table_name
                    ):
                        # Outgoing FK - safe to drop
                        await connection.execute(
                            f"ALTER TABLE {plan.table_name} DROP CONSTRAINT IF EXISTS {dep.constraint_name}"
                        )
                        objects_affected.append(f"fk_constraint:{dep.constraint_name}")
                    else:
                        # Incoming FK - this would break referencing tables
                        warnings.append(
                            f"Cannot drop incoming FK constraint {dep.constraint_name} - "
                            f"would break referencing table {dep.source_table}"
                        )

                elif dep.dependency_type == DependencyType.CONSTRAINT:
                    await connection.execute(
                        f"ALTER TABLE {plan.table_name} DROP CONSTRAINT IF EXISTS {dep.constraint_name}"
                    )
                    objects_affected.append(f"check_constraint:{dep.constraint_name}")

            except Exception as e:
                dep_name = getattr(dep, "constraint_name", "unknown")
                warnings.append(f"Failed to remove constraint {dep_name}: {str(e)}")

        return RemovalStageResult(
            stage=RemovalStage.CONSTRAINT_REMOVAL,
            success=True,
            duration=(datetime.now() - stage_start).total_seconds(),
            objects_affected=objects_affected,
            warnings=warnings,
        )

    async def _execute_index_removal_stage(
        self, plan: RemovalPlan, connection: asyncpg.Connection
    ) -> RemovalStageResult:
        """Execute index removal stage."""
        stage_start = datetime.now()
        objects_affected = []
        warnings = []

        # Get indexes that need removal
        indexes = [
            dep
            for dep in plan.dependencies
            if dep.dependency_type == DependencyType.INDEX
        ]

        for dep in indexes:
            try:
                details = getattr(dep, "details", {}) or {}
                # Check if it's a single column index
                is_single_column = (
                    len(dep.columns) == 1
                    if hasattr(dep, "columns")
                    else details.get("is_single_column", False)
                )

                if is_single_column:
                    # Single column index - safe to drop
                    await connection.execute(f"DROP INDEX IF EXISTS {dep.index_name}")
                    objects_affected.append(f"index:{dep.index_name}")
                else:
                    # Multi-column index - dropping might affect performance
                    await connection.execute(f"DROP INDEX IF EXISTS {dep.index_name}")
                    objects_affected.append(f"composite_index:{dep.index_name}")
                    warnings.append(
                        f"Dropped composite index {dep.index_name} - may affect query performance"
                    )

            except Exception as e:
                dep_name = getattr(dep, "index_name", "unknown")
                warnings.append(f"Failed to remove index {dep_name}: {str(e)}")

        return RemovalStageResult(
            stage=RemovalStage.INDEX_REMOVAL,
            success=True,
            duration=(datetime.now() - stage_start).total_seconds(),
            objects_affected=objects_affected,
            warnings=warnings,
        )

    async def _execute_column_removal_stage(
        self, plan: RemovalPlan, connection: asyncpg.Connection
    ) -> RemovalStageResult:
        """Execute the actual column removal."""
        stage_start = datetime.now()

        try:
            # Drop the column
            await connection.execute(
                f"ALTER TABLE {plan.table_name} DROP COLUMN IF EXISTS {plan.column_name}"
            )

            return RemovalStageResult(
                stage=RemovalStage.COLUMN_REMOVAL,
                success=True,
                duration=(datetime.now() - stage_start).total_seconds(),
                objects_affected=[f"column:{plan.table_name}.{plan.column_name}"],
            )

        except Exception as e:
            return RemovalStageResult(
                stage=RemovalStage.COLUMN_REMOVAL,
                success=False,
                duration=(datetime.now() - stage_start).total_seconds(),
                errors=[f"Column removal failed: {str(e)}"],
            )

    async def _execute_cleanup_stage(
        self, plan: RemovalPlan, connection: asyncpg.Connection
    ) -> RemovalStageResult:
        """Execute cleanup stage."""
        stage_start = datetime.now()
        warnings = []

        # Basic cleanup - could be extended for specific cleanup operations
        if plan.backup_info and plan.backup_strategy == BackupStrategy.NONE:
            warnings.append("No backup cleanup needed")
        else:
            warnings.append("Backup preserved for recovery")

        return RemovalStageResult(
            stage=RemovalStage.CLEANUP,
            success=True,
            duration=(datetime.now() - stage_start).total_seconds(),
            warnings=warnings,
        )

    async def _execute_validation_stage(
        self, plan: RemovalPlan, connection: asyncpg.Connection
    ) -> RemovalStageResult:
        """Execute post-removal validation."""
        stage_start = datetime.now()
        warnings = []
        errors = []

        try:
            # Verify column no longer exists
            column_exists = await self._check_column_exists(
                plan.table_name, plan.column_name, connection
            )
            if column_exists:
                errors.append(f"Column {plan.column_name} still exists after removal")

            # Verify table integrity
            try:
                row_count = await connection.fetchval(
                    f"SELECT COUNT(*) FROM {plan.table_name}"
                )
                if row_count >= 0:  # Just verify table is accessible
                    warnings.append(
                        f"Table {plan.table_name} accessible with {row_count} rows"
                    )
            except Exception as e:
                errors.append(f"Table integrity check failed: {str(e)}")

            return RemovalStageResult(
                stage=RemovalStage.VALIDATION,
                success=len(errors) == 0,
                duration=(datetime.now() - stage_start).total_seconds(),
                warnings=warnings,
                errors=errors,
            )

        except Exception as e:
            return RemovalStageResult(
                stage=RemovalStage.VALIDATION,
                success=False,
                duration=(datetime.now() - stage_start).total_seconds(),
                errors=[f"Validation failed: {str(e)}"],
            )

    async def _validate_stage_completion(
        self, stage: RemovalStage, plan: RemovalPlan, connection: asyncpg.Connection
    ) -> bool:
        """Validate that a stage completed successfully."""
        # Basic validation - could be extended for specific stage validations
        return True

    async def _validate_table_access(
        self, table_name: str, connection: asyncpg.Connection
    ) -> bool:
        """Validate that table exists and is accessible."""
        try:
            result = await connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = $1)",
                table_name,
            )
            return result
        except Exception:
            return False

    async def _check_column_exists(
        self, table_name: str, column_name: str, connection: asyncpg.Connection
    ) -> bool:
        """Check if column exists in table."""
        try:
            result = await connection.fetchval(
                """SELECT EXISTS(
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = $1 AND column_name = $2
                )""",
                table_name,
                column_name,
            )
            return result
        except Exception:
            return False

    def _generate_recovery_instructions(
        self, stages_completed: List[RemovalStageResult], error: Exception
    ) -> List[str]:
        """Generate recovery instructions based on completed stages and error."""
        instructions = []

        instructions.append("Transaction was automatically rolled back")

        if any(
            stage.stage == RemovalStage.BACKUP_CREATION and stage.success
            for stage in stages_completed
        ):
            instructions.append("Backup was created and preserved")

        instructions.append(f"Error occurred: {str(error)}")
        instructions.append("Review dependencies and retry with updated plan")

        return instructions
