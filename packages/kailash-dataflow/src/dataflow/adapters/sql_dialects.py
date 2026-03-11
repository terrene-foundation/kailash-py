"""
SQL Dialect Handling

Utilities for handling SQL dialect differences between databases.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


class SQLDialect(ABC):
    """Abstract base class for SQL dialects."""

    @abstractmethod
    def get_parameter_placeholder(self, position: int) -> str:
        """Get parameter placeholder for given position."""
        pass

    @abstractmethod
    def quote_identifier(self, identifier: str) -> str:
        """Quote database identifier (table name, column name, etc.)."""
        pass

    @abstractmethod
    def get_limit_clause(self, limit: int, offset: int = 0) -> str:
        """Get LIMIT clause for pagination."""
        pass

    @abstractmethod
    def get_type_mapping(self) -> Dict[str, str]:
        """Get type mapping from generic to database-specific types."""
        pass

    @abstractmethod
    def supports_feature(self, feature: str) -> bool:
        """Check if dialect supports a specific feature."""
        pass


class PostgreSQLDialect(SQLDialect):
    """PostgreSQL SQL dialect."""

    def get_parameter_placeholder(self, position: int) -> str:
        """PostgreSQL uses $1, $2, etc."""
        return f"${position}"

    def quote_identifier(self, identifier: str) -> str:
        """PostgreSQL uses double quotes for identifiers."""
        return f'"{identifier}"'

    def get_limit_clause(self, limit: int, offset: int = 0) -> str:
        """PostgreSQL LIMIT/OFFSET clause."""
        clause = f"LIMIT {limit}"
        if offset > 0:
            clause += f" OFFSET {offset}"
        return clause

    def get_type_mapping(self) -> Dict[str, str]:
        """PostgreSQL type mapping."""
        return {
            "integer": "INTEGER",
            "bigint": "BIGINT",
            "smallint": "SMALLINT",
            "decimal": "DECIMAL",
            "numeric": "NUMERIC",
            "real": "REAL",
            "double": "DOUBLE PRECISION",
            "varchar": "VARCHAR",
            "char": "CHAR",
            "text": "TEXT",
            "boolean": "BOOLEAN",
            "date": "DATE",
            "time": "TIME",
            "timestamp": "TIMESTAMP",
            "timestamptz": "TIMESTAMP WITH TIME ZONE",
            "json": "JSON",
            "jsonb": "JSONB",
            "uuid": "UUID",
            "bytea": "BYTEA",
            "array": "ARRAY",
            "hstore": "HSTORE",
        }

    def supports_feature(self, feature: str) -> bool:
        """PostgreSQL feature support."""
        features = {
            "json": True,
            "arrays": True,
            "regex": True,
            "window_functions": True,
            "cte": True,
            "upsert": True,
            "returning": True,
            "full_outer_join": True,
            "lateral_join": True,
            "recursive_cte": True,
            "intersect": True,
            "except": True,
        }
        return features.get(feature, False)


class MySQLDialect(SQLDialect):
    """MySQL SQL dialect."""

    def get_parameter_placeholder(self, position: int) -> str:
        """MySQL uses %s for all parameters."""
        return "%s"

    def quote_identifier(self, identifier: str) -> str:
        """MySQL uses backticks for identifiers."""
        return f"`{identifier}`"

    def get_limit_clause(self, limit: int, offset: int = 0) -> str:
        """MySQL LIMIT clause."""
        if offset > 0:
            return f"LIMIT {offset}, {limit}"
        return f"LIMIT {limit}"

    def get_type_mapping(self) -> Dict[str, str]:
        """MySQL type mapping."""
        return {
            "integer": "INT",
            "bigint": "BIGINT",
            "smallint": "SMALLINT",
            "decimal": "DECIMAL",
            "numeric": "DECIMAL",
            "real": "FLOAT",
            "double": "DOUBLE",
            "varchar": "VARCHAR",
            "char": "CHAR",
            "text": "TEXT",
            "boolean": "BOOLEAN",
            "date": "DATE",
            "time": "TIME",
            "timestamp": "TIMESTAMP",
            "datetime": "DATETIME",
            "json": "JSON",
            "binary": "BINARY",
            "varbinary": "VARBINARY",
            "blob": "BLOB",
            "longtext": "LONGTEXT",
        }

    def supports_feature(self, feature: str) -> bool:
        """MySQL feature support."""
        features = {
            "json": True,  # MySQL 5.7+
            "arrays": False,
            "regex": True,
            "window_functions": True,  # MySQL 8.0+
            "cte": True,  # MySQL 8.0+
            "upsert": True,  # INSERT ... ON DUPLICATE KEY UPDATE
            "returning": False,  # Not supported
            "full_outer_join": False,  # Not supported
            "lateral_join": True,  # MySQL 8.0+
            "recursive_cte": True,  # MySQL 8.0+
            "intersect": False,  # Not supported
            "except": False,  # Not supported
        }
        return features.get(feature, False)


class SQLiteDialect(SQLDialect):
    """SQLite SQL dialect."""

    def get_parameter_placeholder(self, position: int) -> str:
        """SQLite uses ? for all parameters."""
        return "?"

    def quote_identifier(self, identifier: str) -> str:
        """SQLite uses double quotes for identifiers."""
        return f'"{identifier}"'

    def get_limit_clause(self, limit: int, offset: int = 0) -> str:
        """SQLite LIMIT/OFFSET clause."""
        clause = f"LIMIT {limit}"
        if offset > 0:
            clause += f" OFFSET {offset}"
        return clause

    def get_type_mapping(self) -> Dict[str, str]:
        """SQLite type mapping (note: SQLite has type affinity)."""
        return {
            "integer": "INTEGER",
            "bigint": "INTEGER",
            "smallint": "INTEGER",
            "decimal": "REAL",
            "numeric": "NUMERIC",
            "real": "REAL",
            "double": "REAL",
            "varchar": "TEXT",
            "char": "TEXT",
            "text": "TEXT",
            "boolean": "INTEGER",  # SQLite stores as 0/1
            "date": "TEXT",  # SQLite stores as ISO string
            "time": "TEXT",
            "timestamp": "TEXT",
            "datetime": "TEXT",
            "json": "TEXT",  # SQLite 3.38+ has JSON functions
            "blob": "BLOB",
        }

    def supports_feature(self, feature: str) -> bool:
        """SQLite feature support."""
        features = {
            "json": True,  # SQLite 3.38+
            "arrays": False,
            "regex": False,  # Requires extension
            "window_functions": True,  # SQLite 3.25+
            "cte": True,
            "upsert": True,  # INSERT ... ON CONFLICT
            "returning": True,  # SQLite 3.35+
            "full_outer_join": False,  # Not supported
            "lateral_join": False,  # Not supported
            "recursive_cte": True,
            "intersect": True,
            "except": True,
        }
        return features.get(feature, False)


class DialectManager:
    """Manager for SQL dialects."""

    def __init__(self):
        self.dialects = {
            "postgresql": PostgreSQLDialect(),
            "mysql": MySQLDialect(),
            "sqlite": SQLiteDialect(),
        }

    def get_dialect(self, database_type: str) -> SQLDialect:
        """Get SQL dialect for database type."""
        return self.dialects.get(database_type)

    def convert_query_parameters(
        self, query: str, params: List[Any], source_dialect: str, target_dialect: str
    ) -> Tuple[str, List[Any]]:
        """
        Convert query parameters between dialects.

        Args:
            query: SQL query with parameters
            params: Query parameters
            source_dialect: Source dialect name
            target_dialect: Target dialect name

        Returns:
            Tuple of (converted_query, converted_params)
        """
        source = self.get_dialect(source_dialect)
        target = self.get_dialect(target_dialect)

        if not source or not target:
            return query, params

        # Convert parameter placeholders
        converted_query = query
        param_position = 1

        # Replace source placeholders with target placeholders
        while True:
            source_placeholder = source.get_parameter_placeholder(param_position)
            target_placeholder = target.get_parameter_placeholder(param_position)

            if source_placeholder not in converted_query:
                break

            converted_query = converted_query.replace(
                source_placeholder, target_placeholder, 1
            )
            param_position += 1

        return converted_query, params

    def check_feature_compatibility(
        self, feature: str, source_dialect: str, target_dialect: str
    ) -> bool:
        """
        Check if a feature is compatible between dialects.

        Args:
            feature: Feature to check
            source_dialect: Source dialect name
            target_dialect: Target dialect name

        Returns:
            True if feature is supported in both dialects
        """
        source = self.get_dialect(source_dialect)
        target = self.get_dialect(target_dialect)

        if not source or not target:
            return False

        return source.supports_feature(feature) and target.supports_feature(feature)

    def get_migration_compatibility(
        self, source_dialect: str, target_dialect: str
    ) -> Dict[str, bool]:
        """
        Get compatibility matrix for migration between dialects.

        Args:
            source_dialect: Source dialect name
            target_dialect: Target dialect name

        Returns:
            Dictionary with feature compatibility
        """
        source = self.get_dialect(source_dialect)
        target = self.get_dialect(target_dialect)

        if not source or not target:
            return {}

        # Common features to check
        features = [
            "json",
            "arrays",
            "regex",
            "window_functions",
            "cte",
            "upsert",
            "returning",
            "full_outer_join",
            "lateral_join",
            "recursive_cte",
            "intersect",
            "except",
        ]

        compatibility = {}
        for feature in features:
            compatibility[feature] = source.supports_feature(
                feature
            ) and target.supports_feature(feature)

        return compatibility
