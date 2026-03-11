"""
DataFlow Auto-Migration System - Universal Database Support

Advanced migration system that automatically detects schema changes,
provides visual confirmation, and supports rollback capabilities.

Features:
- Automatic schema comparison and diff generation for PostgreSQL and SQLite
- Visual confirmation before applying changes
- Rollback and versioning support
- Database-specific DDL generation (PostgreSQL JSONB, SQLite constraints)
- Zero SQL knowledge required for users
- Multi-database compatibility with optimized SQL generation

Universal Support: PostgreSQL and SQLite implementations with database-specific optimizations.
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from kailash.runtime import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime

# Kailash imports for async workflow pattern
from kailash.workflow.builder import WorkflowBuilder

logger = logging.getLogger(__name__)


def _execute_workflow_safe(workflow: WorkflowBuilder) -> Tuple[Dict[str, Any], str]:
    """
    Execute a workflow safely in any context (sync or async).

    ARCHITECTURE FIX (v0.10.11):
    This function now uses synchronous database connections (psycopg2/sqlite3)
    instead of async connections via AsyncLocalRuntime.

    The previous async_safe_run approach failed in Docker/FastAPI because:
    - async_safe_run creates a NEW event loop in a thread pool
    - Database connections are bound to the event loop they're created in
    - Connections created in thread pool's loop cannot be used in uvicorn's loop
    - This is a fundamental asyncio limitation, not a bug in the code

    The new sync approach works because:
    - DDL operations don't need async at all - they're one-time setup operations
    - Sync connections (psycopg2) have no event loop binding
    - No thread pools or event loop juggling needed

    Args:
        workflow: The WorkflowBuilder instance to execute

    Returns:
        Tuple of (results dict, run_id string)
    """
    from dataflow.migrations.sync_ddl_executor import SyncDDLExecutor

    # Extract the query and connection info from the workflow
    # Workflows in this module use a single AsyncSQLDatabaseNode pattern
    built_workflow = workflow.build()
    results = {}
    run_id = f"sync_ddl_{id(workflow)}"

    # FIX: built_workflow.nodes is a dict, not a list - iterate over values
    for node in built_workflow.nodes.values():
        node_id = node.node_id
        params = node.config  # FIX: NodeInstance uses .config, not .parameters

        # Extract connection string and query from node parameters
        connection_string = params.get("connection_string", "")
        query = params.get("query", "")

        if not connection_string or not query:
            logger.warning(
                f"Node {node_id} missing connection_string or query, skipping"
            )
            results[node_id] = {"result": [], "error": "Missing parameters"}
            continue

        # Use sync executor
        executor = SyncDDLExecutor(connection_string)

        # Determine if this is a DDL or query operation
        query_upper = query.strip().upper()
        is_ddl = any(
            query_upper.startswith(kw)
            for kw in ["CREATE", "ALTER", "DROP", "INSERT", "UPDATE", "DELETE"]
        )

        if is_ddl:
            result = executor.execute_ddl(query)
            if result.get("success"):
                results[node_id] = {"result": [], "success": True}
            else:
                results[node_id] = {"result": [], "error": result.get("error")}
        else:
            # Schema inspection queries (SELECT)
            result = executor.execute_query(query)
            if "error" in result:
                results[node_id] = {"result": [], "error": result.get("error")}
            else:
                results[node_id] = {"result": result.get("result", [])}

    return results, run_id


class MigrationType(Enum):
    """Types of database migrations."""

    CREATE_TABLE = "create_table"
    DROP_TABLE = "drop_table"
    ADD_COLUMN = "add_column"
    DROP_COLUMN = "drop_column"
    MODIFY_COLUMN = "modify_column"
    ADD_INDEX = "add_index"
    DROP_INDEX = "drop_index"
    ADD_CONSTRAINT = "add_constraint"
    DROP_CONSTRAINT = "drop_constraint"
    RENAME_TABLE = "rename_table"
    RENAME_COLUMN = "rename_column"


class MigrationStatus(Enum):
    """Status of migration operations."""

    PENDING = "pending"
    APPLIED = "applied"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class ColumnDefinition:
    """Definition of a database column."""

    name: str
    type: str
    nullable: bool = True
    default: Optional[Any] = None
    primary_key: bool = False
    foreign_key: Optional[str] = None
    unique: bool = False
    auto_increment: bool = False
    max_length: Optional[int] = None


@dataclass
class TableDefinition:
    """Definition of a database table."""

    name: str
    columns: List[ColumnDefinition] = field(default_factory=list)
    indexes: List[Dict[str, Any]] = field(default_factory=list)
    constraints: List[Dict[str, Any]] = field(default_factory=list)

    def get_column(self, name: str) -> Optional[ColumnDefinition]:
        """Get column by name."""
        for column in self.columns:
            if column.name == name:
                return column
        return None


@dataclass
class MigrationOperation:
    """A single migration operation."""

    operation_type: MigrationType
    table_name: str
    description: str
    sql_up: str
    sql_down: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self):
        return f"{self.operation_type.value}: {self.description}"


@dataclass
class Migration:
    """A complete migration with multiple operations."""

    version: str
    name: str
    operations: List[MigrationOperation] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    applied_at: Optional[datetime] = None
    status: MigrationStatus = MigrationStatus.PENDING
    checksum: Optional[str] = None

    def add_operation(self, operation: MigrationOperation):
        """Add an operation to this migration."""
        self.operations.append(operation)

    def generate_checksum(self) -> str:
        """Generate checksum for migration integrity."""
        import hashlib

        content = f"{self.version}:{self.name}:" + "".join(
            op.sql_up for op in self.operations
        )
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class SchemaDiff:
    """Difference between current and target schemas."""

    tables_to_create: List[TableDefinition] = field(default_factory=list)
    tables_to_drop: List[str] = field(default_factory=list)
    tables_to_modify: List[Tuple[str, TableDefinition, TableDefinition]] = field(
        default_factory=list
    )

    def has_changes(self) -> bool:
        """Check if there are any schema changes."""
        return bool(
            self.tables_to_create or self.tables_to_drop or self.tables_to_modify
        )

    def change_count(self) -> int:
        """Count total number of changes."""
        count = len(self.tables_to_create) + len(self.tables_to_drop)
        for _, _, _ in self.tables_to_modify:
            count += 1  # Each modified table counts as one change
        return count


class PostgreSQLSchemaInspector:
    """PostgreSQL schema inspector for DataFlow with advanced optimizations."""

    def __init__(self, connection_string):
        """
        Initialize PostgreSQL schema inspector.

        Automatically detects async context and uses appropriate runtime
        to prevent deadlocks in FastAPI, pytest async, and other async environments.
        """
        self.connection_string = connection_string

        # ✅ FIX: Detect async context and use appropriate runtime
        # This prevents deadlocks when DataFlow is used in FastAPI, pytest async, etc.
        try:
            asyncio.get_running_loop()
            # Running in async context - use AsyncLocalRuntime
            self.runtime = AsyncLocalRuntime()
            self._is_async = True
            logger.debug(
                "PostgreSQLSchemaInspector: Detected async context, using AsyncLocalRuntime"
            )
        except RuntimeError:
            # No event loop - use sync LocalRuntime
            self.runtime = LocalRuntime()
            self._is_async = False
            logger.debug(
                "PostgreSQLSchemaInspector: Detected sync context, using LocalRuntime"
            )

        # Default to PostgreSQL dialect for SQL databases
        self.dialect = "postgresql"

        # Detect database type for AsyncSQLDatabaseNode
        from ..adapters.connection_parser import ConnectionParser

        self.database_type = ConnectionParser.detect_database_type(connection_string)

    async def get_current_schema(self) -> Dict[str, TableDefinition]:
        """Get current PostgreSQL schema with optimizations."""
        return await self._get_postgresql_schema()

    async def _get_postgresql_schema(self) -> Dict[str, TableDefinition]:
        """Get PostgreSQL schema information with advanced optimizations."""
        tables = {}

        # PostgreSQL-optimized query with JSONB and advanced type detection
        query = """
        SELECT
            t.table_name,
            c.column_name,
            c.data_type,
            c.is_nullable,
            c.column_default,
            c.character_maximum_length,
            CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END as is_primary_key,
            -- PostgreSQL-specific type information
            c.udt_name,
            CASE WHEN c.data_type = 'ARRAY' THEN 'ARRAY' ELSE c.data_type END as pg_type
        FROM information_schema.tables t
        LEFT JOIN information_schema.columns c ON t.table_name = c.table_name
        LEFT JOIN (
            SELECT ku.column_name, ku.table_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage ku ON tc.constraint_name = ku.constraint_name
            WHERE tc.constraint_type = 'PRIMARY KEY'
        ) pk ON c.table_name = pk.table_name AND c.column_name = pk.column_name
        WHERE t.table_schema = 'public'
          AND t.table_type = 'BASE TABLE'
          AND t.table_name NOT LIKE 'dataflow_%'
        ORDER BY t.table_name, c.ordinal_position
        """

        try:
            # Use WorkflowBuilder pattern instead of direct connection
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "get_schema",
                {
                    "connection_string": self.connection_string,
                    "database_type": self.database_type,
                    "query": query,
                    "validate_queries": False,
                },
            )

            # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
            results, _ = _execute_workflow_safe(workflow)

            # Defensive error checking - handle both dict and other result formats
            schema_result = results.get("get_schema")
            if not schema_result:
                logger.error("Failed to get PostgreSQL schema: No result returned")
                return {}

            # Check if result is a dict and contains error
            if isinstance(schema_result, dict) and schema_result.get("error"):
                error_msg = schema_result.get("error", "Unknown error")
                logger.error(f"Failed to get PostgreSQL schema: {error_msg}")
                return {}

            rows = results["get_schema"].get("result", [])

            current_table = None
            for row in rows:
                # Skip empty or malformed rows
                if not row or len(row) < 7:
                    continue

                table_name = row[0]
                if table_name != current_table:
                    tables[table_name] = TableDefinition(name=table_name)
                    current_table = table_name

                if row[1]:  # column_name exists
                    # Use PostgreSQL-specific type information
                    # pg_type is at index 8, but fall back to data_type at index 2 if not available
                    pg_type = row[8] if len(row) > 8 else row[2]

                    column = ColumnDefinition(
                        name=row[1],
                        type=pg_type,
                        nullable=row[3] == "YES",
                        default=row[4],
                        max_length=row[5],
                        primary_key=row[6],
                    )
                    tables[table_name].columns.append(column)

            # Get PostgreSQL indexes for each table with optimization
            for table_name in tables:
                await self._get_postgresql_indexes(table_name, tables[table_name])

            return tables

        except Exception as e:
            logger.error(f"Failed to get PostgreSQL schema: {e}")
            return {}

    async def _get_postgresql_indexes(
        self, table_name: str, table_def: TableDefinition
    ):
        """Get PostgreSQL indexes for a table."""
        query = """
        SELECT
            i.relname as index_name,
            array_agg(a.attname ORDER BY c.ordinality) as column_names,
            ix.indisunique as is_unique
        FROM pg_index ix
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_class t ON t.oid = ix.indrelid
        JOIN unnest(ix.indkey) WITH ORDINALITY AS c(attnum, ordinality) ON true
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = c.attnum
        WHERE t.relname = $1
          AND i.relname NOT LIKE '%_pkey'
        GROUP BY i.relname, ix.indisunique
        """

        try:
            # Use WorkflowBuilder pattern for indexes query
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                f"get_indexes_{table_name}",
                {
                    "connection_string": self.connection_string,
                    "database_type": self.database_type,
                    "query": query,
                    "params": [table_name],
                    "validate_queries": False,
                },
            )

            # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
            results, _ = _execute_workflow_safe(workflow)
            node_id = f"get_indexes_{table_name}"

            # Defensive error checking - handle both dict and other result formats
            node_result = results.get(node_id)
            if node_result and not (
                isinstance(node_result, dict) and node_result.get("error")
            ):
                rows = results[node_id].get("result", [])
                for row in rows:
                    index_info = {"name": row[0], "columns": row[1], "unique": row[2]}
                    table_def.indexes.append(index_info)
        except Exception as e:
            logger.warning(f"Failed to get indexes for table {table_name}: {e}")
            # Don't fail the whole schema discovery for index issues

    # PostgreSQL-optimized implementation
    # SQLite and MongoDB have separate adapter implementations

    def compare_schemas(
        self,
        current_schema: Dict[str, TableDefinition],
        target_schema: Dict[str, TableDefinition],
        existing_schema_mode: bool = False,
    ) -> SchemaDiff:
        """Compare current and target schemas to generate diff with smart compatibility."""
        from ..core.schema_comparator import compare_schemas_unified

        # Use unified schema comparator with full schema mode (non-incremental)
        unified_result = compare_schemas_unified(
            current_schema,
            target_schema,
            incremental_mode=False,  # AutoMigrationSystem wants full comparison
            compatibility_check=True,
        )

        # Convert UnifiedSchemaComparisonResult back to SchemaDiff for backward compatibility
        diff = SchemaDiff()
        diff.tables_to_create = unified_result.tables_to_create
        diff.tables_to_drop = unified_result.tables_to_drop
        diff.tables_to_modify = unified_result.tables_to_modify

        return diff

    def _schemas_are_compatible(
        self, db_table: TableDefinition, model_table: TableDefinition
    ) -> bool:
        """
        Check if a database table is compatible with a model table.

        Compatible means the database has all required model fields,
        even if it has additional fields (legacy support).
        """
        db_columns = {col.name: col for col in db_table.columns}

        for model_col in model_table.columns:
            # Skip auto-generated fields
            if model_col.name in ["id", "created_at", "updated_at"]:
                continue

            # Check if required field exists in database
            if model_col.name not in db_columns:
                return False

            # Check type compatibility
            db_col = db_columns[model_col.name]
            if not self._types_are_compatible(model_col.type, db_col.type):
                return False

        return True

    def _types_are_compatible(self, model_type: str, db_type: str) -> bool:
        """
        Check if model type is compatible with database type.

        This allows for common type variations and PostgreSQL specifics.
        """
        # Normalize types for comparison
        model_type = model_type.lower()
        db_type = db_type.lower()

        # Type compatibility mappings
        type_mappings = {
            "str": ["varchar", "text", "character varying", "char"],
            "int": ["integer", "bigint", "serial", "bigserial", "int4", "int8"],
            "float": [
                "decimal",
                "numeric",
                "real",
                "double precision",
                "float4",
                "float8",
            ],
            "bool": ["boolean", "bool"],
            "datetime": [
                "timestamp",
                "timestamptz",
                "timestamp with time zone",
                "timestamp without time zone",
            ],
            "date": ["date"],
            "time": ["time", "timetz"],
            "json": ["json", "jsonb"],
            "uuid": ["uuid"],
            "bytes": ["bytea"],
        }

        # Check direct match first
        if model_type == db_type:
            return True

        # Check mapped compatibility
        for mapped_type, compatible_types in type_mappings.items():
            if model_type == mapped_type:
                return any(compat in db_type for compat in compatible_types)

        # Handle special cases like varchar(255)
        if "varchar" in db_type and model_type == "str":
            return True

        return False

    def _tables_differ(self, current: TableDefinition, target: TableDefinition) -> bool:
        """Check if two table definitions differ."""
        # Compare columns
        current_cols = {col.name: col for col in current.columns}
        target_cols = {col.name: col for col in target.columns}

        if set(current_cols.keys()) != set(target_cols.keys()):
            return True

        # Compare column definitions
        for col_name in current_cols:
            current_col = current_cols[col_name]
            target_col = target_cols[col_name]

            if (
                current_col.type != target_col.type
                or current_col.nullable != target_col.nullable
                or current_col.primary_key != target_col.primary_key
                or current_col.default != target_col.default
            ):
                return True

        return False


class PostgreSQLMigrationGenerator:
    """PostgreSQL migration generator for DataFlow with advanced features."""

    def __init__(self):
        self.dialect = "postgresql"

    def generate_migration(self, diff: SchemaDiff, name: str = None) -> Migration:
        """Generate migration from schema diff."""
        if not name:
            name = f"auto_migration_{int(time.time())}"

        version = datetime.now().strftime("%Y%m%d_%H%M%S")
        migration = Migration(version=version, name=name)

        # Generate operations for new tables
        for table in diff.tables_to_create:
            operation = self._generate_create_table_operation(table)
            migration.add_operation(operation)

        # Generate operations for dropped tables
        for table_name in diff.tables_to_drop:
            operation = self._generate_drop_table_operation(table_name)
            migration.add_operation(operation)

        # Generate operations for modified tables
        for table_name, current_table, target_table in diff.tables_to_modify:
            operations = self._generate_modify_table_operations(
                table_name, current_table, target_table
            )
            for operation in operations:
                migration.add_operation(operation)

        migration.checksum = migration.generate_checksum()
        return migration

    def _generate_create_table_operation(
        self, table: TableDefinition
    ) -> MigrationOperation:
        """Generate CREATE TABLE operation."""
        sql_up = self._create_table_sql(table)
        sql_down = f"DROP TABLE IF EXISTS {table.name};"

        return MigrationOperation(
            operation_type=MigrationType.CREATE_TABLE,
            table_name=table.name,
            description=f"Create table '{table.name}' with {len(table.columns)} columns",
            sql_up=sql_up,
            sql_down=sql_down,
            metadata={"columns": len(table.columns)},
        )

    def _generate_drop_table_operation(self, table_name: str) -> MigrationOperation:
        """Generate DROP TABLE operation."""
        sql_up = f"DROP TABLE IF EXISTS {table_name};"
        sql_down = f"-- Cannot automatically recreate dropped table: {table_name}"

        return MigrationOperation(
            operation_type=MigrationType.DROP_TABLE,
            table_name=table_name,
            description=f"Drop table '{table_name}'",
            sql_up=sql_up,
            sql_down=sql_down,
            metadata={"warning": "Cannot automatically rollback table drops"},
        )

    def _generate_modify_table_operations(
        self,
        table_name: str,
        current_table: TableDefinition,
        target_table: TableDefinition,
    ) -> List[MigrationOperation]:
        """Generate operations for table modifications."""
        operations = []

        current_cols = {col.name: col for col in current_table.columns}
        target_cols = {col.name: col for col in target_table.columns}

        # Add new columns
        for col_name in set(target_cols.keys()) - set(current_cols.keys()):
            column = target_cols[col_name]
            operation = self._generate_add_column_operation(table_name, column)
            operations.append(operation)

        # Drop columns
        for col_name in set(current_cols.keys()) - set(target_cols.keys()):
            operation = self._generate_drop_column_operation(table_name, col_name)
            operations.append(operation)

        # Modify existing columns
        for col_name in set(current_cols.keys()) & set(target_cols.keys()):
            current_col = current_cols[col_name]
            target_col = target_cols[col_name]

            if self._columns_differ(current_col, target_col):
                operation = self._generate_modify_column_operation(
                    table_name, current_col, target_col
                )
                operations.append(operation)

        return operations

    def _generate_add_column_operation(
        self, table_name: str, column: ColumnDefinition
    ) -> MigrationOperation:
        """Generate ADD COLUMN operation."""
        column_sql = self._column_definition_sql(column)
        sql_up = f"ALTER TABLE {table_name} ADD COLUMN {column_sql};"
        sql_down = f"ALTER TABLE {table_name} DROP COLUMN {column.name};"

        return MigrationOperation(
            operation_type=MigrationType.ADD_COLUMN,
            table_name=table_name,
            description=f"Add column '{column.name}' to table '{table_name}'",
            sql_up=sql_up,
            sql_down=sql_down,
            metadata={"column_name": column.name, "column_type": column.type},
        )

    def _generate_drop_column_operation(
        self, table_name: str, column_name: str
    ) -> MigrationOperation:
        """Generate DROP COLUMN operation."""
        sql_up = f"ALTER TABLE {table_name} DROP COLUMN {column_name};"
        sql_down = f"-- Cannot automatically recreate dropped column: {column_name}"

        return MigrationOperation(
            operation_type=MigrationType.DROP_COLUMN,
            table_name=table_name,
            description=f"Drop column '{column_name}' from table '{table_name}'",
            sql_up=sql_up,
            sql_down=sql_down,
            metadata={
                "column_name": column_name,
                "warning": "Cannot automatically rollback",
            },
        )

    def _generate_modify_column_operation(
        self,
        table_name: str,
        current_col: ColumnDefinition,
        target_col: ColumnDefinition,
    ) -> MigrationOperation:
        """Generate PostgreSQL MODIFY COLUMN operation with advanced features."""
        # PostgreSQL-specific ALTER COLUMN with advanced type handling
        sql_up = self._postgresql_modify_column_sql(table_name, current_col, target_col)
        sql_down = self._postgresql_modify_column_sql(
            table_name, target_col, current_col
        )

        return MigrationOperation(
            operation_type=MigrationType.MODIFY_COLUMN,
            table_name=table_name,
            description=f"Modify PostgreSQL column '{current_col.name}' in table '{table_name}'",
            sql_up=sql_up,
            sql_down=sql_down,
            metadata={
                "column_name": current_col.name,
                "old_type": current_col.type,
                "new_type": target_col.type,
                "postgresql_optimized": True,
            },
        )

    def _create_table_sql(self, table: TableDefinition) -> str:
        """Generate CREATE TABLE SQL."""
        columns_sql = []
        for column in table.columns:
            columns_sql.append(self._column_definition_sql(column))

        sql = f"CREATE TABLE {table.name} (\n"
        sql += ",\n".join(f"    {col_sql}" for col_sql in columns_sql)
        sql += "\n);"

        return sql

    def _column_definition_sql(self, column: ColumnDefinition) -> str:
        """Generate column definition SQL."""
        parts = [column.name, column.type]

        if column.max_length and column.type.upper() in ("VARCHAR", "CHAR"):
            parts[1] = f"{column.type}({column.max_length})"

        # Check for auto_increment first, as SERIAL includes NOT NULL and a default
        if column.auto_increment:
            # PostgreSQL SERIAL types already include NOT NULL and DEFAULT nextval()
            parts[1] = "SERIAL"
            # Don't add NOT NULL or DEFAULT for SERIAL columns
        else:
            if not column.nullable:
                parts.append("NOT NULL")

            if column.default is not None:
                if isinstance(column.default, str):
                    # Special handling for SQL functions
                    if column.default.upper() in (
                        "CURRENT_TIMESTAMP",
                        "CURRENT_DATE",
                        "CURRENT_TIME",
                        "NOW()",
                    ):
                        parts.append(f"DEFAULT {column.default}")
                    else:
                        parts.append(f"DEFAULT '{column.default}'")
                else:
                    parts.append(f"DEFAULT {column.default}")

        if column.primary_key:
            parts.append("PRIMARY KEY")

        if column.unique:
            parts.append("UNIQUE")

        return " ".join(parts)

    def _postgresql_modify_column_sql(
        self,
        table_name: str,
        current_col: ColumnDefinition,
        target_col: ColumnDefinition,
    ) -> str:
        """Generate PostgreSQL-specific ALTER COLUMN SQL."""
        statements = []

        # Change data type
        if current_col.type != target_col.type:
            statements.append(
                f"ALTER TABLE {table_name} ALTER COLUMN {current_col.name} TYPE {target_col.type};"
            )

        # Change nullable
        if current_col.nullable != target_col.nullable:
            if target_col.nullable:
                statements.append(
                    f"ALTER TABLE {table_name} ALTER COLUMN {current_col.name} DROP NOT NULL;"
                )
            else:
                statements.append(
                    f"ALTER TABLE {table_name} ALTER COLUMN {current_col.name} SET NOT NULL;"
                )

        # Change default
        if current_col.default != target_col.default:
            if target_col.default is not None:
                default_val = (
                    f"'{target_col.default}'"
                    if isinstance(target_col.default, str)
                    else target_col.default
                )
                statements.append(
                    f"ALTER TABLE {table_name} ALTER COLUMN {current_col.name} SET DEFAULT {default_val};"
                )
            else:
                statements.append(
                    f"ALTER TABLE {table_name} ALTER COLUMN {current_col.name} DROP DEFAULT;"
                )

        return "\n".join(statements)

    def _columns_differ(
        self, current: ColumnDefinition, target: ColumnDefinition
    ) -> bool:
        """Check if column definitions differ."""
        return (
            current.type != target.type
            or current.nullable != target.nullable
            or current.default != target.default
            or current.primary_key != target.primary_key
            or current.unique != target.unique
        )

    def _schemas_are_compatible(
        self, db_table: TableDefinition, model_table: TableDefinition
    ) -> bool:
        """
        Check if database schema is compatible with model schema.

        Compatible means:
        - All model fields exist in database (ignoring auto-generated fields)
        - Types are compatible (not necessarily identical)
        - Constraints are satisfied

        This is the KEY to solving the multi-app and existing database scenarios!
        """
        db_columns = {col.name: col for col in db_table.columns}
        model_columns = {col.name: col for col in model_table.columns}

        # Check each model column exists in database with compatible type
        for col_name, model_col in model_columns.items():
            # Skip auto-generated fields
            if col_name in ["id", "created_at", "updated_at"]:
                continue

            # Check if column exists in database
            if col_name not in db_columns:
                logger.debug(f"Column '{col_name}' not found in database")
                return False

            db_col = db_columns[col_name]

            # Check type compatibility
            if not self._types_are_compatible(model_col.type, db_col.type):
                logger.debug(
                    f"Column '{col_name}' types incompatible: "
                    f"model={model_col.type} vs db={db_col.type}"
                )
                return False

            # Check nullable compatibility
            # Model requires NOT NULL but DB allows NULL = incompatible
            if not model_col.nullable and db_col.nullable:
                logger.debug(f"Column '{col_name}' nullable mismatch")
                return False

        # All model columns are satisfied by database
        return True

    def _types_are_compatible(self, model_type: str, db_type: str) -> bool:
        """
        Check if types are compatible (not necessarily identical).

        Handles common variations like:
        - str → varchar, text, character varying
        - int → integer, bigint, smallint
        - float → decimal, numeric, real
        - datetime → timestamp with/without timezone
        """
        # Normalize types to lowercase
        model_type_lower = model_type.lower()
        db_type_lower = db_type.lower()

        # Direct match
        if model_type_lower == db_type_lower:
            return True

        # Type compatibility mappings
        compatible_types = {
            # Python type → Compatible database types
            "str": ["varchar", "text", "character varying", "char"],
            "string": ["varchar", "text", "character varying", "char"],
            "int": ["integer", "bigint", "smallint", "serial", "bigserial"],
            "integer": ["integer", "bigint", "smallint", "serial", "bigserial"],
            "float": ["decimal", "numeric", "real", "double precision", "float"],
            "bool": ["boolean", "bool"],
            "boolean": ["boolean", "bool"],
            "datetime": [
                "timestamp",
                "timestamptz",
                "timestamp with time zone",
                "timestamp without time zone",
            ],
            "date": ["date"],
            "time": ["time", "timetz", "time with time zone", "time without time zone"],
            "json": ["json", "jsonb"],
            "dict": ["json", "jsonb"],
            "list": ["json", "jsonb", "array"],
            "uuid": ["uuid"],
            "bytes": ["bytea"],
        }

        # Check compatibility
        for python_type, db_types in compatible_types.items():
            if model_type_lower == python_type:
                # Check if database type starts with any compatible type
                return any(db_type_lower.startswith(db_t) for db_t in db_types)

        # Check reverse mapping (database type → Python type)
        for python_type, db_types in compatible_types.items():
            if any(db_type_lower.startswith(db_t) for db_t in db_types):
                return model_type_lower == python_type

        return False


class SQLiteSchemaInspector:
    """SQLite schema inspector for DataFlow."""

    def __init__(self, connection_string):
        """
        Initialize SQLite schema inspector.

        Automatically detects async context and uses appropriate runtime
        to prevent deadlocks in FastAPI, pytest async, and other async environments.
        """
        self.connection_string = connection_string

        # ✅ FIX: Detect async context and use appropriate runtime
        # This prevents deadlocks when DataFlow is used in FastAPI, pytest async, etc.
        try:
            asyncio.get_running_loop()
            # Running in async context - use AsyncLocalRuntime
            self.runtime = AsyncLocalRuntime()
            self._is_async = True
            logger.debug(
                "SQLiteSchemaInspector: Detected async context, using AsyncLocalRuntime"
            )
        except RuntimeError:
            # No event loop - use sync LocalRuntime
            self.runtime = LocalRuntime()
            self._is_async = False
            logger.debug(
                "SQLiteSchemaInspector: Detected sync context, using LocalRuntime"
            )

        self.dialect = "sqlite"

        # Detect database type for AsyncSQLDatabaseNode compatibility
        from ..adapters.connection_parser import ConnectionParser

        self.database_type = ConnectionParser.detect_database_type(connection_string)

    async def get_current_schema(self) -> Dict[str, TableDefinition]:
        """Get current SQLite schema."""
        return await self._get_sqlite_schema()

    async def _get_sqlite_schema(self) -> Dict[str, TableDefinition]:
        """Get SQLite schema information."""
        tables = {}

        # SQLite query to get all tables and their column information
        query = """
        SELECT
            m.name as table_name,
            p.cid as column_order,
            p.name as column_name,
            p.type as data_type,
            p."notnull" as not_null,
            p.dflt_value as column_default,
            p.pk as is_primary_key
        FROM sqlite_master m
        LEFT JOIN pragma_table_info(m.name) p ON 1=1
        WHERE m.type = 'table'
          AND m.name NOT LIKE 'sqlite_%'
          AND m.name NOT LIKE 'dataflow_%'
        ORDER BY m.name, p.cid
        """

        try:
            # Use WorkflowBuilder pattern
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "get_schema",
                {
                    "connection_string": self.connection_string,
                    "database_type": self.database_type,
                    "query": query,
                    "validate_queries": False,
                },
            )

            # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
            results, _ = _execute_workflow_safe(workflow)

            # Defensive error checking - handle both dict and other result formats
            schema_result = results.get("get_schema")
            if not schema_result:
                logger.error("Failed to get SQLite schema: No result returned")
                return {}

            # Check if result is a dict and contains error
            if isinstance(schema_result, dict) and schema_result.get("error"):
                error_msg = schema_result.get("error", "Unknown error")
                logger.error(f"Failed to get SQLite schema: {error_msg}")
                return {}

            # Handle different result formats from AsyncSQLDatabaseNode
            result_data = results["get_schema"].get("result", [])

            # Check if result has data field (newer format)
            if isinstance(result_data, dict) and "data" in result_data:
                rows = result_data["data"]
            else:
                rows = result_data

            current_table = None
            for row in rows:
                # Skip metadata rows that don't have actual data
                if isinstance(row, dict):
                    # Dict format from newer AsyncSQLDatabaseNode
                    table_name = row.get("table_name")
                    column_name = row.get("column_name")
                    data_type = row.get("data_type")
                    not_null = row.get("not_null")
                    column_default = row.get("column_default")
                    is_primary_key = row.get("is_primary_key")

                    # Skip invalid rows
                    if not table_name or table_name in ["data", "query", "format"]:
                        continue

                else:
                    # List/tuple format
                    if not isinstance(row, (list, tuple)) or len(row) < 7:
                        logger.debug(f"Skipping invalid row: {row}")
                        continue
                    table_name = row[0]
                    column_name = row[2]
                    data_type = row[3]
                    not_null = row[4]
                    column_default = row[5]
                    is_primary_key = row[6]

                if table_name and table_name != current_table:
                    tables[table_name] = TableDefinition(name=table_name)
                    current_table = table_name

                if column_name:  # column_name exists
                    column = ColumnDefinition(
                        name=column_name,
                        type=self._normalize_sqlite_type(data_type),
                        nullable=not bool(not_null),  # not_null -> nullable
                        default=column_default,
                        primary_key=bool(is_primary_key),
                    )
                    tables[table_name].columns.append(column)

            # Get SQLite indexes for each table
            for table_name in tables:
                await self._get_sqlite_indexes(table_name, tables[table_name])

            return tables

        except Exception as e:
            logger.error(f"Failed to get SQLite schema: {e}")
            return {}

    def _normalize_sqlite_type(self, sqlite_type: str) -> str:
        """Normalize SQLite type to standard form."""
        if not sqlite_type:
            return "text"  # SQLite default affinity

        sqlite_type = sqlite_type.lower()

        # SQLite type affinity mapping
        if "int" in sqlite_type:
            return "integer"
        elif any(t in sqlite_type for t in ["char", "text", "clob"]):
            return "text"
        elif "blob" in sqlite_type:
            return "blob"
        elif any(t in sqlite_type for t in ["real", "floa", "doub"]):
            return "real"
        else:
            return "numeric"

    async def _get_sqlite_indexes(self, table_name: str, table_def: TableDefinition):
        """Get SQLite indexes for a table."""
        query = """
        SELECT
            il.name as index_name,
            ii.name as column_name,
            il."unique" as is_unique
        FROM sqlite_master m
        LEFT JOIN pragma_index_list(m.name) il ON 1=1
        LEFT JOIN pragma_index_info(il.name) ii ON 1=1
        WHERE m.name = ? AND m.type = 'table'
          AND il.name NOT LIKE 'sqlite_%'
        ORDER BY il.name, ii.seqno
        """

        try:
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                f"get_indexes_{table_name}",
                {
                    "connection_string": self.connection_string,
                    "database_type": self.database_type,
                    "query": query,
                    "params": [table_name],
                    "validate_queries": False,
                },
            )

            # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
            results, _ = _execute_workflow_safe(workflow)
            node_id = f"get_indexes_{table_name}"

            # Defensive error checking - handle both dict and other result formats
            node_result = results.get(node_id)
            if node_result and not (
                isinstance(node_result, dict) and node_result.get("error")
            ):
                rows = results[node_id].get("result", [])

                # Group by index name
                indexes = {}
                for row in rows:
                    if row[0]:  # index_name exists
                        index_name = row[0]
                        if index_name not in indexes:
                            indexes[index_name] = {
                                "name": index_name,
                                "columns": [],
                                "unique": bool(row[2]),
                            }
                        if row[1]:  # column_name exists
                            indexes[index_name]["columns"].append(row[1])

                # Add to table definition
                for index_info in indexes.values():
                    table_def.indexes.append(index_info)

        except Exception as e:
            logger.warning(f"Failed to get indexes for table {table_name}: {e}")

    def compare_schemas(
        self,
        current_schema: Dict[str, TableDefinition],
        target_schema: Dict[str, TableDefinition],
        existing_schema_mode: bool = False,
    ) -> SchemaDiff:
        """Compare current and target schemas to generate diff."""
        from ..core.schema_comparator import compare_schemas_unified

        # Use unified schema comparator
        unified_result = compare_schemas_unified(
            current_schema,
            target_schema,
            incremental_mode=False,
            compatibility_check=True,
        )

        # Convert to SchemaDiff for backward compatibility
        diff = SchemaDiff()
        diff.tables_to_create = unified_result.tables_to_create
        diff.tables_to_drop = unified_result.tables_to_drop
        diff.tables_to_modify = unified_result.tables_to_modify

        return diff


class SQLiteMigrationGenerator:
    """SQLite migration generator for DataFlow."""

    def __init__(self):
        self.dialect = "sqlite"

    def generate_migration(self, diff: SchemaDiff, name: str = None) -> Migration:
        """Generate migration from schema diff."""
        if not name:
            name = f"auto_migration_{int(time.time())}"

        version = datetime.now().strftime("%Y%m%d_%H%M%S")
        migration = Migration(version=version, name=name)

        # Generate operations for new tables
        for table in diff.tables_to_create:
            operation = self._generate_create_table_operation(table)
            migration.add_operation(operation)

        # Generate operations for dropped tables
        for table_name in diff.tables_to_drop:
            operation = self._generate_drop_table_operation(table_name)
            migration.add_operation(operation)

        # Generate operations for modified tables
        for table_name, current_table, target_table in diff.tables_to_modify:
            operations = self._generate_modify_table_operations(
                table_name, current_table, target_table
            )
            for operation in operations:
                migration.add_operation(operation)

        migration.checksum = migration.generate_checksum()
        return migration

    def _generate_create_table_operation(
        self, table: TableDefinition
    ) -> MigrationOperation:
        """Generate CREATE TABLE operation for SQLite."""
        sql_up = self._create_table_sql(table)
        sql_down = f"DROP TABLE IF EXISTS {table.name};"

        return MigrationOperation(
            operation_type=MigrationType.CREATE_TABLE,
            table_name=table.name,
            description=f"Create table '{table.name}' with {len(table.columns)} columns",
            sql_up=sql_up,
            sql_down=sql_down,
            metadata={"columns": len(table.columns), "database": "sqlite"},
        )

    def _generate_drop_table_operation(self, table_name: str) -> MigrationOperation:
        """Generate DROP TABLE operation for SQLite."""
        sql_up = f"DROP TABLE IF EXISTS {table_name};"
        sql_down = f"-- Cannot automatically recreate dropped table: {table_name}"

        return MigrationOperation(
            operation_type=MigrationType.DROP_TABLE,
            table_name=table_name,
            description=f"Drop table '{table_name}'",
            sql_up=sql_up,
            sql_down=sql_down,
            metadata={
                "warning": "Cannot automatically rollback table drops",
                "database": "sqlite",
            },
        )

    def _generate_modify_table_operations(
        self,
        table_name: str,
        current_table: TableDefinition,
        target_table: TableDefinition,
    ) -> List[MigrationOperation]:
        """Generate operations for table modifications (SQLite-specific)."""
        operations = []

        current_cols = {col.name: col for col in current_table.columns}
        target_cols = {col.name: col for col in target_table.columns}

        # Add new columns (SQLite supports this)
        for col_name in set(target_cols.keys()) - set(current_cols.keys()):
            column = target_cols[col_name]
            operation = self._generate_add_column_operation(table_name, column)
            operations.append(operation)

        # For operations SQLite doesn't support, create warning operations
        dropped_cols = set(current_cols.keys()) - set(target_cols.keys())
        if dropped_cols:
            operation = MigrationOperation(
                operation_type=MigrationType.DROP_COLUMN,
                table_name=table_name,
                description=f"SQLite does not support DROP COLUMN for: {', '.join(dropped_cols)}",
                sql_up=f"-- SQLite limitation: Cannot drop columns {', '.join(dropped_cols)} from {table_name}",
                sql_down="-- No rollback needed",
                metadata={
                    "sqlite_limitation": True,
                    "unsupported_operation": "DROP_COLUMN",
                    "columns": list(dropped_cols),
                },
            )
            operations.append(operation)

        # Check for column modifications (SQLite limitations)
        for col_name in set(current_cols.keys()) & set(target_cols.keys()):
            current_col = current_cols[col_name]
            target_col = target_cols[col_name]

            if self._columns_differ(current_col, target_col):
                operation = MigrationOperation(
                    operation_type=MigrationType.MODIFY_COLUMN,
                    table_name=table_name,
                    description=f"SQLite does not support ALTER COLUMN for: {col_name}",
                    sql_up=f"-- SQLite limitation: Cannot modify column {col_name} in {table_name}",
                    sql_down="-- No rollback needed",
                    metadata={
                        "sqlite_limitation": True,
                        "unsupported_operation": "ALTER_COLUMN",
                        "column": col_name,
                        "current_type": current_col.type,
                        "target_type": target_col.type,
                    },
                )
                operations.append(operation)

        return operations

    def _generate_add_column_operation(
        self, table_name: str, column: ColumnDefinition
    ) -> MigrationOperation:
        """Generate ADD COLUMN operation for SQLite."""
        column_sql = self._column_definition_sql(column)
        sql_up = f"ALTER TABLE {table_name} ADD COLUMN {column_sql};"
        sql_down = f"-- SQLite does not support DROP COLUMN: {column.name}"

        return MigrationOperation(
            operation_type=MigrationType.ADD_COLUMN,
            table_name=table_name,
            description=f"Add column '{column.name}' to table '{table_name}'",
            sql_up=sql_up,
            sql_down=sql_down,
            metadata={
                "column_name": column.name,
                "column_type": column.type,
                "database": "sqlite",
            },
        )

    def _create_table_sql(self, table: TableDefinition) -> str:
        """Generate CREATE TABLE SQL for SQLite."""
        columns_sql = []
        for column in table.columns:
            columns_sql.append(self._column_definition_sql(column))

        sql = f"CREATE TABLE {table.name} (\n"
        sql += ",\n".join(f"    {col_sql}" for col_sql in columns_sql)
        sql += "\n);"

        return sql

    def _column_definition_sql(self, column: ColumnDefinition) -> str:
        """Generate column definition SQL for SQLite."""
        parts = [column.name, self._map_type_to_sqlite(column.type)]

        if column.primary_key:
            parts.append("PRIMARY KEY")
            if column.type.lower() in ["integer", "int"]:
                parts.append("AUTOINCREMENT")

        if not column.nullable:
            parts.append("NOT NULL")

        # Skip default for AUTOINCREMENT columns or PostgreSQL-style defaults
        is_autoincrement = column.primary_key and column.type.lower() in [
            "integer",
            "int",
        ]
        is_nextval = column.default == "nextval"

        if column.default is not None and not is_autoincrement and not is_nextval:
            if isinstance(column.default, str):
                # Special handling for SQL functions
                if column.default.upper() in (
                    "CURRENT_TIMESTAMP",
                    "CURRENT_DATE",
                    "CURRENT_TIME",
                    "NOW()",
                ):
                    parts.append(f"DEFAULT {column.default}")
                else:
                    parts.append(f"DEFAULT '{column.default}'")
            else:
                parts.append(f"DEFAULT {column.default}")

        if column.unique and not column.primary_key:
            parts.append("UNIQUE")

        return " ".join(parts)

    def _map_type_to_sqlite(self, column_type: str) -> str:
        """Map column type to SQLite type."""
        type_mapping = {
            "varchar": "TEXT",
            "char": "TEXT",
            "text": "TEXT",
            "string": "TEXT",
            "str": "TEXT",
            "integer": "INTEGER",
            "int": "INTEGER",
            "bigint": "INTEGER",
            "smallint": "INTEGER",
            "serial": "INTEGER",
            "bigserial": "INTEGER",
            "float": "REAL",
            "real": "REAL",
            "double": "REAL",
            "decimal": "NUMERIC",
            "numeric": "NUMERIC",
            "boolean": "INTEGER",  # SQLite doesn't have native boolean
            "bool": "INTEGER",
            "timestamp": "TEXT",  # SQLite stores dates as text
            "timestamptz": "TEXT",
            "datetime": "TEXT",
            "date": "TEXT",
            "time": "TEXT",
            "json": "TEXT",  # SQLite can store JSON as TEXT
            "jsonb": "TEXT",
            "uuid": "TEXT",
            "bytes": "BLOB",
            "bytea": "BLOB",
        }
        return type_mapping.get(column_type.lower(), "TEXT")

    def _columns_differ(
        self, current: ColumnDefinition, target: ColumnDefinition
    ) -> bool:
        """Check if column definitions differ."""
        return (
            current.type != target.type
            or current.nullable != target.nullable
            or current.default != target.default
            or current.primary_key != target.primary_key
            or current.unique != target.unique
        )


class AutoMigrationSystem:
    """
    Universal auto-migration system for DataFlow.

    Orchestrates schema comparison, migration generation, and execution
    with visual confirmation and advanced features for PostgreSQL and SQLite.
    """

    def __init__(
        self,
        connection_string: str,
        dialect: str = "postgresql",
        migrations_dir: str = "migrations",
        dataflow_instance=None,
        lock_timeout: int = 30,
    ):
        """
        Initialize Auto Migration System.

        Automatically detects async context and uses appropriate runtime
        to prevent deadlocks in FastAPI, pytest async, and other async environments.
        """
        self.connection_string = connection_string

        # ✅ FIX: Detect async context and use appropriate runtime
        # This prevents deadlocks when DataFlow is used in FastAPI, pytest async, etc.
        try:
            asyncio.get_running_loop()
            # Running in async context - use AsyncLocalRuntime
            self.runtime = AsyncLocalRuntime()
            self._is_async = True
            logger.debug(
                "AutoMigrationSystem: Detected async context, using AsyncLocalRuntime"
            )
        except RuntimeError:
            # No event loop - use sync LocalRuntime
            self.runtime = LocalRuntime()
            self._is_async = False
            logger.debug(
                "AutoMigrationSystem: Detected sync context, using LocalRuntime"
            )

        # Detect database type from connection string
        self.dialect = self._detect_database_type(connection_string)
        self.database_type = (
            self.dialect
        )  # Set database_type for AsyncSQLDatabaseNode compatibility

        # Support SQLite and PostgreSQL - no restrictions
        if self.dialect not in ["postgresql", "sqlite"]:
            logger.warning(
                f"DataFlow currently supports PostgreSQL and SQLite. Detected dialect '{self.dialect}' may need additional support."
            )
            # Don't default to PostgreSQL - use detected type

        # Initialize migration lock manager if DataFlow instance is provided
        self._dataflow_instance = dataflow_instance
        self._migration_lock_manager = None
        self._connection_adapter = None

        if dataflow_instance:
            from ..utils.connection_adapter import ConnectionManagerAdapter
            from .concurrent_access_manager import MigrationLockManager

            # Create connection adapter for the lock manager
            self._connection_adapter = ConnectionManagerAdapter(dataflow_instance)

            # Initialize migration lock manager
            self._migration_lock_manager = MigrationLockManager(
                self._connection_adapter, lock_timeout=lock_timeout
            )
            logger.info(
                "AutoMigrationSystem initialized with MigrationLockManager for concurrent safety"
            )
            logger.info(f"Proceeding with detected database type: {self.dialect}")

        self.migrations_dir = Path(migrations_dir)
        self.migrations_dir.mkdir(exist_ok=True)

        # Use database-specific components
        if self.dialect == "sqlite":
            self.inspector = SQLiteSchemaInspector(connection_string)
            self.generator = SQLiteMigrationGenerator()
        else:
            self.inspector = PostgreSQLSchemaInspector(connection_string)
            self.generator = PostgreSQLMigrationGenerator()

        # Migration history
        self.applied_migrations: List[Migration] = []
        self.pending_migrations: List[Migration] = []

        # DataFlow integration: existing schema mode
        self._existing_schema_mode: bool = False

    def _detect_database_type(self, connection_string: str) -> str:
        """Detect database type from connection string."""
        connection_lower = connection_string.lower()

        # SQLite detection patterns
        if (
            connection_lower.startswith("sqlite")
            or connection_lower == ":memory:"
            or connection_lower.endswith(".db")
            or connection_lower.endswith(".sqlite")
            or connection_lower.endswith(".sqlite3")
            or "/" in connection_string
            and "://" not in connection_string
        ):  # File path
            return "sqlite"
        elif connection_lower.startswith("postgresql") or connection_lower.startswith(
            "postgres"
        ):
            return "postgresql"
        else:
            # Try to infer from connection string format
            if "://" in connection_string:
                # Looks like a URL - likely PostgreSQL
                return "postgresql"
            else:
                # Looks like a file path - likely SQLite
                return "sqlite"

    async def auto_migrate(
        self,
        target_schema: Dict[str, TableDefinition],
        dry_run: bool = False,
        interactive: bool = True,
        auto_confirm: bool = False,
    ) -> Tuple[bool, List[Migration]]:
        """
        Automatically generate and apply migrations to match target schema.

        Args:
            target_schema: Target schema to migrate to
            dry_run: If True, only show what would be done
            interactive: If True, prompt user for confirmation
            auto_confirm: If True, automatically confirm all changes

        Returns:
            Tuple of (success, list of applied migrations)
        """
        logger.info("Starting auto-migration process")

        # Acquire migration lock to prevent concurrent migrations
        try:
            lock_acquired = await self._acquire_migration_lock()
            if not lock_acquired:
                raise RuntimeError(
                    "Cannot proceed without migration lock: Lock acquisition failed"
                )
        except Exception as e:
            logger.error(f"Failed to acquire migration lock: {e}")
            raise RuntimeError(f"Cannot proceed without migration lock: {e}")

        # CRITICAL FIX: All migration logic must happen while lock is held
        try:
            # Ensure migration tracking table exists
            await self._ensure_migration_table()

            # Load migration history with validation
            await self._load_migration_history()

            # Get current schema
            current_schema = await self.inspector.get_current_schema()
            logger.info(f"Current schema has {len(current_schema)} tables")

            # Compare schemas with existing_schema_mode support
            logger.info(f"Current schema type: {type(current_schema)}")
            logger.info(f"Target schema type: {type(target_schema)}")
            logger.info(
                f"Current schema keys: {list(current_schema.keys()) if isinstance(current_schema, dict) else 'N/A'}"
            )
            logger.info(
                f"Target schema keys: {list(target_schema.keys()) if isinstance(target_schema, dict) else 'N/A'}"
            )

            try:
                diff = self.inspector.compare_schemas(
                    current_schema,
                    target_schema,
                    existing_schema_mode=self._existing_schema_mode,
                )
            except Exception as e:
                logger.error(f"Schema comparison failed: {e}")
                logger.error(f"Current schema sample: {str(current_schema)[:200]}...")
                logger.error(f"Target schema sample: {str(target_schema)[:200]}...")
                import traceback

                logger.error(f"Full traceback: {traceback.format_exc()}")
                raise

            # Handle case where schema comparison fails
            if not diff:
                logger.warning("Schema comparison returned None - no changes detected")
                return True, []

            # Generate migration to get checksum (even if no changes)
            migration = self.generator.generate_migration(diff, "auto_generated")

            # KEY FIX: Check if this migration was already applied
            if self._is_migration_already_applied(migration):
                logger.info(
                    f"Migration with checksum {migration.checksum} already applied - skipping"
                )
                return True, []

            # Now check if there are actual schema changes
            if not diff.has_changes():
                logger.info("No schema changes detected")
                return True, []
            logger.info(
                f"Generated migration with {len(migration.operations)} operations"
            )

            # Show visual confirmation
            if interactive and not auto_confirm:
                confirmed = await self._show_visual_confirmation(migration, diff)
                if not confirmed:
                    logger.info("Migration cancelled by user")
                    return False, []

            if dry_run:
                logger.info("Dry run mode - no changes applied")
                self._print_migration_preview(migration)
                return True, [migration]

            # Apply migration while lock is still held
            success = await self._apply_migration(migration)

            if success:
                logger.info(f"Migration {migration.version} applied successfully")
                return True, [migration]
            else:
                logger.error(f"Migration {migration.version} failed")
                return False, []

        except Exception as e:
            logger.error(f"Auto-migration failed: {e}")
            return False, []

        finally:
            # Release the migration lock
            try:
                await self._release_migration_lock()
            except Exception as e:
                logger.error(f"Failed to release migration lock: {e}")

    async def rollback_migration(self, migration_version: str = None) -> bool:
        """
        Rollback a migration.

        Args:
            migration_version: Version to rollback to. If None, rollback last migration.

        Returns:
            True if rollback successful
        """
        logger.info(f"Starting rollback process for version: {migration_version}")

        try:
            await self._load_migration_history()

            if not migration_version:
                # Rollback last migration
                applied_migrations = [
                    m
                    for m in self.applied_migrations
                    if m.status == MigrationStatus.APPLIED
                ]
                if not applied_migrations:
                    logger.warning("No migrations to rollback")
                    return False

                migration_to_rollback = max(
                    applied_migrations, key=lambda m: m.created_at
                )
            else:
                # Find specific migration
                migration_to_rollback = None
                for migration in self.applied_migrations:
                    if migration.version == migration_version:
                        migration_to_rollback = migration
                        break

                if not migration_to_rollback:
                    logger.error(f"Migration {migration_version} not found")
                    return False

            # Execute rollback operations in reverse order
            logger.info(f"Rolling back migration {migration_to_rollback.version}")

            # Execute rollback operations using WorkflowBuilder pattern
            for operation in reversed(migration_to_rollback.operations):
                if operation.sql_down.startswith("-- Cannot"):
                    logger.warning(
                        f"Cannot rollback operation: {operation.description}"
                    )
                    continue

                try:
                    workflow = WorkflowBuilder()
                    workflow.add_node(
                        "AsyncSQLDatabaseNode",
                        f"rollback_{operation.operation_type.value}",
                        {
                            "connection_string": self.connection_string,
                            "database_type": self.database_type,
                            "query": operation.sql_down,
                            "validate_queries": False,
                        },
                    )

                    # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
                    results, _ = _execute_workflow_safe(workflow)
                    node_id = f"rollback_{operation.operation_type.value}"

                    # Defensive error checking - handle both dict and other result formats
                    node_result = results.get(node_id)
                    if not node_result:
                        error_msg = "No result returned"
                    elif isinstance(node_result, dict) and node_result.get("error"):
                        error_msg = node_result.get("error", "Unknown error")
                    else:
                        error_msg = None

                    if error_msg:
                        logger.error(
                            f"Failed to rollback operation {operation.description}: {error_msg}"
                        )
                        raise RuntimeError(f"Rollback failed: {error_msg}")

                    logger.info(f"Rolled back: {operation.description}")
                except Exception as e:
                    logger.error(
                        f"Failed to rollback operation {operation.description}: {e}"
                    )
                    raise

            # Update migration status
            await self._update_migration_status(
                migration_to_rollback.version, MigrationStatus.ROLLED_BACK
            )

            logger.info(
                f"Migration {migration_to_rollback.version} rolled back successfully"
            )
            return True

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False

    async def get_migration_status(self) -> Dict[str, Any]:
        """Get current migration status and history."""
        await self._load_migration_history()

        applied_count = sum(
            1 for m in self.applied_migrations if m.status == MigrationStatus.APPLIED
        )
        failed_count = sum(
            1 for m in self.applied_migrations if m.status == MigrationStatus.FAILED
        )
        rolled_back_count = sum(
            1
            for m in self.applied_migrations
            if m.status == MigrationStatus.ROLLED_BACK
        )

        return {
            "total_migrations": len(self.applied_migrations),
            "applied_migrations": applied_count,
            "failed_migrations": failed_count,
            "rolled_back_migrations": rolled_back_count,
            "pending_migrations": len(self.pending_migrations),
            "last_migration": (
                max(self.applied_migrations, key=lambda m: m.created_at)
                if self.applied_migrations
                else None
            ),
        }

    def compare_schemas(
        self,
        current_schema: Dict[str, TableDefinition],
        target_schema: Dict[str, TableDefinition],
    ) -> SchemaDiff:
        """
        Compare current and target schemas to generate diff with smart compatibility.

        This method delegates to the unified schema comparator for consistent behavior.
        """
        return self.inspector.compare_schemas(current_schema, target_schema)

    async def _ensure_migration_table(self):
        """Ensure migration tracking table exists for both PostgreSQL and SQLite."""
        if self.dialect == "sqlite":
            statements = self._get_sqlite_migration_table_statements()
        else:
            statements = self._get_postgresql_migration_table_statements()

        try:
            for i, statement in enumerate(statements):
                workflow = WorkflowBuilder()
                workflow.add_node(
                    "AsyncSQLDatabaseNode",
                    f"create_migration_table_{i}",
                    {
                        "connection_string": self.connection_string,
                        "database_type": self.database_type,
                        "query": statement.strip(),
                        "validate_queries": False,
                    },
                )

                # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
                results, _ = _execute_workflow_safe(workflow)
                if f"create_migration_table_{i}" not in results or results[
                    f"create_migration_table_{i}"
                ].get("error"):
                    error_msg = results.get(f"create_migration_table_{i}", {}).get(
                        "error", "Unknown error"
                    )
                    logger.error(
                        f"Failed to execute migration table statement {i}: {error_msg}"
                    )
                    raise RuntimeError(f"Migration table creation failed: {error_msg}")

        except Exception as e:
            logger.error(f"Failed to create {self.dialect} migration table: {e}")
            raise

    def _get_postgresql_migration_table_statements(self) -> List[str]:
        """Get PostgreSQL migration table creation statements."""
        return [
            """
            CREATE TABLE IF NOT EXISTS dataflow_migrations (
                version VARCHAR(255) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                checksum VARCHAR(32) NOT NULL,
                applied_at TIMESTAMP WITH TIME ZONE,
                status VARCHAR(50) NOT NULL DEFAULT 'pending',
                operations JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT valid_status CHECK (status IN ('pending', 'applied', 'failed', 'rolled_back'))
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_migrations_status ON dataflow_migrations(status)",
            "CREATE INDEX IF NOT EXISTS idx_migrations_applied_at ON dataflow_migrations(applied_at)",
            "CREATE INDEX IF NOT EXISTS idx_migrations_operations_gin ON dataflow_migrations USING GIN(operations)",
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_migrations_checksum_unique
            ON dataflow_migrations(checksum)
            WHERE status = 'applied'
            """,
        ]

    def _get_sqlite_migration_table_statements(self) -> List[str]:
        """Get SQLite migration table creation statements."""
        return [
            """
            CREATE TABLE IF NOT EXISTS dataflow_migrations (
                version TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                checksum TEXT NOT NULL,
                applied_at TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                operations TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                CHECK (status IN ('pending', 'applied', 'failed', 'rolled_back'))
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_migrations_status ON dataflow_migrations(status)",
            "CREATE INDEX IF NOT EXISTS idx_migrations_applied_at ON dataflow_migrations(applied_at)",
            "CREATE INDEX IF NOT EXISTS idx_migrations_operations ON dataflow_migrations(operations)",
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_migrations_checksum_unique
            ON dataflow_migrations(checksum)
            WHERE status = 'applied'
            """,
        ]

    async def _load_migration_history(self):
        """Load migration history from database with validation."""
        try:
            # First validate the migration table structure using WorkflowBuilder
            workflow = WorkflowBuilder()

            # Use database-specific validation query
            if self.dialect == "sqlite":
                validate_query = """
                    SELECT name as column_name, type as data_type
                    FROM pragma_table_info('dataflow_migrations')
                """
            else:  # PostgreSQL
                validate_query = """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = 'dataflow_migrations'
                    AND table_schema = 'public'
                """

            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "validate_table",
                {
                    "connection_string": self.connection_string,
                    "database_type": self.database_type,
                    "query": validate_query,
                    "validate_queries": False,
                },
            )

            # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
            results, _ = _execute_workflow_safe(workflow)

            # Defensive error checking - handle both dict and other result formats
            validate_result = results.get("validate_table")
            if not validate_result:
                logger.warning("Failed to validate migration table: No result returned")
                columns = {}
            elif isinstance(validate_result, dict) and validate_result.get("error"):
                error_msg = validate_result.get("error", "Unknown error")
                logger.warning(f"Failed to validate migration table: {error_msg}")
                columns = {}
            else:
                rows = results["validate_table"].get("result", [])
                columns = {row[0]: row[1] for row in rows}

                # Database-specific column validation
                if self.dialect == "sqlite":
                    required_columns = {
                        "version": "TEXT",
                        "name": "TEXT",
                        "checksum": "TEXT",
                        "status": "TEXT",
                        "operations": "TEXT",
                        "applied_at": "TEXT",
                        "created_at": "TEXT",
                    }
                else:  # PostgreSQL
                    required_columns = {
                        "version": "character varying",
                        "name": "character varying",
                        "checksum": "character varying",
                        "status": "character varying",
                        "operations": ["json", "jsonb"],
                        "applied_at": "timestamp",
                        "created_at": "timestamp",
                    }

                for col_name, expected_types in required_columns.items():
                    if col_name not in columns:
                        raise RuntimeError(
                            f"Migration table missing required column '{col_name}'. "
                            f"Database migration table may be corrupted."
                        )

                    # Check type compatibility
                    actual_type = columns[col_name].lower()
                    if isinstance(expected_types, list):
                        if not any(t in actual_type for t in expected_types):
                            logger.warning(
                                f"Column '{col_name}' has unexpected type '{actual_type}', "
                                f"expected one of {expected_types}"
                            )
                    elif expected_types not in actual_type:
                        logger.warning(
                            f"Column '{col_name}' has unexpected type '{actual_type}', "
                            f"expected '{expected_types}'"
                        )

            # Load migration history using WorkflowBuilder
            query = """
                SELECT version, name, checksum, applied_at, status, operations, created_at
                FROM dataflow_migrations
                ORDER BY created_at
            """

            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "load_history",
                {
                    "connection_string": self.connection_string,
                    "database_type": self.database_type,
                    "query": query,
                    "validate_queries": False,
                },
            )

            # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
            results, _ = _execute_workflow_safe(workflow)

            # Defensive error checking - handle both dict and other result formats
            history_result = results.get("load_history")
            if not history_result:
                logger.warning("Failed to load migration history: No result returned")
                rows = []
            elif isinstance(history_result, dict) and history_result.get("error"):
                error_msg = history_result.get("error", "Unknown error")
                logger.warning(f"Failed to load migration history: {error_msg}")
                rows = []
            else:
                rows = results["load_history"].get("result", [])

            self.applied_migrations = []
            for idx, row in enumerate(rows):
                try:
                    # Safely parse operations JSON
                    operations_data = []
                    if row[5]:
                        try:
                            operations_data = json.loads(row[5])
                        except json.JSONDecodeError as e:
                            logger.error(
                                f"Corrupted operations JSON in migration {row[0]}: {e}"
                            )
                            # Continue with empty operations rather than failing
                            operations_data = []

                    # Safely create operation objects
                    operations = []
                    for op in operations_data:
                        try:
                            operations.append(
                                MigrationOperation(
                                    operation_type=MigrationType(op["operation_type"]),
                                    table_name=op["table_name"],
                                    description=op["description"],
                                    sql_up=op["sql_up"],
                                    sql_down=op["sql_down"],
                                    metadata=op.get("metadata", {}),
                                )
                            )
                        except (KeyError, ValueError) as e:
                            logger.error(
                                f"Corrupted operation in migration {row[0]}: {e}"
                            )
                            # Skip corrupted operation
                            continue

                    # Create migration object
                    migration = Migration(
                        version=row[0],
                        name=row[1],
                        checksum=row[2],
                        applied_at=row[3],
                        status=MigrationStatus(row[4]),
                        operations=operations,
                        created_at=row[6],
                    )
                    self.applied_migrations.append(migration)

                except Exception as e:
                    logger.error(
                        f"Failed to load migration at index {idx}: {e}. "
                        f"Migration data: version={row[0] if row else 'unknown'}"
                    )
                    # Decide on fail-safe approach: skip corrupted migrations
                    # This allows the system to continue but logs the issue
                    continue

        except Exception as e:
            logger.error(f"Failed to load migration history: {e}")
            # For safety, treat missing/corrupted history as empty
            # This prevents accidental re-application but logs the issue
            self.applied_migrations = []
            logger.warning(
                "Migration history could not be loaded. "
                "Treating as empty history to prevent data loss."
            )

    def _is_migration_already_applied(self, migration: Migration) -> bool:
        """
        Check if a migration with the same checksum has already been applied.

        This prevents duplicate migrations when:
        - Multiple apps register the same models
        - Apps restart and re-register models
        - Different instances try to apply the same migration

        Args:
            migration: The migration to check

        Returns:
            True if migration with same checksum was already applied successfully
        """
        # Generate checksum for the current migration
        current_checksum = migration.generate_checksum()

        # Check against all applied migrations
        for applied_migration in self.applied_migrations:
            if (
                applied_migration.checksum == current_checksum
                and applied_migration.status == MigrationStatus.APPLIED
            ):
                logger.debug(
                    f"Found applied migration {applied_migration.version} "
                    f"with matching checksum {current_checksum}"
                )
                return True

        return False

    async def _apply_migration(self, migration: Migration) -> bool:
        """Apply a migration to the database."""
        try:
            # Execute migration operations using WorkflowBuilder pattern
            for operation in migration.operations:
                workflow = WorkflowBuilder()
                workflow.add_node(
                    "AsyncSQLDatabaseNode",
                    f"apply_{operation.operation_type.value}",
                    {
                        "connection_string": self.connection_string,
                        "database_type": self.database_type,
                        "query": operation.sql_up,
                        "validate_queries": False,
                    },
                )

                # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
                results, _ = _execute_workflow_safe(workflow)
                node_id = f"apply_{operation.operation_type.value}"

                # Defensive error checking - handle both dict and other result formats
                node_result = results.get(node_id)
                if not node_result:
                    logger.error(
                        f"Failed to apply operation {operation.description}: No result returned"
                    )
                    raise RuntimeError("Migration operation failed: No result returned")

                # Check if result is a dict and contains error
                if isinstance(node_result, dict) and node_result.get("error"):
                    error_msg = node_result.get("error", "Unknown error")
                    logger.error(
                        f"Failed to apply operation {operation.description}: {error_msg}"
                    )
                    raise RuntimeError(f"Migration operation failed: {error_msg}")

                logger.info(f"Applied: {operation.description}")

            # Record migration in history
            await self._record_migration(migration)

            migration.status = MigrationStatus.APPLIED
            migration.applied_at = datetime.now()
            return True

        except Exception as e:
            logger.error(f"Failed to apply migration: {e}")
            migration.status = MigrationStatus.FAILED

            # Record failed migration
            try:
                await self._record_migration(migration)
            except:
                pass  # Don't fail if we can't record the failure

            return False

    async def _record_migration(self, migration: Migration):
        """Record migration in the database."""
        operations_json = json.dumps(
            [
                {
                    "operation_type": op.operation_type.value,
                    "table_name": op.table_name,
                    "description": op.description,
                    "sql_up": op.sql_up,
                    "sql_down": op.sql_down,
                    "metadata": op.metadata,
                }
                for op in migration.operations
            ]
        )

        # Database-specific INSERT SQL
        if self.database_type.lower() == "sqlite":
            insert_sql = """
            INSERT OR REPLACE INTO dataflow_migrations (version, name, checksum, applied_at, status, operations)
            VALUES (?, ?, ?, ?, ?, ?)
            """
        else:  # PostgreSQL
            insert_sql = """
            INSERT INTO dataflow_migrations (version, name, checksum, applied_at, status, operations)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            ON CONFLICT (version) DO UPDATE SET
                applied_at = EXCLUDED.applied_at,
                status = EXCLUDED.status,
                operations = EXCLUDED.operations
            """

        try:
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "record_migration",
                {
                    "connection_string": self.connection_string,
                    "database_type": self.database_type,
                    "query": insert_sql,
                    "params": [
                        migration.version,
                        migration.name,
                        migration.checksum,
                        (
                            migration.applied_at.isoformat()
                            if migration.applied_at
                            else None
                        ),
                        migration.status.value,
                        operations_json,
                    ],
                    "validate_queries": False,
                },
            )

            # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
            results, _ = _execute_workflow_safe(workflow)

            # Defensive error checking - handle both dict and other result formats
            record_result = results.get("record_migration")
            if not record_result:
                logger.error(
                    f"Failed to record {self.dialect} migration: No result returned"
                )
                raise RuntimeError("Migration recording failed: No result returned")

            # Check if result is a dict and contains error
            if isinstance(record_result, dict) and record_result.get("error"):
                error_msg = record_result.get("error", "Unknown error")
                logger.error(f"Failed to record {self.dialect} migration: {error_msg}")
                raise RuntimeError(f"Migration recording failed: {error_msg}")

        except Exception as e:
            logger.error(f"Failed to record {self.dialect} migration: {e}")
            raise

    async def _update_migration_status(self, version: str, status: MigrationStatus):
        """Update migration status in database."""
        # Database-specific UPDATE SQL
        if self.dialect == "sqlite":
            update_sql = """
            UPDATE dataflow_migrations
            SET status = ?,
                applied_at = CASE WHEN ? = 'applied' THEN datetime('now') ELSE applied_at END
            WHERE version = ?
            """
        else:  # PostgreSQL
            update_sql = """
            UPDATE dataflow_migrations
            SET status = $1,
                applied_at = CASE WHEN $2 = 'applied' THEN CURRENT_TIMESTAMP ELSE applied_at END
            WHERE version = $3
            """

        try:
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "update_status",
                {
                    "connection_string": self.connection_string,
                    "database_type": self.database_type,
                    "query": update_sql,
                    "params": [status.value, status.value, version],
                    "validate_queries": False,
                },
            )

            # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
            results, _ = _execute_workflow_safe(workflow)

            # Defensive error checking - handle both dict and other result formats
            update_result = results.get("update_status")
            if not update_result:
                logger.error(
                    f"Failed to update {self.dialect} migration status: No result returned"
                )
            elif isinstance(update_result, dict) and update_result.get("error"):
                error_msg = update_result.get("error", "Unknown error")
                logger.error(
                    f"Failed to update {self.dialect} migration status: {error_msg}"
                )
                raise RuntimeError(f"Status update failed: {error_msg}")

        except Exception as e:
            logger.error(f"Failed to update {self.dialect} migration status: {e}")
            raise

    async def _show_visual_confirmation(
        self, migration: Migration, diff: SchemaDiff
    ) -> bool:
        """Show visual confirmation of migration changes."""
        print("\n" + "=" * 60)
        print("🔄 DataFlow Auto-Migration Preview")
        print("=" * 60)

        print("\n📊 Migration Summary:")
        print(f"  Version: {migration.version}")
        print(f"  Name: {migration.name}")
        print(f"  Operations: {len(migration.operations)}")
        print(f"  Total changes: {diff.change_count()}")

        # Show detailed changes
        if diff.tables_to_create:
            print(f"\n✅ Tables to CREATE ({len(diff.tables_to_create)}):")
            for table in diff.tables_to_create:
                print(f"  📋 {table.name} ({len(table.columns)} columns)")
                for col in table.columns[:3]:  # Show first 3 columns
                    print(f"    - {col.name}: {col.type}")
                if len(table.columns) > 3:
                    print(f"    ... and {len(table.columns) - 3} more columns")

        if diff.tables_to_drop:
            print(f"\n❌ Tables to DROP ({len(diff.tables_to_drop)}):")
            for table_name in diff.tables_to_drop:
                print(f"  🗑️ {table_name} (⚠️ Data will be lost!)")

        if diff.tables_to_modify:
            print(f"\n🔄 Tables to MODIFY ({len(diff.tables_to_modify)}):")
            for table_name, current, target in diff.tables_to_modify:
                print(f"  📝 {table_name}")
                # Show specific changes
                current_cols = {col.name: col for col in current.columns}
                target_cols = {col.name: col for col in target.columns}

                new_cols = set(target_cols.keys()) - set(current_cols.keys())
                dropped_cols = set(current_cols.keys()) - set(target_cols.keys())

                if new_cols:
                    print(f"    ➕ Adding columns: {', '.join(new_cols)}")
                if dropped_cols:
                    print(
                        f"    ➖ Dropping columns: {', '.join(dropped_cols)} (⚠️ Data will be lost!)"
                    )

        # Show SQL preview
        print("\n📜 SQL Operations Preview:")
        for i, operation in enumerate(migration.operations[:5], 1):
            print(f"  {i}. {operation.description}")
            # Show first line of SQL
            first_line = operation.sql_up.split("\n")[0]
            print(f"     SQL: {first_line[:60]}{'...' if len(first_line) > 60 else ''}")

        if len(migration.operations) > 5:
            print(f"     ... and {len(migration.operations) - 5} more operations")

        # Warnings
        has_data_loss = any(
            op.operation_type in [MigrationType.DROP_TABLE, MigrationType.DROP_COLUMN]
            for op in migration.operations
        )

        if has_data_loss:
            print("\n⚠️ WARNING: This migration will result in DATA LOSS!")
            print("   Please ensure you have backups before proceeding.")

        print(
            f"\n🔄 This migration can be rolled back: {self._can_rollback(migration)}"
        )

        # Confirmation prompt
        print("\n" + "-" * 60)
        while True:
            response = (
                input("Do you want to apply this migration? [y/N/details]: ")
                .lower()
                .strip()
            )

            if response in ["y", "yes"]:
                return True
            elif response in ["n", "no", ""]:
                return False
            elif response in ["d", "details"]:
                self._print_migration_details(migration)
            else:
                print(
                    "Please enter 'y' for yes, 'n' for no, or 'details' for more information."
                )

    def _can_rollback(self, migration: Migration) -> bool:
        """Check if migration can be rolled back."""
        for operation in migration.operations:
            if operation.sql_down.startswith("-- Cannot"):
                return False
        return True

    def _print_migration_preview(self, migration: Migration):
        """Print migration preview for dry run."""
        print("\n📋 Migration Preview (Dry Run)")
        print(f"Version: {migration.version}")
        print(f"Operations: {len(migration.operations)}")

        for operation in migration.operations:
            print(
                f"\n{operation.operation_type.value.upper()}: {operation.description}"
            )
            print(f"SQL: {operation.sql_up}")

    def _print_migration_details(self, migration: Migration):
        """Print detailed migration information."""
        print("\n" + "=" * 60)
        print("📋 Detailed Migration Information")
        print("=" * 60)

        for i, operation in enumerate(migration.operations, 1):
            print(f"\n{i}. {operation.operation_type.value.upper()}")
            print(f"   Table: {operation.table_name}")
            print(f"   Description: {operation.description}")
            print("   Forward SQL:")
            for line in operation.sql_up.split("\n"):
                print(f"     {line}")
            print("   Rollback SQL:")
            for line in operation.sql_down.split("\n"):
                print(f"     {line}")

            if operation.metadata:
                print(f"   Metadata: {operation.metadata}")

        print("\n" + "=" * 60)

    async def _acquire_migration_lock(self) -> bool:
        """Acquire migration lock using MigrationLockManager or fallback to advisory locks."""
        if self._migration_lock_manager:
            # Use new MigrationLockManager for concurrent safety
            schema_name = self._get_schema_name_from_connection()
            return await self._migration_lock_manager.acquire_migration_lock(
                schema_name
            )
        else:
            # Fallback to database-specific advisory locks
            if self.dialect == "sqlite":
                return await self._acquire_sqlite_migration_lock()
            else:
                return await self._acquire_postgresql_migration_lock()

    async def _release_migration_lock(self) -> None:
        """Release migration lock using MigrationLockManager or fallback to advisory locks."""
        if self._migration_lock_manager:
            # Use new MigrationLockManager for concurrent safety
            schema_name = self._get_schema_name_from_connection()
            await self._migration_lock_manager.release_migration_lock(schema_name)
        else:
            # Fallback to database-specific advisory locks
            if self.dialect == "sqlite":
                await self._release_sqlite_migration_lock()
            else:
                await self._release_postgresql_migration_lock()

    def _get_schema_name_from_connection(self) -> str:
        """Extract schema/database name from connection string for lock identification."""
        try:
            from ..adapters.connection_parser import ConnectionParser

            components = ConnectionParser.parse_connection_string(
                self.connection_string
            )
            database_name = components.get("database", "default")
            if not database_name or database_name in ["", "default"]:
                # Fallback to a consistent name for the application
                database_name = "dataflow_default"
            return database_name
        except Exception as e:
            logger.warning(
                f"Failed to extract database name from connection string: {e}"
            )
            return "dataflow_default"

    async def _acquire_postgresql_migration_lock(self) -> bool:
        """Acquire PostgreSQL advisory lock."""
        MIGRATION_LOCK_ID = 314159265  # Unique ID for DataFlow migrations

        # Try to acquire lock first
        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "try_lock",
            {
                "connection_string": self.connection_string,
                "database_type": self.database_type,
                "query": "SELECT pg_try_advisory_lock($1) as acquired",
                "params": [MIGRATION_LOCK_ID],
                "validate_queries": False,
            },
        )

        # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
        results, _ = _execute_workflow_safe(workflow)

        # Defensive error checking - handle both dict and other result formats
        lock_result = results.get("try_lock")
        if not lock_result:
            logger.error("Failed to try advisory lock: No result returned")
            raise RuntimeError("Cannot proceed without migration lock")

        # Check if result is a dict and contains error
        if isinstance(lock_result, dict) and lock_result.get("error"):
            error_msg = lock_result.get("error", "Unknown error")
            logger.error(f"Failed to try advisory lock: {error_msg}")
            raise RuntimeError("Cannot proceed without migration lock")

        # PostgreSQL pg_try_advisory_lock returns true if lock acquired, false if already held
        lock_result = results["try_lock"].get("result", {})
        if "data" in lock_result and len(lock_result["data"]) > 0:
            # AsyncSQLDatabaseNode returns dict format: {"data": [{"acquired": True}], ...}
            acquired_value = lock_result["data"][0].get("acquired", False)
            lock_acquired = bool(acquired_value)
        else:
            lock_acquired = False

        logger.debug(
            f"Advisory lock attempt result: {lock_result}, acquired: {lock_acquired}"
        )

        if not lock_acquired:
            logger.warning("Another migration is in progress, waiting...")
            # Wait for lock
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "wait_lock",
                {
                    "connection_string": self.connection_string,
                    "database_type": self.database_type,
                    "query": "SELECT pg_advisory_lock($1)",
                    "params": [MIGRATION_LOCK_ID],
                    "validate_queries": False,
                },
            )

            # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
            results, _ = _execute_workflow_safe(workflow)

            # Defensive error checking - handle both dict and other result formats
            wait_result = results.get("wait_lock")
            if not wait_result:
                logger.error("Failed to acquire advisory lock: No result returned")
                raise RuntimeError("Cannot proceed without migration lock")

            # Check if result is a dict and contains error
            if isinstance(wait_result, dict) and wait_result.get("error"):
                error_msg = wait_result.get("error", "Unknown error")
                logger.error(f"Failed to acquire advisory lock: {error_msg}")
                raise RuntimeError("Cannot proceed without migration lock")

            logger.info("Migration lock acquired")

        return True

    async def _release_postgresql_migration_lock(self) -> None:
        """Release PostgreSQL advisory lock."""
        MIGRATION_LOCK_ID = 314159265  # Same ID as acquire

        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "release_lock",
            {
                "connection_string": self.connection_string,
                "database_type": self.database_type,
                "query": "SELECT pg_advisory_unlock($1)",
                "params": [MIGRATION_LOCK_ID],
                "validate_queries": False,
            },
        )

        # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
        results, _ = _execute_workflow_safe(workflow)

        # Defensive error checking - handle both dict and other result formats
        release_result = results.get("release_lock")
        if not release_result:
            logger.error("Failed to release migration lock: No result returned")
        elif isinstance(release_result, dict) and release_result.get("error"):
            logger.error("Failed to release migration lock")
        else:
            logger.debug("Migration lock released")

    async def _acquire_sqlite_migration_lock(self) -> bool:
        """Acquire SQLite migration lock using a lock table with retry mechanism."""
        import asyncio

        # SQLite doesn't have advisory locks, so we use a simple lock table approach
        # Add retry logic similar to PostgreSQL to prevent infinite timeouts
        max_retries = 30  # 30 seconds with 1-second intervals
        retry_count = 0

        while retry_count < max_retries:
            try:
                # First ensure lock table exists
                await self._ensure_sqlite_lock_table()

                # Try to insert a lock record
                workflow = WorkflowBuilder()
                workflow.add_node(
                    "AsyncSQLDatabaseNode",
                    "acquire_lock",
                    {
                        "connection_string": self.connection_string,
                        "database_type": self.database_type,
                        "query": """
                        INSERT INTO dataflow_migration_lock (lock_name, acquired_at, pid)
                        VALUES ('migration_lock', datetime('now'), ?)
                    """,
                        "params": [str(os.getpid())],
                        "validate_queries": False,
                    },
                )

                # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
                results, _ = _execute_workflow_safe(workflow)

                # Defensive error checking - handle both dict and other result formats
                acquire_result = results.get("acquire_lock")
                if not acquire_result:
                    error_msg = "No result returned"
                elif isinstance(acquire_result, dict) and acquire_result.get("error"):
                    error_msg = acquire_result.get("error", "Unknown error")
                else:
                    error_msg = None

                if error_msg:
                    if "UNIQUE constraint failed" in error_msg:
                        if retry_count < max_retries - 1:
                            logger.warning(
                                f"SQLite lock exists, waiting... (attempt {retry_count + 1}/{max_retries})"
                            )
                            await asyncio.sleep(1)  # Wait 1 second before retry
                            retry_count += 1
                            continue
                        else:
                            logger.error(
                                "Failed to acquire SQLite lock after maximum retries"
                            )
                            return False
                    else:
                        logger.error(
                            f"Failed to acquire SQLite migration lock: {error_msg}"
                        )
                        raise RuntimeError("Cannot proceed without migration lock")

                logger.info("SQLite migration lock acquired")
                return True

            except Exception as e:
                if retry_count < max_retries - 1:
                    logger.warning(
                        f"Error acquiring SQLite lock, retrying... (attempt {retry_count + 1}/{max_retries}): {e}"
                    )
                    await asyncio.sleep(1)
                    retry_count += 1
                    continue
                logger.error(
                    f"Failed to acquire SQLite migration lock after retries: {e}"
                )
                raise

    async def _release_sqlite_migration_lock(self) -> None:
        """Release SQLite migration lock."""
        try:
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "release_lock",
                {
                    "connection_string": self.connection_string,
                    "database_type": self.database_type,
                    "query": "DELETE FROM dataflow_migration_lock WHERE lock_name = 'migration_lock'",
                    "validate_queries": False,
                },
            )

            # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
            results, _ = _execute_workflow_safe(workflow)

            # Defensive error checking - handle both dict and other result formats
            release_result = results.get("release_lock")
            if not release_result:
                logger.error(
                    "Failed to release SQLite migration lock: No result returned"
                )
            elif isinstance(release_result, dict) and release_result.get("error"):
                logger.error("Failed to release SQLite migration lock")
            else:
                logger.debug("SQLite migration lock released")

        except Exception as e:
            logger.error(f"Failed to release SQLite migration lock: {e}")

    async def _ensure_sqlite_lock_table(self) -> None:
        """Ensure SQLite lock table exists."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "create_lock_table",
            {
                "connection_string": self.connection_string,
                "database_type": self.database_type,
                "query": """
                CREATE TABLE IF NOT EXISTS dataflow_migration_lock (
                    lock_name TEXT PRIMARY KEY,
                    acquired_at TEXT NOT NULL,
                    pid TEXT NOT NULL
                )
            """,
                "validate_queries": False,
            },
        )

        # ✅ FIX: Use _execute_workflow_safe for async-safe execution in Docker/FastAPI
        results, _ = _execute_workflow_safe(workflow)

        # Defensive error checking - handle both dict and other result formats
        create_result = results.get("create_lock_table")
        if not create_result:
            logger.error("Failed to create SQLite lock table: No result returned")
            raise RuntimeError("Lock table creation failed: No result returned")

        # Check if result is a dict and contains error
        if isinstance(create_result, dict) and create_result.get("error"):
            error_msg = create_result.get("error", "Unknown error")
            logger.error(f"Failed to create SQLite lock table: {error_msg}")
            raise RuntimeError(f"Lock table creation failed: {error_msg}")
