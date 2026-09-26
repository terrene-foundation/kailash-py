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
import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from dataflow.adapters.dialect import DialectManager

from .auto_migration_system import (
    ColumnDefinition,
    Migration,
    MigrationOperation,
    MigrationType,
    TableDefinition,
)
from .drop_confirmation import require_force_drop

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
        if self.max_length is not None and self.column_type not in (
            ColumnType.VARCHAR,
            ColumnType.CHAR,
        ):
            raise ValueError("Column length requires VARCHAR or CHAR")
        if (
            self.precision is not None or self.scale is not None
        ) and self.column_type != ColumnType.DECIMAL:
            raise ValueError("Column precision/scale requires DECIMAL")
        for value in (self.max_length, self.precision):
            if value is not None and (type(value) is not int or value <= 0):
                raise ValueError("Column length/precision must be positive integers")
        if self.scale is not None and (
            type(self.scale) is not int
            or self.scale < 0
            or self.precision is None
            or self.scale > self.precision
        ):
            raise ValueError("Column scale must be between zero and precision")
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
        self._pending_operations = []
        self._quote = DialectManager.get_dialect(dialect).quote_identifier
        self.version = datetime.now().strftime("%Y%m%d_%H%M%S")

    def create_table(self, name: str) -> TableBuilder:
        """Create a new table with fluent API."""
        table_builder = TableBuilder(name=name)

        # Store a reference to add the operation later
        self._queue_operation(
            table_builder, lambda: self._create_table_operations(table_builder)
        )
        return table_builder

    def drop_table(
        self, name: str, *, force_drop: bool = False
    ) -> "VisualMigrationBuilder":
        """Drop an existing table.

        Per rules/dataflow-identifier-safety.md MUST Rule 4, destructive DDL
        requires explicit ``force_drop=True``. Dropped tables are
        unrecoverable; the flag is the last human gate before destruction.
        """
        require_force_drop(f"drop_table({name!r})", force_drop)
        operation = MigrationOperation(
            operation_type=MigrationType.DROP_TABLE,
            table_name=name,
            description=f"Drop table '{name}'",
            sql_up=f"DROP TABLE IF EXISTS {self._quote(name)};",
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
            sql_up=f"ALTER TABLE {self._quote(old_name)} RENAME TO {self._quote(new_name)};",
            sql_down=f"ALTER TABLE {self._quote(new_name)} RENAME TO {self._quote(old_name)};",
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
        self._queue_operation(
            column_builder,
            lambda: self._add_column_operation(table_name, column_builder),
        )
        return column_builder

    def drop_column(
        self, table_name: str, column_name: str, *, force_drop: bool = False
    ) -> "VisualMigrationBuilder":
        """Drop a column from an existing table.

        Per rules/dataflow-identifier-safety.md MUST Rule 4, destructive DDL
        requires explicit ``force_drop=True``.
        """
        require_force_drop(f"drop_column({table_name!r}, {column_name!r})", force_drop)
        operation = MigrationOperation(
            operation_type=MigrationType.DROP_COLUMN,
            table_name=table_name,
            description=f"Drop column '{column_name}' from table '{table_name}'",
            sql_up=f"ALTER TABLE {self._quote(table_name)} DROP COLUMN {self._quote(column_name)};",
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
        sql_up = f"ALTER TABLE {self._quote(table_name)} RENAME COLUMN {self._quote(old_name)} TO {self._quote(new_name)};"
        sql_down = f"ALTER TABLE {self._quote(table_name)} RENAME COLUMN {self._quote(new_name)} TO {self._quote(old_name)};"

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

        self._queue_operation(
            column_builder,
            lambda: self._modify_column_operation(table_name, column_builder),
        )
        return column_builder

    def add_index(self, table_name: str, index_name: str) -> IndexBuilder:
        """Add an index to a table."""
        index_builder = IndexBuilder(name=index_name, table_name=table_name)

        self._queue_operation(
            index_builder, lambda: self._add_index_operation(index_builder)
        )
        return index_builder

    def drop_index(
        self,
        index_name: str,
        table_name: str = None,
        *,
        force_drop: bool = False,
    ) -> "VisualMigrationBuilder":
        """Drop an index.

        Per rules/dataflow-identifier-safety.md MUST Rule 4, destructive DDL
        requires explicit ``force_drop=True``. Indexes are rebuildable from
        schema but dropping a large production index mid-traffic can cause
        query plan regressions; the flag forces deliberate acknowledgement.
        """
        require_force_drop(f"drop_index({index_name!r})", force_drop)
        if self.dialect == "mysql" and table_name:
            sql_up = (
                f"DROP INDEX {self._quote(index_name)} ON {self._quote(table_name)};"
            )
        else:
            sql_up = f"DROP INDEX {self._quote(index_name)};"

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

    def _create_table_operations(self, table_builder):
        operations = [self._create_table_operation(table_builder)]
        operations.extend(
            self._add_index_operation(index) for index in table_builder.indexes
        )
        if table_builder._comment is not None:
            if self.dialect == "sqlite":
                raise ValueError("SQLite does not support table comments")
            if self.dialect == "postgresql":
                sql = f"COMMENT ON TABLE {self._quote(table_builder.name)} IS {self._literal(table_builder._comment)};"
            else:
                sql = f"ALTER TABLE {self._quote(table_builder.name)} COMMENT = {self._literal(table_builder._comment)};"
            operations.append(
                MigrationOperation(
                    MigrationType.CREATE_TABLE,
                    table_builder.name,
                    "Set table comment",
                    sql,
                    "",
                    {},
                )
            )
        for column in table_builder.columns:
            if column._comment is not None and self.dialect == "postgresql":
                sql = f"COMMENT ON COLUMN {self._quote(table_builder.name)}.{self._quote(column.name)} IS {self._literal(column._comment)};"
                operations.append(
                    MigrationOperation(
                        MigrationType.ADD_COLUMN,
                        table_builder.name,
                        "Set column comment",
                        sql,
                        "",
                        {},
                    )
                )
        return operations

    def _create_table_operation(
        self, table_builder: TableBuilder
    ) -> MigrationOperation:
        """Convert TableBuilder to CREATE TABLE operation."""
        table_def = self._table_builder_to_definition(table_builder)
        sql_up = self._generate_create_table_sql(table_def, table_builder.columns)
        sql_down = f"DROP TABLE IF EXISTS {self._quote(table_builder.name)};"

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
        column_sql = self._generate_column_sql(column_def, column_builder)

        sql_up = f"ALTER TABLE {self._quote(table_name)} ADD COLUMN {column_sql};"
        if column_builder._comment is not None and self.dialect == "postgresql":
            sql_up += f"\nCOMMENT ON COLUMN {self._quote(table_name)}.{self._quote(column_builder.name)} IS {self._literal(column_builder._comment)};"
        sql_down = f"ALTER TABLE {self._quote(table_name)} DROP COLUMN {self._quote(column_builder.name)};"

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
        if any(
            (
                column_builder.is_primary_key,
                column_builder.is_unique,
                column_builder.foreign_key,
                column_builder.check_constraint,
                column_builder._auto_increment,
            )
        ):
            raise ValueError("Constraint changes require explicit migration operations")

        if self.dialect == "postgresql":
            sql_up = self._postgresql_modify_column_sql(table_name, column_def)
            if column_builder._comment is not None:
                sql_up += f"\nCOMMENT ON COLUMN {self._quote(table_name)}.{self._quote(column_builder.name)} IS {self._literal(column_builder._comment)};"
        elif self.dialect == "mysql":
            column_sql = self._generate_column_sql(column_def, column_builder)
            sql_up = (
                f"ALTER TABLE {self._quote(table_name)} MODIFY COLUMN {column_sql};"
            )
        else:  # SQLite
            raise ValueError(
                "SQLite column modification requires an explicit table rebuild"
            )

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
            sql_down = f"DROP INDEX {self._quote(index_builder.name)} ON {self._quote(index_builder.table_name)};"
        else:
            sql_down = f"DROP INDEX {self._quote(index_builder.name)};"

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

    def _generate_create_table_sql(
        self, table_def: TableDefinition, builders=None
    ) -> str:
        """Generate CREATE TABLE SQL from TableDefinition."""
        columns_sql = []
        for index, column in enumerate(table_def.columns):
            columns_sql.append(
                self._generate_column_sql(column, builders[index] if builders else None)
            )
        for constraint in table_def.constraints:
            if constraint["type"] == "foreign_key":
                action = constraint["on_delete"].upper()
                if action not in {
                    "CASCADE",
                    "RESTRICT",
                    "SET NULL",
                    "SET DEFAULT",
                    "NO ACTION",
                }:
                    raise ValueError("Unsupported foreign-key deletion action")
                columns_sql.append(
                    f"FOREIGN KEY ({self._quote(constraint['column'])}) REFERENCES {self._reference_sql(constraint['references'])} ON DELETE {action}"
                )
            elif constraint["type"] == "check":
                columns_sql.append(
                    f"CONSTRAINT {self._quote(constraint['name'])} CHECK ({constraint['condition']})"
                )
            else:
                raise ValueError("Unsupported table constraint")

        sql = f"CREATE TABLE {self._quote(table_def.name)} (\n"
        sql += ",\n".join(f"    {col_sql}" for col_sql in columns_sql)
        sql += "\n);"

        return sql

    def _generate_column_sql(self, column_def: ColumnDefinition, builder=None) -> str:
        """Generate column definition SQL."""
        parts = [self._quote(column_def.name), column_def.type]

        if not column_def.nullable:
            parts.append("NOT NULL")

        if column_def.default is not None:
            parts.append(f"DEFAULT {self._default_sql(column_def.default)}")

        if column_def.primary_key:
            parts.append("PRIMARY KEY")

        if column_def.unique:
            parts.append("UNIQUE")

        if column_def.auto_increment:
            if column_def.type not in ("INTEGER", "BIGINT", "SMALLINT"):
                raise ValueError("Auto-increment requires an integer column")
            if self.dialect == "postgresql":
                parts[1] = {
                    "INTEGER": "SERIAL",
                    "BIGINT": "BIGSERIAL",
                    "SMALLINT": "SMALLSERIAL",
                }[column_def.type]
            elif self.dialect == "mysql":
                parts.append("AUTO_INCREMENT")
            else:
                if column_def.type != "INTEGER" or not column_def.primary_key:
                    raise ValueError(
                        "SQLite auto-increment requires INTEGER PRIMARY KEY"
                    )
                # SQLite requires this immediately after PRIMARY KEY, including
                # when the column also carries a UNIQUE constraint.
                parts.insert(parts.index("PRIMARY KEY") + 1, "AUTOINCREMENT")

        if column_def.foreign_key:
            parts.append(f"REFERENCES {self._reference_sql(column_def.foreign_key)}")
        if builder is not None:
            if builder.check_constraint is not None:
                parts.append(f"CHECK ({builder.check_constraint})")
            if builder._comment is not None:
                if self.dialect == "sqlite":
                    raise ValueError("SQLite does not support column comments")
                if self.dialect == "mysql":
                    parts.append(f"COMMENT {self._literal(builder._comment)}")
        return " ".join(parts)

    def _generate_index_sql(self, index_builder: IndexBuilder) -> str:
        """Generate CREATE INDEX SQL."""
        if not index_builder.columns:
            raise ValueError("An index requires at least one column")
        if self.dialect != "postgresql":
            if index_builder.include_columns:
                raise ValueError("Included index columns require PostgreSQL")
            if index_builder.index_type not in {
                IndexType.BTREE,
                IndexType.UNIQUE,
                IndexType.COMPOSITE,
                IndexType.PARTIAL,
            }:
                raise ValueError("Unsupported index type for this dialect")
            if self.dialect == "mysql" and index_builder.partial_condition:
                raise ValueError("MySQL does not support partial indexes")
        if self.dialect == "postgresql":
            unique_keyword = (
                "UNIQUE "
                if (
                    index_builder._unique
                    or index_builder.index_type == IndexType.UNIQUE
                )
                else ""
            )
            concurrently = ""  # Migration operations execute inside transactions.

            if index_builder.index_type == IndexType.HASH:
                using_clause = "USING hash"
            elif index_builder.index_type == IndexType.GIN:
                using_clause = "USING gin"
            elif index_builder.index_type == IndexType.GIST:
                using_clause = "USING gist"
            else:
                using_clause = ""

            columns_str = ", ".join(map(self._quote, index_builder.columns))
            sql = f"CREATE {unique_keyword}INDEX {concurrently}{self._quote(index_builder.name)} ON {self._quote(index_builder.table_name)}"

            if using_clause:
                sql += f" {using_clause}"

            sql += f" ({columns_str})"

            if index_builder.include_columns:
                sql += f" INCLUDE ({', '.join(map(self._quote, index_builder.include_columns))})"

            if index_builder.partial_condition:
                sql += f" WHERE {index_builder.partial_condition}"

            sql += ";"

        else:
            # MySQL/SQLite
            unique_keyword = (
                "UNIQUE "
                if (
                    index_builder._unique
                    or index_builder.index_type == IndexType.UNIQUE
                )
                else ""
            )
            columns_str = ", ".join(map(self._quote, index_builder.columns))
            sql = f"CREATE {unique_keyword}INDEX {self._quote(index_builder.name)} ON {self._quote(index_builder.table_name)} ({columns_str})"
            if index_builder.partial_condition:
                sql += f" WHERE {index_builder.partial_condition}"
            sql += ";"

        return sql

    def _postgresql_modify_column_sql(
        self, table_name: str, column_def: ColumnDefinition
    ) -> str:
        """Generate PostgreSQL-specific column modification SQL."""
        statements = []

        # Change data type
        statements.append(
            f"ALTER TABLE {self._quote(table_name)} ALTER COLUMN {self._quote(column_def.name)} TYPE {column_def.type};"
        )

        # Change nullable
        if not column_def.nullable:
            statements.append(
                f"ALTER TABLE {self._quote(table_name)} ALTER COLUMN {self._quote(column_def.name)} SET NOT NULL;"
            )
        else:
            statements.append(
                f"ALTER TABLE {self._quote(table_name)} ALTER COLUMN {self._quote(column_def.name)} DROP NOT NULL;"
            )

        # Change default
        if column_def.default is not None:
            default_val = self._default_sql(column_def.default)
            statements.append(
                f"ALTER TABLE {self._quote(table_name)} ALTER COLUMN {self._quote(column_def.name)} SET DEFAULT {default_val};"
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

    def _queue_operation(self, builder, factory):
        # Remember declaration position even when immediate operations follow.
        position = len(self.operations) + len(self._pending_operations)
        self._pending_operations.append((position, factory))
        builder._finalize = self._finalize_pending_operations

    def _finalize_pending_operations(self):
        """Materialize fluent operations once, retaining failures for retry."""
        operations = self.operations.copy()
        offset = 0
        for position, factory in self._pending_operations:
            result = factory()
            resolved = result if isinstance(result, list) else [result]
            operations[position + offset : position + offset] = resolved
            offset += len(resolved) - 1
        self.operations[:] = operations
        self._pending_operations.clear()

    def _reference_sql(self, reference):
        parts = reference.split(".")
        if len(parts) != 2:
            raise ValueError("Foreign-key reference must be table.column")
        return f"{self._quote(parts[0])} ({self._quote(parts[1])})"

    def _literal(self, value):
        if not isinstance(value, str):
            raise TypeError("SQL text literal must be a string")
        if self.dialect == "mysql":
            value = value.replace("\\", "\\\\")
        return "'" + value.replace("'", "''") + "'"

    def _default_sql(self, value):
        if isinstance(value, str):
            if value.upper() in {
                "CURRENT_TIMESTAMP",
                "CURRENT_DATE",
                "CURRENT_TIME",
                "NOW()",
            }:
                return value.upper()
            return self._literal(value)
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, (int, float)):
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Column defaults must be finite")
            return str(value)
        raise TypeError("Unsupported column default type")


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
