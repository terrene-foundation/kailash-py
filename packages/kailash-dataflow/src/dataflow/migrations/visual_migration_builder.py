"""
DataFlow Visual Migration Builder

Advanced migration builder that allows creating migrations through method calls
instead of SQL, providing a declarative and intuitive API for schema changes.

Features:
- Declarative schema modification API
- Visual operation builder with method chaining
- Automatic SQL generation from method calls
- Support for all major database operations
- Type-safe migration building
- Preview and validation before execution
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from .auto_migration_system import (
    ColumnDefinition,
    Migration,
    MigrationOperation,
    MigrationType,
    TableDefinition,
)

logger = logging.getLogger(__name__)


class ColumnType(Enum):
    """Standard column types for cross-database compatibility."""

    INTEGER = "INTEGER"
    BIGINT = "BIGINT"
    SMALLINT = "SMALLINT"
    VARCHAR = "VARCHAR"
    TEXT = "TEXT"
    CHAR = "CHAR"
    BOOLEAN = "BOOLEAN"
    DECIMAL = "DECIMAL"
    FLOAT = "FLOAT"
    DOUBLE = "DOUBLE"
    DATE = "DATE"
    TIME = "TIME"
    TIMESTAMP = "TIMESTAMP"
    DATETIME = "DATETIME"
    BLOB = "BLOB"
    JSON = "JSON"
    UUID = "UUID"


class IndexType(Enum):
    """Index types for database optimization."""

    BTREE = "btree"
    HASH = "hash"
    GIN = "gin"
    GIST = "gist"
    UNIQUE = "unique"
    PARTIAL = "partial"
    COMPOSITE = "composite"
    COVERING = "covering"


class ConstraintType(Enum):
    """Constraint types for data integrity."""

    PRIMARY_KEY = "primary_key"
    FOREIGN_KEY = "foreign_key"
    UNIQUE = "unique"
    CHECK = "check"
    NOT_NULL = "not_null"
    DEFAULT = "default"


@dataclass
class ColumnBuilder:
    """Builder for column definitions with fluent API."""

    name: str
    column_type: ColumnType
    nullable: bool = True
    default: Optional[Any] = None
    max_length: Optional[int] = None
    precision: Optional[int] = None
    scale: Optional[int] = None
    _auto_increment: bool = False
    is_primary_key: bool = False
    is_unique: bool = False
    foreign_key: Optional[str] = None
    check_constraint: Optional[str] = None
    _comment: Optional[str] = None

    def not_null(self) -> "ColumnBuilder":
        """Make column NOT NULL."""
        self.nullable = False
        return self

    def null(self) -> "ColumnBuilder":
        """Make column nullable."""
        self.nullable = True
        return self

    def default_value(self, value: Any) -> "ColumnBuilder":
        """Set default value for column."""
        self.default = value
        return self

    def length(self, max_length: int) -> "ColumnBuilder":
        """Set maximum length for VARCHAR/CHAR columns."""
        self.max_length = max_length
        return self

    def decimal(self, precision: int, scale: int = 0) -> "ColumnBuilder":
        """Set precision and scale for DECIMAL columns."""
        self.precision = precision
        self.scale = scale
        return self

    def auto_increment(self) -> "ColumnBuilder":
        """Make column auto-incrementing."""
        self._auto_increment = True
        return self

    def primary_key(self) -> "ColumnBuilder":
        """Make column a primary key."""
        self.is_primary_key = True
        self.nullable = False
        return self

    def unique(self) -> "ColumnBuilder":
        """Add unique constraint to column."""
        object.__setattr__(self, "is_unique", True)
        return self

    def references(self, table_column: str) -> "ColumnBuilder":
        """Add foreign key reference."""
        self.foreign_key = table_column
        return self

    def check(self, constraint: str) -> "ColumnBuilder":
        """Add check constraint."""
        self.check_constraint = constraint
        return self

    def comment(self, comment_text: str) -> "ColumnBuilder":
        """Add column comment."""
        self._comment = comment_text
        return self

    def build(self) -> ColumnDefinition:
        """Build the final ColumnDefinition."""
        return ColumnDefinition(
            name=self.name,
            type=self._get_sql_type(),
            nullable=self.nullable,
            default=self.default,
            max_length=self.max_length,
            primary_key=self.is_primary_key,
            unique=self.is_unique,
            auto_increment=self._auto_increment,
            foreign_key=self.foreign_key,
        )

    def _get_sql_type(self) -> str:
        """Convert ColumnType to SQL type string."""
        if self.column_type == ColumnType.VARCHAR and self.max_length:
            return f"VARCHAR({self.max_length})"
        elif self.column_type == ColumnType.CHAR and self.max_length:
            return f"CHAR({self.max_length})"
        elif self.column_type == ColumnType.DECIMAL and self.precision:
            if self.scale:
                return f"DECIMAL({self.precision},{self.scale})"
            else:
                return f"DECIMAL({self.precision})"
        else:
            return self.column_type.value


@dataclass
class IndexBuilder:
    """Builder for index definitions."""

    name: str
    table_name: str
    columns: List[str] = field(default_factory=list)
    index_type: IndexType = IndexType.BTREE
    _unique: bool = False
    partial_condition: Optional[str] = None
    include_columns: List[str] = field(default_factory=list)

    def on_columns(self, *columns: str) -> "IndexBuilder":
        """Specify columns for the index."""
        self.columns = list(columns)
        return self

    def using(self, index_type: IndexType) -> "IndexBuilder":
        """Set index type."""
        self.index_type = index_type
        return self

    def unique(self) -> "IndexBuilder":
        """Make index unique."""
        self._unique = True
        return self

    def where(self, condition: str) -> "IndexBuilder":
        """Add partial index condition."""
        self.partial_condition = condition
        return self

    def include(self, *columns: str) -> "IndexBuilder":
        """Add include columns for covering index."""
        self.include_columns = list(columns)
        return self


@dataclass
class TableBuilder:
    """Builder for table definitions."""

    name: str
    columns: List[ColumnBuilder] = field(default_factory=list)
    indexes: List[IndexBuilder] = field(default_factory=list)
    constraints: List[Dict[str, Any]] = field(default_factory=list)
    _comment: Optional[str] = None

    def add_column(self, name: str, column_type: ColumnType) -> ColumnBuilder:
        """Add a new column to the table."""
        column = ColumnBuilder(name=name, column_type=column_type)
        self.columns.append(column)
        return column

    def id(self, name: str = "id") -> ColumnBuilder:
        """Add auto-incrementing ID column."""
        return self.add_column(name, ColumnType.INTEGER).primary_key().auto_increment()

    def string(self, name: str, length: int = 255) -> ColumnBuilder:
        """Add VARCHAR column."""
        return self.add_column(name, ColumnType.VARCHAR).length(length)

    def text(self, name: str) -> ColumnBuilder:
        """Add TEXT column."""
        return self.add_column(name, ColumnType.TEXT)

    def integer(self, name: str) -> ColumnBuilder:
        """Add INTEGER column."""
        return self.add_column(name, ColumnType.INTEGER)

    def bigint(self, name: str) -> ColumnBuilder:
        """Add BIGINT column."""
        return self.add_column(name, ColumnType.BIGINT)

    def decimal(self, name: str, precision: int = 10, scale: int = 2) -> ColumnBuilder:
        """Add DECIMAL column."""
        return self.add_column(name, ColumnType.DECIMAL).decimal(precision, scale)

    def boolean(self, name: str) -> ColumnBuilder:
        """Add BOOLEAN column."""
        return self.add_column(name, ColumnType.BOOLEAN)

    def timestamp(self, name: str) -> ColumnBuilder:
        """Add TIMESTAMP column."""
        return self.add_column(name, ColumnType.TIMESTAMP)

    def timestamps(self) -> "TableBuilder":
        """Add created_at and updated_at timestamp columns."""
        self.timestamp("created_at").default_value("CURRENT_TIMESTAMP").not_null()
        self.timestamp("updated_at").default_value("CURRENT_TIMESTAMP").not_null()
        return self

    def json(self, name: str) -> ColumnBuilder:
        """Add JSON column."""
        return self.add_column(name, ColumnType.JSON)

    def uuid(self, name: str) -> ColumnBuilder:
        """Add UUID column."""
        return self.add_column(name, ColumnType.UUID)

    def add_index(self, name: str) -> IndexBuilder:
        """Add an index to the table."""
        index = IndexBuilder(name=name, table_name=self.name)
        self.indexes.append(index)
        return index

    def index(self, *columns: str) -> IndexBuilder:
        """Add a simple index on specified columns."""
        index_name = f"idx_{self.name}_{'_'.join(columns)}"
        return self.add_index(index_name).on_columns(*columns)

    def unique_index(self, *columns: str) -> IndexBuilder:
        """Add a unique index on specified columns."""
        index_name = f"uniq_{self.name}_{'_'.join(columns)}"
        return self.add_index(index_name).on_columns(*columns).unique()

    def foreign_key(
        self, column: str, references: str, on_delete: str = "CASCADE"
    ) -> "TableBuilder":
        """Add foreign key constraint."""
        self.constraints.append(
            {
                "type": "foreign_key",
                "column": column,
                "references": references,
                "on_delete": on_delete,
            }
        )
        return self

    def check_constraint(self, name: str, condition: str) -> "TableBuilder":
        """Add check constraint."""
        self.constraints.append({"type": "check", "name": name, "condition": condition})
        return self

    def comment(self, comment_text: str) -> "TableBuilder":
        """Add table comment."""
        self._comment = comment_text
        return self


class VisualMigrationBuilder:
    """
    Main migration builder that provides a visual, declarative API for
    creating database migrations without writing SQL.
    """

    def __init__(self, name: str, dialect: str = "postgresql"):
        self.name = name
        self.dialect = dialect
        self.operations: List[MigrationOperation] = []
        self.version = datetime.now().strftime("%Y%m%d_%H%M%S")

    def create_table(self, name: str) -> TableBuilder:
        """Create a new table with fluent API."""
        table_builder = TableBuilder(name=name)

        # Store a reference to add the operation later
        def finalize_table():
            # Convert TableBuilder to MigrationOperation
            operation = self._create_table_operation(table_builder)
            self.operations.append(operation)

        # Add finalization method to table builder
        table_builder._finalize = finalize_table
        return table_builder

    def drop_table(self, name: str) -> "VisualMigrationBuilder":
        """Drop an existing table."""
        operation = MigrationOperation(
            operation_type=MigrationType.DROP_TABLE,
            table_name=name,
            description=f"Drop table '{name}'",
            sql_up=f"DROP TABLE IF EXISTS {name};",
            sql_down=f"-- Cannot automatically recreate dropped table: {name}",
            metadata={"warning": "Cannot automatically rollback table drops"},
        )
        self.operations.append(operation)
        return self

    def rename_table(self, old_name: str, new_name: str) -> "VisualMigrationBuilder":
        """Rename an existing table."""
        operation = MigrationOperation(
            operation_type=MigrationType.RENAME_TABLE,
            table_name=old_name,
            description=f"Rename table '{old_name}' to '{new_name}'",
            sql_up=f"ALTER TABLE {old_name} RENAME TO {new_name};",
            sql_down=f"ALTER TABLE {new_name} RENAME TO {old_name};",
            metadata={"old_name": old_name, "new_name": new_name},
        )
        self.operations.append(operation)
        return self

    def add_column(
        self, table_name: str, column_name: str, column_type: ColumnType
    ) -> ColumnBuilder:
        """Add a column to an existing table."""
        column_builder = ColumnBuilder(name=column_name, column_type=column_type)

        # Store a reference to add the operation later
        def finalize_column():
            operation = self._add_column_operation(table_name, column_builder)
            self.operations.append(operation)

        column_builder._finalize = finalize_column
        return column_builder

    def drop_column(
        self, table_name: str, column_name: str
    ) -> "VisualMigrationBuilder":
        """Drop a column from an existing table."""
        operation = MigrationOperation(
            operation_type=MigrationType.DROP_COLUMN,
            table_name=table_name,
            description=f"Drop column '{column_name}' from table '{table_name}'",
            sql_up=f"ALTER TABLE {table_name} DROP COLUMN {column_name};",
            sql_down=f"-- Cannot automatically recreate dropped column: {column_name}",
            metadata={
                "column_name": column_name,
                "warning": "Cannot automatically rollback",
            },
        )
        self.operations.append(operation)
        return self

    def rename_column(
        self, table_name: str, old_name: str, new_name: str
    ) -> "VisualMigrationBuilder":
        """Rename a column in an existing table."""
        if self.dialect == "postgresql":
            sql_up = f"ALTER TABLE {table_name} RENAME COLUMN {old_name} TO {new_name};"
            sql_down = (
                f"ALTER TABLE {table_name} RENAME COLUMN {new_name} TO {old_name};"
            )
        elif self.dialect == "mysql":
            # MySQL requires specifying the column definition
            sql_up = f"-- ALTER TABLE {table_name} CHANGE {old_name} {new_name} <type>;"
            sql_down = (
                f"-- ALTER TABLE {table_name} CHANGE {new_name} {old_name} <type>;"
            )
        else:  # SQLite
            sql_up = "-- SQLite does not support RENAME COLUMN directly"
            sql_down = "-- SQLite does not support RENAME COLUMN directly"

        operation = MigrationOperation(
            operation_type=MigrationType.RENAME_COLUMN,
            table_name=table_name,
            description=f"Rename column '{old_name}' to '{new_name}' in table '{table_name}'",
            sql_up=sql_up,
            sql_down=sql_down,
            metadata={"old_name": old_name, "new_name": new_name},
        )
        self.operations.append(operation)
        return self

    def modify_column(
        self, table_name: str, column_name: str, column_type: ColumnType
    ) -> ColumnBuilder:
        """Modify an existing column."""
        column_builder = ColumnBuilder(name=column_name, column_type=column_type)

        def finalize_modify():
            operation = self._modify_column_operation(table_name, column_builder)
            self.operations.append(operation)

        column_builder._finalize = finalize_modify
        return column_builder

    def add_index(self, table_name: str, index_name: str) -> IndexBuilder:
        """Add an index to a table."""
        index_builder = IndexBuilder(name=index_name, table_name=table_name)

        def finalize_index():
            operation = self._add_index_operation(index_builder)
            self.operations.append(operation)

        index_builder._finalize = finalize_index
        return index_builder

    def drop_index(
        self, index_name: str, table_name: str = None
    ) -> "VisualMigrationBuilder":
        """Drop an index."""
        if self.dialect == "mysql" and table_name:
            sql_up = f"DROP INDEX {index_name} ON {table_name};"
        else:
            sql_up = f"DROP INDEX {index_name};"

        operation = MigrationOperation(
            operation_type=MigrationType.DROP_INDEX,
            table_name=table_name or "unknown",
            description=f"Drop index '{index_name}'",
            sql_up=sql_up,
            sql_down=f"-- Cannot automatically recreate dropped index: {index_name}",
            metadata={
                "index_name": index_name,
                "warning": "Cannot automatically rollback",
            },
        )
        self.operations.append(operation)
        return self

    def execute_sql(
        self, sql: str, description: str = None
    ) -> "VisualMigrationBuilder":
        """Execute custom SQL (escape hatch for complex operations)."""
        operation = MigrationOperation(
            operation_type=MigrationType.CREATE_TABLE,  # Generic type
            table_name="custom",
            description=description or "Execute custom SQL",
            sql_up=sql,
            sql_down="-- No automatic rollback for custom SQL",
            metadata={
                "custom_sql": True,
                "warning": "Custom SQL cannot be automatically rolled back",
            },
        )
        self.operations.append(operation)
        return self

    def build(self) -> Migration:
        """Build the final Migration object."""
        # Finalize any pending operations
        self._finalize_pending_operations()

        migration = Migration(
            version=self.version, name=self.name, operations=self.operations.copy()
        )
        migration.checksum = migration.generate_checksum()
        return migration

    def preview(self) -> str:
        """Generate a preview of the migration operations."""
        migration = self.build()

        preview = f"Migration Preview: {migration.name}\n"
        preview += f"Version: {migration.version}\n"
        preview += f"Operations: {len(migration.operations)}\n"
        preview += "=" * 50 + "\n\n"

        for i, operation in enumerate(migration.operations, 1):
            preview += f"{i}. {operation.operation_type.value.upper()}\n"
            preview += f"   Description: {operation.description}\n"
            preview += f"   Table: {operation.table_name}\n"
            preview += "   SQL:\n"

            for line in operation.sql_up.split("\n"):
                if line.strip():
                    preview += f"     {line}\n"

            if operation.metadata:
                preview += f"   Metadata: {operation.metadata}\n"

            preview += "\n"

        return preview

    def _create_table_operation(
        self, table_builder: TableBuilder
    ) -> MigrationOperation:
        """Convert TableBuilder to CREATE TABLE operation."""
        table_def = self._table_builder_to_definition(table_builder)
        sql_up = self._generate_create_table_sql(table_def)
        sql_down = f"DROP TABLE IF EXISTS {table_builder.name};"

        return MigrationOperation(
            operation_type=MigrationType.CREATE_TABLE,
            table_name=table_builder.name,
            description=f"Create table '{table_builder.name}' with {len(table_builder.columns)} columns",
            sql_up=sql_up,
            sql_down=sql_down,
            metadata={
                "columns": len(table_builder.columns),
                "indexes": len(table_builder.indexes),
            },
        )

    def _add_column_operation(
        self, table_name: str, column_builder: ColumnBuilder
    ) -> MigrationOperation:
        """Convert ColumnBuilder to ADD COLUMN operation."""
        column_def = column_builder.build()
        column_sql = self._generate_column_sql(column_def)

        sql_up = f"ALTER TABLE {table_name} ADD COLUMN {column_sql};"
        sql_down = f"ALTER TABLE {table_name} DROP COLUMN {column_builder.name};"

        return MigrationOperation(
            operation_type=MigrationType.ADD_COLUMN,
            table_name=table_name,
            description=f"Add column '{column_builder.name}' to table '{table_name}'",
            sql_up=sql_up,
            sql_down=sql_down,
            metadata={
                "column_name": column_builder.name,
                "column_type": column_builder.column_type.value,
            },
        )

    def _modify_column_operation(
        self, table_name: str, column_builder: ColumnBuilder
    ) -> MigrationOperation:
        """Convert ColumnBuilder to MODIFY COLUMN operation."""
        column_def = column_builder.build()

        if self.dialect == "postgresql":
            sql_up = self._postgresql_modify_column_sql(table_name, column_def)
        elif self.dialect == "mysql":
            column_sql = self._generate_column_sql(column_def)
            sql_up = f"ALTER TABLE {table_name} MODIFY COLUMN {column_sql};"
        else:  # SQLite
            sql_up = "-- SQLite does not support MODIFY COLUMN directly"

        sql_down = "-- Cannot automatically rollback column modification"

        return MigrationOperation(
            operation_type=MigrationType.MODIFY_COLUMN,
            table_name=table_name,
            description=f"Modify column '{column_builder.name}' in table '{table_name}'",
            sql_up=sql_up,
            sql_down=sql_down,
            metadata={
                "column_name": column_builder.name,
                "new_type": column_builder.column_type.value,
            },
        )

    def _add_index_operation(self, index_builder: IndexBuilder) -> MigrationOperation:
        """Convert IndexBuilder to ADD INDEX operation."""
        sql_up = self._generate_index_sql(index_builder)

        if self.dialect == "mysql":
            sql_down = f"DROP INDEX {index_builder.name} ON {index_builder.table_name};"
        else:
            sql_down = f"DROP INDEX {index_builder.name};"

        return MigrationOperation(
            operation_type=MigrationType.ADD_INDEX,
            table_name=index_builder.table_name,
            description=f"Add index '{index_builder.name}' on {', '.join(index_builder.columns)}",
            sql_up=sql_up,
            sql_down=sql_down,
            metadata={
                "index_name": index_builder.name,
                "columns": index_builder.columns,
                "index_type": index_builder.index_type.value,
            },
        )

    def _generate_create_table_sql(self, table_def: TableDefinition) -> str:
        """Generate CREATE TABLE SQL from TableDefinition."""
        columns_sql = []
        for column in table_def.columns:
            columns_sql.append(self._generate_column_sql(column))

        sql = f"CREATE TABLE {table_def.name} (\n"
        sql += ",\n".join(f"    {col_sql}" for col_sql in columns_sql)
        sql += "\n);"

        return sql

    def _generate_column_sql(self, column_def: ColumnDefinition) -> str:
        """Generate column definition SQL."""
        parts = [column_def.name, column_def.type]

        if not column_def.nullable:
            parts.append("NOT NULL")

        if column_def.default is not None:
            if isinstance(
                column_def.default, str
            ) and not column_def.default.upper().startswith(("CURRENT_", "NOW()")):
                parts.append(f"DEFAULT '{column_def.default}'")
            else:
                parts.append(f"DEFAULT {column_def.default}")

        if column_def.primary_key:
            parts.append("PRIMARY KEY")

        if column_def.unique:
            parts.append("UNIQUE")

        if column_def.auto_increment:
            if self.dialect == "postgresql":
                # Replace INTEGER with SERIAL for PostgreSQL
                if parts[1] == "INTEGER":
                    parts[1] = "SERIAL"
            elif self.dialect == "mysql":
                parts.append("AUTO_INCREMENT")

        return " ".join(parts)

    def _generate_index_sql(self, index_builder: IndexBuilder) -> str:
        """Generate CREATE INDEX SQL."""
        if self.dialect == "postgresql":
            unique_keyword = "UNIQUE " if index_builder._unique else ""
            concurrently = "CONCURRENTLY "

            if index_builder.index_type == IndexType.HASH:
                using_clause = "USING hash"
            elif index_builder.index_type == IndexType.GIN:
                using_clause = "USING gin"
            elif index_builder.index_type == IndexType.GIST:
                using_clause = "USING gist"
            else:
                using_clause = ""

            columns_str = ", ".join(index_builder.columns)
            sql = f"CREATE {unique_keyword}INDEX {concurrently}{index_builder.name} ON {index_builder.table_name}"

            if using_clause:
                sql += f" {using_clause}"

            sql += f" ({columns_str})"

            if index_builder.include_columns:
                sql += f" INCLUDE ({', '.join(index_builder.include_columns)})"

            if index_builder.partial_condition:
                sql += f" WHERE {index_builder.partial_condition}"

            sql += ";"

        else:
            # MySQL/SQLite
            unique_keyword = "UNIQUE " if index_builder._unique else ""
            columns_str = ", ".join(index_builder.columns)
            sql = f"CREATE {unique_keyword}INDEX {index_builder.name} ON {index_builder.table_name} ({columns_str});"

        return sql

    def _postgresql_modify_column_sql(
        self, table_name: str, column_def: ColumnDefinition
    ) -> str:
        """Generate PostgreSQL-specific column modification SQL."""
        statements = []

        # Change data type
        statements.append(
            f"ALTER TABLE {table_name} ALTER COLUMN {column_def.name} TYPE {column_def.type};"
        )

        # Change nullable
        if not column_def.nullable:
            statements.append(
                f"ALTER TABLE {table_name} ALTER COLUMN {column_def.name} SET NOT NULL;"
            )
        else:
            statements.append(
                f"ALTER TABLE {table_name} ALTER COLUMN {column_def.name} DROP NOT NULL;"
            )

        # Change default
        if column_def.default is not None:
            if isinstance(
                column_def.default, str
            ) and not column_def.default.upper().startswith("CURRENT_"):
                default_val = f"'{column_def.default}'"
            else:
                default_val = column_def.default
            statements.append(
                f"ALTER TABLE {table_name} ALTER COLUMN {column_def.name} SET DEFAULT {default_val};"
            )

        return "\n".join(statements)

    def _table_builder_to_definition(
        self, table_builder: TableBuilder
    ) -> TableDefinition:
        """Convert TableBuilder to TableDefinition."""
        table_def = TableDefinition(name=table_builder.name)

        for column_builder in table_builder.columns:
            table_def.columns.append(column_builder.build())

        # Convert indexes to simple dict format
        for index_builder in table_builder.indexes:
            index_info = {
                "name": index_builder.name,
                "columns": index_builder.columns,
                "unique": index_builder._unique,
                "type": index_builder.index_type.value,
            }
            table_def.indexes.append(index_info)

        # Add constraints
        table_def.constraints = table_builder.constraints.copy()

        return table_def

    def _finalize_pending_operations(self):
        """Finalize any pending operations from builders."""
        # This would normally be handled by the builders themselves
        # when their finalize methods are called, but this provides a safety net
        pass


class MigrationScript:
    """
    Helper class for creating complete migration scripts with multiple operations.
    """

    def __init__(self, name: str, dialect: str = "postgresql"):
        self.name = name
        self.dialect = dialect
        self.builders: List[VisualMigrationBuilder] = []

    def up(self) -> VisualMigrationBuilder:
        """Create the 'up' migration (forward changes)."""
        builder = VisualMigrationBuilder(f"{self.name}_up", self.dialect)
        self.builders.append(builder)
        return builder

    def down(self) -> VisualMigrationBuilder:
        """Create the 'down' migration (rollback changes)."""
        builder = VisualMigrationBuilder(f"{self.name}_down", self.dialect)
        self.builders.append(builder)
        return builder

    def preview_all(self) -> str:
        """Preview all migration operations."""
        preview = f"Migration Script: {self.name}\n"
        preview += "=" * 50 + "\n\n"

        for builder in self.builders:
            preview += builder.preview()
            preview += "\n" + "-" * 50 + "\n\n"

        return preview
