"""
DataFlow Multi-Database Support

Provides comprehensive database adapter system for PostgreSQL, MySQL, and SQLite
with dialect-specific SQL generation, type mapping, and feature compatibility.

Key Features:
- Unified API across all databases
- Dialect-specific SQL generation
- Automatic type conversion
- Feature compatibility detection
- Performance optimizations per database
- Migration support across databases
"""

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from ..adapters.connection_parser import ConnectionParser

logger = logging.getLogger(__name__)


class DatabaseDialect(Enum):
    """Supported database dialects."""

    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"

    @classmethod
    def from_url(cls, url: str) -> "DatabaseDialect":
        """Detect dialect from database URL."""
        components = ConnectionParser.parse_connection_string(url)
        scheme = components.get("scheme", "").lower()

        if scheme in [
            "postgresql",
            "postgres",
            "postgresql+asyncpg",
        ]:
            return cls.POSTGRESQL
        elif scheme in ["mysql", "mysql+pymysql", "mysql+mysqldb", "mysql+aiomysql"]:
            return cls.MYSQL
        elif scheme in ["sqlite", "sqlite+aiosqlite"]:
            return cls.SQLITE
        else:
            raise ValueError(f"Unsupported database dialect: {scheme}")


class DatabaseFeature(Enum):
    """Database feature flags for compatibility checking."""

    # Basic features
    TRANSACTIONS = "transactions"
    FOREIGN_KEYS = "foreign_keys"
    INDEXES = "indexes"
    UNIQUE_CONSTRAINTS = "unique_constraints"
    CHECK_CONSTRAINTS = "check_constraints"

    # Advanced features
    PARTIAL_INDEXES = "partial_indexes"
    COVERING_INDEXES = "covering_indexes"
    HASH_INDEXES = "hash_indexes"
    GIN_INDEXES = "gin_indexes"
    FULL_TEXT_SEARCH = "full_text_search"

    # Data types
    JSON_TYPE = "json_type"
    UUID_TYPE = "uuid_type"
    ARRAY_TYPE = "array_type"
    ENUM_TYPE = "enum_type"

    # Operations
    UPSERT = "upsert"
    RETURNING = "returning"
    WITH_CLAUSE = "with_clause"
    WINDOW_FUNCTIONS = "window_functions"

    # Performance
    EXPLAIN_ANALYZE = "explain_analyze"
    QUERY_HINTS = "query_hints"
    PARALLEL_QUERIES = "parallel_queries"

    # Schema operations
    ALTER_COLUMN = "alter_column"
    RENAME_COLUMN = "rename_column"
    DROP_COLUMN = "drop_column"
    ADD_COLUMN_AFTER = "add_column_after"

    # Enterprise features
    PARTITIONING = "partitioning"
    MATERIALIZED_VIEWS = "materialized_views"
    TRIGGERS = "triggers"
    STORED_PROCEDURES = "stored_procedures"


@dataclass
class TypeMapping:
    """Database type mapping configuration."""

    # Standard SQL types to dialect-specific types
    type_map: Dict[str, str]
    # Python types to SQL types
    python_type_map: Dict[type, str]
    # Default lengths for string types
    default_lengths: Dict[str, int]


class DatabaseAdapter(ABC):
    """
    Abstract base class for database adapters.

    Each adapter provides dialect-specific SQL generation and feature support.
    """

    def __init__(self):
        self.dialect = self._get_dialect()
        self.features = self._get_supported_features()
        self.type_mapping = self._get_type_mapping()

    @abstractmethod
    def _get_dialect(self) -> DatabaseDialect:
        """Get the database dialect."""
        pass

    @abstractmethod
    def _get_supported_features(self) -> set[DatabaseFeature]:
        """Get the set of supported features."""
        pass

    @abstractmethod
    def _get_type_mapping(self) -> TypeMapping:
        """Get the type mapping configuration."""
        pass

    def supports_feature(self, feature: DatabaseFeature) -> bool:
        """Check if a feature is supported."""
        return feature in self.features

    def map_type(self, sql_type: str) -> str:
        """Map a standard SQL type to dialect-specific type."""
        return self.type_mapping.type_map.get(sql_type.upper(), sql_type)

    def map_python_type(self, python_type: type) -> str:
        """Map a Python type to SQL type."""
        return self.type_mapping.python_type_map.get(python_type, "VARCHAR")

    @abstractmethod
    def quote_identifier(self, identifier: str) -> str:
        """Quote an identifier (table/column name)."""
        pass

    @abstractmethod
    def get_auto_increment_sql(self) -> str:
        """Get the auto-increment column modifier."""
        pass

    @abstractmethod
    def get_current_timestamp_sql(self) -> str:
        """Get the current timestamp expression."""
        pass

    @abstractmethod
    def get_upsert_sql(
        self,
        table: str,
        columns: List[str],
        values: List[Any],
        conflict_columns: List[str],
        update_columns: Optional[List[str]] = None,
    ) -> Tuple[str, List[Any]]:
        """Generate UPSERT (INSERT ... ON CONFLICT) SQL."""
        pass

    @abstractmethod
    def get_limit_offset_sql(self, limit: Optional[int], offset: Optional[int]) -> str:
        """Generate LIMIT/OFFSET clause."""
        pass

    @abstractmethod
    def get_random_function(self) -> str:
        """Get the random function name."""
        pass

    @abstractmethod
    def get_string_agg_function(self) -> str:
        """Get the string aggregation function."""
        pass

    @abstractmethod
    def get_json_extract_sql(self, column: str, path: str) -> str:
        """Generate JSON extraction SQL."""
        pass

    def get_create_table_sql(
        self,
        table_name: str,
        columns: List[Dict[str, Any]],
        constraints: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Generate CREATE TABLE SQL."""
        sql_parts = [f"CREATE TABLE {self.quote_identifier(table_name)} ("]

        # Add columns
        column_definitions = []
        for col in columns:
            col_def = self._build_column_definition(col)
            column_definitions.append(col_def)

        # Add constraints
        if constraints:
            for constraint in constraints:
                constraint_sql = self._build_constraint_sql(constraint)
                if constraint_sql:
                    column_definitions.append(constraint_sql)

        sql_parts.append(",\n    ".join(column_definitions))
        sql_parts.append(")")

        return "\n".join(sql_parts)

    def _build_column_definition(self, column: Dict[str, Any]) -> str:
        """Build a column definition."""
        parts = [self.quote_identifier(column["name"]), self.map_type(column["type"])]

        # Add length/precision
        if "length" in column:
            parts[-1] += f"({column['length']})"
        elif "precision" in column and "scale" in column:
            parts[-1] += f"({column['precision']},{column['scale']})"

        # Add modifiers
        if column.get("primary_key"):
            parts.append("PRIMARY KEY")
            if column.get("auto_increment"):
                parts.append(self.get_auto_increment_sql())

        if not column.get("nullable", True):
            parts.append("NOT NULL")

        if "default" in column:
            default = column["default"]
            if default == "CURRENT_TIMESTAMP":
                parts.append(f"DEFAULT {self.get_current_timestamp_sql()}")
            elif isinstance(default, str):
                parts.append(f"DEFAULT '{default}'")
            else:
                parts.append(f"DEFAULT {default}")

        if column.get("unique"):
            parts.append("UNIQUE")

        return " ".join(parts)

    def _build_constraint_sql(self, constraint: Dict[str, Any]) -> Optional[str]:
        """Build a constraint definition."""
        constraint_type = constraint.get("type")

        if constraint_type == "primary_key":
            columns = ", ".join(self.quote_identifier(c) for c in constraint["columns"])
            return f"PRIMARY KEY ({columns})"

        elif constraint_type == "foreign_key":
            name = constraint.get("name", f"fk_{constraint['column']}")
            return (
                f"CONSTRAINT {self.quote_identifier(name)} "
                f"FOREIGN KEY ({self.quote_identifier(constraint['column'])}) "
                f"REFERENCES {constraint['references']} "
                f"ON DELETE {constraint.get('on_delete', 'CASCADE')}"
            )

        elif constraint_type == "unique":
            name = constraint.get("name")
            columns = ", ".join(self.quote_identifier(c) for c in constraint["columns"])
            if name:
                return f"CONSTRAINT {self.quote_identifier(name)} UNIQUE ({columns})"
            else:
                return f"UNIQUE ({columns})"

        elif constraint_type == "check" and self.supports_feature(
            DatabaseFeature.CHECK_CONSTRAINTS
        ):
            name = constraint.get("name", "check_constraint")
            return f"CONSTRAINT {self.quote_identifier(name)} CHECK ({constraint['condition']})"

        return None


class PostgreSQLAdapter(DatabaseAdapter):
    """PostgreSQL-specific database adapter."""

    def _get_dialect(self) -> DatabaseDialect:
        return DatabaseDialect.POSTGRESQL

    def _get_supported_features(self) -> set[DatabaseFeature]:
        """PostgreSQL supports almost all features."""
        return {
            # Basic features
            DatabaseFeature.TRANSACTIONS,
            DatabaseFeature.FOREIGN_KEYS,
            DatabaseFeature.INDEXES,
            DatabaseFeature.UNIQUE_CONSTRAINTS,
            DatabaseFeature.CHECK_CONSTRAINTS,
            # Advanced features
            DatabaseFeature.PARTIAL_INDEXES,
            DatabaseFeature.COVERING_INDEXES,
            DatabaseFeature.HASH_INDEXES,
            DatabaseFeature.GIN_INDEXES,
            DatabaseFeature.FULL_TEXT_SEARCH,
            # Data types
            DatabaseFeature.JSON_TYPE,
            DatabaseFeature.UUID_TYPE,
            DatabaseFeature.ARRAY_TYPE,
            DatabaseFeature.ENUM_TYPE,
            # Operations
            DatabaseFeature.UPSERT,
            DatabaseFeature.RETURNING,
            DatabaseFeature.WITH_CLAUSE,
            DatabaseFeature.WINDOW_FUNCTIONS,
            # Performance
            DatabaseFeature.EXPLAIN_ANALYZE,
            DatabaseFeature.PARALLEL_QUERIES,
            # Schema operations
            DatabaseFeature.ALTER_COLUMN,
            DatabaseFeature.RENAME_COLUMN,
            DatabaseFeature.DROP_COLUMN,
            # Enterprise features
            DatabaseFeature.PARTITIONING,
            DatabaseFeature.MATERIALIZED_VIEWS,
            DatabaseFeature.TRIGGERS,
            DatabaseFeature.STORED_PROCEDURES,
        }

    def _get_type_mapping(self) -> TypeMapping:
        return TypeMapping(
            type_map={
                "INTEGER": "INTEGER",
                "BIGINT": "BIGINT",
                "SMALLINT": "SMALLINT",
                "FLOAT": "REAL",
                "DOUBLE": "DOUBLE PRECISION",
                "DECIMAL": "DECIMAL",
                "VARCHAR": "VARCHAR",
                "TEXT": "TEXT",
                "CHAR": "CHAR",
                "BOOLEAN": "BOOLEAN",
                "DATE": "DATE",
                "TIME": "TIME",
                "TIMESTAMP": "TIMESTAMP",
                "DATETIME": "TIMESTAMP",
                "BLOB": "BYTEA",
                "JSON": "JSONB",
                "UUID": "UUID",
            },
            python_type_map={
                int: "INTEGER",
                float: "DOUBLE PRECISION",
                str: "VARCHAR",
                bool: "BOOLEAN",
                bytes: "BYTEA",
            },
            default_lengths={"VARCHAR": 255, "CHAR": 1},
        )

    def quote_identifier(self, identifier: str) -> str:
        """PostgreSQL uses double quotes."""
        return f'"{identifier}"'

    def get_auto_increment_sql(self) -> str:
        """PostgreSQL uses SERIAL."""
        return ""  # SERIAL is a pseudo-type, not a modifier

    def get_current_timestamp_sql(self) -> str:
        """PostgreSQL current timestamp."""
        return "CURRENT_TIMESTAMP"

    def get_upsert_sql(
        self,
        table: str,
        columns: List[str],
        values: List[Any],
        conflict_columns: List[str],
        update_columns: Optional[List[str]] = None,
    ) -> Tuple[str, List[Any]]:
        """PostgreSQL UPSERT using ON CONFLICT."""
        quoted_table = self.quote_identifier(table)
        quoted_columns = [self.quote_identifier(col) for col in columns]
        placeholders = [f"${i+1}" for i in range(len(values))]

        sql = f"""
        INSERT INTO {quoted_table} ({', '.join(quoted_columns)})
        VALUES ({', '.join(placeholders)})
        ON CONFLICT ({', '.join(self.quote_identifier(c) for c in conflict_columns)})
        """

        if update_columns:
            updates = []
            for col in update_columns:
                updates.append(
                    f"{self.quote_identifier(col)} = EXCLUDED.{self.quote_identifier(col)}"
                )
            sql += f"DO UPDATE SET {', '.join(updates)}"
        else:
            sql += "DO NOTHING"

        return sql.strip(), values

    def get_limit_offset_sql(self, limit: Optional[int], offset: Optional[int]) -> str:
        """PostgreSQL LIMIT/OFFSET."""
        parts = []
        if limit is not None:
            parts.append(f"LIMIT {limit}")
        if offset is not None:
            parts.append(f"OFFSET {offset}")
        return " ".join(parts)

    def get_random_function(self) -> str:
        """PostgreSQL random function."""
        return "RANDOM()"

    def get_string_agg_function(self) -> str:
        """PostgreSQL string aggregation."""
        return "STRING_AGG"

    def get_json_extract_sql(self, column: str, path: str) -> str:
        """PostgreSQL JSON extraction using ->> operator."""
        # Split path like "$.user.name" into parts
        parts = path.strip("$").strip(".").split(".")
        result = self.quote_identifier(column)

        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                # Last part: use ->> to get text
                result = f"{result}->>{self._quote_json_key(part)}"
            else:
                # Intermediate parts: use -> to get JSON
                result = f"{result}->{self._quote_json_key(part)}"

        return result

    def _quote_json_key(self, key: str) -> str:
        """Quote a JSON key."""
        return f"'{key}'"

    def _build_column_definition(self, column: Dict[str, Any]) -> str:
        """Override to handle SERIAL type."""
        if column.get("primary_key") and column.get("auto_increment"):
            # Use SERIAL instead of INTEGER for auto-increment
            parts = [self.quote_identifier(column["name"]), "SERIAL PRIMARY KEY"]
            return " ".join(parts)
        return super()._build_column_definition(column)


class MySQLAdapter(DatabaseAdapter):
    """MySQL-specific database adapter."""

    def _get_dialect(self) -> DatabaseDialect:
        return DatabaseDialect.MYSQL

    def _get_supported_features(self) -> set[DatabaseFeature]:
        """MySQL supports most common features."""
        return {
            # Basic features
            DatabaseFeature.TRANSACTIONS,
            DatabaseFeature.FOREIGN_KEYS,
            DatabaseFeature.INDEXES,
            DatabaseFeature.UNIQUE_CONSTRAINTS,
            DatabaseFeature.CHECK_CONSTRAINTS,  # MySQL 8.0+
            # Advanced features
            DatabaseFeature.FULL_TEXT_SEARCH,
            # Data types
            DatabaseFeature.JSON_TYPE,  # MySQL 5.7+
            # Operations
            DatabaseFeature.UPSERT,  # Using INSERT ... ON DUPLICATE KEY
            DatabaseFeature.WITH_CLAUSE,  # MySQL 8.0+
            DatabaseFeature.WINDOW_FUNCTIONS,  # MySQL 8.0+
            # Performance
            DatabaseFeature.EXPLAIN_ANALYZE,
            DatabaseFeature.QUERY_HINTS,
            # Schema operations
            DatabaseFeature.ALTER_COLUMN,
            DatabaseFeature.RENAME_COLUMN,
            DatabaseFeature.DROP_COLUMN,
            DatabaseFeature.ADD_COLUMN_AFTER,
            # Enterprise features
            DatabaseFeature.PARTITIONING,
            DatabaseFeature.TRIGGERS,
            DatabaseFeature.STORED_PROCEDURES,
        }

    def _get_type_mapping(self) -> TypeMapping:
        return TypeMapping(
            type_map={
                "INTEGER": "INT",
                "BIGINT": "BIGINT",
                "SMALLINT": "SMALLINT",
                "FLOAT": "FLOAT",
                "DOUBLE": "DOUBLE",
                "DECIMAL": "DECIMAL",
                "VARCHAR": "VARCHAR",
                "TEXT": "TEXT",
                "CHAR": "CHAR",
                "BOOLEAN": "BOOLEAN",
                "DATE": "DATE",
                "TIME": "TIME",
                "TIMESTAMP": "TIMESTAMP",
                "DATETIME": "DATETIME",
                "BLOB": "BLOB",
                "JSON": "JSON",
                "UUID": "VARCHAR(36)",  # MySQL doesn't have native UUID
            },
            python_type_map={
                int: "INT",
                float: "DOUBLE",
                str: "VARCHAR",
                bool: "BOOLEAN",
                bytes: "BLOB",
            },
            default_lengths={"VARCHAR": 255, "CHAR": 1},
        )

    def quote_identifier(self, identifier: str) -> str:
        """MySQL uses backticks."""
        return f"`{identifier}`"

    def get_auto_increment_sql(self) -> str:
        """MySQL uses AUTO_INCREMENT."""
        return "AUTO_INCREMENT"

    def get_current_timestamp_sql(self) -> str:
        """MySQL current timestamp."""
        return "CURRENT_TIMESTAMP"

    def get_upsert_sql(
        self,
        table: str,
        columns: List[str],
        values: List[Any],
        conflict_columns: List[str],
        update_columns: Optional[List[str]] = None,
    ) -> Tuple[str, List[Any]]:
        """MySQL UPSERT using ON DUPLICATE KEY UPDATE."""
        quoted_table = self.quote_identifier(table)
        quoted_columns = [self.quote_identifier(col) for col in columns]
        placeholders = ["%s" for _ in values]

        sql = f"""
        INSERT INTO {quoted_table} ({', '.join(quoted_columns)})
        VALUES ({', '.join(placeholders)})
        """

        if update_columns:
            updates = []
            for col in update_columns:
                quoted_col = self.quote_identifier(col)
                updates.append(f"{quoted_col} = VALUES({quoted_col})")
            sql += f"ON DUPLICATE KEY UPDATE {', '.join(updates)}"

        return sql.strip(), values

    def get_limit_offset_sql(self, limit: Optional[int], offset: Optional[int]) -> str:
        """MySQL LIMIT/OFFSET."""
        if limit is not None and offset is not None:
            return f"LIMIT {offset}, {limit}"
        elif limit is not None:
            return f"LIMIT {limit}"
        return ""

    def get_random_function(self) -> str:
        """MySQL random function."""
        return "RAND()"

    def get_string_agg_function(self) -> str:
        """MySQL string aggregation."""
        return "GROUP_CONCAT"

    def get_json_extract_sql(self, column: str, path: str) -> str:
        """MySQL JSON extraction using JSON_EXTRACT."""
        return f"JSON_UNQUOTE(JSON_EXTRACT({self.quote_identifier(column)}, '{path}'))"


class SQLiteAdapter(DatabaseAdapter):
    """SQLite-specific database adapter."""

    def _get_dialect(self) -> DatabaseDialect:
        return DatabaseDialect.SQLITE

    def _get_supported_features(self) -> set[DatabaseFeature]:
        """SQLite supports basic features."""
        return {
            # Basic features
            DatabaseFeature.TRANSACTIONS,
            DatabaseFeature.FOREIGN_KEYS,  # Must be enabled
            DatabaseFeature.INDEXES,
            DatabaseFeature.UNIQUE_CONSTRAINTS,
            DatabaseFeature.CHECK_CONSTRAINTS,
            # Advanced features
            DatabaseFeature.PARTIAL_INDEXES,
            DatabaseFeature.FULL_TEXT_SEARCH,  # FTS extension
            # Data types
            DatabaseFeature.JSON_TYPE,  # Via JSON1 extension
            # Operations
            DatabaseFeature.UPSERT,  # SQLite 3.24+
            DatabaseFeature.RETURNING,  # SQLite 3.35+
            DatabaseFeature.WITH_CLAUSE,
            DatabaseFeature.WINDOW_FUNCTIONS,  # SQLite 3.25+
            # Schema operations
            DatabaseFeature.DROP_COLUMN,  # SQLite 3.35+
            DatabaseFeature.RENAME_COLUMN,  # SQLite 3.25+
            # Enterprise features
            DatabaseFeature.TRIGGERS,
        }

    def _get_type_mapping(self) -> TypeMapping:
        return TypeMapping(
            type_map={
                "INTEGER": "INTEGER",
                "BIGINT": "INTEGER",
                "SMALLINT": "INTEGER",
                "FLOAT": "REAL",
                "DOUBLE": "REAL",
                "DECIMAL": "REAL",
                "VARCHAR": "TEXT",
                "TEXT": "TEXT",
                "CHAR": "TEXT",
                "BOOLEAN": "INTEGER",  # 0 or 1
                "DATE": "TEXT",
                "TIME": "TEXT",
                "TIMESTAMP": "TEXT",
                "DATETIME": "TEXT",
                "BLOB": "BLOB",
                "JSON": "TEXT",  # JSON stored as TEXT
                "UUID": "TEXT",
            },
            python_type_map={
                int: "INTEGER",
                float: "REAL",
                str: "TEXT",
                bool: "INTEGER",
                bytes: "BLOB",
            },
            default_lengths={"VARCHAR": 255, "CHAR": 1},
        )

    def quote_identifier(self, identifier: str) -> str:
        """SQLite uses double quotes or square brackets."""
        return f'"{identifier}"'

    def get_auto_increment_sql(self) -> str:
        """SQLite uses AUTOINCREMENT (optional with INTEGER PRIMARY KEY)."""
        return "AUTOINCREMENT"

    def get_current_timestamp_sql(self) -> str:
        """SQLite current timestamp."""
        return "CURRENT_TIMESTAMP"

    def get_upsert_sql(
        self,
        table: str,
        columns: List[str],
        values: List[Any],
        conflict_columns: List[str],
        update_columns: Optional[List[str]] = None,
    ) -> Tuple[str, List[Any]]:
        """SQLite UPSERT using ON CONFLICT (SQLite 3.24+)."""
        quoted_table = self.quote_identifier(table)
        quoted_columns = [self.quote_identifier(col) for col in columns]
        placeholders = ["?" for _ in values]

        sql = f"""
        INSERT INTO {quoted_table} ({', '.join(quoted_columns)})
        VALUES ({', '.join(placeholders)})
        ON CONFLICT ({', '.join(self.quote_identifier(c) for c in conflict_columns)})
        """

        if update_columns:
            updates = []
            for col in update_columns:
                quoted_col = self.quote_identifier(col)
                updates.append(f"{quoted_col} = excluded.{quoted_col}")
            sql += f"DO UPDATE SET {', '.join(updates)}"
        else:
            sql += "DO NOTHING"

        return sql.strip(), values

    def get_limit_offset_sql(self, limit: Optional[int], offset: Optional[int]) -> str:
        """SQLite LIMIT/OFFSET."""
        parts = []
        if limit is not None:
            parts.append(f"LIMIT {limit}")
        if offset is not None:
            parts.append(f"OFFSET {offset}")
        return " ".join(parts)

    def get_random_function(self) -> str:
        """SQLite random function."""
        return "RANDOM()"

    def get_string_agg_function(self) -> str:
        """SQLite string aggregation."""
        return "GROUP_CONCAT"

    def get_json_extract_sql(self, column: str, path: str) -> str:
        """SQLite JSON extraction using json_extract."""
        return f"json_extract({self.quote_identifier(column)}, '{path}')"


class SQLGenerator:
    """
    High-level SQL generator that uses database adapters for dialect-specific SQL.
    """

    def __init__(self, adapter: DatabaseAdapter):
        self.adapter = adapter

    def create_table(
        self,
        table_name: str,
        columns: List[Dict[str, Any]],
        constraints: Optional[List[Dict[str, Any]]] = None,
        if_not_exists: bool = True,
    ) -> str:
        """Generate CREATE TABLE SQL."""
        create_clause = "CREATE TABLE"
        if if_not_exists:
            create_clause += " IF NOT EXISTS"

        sql = self.adapter.get_create_table_sql(table_name, columns, constraints)
        return sql.replace("CREATE TABLE", create_clause, 1)

    def create_index(
        self,
        index_name: str,
        table_name: str,
        columns: List[str],
        unique: bool = False,
        if_not_exists: bool = True,
        where_clause: Optional[str] = None,
        index_type: Optional[str] = None,
        include_columns: Optional[List[str]] = None,
    ) -> str:
        """Generate CREATE INDEX SQL."""
        parts = ["CREATE"]

        if unique:
            parts.append("UNIQUE")

        parts.append("INDEX")

        if if_not_exists:
            parts.append("IF NOT EXISTS")

        parts.append(self.adapter.quote_identifier(index_name))
        parts.append("ON")
        parts.append(self.adapter.quote_identifier(table_name))

        # Index type (PostgreSQL)
        if index_type and self.adapter.dialect == DatabaseDialect.POSTGRESQL:
            parts.append(f"USING {index_type}")

        # Column list
        quoted_columns = [self.adapter.quote_identifier(col) for col in columns]
        parts.append(f"({', '.join(quoted_columns)})")

        # Include columns (PostgreSQL covering index)
        if include_columns and self.adapter.supports_feature(
            DatabaseFeature.COVERING_INDEXES
        ):
            quoted_include = [
                self.adapter.quote_identifier(col) for col in include_columns
            ]
            parts.append(f"INCLUDE ({', '.join(quoted_include)})")

        # Partial index
        if where_clause and self.adapter.supports_feature(
            DatabaseFeature.PARTIAL_INDEXES
        ):
            parts.append(f"WHERE {where_clause}")

        return " ".join(parts)

    def insert(
        self,
        table_name: str,
        columns: List[str],
        values: List[Any],
        returning: Optional[List[str]] = None,
    ) -> Tuple[str, List[Any]]:
        """Generate INSERT SQL."""
        quoted_table = self.adapter.quote_identifier(table_name)
        quoted_columns = [self.adapter.quote_identifier(col) for col in columns]

        if self.adapter.dialect == DatabaseDialect.POSTGRESQL:
            placeholders = [f"${i+1}" for i in range(len(values))]
        else:
            placeholders = [
                "?" if self.adapter.dialect == DatabaseDialect.SQLITE else "%s"
                for _ in values
            ]

        sql = f"""
        INSERT INTO {quoted_table} ({', '.join(quoted_columns)})
        VALUES ({', '.join(placeholders)})
        """

        if returning and self.adapter.supports_feature(DatabaseFeature.RETURNING):
            quoted_returning = [self.adapter.quote_identifier(col) for col in returning]
            sql += f" RETURNING {', '.join(quoted_returning)}"

        return sql.strip(), values

    def update(
        self,
        table_name: str,
        set_columns: Dict[str, Any],
        where_clause: Optional[str] = None,
        returning: Optional[List[str]] = None,
    ) -> Tuple[str, List[Any]]:
        """Generate UPDATE SQL."""
        quoted_table = self.adapter.quote_identifier(table_name)

        set_parts = []
        values = []
        param_index = 1

        for column, value in set_columns.items():
            quoted_col = self.adapter.quote_identifier(column)
            if self.adapter.dialect == DatabaseDialect.POSTGRESQL:
                set_parts.append(f"{quoted_col} = ${param_index}")
                param_index += 1
            else:
                placeholder = (
                    "?" if self.adapter.dialect == DatabaseDialect.SQLITE else "%s"
                )
                set_parts.append(f"{quoted_col} = {placeholder}")
            values.append(value)

        sql = f"UPDATE {quoted_table} SET {', '.join(set_parts)}"

        if where_clause:
            sql += f" WHERE {where_clause}"

        if returning and self.adapter.supports_feature(DatabaseFeature.RETURNING):
            quoted_returning = [self.adapter.quote_identifier(col) for col in returning]
            sql += f" RETURNING {', '.join(quoted_returning)}"

        return sql, values

    def delete(
        self,
        table_name: str,
        where_clause: Optional[str] = None,
        returning: Optional[List[str]] = None,
    ) -> str:
        """Generate DELETE SQL."""
        quoted_table = self.adapter.quote_identifier(table_name)

        sql = f"DELETE FROM {quoted_table}"

        if where_clause:
            sql += f" WHERE {where_clause}"

        if returning and self.adapter.supports_feature(DatabaseFeature.RETURNING):
            quoted_returning = [self.adapter.quote_identifier(col) for col in returning]
            sql += f" RETURNING {', '.join(quoted_returning)}"

        return sql

    def select(
        self,
        table_name: str,
        columns: Optional[List[str]] = None,
        where_clause: Optional[str] = None,
        order_by: Optional[List[Tuple[str, str]]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        group_by: Optional[List[str]] = None,
        having_clause: Optional[str] = None,
        joins: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Generate SELECT SQL."""
        # SELECT clause
        if columns:
            quoted_columns = [self.adapter.quote_identifier(col) for col in columns]
            select_clause = f"SELECT {', '.join(quoted_columns)}"
        else:
            select_clause = "SELECT *"

        # FROM clause
        from_clause = f"FROM {self.adapter.quote_identifier(table_name)}"

        # JOIN clauses
        join_clauses = []
        if joins:
            for join in joins:
                join_type = join.get("type", "INNER").upper()
                join_table = self.adapter.quote_identifier(join["table"])
                join_condition = join["on"]
                join_clauses.append(
                    f"{join_type} JOIN {join_table} ON {join_condition}"
                )

        # WHERE clause
        where_part = f"WHERE {where_clause}" if where_clause else ""

        # GROUP BY clause
        group_by_part = ""
        if group_by:
            quoted_group_by = [self.adapter.quote_identifier(col) for col in group_by]
            group_by_part = f"GROUP BY {', '.join(quoted_group_by)}"

        # HAVING clause
        having_part = f"HAVING {having_clause}" if having_clause else ""

        # ORDER BY clause
        order_by_part = ""
        if order_by:
            order_parts = []
            for column, direction in order_by:
                quoted_col = self.adapter.quote_identifier(column)
                order_parts.append(f"{quoted_col} {direction.upper()}")
            order_by_part = f"ORDER BY {', '.join(order_parts)}"

        # LIMIT/OFFSET
        limit_offset_part = self.adapter.get_limit_offset_sql(limit, offset)

        # Combine all parts
        sql_parts = [select_clause, from_clause]
        sql_parts.extend(join_clauses)

        if where_part:
            sql_parts.append(where_part)
        if group_by_part:
            sql_parts.append(group_by_part)
        if having_part:
            sql_parts.append(having_part)
        if order_by_part:
            sql_parts.append(order_by_part)
        if limit_offset_part:
            sql_parts.append(limit_offset_part)

        return "\n".join(sql_parts)


def get_database_adapter(dialect: Union[str, DatabaseDialect]) -> DatabaseAdapter:
    """
    Get the appropriate database adapter for a dialect.

    Args:
        dialect: Database dialect string or enum

    Returns:
        Database adapter instance
    """
    if isinstance(dialect, str):
        dialect = DatabaseDialect(dialect.lower())

    adapters = {
        DatabaseDialect.POSTGRESQL: PostgreSQLAdapter,
        DatabaseDialect.MYSQL: MySQLAdapter,
        DatabaseDialect.SQLITE: SQLiteAdapter,
    }

    adapter_class = adapters.get(dialect)
    if not adapter_class:
        raise ValueError(f"Unsupported database dialect: {dialect}")

    return adapter_class()


def detect_dialect(url: str) -> DatabaseDialect:
    """
    Detect database dialect from connection URL.

    Args:
        url: Database connection URL

    Returns:
        Detected database dialect
    """
    return DatabaseDialect.from_url(url)
