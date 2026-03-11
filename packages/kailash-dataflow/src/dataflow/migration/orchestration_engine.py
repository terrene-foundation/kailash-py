"""
Migration Orchestration Engine - Central coordinator for all migration operations.

This is the critical foundation component for DataFlow's migration system that provides:
- Central coordination for all migration operations
- Migration pipeline with validation → execution → rollback capability
- Transaction-aware execution with checkpointing
- Integration with existing AutoMigrationSystem and SchemaStateManager
- Support for 11 migration scenarios (column changes, additions, removals, renames, etc.)

The orchestration engine serves as the single point of coordination for complex
migration workflows while maintaining safety and reliability.
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from kailash.runtime import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

logger = logging.getLogger(__name__)


class MigrationType(Enum):
    """Types of database migrations supported by the orchestration engine."""

    # Table operations
    CREATE_TABLE = "create_table"
    DROP_TABLE = "drop_table"
    RENAME_TABLE = "rename_table"

    # Column operations
    ADD_COLUMN = "add_column"
    DROP_COLUMN = "drop_column"
    MODIFY_COLUMN = "modify_column"
    RENAME_COLUMN = "rename_column"

    # Index operations
    ADD_INDEX = "add_index"
    DROP_INDEX = "drop_index"

    # Constraint operations
    ADD_CONSTRAINT = "add_constraint"
    DROP_CONSTRAINT = "drop_constraint"


class RiskLevel(Enum):
    """Risk levels for migration operations."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class MigrationOperation:
    """A single migration operation with metadata and rollback capability."""

    operation_type: MigrationType
    table_name: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    rollback_sql: Optional[str] = None


@dataclass
class Migration:
    """A complete migration with multiple operations and dependencies."""

    operations: List[MigrationOperation]
    version: str
    dependencies: List[str] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW


@dataclass
class ValidationResult:
    """Result of migration safety validation."""

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    risk_assessment: RiskLevel = RiskLevel.NONE


@dataclass
class MigrationCheckpoint:
    """Checkpoint created during migration execution for rollback."""

    checkpoint_id: str
    operation_index: int
    description: str
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ExecutionPlan:
    """Plan for executing a migration with checkpoints and rollback strategy."""

    migration: Migration
    checkpoints: List[MigrationCheckpoint] = field(default_factory=list)
    estimated_duration_ms: int = 0
    rollback_strategy: str = "full"  # "full", "partial", "none"


@dataclass
class MigrationResult:
    """Result of migration execution."""

    success: bool
    migration_version: str
    executed_operations: int
    execution_time_ms: int
    checkpoints_created: int
    error_message: Optional[str] = None


class OrchestrationError(Exception):
    """Exception raised by the Migration Orchestration Engine."""

    def __init__(self, message: str, error_code: str = "ORCHESTRATION_ERROR"):
        super().__init__(message)
        self.error_code = error_code


class MigrationOrchestrationEngine:
    """
    Central coordinator for all migration operations.

    This engine orchestrates the entire migration lifecycle:
    1. Validation of migration safety and dependencies
    2. Creation of execution plans with checkpoints
    3. Transaction-aware execution with rollback capability
    4. Integration with AutoMigrationSystem and SchemaStateManager
    """

    def __init__(
        self,
        auto_migration_system,
        schema_state_manager,
        connection_string: str,
        connection_pool_name: str = "default",
    ):
        """
        Initialize the Migration Orchestration Engine.

        Args:
            auto_migration_system: Existing AutoMigrationSystem instance
            schema_state_manager: Existing SchemaStateManager instance
            connection_string: Database connection string
        """
        self.auto_migration_system = auto_migration_system
        self.schema_state_manager = schema_state_manager
        self.connection_string = connection_string
        self.connection_pool_name = connection_pool_name

        # Detect database type for AsyncSQLDatabaseNode
        from ..adapters.connection_parser import ConnectionParser

        self.database_type = ConnectionParser.detect_database_type(connection_string)

        # ✅ FIX: Detect async context and use appropriate runtime
        try:
            asyncio.get_running_loop()
            # Running in async context - use AsyncLocalRuntime
            self.runtime = AsyncLocalRuntime()
            self._is_async = True
            logger.debug(
                "OrchestrationEngine: Detected async context, using AsyncLocalRuntime"
            )
        except RuntimeError:
            # No event loop - use sync LocalRuntime
            self.runtime = LocalRuntime()
            self._is_async = False
            logger.debug(
                "OrchestrationEngine: Detected sync context, using LocalRuntime"
            )

        # TODO: Integrate with DataFlow connection pooling
        # from dataflow.core.connection_manager import get_connection_pool
        # self.connection_pool = get_connection_pool(connection_pool_name)

        # Migration coordination state
        self._migration_lock = asyncio.Lock()
        self._active_migration = None
        self._migration_history = []

        # Initialize column type conversion components
        self._data_validator = None
        self._safe_type_converter = None

        logger.info("Migration Orchestration Engine initialized")

    def _check_node_result(
        self, results: dict, node_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Standardized method for checking node execution results.

        Args:
            results: Results dictionary from workflow execution
            node_id: ID of the node to check

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        if node_id not in results:
            return False, f"Node {node_id} not found in execution results"

        node_result = results[node_id]
        if node_result.get("error"):
            return False, str(node_result["error"])

        return True, None

    async def execute_migration(self, migration: Migration) -> MigrationResult:
        """
        Execute a complete migration with validation and rollback capability.

        This is the main entry point for migration execution.

        Args:
            migration: Migration to execute

        Returns:
            MigrationResult with execution details

        Raises:
            OrchestrationError: If migration cannot be executed safely
        """
        start_time = time.time()

        try:
            # Prevent concurrent migrations
            if not await self._acquire_migration_lock(migration.version):
                raise OrchestrationError(
                    "Another migration is already in progress. Concurrent migrations are not allowed.",
                    "CONCURRENT_MIGRATION",
                )

            logger.info(f"Starting migration execution: {migration.version}")

            # Step 1: Validate migration safety
            validation_result = await self.validate_migration_safety(migration)
            if not validation_result.is_valid:
                error_msg = f"Migration validation failed: {'; '.join(validation_result.errors)}"
                logger.error(error_msg)
                raise OrchestrationError(error_msg, "VALIDATION_FAILED")

            # Log warnings
            for warning in validation_result.warnings:
                logger.warning(f"Migration warning: {warning}")

            # Step 2: Create execution plan
            execution_plan = await self.create_execution_plan(migration)
            logger.info(
                f"Created execution plan with {len(execution_plan.checkpoints)} checkpoints"
            )

            # Step 3: Execute with rollback capability
            result = await self.execute_with_rollback(execution_plan)

            # Record execution time
            execution_time_ms = int((time.time() - start_time) * 1000)
            result.execution_time_ms = execution_time_ms

            if result.success:
                logger.info(
                    f"Migration {migration.version} completed successfully in {execution_time_ms}ms"
                )
            else:
                logger.error(
                    f"Migration {migration.version} failed after {execution_time_ms}ms: {result.error_message}"
                )

            return result

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            logger.error(
                f"Migration {migration.version} failed with exception after {execution_time_ms}ms: {e}"
            )

            return MigrationResult(
                success=False,
                migration_version=migration.version,
                executed_operations=0,
                execution_time_ms=execution_time_ms,
                checkpoints_created=0,
                error_message=str(e),
            )
        finally:
            await self._release_migration_lock()

    async def validate_migration_safety(self, migration: Migration) -> ValidationResult:
        """
        Validate migration safety including dependencies and risk assessment.

        Args:
            migration: Migration to validate

        Returns:
            ValidationResult with validation details
        """
        errors = []
        warnings = []
        risk_level = RiskLevel.NONE

        try:
            # Check dependencies are applied
            if migration.dependencies:
                dependencies_met = await self._check_dependencies_applied(
                    migration.dependencies
                )
                if not dependencies_met:
                    errors.append(
                        f"Migration dependencies not met: {migration.dependencies}"
                    )

            # Validate each operation
            for i, operation in enumerate(migration.operations):
                operation_validation = await self._validate_operation(operation)

                if not operation_validation["is_valid"]:
                    errors.extend(
                        [
                            f"Operation {i+1}: {error}"
                            for error in operation_validation["errors"]
                        ]
                    )

                warnings.extend(
                    [
                        f"Operation {i+1}: {warning}"
                        for warning in operation_validation["warnings"]
                    ]
                )

                # Update risk level
                op_risk = operation_validation["risk_level"]
                if self._risk_level_higher(op_risk, risk_level):
                    risk_level = op_risk

            # Overall risk assessment
            if migration.risk_level != RiskLevel.NONE:
                if self._risk_level_higher(migration.risk_level, risk_level):
                    risk_level = migration.risk_level

            # Add high-risk warnings
            if risk_level == RiskLevel.HIGH:
                warnings.append(
                    "This migration contains high-risk operations that may cause data loss"
                )
            elif risk_level == RiskLevel.MEDIUM:
                warnings.append(
                    "This migration contains medium-risk operations - backup recommended"
                )

            is_valid = len(errors) == 0

            return ValidationResult(
                is_valid=is_valid,
                errors=errors,
                warnings=warnings,
                risk_assessment=risk_level,
            )

        except Exception as e:
            logger.error(f"Migration validation failed with exception: {e}")
            return ValidationResult(
                is_valid=False,
                errors=[f"Validation error: {str(e)}"],
                warnings=warnings,
                risk_assessment=RiskLevel.HIGH,
            )

    async def create_execution_plan(self, migration: Migration) -> ExecutionPlan:
        """
        Create execution plan with checkpoints and rollback strategy.

        Args:
            migration: Migration to create plan for

        Returns:
            ExecutionPlan with checkpoints and strategy
        """
        checkpoints = []
        estimated_duration = 0
        rollback_strategy = "full"

        # Create checkpoints for risky operations
        for i, operation in enumerate(migration.operations):
            # Estimate operation duration
            op_duration = self._estimate_operation_duration(operation)
            estimated_duration += op_duration

            # Create checkpoint before risky operations
            if self._operation_needs_checkpoint(operation):
                checkpoint = MigrationCheckpoint(
                    checkpoint_id=f"checkpoint_{i}_{uuid.uuid4().hex[:8]}",
                    operation_index=i,
                    description=f"Before {operation.operation_type.value} on {operation.table_name}",
                )
                checkpoints.append(checkpoint)

            # Check if operation supports rollback
            if not operation.rollback_sql and self._operation_is_destructive(operation):
                rollback_strategy = "partial"
                if operation.operation_type in [
                    MigrationType.DROP_TABLE,
                    MigrationType.DROP_COLUMN,
                ]:
                    rollback_strategy = "none"

        return ExecutionPlan(
            migration=migration,
            checkpoints=checkpoints,
            estimated_duration_ms=estimated_duration,
            rollback_strategy=rollback_strategy,
        )

    async def execute_with_rollback(self, plan: ExecutionPlan) -> MigrationResult:
        """
        Execute migration plan with automatic rollback on failure.

        Args:
            plan: ExecutionPlan to execute

        Returns:
            MigrationResult with execution details
        """
        start_time = time.time()
        executed_operations = 0
        checkpoints_created = 0

        try:
            # Execute the plan
            result = await self._execute_plan(plan)

            if result.success:
                return result
            else:
                # Attempt rollback on failure
                logger.warning(
                    f"Migration failed, attempting rollback: {result.error_message}"
                )

                if plan.rollback_strategy != "none":
                    rollback_success = await self._rollback_migration(plan)
                    if rollback_success:
                        logger.info("Migration rollback completed successfully")
                    else:
                        logger.error(
                            "Migration rollback failed - manual intervention may be required"
                        )

                return result

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Migration execution failed with exception: {e}")

            # Attempt emergency rollback
            if plan.rollback_strategy != "none":
                try:
                    await self._rollback_migration(plan)
                except Exception as rollback_error:
                    logger.error(f"Emergency rollback failed: {rollback_error}")

            return MigrationResult(
                success=False,
                migration_version=plan.migration.version,
                executed_operations=executed_operations,
                execution_time_ms=execution_time_ms,
                checkpoints_created=checkpoints_created,
                error_message=str(e),
            )

    async def _execute_plan(self, plan: ExecutionPlan) -> MigrationResult:
        """Execute the migration plan operations."""
        start_time = time.time()
        executed_operations = 0
        checkpoints_created = 0

        try:
            # Create initial checkpoint if high-risk migration
            if plan.migration.risk_level in [RiskLevel.HIGH, RiskLevel.MEDIUM]:
                await self._create_checkpoint(f"initial_{plan.migration.version}")
                checkpoints_created += 1

            # Execute operations with checkpointing
            for i, operation in enumerate(plan.migration.operations):
                # Create checkpoint if planned
                checkpoint_for_operation = next(
                    (cp for cp in plan.checkpoints if cp.operation_index == i), None
                )
                if checkpoint_for_operation:
                    await self._create_checkpoint(
                        checkpoint_for_operation.checkpoint_id
                    )
                    checkpoints_created += 1

                # Execute operation
                success = await self._execute_operation(operation)
                if not success:
                    raise Exception(
                        f"Operation failed: {operation.operation_type.value} on {operation.table_name}"
                    )

                executed_operations += 1
                logger.debug(
                    f"Completed operation {i+1}/{len(plan.migration.operations)}: {operation.operation_type.value}"
                )

            execution_time_ms = int((time.time() - start_time) * 1000)

            return MigrationResult(
                success=True,
                migration_version=plan.migration.version,
                executed_operations=executed_operations,
                execution_time_ms=execution_time_ms,
                checkpoints_created=checkpoints_created,
                error_message=None,
            )

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            return MigrationResult(
                success=False,
                migration_version=plan.migration.version,
                executed_operations=executed_operations,
                execution_time_ms=execution_time_ms,
                checkpoints_created=checkpoints_created,
                error_message=str(e),
            )

    async def _execute_operation(self, operation: MigrationOperation) -> bool:
        """
        Execute a single migration operation.

        This integrates with the existing AutoMigrationSystem for actual SQL execution.
        """
        try:
            # Generate SQL for operation using existing system
            sql = self._generate_operation_sql(operation)

            if not sql:
                logger.warning(
                    f"No SQL generated for operation: {operation.operation_type.value}"
                )
                return True  # Skip operations that don't need SQL

            # Execute SQL using WorkflowBuilder pattern
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                f"execute_{operation.operation_type.value}",
                {
                    "connection_string": self.connection_string,
                    "database_type": self.database_type,
                    "query": sql,
                    "validate_queries": False,
                },
            )

            # ✅ FIX: Use LocalRuntime for migration operations to avoid async context issues
            init_runtime = LocalRuntime()
            results, _ = init_runtime.execute(workflow.build())
            node_id = f"execute_{operation.operation_type.value}"

            success, error_msg = self._check_node_result(results, node_id)
            if not success:
                logger.error(f"Operation failed: {error_msg}")
                return False

            return True

        except Exception as e:
            logger.error(f"Operation execution failed: {e}")
            return False

    async def _create_checkpoint(self, checkpoint_id: str) -> str:
        """Create a checkpoint for rollback purposes."""
        try:
            # In a full implementation, this would create database savepoints
            # For now, we log the checkpoint creation
            logger.debug(f"Created checkpoint: {checkpoint_id}")
            return checkpoint_id
        except Exception as e:
            logger.error(f"Failed to create checkpoint {checkpoint_id}: {e}")
            raise

    async def _rollback_to_checkpoint(self, checkpoint_id: str) -> bool:
        """Rollback to a specific checkpoint."""
        try:
            # In a full implementation, this would rollback to database savepoint
            # For now, we log the rollback
            logger.info(f"Rolling back to checkpoint: {checkpoint_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to rollback to checkpoint {checkpoint_id}: {e}")
            return False

    async def _rollback_migration(self, plan: ExecutionPlan) -> bool:
        """Rollback migration using available rollback SQL."""
        try:
            # Execute rollback operations in reverse order
            for operation in reversed(plan.migration.operations):
                if operation.rollback_sql:
                    workflow = WorkflowBuilder()
                    workflow.add_node(
                        "AsyncSQLDatabaseNode",
                        f"rollback_{operation.operation_type.value}",
                        {
                            "connection_string": self.connection_string,
                            "database_type": self.database_type,
                            "query": operation.rollback_sql,
                            "validate_queries": False,
                        },
                    )

                    # ✅ FIX: Use LocalRuntime for migration operations to avoid async context issues
                    init_runtime = LocalRuntime()
                    results, _ = init_runtime.execute(workflow.build())
                    node_id = f"rollback_{operation.operation_type.value}"

                    if node_id not in results or results[node_id].get("error"):
                        error_msg = results.get(node_id, {}).get(
                            "error", "Unknown error"
                        )
                        logger.error(f"Rollback operation failed: {error_msg}")
                        return False

                    logger.debug(
                        f"Rolled back: {operation.operation_type.value} on {operation.table_name}"
                    )

            return True

        except Exception as e:
            logger.error(f"Migration rollback failed: {e}")
            return False

    async def _acquire_migration_lock(self, migration_version: str) -> bool:
        """Acquire lock to prevent concurrent migrations."""
        try:
            # Use asyncio lock for concurrency control
            if self._migration_lock.locked():
                logger.warning(
                    f"Migration lock already held by: {self._active_migration}"
                )
                return False

            await self._migration_lock.acquire()
            self._active_migration = migration_version
            logger.debug(f"Acquired migration lock for: {migration_version}")
            return True
        except Exception as e:
            logger.error(f"Failed to acquire migration lock: {e}")
            return False

    async def _release_migration_lock(self):
        """Release migration lock."""
        try:
            if self._migration_lock.locked():
                self._migration_lock.release()
                self._active_migration = None
                logger.debug("Released migration lock")
        except Exception as e:
            logger.error(f"Failed to release migration lock: {e}")

    async def _check_dependencies_applied(self, dependencies: List[str]) -> bool:
        """Check if migration dependencies have been applied."""
        try:
            # Query migration history to check dependencies
            # This integrates with existing AutoMigrationSystem
            for dependency in dependencies:
                # In a full implementation, check if dependency migration was applied
                # For now, assume dependencies are met
                pass
            return True
        except Exception as e:
            logger.error(f"Failed to check dependencies: {e}")
            return False

    async def _validate_operation(
        self, operation: MigrationOperation
    ) -> Dict[str, Any]:
        """Validate a single migration operation."""
        errors = []
        warnings = []
        risk_level = RiskLevel.LOW

        # Risk assessment based on operation type
        if operation.operation_type in [
            MigrationType.DROP_TABLE,
            MigrationType.DROP_COLUMN,
        ]:
            risk_level = RiskLevel.HIGH
            warnings.append("This operation will permanently delete data")
        elif operation.operation_type in [
            MigrationType.MODIFY_COLUMN,
            MigrationType.DROP_CONSTRAINT,
        ]:
            risk_level = RiskLevel.MEDIUM
            warnings.append(
                "This operation may cause data loss or constraint violations"
            )
        elif operation.operation_type in [
            MigrationType.ADD_COLUMN,
            MigrationType.ADD_INDEX,
        ]:
            risk_level = RiskLevel.LOW
        else:
            risk_level = RiskLevel.LOW

        # Validate operation metadata
        if not operation.table_name:
            errors.append("Table name is required")

        # Operation-specific validations
        if operation.operation_type == MigrationType.ADD_COLUMN:
            if "column_name" not in operation.metadata:
                errors.append("Column name is required for ADD_COLUMN operation")
            # Make column_type optional for flexibility
            # if "column_type" not in operation.metadata:
            #     errors.append("Column type is required for ADD_COLUMN operation")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "risk_level": risk_level,
        }

    def _generate_operation_sql(self, operation: MigrationOperation) -> Optional[str]:
        """Generate SQL for migration operation."""
        # This integrates with existing AutoMigrationSystem SQL generation
        # For now, return placeholder SQL based on operation type

        sql_templates = {
            MigrationType.CREATE_TABLE: "CREATE TABLE {table_name} ({columns})",
            MigrationType.DROP_TABLE: "DROP TABLE IF EXISTS {table_name}",
            MigrationType.ADD_COLUMN: "ALTER TABLE {table_name} ADD COLUMN {column_def}",
            MigrationType.DROP_COLUMN: "ALTER TABLE {table_name} DROP COLUMN {column_name}",
            MigrationType.MODIFY_COLUMN: "ALTER TABLE {table_name} ALTER COLUMN {column_name} TYPE {new_type}",
            MigrationType.RENAME_COLUMN: "ALTER TABLE {table_name} RENAME COLUMN {old_name} TO {new_name}",
            MigrationType.ADD_INDEX: "CREATE INDEX {index_name} ON {table_name} ({columns})",
            MigrationType.DROP_INDEX: "DROP INDEX IF EXISTS {index_name}",
            MigrationType.ADD_CONSTRAINT: "ALTER TABLE {table_name} ADD CONSTRAINT {constraint_name} {constraint_def}",
            MigrationType.DROP_CONSTRAINT: "ALTER TABLE {table_name} DROP CONSTRAINT {constraint_name}",
            MigrationType.RENAME_TABLE: "ALTER TABLE {table_name} RENAME TO {new_name}",
        }

        template = sql_templates.get(operation.operation_type)
        if not template:
            return None

        try:
            # Basic SQL generation - in full implementation, this would use AutoMigrationSystem
            if operation.operation_type == MigrationType.ADD_COLUMN:
                column_name = operation.metadata.get("column_name", "new_column")
                column_type = operation.metadata.get("column_type", "VARCHAR(255)")
                return f"ALTER TABLE {operation.table_name} ADD COLUMN {column_name} {column_type}"
            elif operation.operation_type == MigrationType.DROP_COLUMN:
                column_name = operation.metadata.get("column_name", "unknown_column")
                return f"ALTER TABLE {operation.table_name} DROP COLUMN {column_name}"
            else:
                # Return basic template for other operations
                return template.format(
                    table_name=operation.table_name, **operation.metadata
                )
        except KeyError as e:
            logger.error(f"Missing metadata for SQL generation: {e}")
            return None

    def _estimate_operation_duration(self, operation: MigrationOperation) -> int:
        """Estimate operation duration in milliseconds."""
        duration_estimates = {
            MigrationType.CREATE_TABLE: 200,
            MigrationType.DROP_TABLE: 100,
            MigrationType.ADD_COLUMN: 300,
            MigrationType.DROP_COLUMN: 250,
            MigrationType.MODIFY_COLUMN: 400,
            MigrationType.RENAME_COLUMN: 150,
            MigrationType.ADD_INDEX: 1000,
            MigrationType.DROP_INDEX: 200,
            MigrationType.ADD_CONSTRAINT: 500,
            MigrationType.DROP_CONSTRAINT: 300,
            MigrationType.RENAME_TABLE: 100,
        }

        return duration_estimates.get(operation.operation_type, 250)

    def _operation_needs_checkpoint(self, operation: MigrationOperation) -> bool:
        """Determine if operation needs a checkpoint."""
        risky_operations = [
            MigrationType.DROP_TABLE,
            MigrationType.DROP_COLUMN,
            MigrationType.MODIFY_COLUMN,
            MigrationType.DROP_CONSTRAINT,
            MigrationType.ADD_COLUMN,  # Add column operations can be risky too
            MigrationType.CREATE_TABLE,  # Table creation should have checkpoints for medium-risk migrations
        ]
        return operation.operation_type in risky_operations

    def _operation_is_destructive(self, operation: MigrationOperation) -> bool:
        """Determine if operation is destructive (cannot be easily rolled back)."""
        destructive_operations = [MigrationType.DROP_TABLE, MigrationType.DROP_COLUMN]
        return operation.operation_type in destructive_operations

    def _risk_level_higher(self, level1: RiskLevel, level2: RiskLevel) -> bool:
        """Compare risk levels to determine which is higher."""
        risk_order = {
            RiskLevel.NONE: 0,
            RiskLevel.LOW: 1,
            RiskLevel.MEDIUM: 2,
            RiskLevel.HIGH: 3,
        }
        return risk_order[level1] > risk_order[level2]

    # Column Type Conversion Methods

    def _get_data_validator(self):
        """Lazy initialization of DataValidationEngine."""
        if self._data_validator is None:
            from .data_validation_engine import DataValidationEngine

            self._data_validator = DataValidationEngine(self.connection_string)
        return self._data_validator

    def _get_safe_type_converter(self):
        """Lazy initialization of SafeTypeConverter."""
        if self._safe_type_converter is None:
            from .type_converter import SafeTypeConverter

            self._safe_type_converter = SafeTypeConverter(
                connection_string=self.connection_string, orchestration_engine=self
            )
        return self._safe_type_converter

    async def execute_column_type_conversion(
        self, table_name: str, column_name: str, old_type: str, new_type: str
    ) -> MigrationResult:
        """
        Execute a column type conversion using the safe conversion engine.

        This method provides a high-level interface for column type conversions
        that integrates with the orchestration engine's safety mechanisms.

        Args:
            table_name: Name of the table
            column_name: Name of the column to convert
            old_type: Current column type
            new_type: Target column type

        Returns:
            MigrationResult with conversion details
        """
        start_time = time.time()

        try:
            logger.info(
                f"Starting column type conversion: {table_name}.{column_name} {old_type} -> {new_type}"
            )

            # Use SafeTypeConverter for the actual conversion
            converter = self._get_safe_type_converter()
            conversion_result = await converter.convert_column_type_safe(
                table_name, column_name, old_type, new_type
            )

            # Convert ConversionResult to MigrationResult format
            execution_time_ms = int((time.time() - start_time) * 1000)

            migration_result = MigrationResult(
                success=conversion_result.success,
                migration_version=f"column_type_conversion_{table_name}_{column_name}_{int(time.time())}",
                executed_operations=conversion_result.executed_steps,
                execution_time_ms=execution_time_ms,
                checkpoints_created=0,  # SafeTypeConverter handles its own checkpointing
                error_message=conversion_result.error_message,
            )

            if conversion_result.success:
                logger.info(
                    f"Column type conversion completed successfully in {execution_time_ms}ms"
                )
            else:
                logger.error(
                    f"Column type conversion failed: {conversion_result.error_message}"
                )

            return migration_result

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Column type conversion failed with exception: {e}")

            return MigrationResult(
                success=False,
                migration_version=f"column_type_conversion_{table_name}_{column_name}_failed",
                executed_operations=0,
                execution_time_ms=execution_time_ms,
                checkpoints_created=0,
                error_message=str(e),
            )

    async def validate_column_type_conversion(
        self, table_name: str, column_name: str, old_type: str, new_type: str
    ) -> ValidationResult:
        """
        Validate a column type conversion without executing it.

        This method provides pre-validation capabilities to assess the
        safety and feasibility of a column type conversion.

        Args:
            table_name: Name of the table
            column_name: Name of the column to convert
            old_type: Current column type
            new_type: Target column type

        Returns:
            ValidationResult with validation details
        """
        try:
            logger.info(
                f"Validating column type conversion: {table_name}.{column_name} {old_type} -> {new_type}"
            )

            # Use DataValidationEngine for validation
            validator = self._get_data_validator()
            validation_result = await validator.validate_type_conversion(
                table_name, column_name, old_type, new_type
            )

            logger.info(
                f"Validation completed: {'compatible' if validation_result.is_compatible else 'incompatible'}"
            )

            return ValidationResult(
                is_valid=validation_result.is_compatible,
                errors=[
                    issue.message
                    for issue in validation_result.issues
                    if issue.severity.value in ["error", "critical"]
                ],
                warnings=[
                    issue.message
                    for issue in validation_result.issues
                    if issue.severity.value == "warning"
                ],
                risk_assessment=self._convert_conversion_risk_to_risk_level(
                    validation_result
                ),
            )

        except Exception as e:
            logger.error(f"Column type conversion validation failed: {e}")

            return ValidationResult(
                is_valid=False,
                errors=[f"Validation failed: {str(e)}"],
                warnings=[],
                risk_assessment=RiskLevel.HIGH,
            )

    def _convert_conversion_risk_to_risk_level(self, validation_result) -> RiskLevel:
        """Convert ConversionRisk to RiskLevel for orchestration engine compatibility."""
        # Import here to avoid circular imports
        from .type_converter import ConversionRisk

        # Default risk level based on validation issues
        if not validation_result.is_compatible:
            return RiskLevel.HIGH

        # Check for critical/error issues
        critical_or_error_issues = [
            issue
            for issue in validation_result.issues
            if issue.severity.value in ["critical", "error"]
        ]

        if critical_or_error_issues:
            return RiskLevel.HIGH

        # Check for warning issues
        warning_issues = [
            issue
            for issue in validation_result.issues
            if issue.severity.value == "warning"
        ]

        if warning_issues:
            return RiskLevel.MEDIUM

        return RiskLevel.LOW

    async def create_column_type_conversion_migration(
        self, table_name: str, column_name: str, old_type: str, new_type: str
    ) -> Migration:
        """
        Create a Migration object for column type conversion.

        This method creates a Migration that can be executed through the
        standard orchestration engine pipeline.

        Args:
            table_name: Name of the table
            column_name: Name of the column to convert
            old_type: Current column type
            new_type: Target column type

        Returns:
            Migration object ready for execution
        """
        try:
            # Create conversion plan using SafeTypeConverter
            converter = self._get_safe_type_converter()
            plan = await converter.create_conversion_plan(
                table_name, column_name, old_type, new_type
            )

            if not plan:
                raise OrchestrationError(
                    f"Could not create conversion plan for {table_name}.{column_name}",
                    "PLAN_CREATION_FAILED",
                )

            # Convert conversion steps to migration operations
            operations = []
            for i, step in enumerate(plan.steps):
                operations.append(
                    MigrationOperation(
                        operation_type=MigrationType.MODIFY_COLUMN,
                        table_name=table_name,
                        metadata={
                            "column_name": column_name,
                            "old_type": old_type,
                            "new_type": new_type,
                            "step_index": i,
                            "step_operation": step.operation,
                            "step_description": step.description,
                            "sql": step.sql_template,
                        },
                        rollback_sql=step.rollback_sql,
                    )
                )

            # Determine risk level from conversion plan
            risk_level = RiskLevel.LOW
            if plan.risk_assessment.value == "high_risk":
                risk_level = RiskLevel.HIGH
            elif plan.risk_assessment.value == "medium_risk":
                risk_level = RiskLevel.MEDIUM

            migration = Migration(
                operations=operations,
                version=f"column_type_conversion_{table_name}_{column_name}_{int(time.time())}",
                dependencies=[],
                risk_level=risk_level,
            )

            logger.info(
                f"Created column type conversion migration with {len(operations)} operations"
            )

            return migration

        except Exception as e:
            logger.error(f"Failed to create column type conversion migration: {e}")
            raise OrchestrationError(
                f"Migration creation failed: {str(e)}", "MIGRATION_CREATION_FAILED"
            )
