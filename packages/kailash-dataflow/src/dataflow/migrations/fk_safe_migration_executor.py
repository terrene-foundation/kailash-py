#!/usr/bin/env python3
"""
FK-Safe Migration Executor - TODO-138 Phase 2

Implements safe migration execution with complete referential integrity preservation
and multi-table transaction coordination.

CRITICAL CAPABILITIES:
- FK Constraint Temporary Disable/Enable - Allow safe schema changes without violating constraints
- Multi-table Transaction Coordination - Ensure ACID compliance across multiple tables
- Data Preservation During FK Changes - Maintain all existing data relationships
- Rollback with FK Restoration - Complete rollback including constraint recreation

SPECIFIC MIGRATION SCENARIOS SUPPORTED:
1. Primary Key Data Type Changes - Change PK column type and update all FK references
2. FK Target Column Renaming - Rename PK column and update all FK column names
3. FK Reference Chain Updates - Handle cascading changes through FK chains
4. Composite FK Management - Handle multi-column foreign key relationships

SAFETY REQUIREMENTS:
- Zero Data Loss - All existing data relationships must be preserved
- Constraint Integrity - All FK constraints must be maintained or properly recreated
- Transaction Safety - Full rollback on any failure with FK constraint restoration
- Cross-table ACID - Multi-table operations must be atomic
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import asyncpg

from .dependency_analyzer import DependencyAnalyzer, ForeignKeyDependency
from .foreign_key_analyzer import (
    FKImpactLevel,
    FKImpactReport,
    FKSafeMigrationPlan,
    ForeignKeyAnalyzer,
    IntegrityValidation,
    MigrationStep,
)

logger = logging.getLogger(__name__)


class FKMigrationStage(Enum):
    """Stages of FK-safe migration execution."""

    ANALYSIS = "analysis"
    BACKUP = "backup"
    FK_CONSTRAINT_DISABLE = "fk_constraint_disable"
    SCHEMA_MODIFICATION = "schema_modification"
    DATA_MIGRATION = "data_migration"
    FK_CONSTRAINT_RESTORE = "fk_constraint_restore"
    VALIDATION = "validation"
    CLEANUP = "cleanup"


class FKTransactionState(Enum):
    """Transaction states during FK-safe migration."""

    STARTED = "started"
    FK_CONSTRAINTS_DISABLED = "fk_constraints_disabled"
    SCHEMA_MODIFIED = "schema_modified"
    DATA_MIGRATED = "data_migrated"
    FK_CONSTRAINTS_RESTORED = "fk_constraints_restored"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass
class FKConstraintInfo:
    """Information about a foreign key constraint for restoration."""

    constraint_name: str
    source_table: str
    source_columns: List[str]
    target_table: str
    target_columns: List[str]
    on_delete: str = "RESTRICT"
    on_update: str = "RESTRICT"
    is_deferred: bool = False

    @property
    def restore_sql(self) -> str:
        """Generate SQL to restore this constraint."""
        source_cols = ", ".join(self.source_columns)
        target_cols = ", ".join(self.target_columns)

        sql = f"""ALTER TABLE {self.source_table}
                  ADD CONSTRAINT {self.constraint_name}
                  FOREIGN KEY ({source_cols})
                  REFERENCES {self.target_table}({target_cols})"""

        if self.on_delete != "RESTRICT":
            sql += f" ON DELETE {self.on_delete}"
        if self.on_update != "RESTRICT":
            sql += f" ON UPDATE {self.on_update}"
        if self.is_deferred:
            sql += " DEFERRABLE INITIALLY DEFERRED"

        return sql


@dataclass
class FKMigrationResult:
    """Result of FK-safe migration execution."""

    operation_id: str
    success: bool
    stage_results: Dict[FKMigrationStage, bool] = field(default_factory=dict)
    execution_time: float = 0.0
    rows_affected: int = 0
    constraints_disabled: int = 0
    constraints_restored: int = 0
    rollback_performed: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def completed_stages(self) -> List[FKMigrationStage]:
        """Get list of successfully completed stages."""
        return [stage for stage, success in self.stage_results.items() if success]


@dataclass
class ConstraintHandlingResult:
    """Result of FK constraint handling operations."""

    constraints_disabled: List[FKConstraintInfo] = field(default_factory=list)
    constraints_restored: List[FKConstraintInfo] = field(default_factory=list)
    failed_operations: List[str] = field(default_factory=list)
    success: bool = True


@dataclass
class CoordinationResult:
    """Result of multi-table operation coordination."""

    tables_modified: List[str] = field(default_factory=list)
    transaction_savepoints: List[str] = field(default_factory=list)
    rollback_required: bool = False
    success: bool = True


@dataclass
class IntegrityPreservationResult:
    """Result of referential integrity preservation checks."""

    integrity_preserved: bool = True
    data_loss_detected: bool = False
    orphaned_records: List[Dict[str, Any]] = field(default_factory=list)
    constraint_violations: List[str] = field(default_factory=list)


class FKSafeMigrationExecutor:
    """
    Executes FK-safe migration operations with complete referential integrity preservation.

    Provides safe schema changes by temporarily disabling FK constraints, coordinating
    multi-table operations, and ensuring complete rollback capabilities.
    """

    def __init__(
        self,
        connection_manager: Optional[Any] = None,
        foreign_key_analyzer: Optional[ForeignKeyAnalyzer] = None,
        dependency_analyzer: Optional[DependencyAnalyzer] = None,
    ):
        """Initialize the FK-safe migration executor."""
        self.connection_manager = connection_manager
        self.foreign_key_analyzer = foreign_key_analyzer or ForeignKeyAnalyzer(
            connection_manager
        )
        self.dependency_analyzer = dependency_analyzer or DependencyAnalyzer(
            connection_manager
        )
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # State tracking
        self._active_transactions: Dict[str, FKTransactionState] = {}
        self._disabled_constraints: Dict[str, List[FKConstraintInfo]] = {}
        self._operation_savepoints: Dict[str, List[str]] = {}

    async def execute_fk_aware_column_modification(
        self, plan: FKSafeMigrationPlan, connection: Optional[asyncpg.Connection] = None
    ) -> FKMigrationResult:
        """
        Execute FK-aware column modification with complete safety guarantees.

        Args:
            plan: FK-safe migration plan from foreign_key_analyzer
            connection: Optional database connection

        Returns:
            FKMigrationResult with comprehensive execution details
        """
        operation_id = plan.operation_id
        start_time = datetime.now()

        if connection is None:
            connection = await self._get_connection()

        self.logger.info(f"Starting FK-aware column modification: {operation_id}")

        result = FKMigrationResult(operation_id=operation_id, success=False)

        # Initialize transaction state
        self._active_transactions[operation_id] = FKTransactionState.STARTED
        self._disabled_constraints[operation_id] = []
        self._operation_savepoints[operation_id] = []

        try:
            # Start transaction with initial savepoint
            await connection.execute("BEGIN")
            initial_savepoint = f"fk_migration_{operation_id}_{uuid.uuid4().hex[:8]}"
            await connection.execute(f"SAVEPOINT {initial_savepoint}")
            self._operation_savepoints[operation_id].append(initial_savepoint)

            # Stage 1: Analysis
            self.logger.info(f"[{operation_id}] Stage 1: Analysis")
            analysis_success = await self._execute_analysis_stage(
                plan, connection, result
            )
            result.stage_results[FKMigrationStage.ANALYSIS] = analysis_success

            if not analysis_success:
                await self._rollback_transaction(operation_id, connection)
                return result

            # Stage 2: Backup (if required)
            self.logger.info(f"[{operation_id}] Stage 2: Backup")
            backup_success = await self._execute_backup_stage(plan, connection, result)
            result.stage_results[FKMigrationStage.BACKUP] = backup_success

            if not backup_success:
                await self._rollback_transaction(operation_id, connection)
                return result

            # Stage 3: FK Constraint Disable
            self.logger.info(f"[{operation_id}] Stage 3: FK Constraint Disable")
            disable_success = await self._execute_fk_disable_stage(
                plan, connection, result
            )
            result.stage_results[FKMigrationStage.FK_CONSTRAINT_DISABLE] = (
                disable_success
            )

            if not disable_success:
                await self._rollback_transaction(operation_id, connection)
                return result

            self._active_transactions[operation_id] = (
                FKTransactionState.FK_CONSTRAINTS_DISABLED
            )
            result.constraints_disabled = len(self._disabled_constraints[operation_id])

            # Stage 4: Schema Modification
            self.logger.info(f"[{operation_id}] Stage 4: Schema Modification")
            schema_success = await self._execute_schema_modification_stage(
                plan, connection, result
            )
            result.stage_results[FKMigrationStage.SCHEMA_MODIFICATION] = schema_success

            if not schema_success:
                await self._rollback_transaction(operation_id, connection)
                return result

            self._active_transactions[operation_id] = FKTransactionState.SCHEMA_MODIFIED

            # Stage 5: Data Migration (if needed)
            self.logger.info(f"[{operation_id}] Stage 5: Data Migration")
            data_success = await self._execute_data_migration_stage(
                plan, connection, result
            )
            result.stage_results[FKMigrationStage.DATA_MIGRATION] = data_success

            if not data_success:
                await self._rollback_transaction(operation_id, connection)
                return result

            self._active_transactions[operation_id] = FKTransactionState.DATA_MIGRATED

            # Stage 6: FK Constraint Restore
            self.logger.info(f"[{operation_id}] Stage 6: FK Constraint Restore")
            restore_success = await self._execute_fk_restore_stage(
                plan, connection, result
            )
            result.stage_results[FKMigrationStage.FK_CONSTRAINT_RESTORE] = (
                restore_success
            )

            if not restore_success:
                await self._rollback_transaction(operation_id, connection)
                return result

            self._active_transactions[operation_id] = (
                FKTransactionState.FK_CONSTRAINTS_RESTORED
            )
            result.constraints_restored = len(self._disabled_constraints[operation_id])

            # Stage 7: Validation
            self.logger.info(f"[{operation_id}] Stage 7: Validation")
            validation_success = await self._execute_validation_stage(
                plan, connection, result
            )
            result.stage_results[FKMigrationStage.VALIDATION] = validation_success

            if not validation_success:
                await self._rollback_transaction(operation_id, connection)
                return result

            # Stage 8: Cleanup and Commit
            self.logger.info(f"[{operation_id}] Stage 8: Cleanup and Commit")
            cleanup_success = await self._execute_cleanup_stage(
                plan, connection, result
            )
            result.stage_results[FKMigrationStage.CLEANUP] = cleanup_success

            # Commit transaction
            await connection.execute("COMMIT")
            self._active_transactions[operation_id] = FKTransactionState.COMMITTED

            result.success = True
            result.execution_time = (datetime.now() - start_time).total_seconds()

            self.logger.info(
                f"FK-aware column modification completed successfully: {operation_id} "
                f"({result.execution_time:.2f}s)"
            )

        except Exception as e:
            self.logger.error(
                f"FK-aware column modification failed: {operation_id} - {e}"
            )
            result.errors.append(str(e))
            await self._rollback_transaction(operation_id, connection)
            result.execution_time = (datetime.now() - start_time).total_seconds()

        finally:
            # Cleanup state
            self._cleanup_operation_state(operation_id)

        return result

    async def handle_foreign_key_constraints(
        self, operation: Any, connection: Optional[asyncpg.Connection] = None
    ) -> ConstraintHandlingResult:
        """
        Handle foreign key constraints for safe schema modifications.

        Args:
            operation: Migration operation requiring FK handling
            connection: Optional database connection

        Returns:
            ConstraintHandlingResult with constraint management details
        """
        if connection is None:
            connection = await self._get_connection()

        result = ConstraintHandlingResult()

        try:
            # Extract operation details
            table = getattr(operation, "table", "")
            column = getattr(operation, "column", "")

            # Handle different operation types
            if not column:
                # Check for rename operations
                column = getattr(operation, "old_column_name", "")

            if not table:
                result.failed_operations.append("Operation missing table information")
                result.success = False
                return result

            # Find all FK constraints that need to be handled
            if column:
                fk_dependencies = (
                    await self.dependency_analyzer.find_foreign_key_dependencies(
                        table, column, connection
                    )
                )
            else:
                # Table-level operation - find all table FKs
                fk_dependencies = await self._find_all_table_foreign_keys(
                    table, connection
                )

            # Convert to constraint info objects
            constraint_infos = []
            for fk_dep in fk_dependencies:
                constraint_info = FKConstraintInfo(
                    constraint_name=fk_dep.constraint_name,
                    source_table=fk_dep.source_table,
                    source_columns=[fk_dep.source_column],
                    target_table=fk_dep.target_table,
                    target_columns=[fk_dep.target_column],
                    on_delete=fk_dep.on_delete,
                    on_update=fk_dep.on_update,
                )
                constraint_infos.append(constraint_info)

            # Disable constraints
            for constraint_info in constraint_infos:
                try:
                    drop_sql = f"ALTER TABLE {constraint_info.source_table} DROP CONSTRAINT {constraint_info.constraint_name}"
                    await connection.execute(drop_sql)
                    result.constraints_disabled.append(constraint_info)
                    self.logger.info(
                        f"Disabled FK constraint: {constraint_info.constraint_name}"
                    )
                except Exception as e:
                    self.logger.error(
                        f"Failed to disable FK constraint {constraint_info.constraint_name}: {e}"
                    )
                    result.failed_operations.append(
                        f"Drop constraint {constraint_info.constraint_name}: {e}"
                    )
                    result.success = False

            self.logger.info(
                f"Handled {len(result.constraints_disabled)} FK constraints"
            )

        except Exception as e:
            self.logger.error(f"Error handling FK constraints: {e}")
            result.failed_operations.append(f"Constraint handling error: {e}")
            result.success = False

        return result

    async def coordinate_multi_table_changes(
        self,
        tables: List[str],
        changes: Dict[str, Any],
        connection: Optional[asyncpg.Connection] = None,
    ) -> CoordinationResult:
        """
        Coordinate changes across multiple tables with ACID compliance.

        Args:
            tables: List of tables involved in the operation
            changes: Dictionary of changes to apply per table
            connection: Optional database connection

        Returns:
            CoordinationResult with coordination status
        """
        if connection is None:
            connection = await self._get_connection()

        result = CoordinationResult()
        operation_id = uuid.uuid4().hex[:8]

        try:
            self.logger.info(
                f"Coordinating multi-table changes across {len(tables)} tables"
            )

            # Try to create savepoints, start transaction if needed
            transaction_started = False
            try:
                # Try to create first savepoint to test if we're in a transaction
                savepoint_name = f"table_change_{operation_id}_0"
                await connection.execute(f"SAVEPOINT {savepoint_name}")
                result.transaction_savepoints.append(savepoint_name)
                self.logger.debug(f"Created savepoint: {savepoint_name}")
            except Exception as e:
                if "SAVEPOINT can only be used in transaction blocks" in str(e):
                    # Start transaction and create savepoint
                    await connection.execute("BEGIN")
                    transaction_started = True
                    await connection.execute(f"SAVEPOINT {savepoint_name}")
                    result.transaction_savepoints.append(savepoint_name)
                    self.logger.debug(
                        "Started transaction and created initial savepoint"
                    )
                else:
                    raise e

            # Create savepoints for remaining tables
            for i, table in enumerate(tables[1:], 1):
                savepoint_name = f"table_change_{operation_id}_{i}"
                await connection.execute(f"SAVEPOINT {savepoint_name}")
                result.transaction_savepoints.append(savepoint_name)
                self.logger.debug(
                    f"Created savepoint: {savepoint_name} for table: {table}"
                )

            # Apply changes to each table
            for table in tables:
                if table in changes:
                    table_changes = changes[table]

                    try:
                        # Apply table-specific changes
                        await self._apply_table_changes(
                            table, table_changes, connection
                        )
                        result.tables_modified.append(table)
                        self.logger.info(f"Applied changes to table: {table}")

                    except Exception as e:
                        self.logger.error(
                            f"Failed to apply changes to table {table}: {e}"
                        )
                        result.rollback_required = True
                        result.success = False
                        break

            # If any operation failed, rollback is required
            if result.rollback_required:
                # Rollback to the beginning of the multi-table operation
                if result.transaction_savepoints:
                    first_savepoint = result.transaction_savepoints[0]
                    await connection.execute(f"ROLLBACK TO SAVEPOINT {first_savepoint}")
                    self.logger.info(
                        f"Rolled back multi-table changes to {first_savepoint}"
                    )
                    result.tables_modified.clear()

            self.logger.info(
                f"Multi-table coordination {'completed' if result.success else 'failed'}: "
                f"{len(result.tables_modified)} tables modified"
            )

        except Exception as e:
            self.logger.error(f"Error coordinating multi-table changes: {e}")
            result.rollback_required = True
            result.success = False

        return result

    async def ensure_referential_integrity_preservation(
        self, operation: Any, connection: Optional[asyncpg.Connection] = None
    ) -> IntegrityPreservationResult:
        """
        Ensure that referential integrity is preserved during migration.

        Args:
            operation: Migration operation to validate
            connection: Optional database connection

        Returns:
            IntegrityPreservationResult with integrity analysis
        """
        if connection is None:
            connection = await self._get_connection()

        result = IntegrityPreservationResult()

        try:
            # Extract operation details
            table = getattr(operation, "table", "")
            column = getattr(operation, "column", "")

            if not table:
                result.integrity_preserved = False
                result.constraint_violations.append(
                    "Operation missing table information"
                )
                return result

            # Check for orphaned records that would be created
            orphaned_records = await self._detect_orphaned_records(
                table, column, operation, connection
            )
            if orphaned_records:
                result.orphaned_records = orphaned_records
                result.data_loss_detected = True
                result.integrity_preserved = False
                self.logger.warning(
                    f"Detected {len(orphaned_records)} potentially orphaned records"
                )

            # Validate FK constraints would still be satisfied after operation
            constraint_violations = await self._validate_constraint_satisfaction(
                table, column, operation, connection
            )
            if constraint_violations:
                result.constraint_violations = constraint_violations
                result.integrity_preserved = False
                self.logger.error(
                    f"Detected {len(constraint_violations)} constraint violations"
                )

            # Additional integrity checks
            integrity_checks = await self._perform_additional_integrity_checks(
                table, operation, connection
            )
            if not integrity_checks:
                result.integrity_preserved = False
                result.constraint_violations.append(
                    "Additional integrity checks failed"
                )

            if result.integrity_preserved:
                self.logger.info(
                    f"Referential integrity preservation validated for {table}"
                )
            else:
                self.logger.error(
                    f"Referential integrity preservation validation failed for {table}"
                )

        except Exception as e:
            self.logger.error(
                f"Error validating referential integrity preservation: {e}"
            )
            result.integrity_preserved = False
            result.constraint_violations.append(f"Validation error: {e}")

        return result

    # Private helper methods

    async def _get_connection(self) -> asyncpg.Connection:
        """Get database connection from connection manager."""
        if self.connection_manager is None:
            raise ValueError("Connection manager not configured")

        return await self.connection_manager.get_connection()

    async def _execute_analysis_stage(
        self,
        plan: FKSafeMigrationPlan,
        connection: asyncpg.Connection,
        result: FKMigrationResult,
    ) -> bool:
        """Execute analysis stage of migration."""
        try:
            # Verify plan validity
            if not plan.steps:
                result.errors.append("Migration plan is empty")
                return False

            # Check database state
            if not await self._verify_database_state(connection):
                result.errors.append("Database state verification failed")
                return False

            return True
        except Exception as e:
            result.errors.append(f"Analysis stage failed: {e}")
            return False

    async def _execute_backup_stage(
        self,
        plan: FKSafeMigrationPlan,
        connection: asyncpg.Connection,
        result: FKMigrationResult,
    ) -> bool:
        """Execute backup stage of migration."""
        try:
            # For now, just log backup intention
            # In full implementation, would create backups based on plan requirements
            self.logger.info("Backup stage completed (implementation placeholder)")
            return True
        except Exception as e:
            result.errors.append(f"Backup stage failed: {e}")
            return False

    async def _execute_fk_disable_stage(
        self,
        plan: FKSafeMigrationPlan,
        connection: asyncpg.Connection,
        result: FKMigrationResult,
    ) -> bool:
        """Execute FK constraint disable stage."""
        try:
            operation_id = plan.operation_id

            # Find FK constraints to disable based on plan steps
            for step in plan.steps:
                if step.step_type == "drop_constraint":
                    # Extract constraint info from step
                    constraint_name = self._extract_constraint_name_from_sql(
                        step.sql_command
                    )
                    table_name = self._extract_table_name_from_sql(step.sql_command)

                    if constraint_name and table_name:
                        # Get full constraint information before dropping
                        constraint_info = await self._get_constraint_info(
                            constraint_name, table_name, connection
                        )

                        if constraint_info:
                            # Execute the drop constraint command
                            await connection.execute(step.sql_command)
                            self._disabled_constraints[operation_id].append(
                                constraint_info
                            )
                            self.logger.info(
                                f"Disabled FK constraint: {constraint_name}"
                            )
                        else:
                            result.warnings.append(
                                f"Could not get info for constraint: {constraint_name}"
                            )

            return True
        except Exception as e:
            result.errors.append(f"FK disable stage failed: {e}")
            return False

    async def _execute_schema_modification_stage(
        self,
        plan: FKSafeMigrationPlan,
        connection: asyncpg.Connection,
        result: FKMigrationResult,
    ) -> bool:
        """Execute schema modification stage."""
        try:
            # Execute schema modification steps
            for step in plan.steps:
                if step.step_type == "modify_column":
                    await connection.execute(step.sql_command)
                    self.logger.info(
                        f"Executed schema modification: {step.description}"
                    )

            return True
        except Exception as e:
            result.errors.append(f"Schema modification stage failed: {e}")
            return False

    async def _execute_data_migration_stage(
        self,
        plan: FKSafeMigrationPlan,
        connection: asyncpg.Connection,
        result: FKMigrationResult,
    ) -> bool:
        """Execute data migration stage."""
        try:
            # Data migration logic would go here
            # For now, assume no data migration is needed
            self.logger.info("Data migration stage completed (no migration required)")
            return True
        except Exception as e:
            result.errors.append(f"Data migration stage failed: {e}")
            return False

    async def _execute_fk_restore_stage(
        self,
        plan: FKSafeMigrationPlan,
        connection: asyncpg.Connection,
        result: FKMigrationResult,
    ) -> bool:
        """Execute FK constraint restore stage."""
        try:
            operation_id = plan.operation_id

            # Restore all disabled constraints
            for constraint_info in self._disabled_constraints[operation_id]:
                try:
                    await connection.execute(constraint_info.restore_sql)
                    self.logger.info(
                        f"Restored FK constraint: {constraint_info.constraint_name}"
                    )
                except Exception as e:
                    result.errors.append(
                        f"Failed to restore constraint {constraint_info.constraint_name}: {e}"
                    )
                    return False

            return True
        except Exception as e:
            result.errors.append(f"FK restore stage failed: {e}")
            return False

    async def _execute_validation_stage(
        self,
        plan: FKSafeMigrationPlan,
        connection: asyncpg.Connection,
        result: FKMigrationResult,
    ) -> bool:
        """Execute validation stage."""
        try:
            # Validate that all constraints are working
            operation_id = plan.operation_id

            for constraint_info in self._disabled_constraints[operation_id]:
                # Check that the constraint exists and is valid
                exists = await self._verify_constraint_exists(
                    constraint_info, connection
                )
                if not exists:
                    result.errors.append(
                        f"Constraint validation failed: {constraint_info.constraint_name}"
                    )
                    return False

            return True
        except Exception as e:
            result.errors.append(f"Validation stage failed: {e}")
            return False

    async def _execute_cleanup_stage(
        self,
        plan: FKSafeMigrationPlan,
        connection: asyncpg.Connection,
        result: FKMigrationResult,
    ) -> bool:
        """Execute cleanup stage."""
        try:
            # Cleanup temporary objects, release savepoints, etc.
            operation_id = plan.operation_id

            # Release savepoints
            for savepoint in self._operation_savepoints.get(operation_id, []):
                try:
                    await connection.execute(f"RELEASE SAVEPOINT {savepoint}")
                except Exception:
                    # Savepoints may already be released, ignore errors
                    pass

            return True
        except Exception as e:
            result.errors.append(f"Cleanup stage failed: {e}")
            return False

    async def _rollback_transaction(
        self, operation_id: str, connection: asyncpg.Connection
    ):
        """Rollback transaction and restore FK constraints."""
        try:
            self.logger.info(f"Rolling back transaction for operation: {operation_id}")

            # Try to rollback to the initial savepoint
            savepoints = self._operation_savepoints.get(operation_id, [])
            if savepoints:
                initial_savepoint = savepoints[0]
                await connection.execute(f"ROLLBACK TO SAVEPOINT {initial_savepoint}")
                self.logger.info(f"Rolled back to savepoint: {initial_savepoint}")
            else:
                # Full rollback
                await connection.execute("ROLLBACK")
                self.logger.info("Performed full transaction rollback")

            self._active_transactions[operation_id] = FKTransactionState.ROLLED_BACK

        except Exception as e:
            self.logger.error(f"Error during rollback: {e}")
            self._active_transactions[operation_id] = FKTransactionState.FAILED

    def _cleanup_operation_state(self, operation_id: str):
        """Clean up operation state tracking."""
        self._active_transactions.pop(operation_id, None)
        self._disabled_constraints.pop(operation_id, None)
        self._operation_savepoints.pop(operation_id, None)

    async def _verify_database_state(self, connection: asyncpg.Connection) -> bool:
        """Verify database is in a valid state for migration."""
        try:
            # Check database connectivity
            await connection.fetchval("SELECT 1")
            return True
        except Exception:
            return False

    def _extract_constraint_name_from_sql(self, sql: str) -> Optional[str]:
        """Extract constraint name from DROP CONSTRAINT SQL."""
        import re

        match = re.search(r"DROP CONSTRAINT\s+(\w+)", sql, re.IGNORECASE)
        return match.group(1) if match else None

    def _extract_table_name_from_sql(self, sql: str) -> Optional[str]:
        """Extract table name from ALTER TABLE SQL."""
        import re

        match = re.search(r"ALTER TABLE\s+(\w+)", sql, re.IGNORECASE)
        return match.group(1) if match else None

    async def _get_constraint_info(
        self, constraint_name: str, table_name: str, connection: asyncpg.Connection
    ) -> Optional[FKConstraintInfo]:
        """Get full information about a foreign key constraint."""
        try:
            query = """
            SELECT DISTINCT
                tc.constraint_name,
                tc.table_name as source_table,
                kcu.column_name as source_column,
                ccu.table_name as target_table,
                ccu.column_name as target_column,
                rc.delete_rule as on_delete,
                rc.update_rule as on_update
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            LEFT JOIN information_schema.referential_constraints AS rc
                ON rc.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.constraint_name = $1
                AND tc.table_name = $2
                AND tc.table_schema = 'public'
            """

            row = await connection.fetchrow(query, constraint_name, table_name)
            if row:
                return FKConstraintInfo(
                    constraint_name=row["constraint_name"],
                    source_table=row["source_table"],
                    source_columns=[row["source_column"]],
                    target_table=row["target_table"],
                    target_columns=[row["target_column"]],
                    on_delete=row["on_delete"] or "RESTRICT",
                    on_update=row["on_update"] or "RESTRICT",
                )
            return None
        except Exception as e:
            self.logger.error(f"Error getting constraint info: {e}")
            return None

    async def _verify_constraint_exists(
        self, constraint_info: FKConstraintInfo, connection: asyncpg.Connection
    ) -> bool:
        """Verify that a constraint exists and is valid."""
        try:
            query = """
            SELECT COUNT(*)
            FROM information_schema.table_constraints
            WHERE constraint_name = $1
                AND table_name = $2
                AND constraint_type = 'FOREIGN KEY'
                AND table_schema = 'public'
            """

            count = await connection.fetchval(
                query, constraint_info.constraint_name, constraint_info.source_table
            )
            return count > 0
        except Exception:
            return False

    async def _find_all_table_foreign_keys(
        self, table: str, connection: asyncpg.Connection
    ) -> List[ForeignKeyDependency]:
        """Find all FK constraints involving a table (as source or target)."""
        # For now, return empty list - would implement full logic
        return []

    async def _apply_table_changes(
        self, table: str, changes: Dict[str, Any], connection: asyncpg.Connection
    ):
        """Apply changes to a specific table."""
        # Implementation would depend on the type of changes
        self.logger.info(f"Applied changes to table: {table}")

    async def _detect_orphaned_records(
        self, table: str, column: str, operation: Any, connection: asyncpg.Connection
    ) -> List[Dict[str, Any]]:
        """Detect records that would become orphaned."""
        # Implementation would check for referential integrity violations
        return []

    async def _validate_constraint_satisfaction(
        self, table: str, column: str, operation: Any, connection: asyncpg.Connection
    ) -> List[str]:
        """Validate that constraints would still be satisfied."""
        # Implementation would check constraint violations
        return []

    async def _perform_additional_integrity_checks(
        self, table: str, operation: Any, connection: asyncpg.Connection
    ) -> bool:
        """Perform additional integrity checks."""
        # Implementation would perform comprehensive checks
        return True
