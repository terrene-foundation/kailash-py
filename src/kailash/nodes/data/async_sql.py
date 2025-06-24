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
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, AsyncIterator, Optional, Union

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


class DatabaseType(Enum):
    """Supported database types."""

    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"


class FetchMode(Enum):
    """Result fetch modes."""

    ONE = "one"  # Fetch single row
    ALL = "all"  # Fetch all rows
    MANY = "many"  # Fetch specific number of rows
    ITERATOR = "iterator"  # Return async iterator


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
            if isinstance(value, Decimal):
                # Convert Decimal to float for JSON serialization
                converted[key] = float(value)
            elif isinstance(value, datetime):
                # Convert datetime to ISO format string
                converted[key] = value.isoformat()
            elif isinstance(value, date):
                # Convert date to ISO format string
                converted[key] = value.isoformat()
            else:
                converted[key] = value
        return converted

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
    ) -> Any:
        """Execute query and return results."""
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
    ) -> Any:
        """Execute query and return results."""
        async with self._pool.acquire() as conn:
            # Convert dict params to positional for asyncpg
            if isinstance(params, dict):
                # Simple parameter substitution for named params
                # In production, use a proper SQL parser
                query_params = []
                for i, (key, value) in enumerate(params.items(), 1):
                    query = query.replace(f":{key}", f"${i}")
                    query_params.append(value)
                params = query_params

            # Ensure params is a list/tuple for asyncpg
            if params is None:
                params = []
            elif not isinstance(params, (list, tuple)):
                params = [params]

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
        self, query: str, params_list: list[Union[tuple, dict]]
    ) -> None:
        """Execute query multiple times with different parameters."""
        async with self._pool.acquire() as conn:
            # Convert all dict params to tuples
            converted_params = []
            for params in params_list:
                if isinstance(params, dict):
                    query_params = []
                    for i, (key, value) in enumerate(params.items(), 1):
                        if i == 1:  # Only replace on first iteration
                            query = query.replace(f":{key}", f"${i}")
                        query_params.append(value)
                    converted_params.append(query_params)
                else:
                    converted_params.append(params)

            await conn.executemany(query, converted_params)

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
    ) -> Any:
        """Execute query and return results."""
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

    async def execute_many(
        self, query: str, params_list: list[Union[tuple, dict]]
    ) -> None:
        """Execute query multiple times with different parameters."""
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
    ) -> Any:
        """Execute query and return results."""
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
        self, query: str, params_list: list[Union[tuple, dict]]
    ) -> None:
        """Execute query multiple times with different parameters."""
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

    Example:
        >>> node = AsyncSQLDatabaseNode(
        ...     name="fetch_users",
        ...     database_type="postgresql",
        ...     host="localhost",
        ...     database="myapp",
        ...     user="dbuser",
        ...     password="dbpass",
        ...     query="SELECT * FROM users WHERE active = :active",
        ...     params={"active": True},
        ...     fetch_mode="all"
        ... )
        >>> result = await node.async_run()
        >>> users = result["data"]
    """

    def __init__(self, **config):
        self._adapter: Optional[DatabaseAdapter] = None
        self._connected = False
        # Extract access control manager before passing to parent
        self.access_control_manager = config.pop("access_control_manager", None)
        super().__init__(**config)

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
        ]

        # Convert list to dict as required by base class
        return {param.name: param for param in params}

    def _validate_config(self):
        """Validate node configuration."""
        super()._validate_config()

        # Validate database type
        db_type = self.config.get("database_type", "").lower()
        if db_type not in ["postgresql", "mysql", "sqlite"]:
            raise NodeValidationError(
                f"Invalid database_type: {db_type}. "
                "Must be one of: postgresql, mysql, sqlite"
            )

        # Validate connection parameters
        if not self.config.get("connection_string"):
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

    async def _get_adapter(self) -> DatabaseAdapter:
        """Get or create database adapter."""
        if not self._adapter:
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
                self._adapter = PostgreSQLAdapter(db_config)
            elif db_type == DatabaseType.MYSQL:
                self._adapter = MySQLAdapter(db_config)
            elif db_type == DatabaseType.SQLITE:
                self._adapter = SQLiteAdapter(db_config)
            else:
                raise NodeExecutionError(f"Unsupported database type: {db_type}")

        if not self._connected:
            await self._adapter.connect()
            self._connected = True

        return self._adapter

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
            user_context = inputs.get("user_context")

            if not query:
                raise NodeExecutionError("No query provided")

            # Check access control if enabled
            if self.access_control_manager and user_context:
                from kailash.access_control import NodePermission

                decision = self.access_control_manager.check_node_access(
                    user_context, self.metadata.name, NodePermission.EXECUTE
                )
                if not decision.allowed:
                    raise NodeExecutionError(f"Access denied: {decision.reason}")

            # Get adapter and execute query
            adapter = await self._get_adapter()

            # Execute query with retry logic
            max_retries = 3
            retry_delay = 1.0

            for attempt in range(max_retries):
                try:
                    result = await adapter.execute(
                        query=query,
                        params=params,
                        fetch_mode=fetch_mode,
                        fetch_size=fetch_size,
                    )

                    # Apply data masking if access control is enabled
                    if (
                        self.access_control_manager
                        and user_context
                        and isinstance(result, list)
                    ):
                        masked_result = []
                        for row in result:
                            masked_row = self.access_control_manager.apply_data_masking(
                                user_context, self.metadata.name, row
                            )
                            masked_result.append(masked_row)
                        result = masked_result
                    elif (
                        self.access_control_manager
                        and user_context
                        and isinstance(result, dict)
                    ):
                        result = self.access_control_manager.apply_data_masking(
                            user_context, self.metadata.name, result
                        )

                    return {
                        "result": {
                            "data": result,
                            "row_count": (
                                len(result)
                                if isinstance(result, list)
                                else (1 if result else 0)
                            ),
                            "query": query,
                            "database_type": self.config["database_type"],
                        }
                    }

                except Exception as e:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (2**attempt))
                        continue
                    raise

        except Exception as e:
            raise NodeExecutionError(f"Database query failed: {str(e)}")

    async def process(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Async process method for middleware compatibility."""
        return await self.async_run(**inputs)

    async def cleanup(self):
        """Clean up database connections."""
        if self._adapter and self._connected:
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
