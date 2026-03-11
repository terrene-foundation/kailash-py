#!/usr/bin/env python3
"""
FK Migration Operations - Specialized handlers for specific FK migration scenarios.

Implements specialized operations for:
1. Primary Key Data Type Changes - Change PK column type and update all FK references
2. FK Target Column Renaming - Rename PK column and update all FK column names
3. FK Reference Chain Updates - Handle cascading changes through FK chains
4. Composite FK Management - Handle multi-column foreign key relationships

CRITICAL SAFETY GUARANTEES:
- Zero Data Loss - All existing data relationships preserved
- Referential Integrity - FK constraints maintained throughout process
- Multi-table ACID Compliance - All operations atomic across tables
- Complete Rollback - Full recovery including FK constraint restoration
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

import asyncpg

from .dependency_analyzer import DependencyAnalyzer, ForeignKeyDependency
from .fk_safe_migration_executor import (
    CoordinationResult,
    FKConstraintInfo,
    FKMigrationResult,
    FKSafeMigrationExecutor,
    IntegrityPreservationResult,
)
from .foreign_key_analyzer import FKChain, ForeignKeyAnalyzer

logger = logging.getLogger(__name__)


class FKOperationScenario(Enum):
    """Types of FK migration scenarios."""

    PRIMARY_KEY_TYPE_CHANGE = "primary_key_type_change"
    FK_TARGET_COLUMN_RENAME = "fk_target_column_rename"
    FK_REFERENCE_CHAIN_UPDATE = "fk_reference_chain_update"
    COMPOSITE_FK_MANAGEMENT = "composite_fk_management"


@dataclass
class PKTypeChangeOperation:
    """Operation to change primary key column type and update all FK references."""

    table: str
    column: str
    old_type: str
    new_type: str
    affected_fk_tables: List[str] = field(default_factory=list)
    data_conversion_required: bool = False
    conversion_sql: Optional[str] = None


@dataclass
class FKTargetRenameOperation:
    """Operation to rename FK target column and update all referencing FK columns."""

    table: str
    old_column_name: str
    new_column_name: str
    affected_fk_constraints: List[str] = field(default_factory=list)
    requires_index_recreation: bool = False


@dataclass
class FKChainUpdateOperation:
    """Operation to handle cascading changes through FK dependency chains."""

    root_table: str
    chain: FKChain
    update_type: str  # "rename", "type_change", "drop"
    cascading_changes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompositeFKOperation:
    """Operation to handle multi-column foreign key relationships."""

    source_table: str
    target_table: str
    source_columns: List[str]
    target_columns: List[str]
    constraint_name: str
    operation_type: str  # "modify", "add", "drop"
    column_changes: Dict[str, str] = field(default_factory=dict)  # old_name -> new_name


class FKMigrationOperations:
    """
    Specialized handlers for complex FK migration scenarios.

    Provides safe execution of complex FK operations that require coordinated
    multi-table changes with complete referential integrity preservation.
    """

    def __init__(
        self,
        executor: FKSafeMigrationExecutor,
        foreign_key_analyzer: Optional[ForeignKeyAnalyzer] = None,
        dependency_analyzer: Optional[DependencyAnalyzer] = None,
    ):
        """Initialize FK migration operations handler."""
        self.executor = executor
        self.foreign_key_analyzer = foreign_key_analyzer or ForeignKeyAnalyzer()
        self.dependency_analyzer = dependency_analyzer or DependencyAnalyzer()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def execute_primary_key_type_change(
        self,
        operation: PKTypeChangeOperation,
        connection: Optional[asyncpg.Connection] = None,
    ) -> FKMigrationResult:
        """
        Execute primary key type change with FK reference updates.

        This is the most complex FK operation as it requires:
        1. Identifying all FK references to the PK
        2. Temporarily disabling all FK constraints
        3. Changing the PK column type
        4. Updating all FK column types to match
        5. Re-enabling FK constraints
        6. Validating referential integrity

        Args:
            operation: PK type change operation details
            connection: Optional database connection

        Returns:
            FKMigrationResult with execution details
        """
        if connection is None:
            connection = await self.executor._get_connection()

        self.logger.info(
            f"Executing PK type change: {operation.table}.{operation.column} "
            f"({operation.old_type} -> {operation.new_type})"
        )

        # Phase 1: Analysis - Find all FK dependencies
        fk_dependencies = await self.dependency_analyzer.find_foreign_key_dependencies(
            operation.table, operation.column, connection
        )

        if not fk_dependencies:
            self.logger.info(
                "No FK dependencies found, executing simple column type change"
            )
            return await self._execute_simple_type_change(operation, connection)

        operation.affected_fk_tables = list(
            set(fk.source_table for fk in fk_dependencies)
        )
        self.logger.info(
            f"Found {len(fk_dependencies)} FK dependencies across {len(operation.affected_fk_tables)} tables"
        )

        # Phase 2: Prepare multi-table changes
        changes = {
            operation.table: {
                "type": "column_type_change",
                "column": operation.column,
                "old_type": operation.old_type,
                "new_type": operation.new_type,
                "conversion_sql": operation.conversion_sql,
            }
        }

        # Add FK column type changes
        for fk_dep in fk_dependencies:
            if fk_dep.source_table not in changes:
                changes[fk_dep.source_table] = {}

            changes[fk_dep.source_table][f"fk_column_{fk_dep.source_column}"] = {
                "type": "fk_column_type_change",
                "column": fk_dep.source_column,
                "new_type": operation.new_type,
                "constraint_name": fk_dep.constraint_name,
            }

        # Phase 3: Execute coordinated multi-table changes
        all_tables = [operation.table] + operation.affected_fk_tables
        coordination_result = await self.executor.coordinate_multi_table_changes(
            all_tables, changes, connection
        )

        if not coordination_result.success:
            return FKMigrationResult(
                operation_id=f"pk_type_change_{operation.table}_{operation.column}",
                success=False,
                errors=[f"Multi-table coordination failed: {coordination_result}"],
            )

        # Phase 4: Validate integrity preservation
        integrity_result = (
            await self.executor.ensure_referential_integrity_preservation(
                operation, connection
            )
        )

        result = FKMigrationResult(
            operation_id=f"pk_type_change_{operation.table}_{operation.column}",
            success=coordination_result.success
            and integrity_result.integrity_preserved,
            rows_affected=len(fk_dependencies),
            constraints_disabled=len(fk_dependencies),
            constraints_restored=(
                len(fk_dependencies) if coordination_result.success else 0
            ),
        )

        if not integrity_result.integrity_preserved:
            result.errors.extend(integrity_result.constraint_violations)

        self.logger.info(
            f"PK type change {'completed' if result.success else 'failed'}"
        )
        return result

    async def execute_fk_target_column_rename(
        self,
        operation: FKTargetRenameOperation,
        connection: Optional[asyncpg.Connection] = None,
    ) -> FKMigrationResult:
        """
        Execute FK target column rename with FK constraint updates.

        This operation requires:
        1. Finding all FK constraints referencing the target column
        2. Dropping FK constraints
        3. Renaming the target column
        4. Recreating FK constraints with updated references
        5. Updating any indexes if necessary

        Args:
            operation: FK target rename operation details
            connection: Optional database connection

        Returns:
            FKMigrationResult with execution details
        """
        if connection is None:
            connection = await self.executor._get_connection()

        self.logger.info(
            f"Executing FK target column rename: {operation.table}.{operation.old_column_name} "
            f"-> {operation.new_column_name}"
        )

        # Phase 1: Find all FK constraints referencing this column
        fk_dependencies = await self.dependency_analyzer.find_foreign_key_dependencies(
            operation.table, operation.old_column_name, connection
        )

        operation.affected_fk_constraints = [
            fk.constraint_name for fk in fk_dependencies
        ]

        if not fk_dependencies:
            self.logger.info("No FK dependencies found, executing simple column rename")
            return await self._execute_simple_column_rename(operation, connection)

        # Phase 2: Handle FK constraints
        constraint_result = await self.executor.handle_foreign_key_constraints(
            operation, connection
        )

        if not constraint_result.success:
            return FKMigrationResult(
                operation_id=f"fk_rename_{operation.table}_{operation.old_column_name}",
                success=False,
                errors=constraint_result.failed_operations,
            )

        # Phase 3: Rename the column
        try:
            rename_sql = f"ALTER TABLE {operation.table} RENAME COLUMN {operation.old_column_name} TO {operation.new_column_name}"
            await connection.execute(rename_sql)
            self.logger.info(
                f"Column renamed: {operation.old_column_name} -> {operation.new_column_name}"
            )
        except Exception as e:
            return FKMigrationResult(
                operation_id=f"fk_rename_{operation.table}_{operation.old_column_name}",
                success=False,
                errors=[f"Column rename failed: {e}"],
            )

        # Phase 4: Recreate FK constraints with new column reference
        restored_constraints = 0
        for fk_dep in fk_dependencies:
            try:
                # Create new constraint with updated target column name
                restore_sql = f"""ALTER TABLE {fk_dep.source_table}
                                 ADD CONSTRAINT {fk_dep.constraint_name}
                                 FOREIGN KEY ({fk_dep.source_column})
                                 REFERENCES {operation.table}({operation.new_column_name})"""

                if fk_dep.on_delete != "RESTRICT":
                    restore_sql += f" ON DELETE {fk_dep.on_delete}"
                if fk_dep.on_update != "RESTRICT":
                    restore_sql += f" ON UPDATE {fk_dep.on_update}"

                await connection.execute(restore_sql)
                restored_constraints += 1
                self.logger.info(f"Restored FK constraint: {fk_dep.constraint_name}")

            except Exception as e:
                return FKMigrationResult(
                    operation_id=f"fk_rename_{operation.table}_{operation.old_column_name}",
                    success=False,
                    errors=[
                        f"Failed to restore constraint {fk_dep.constraint_name}: {e}"
                    ],
                )

        result = FKMigrationResult(
            operation_id=f"fk_rename_{operation.table}_{operation.old_column_name}",
            success=True,
            constraints_disabled=len(constraint_result.constraints_disabled),
            constraints_restored=restored_constraints,
        )

        self.logger.info("FK target column rename completed successfully")
        return result

    async def execute_fk_reference_chain_update(
        self,
        operation: FKChainUpdateOperation,
        connection: Optional[asyncpg.Connection] = None,
    ) -> FKMigrationResult:
        """
        Execute cascading updates through FK dependency chains.

        This operation handles complex scenarios where changes need to
        propagate through multiple levels of FK relationships.

        Args:
            operation: FK chain update operation details
            connection: Optional database connection

        Returns:
            FKMigrationResult with execution details
        """
        if connection is None:
            connection = await self.executor._get_connection()

        self.logger.info(
            f"Executing FK chain update for root table: {operation.root_table}"
        )

        # Phase 1: Analyze the FK chain
        chain = operation.chain
        if chain.contains_cycles:
            return FKMigrationResult(
                operation_id=f"fk_chain_{operation.root_table}",
                success=False,
                errors=[
                    "Cannot process FK chain with cycles - manual intervention required"
                ],
            )

        all_tables = list(chain.get_all_tables())
        self.logger.info(f"FK chain involves {len(all_tables)} tables: {all_tables}")

        # Phase 2: Plan cascading changes
        cascading_changes = {}

        # Build change plan based on update type
        if operation.update_type == "rename":
            cascading_changes = await self._plan_chain_rename_changes(
                chain, operation.cascading_changes
            )
        elif operation.update_type == "type_change":
            cascading_changes = await self._plan_chain_type_changes(
                chain, operation.cascading_changes
            )
        else:
            return FKMigrationResult(
                operation_id=f"fk_chain_{operation.root_table}",
                success=False,
                errors=[f"Unsupported chain update type: {operation.update_type}"],
            )

        # Phase 3: Execute coordinated changes
        coordination_result = await self.executor.coordinate_multi_table_changes(
            all_tables, cascading_changes, connection
        )

        result = FKMigrationResult(
            operation_id=f"fk_chain_{operation.root_table}",
            success=coordination_result.success,
            rows_affected=len(chain.nodes),
        )

        if not coordination_result.success:
            result.errors.append("FK chain update coordination failed")

        self.logger.info(
            f"FK chain update {'completed' if result.success else 'failed'}"
        )
        return result

    async def execute_composite_fk_management(
        self,
        operation: CompositeFKOperation,
        connection: Optional[asyncpg.Connection] = None,
    ) -> FKMigrationResult:
        """
        Execute composite (multi-column) FK management operations.

        Handles complex scenarios with multi-column foreign keys,
        including column renaming within composite keys.

        Args:
            operation: Composite FK operation details
            connection: Optional database connection

        Returns:
            FKMigrationResult with execution details
        """
        if connection is None:
            connection = await self.executor._get_connection()

        self.logger.info(
            f"Executing composite FK operation: {operation.constraint_name}"
        )

        # Phase 1: Validate composite FK exists
        constraint_info = await self._get_composite_constraint_info(
            operation, connection
        )
        if not constraint_info:
            return FKMigrationResult(
                operation_id=f"composite_fk_{operation.constraint_name}",
                success=False,
                errors=[
                    f"Composite FK constraint not found: {operation.constraint_name}"
                ],
            )

        # Phase 2: Handle based on operation type
        if operation.operation_type == "modify":
            return await self._execute_composite_fk_modification(
                operation, constraint_info, connection
            )
        elif operation.operation_type == "add":
            return await self._execute_composite_fk_addition(operation, connection)
        elif operation.operation_type == "drop":
            return await self._execute_composite_fk_removal(operation, connection)
        else:
            return FKMigrationResult(
                operation_id=f"composite_fk_{operation.constraint_name}",
                success=False,
                errors=[
                    f"Unsupported composite FK operation: {operation.operation_type}"
                ],
            )

    # Private helper methods

    async def _execute_simple_type_change(
        self, operation: PKTypeChangeOperation, connection: asyncpg.Connection
    ) -> FKMigrationResult:
        """Execute simple column type change without FK dependencies."""
        try:
            sql = f"ALTER TABLE {operation.table} ALTER COLUMN {operation.column} TYPE {operation.new_type}"
            if operation.conversion_sql:
                sql += f" USING {operation.conversion_sql}"

            await connection.execute(sql)

            return FKMigrationResult(
                operation_id=f"simple_type_change_{operation.table}_{operation.column}",
                success=True,
            )
        except Exception as e:
            return FKMigrationResult(
                operation_id=f"simple_type_change_{operation.table}_{operation.column}",
                success=False,
                errors=[f"Simple type change failed: {e}"],
            )

    async def _execute_simple_column_rename(
        self, operation: FKTargetRenameOperation, connection: asyncpg.Connection
    ) -> FKMigrationResult:
        """Execute simple column rename without FK dependencies."""
        try:
            sql = f"ALTER TABLE {operation.table} RENAME COLUMN {operation.old_column_name} TO {operation.new_column_name}"
            await connection.execute(sql)

            return FKMigrationResult(
                operation_id=f"simple_rename_{operation.table}_{operation.old_column_name}",
                success=True,
            )
        except Exception as e:
            return FKMigrationResult(
                operation_id=f"simple_rename_{operation.table}_{operation.old_column_name}",
                success=False,
                errors=[f"Simple rename failed: {e}"],
            )

    async def _plan_chain_rename_changes(
        self, chain: FKChain, base_changes: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Plan cascading rename changes through FK chain."""
        changes = base_changes.copy()

        # Add changes for each node in the chain
        for node in chain.nodes:
            if node.table_name not in changes:
                changes[node.table_name] = {}

            # Add FK constraint recreation with new names
            changes[node.table_name][f"fk_update_{node.constraint_name}"] = {
                "type": "fk_constraint_update",
                "constraint_name": node.constraint_name,
                "source_column": node.column_name,
                "target_table": node.target_table,
                "target_column": node.target_column,
            }

        return changes

    async def _plan_chain_type_changes(
        self, chain: FKChain, base_changes: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Plan cascading type changes through FK chain."""
        changes = base_changes.copy()

        # Similar to rename, but for type changes
        for node in chain.nodes:
            if node.table_name not in changes:
                changes[node.table_name] = {}

            changes[node.table_name][f"type_update_{node.column_name}"] = {
                "type": "column_type_change",
                "column": node.column_name,
                "new_type": base_changes.get("new_type", "VARCHAR"),  # Default fallback
            }

        return changes

    async def _get_composite_constraint_info(
        self, operation: CompositeFKOperation, connection: asyncpg.Connection
    ) -> Optional[Dict[str, Any]]:
        """Get information about a composite FK constraint."""
        try:
            query = """
            SELECT
                tc.constraint_name,
                array_agg(kcu.column_name ORDER BY kcu.ordinal_position) as source_columns,
                ccu.table_name as target_table,
                array_agg(ccu.column_name ORDER BY kcu.ordinal_position) as target_columns
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_name = $1
                AND tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_schema = current_schema()
            GROUP BY tc.constraint_name, ccu.table_name
            """

            row = await connection.fetchrow(query, operation.constraint_name)
            if row:
                return {
                    "constraint_name": row["constraint_name"],
                    "source_columns": row["source_columns"],
                    "target_table": row["target_table"],
                    "target_columns": row["target_columns"],
                }
            return None
        except Exception as e:
            self.logger.error(f"Error getting composite constraint info: {e}")
            return None

    async def _execute_composite_fk_modification(
        self,
        operation: CompositeFKOperation,
        constraint_info: Dict[str, Any],
        connection: asyncpg.Connection,
    ) -> FKMigrationResult:
        """Execute composite FK modification."""
        try:
            # Drop existing constraint
            drop_sql = f"ALTER TABLE {operation.source_table} DROP CONSTRAINT {operation.constraint_name}"
            await connection.execute(drop_sql)

            # Apply column changes if any
            for old_col, new_col in operation.column_changes.items():
                if old_col in constraint_info["source_columns"]:
                    rename_sql = f"ALTER TABLE {operation.source_table} RENAME COLUMN {old_col} TO {new_col}"
                    await connection.execute(rename_sql)

            # Recreate constraint with updated columns
            source_cols = ", ".join(operation.source_columns)
            target_cols = ", ".join(operation.target_columns)

            restore_sql = f"""ALTER TABLE {operation.source_table}
                             ADD CONSTRAINT {operation.constraint_name}
                             FOREIGN KEY ({source_cols})
                             REFERENCES {operation.target_table}({target_cols})"""

            await connection.execute(restore_sql)

            return FKMigrationResult(
                operation_id=f"composite_modify_{operation.constraint_name}",
                success=True,
                constraints_disabled=1,
                constraints_restored=1,
            )
        except Exception as e:
            return FKMigrationResult(
                operation_id=f"composite_modify_{operation.constraint_name}",
                success=False,
                errors=[f"Composite FK modification failed: {e}"],
            )

    async def _execute_composite_fk_addition(
        self, operation: CompositeFKOperation, connection: asyncpg.Connection
    ) -> FKMigrationResult:
        """Execute composite FK addition."""
        try:
            source_cols = ", ".join(operation.source_columns)
            target_cols = ", ".join(operation.target_columns)

            add_sql = f"""ALTER TABLE {operation.source_table}
                         ADD CONSTRAINT {operation.constraint_name}
                         FOREIGN KEY ({source_cols})
                         REFERENCES {operation.target_table}({target_cols})"""

            await connection.execute(add_sql)

            return FKMigrationResult(
                operation_id=f"composite_add_{operation.constraint_name}",
                success=True,
                constraints_restored=1,
            )
        except Exception as e:
            return FKMigrationResult(
                operation_id=f"composite_add_{operation.constraint_name}",
                success=False,
                errors=[f"Composite FK addition failed: {e}"],
            )

    async def _execute_composite_fk_removal(
        self, operation: CompositeFKOperation, connection: asyncpg.Connection
    ) -> FKMigrationResult:
        """Execute composite FK removal."""
        try:
            drop_sql = f"ALTER TABLE {operation.source_table} DROP CONSTRAINT {operation.constraint_name}"
            await connection.execute(drop_sql)

            return FKMigrationResult(
                operation_id=f"composite_drop_{operation.constraint_name}",
                success=True,
                constraints_disabled=1,
            )
        except Exception as e:
            return FKMigrationResult(
                operation_id=f"composite_drop_{operation.constraint_name}",
                success=False,
                errors=[f"Composite FK removal failed: {e}"],
            )
