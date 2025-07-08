"""Asynchronous SQL database node for the Kailash SDK.

This module provides async nodes for interacting with relational databases using SQL.
It supports PostgreSQL, MySQL, and SQLite through database-specific async libraries,
providing high-performance concurrent database operations.

Design Philosophy:
1. Async-first design for high concurrency
2. Database-agnostic interface with adapter pattern
3. Connection pooling for performance
4. Safe parameterized queries
5. Flexible result formats
6. Transaction support
7. Compatible with external repositories

Key Features:
- Non-blocking database operations
- Connection pooling with configurable limits
- Support for PostgreSQL (asyncpg), MySQL (aiomysql), SQLite (aiosqlite)
- Parameterized queries to prevent SQL injection
- Multiple fetch modes (one, all, many, iterator)
- Transaction management
- Timeout handling
- Retry logic with exponential backoff
"""

import asyncio
import json
import os
import random
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, AsyncIterator, Optional, Union

import yaml

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError

# Import optimistic locking for version control
try:
    from kailash.nodes.data.optimistic_locking import (
        ConflictResolution,
        LockStatus,
        OptimisticLockingNode,
    )

    OPTIMISTIC_LOCKING_AVAILABLE = True
except ImportError:
    OPTIMISTIC_LOCKING_AVAILABLE = False

    # Define minimal enums if not available
    class ConflictResolution:
        FAIL_FAST = "fail_fast"
        RETRY = "retry"
        MERGE = "merge"
        LAST_WRITER_WINS = "last_writer_wins"

    class LockStatus:
        SUCCESS = "success"
        VERSION_CONFLICT = "version_conflict"
        RECORD_NOT_FOUND = "record_not_found"
        RETRY_EXHAUSTED = "retry_exhausted"


class DatabaseType(Enum):
    """Supported database types."""

    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"


class QueryValidator:
    """Validates SQL queries for common security issues."""

    # Dangerous SQL patterns that could indicate injection attempts
    DANGEROUS_PATTERNS = [
        # Multiple statements
        r";\s*(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|GRANT|REVOKE)",
        # Comments that might hide malicious code
        r"--.*$",
        r"/\*.*\*/",
        # Union-based injection
        r"\bUNION\b.*\bSELECT\b",
        # Time-based blind injection
        r"\b(SLEEP|WAITFOR|PG_SLEEP)\b",
        # Out-of-band injection
        r"\b(LOAD_FILE|INTO\s+OUTFILE|INTO\s+DUMPFILE)\b",
        # System command execution
        r"\b(XP_CMDSHELL|EXEC\s+MASTER)",
    ]

    # Patterns that should only appear in admin queries
    ADMIN_ONLY_PATTERNS = [
        r"\b(CREATE|ALTER|DROP)\s+(?:\w+\s+)*(TABLE|INDEX|VIEW|PROCEDURE|FUNCTION|TRIGGER)",
        r"\b(GRANT|REVOKE)\b",
        r"\bTRUNCATE\b",
    ]

    @classmethod
    def validate_query(cls, query: str, allow_admin: bool = False) -> None:
        """Validate a SQL query for security issues.

        Args:
            query: The SQL query to validate
            allow_admin: Whether to allow administrative commands

        Raises:
            NodeValidationError: If the query contains dangerous patterns
        """
        query_upper = query.upper()

        # Check for dangerous patterns
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE | re.MULTILINE):
                raise NodeValidationError(
                    f"Query contains potentially dangerous pattern: {pattern}"
                )

        # Check for admin-only patterns if not allowed
        if not allow_admin:
            for pattern in cls.ADMIN_ONLY_PATTERNS:
                if re.search(pattern, query, re.IGNORECASE):
                    raise NodeValidationError(
                        f"Query contains administrative command that is not allowed: {pattern}"
                    )

    @classmethod
    def validate_identifier(cls, identifier: str) -> None:
        """Validate a database identifier (table/column name).

        Args:
            identifier: The identifier to validate

        Raises:
            NodeValidationError: If the identifier is invalid
        """
        # Allow alphanumeric, underscore, and dot (for schema.table)
        if not re.match(
            r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$", identifier
        ):
            raise NodeValidationError(
                f"Invalid identifier: {identifier}. "
                "Identifiers must start with letter/underscore and contain only letters, numbers, underscores."
            )

    @classmethod
    def sanitize_string_literal(cls, value: str) -> str:
        """Sanitize a string value for SQL by escaping quotes.

        Args:
            value: The string value to sanitize

        Returns:
            Escaped string safe for SQL
        """
        # This is a basic implementation - real escaping should be done by the driver
        return value.replace("'", "''").replace("\\", "\\\\")

    @classmethod
    def validate_connection_string(cls, connection_string: str) -> None:
        """Validate a database connection string.

        Args:
            connection_string: The connection string to validate

        Raises:
            NodeValidationError: If the connection string appears malicious
        """
        # Check for suspicious patterns in connection strings
        suspicious_patterns = [
            # SQL injection attempts
            r";\s*(DROP|DELETE|TRUNCATE|ALTER|CREATE|INSERT|UPDATE)",
            # Command execution attempts
            r';.*\bhost\s*=\s*[\'"]?\|',
            r';.*\bhost\s*=\s*[\'"]?`',
            r"\$\(",  # Command substitution
            r"`",  # Backticks
            # File access attempts
            r'sslcert\s*=\s*[\'"]?(/etc/passwd|/etc/shadow)',
            r'sslkey\s*=\s*[\'"]?(/etc/passwd|/etc/shadow)',
        ]

        for pattern in suspicious_patterns:
            if re.search(pattern, connection_string, re.IGNORECASE):
                raise NodeValidationError(
                    "Connection string contains suspicious pattern"
                )


class FetchMode(Enum):
    """Result fetch modes."""

    ONE = "one"  # Fetch single row
    ALL = "all"  # Fetch all rows
    MANY = "many"  # Fetch specific number of rows
    ITERATOR = "iterator"  # Return async iterator


@dataclass
class RetryConfig:
    """Configuration for retry logic."""

    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True

    # Retryable error patterns (database-specific)
    retryable_errors: list[str] = None

    def __post_init__(self):
        """Initialize default retryable errors."""
        if self.retryable_errors is None:
            self.retryable_errors = [
                # PostgreSQL
                "connection_refused",
                "connection_reset",
                "connection reset",  # Handle different cases
                "connection_aborted",
                "could not connect",
                "server closed the connection",
                "terminating connection",
                "connectionreseterror",
                "connectionrefusederror",
                "brokenpipeerror",
                # MySQL
                "lost connection to mysql server",
                "mysql server has gone away",
                "can't connect to mysql server",
                # SQLite
                "database is locked",
                "disk i/o error",
                # General
                "timeout",
                "timed out",
                "pool is closed",
                # DNS/Network errors
                "nodename nor servname provided",
                "name or service not known",
                "gaierror",
                "getaddrinfo failed",
                "temporary failure in name resolution",
            ]

    def should_retry(self, error: Exception) -> bool:
        """Check if an error is retryable."""
        error_str = str(error).lower()
        return any(pattern.lower() in error_str for pattern in self.retryable_errors)

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for a retry attempt."""
        delay = min(
            self.initial_delay * (self.exponential_base**attempt), self.max_delay
        )

        if self.jitter:
            # Add random jitter (±25%)
            jitter_amount = delay * 0.25
            delay += random.uniform(-jitter_amount, jitter_amount)

        return max(0, delay)  # Ensure non-negative


@dataclass
class DatabaseConfig:
    """Database connection configuration."""

    type: DatabaseType
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None
    connection_string: Optional[str] = None
    pool_size: int = 10
    max_pool_size: int = 20
    pool_timeout: float = 30.0
    command_timeout: float = 60.0

    def __post_init__(self):
        """Validate configuration."""
        if not self.connection_string:
            if self.type != DatabaseType.SQLITE:
                if not all([self.host, self.database]):
                    raise ValueError(
                        f"{self.type.value} requires host and database or connection_string"
                    )
            else:
                if not self.database:
                    raise ValueError("SQLite requires database path")


class DatabaseAdapter(ABC):
    """Abstract base class for database adapters."""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._pool = None

    def _convert_row(self, row: dict) -> dict:
        """Convert database-specific types to JSON-serializable types."""
        converted = {}
        for key, value in row.items():
            converted[key] = self._serialize_value(value)
        return converted

    def _serialize_value(self, value: Any) -> Any:
        """Convert database-specific types to JSON-serializable types."""
        if value is None:
            return None
        elif isinstance(value, bool):
            # Handle bool before int (bool is subclass of int in Python)
            return value
        elif isinstance(value, (int, float)):
            # Return numeric types as-is
            return value
        elif isinstance(value, str):
            # Return strings as-is
            return value
        elif isinstance(value, bytes):
            import base64

            result = base64.b64encode(value).decode("utf-8")
            return result
        elif isinstance(value, Decimal):
            return float(value)
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, date):
            return value.isoformat()
        elif hasattr(value, "total_seconds"):  # timedelta
            return value.total_seconds()
        elif hasattr(value, "hex"):  # UUID
            return str(value)
        elif isinstance(value, (list, tuple)):
            return [self._serialize_value(item) for item in value]
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        return value

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection pool."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection pool."""
        pass

    @abstractmethod
    async def execute(
        self,
        query: str,
        params: Optional[Union[tuple, dict]] = None,
        fetch_mode: FetchMode = FetchMode.ALL,
        fetch_size: Optional[int] = None,
        transaction: Optional[Any] = None,
    ) -> Any:
        """Execute query and return results, optionally within a transaction."""
        pass

    @abstractmethod
    async def execute_many(
        self, query: str, params_list: list[Union[tuple, dict]]
    ) -> None:
        """Execute query multiple times with different parameters."""
        pass

    @abstractmethod
    async def begin_transaction(self) -> Any:
        """Begin a transaction."""
        pass

    @abstractmethod
    async def commit_transaction(self, transaction: Any) -> None:
        """Commit a transaction."""
        pass

    @abstractmethod
    async def rollback_transaction(self, transaction: Any) -> None:
        """Rollback a transaction."""
        pass


class PostgreSQLAdapter(DatabaseAdapter):
    """PostgreSQL adapter using asyncpg."""

    async def connect(self) -> None:
        """Establish connection pool."""
        try:
            import asyncpg
        except ImportError:
            raise NodeExecutionError(
                "asyncpg not installed. Install with: pip install asyncpg"
            )

        if self.config.connection_string:
            dsn = self.config.connection_string
        else:
            dsn = (
                f"postgresql://{self.config.user}:{self.config.password}@"
                f"{self.config.host}:{self.config.port or 5432}/{self.config.database}"
            )

        self._pool = await asyncpg.create_pool(
            dsn,
            min_size=1,
            max_size=self.config.max_pool_size,
            timeout=self.config.pool_timeout,
            command_timeout=self.config.command_timeout,
        )

    async def disconnect(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()

    async def execute(
        self,
        query: str,
        params: Optional[Union[tuple, dict]] = None,
        fetch_mode: FetchMode = FetchMode.ALL,
        fetch_size: Optional[int] = None,
        transaction: Optional[Any] = None,
    ) -> Any:
        """Execute query and return results."""
        # Convert dict params to positional for asyncpg
        if isinstance(params, dict):
            # Simple parameter substitution for named params
            # In production, use a proper SQL parser
            import json

            query_params = []
            for i, (key, value) in enumerate(params.items(), 1):
                query = query.replace(f":{key}", f"${i}")
                # For PostgreSQL, lists should remain as lists for array operations
                # Only convert dicts to JSON strings
                if isinstance(value, dict):
                    value = json.dumps(value)
                query_params.append(value)
            params = query_params

        # Ensure params is a list/tuple for asyncpg
        if params is None:
            params = []
        elif not isinstance(params, (list, tuple)):
            params = [params]

        # Execute query on appropriate connection
        if transaction:
            # Use transaction connection
            conn, tx = transaction

            # For UPDATE/DELETE queries without RETURNING, use execute() to get affected rows
            query_upper = query.upper()
            if (
                (
                    "UPDATE" in query_upper
                    or "DELETE" in query_upper
                    or "INSERT" in query_upper
                )
                and "RETURNING" not in query_upper
                and fetch_mode == FetchMode.ALL
            ):
                result = await conn.execute(query, *params)
                # asyncpg returns a string like "UPDATE 1", extract the count
                if isinstance(result, str):
                    parts = result.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        rows_affected = int(parts[1])
                    else:
                        rows_affected = 0
                    return [{"rows_affected": rows_affected}]
                return []

            if fetch_mode == FetchMode.ONE:
                row = await conn.fetchrow(query, *params)
                return self._convert_row(dict(row)) if row else None
            elif fetch_mode == FetchMode.ALL:
                rows = await conn.fetch(query, *params)
                return [self._convert_row(dict(row)) for row in rows]
            elif fetch_mode == FetchMode.MANY:
                if not fetch_size:
                    raise ValueError("fetch_size required for MANY mode")
                rows = await conn.fetch(query, *params)
                return [self._convert_row(dict(row)) for row in rows[:fetch_size]]
            elif fetch_mode == FetchMode.ITERATOR:
                raise NotImplementedError("Iterator mode not yet implemented")
        else:
            # Use pool connection
            async with self._pool.acquire() as conn:
                # For UPDATE/DELETE queries without RETURNING, use execute() to get affected rows
                query_upper = query.upper()
                if (
                    (
                        "UPDATE" in query_upper
                        or "DELETE" in query_upper
                        or "INSERT" in query_upper
                    )
                    and "RETURNING" not in query_upper
                    and fetch_mode == FetchMode.ALL
                ):
                    result = await conn.execute(query, *params)
                    # asyncpg returns a string like "UPDATE 1", extract the count
                    if isinstance(result, str):
                        parts = result.split()
                        if len(parts) >= 2 and parts[1].isdigit():
                            rows_affected = int(parts[1])
                        else:
                            rows_affected = 0
                        return [{"rows_affected": rows_affected}]
                    return []

                if fetch_mode == FetchMode.ONE:
                    row = await conn.fetchrow(query, *params)
                    return self._convert_row(dict(row)) if row else None
                elif fetch_mode == FetchMode.ALL:
                    rows = await conn.fetch(query, *params)
                    return [self._convert_row(dict(row)) for row in rows]
                elif fetch_mode == FetchMode.MANY:
                    if not fetch_size:
                        raise ValueError("fetch_size required for MANY mode")
                    rows = await conn.fetch(query, *params)
                    return [self._convert_row(dict(row)) for row in rows[:fetch_size]]
                elif fetch_mode == FetchMode.ITERATOR:
                    raise NotImplementedError("Iterator mode not yet implemented")

    async def execute_many(
        self,
        query: str,
        params_list: list[Union[tuple, dict]],
        transaction: Optional[Any] = None,
    ) -> None:
        """Execute query multiple times with different parameters."""
        # Convert all dict params to tuples

        converted_params = []
        query_converted = query
        for params in params_list:
            if isinstance(params, dict):
                query_params = []
                for i, (key, value) in enumerate(params.items(), 1):
                    if converted_params == []:  # Only replace on first iteration
                        query_converted = query_converted.replace(f":{key}", f"${i}")
                    # Serialize complex objects to JSON strings for PostgreSQL
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value)
                    query_params.append(value)
                converted_params.append(query_params)
            else:
                converted_params.append(params)

        if transaction:
            # Use transaction connection
            conn, tx = transaction
            await conn.executemany(query_converted, converted_params)
        else:
            # Use pool connection
            async with self._pool.acquire() as conn:
                await conn.executemany(query_converted, converted_params)

    async def begin_transaction(self) -> Any:
        """Begin a transaction."""
        conn = await self._pool.acquire()
        tx = conn.transaction()
        await tx.start()
        return (conn, tx)

    async def commit_transaction(self, transaction: Any) -> None:
        """Commit a transaction."""
        conn, tx = transaction
        await tx.commit()
        await self._pool.release(conn)

    async def rollback_transaction(self, transaction: Any) -> None:
        """Rollback a transaction."""
        conn, tx = transaction
        await tx.rollback()
        await self._pool.release(conn)


class MySQLAdapter(DatabaseAdapter):
    """MySQL adapter using aiomysql."""

    async def connect(self) -> None:
        """Establish connection pool."""
        try:
            import aiomysql
        except ImportError:
            raise NodeExecutionError(
                "aiomysql not installed. Install with: pip install aiomysql"
            )

        self._pool = await aiomysql.create_pool(
            host=self.config.host,
            port=self.config.port or 3306,
            user=self.config.user,
            password=self.config.password,
            db=self.config.database,
            minsize=1,
            maxsize=self.config.max_pool_size,
            pool_recycle=3600,
        )

    async def disconnect(self) -> None:
        """Close connection pool."""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()

    async def execute(
        self,
        query: str,
        params: Optional[Union[tuple, dict]] = None,
        fetch_mode: FetchMode = FetchMode.ALL,
        fetch_size: Optional[int] = None,
        transaction: Optional[Any] = None,
    ) -> Any:
        """Execute query and return results."""
        # Use transaction connection if provided, otherwise get from pool
        if transaction:
            conn = transaction
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)

                if fetch_mode == FetchMode.ONE:
                    row = await cursor.fetchone()
                    if row and cursor.description:
                        columns = [desc[0] for desc in cursor.description]
                        return self._convert_row(dict(zip(columns, row)))
                    return None
                elif fetch_mode == FetchMode.ALL:
                    rows = await cursor.fetchall()
                    if rows and cursor.description:
                        columns = [desc[0] for desc in cursor.description]
                        return [
                            self._convert_row(dict(zip(columns, row))) for row in rows
                        ]
                    return []
                elif fetch_mode == FetchMode.MANY:
                    if not fetch_size:
                        raise ValueError("fetch_size required for MANY mode")
                    rows = await cursor.fetchmany(fetch_size)
                    if rows and cursor.description:
                        columns = [desc[0] for desc in cursor.description]
                        return [
                            self._convert_row(dict(zip(columns, row))) for row in rows
                        ]
                    return []
        else:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, params)

                    if fetch_mode == FetchMode.ONE:
                        row = await cursor.fetchone()
                        if row and cursor.description:
                            columns = [desc[0] for desc in cursor.description]
                            return self._convert_row(dict(zip(columns, row)))
                        return None
                    elif fetch_mode == FetchMode.ALL:
                        rows = await cursor.fetchall()
                        if rows and cursor.description:
                            columns = [desc[0] for desc in cursor.description]
                            return [
                                self._convert_row(dict(zip(columns, row)))
                                for row in rows
                            ]
                        return []
                    elif fetch_mode == FetchMode.MANY:
                        if not fetch_size:
                            raise ValueError("fetch_size required for MANY mode")
                        rows = await cursor.fetchmany(fetch_size)
                        if rows and cursor.description:
                            columns = [desc[0] for desc in cursor.description]
                            return [
                                self._convert_row(dict(zip(columns, row)))
                                for row in rows
                            ]
                        return []

    async def execute_many(
        self,
        query: str,
        params_list: list[Union[tuple, dict]],
        transaction: Optional[Any] = None,
    ) -> None:
        """Execute query multiple times with different parameters."""
        if transaction:
            # Use transaction connection
            async with transaction.cursor() as cursor:
                await cursor.executemany(query, params_list)
                # Don't commit here - let transaction handling do it
        else:
            # Use pool connection
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.executemany(query, params_list)
                    await conn.commit()

    async def begin_transaction(self) -> Any:
        """Begin a transaction."""
        conn = await self._pool.acquire()
        await conn.begin()
        return conn

    async def commit_transaction(self, transaction: Any) -> None:
        """Commit a transaction."""
        await transaction.commit()
        await self._pool.release(transaction)

    async def rollback_transaction(self, transaction: Any) -> None:
        """Rollback a transaction."""
        await transaction.rollback()
        await self._pool.release(transaction)


class SQLiteAdapter(DatabaseAdapter):
    """SQLite adapter using aiosqlite."""

    async def connect(self) -> None:
        """Establish connection pool."""
        try:
            import aiosqlite
        except ImportError:
            raise NodeExecutionError(
                "aiosqlite not installed. Install with: pip install aiosqlite"
            )

        # SQLite doesn't have true connection pooling
        # We'll manage a single connection for simplicity
        self._aiosqlite = aiosqlite
        self._db_path = self.config.database

    async def disconnect(self) -> None:
        """Close connection."""
        # Connections are managed per-operation for SQLite
        pass

    async def execute(
        self,
        query: str,
        params: Optional[Union[tuple, dict]] = None,
        fetch_mode: FetchMode = FetchMode.ALL,
        fetch_size: Optional[int] = None,
        transaction: Optional[Any] = None,
    ) -> Any:
        """Execute query and return results."""
        if transaction:
            # Use existing transaction connection
            db = transaction
            cursor = await db.execute(query, params or [])

            if fetch_mode == FetchMode.ONE:
                row = await cursor.fetchone()
                return self._convert_row(dict(row)) if row else None
            elif fetch_mode == FetchMode.ALL:
                rows = await cursor.fetchall()
                return [self._convert_row(dict(row)) for row in rows]
            elif fetch_mode == FetchMode.MANY:
                if not fetch_size:
                    raise ValueError("fetch_size required for MANY mode")
                rows = await cursor.fetchmany(fetch_size)
                return [self._convert_row(dict(row)) for row in rows]
        else:
            # Create new connection for non-transactional queries
            async with self._aiosqlite.connect(self._db_path) as db:
                db.row_factory = self._aiosqlite.Row
                cursor = await db.execute(query, params or [])

                if fetch_mode == FetchMode.ONE:
                    row = await cursor.fetchone()
                    return self._convert_row(dict(row)) if row else None
                elif fetch_mode == FetchMode.ALL:
                    rows = await cursor.fetchall()
                    return [self._convert_row(dict(row)) for row in rows]
                elif fetch_mode == FetchMode.MANY:
                    if not fetch_size:
                        raise ValueError("fetch_size required for MANY mode")
                    rows = await cursor.fetchmany(fetch_size)
                    return [self._convert_row(dict(row)) for row in rows]

                await db.commit()

    async def execute_many(
        self,
        query: str,
        params_list: list[Union[tuple, dict]],
        transaction: Optional[Any] = None,
    ) -> None:
        """Execute query multiple times with different parameters."""
        if transaction:
            # Use existing transaction connection
            await transaction.executemany(query, params_list)
            # Don't commit here - let transaction handling do it
        else:
            # Create new connection for non-transactional queries
            async with self._aiosqlite.connect(self._db_path) as db:
                await db.executemany(query, params_list)
                await db.commit()

    async def begin_transaction(self) -> Any:
        """Begin a transaction."""
        db = await self._aiosqlite.connect(self._db_path)
        db.row_factory = self._aiosqlite.Row
        await db.execute("BEGIN")
        return db

    async def commit_transaction(self, transaction: Any) -> None:
        """Commit a transaction."""
        await transaction.commit()
        await transaction.close()

    async def rollback_transaction(self, transaction: Any) -> None:
        """Rollback a transaction."""
        await transaction.rollback()
        await transaction.close()


class DatabaseConfigManager:
    """Manager for database configurations from YAML files."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize with configuration file path.

        Args:
            config_path: Path to YAML configuration file. If not provided,
                        looks for 'database.yaml' in current directory.
        """
        self.config_path = config_path or "database.yaml"
        self._config: Optional[dict[str, Any]] = None
        self._config_cache: dict[str, tuple[str, dict[str, Any]]] = {}

    def _load_config(self) -> dict[str, Any]:
        """Load configuration from YAML file."""
        if self._config is not None:
            return self._config

        if not os.path.exists(self.config_path):
            # No config file, return empty config
            self._config = {}
            return self._config

        try:
            with open(self.config_path, "r") as f:
                self._config = yaml.safe_load(f) or {}
                return self._config
        except yaml.YAMLError as e:
            raise NodeValidationError(f"Invalid YAML in configuration file: {e}")
        except Exception as e:
            raise NodeExecutionError(f"Failed to load configuration file: {e}")

    def get_database_config(self, connection_name: str) -> tuple[str, dict[str, Any]]:
        """Get database configuration by connection name.

        Args:
            connection_name: Name of the database connection from config

        Returns:
            Tuple of (connection_string, additional_config)

        Raises:
            NodeExecutionError: If connection not found
        """
        # Check cache first
        if connection_name in self._config_cache:
            return self._config_cache[connection_name]

        config = self._load_config()
        databases = config.get("databases", {})

        if connection_name in databases:
            db_config = databases[connection_name].copy()
            connection_string = db_config.pop(
                "connection_string", db_config.pop("url", None)
            )

            if not connection_string:
                raise NodeExecutionError(
                    f"No 'connection_string' or 'url' specified for database '{connection_name}'"
                )

            # Handle environment variable substitution
            connection_string = self._substitute_env_vars(connection_string)

            # Process other config values
            for key, value in db_config.items():
                if isinstance(value, str):
                    db_config[key] = self._substitute_env_vars(value)

            # Cache the result
            self._config_cache[connection_name] = (connection_string, db_config)
            return connection_string, db_config

        # Try default connection
        if "default" in databases:
            return self.get_database_config("default")

        # No configuration found
        available = list(databases.keys()) if databases else []
        raise NodeExecutionError(
            f"Database connection '{connection_name}' not found in configuration. "
            f"Available connections: {available}"
        )

    def _substitute_env_vars(self, value: str) -> str:
        """Substitute environment variables in configuration values.

        Supports:
        - ${VAR_NAME} - Full substitution
        - $VAR_NAME - Simple substitution
        """
        if not isinstance(value, str):
            return value

        # Handle ${VAR_NAME} format
        if value.startswith("${") and value.endswith("}"):
            env_var = value[2:-1]
            env_value = os.getenv(env_var)
            if env_value is None:
                raise NodeExecutionError(f"Environment variable '{env_var}' not found")
            return env_value

        # Handle $VAR_NAME and ${VAR_NAME} formats in connection strings
        import re

        # Pattern to match both $VAR_NAME and ${VAR_NAME}
        pattern = r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)"

        def replace_var(match):
            # Group 1 is for ${VAR_NAME}, group 2 is for $VAR_NAME
            var_name = match.group(1) or match.group(2)
            var_value = os.getenv(var_name)
            if var_value is None:
                raise NodeExecutionError(f"Environment variable '{var_name}' not found")
            return var_value

        return re.sub(pattern, replace_var, value)

    def list_connections(self) -> list[str]:
        """List all available database connections."""
        config = self._load_config()
        databases = config.get("databases", {})
        return list(databases.keys())

    def validate_config(self) -> None:
        """Validate the configuration file."""
        config = self._load_config()
        databases = config.get("databases", {})

        for name, db_config in databases.items():
            if not isinstance(db_config, dict):
                raise NodeValidationError(
                    f"Database '{name}' configuration must be a dictionary"
                )

            # Must have connection string
            if "connection_string" not in db_config and "url" not in db_config:
                raise NodeValidationError(
                    f"Database '{name}' must have 'connection_string' or 'url'"
                )


@register_node()
class AsyncSQLDatabaseNode(AsyncNode):
    """Asynchronous SQL database node for high-concurrency database operations.

    This node provides non-blocking database operations with connection pooling,
    supporting PostgreSQL, MySQL, and SQLite databases. It's designed for
    high-concurrency scenarios and can handle hundreds of simultaneous connections.

    Parameters:
        database_type: Type of database (postgresql, mysql, sqlite)
        connection_string: Full database connection string (optional)
        host: Database host (required if no connection_string)
        port: Database port (optional, uses defaults)
        database: Database name
        user: Database user
        password: Database password
        query: SQL query to execute
        params: Query parameters (dict or tuple)
        fetch_mode: How to fetch results (one, all, many)
        fetch_size: Number of rows for 'many' mode
        pool_size: Initial connection pool size
        max_pool_size: Maximum connection pool size
        timeout: Query timeout in seconds
        transaction_mode: Transaction handling mode ('auto', 'manual', 'none')
        share_pool: Whether to share connection pool across instances (default: True)

    Transaction Modes:
        - 'auto' (default): Each query runs in its own transaction, automatically
          committed on success or rolled back on error
        - 'manual': Transactions must be explicitly managed using begin_transaction(),
          commit(), and rollback() methods
        - 'none': No transaction wrapping, queries execute immediately

    Example (auto transaction):
        >>> node = AsyncSQLDatabaseNode(
        ...     name="update_users",
        ...     database_type="postgresql",
        ...     host="localhost",
        ...     database="myapp",
        ...     user="dbuser",
        ...     password="dbpass"
        ... )
        >>> # This will automatically rollback on error
        >>> await node.async_run(query="INSERT INTO users VALUES (1, 'test')")
        >>> await node.async_run(query="INVALID SQL")  # Previous insert rolled back

    Example (manual transaction):
        >>> node = AsyncSQLDatabaseNode(
        ...     name="transfer_funds",
        ...     database_type="postgresql",
        ...     host="localhost",
        ...     database="myapp",
        ...     user="dbuser",
        ...     password="dbpass",
        ...     transaction_mode="manual"
        ... )
        >>> await node.begin_transaction()
        >>> try:
        ...     await node.async_run(query="UPDATE accounts SET balance = balance - 100 WHERE id = 1")
        ...     await node.async_run(query="UPDATE accounts SET balance = balance + 100 WHERE id = 2")
        ...     await node.commit()
        >>> except Exception:
        ...     await node.rollback()
        ...     raise
    """

    # Class-level pool storage for sharing across instances
    _shared_pools: dict[str, tuple[DatabaseAdapter, int]] = {}
    _pool_lock: Optional[asyncio.Lock] = None

    @classmethod
    def _get_pool_lock(cls) -> asyncio.Lock:
        """Get or create pool lock for the current event loop."""
        # Check if we have a lock and if it's for the current loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, create a new lock
            cls._pool_lock = asyncio.Lock()
            return cls._pool_lock

        # Check if existing lock is for current loop
        if cls._pool_lock is None:
            cls._pool_lock = asyncio.Lock()
            cls._pool_lock_loop_id = id(loop)
        else:
            # Verify the lock is for the current event loop
            # Just create a new lock if we're in a different loop
            # The simplest approach is to store the loop ID with the lock
            if not hasattr(cls, "_pool_lock_loop_id"):
                cls._pool_lock_loop_id = id(loop)
            elif cls._pool_lock_loop_id != id(loop):
                # Different event loop, clear everything
                cls._pool_lock = asyncio.Lock()
                cls._pool_lock_loop_id = id(loop)
                cls._shared_pools.clear()

        return cls._pool_lock

    def __init__(self, **config):
        self._adapter: Optional[DatabaseAdapter] = None
        self._connected = False
        # Extract access control manager before passing to parent
        self.access_control_manager = config.pop("access_control_manager", None)

        # Transaction state management
        self._active_transaction = None
        self._transaction_connection = None
        self._transaction_mode = config.get("transaction_mode", "auto")

        # Pool sharing configuration
        self._share_pool = config.get("share_pool", True)
        self._pool_key = None

        # Security configuration
        self._validate_queries = config.get("validate_queries", True)
        self._allow_admin = config.get("allow_admin", False)

        # Retry configuration
        retry_config = config.get("retry_config")
        if retry_config:
            if isinstance(retry_config, dict):
                self._retry_config = RetryConfig(**retry_config)
            else:
                self._retry_config = retry_config
        else:
            # Build from individual parameters
            self._retry_config = RetryConfig(
                max_retries=config.get("max_retries", 3),
                initial_delay=config.get("retry_delay", 1.0),
            )

        # Optimistic locking configuration
        self._enable_optimistic_locking = config.get("enable_optimistic_locking", False)
        self._version_field = config.get("version_field", "version")
        self._conflict_resolution = config.get("conflict_resolution", "fail_fast")
        self._version_retry_attempts = config.get("version_retry_attempts", 3)

        super().__init__(**config)

    def _reinitialize_from_config(self):
        """Re-initialize instance variables from config after config file loading."""
        # Update transaction mode
        self._transaction_mode = self.config.get("transaction_mode", "auto")

        # Update pool sharing configuration
        self._share_pool = self.config.get("share_pool", True)

        # Update security configuration
        self._validate_queries = self.config.get("validate_queries", True)
        self._allow_admin = self.config.get("allow_admin", False)

        # Update retry configuration
        retry_config = self.config.get("retry_config")
        if retry_config:
            if isinstance(retry_config, dict):
                self._retry_config = RetryConfig(**retry_config)
            else:
                self._retry_config = retry_config
        else:
            # Build from individual parameters
            self._retry_config = RetryConfig(
                max_retries=self.config.get("max_retries", 3),
                initial_delay=self.config.get("retry_delay", 1.0),
            )

        # Update optimistic locking configuration
        self._enable_optimistic_locking = self.config.get(
            "enable_optimistic_locking", False
        )
        self._version_field = self.config.get("version_field", "version")
        self._conflict_resolution = self.config.get("conflict_resolution", "fail_fast")
        self._version_retry_attempts = self.config.get("version_retry_attempts", 3)

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define the parameters this node accepts."""
        params = [
            NodeParameter(
                name="database_type",
                type=str,
                required=True,
                default="postgresql",
                description="Type of database: postgresql, mysql, or sqlite",
            ),
            NodeParameter(
                name="connection_string",
                type=str,
                required=False,
                description="Full database connection string (overrides individual params)",
            ),
            NodeParameter(
                name="connection_name",
                type=str,
                required=False,
                description="Name of database connection from config file",
            ),
            NodeParameter(
                name="config_file",
                type=str,
                required=False,
                description="Path to YAML configuration file (default: database.yaml)",
            ),
            NodeParameter(
                name="host", type=str, required=False, description="Database host"
            ),
            NodeParameter(
                name="port", type=int, required=False, description="Database port"
            ),
            NodeParameter(
                name="database", type=str, required=False, description="Database name"
            ),
            NodeParameter(
                name="user", type=str, required=False, description="Database user"
            ),
            NodeParameter(
                name="password",
                type=str,
                required=False,
                description="Database password",
            ),
            NodeParameter(
                name="query",
                type=str,
                required=True,
                description="SQL query to execute",
            ),
            NodeParameter(
                name="params",
                type=Any,
                required=False,
                description="Query parameters as dict or tuple",
            ),
            NodeParameter(
                name="fetch_mode",
                type=str,
                required=False,
                default="all",
                description="Fetch mode: one, all, many",
            ),
            NodeParameter(
                name="fetch_size",
                type=int,
                required=False,
                description="Number of rows to fetch in 'many' mode",
            ),
            NodeParameter(
                name="pool_size",
                type=int,
                required=False,
                default=10,
                description="Initial connection pool size",
            ),
            NodeParameter(
                name="max_pool_size",
                type=int,
                required=False,
                default=20,
                description="Maximum connection pool size",
            ),
            NodeParameter(
                name="timeout",
                type=float,
                required=False,
                default=60.0,
                description="Query timeout in seconds",
            ),
            NodeParameter(
                name="user_context",
                type=Any,
                required=False,
                description="User context for access control",
            ),
            NodeParameter(
                name="transaction_mode",
                type=str,
                required=False,
                default="auto",
                description="Transaction mode: 'auto' (default), 'manual', or 'none'",
            ),
            NodeParameter(
                name="share_pool",
                type=bool,
                required=False,
                default=True,
                description="Whether to share connection pool across instances with same config",
            ),
            NodeParameter(
                name="validate_queries",
                type=bool,
                required=False,
                default=True,
                description="Whether to validate queries for SQL injection attempts",
            ),
            NodeParameter(
                name="allow_admin",
                type=bool,
                required=False,
                default=False,
                description="Whether to allow administrative SQL commands (CREATE, DROP, etc.)",
            ),
            NodeParameter(
                name="retry_config",
                type=Any,
                required=False,
                description="Retry configuration dict or RetryConfig object",
            ),
            NodeParameter(
                name="max_retries",
                type=int,
                required=False,
                default=3,
                description="Maximum number of retry attempts for transient failures",
            ),
            NodeParameter(
                name="retry_delay",
                type=float,
                required=False,
                default=1.0,
                description="Initial retry delay in seconds",
            ),
            NodeParameter(
                name="enable_optimistic_locking",
                type=bool,
                required=False,
                default=False,
                description="Enable optimistic locking for version control",
            ),
            NodeParameter(
                name="version_field",
                type=str,
                required=False,
                default="version",
                description="Column name for version tracking",
            ),
            NodeParameter(
                name="conflict_resolution",
                type=str,
                required=False,
                default="fail_fast",
                description="How to handle version conflicts: fail_fast, retry, last_writer_wins",
            ),
            NodeParameter(
                name="version_retry_attempts",
                type=int,
                required=False,
                default=3,
                description="Maximum retries for version conflicts",
            ),
            NodeParameter(
                name="result_format",
                type=str,
                required=False,
                default="dict",
                description="Result format: 'dict' (default), 'list', or 'dataframe'",
            ),
        ]

        # Convert list to dict as required by base class
        return {param.name: param for param in params}

    def _validate_config(self):
        """Validate node configuration."""
        super()._validate_config()

        # Handle config file loading
        connection_name = self.config.get("connection_name")
        config_file = self.config.get("config_file")

        if connection_name:
            # Load from config file
            config_manager = DatabaseConfigManager(config_file)
            try:
                conn_string, db_config = config_manager.get_database_config(
                    connection_name
                )
                # Update config with values from file
                self.config["connection_string"] = conn_string
                # Merge additional config
                # Config file values should override defaults but not explicit params
                for key, value in db_config.items():
                    # Check if this was explicitly provided by user
                    param_info = self.get_parameters().get(key)
                    if param_info and key in self.config:
                        # If it equals the default, it wasn't explicitly set
                        if self.config[key] == param_info.default:
                            self.config[key] = value
                    else:
                        # Not a parameter or not in config yet
                        self.config[key] = value
            except Exception as e:
                raise NodeValidationError(
                    f"Failed to load config '{connection_name}': {e}"
                )

        # Re-initialize instance variables with updated config
        self._reinitialize_from_config()

        # Validate database type
        db_type = self.config.get("database_type", "").lower()
        if db_type not in ["postgresql", "mysql", "sqlite"]:
            raise NodeValidationError(
                f"Invalid database_type: {db_type}. "
                "Must be one of: postgresql, mysql, sqlite"
            )

        # Validate connection parameters
        connection_string = self.config.get("connection_string")
        if connection_string:
            # Validate connection string for security
            if self._validate_queries:
                try:
                    QueryValidator.validate_connection_string(connection_string)
                except NodeValidationError:
                    raise NodeValidationError(
                        "Connection string failed security validation. "
                        "Set validate_queries=False to bypass (not recommended)."
                    )
        else:
            if db_type != "sqlite":
                if not self.config.get("host") or not self.config.get("database"):
                    raise NodeValidationError(
                        f"{db_type} requires host and database or connection_string"
                    )
            else:
                if not self.config.get("database"):
                    raise NodeValidationError("SQLite requires database path")

        # Validate fetch mode
        fetch_mode = self.config.get("fetch_mode", "all").lower()
        if fetch_mode not in ["one", "all", "many", "iterator"]:
            raise NodeValidationError(
                f"Invalid fetch_mode: {fetch_mode}. "
                "Must be one of: one, all, many, iterator"
            )

        if fetch_mode == "many" and not self.config.get("fetch_size"):
            raise NodeValidationError("fetch_size required when fetch_mode is 'many'")

        # Validate initial query if provided
        if self.config.get("query") and self._validate_queries:
            try:
                QueryValidator.validate_query(
                    self.config["query"], allow_admin=self._allow_admin
                )
            except NodeValidationError as e:
                raise NodeValidationError(
                    f"Initial query validation failed: {e}. "
                    "Set validate_queries=False to bypass (not recommended)."
                )

    def _generate_pool_key(self) -> str:
        """Generate a unique key for connection pool sharing."""
        # Create a unique key based on connection parameters
        key_parts = [
            self.config.get("database_type", ""),
            self.config.get("connection_string", "")
            or (
                f"{self.config.get('host', '')}:"
                f"{self.config.get('port', '')}:"
                f"{self.config.get('database', '')}:"
                f"{self.config.get('user', '')}"
            ),
            str(self.config.get("pool_size", 10)),
            str(self.config.get("max_pool_size", 20)),
        ]
        return "|".join(key_parts)

    async def _get_adapter(self) -> DatabaseAdapter:
        """Get or create database adapter with optional pool sharing."""
        if not self._adapter:
            if self._share_pool:
                # Use shared pool if available
                async with self._get_pool_lock():
                    self._pool_key = self._generate_pool_key()

                    if self._pool_key in self._shared_pools:
                        # Reuse existing pool
                        adapter, ref_count = self._shared_pools[self._pool_key]
                        self._shared_pools[self._pool_key] = (adapter, ref_count + 1)
                        self._adapter = adapter
                        self._connected = True
                        return self._adapter

                    # Create new shared pool
                    self._adapter = await self._create_adapter()
                    self._shared_pools[self._pool_key] = (self._adapter, 1)
            else:
                # Create dedicated pool
                self._adapter = await self._create_adapter()

        return self._adapter

    async def _create_adapter(self) -> DatabaseAdapter:
        """Create a new database adapter with retry logic for initial connection."""
        db_type = DatabaseType(self.config["database_type"].lower())
        db_config = DatabaseConfig(
            type=db_type,
            host=self.config.get("host"),
            port=self.config.get("port"),
            database=self.config.get("database"),
            user=self.config.get("user"),
            password=self.config.get("password"),
            connection_string=self.config.get("connection_string"),
            pool_size=self.config.get("pool_size", 10),
            max_pool_size=self.config.get("max_pool_size", 20),
            command_timeout=self.config.get("timeout", 60.0),
        )

        if db_type == DatabaseType.POSTGRESQL:
            adapter = PostgreSQLAdapter(db_config)
        elif db_type == DatabaseType.MYSQL:
            adapter = MySQLAdapter(db_config)
        elif db_type == DatabaseType.SQLITE:
            adapter = SQLiteAdapter(db_config)
        else:
            raise NodeExecutionError(f"Unsupported database type: {db_type}")

        # Retry connection with exponential backoff
        last_error = None
        for attempt in range(self._retry_config.max_retries):
            try:
                await adapter.connect()
                self._connected = True
                return adapter
            except Exception as e:
                last_error = e

                # Check if error is retryable
                if not self._retry_config.should_retry(e):
                    raise

                # Check if we have more attempts
                if attempt >= self._retry_config.max_retries - 1:
                    raise NodeExecutionError(
                        f"Failed to connect after {self._retry_config.max_retries} attempts: {e}"
                    )

                # Calculate delay
                delay = self._retry_config.get_delay(attempt)

                # Wait before retry
                await asyncio.sleep(delay)

        # Should not reach here, but just in case
        raise NodeExecutionError(
            f"Failed to connect after {self._retry_config.max_retries} attempts: {last_error}"
        )

    async def async_run(self, **inputs) -> dict[str, Any]:
        """Execute database query asynchronously with optional access control."""
        try:
            # Get runtime parameters
            query = inputs.get("query", self.config.get("query"))
            params = inputs.get("params", self.config.get("params"))
            fetch_mode = FetchMode(
                inputs.get("fetch_mode", self.config.get("fetch_mode", "all")).lower()
            )
            fetch_size = inputs.get("fetch_size", self.config.get("fetch_size"))
            result_format = inputs.get(
                "result_format", self.config.get("result_format", "dict")
            )
            user_context = inputs.get("user_context")

            if not query:
                raise NodeExecutionError("No query provided")

            # Handle parameter style conversion
            if params is not None:
                if isinstance(params, (list, tuple)):
                    # Convert positional parameters to named parameters
                    query, params = self._convert_to_named_parameters(query, params)
                elif not isinstance(params, dict):
                    # Single parameter - wrap in list and convert
                    query, params = self._convert_to_named_parameters(query, [params])

            # Validate query for security
            if self._validate_queries:
                try:
                    QueryValidator.validate_query(query, allow_admin=self._allow_admin)
                except NodeValidationError as e:
                    raise NodeExecutionError(
                        f"Query validation failed: {e}. "
                        "Set validate_queries=False to bypass (not recommended)."
                    )

            # Check access control if enabled
            if self.access_control_manager and user_context:
                from kailash.access_control import NodePermission

                decision = self.access_control_manager.check_node_access(
                    user_context, self.metadata.name, NodePermission.EXECUTE
                )
                if not decision.allowed:
                    raise NodeExecutionError(f"Access denied: {decision.reason}")

            # Get adapter
            adapter = await self._get_adapter()

            # Execute query with retry logic
            result = await self._execute_with_retry(
                adapter=adapter,
                query=query,
                params=params,
                fetch_mode=fetch_mode,
                fetch_size=fetch_size,
                user_context=user_context,
            )

            # Format results based on requested format
            formatted_data = self._format_results(result, result_format)

            # For DataFrame, we need special handling for row count
            row_count = 0
            if result_format == "dataframe":
                try:
                    row_count = len(formatted_data)
                except:
                    # If pandas isn't available, formatted_data is still a list
                    row_count = (
                        len(result)
                        if isinstance(result, list)
                        else (1 if result else 0)
                    )
            else:
                row_count = (
                    len(result) if isinstance(result, list) else (1 if result else 0)
                )

            # Extract column names if available
            columns = []
            if result and isinstance(result, list) and result:
                if isinstance(result[0], dict):
                    columns = list(result[0].keys())

            # Handle DataFrame serialization for JSON compatibility
            if result_format == "dataframe":
                try:
                    import pandas as pd

                    if isinstance(formatted_data, pd.DataFrame):
                        # Convert DataFrame to JSON-compatible format
                        serializable_data = {
                            "dataframe": formatted_data.to_dict("records"),
                            "columns": formatted_data.columns.tolist(),
                            "index": formatted_data.index.tolist(),
                            "_type": "dataframe",
                        }
                    else:
                        # pandas not available, use regular data
                        serializable_data = formatted_data
                except ImportError:
                    serializable_data = formatted_data
            else:
                serializable_data = formatted_data

            result_dict = {
                "result": {
                    "data": serializable_data,
                    "row_count": row_count,
                    "query": query,
                    "database_type": self.config["database_type"],
                    "format": result_format,
                }
            }

            # Add columns info for list format
            if result_format == "list" and columns:
                result_dict["result"]["columns"] = columns

            return result_dict

        except NodeExecutionError:
            # Re-raise our own errors
            raise
        except Exception as e:
            # Wrap other errors
            raise NodeExecutionError(f"Database query failed: {str(e)}")

    async def process(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Async process method for middleware compatibility."""
        return await self.async_run(**inputs)

    async def execute_many_async(
        self, query: str, params_list: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Execute the same query multiple times with different parameters.

        This is useful for bulk inserts, updates, or deletes. The operation
        runs in a single transaction (in auto or manual mode) for better
        performance and atomicity.

        Args:
            query: SQL query to execute multiple times
            params_list: List of parameter dictionaries

        Returns:
            dict: Result with affected row count

        Example:
            >>> params_list = [
            ...     {"name": "Alice", "age": 30},
            ...     {"name": "Bob", "age": 25},
            ...     {"name": "Charlie", "age": 35},
            ... ]
            >>> result = await node.execute_many_async(
            ...     query="INSERT INTO users (name, age) VALUES (:name, :age)",
            ...     params_list=params_list
            ... )
            >>> print(result["result"]["affected_rows"])  # 3
        """
        if not params_list:
            return {
                "result": {
                    "affected_rows": 0,
                    "query": query,
                    "database_type": self.config["database_type"],
                }
            }

        # Validate query if security is enabled
        if self._validate_queries:
            try:
                QueryValidator.validate_query(query, allow_admin=self._allow_admin)
            except NodeValidationError as e:
                raise NodeExecutionError(
                    f"Query validation failed: {e}. "
                    "Set validate_queries=False to bypass (not recommended)."
                )

        try:
            # Get adapter
            adapter = await self._get_adapter()

            # Execute batch with retry logic
            affected_rows = await self._execute_many_with_retry(
                adapter=adapter,
                query=query,
                params_list=params_list,
            )

            return {
                "result": {
                    "affected_rows": affected_rows,
                    "batch_size": len(params_list),
                    "query": query,
                    "database_type": self.config["database_type"],
                }
            }

        except NodeExecutionError:
            raise
        except Exception as e:
            raise NodeExecutionError(f"Batch operation failed: {str(e)}")

    async def begin_transaction(self):
        """Begin a manual transaction.

        Returns:
            Transaction context that can be used for manual control

        Raises:
            NodeExecutionError: If transaction already active or mode is 'auto'
        """
        if self._transaction_mode != "manual":
            raise NodeExecutionError(
                "begin_transaction() can only be called in 'manual' transaction mode"
            )

        if self._active_transaction:
            raise NodeExecutionError("Transaction already active")

        adapter = await self._get_adapter()
        self._active_transaction = await adapter.begin_transaction()
        return self._active_transaction

    async def commit(self):
        """Commit the active transaction.

        Raises:
            NodeExecutionError: If no active transaction or mode is not 'manual'
        """
        if self._transaction_mode != "manual":
            raise NodeExecutionError(
                "commit() can only be called in 'manual' transaction mode"
            )

        if not self._active_transaction:
            raise NodeExecutionError("No active transaction to commit")

        adapter = await self._get_adapter()
        try:
            await adapter.commit_transaction(self._active_transaction)
        finally:
            # Always clear transaction, even on error
            self._active_transaction = None

    async def rollback(self):
        """Rollback the active transaction.

        Raises:
            NodeExecutionError: If no active transaction or mode is not 'manual'
        """
        if self._transaction_mode != "manual":
            raise NodeExecutionError(
                "rollback() can only be called in 'manual' transaction mode"
            )

        if not self._active_transaction:
            raise NodeExecutionError("No active transaction to rollback")

        adapter = await self._get_adapter()
        try:
            await adapter.rollback_transaction(self._active_transaction)
        finally:
            # Always clear transaction, even on error
            self._active_transaction = None

    async def _execute_with_retry(
        self,
        adapter: DatabaseAdapter,
        query: str,
        params: Any,
        fetch_mode: FetchMode,
        fetch_size: Optional[int],
        user_context: Any = None,
    ) -> Any:
        """Execute query with retry logic for transient failures.

        Args:
            adapter: Database adapter
            query: SQL query
            params: Query parameters
            fetch_mode: How to fetch results
            fetch_size: Number of rows for 'many' mode
            user_context: User context for access control

        Returns:
            Query results

        Raises:
            NodeExecutionError: After all retry attempts are exhausted
        """
        last_error = None

        for attempt in range(self._retry_config.max_retries):
            try:
                # Execute query with transaction
                result = await self._execute_with_transaction(
                    adapter=adapter,
                    query=query,
                    params=params,
                    fetch_mode=fetch_mode,
                    fetch_size=fetch_size,
                )

                # Apply data masking if access control is enabled
                if self.access_control_manager and user_context:
                    if isinstance(result, list):
                        masked_result = []
                        for row in result:
                            masked_row = self.access_control_manager.apply_data_masking(
                                user_context, self.metadata.name, row
                            )
                            masked_result.append(masked_row)
                        result = masked_result
                    elif isinstance(result, dict):
                        result = self.access_control_manager.apply_data_masking(
                            user_context, self.metadata.name, result
                        )

                return result

            except Exception as e:
                last_error = e

                # Check if error is retryable
                if not self._retry_config.should_retry(e):
                    raise

                # Check if we have more attempts
                if attempt >= self._retry_config.max_retries - 1:
                    raise

                # Calculate delay
                delay = self._retry_config.get_delay(attempt)

                # Log retry attempt (if logging is available)
                try:
                    self.logger.warning(
                        f"Query failed (attempt {attempt + 1}/{self._retry_config.max_retries}): {e}. "
                        f"Retrying in {delay:.2f} seconds..."
                    )
                except AttributeError:
                    # No logger available
                    pass

                # Wait before retry
                await asyncio.sleep(delay)

                # For connection errors, try to reconnect
                if "pool is closed" in str(e).lower() or "connection" in str(e).lower():
                    try:
                        # Clear existing adapter to force reconnection
                        if self._share_pool and self._pool_key:
                            # Remove from shared pools to force recreation
                            async with self._get_pool_lock():
                                if self._pool_key in self._shared_pools:
                                    _, ref_count = self._shared_pools[self._pool_key]
                                    if ref_count <= 1:
                                        del self._shared_pools[self._pool_key]
                                    else:
                                        # This shouldn't happen with a closed pool
                                        del self._shared_pools[self._pool_key]

                        self._adapter = None
                        self._connected = False
                        adapter = await self._get_adapter()
                    except Exception:
                        # If reconnection fails, continue with retry loop
                        pass

        # All retries exhausted
        raise NodeExecutionError(
            f"Query failed after {self._retry_config.max_retries} attempts: {last_error}"
        )

    async def _execute_many_with_retry(
        self, adapter: DatabaseAdapter, query: str, params_list: list[dict[str, Any]]
    ) -> int:
        """Execute batch operation with retry logic.

        Args:
            adapter: Database adapter
            query: SQL query to execute
            params_list: List of parameter dictionaries

        Returns:
            Number of affected rows

        Raises:
            NodeExecutionError: After all retry attempts are exhausted
        """
        last_error = None

        for attempt in range(self._retry_config.max_retries):
            try:
                # Execute batch with transaction
                return await self._execute_many_with_transaction(
                    adapter=adapter,
                    query=query,
                    params_list=params_list,
                )

            except Exception as e:
                last_error = e

                # Check if error is retryable
                if not self._retry_config.should_retry(e):
                    raise

                # Check if we have more attempts
                if attempt >= self._retry_config.max_retries - 1:
                    raise

                # Calculate delay
                delay = self._retry_config.get_delay(attempt)

                # Wait before retry
                await asyncio.sleep(delay)

                # For connection errors, try to reconnect
                if "pool is closed" in str(e).lower() or "connection" in str(e).lower():
                    try:
                        # Clear existing adapter to force reconnection
                        if self._share_pool and self._pool_key:
                            # Remove from shared pools to force recreation
                            async with self._get_pool_lock():
                                if self._pool_key in self._shared_pools:
                                    _, ref_count = self._shared_pools[self._pool_key]
                                    if ref_count <= 1:
                                        del self._shared_pools[self._pool_key]
                                    else:
                                        # This shouldn't happen with a closed pool
                                        del self._shared_pools[self._pool_key]

                        self._adapter = None
                        self._connected = False
                        adapter = await self._get_adapter()
                    except Exception:
                        # If reconnection fails, continue with retry loop
                        pass

        # All retries exhausted
        raise NodeExecutionError(
            f"Batch operation failed after {self._retry_config.max_retries} attempts: {last_error}"
        )

    async def _execute_many_with_transaction(
        self, adapter: DatabaseAdapter, query: str, params_list: list[dict[str, Any]]
    ) -> int:
        """Execute batch operation with automatic transaction management.

        Args:
            adapter: Database adapter
            query: SQL query to execute
            params_list: List of parameter dictionaries

        Returns:
            Number of affected rows (estimated)

        Raises:
            Exception: Re-raises any execution errors after rollback
        """
        if self._active_transaction:
            # Use existing transaction (manual mode)
            await adapter.execute_many(query, params_list, self._active_transaction)
            # Most adapters don't return row count from execute_many
            return len(params_list)
        elif self._transaction_mode == "auto":
            # Auto-transaction mode
            transaction = await adapter.begin_transaction()
            try:
                await adapter.execute_many(query, params_list, transaction)
                await adapter.commit_transaction(transaction)
                return len(params_list)
            except Exception:
                await adapter.rollback_transaction(transaction)
                raise
        else:
            # No transaction mode
            await adapter.execute_many(query, params_list)
            return len(params_list)

    async def _execute_with_transaction(
        self,
        adapter: DatabaseAdapter,
        query: str,
        params: Any,
        fetch_mode: FetchMode,
        fetch_size: Optional[int],
    ) -> Any:
        """Execute query with automatic transaction management.

        Args:
            adapter: Database adapter
            query: SQL query
            params: Query parameters
            fetch_mode: How to fetch results
            fetch_size: Number of rows for 'many' mode

        Returns:
            Query results

        Raises:
            Exception: Re-raises any execution errors after rollback
        """
        if self._active_transaction:
            # Use existing transaction (manual mode)
            return await adapter.execute(
                query=query,
                params=params,
                fetch_mode=fetch_mode,
                fetch_size=fetch_size,
                transaction=self._active_transaction,
            )
        elif self._transaction_mode == "auto":
            # Auto-transaction mode
            transaction = await adapter.begin_transaction()
            try:
                result = await adapter.execute(
                    query=query,
                    params=params,
                    fetch_mode=fetch_mode,
                    fetch_size=fetch_size,
                    transaction=transaction,
                )
                await adapter.commit_transaction(transaction)
                return result
            except Exception:
                await adapter.rollback_transaction(transaction)
                raise
        else:
            # No transaction mode
            return await adapter.execute(
                query=query,
                params=params,
                fetch_mode=fetch_mode,
                fetch_size=fetch_size,
            )

    @classmethod
    async def get_pool_metrics(cls) -> dict[str, Any]:
        """Get metrics for all shared connection pools.

        Returns:
            dict: Pool metrics including pool count, connections per pool, etc.
        """
        async with cls._get_pool_lock():
            metrics = {"total_pools": len(cls._shared_pools), "pools": []}

            for pool_key, (adapter, ref_count) in cls._shared_pools.items():
                pool_info = {
                    "key": pool_key,
                    "reference_count": ref_count,
                    "type": adapter.__class__.__name__,
                }

                # Try to get pool-specific metrics if available
                if hasattr(adapter, "_pool") and adapter._pool:
                    pool = adapter._pool
                    if hasattr(pool, "size"):
                        pool_info["pool_size"] = pool.size()
                    if hasattr(pool, "_holders"):
                        pool_info["active_connections"] = len(
                            [h for h in pool._holders if h._in_use]
                        )
                    elif hasattr(pool, "size") and hasattr(pool, "freesize"):
                        pool_info["active_connections"] = pool.size - pool.freesize

                metrics["pools"].append(pool_info)

            return metrics

    @classmethod
    async def clear_shared_pools(cls) -> None:
        """Clear all shared connection pools. Use with caution!"""
        async with cls._get_pool_lock():
            for pool_key, (adapter, _) in list(cls._shared_pools.items()):
                try:
                    await adapter.disconnect()
                except Exception:
                    pass  # Best effort
            cls._shared_pools.clear()

    def get_pool_info(self) -> dict[str, Any]:
        """Get information about this instance's connection pool.

        Returns:
            dict: Pool information including shared status and metrics
        """
        info = {
            "shared": self._share_pool,
            "pool_key": self._pool_key,
            "connected": self._connected,
        }

        if self._adapter and hasattr(self._adapter, "_pool") and self._adapter._pool:
            pool = self._adapter._pool
            if hasattr(pool, "size"):
                info["pool_size"] = pool.size()
            if hasattr(pool, "_holders"):
                info["active_connections"] = len(
                    [h for h in pool._holders if h._in_use]
                )
            elif hasattr(pool, "size") and hasattr(pool, "freesize"):
                info["active_connections"] = pool.size - pool.freesize

        return info

    async def execute_with_version_check(
        self,
        query: str,
        params: dict[str, Any],
        expected_version: Optional[int] = None,
        record_id: Optional[Any] = None,
        table_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute a query with optimistic locking version check.

        Args:
            query: SQL query to execute (UPDATE or DELETE)
            params: Query parameters
            expected_version: Expected version number for conflict detection
            record_id: ID of the record being updated (for retry)
            table_name: Table name (for retry to re-read current version)

        Returns:
            dict: Result with version information and conflict status

        Raises:
            NodeExecutionError: On version conflict or database error
        """
        if not self._enable_optimistic_locking:
            # Just execute normally if optimistic locking is disabled
            result = await self.execute_async(query=query, params=params)
            return {
                "result": result,
                "version_checked": False,
                "status": LockStatus.SUCCESS,
            }

        # Add version check to the query
        if expected_version is not None:
            # Ensure version field is in params
            if "expected_version" in query:
                # Query already uses :expected_version, just ensure it's set
                params["expected_version"] = expected_version
            else:
                # Use standard version field
                params[self._version_field] = expected_version

            # For UPDATE queries, also add version increment
            if "UPDATE" in query.upper() and "SET" in query.upper():
                # Find SET clause and add version increment
                set_match = re.search(r"(SET\s+)(.+?)(\s+WHERE)", query, re.IGNORECASE)
                if set_match:
                    set_clause = set_match.group(2)
                    # Add version increment if not already present
                    if self._version_field not in set_clause:
                        new_set_clause = f"{set_clause}, {self._version_field} = {self._version_field} + 1"
                        query = (
                            query[: set_match.start(2)]
                            + new_set_clause
                            + query[set_match.end(2) :]
                        )

            # Modify query to include version check in WHERE clause (only if not already present)
            # Check for version condition in WHERE clause specifically, not just anywhere in query
            where_clause_pattern = (
                r"WHERE\s+.*?" + re.escape(self._version_field) + r"\s*="
            )
            has_version_check_in_where = (
                re.search(where_clause_pattern, query, re.IGNORECASE) is not None
                or ":expected_version" in query
            )
            if not has_version_check_in_where:
                if "WHERE" in query.upper():
                    query += f" AND {self._version_field} = :{self._version_field}"
                else:
                    query += f" WHERE {self._version_field} = :{self._version_field}"

        # Try to execute with version check
        retry_count = 0
        for attempt in range(self._version_retry_attempts):
            try:
                result = await self.execute_async(query=query, params=params)

                # Check if any rows were affected
                rows_affected = 0
                rows_affected_found = False
                if isinstance(result.get("result"), dict):
                    # Check if we have data array with rows_affected
                    data = result["result"].get("data", [])
                    if data and isinstance(data, list) and len(data) > 0:
                        if isinstance(data[0], dict) and "rows_affected" in data[0]:
                            rows_affected = data[0]["rows_affected"]
                            rows_affected_found = True

                    # Only check direct keys if we haven't found rows_affected in data
                    if not rows_affected_found:
                        rows_affected = (
                            result["result"].get("rows_affected", 0)
                            or result["result"].get("rowcount", 0)
                            or result["result"].get("affected_rows", 0)
                            or result["result"].get("row_count", 0)
                        )

                if rows_affected == 0 and expected_version is not None:
                    # Version conflict detected
                    if self._conflict_resolution == "fail_fast":
                        raise NodeExecutionError(
                            f"Version conflict: expected version {expected_version} not found"
                        )
                    elif (
                        self._conflict_resolution == "retry"
                        and record_id
                        and table_name
                    ):
                        # Read current version
                        current = await self.execute_async(
                            query=f"SELECT {self._version_field} FROM {table_name} WHERE id = :id",
                            params={"id": record_id},
                        )

                        if current["result"]["data"]:
                            current_version = current["result"]["data"][0][
                                self._version_field
                            ]
                            params[self._version_field] = current_version
                            # Update expected version for next attempt
                            expected_version = current_version
                            retry_count += 1
                            continue
                        else:
                            return {
                                "result": None,
                                "status": LockStatus.RECORD_NOT_FOUND,
                                "version_checked": True,
                                "retry_count": retry_count,
                            }
                    elif self._conflict_resolution == "last_writer_wins":
                        # Remove version check and try again
                        params_no_version = params.copy()
                        params_no_version.pop(self._version_field, None)
                        query_no_version = query.replace(
                            f" AND {self._version_field} = :{self._version_field}", ""
                        )
                        result = await self.execute_async(
                            query=query_no_version, params=params_no_version
                        )
                        return {
                            "result": result,
                            "status": LockStatus.SUCCESS,
                            "version_checked": False,
                            "conflict_resolved": "last_writer_wins",
                            "retry_count": retry_count,
                        }

                # Success - increment version for UPDATE queries
                if "UPDATE" in query.upper() and rows_affected > 0:
                    # The query should have incremented the version
                    new_version = (
                        (expected_version or 0) + 1
                        if expected_version is not None
                        else None
                    )
                    return {
                        "result": result,
                        "status": LockStatus.SUCCESS,
                        "version_checked": True,
                        "new_version": new_version,
                        "rows_affected": rows_affected,
                        "retry_count": retry_count,
                    }
                else:
                    return {
                        "result": result,
                        "status": LockStatus.SUCCESS,
                        "version_checked": True,
                        "rows_affected": rows_affected,
                        "retry_count": retry_count,
                    }

            except NodeExecutionError:
                if attempt >= self._version_retry_attempts - 1:
                    raise
                await asyncio.sleep(0.1 * (attempt + 1))  # Exponential backoff

        return {
            "result": None,
            "status": LockStatus.RETRY_EXHAUSTED,
            "version_checked": True,
            "retry_count": self._version_retry_attempts,
        }

    async def read_with_version(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute a SELECT query and extract version information.

        Args:
            query: SELECT query to execute
            params: Query parameters

        Returns:
            dict: Result with version information included
        """
        result = await self.execute_async(query=query, params=params)

        if self._enable_optimistic_locking and result.get("result", {}).get("data"):
            # Extract version from results
            data = result["result"]["data"]
            if isinstance(data, list) and len(data) > 0:
                # Single record
                if len(data) == 1 and self._version_field in data[0]:
                    return {
                        "result": result,
                        "version": data[0][self._version_field],
                        "record": data[0],
                    }
                # Multiple records - include version in each
                else:
                    versions = []
                    for record in data:
                        if self._version_field in record:
                            versions.append(record[self._version_field])
                    return {
                        "result": result,
                        "versions": versions,
                        "records": data,
                    }

        return result

    def build_versioned_update_query(
        self,
        table_name: str,
        update_fields: dict[str, Any],
        where_clause: str,
        increment_version: bool = True,
    ) -> str:
        """Build an UPDATE query with version increment.

        Args:
            table_name: Name of the table to update
            update_fields: Fields to update (excluding version)
            where_clause: WHERE clause (without WHERE keyword)
            increment_version: Whether to increment the version field

        Returns:
            str: UPDATE query with version handling
        """
        if not self._enable_optimistic_locking:
            # Build normal update query
            set_parts = [f"{field} = :{field}" for field in update_fields]
            return (
                f"UPDATE {table_name} SET {', '.join(set_parts)} WHERE {where_clause}"
            )

        # Build versioned update query
        set_parts = [f"{field} = :{field}" for field in update_fields]

        if increment_version:
            set_parts.append(f"{self._version_field} = {self._version_field} + 1")

        return f"UPDATE {table_name} SET {', '.join(set_parts)} WHERE {where_clause}"

    def _convert_to_named_parameters(
        self, query: str, parameters: list
    ) -> tuple[str, dict]:
        """Convert positional parameters to named parameters for various SQL dialects.

        This method handles conversion from different SQL parameter styles to a
        consistent named parameter format that works with async database drivers.

        Args:
            query: SQL query with positional placeholders (?, $1, %s)
            parameters: List of parameter values

        Returns:
            Tuple of (modified_query, parameter_dict)

        Examples:
            >>> # SQLite style
            >>> query = "SELECT * FROM users WHERE age > ? AND active = ?"
            >>> params = [25, True]
            >>> new_query, param_dict = node._convert_to_named_parameters(query, params)
            >>> # Returns: ("SELECT * FROM users WHERE age > :p0 AND active = :p1",
            >>> #          {"p0": 25, "p1": True})

            >>> # PostgreSQL style
            >>> query = "UPDATE users SET name = $1 WHERE id = $2"
            >>> params = ["John", 123]
            >>> new_query, param_dict = node._convert_to_named_parameters(query, params)
            >>> # Returns: ("UPDATE users SET name = :p0 WHERE id = :p1",
            >>> #          {"p0": "John", "p1": 123})
        """
        # Create parameter dictionary
        param_dict = {}
        for i, value in enumerate(parameters):
            param_dict[f"p{i}"] = value

        # Replace different placeholder formats with named parameters
        modified_query = query

        # Handle SQLite-style ? placeholders
        placeholder_count = 0

        def replace_question_mark(match):
            nonlocal placeholder_count
            replacement = f":p{placeholder_count}"
            placeholder_count += 1
            return replacement

        modified_query = re.sub(r"\?", replace_question_mark, modified_query)

        # Handle PostgreSQL-style $1, $2, etc. placeholders
        def replace_postgres_placeholder(match):
            index = int(match.group(1)) - 1  # PostgreSQL uses 1-based indexing
            return f":p{index}"

        modified_query = re.sub(
            r"\$(\d+)", replace_postgres_placeholder, modified_query
        )

        # Handle MySQL-style %s placeholders
        placeholder_count = 0

        def replace_mysql_placeholder(match):
            nonlocal placeholder_count
            replacement = f":p{placeholder_count}"
            placeholder_count += 1
            return replacement

        modified_query = re.sub(r"%s", replace_mysql_placeholder, modified_query)

        return modified_query, param_dict

    def _format_results(self, data: list[dict], result_format: str) -> Any:
        """Format query results according to specified format.

        Args:
            data: List of dictionaries from database query
            result_format: Desired output format ('dict', 'list', 'dataframe')

        Returns:
            Formatted results

        Formats:
            - 'dict': List of dictionaries (default) - column names as keys
            - 'list': List of lists - values only, no column names
            - 'dataframe': Pandas DataFrame (if pandas is available)
        """
        if not data:
            # Return empty structure based on format
            if result_format == "dataframe":
                try:
                    import pandas as pd

                    return pd.DataFrame()
                except ImportError:
                    # Fall back to dict if pandas not available
                    return []
            elif result_format == "list":
                return []
            else:
                return []

        if result_format == "dict":
            # Already in dict format from adapters
            return data

        elif result_format == "list":
            # Convert to list of lists (values only)
            if data:
                # Get column order from first row
                columns = list(data[0].keys())
                return [[row.get(col) for col in columns] for row in data]
            return []

        elif result_format == "dataframe":
            # Convert to pandas DataFrame if available
            try:
                import pandas as pd

                return pd.DataFrame(data)
            except ImportError:
                # Log warning and fall back to dict format
                if hasattr(self, "logger"):
                    self.logger.warning(
                        "Pandas not installed. Install with: pip install pandas. "
                        "Falling back to dict format."
                    )
                return data

        else:
            # Unknown format - default to dict with warning
            if hasattr(self, "logger"):
                self.logger.warning(
                    f"Unknown result_format '{result_format}', defaulting to 'dict'"
                )
            return data

    async def cleanup(self):
        """Clean up database connections."""
        # Rollback any active transaction
        if self._active_transaction and self._adapter:
            try:
                await self._adapter.rollback_transaction(self._active_transaction)
            except Exception:
                pass  # Best effort cleanup
            self._active_transaction = None

        if self._adapter and self._connected:
            if self._share_pool and self._pool_key:
                # Decrement reference count for shared pool
                async with self._get_pool_lock():
                    if self._pool_key in self._shared_pools:
                        adapter, ref_count = self._shared_pools[self._pool_key]
                        if ref_count > 1:
                            # Others still using the pool
                            self._shared_pools[self._pool_key] = (
                                adapter,
                                ref_count - 1,
                            )
                        else:
                            # Last reference, close the pool
                            del self._shared_pools[self._pool_key]
                            await adapter.disconnect()
            else:
                # Dedicated pool, close directly
                await self._adapter.disconnect()

            self._connected = False
            self._adapter = None

    def __del__(self):
        """Ensure connections are closed."""
        if self._adapter and self._connected:
            # Schedule cleanup in the event loop if it exists
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_closed():
                    loop.create_task(self.cleanup())
            except RuntimeError:
                # No event loop, can't clean up async resources
                pass
