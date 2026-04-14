"""
Canonical SQL Dialect Module

Single source of truth for all SQL dialect differences.
Each dialect exposes quoting, type mapping, DDL generation,
and feature support methods.

Architecture:
    SQLDialect (ABC)
    ├── PostgreSQLDialect
    ├── MySQLDialect
    └── SQLiteDialect
"""

import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple

from .exceptions import InvalidIdentifierError

logger = logging.getLogger(__name__)

_SAFE_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class SQLDialect(ABC):
    """Abstract base class for SQL dialects.

    Every database adapter delegates dialect-specific SQL generation
    to a subclass of this class. Methods here replace the scattered
    inline checks that previously lived in individual adapters.
    """

    @abstractmethod
    def get_parameter_placeholder(self, position: int) -> str:
        """Get parameter placeholder for given position.

        PostgreSQL uses ``$1``, MySQL uses ``%s``, SQLite uses ``?``.
        """

    @abstractmethod
    def quote_identifier(self, name: str) -> str:
        """Validate and quote a SQL identifier to prevent injection.

        Raises:
            InvalidIdentifierError: If *name* contains unsafe characters.
        """

    @abstractmethod
    def get_type_mapping(self) -> Dict[str, str]:
        """Map generic type names to database-specific type names."""

    @abstractmethod
    def supports_feature(self, feature: str) -> bool:
        """Return whether *feature* is supported by this dialect."""

    # ------------------------------------------------------------------
    # Concrete helpers (common signatures, dialect-appropriate output)
    # ------------------------------------------------------------------

    @abstractmethod
    def blob_type(self) -> str:
        """Binary large object column type."""

    @abstractmethod
    def current_timestamp(self) -> str:
        """Expression for the current timestamp."""

    @abstractmethod
    def limit_clause(self, limit: int, offset: int = 0) -> str:
        """Parameterised LIMIT/OFFSET clause."""

    @abstractmethod
    def auto_increment_clause(self) -> str:
        """Primary-key auto-increment modifier for CREATE TABLE."""

    @abstractmethod
    def upsert_clause(
        self,
        table: str,
        conflict_cols: List[str],
        update_cols: List[str],
    ) -> str:
        """Dialect-specific upsert SQL template.

        Returns a template string using column names directly.
        """

    @abstractmethod
    def returning_clause(self, cols: List[str]) -> str:
        """RETURNING clause (empty string when unsupported)."""


# ======================================================================
# PostgreSQL
# ======================================================================


class PostgreSQLDialect(SQLDialect):
    """PostgreSQL dialect."""

    _MAX_IDENTIFIER_LENGTH = 63  # PostgreSQL NAMEDATALEN-1

    def get_parameter_placeholder(self, position: int) -> str:
        return f"${position}"

    def quote_identifier(self, name: str) -> str:
        if not isinstance(name, str) or not name:
            raise InvalidIdentifierError(
                f"Invalid SQL identifier "
                f"(fingerprint={hash(name) & 0xFFFF:04x}): "
                f"must be a non-empty string"
            )
        if len(name) > self._MAX_IDENTIFIER_LENGTH:
            raise InvalidIdentifierError(
                f"Invalid SQL identifier "
                f"(fingerprint={hash(name) & 0xFFFF:04x}): "
                f"exceeds {self._MAX_IDENTIFIER_LENGTH}-char PostgreSQL limit "
                f"(len={len(name)})"
            )
        if not _SAFE_IDENTIFIER_RE.match(name):
            raise InvalidIdentifierError(
                f"Invalid SQL identifier "
                f"(fingerprint={hash(name) & 0xFFFF:04x}): "
                f"must match {_SAFE_IDENTIFIER_RE.pattern}"
            )
        return f'"{name}"'

    def blob_type(self) -> str:
        return "BYTEA"

    def current_timestamp(self) -> str:
        return "CURRENT_TIMESTAMP"

    def limit_clause(self, limit: int, offset: int = 0) -> str:
        clause = f"LIMIT {int(limit)}"
        if offset > 0:
            clause += f" OFFSET {int(offset)}"
        return clause

    def auto_increment_clause(self) -> str:
        return "SERIAL"

    def upsert_clause(
        self,
        table: str,
        conflict_cols: List[str],
        update_cols: List[str],
    ) -> str:
        conflict = ", ".join(conflict_cols)
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        if not updates:
            updates = f"{conflict_cols[0]} = EXCLUDED.{conflict_cols[0]}"
        return f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}"

    def returning_clause(self, cols: List[str]) -> str:
        if not cols:
            return "RETURNING *"
        return f"RETURNING {', '.join(cols)}"

    def get_type_mapping(self) -> Dict[str, str]:
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
            "hstore": True,
            "fulltext_search": True,
            "spatial_indexes": True,
        }
        return features.get(feature, False)


# ======================================================================
# MySQL
# ======================================================================


class MySQLDialect(SQLDialect):
    """MySQL dialect."""

    _MAX_IDENTIFIER_LENGTH = 64  # MySQL identifier length limit

    def get_parameter_placeholder(self, position: int) -> str:
        return "%s"

    def quote_identifier(self, name: str) -> str:
        if not isinstance(name, str) or not name:
            raise InvalidIdentifierError(
                f"Invalid SQL identifier "
                f"(fingerprint={hash(name) & 0xFFFF:04x}): "
                f"must be a non-empty string"
            )
        if len(name) > self._MAX_IDENTIFIER_LENGTH:
            raise InvalidIdentifierError(
                f"Invalid SQL identifier "
                f"(fingerprint={hash(name) & 0xFFFF:04x}): "
                f"exceeds {self._MAX_IDENTIFIER_LENGTH}-char MySQL limit "
                f"(len={len(name)})"
            )
        if not _SAFE_IDENTIFIER_RE.match(name):
            raise InvalidIdentifierError(
                f"Invalid SQL identifier "
                f"(fingerprint={hash(name) & 0xFFFF:04x}): "
                f"must match {_SAFE_IDENTIFIER_RE.pattern}"
            )
        return f"`{name}`"

    def blob_type(self) -> str:
        return "BLOB"

    def current_timestamp(self) -> str:
        return "CURRENT_TIMESTAMP"

    def limit_clause(self, limit: int, offset: int = 0) -> str:
        if offset > 0:
            return f"LIMIT {int(offset)}, {int(limit)}"
        return f"LIMIT {int(limit)}"

    def auto_increment_clause(self) -> str:
        return "AUTO_INCREMENT"

    def upsert_clause(
        self,
        table: str,
        conflict_cols: List[str],
        update_cols: List[str],
    ) -> str:
        updates = ", ".join(f"{c} = VALUES({c})" for c in update_cols)
        if not updates:
            updates = f"{conflict_cols[0]} = VALUES({conflict_cols[0]})"
        return f"ON DUPLICATE KEY UPDATE {updates}"

    def returning_clause(self, cols: List[str]) -> str:
        # MySQL does not support RETURNING
        return ""

    def get_type_mapping(self) -> Dict[str, str]:
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
        features = {
            "json": True,  # MySQL 5.7+
            "arrays": False,
            "regex": True,
            "window_functions": True,  # MySQL 8.0+
            "cte": True,  # MySQL 8.0+
            "upsert": True,  # INSERT ... ON DUPLICATE KEY UPDATE
            "returning": False,
            "full_outer_join": False,
            "lateral_join": True,  # MySQL 8.0+
            "recursive_cte": True,  # MySQL 8.0+
            "intersect": False,
            "except": False,
            "fulltext_search": True,
            "spatial_indexes": True,
        }
        return features.get(feature, False)


# ======================================================================
# SQLite
# ======================================================================


class SQLiteDialect(SQLDialect):
    """SQLite dialect."""

    _MAX_IDENTIFIER_LENGTH = 128  # SQLite practical limit

    def get_parameter_placeholder(self, position: int) -> str:
        return "?"

    def quote_identifier(self, name: str) -> str:
        if not isinstance(name, str) or not name:
            raise InvalidIdentifierError(
                f"Invalid SQL identifier "
                f"(fingerprint={hash(name) & 0xFFFF:04x}): "
                f"must be a non-empty string"
            )
        if len(name) > self._MAX_IDENTIFIER_LENGTH:
            raise InvalidIdentifierError(
                f"Invalid SQL identifier "
                f"(fingerprint={hash(name) & 0xFFFF:04x}): "
                f"exceeds {self._MAX_IDENTIFIER_LENGTH}-char SQLite limit "
                f"(len={len(name)})"
            )
        if not _SAFE_IDENTIFIER_RE.match(name):
            raise InvalidIdentifierError(
                f"Invalid SQL identifier "
                f"(fingerprint={hash(name) & 0xFFFF:04x}): "
                f"must match {_SAFE_IDENTIFIER_RE.pattern}"
            )
        return f'"{name}"'

    def blob_type(self) -> str:
        return "BLOB"

    def current_timestamp(self) -> str:
        return "CURRENT_TIMESTAMP"

    def limit_clause(self, limit: int, offset: int = 0) -> str:
        clause = f"LIMIT {int(limit)}"
        if offset > 0:
            clause += f" OFFSET {int(offset)}"
        return clause

    def auto_increment_clause(self) -> str:
        return "AUTOINCREMENT"

    def upsert_clause(
        self,
        table: str,
        conflict_cols: List[str],
        update_cols: List[str],
    ) -> str:
        conflict = ", ".join(conflict_cols)
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        if not updates:
            updates = f"{conflict_cols[0]} = EXCLUDED.{conflict_cols[0]}"
        return f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}"

    def returning_clause(self, cols: List[str]) -> str:
        # SQLite 3.35+ supports RETURNING but we return empty for
        # consistency with the adapter layer which handles it separately
        return ""

    def get_type_mapping(self) -> Dict[str, str]:
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
        features = {
            "json": True,  # SQLite 3.38+
            "arrays": False,
            "regex": False,  # Requires extension
            "window_functions": True,  # SQLite 3.25+
            "cte": True,
            "upsert": True,  # INSERT ... ON CONFLICT
            "returning": True,  # SQLite 3.35+
            "full_outer_join": False,
            "lateral_join": False,
            "recursive_cte": True,
            "intersect": True,
            "except": True,
            "fts": True,
            "fulltext_search": True,
        }
        return features.get(feature, False)


# ======================================================================
# Factory / Manager
# ======================================================================


class DialectManager:
    """Singleton-style manager for SQL dialects.

    Usage::

        from dataflow.adapters.dialect import DialectManager
        dialect = DialectManager.get_dialect("postgresql")
        safe_name = dialect.quote_identifier("users")
    """

    _instances: Dict[str, SQLDialect] = {
        "postgresql": PostgreSQLDialect(),
        "mysql": MySQLDialect(),
        "sqlite": SQLiteDialect(),
    }

    @classmethod
    def get_dialect(cls, database_type: str) -> SQLDialect:
        """Return the dialect for *database_type*.

        Raises ``ValueError`` if *database_type* is unknown.
        """
        dialect = cls._instances.get(database_type.lower())
        if dialect is None:
            raise ValueError(
                f"Unsupported database type: {database_type}. "
                f"Supported: {', '.join(cls._instances)}"
            )
        return dialect

    @classmethod
    def convert_query_parameters(
        cls,
        query: str,
        params: List[Any],
        source_dialect: str,
        target_dialect: str,
    ) -> Tuple[str, List[Any]]:
        """Convert query parameter placeholders between dialects."""
        source = cls.get_dialect(source_dialect)
        target = cls.get_dialect(target_dialect)

        converted_query = query
        param_position = 1

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

    @classmethod
    def check_feature_compatibility(
        cls,
        feature: str,
        source_dialect: str,
        target_dialect: str,
    ) -> bool:
        """Return True if *feature* is supported in both dialects."""
        source = cls.get_dialect(source_dialect)
        target = cls.get_dialect(target_dialect)
        return source.supports_feature(feature) and target.supports_feature(feature)

    @classmethod
    def get_migration_compatibility(
        cls,
        source_dialect: str,
        target_dialect: str,
    ) -> Dict[str, bool]:
        """Return a feature-compatibility matrix for a dialect migration."""
        source = cls.get_dialect(source_dialect)
        target = cls.get_dialect(target_dialect)

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

        return {
            f: source.supports_feature(f) and target.supports_feature(f)
            for f in features
        }
