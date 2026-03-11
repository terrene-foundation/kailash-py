"""
SQL Dialect Abstraction Layer

Provides database-specific SQL generation for DataFlow operations.
Eliminates inline database type checks and consolidates SQL generation logic.

Architecture:
    SQLDialectFactory.get_dialect(database_type)
          ↓
    ┌─────────┬─────────┬────────┐
    ▼         ▼         ▼        ▼
PostgreSQL  SQLite   MySQL   MongoDB
Dialect     Dialect  Dialect  Dialect
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class UpsertQuery:
    """
    Result of building an upsert query.

    Attributes:
        query: The SQL query string
        params: Query parameters as a dictionary
        supports_native_flag: Whether database natively detects INSERT vs UPDATE
                             True for PostgreSQL (xmax), False for SQLite (requires pre-check)
    """

    query: str
    params: Dict[str, Any]
    supports_native_flag: bool


class SQLDialect(ABC):
    """
    Abstract base class for database-specific SQL dialects.

    Each database dialect implements its own SQL generation logic
    for operations like upsert, bulk operations, etc.
    """

    @abstractmethod
    def build_upsert_query(
        self,
        table_name: str,
        insert_data: Dict[str, Any],
        update_data: Dict[str, Any],
        conflict_columns: List[str],
        has_updated_at: bool = False,
    ) -> UpsertQuery:
        """
        Build database-specific upsert query.

        Args:
            table_name: Name of the table
            insert_data: Data to insert if record doesn't exist
            update_data: Data to update if record exists
            conflict_columns: Columns that define uniqueness for conflict detection
            has_updated_at: Whether the model has an updated_at timestamp field

        Returns:
            UpsertQuery with query string, parameters, and native flag support info
        """
        pass

    @abstractmethod
    def build_bulk_upsert_query(
        self,
        table_name: str,
        records: List[Dict[str, Any]],
        conflict_columns: List[str],
        update_fields: List[str],
        has_updated_at: bool = False,
    ) -> UpsertQuery:
        """
        Build database-specific bulk upsert query.

        Args:
            table_name: Name of the table
            records: List of records to upsert
            conflict_columns: Columns that define uniqueness for conflict detection
            update_fields: Fields to update on conflict
            has_updated_at: Whether the model has an updated_at timestamp field

        Returns:
            UpsertQuery with query string, parameters, and native flag support info
        """
        pass


class PostgreSQLDialect(SQLDialect):
    """
    PostgreSQL dialect with xmax-based INSERT/UPDATE detection.

    PostgreSQL natively provides xmax column for MVCC which allows
    detecting whether an upsert performed an INSERT or UPDATE:
    - xmax = 0: INSERT occurred (new row)
    - xmax > 0: UPDATE occurred (existing row modified)
    """

    def build_upsert_query(
        self,
        table_name: str,
        insert_data: Dict[str, Any],
        update_data: Dict[str, Any],
        conflict_columns: List[str],
        has_updated_at: bool = False,
    ) -> UpsertQuery:
        """Build PostgreSQL upsert with xmax detection."""

        # Build INSERT clause
        insert_columns = list(insert_data.keys())
        insert_placeholders = [f":p{i}" for i in range(len(insert_columns))]

        # Build ON CONFLICT clause
        conflict_cols_str = ", ".join(conflict_columns)

        # Build UPDATE clause
        update_clauses = []
        for col in update_data.keys():
            if col not in conflict_columns and col != "id":
                update_clauses.append(f"{col} = EXCLUDED.{col}")

        # Add updated_at if present
        if has_updated_at:
            update_clauses.append("updated_at = CURRENT_TIMESTAMP")

        update_clause_str = (
            ", ".join(update_clauses) if update_clauses else "id = EXCLUDED.id"
        )

        # Build complete query with xmax flag
        query = f"""
            INSERT INTO {table_name} ({", ".join(insert_columns)})
            VALUES ({", ".join(insert_placeholders)})
            ON CONFLICT ({conflict_cols_str})
            DO UPDATE SET {update_clause_str}
            RETURNING *, (xmax = 0) AS _upsert_inserted
        """

        # Build parameters
        params = {f"p{i}": insert_data[col] for i, col in enumerate(insert_columns)}

        return UpsertQuery(
            query=query.strip(),
            params=params,
            supports_native_flag=True,  # PostgreSQL has xmax
        )

    def build_bulk_upsert_query(
        self,
        table_name: str,
        records: List[Dict[str, Any]],
        conflict_columns: List[str],
        update_fields: List[str],
        has_updated_at: bool = False,
    ) -> UpsertQuery:
        """Build PostgreSQL bulk upsert with xmax detection."""

        if not records:
            raise ValueError("Cannot build bulk upsert query with empty records list")

        # Get columns from first record
        columns = list(records[0].keys())

        # Build VALUES clause with placeholders
        values_clauses = []
        params = {}
        param_idx = 0

        for record in records:
            placeholders = []
            for col in columns:
                param_key = f"p{param_idx}"
                placeholders.append(f":{param_key}")
                params[param_key] = record[col]
                param_idx += 1
            values_clauses.append(f"({', '.join(placeholders)})")

        values_str = ",\n            ".join(values_clauses)

        # Build ON CONFLICT clause
        conflict_cols_str = ", ".join(conflict_columns)

        # Build UPDATE clause
        update_clauses = []
        for field in update_fields:
            if field not in conflict_columns and field != "id":
                update_clauses.append(f"{field} = EXCLUDED.{field}")

        if has_updated_at:
            update_clauses.append("updated_at = CURRENT_TIMESTAMP")

        update_clause_str = (
            ", ".join(update_clauses) if update_clauses else "id = EXCLUDED.id"
        )

        # Build complete query
        query = f"""
            INSERT INTO {table_name} ({", ".join(columns)})
            VALUES
            {values_str}
            ON CONFLICT ({conflict_cols_str})
            DO UPDATE SET {update_clause_str}
            RETURNING id, (xmax = 0) AS inserted
        """

        return UpsertQuery(
            query=query.strip(),
            params=params,
            supports_native_flag=True,  # PostgreSQL has xmax
        )


class SQLiteDialect(SQLDialect):
    """
    SQLite dialect without xmax support.

    SQLite doesn't have PostgreSQL's xmax column, so we use:
    1. Pre-check query to determine if record exists
    2. Standard upsert without INSERT/UPDATE detection in RETURNING clause
    """

    def build_upsert_query(
        self,
        table_name: str,
        insert_data: Dict[str, Any],
        update_data: Dict[str, Any],
        conflict_columns: List[str],
        has_updated_at: bool = False,
    ) -> UpsertQuery:
        """Build SQLite upsert without xmax (requires pre-check)."""

        # Build INSERT clause
        insert_columns = list(insert_data.keys())
        insert_placeholders = [f":p{i}" for i in range(len(insert_columns))]

        # Build ON CONFLICT clause
        conflict_cols_str = ", ".join(conflict_columns)

        # Build UPDATE clause
        update_clauses = []
        for col in update_data.keys():
            if col not in conflict_columns and col != "id":
                update_clauses.append(f"{col} = EXCLUDED.{col}")

        # Add updated_at if present
        if has_updated_at:
            update_clauses.append("updated_at = CURRENT_TIMESTAMP")

        update_clause_str = (
            ", ".join(update_clauses) if update_clauses else "id = EXCLUDED.id"
        )

        # Build complete query WITHOUT xmax (SQLite doesn't support it)
        query = f"""
            INSERT INTO {table_name} ({", ".join(insert_columns)})
            VALUES ({", ".join(insert_placeholders)})
            ON CONFLICT ({conflict_cols_str})
            DO UPDATE SET {update_clause_str}
            RETURNING *
        """

        # Build parameters
        params = {f"p{i}": insert_data[col] for i, col in enumerate(insert_columns)}

        return UpsertQuery(
            query=query.strip(),
            params=params,
            supports_native_flag=False,  # SQLite needs pre-check for INSERT/UPDATE detection
        )

    def build_bulk_upsert_query(
        self,
        table_name: str,
        records: List[Dict[str, Any]],
        conflict_columns: List[str],
        update_fields: List[str],
        has_updated_at: bool = False,
    ) -> UpsertQuery:
        """Build SQLite bulk upsert without xmax detection."""

        if not records:
            raise ValueError("Cannot build bulk upsert query with empty records list")

        # Get columns from first record
        columns = list(records[0].keys())

        # Build VALUES clause with placeholders
        values_clauses = []
        params = {}
        param_idx = 0

        for record in records:
            placeholders = []
            for col in columns:
                param_key = f"p{param_idx}"
                placeholders.append(f":{param_key}")
                params[param_key] = record[col]
                param_idx += 1
            values_clauses.append(f"({', '.join(placeholders)})")

        values_str = ",\n            ".join(values_clauses)

        # Build ON CONFLICT clause
        conflict_cols_str = ", ".join(conflict_columns)

        # Build UPDATE clause
        update_clauses = []
        for field in update_fields:
            if field not in conflict_columns and field != "id":
                update_clauses.append(f"{field} = EXCLUDED.{field}")

        if has_updated_at:
            update_clauses.append("updated_at = CURRENT_TIMESTAMP")

        update_clause_str = (
            ", ".join(update_clauses) if update_clauses else "id = EXCLUDED.id"
        )

        # Build complete query WITHOUT xmax flag (use constant 1 as placeholder)
        query = f"""
            INSERT INTO {table_name} ({", ".join(columns)})
            VALUES
            {values_str}
            ON CONFLICT ({conflict_cols_str})
            DO UPDATE SET {update_clause_str}
            RETURNING id, 1 AS inserted
        """

        return UpsertQuery(
            query=query.strip(),
            params=params,
            supports_native_flag=False,  # SQLite needs pre-check
        )


class MySQLDialect(SQLDialect):
    """
    MySQL dialect using ON DUPLICATE KEY UPDATE.

    MySQL uses ON DUPLICATE KEY UPDATE instead of ON CONFLICT.
    Uses ROW_COUNT() function to detect INSERT (1) vs UPDATE (2).
    """

    def build_upsert_query(
        self,
        table_name: str,
        insert_data: Dict[str, Any],
        update_data: Dict[str, Any],
        conflict_columns: List[str],
        has_updated_at: bool = False,
    ) -> UpsertQuery:
        """Build MySQL upsert with ON DUPLICATE KEY UPDATE."""

        # Build INSERT clause
        insert_columns = list(insert_data.keys())
        insert_placeholders = [f":p{i}" for i in range(len(insert_columns))]

        # Build UPDATE clause
        update_clauses = []
        for col in update_data.keys():
            if col not in conflict_columns and col != "id":
                update_clauses.append(f"{col} = VALUES({col})")

        # Add updated_at if present
        if has_updated_at:
            update_clauses.append("updated_at = CURRENT_TIMESTAMP")

        update_clause_str = (
            ", ".join(update_clauses) if update_clauses else "id = VALUES(id)"
        )

        # Build complete query
        # Note: MySQL doesn't have RETURNING clause, needs separate SELECT
        query = f"""
            INSERT INTO {table_name} ({", ".join(insert_columns)})
            VALUES ({", ".join(insert_placeholders)})
            ON DUPLICATE KEY UPDATE {update_clause_str}
        """

        # Build parameters
        params = {f"p{i}": insert_data[col] for i, col in enumerate(insert_columns)}

        return UpsertQuery(
            query=query.strip(),
            params=params,
            supports_native_flag=False,  # MySQL needs ROW_COUNT() check
        )

    def build_bulk_upsert_query(
        self,
        table_name: str,
        records: List[Dict[str, Any]],
        conflict_columns: List[str],
        update_fields: List[str],
        has_updated_at: bool = False,
    ) -> UpsertQuery:
        """Build MySQL bulk upsert with ON DUPLICATE KEY UPDATE."""

        if not records:
            raise ValueError("Cannot build bulk upsert query with empty records list")

        # Get columns from first record
        columns = list(records[0].keys())

        # Build VALUES clause with placeholders
        values_clauses = []
        params = {}
        param_idx = 0

        for record in records:
            placeholders = []
            for col in columns:
                param_key = f"p{param_idx}"
                placeholders.append(f":{param_key}")
                params[param_key] = record[col]
                param_idx += 1
            values_clauses.append(f"({', '.join(placeholders)})")

        values_str = ",\n            ".join(values_clauses)

        # Build UPDATE clause
        update_clauses = []
        for field in update_fields:
            if field not in conflict_columns and field != "id":
                update_clauses.append(f"{field} = VALUES({field})")

        if has_updated_at:
            update_clauses.append("updated_at = CURRENT_TIMESTAMP")

        update_clause_str = (
            ", ".join(update_clauses) if update_clauses else "id = VALUES(id)"
        )

        # Build complete query
        query = f"""
            INSERT INTO {table_name} ({", ".join(columns)})
            VALUES
            {values_str}
            ON DUPLICATE KEY UPDATE {update_clause_str}
        """

        return UpsertQuery(
            query=query.strip(),
            params=params,
            supports_native_flag=False,  # MySQL needs ROW_COUNT() check
        )


class SQLDialectFactory:
    """
    Factory for creating SQL dialect instances.

    Usage:
        dialect = SQLDialectFactory.get_dialect("postgresql")
        upsert_query = dialect.build_upsert_query(...)
    """

    _dialects = {
        "postgresql": PostgreSQLDialect,
        "sqlite": SQLiteDialect,
        "mysql": MySQLDialect,
    }

    @classmethod
    def get_dialect(cls, database_type: str) -> SQLDialect:
        """
        Get SQL dialect instance for the specified database type.

        Args:
            database_type: Database type (postgresql, sqlite, mysql)

        Returns:
            SQLDialect instance for the database

        Raises:
            ValueError: If database type is not supported
        """
        database_type_lower = database_type.lower()

        if database_type_lower not in cls._dialects:
            raise ValueError(
                f"Unsupported database type: {database_type}. "
                f"Supported types: {', '.join(cls._dialects.keys())}"
            )

        return cls._dialects[database_type_lower]()

    @classmethod
    def register_dialect(cls, database_type: str, dialect_class: type) -> None:
        """
        Register a custom SQL dialect.

        Args:
            database_type: Database type identifier
            dialect_class: SQLDialect subclass

        Example:
            class MongoDBDialect(SQLDialect):
                ...

            SQLDialectFactory.register_dialect("mongodb", MongoDBDialect)
        """
        if not issubclass(dialect_class, SQLDialect):
            raise TypeError(
                f"dialect_class must be a subclass of SQLDialect, got {dialect_class}"
            )

        cls._dialects[database_type.lower()] = dialect_class

    @classmethod
    def get_supported_databases(cls) -> List[str]:
        """Get list of supported database types."""
        return list(cls._dialects.keys())
