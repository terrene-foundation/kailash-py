# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
DatabaseESA - Enterprise System Agent for Database Systems.

Provides trust-aware proxy access to database systems (PostgreSQL, MySQL, SQLite)
with automatic capability discovery, query validation, and constraint enforcement.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from eatp.chain import CapabilityType
from eatp.esa.base import (
    CapabilityMetadata,
    EnterpriseSystemAgent,
    ESAConfig,
    SystemConnectionInfo,
    SystemMetadata,
)
from eatp.esa.discovery import DatabaseCapabilityDiscoverer, DiscoveryResult
from eatp.esa.exceptions import ESAConnectionError, ESAOperationError
from eatp.operations import TrustOperations


class DatabaseType(Enum):
    """Supported database types."""

    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"


@dataclass
class QueryParseResult:
    """
    Result of query parsing.

    Attributes:
        query_type: Type of query (SELECT, INSERT, UPDATE, DELETE)
        tables: List of tables accessed
        operations: List of operations (read, write, update, delete)
        is_safe: Whether query passes safety checks
        violations: List of safety violations
    """

    query_type: str
    tables: List[str]
    operations: List[str]
    is_safe: bool = True
    violations: List[str] = None

    def __post_init__(self):
        if self.violations is None:
            self.violations = []


class DatabaseESA(EnterpriseSystemAgent):
    """
    Enterprise System Agent for Database Systems.

    Provides trust-aware access to databases with:
    - Automatic capability discovery from schema
    - Query parsing and validation
    - Constraint enforcement (row limits, allowed tables)
    - Connection pooling and retry logic
    - Comprehensive audit logging

    Supported Databases:
    - PostgreSQL (via asyncpg)
    - MySQL (via aiomysql)
    - SQLite (via aiosqlite)

    Example:
        # Initialize DatabaseESA
        esa = DatabaseESA(
            system_id="db-finance-001",
            connection_string="postgresql://user:pass@host/db",
            trust_operations=trust_ops,
            authority_id="org-acme",
            database_type=DatabaseType.POSTGRESQL,
        )

        # Establish trust
        await esa.establish_trust(authority_id="org-acme")

        # Execute query
        result = await esa.execute(
            operation="read_transactions",
            parameters={"limit": 100},
            requesting_agent_id="agent-001",
        )
    """

    def __init__(
        self,
        system_id: str,
        connection_string: str,
        trust_ops: TrustOperations,
        authority_id: str,
        database_type: DatabaseType = DatabaseType.POSTGRESQL,
        system_name: Optional[str] = None,
        config: Optional[ESAConfig] = None,
        max_row_limit: int = 10000,
        allowed_tables: Optional[List[str]] = None,
    ):
        """
        Initialize DatabaseESA.

        Args:
            system_id: Unique identifier for this database
            connection_string: Database connection string
            trust_ops: TrustOperations instance
            authority_id: Authority that will establish trust
            database_type: Type of database (PostgreSQL, MySQL, SQLite)
            system_name: Human-readable name (defaults to system_id)
            config: ESA configuration (optional)
            max_row_limit: Maximum rows per query (default 10000)
            allowed_tables: Optional whitelist of allowed tables
        """
        # Parse connection string to extract endpoint
        endpoint = self._parse_connection_endpoint(connection_string)

        # Initialize base class
        super().__init__(
            system_id=system_id,
            system_name=system_name or f"Database {system_id}",
            trust_ops=trust_ops,
            connection_info=SystemConnectionInfo(
                endpoint=endpoint,
                credentials={"connection_string": connection_string},
            ),
            metadata=SystemMetadata(
                system_type=f"database_{database_type.value}",
                vendor=database_type.value.upper(),
                tags=["database", database_type.value],
            ),
            config=config or ESAConfig(),
        )

        self.database_type = database_type
        self.connection_string = connection_string
        self.authority_id = authority_id
        self.max_row_limit = max_row_limit
        self.allowed_tables = allowed_tables

        # Database connection
        self._connection = None
        self._pool = None

        # Capability discoverer
        self._discoverer: Optional[DatabaseCapabilityDiscoverer] = None

    def _parse_connection_endpoint(self, connection_string: str) -> str:
        """
        Parse connection string to extract endpoint.

        Args:
            connection_string: Database connection string

        Returns:
            Endpoint string (e.g., "postgresql://host:5432/dbname")
        """
        # Remove credentials for endpoint display
        # Format: postgresql://user:pass@host:port/db -> postgresql://host:port/db
        pattern = r"([^:]+)://[^@]+@(.+)"
        match = re.match(pattern, connection_string)
        if match:
            protocol, rest = match.groups()
            return f"{protocol}://{rest}"
        return connection_string

    # =========================================================================
    # Connection Management
    # =========================================================================

    async def _initialize_connection(self) -> None:
        """
        Initialize database connection based on database type.

        Raises:
            ESAConnectionError: If connection initialization fails
        """
        try:
            if self.database_type == DatabaseType.POSTGRESQL:
                await self._init_postgresql()
            elif self.database_type == DatabaseType.MYSQL:
                await self._init_mysql()
            elif self.database_type == DatabaseType.SQLITE:
                await self._init_sqlite()
            else:
                raise ValueError(f"Unsupported database type: {self.database_type}")

        except Exception as e:
            raise ESAConnectionError(
                system_id=self.system_id,
                endpoint=self.connection_info.endpoint,
                reason=f"Failed to initialize connection: {str(e)}",
                original_error=e,
            )

    async def _init_postgresql(self) -> None:
        """Initialize PostgreSQL connection using asyncpg."""
        try:
            import asyncpg

            self._pool = await asyncpg.create_pool(
                self.connection_string,
                min_size=1,
                max_size=10,
                timeout=self.connection_info.timeout_seconds,
            )
        except ImportError:
            raise ESAConnectionError(
                system_id=self.system_id,
                endpoint=self.connection_info.endpoint,
                reason="asyncpg not installed. Install with: pip install asyncpg",
            )

    async def _init_mysql(self) -> None:
        """Initialize MySQL connection using aiomysql."""
        try:
            import aiomysql

            # Parse connection string
            # Format: mysql://user:pass@host:port/db
            pattern = r"mysql://([^:]+):([^@]+)@([^:/]+):?(\d+)?/(.+)"
            match = re.match(pattern, self.connection_string)
            if not match:
                raise ValueError("Invalid MySQL connection string format")

            user, password, host, port, database = match.groups()
            port = int(port) if port else 3306

            self._pool = await aiomysql.create_pool(
                host=host,
                port=port,
                user=user,
                password=password,
                db=database,
                minsize=1,
                maxsize=10,
            )
        except ImportError:
            raise ESAConnectionError(
                system_id=self.system_id,
                endpoint=self.connection_info.endpoint,
                reason="aiomysql not installed. Install with: pip install aiomysql",
            )

    async def _init_sqlite(self) -> None:
        """Initialize SQLite connection using aiosqlite."""
        try:
            import aiosqlite

            # Parse connection string
            # Format: sqlite:///path/to/db.db or sqlite:///:memory:
            db_path = self.connection_string.replace("sqlite:///", "")
            self._connection = await aiosqlite.connect(db_path)
            # Enable row factory for dict-like access
            self._connection.row_factory = aiosqlite.Row
        except ImportError:
            raise ESAConnectionError(
                system_id=self.system_id,
                endpoint=self.connection_info.endpoint,
                reason="aiosqlite not installed. Install with: pip install aiosqlite",
            )

    async def _close_connection(self) -> None:
        """Close database connection."""
        try:
            if self._pool:
                if self.database_type == DatabaseType.POSTGRESQL:
                    await self._pool.close()
                elif self.database_type == DatabaseType.MYSQL:
                    self._pool.close()
                    await self._pool.wait_closed()
                self._pool = None

            if self._connection:
                await self._connection.close()
                self._connection = None

        except Exception:
            pass  # Best effort cleanup

    # =========================================================================
    # Abstract Method Implementations
    # =========================================================================

    async def validate_connection(self) -> bool:
        """
        Validate database connection.

        Returns:
            True if connection is valid, False otherwise
        """
        try:
            if not self._connection and not self._pool:
                await self._initialize_connection()

            # Simple ping query
            if self.database_type == DatabaseType.POSTGRESQL:
                async with self._pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
            elif self.database_type == DatabaseType.MYSQL:
                async with self._pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute("SELECT 1")
            elif self.database_type == DatabaseType.SQLITE:
                await self._connection.execute("SELECT 1")

            return True

        except Exception:
            return False

    async def discover_capabilities(self) -> List[str]:
        """
        Discover capabilities from database schema.

        Returns:
            List of capability names (e.g., ["read_users", "write_orders"])
        """
        if not self._connection and not self._pool:
            await self._initialize_connection()

        # Create discoverer if not exists
        if not self._discoverer:
            # Create wrapper connection for discoverer
            db_conn = self._create_discoverer_connection()
            self._discoverer = DatabaseCapabilityDiscoverer(
                db_connection=db_conn,
                database_type=self.database_type.value,
                include_views=True,
                include_procedures=False,
                table_filter=self.allowed_tables,
                cache_enabled=self.config.cache_capabilities,
                cache_ttl_seconds=self.config.capability_cache_ttl_seconds,
            )

        # Discover capabilities
        result = await self._discoverer.get_capabilities()

        # Store capability metadata
        self._capability_metadata = result.capability_metadata

        return result.capabilities

    def _create_discoverer_connection(self):
        """
        Create a connection wrapper for the discoverer.

        Returns:
            Connection wrapper with fetch() method
        """

        class ConnectionWrapper:
            def __init__(self, esa):
                self.esa = esa

            async def fetch(self, query: str):
                if self.esa.database_type == DatabaseType.POSTGRESQL:
                    async with self.esa._pool.acquire() as conn:
                        return await conn.fetch(query)
                elif self.esa.database_type == DatabaseType.MYSQL:
                    async with self.esa._pool.acquire() as conn:
                        async with conn.cursor() as cursor:
                            await cursor.execute(query)
                            rows = await cursor.fetchall()
                            # Convert to dict-like rows
                            return [dict(zip([d[0] for d in cursor.description], row)) for row in rows]
                elif self.esa.database_type == DatabaseType.SQLITE:
                    cursor = await self.esa._connection.execute(query)
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]

        return ConnectionWrapper(self)

    async def execute_operation(
        self,
        operation: str,
        parameters: Dict[str, Any],
    ) -> Any:
        """
        Execute database operation.

        Args:
            operation: Operation to execute (e.g., "read_users", "insert_orders")
            parameters: Operation parameters

        Returns:
            Operation result (list of rows, affected count, etc.)

        Raises:
            ESAOperationError: If operation fails
        """

        # Parse operation — validate table name to prevent SQL injection
        def _validate_table_name(name: str) -> str:
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
                raise ESAOperationError(
                    f"Invalid table name: {name!r}. Table names must be alphanumeric with underscores."
                )
            return name

        if operation.startswith("read_"):
            table = _validate_table_name(operation[5:])
            return await self.execute_query(
                query=f"SELECT * FROM {table}",
                parameters=parameters,
            )
        elif operation.startswith("insert_"):
            table = _validate_table_name(operation[7:])
            return await self.execute_insert(
                table=table,
                data=parameters.get("data", {}),
            )
        elif operation.startswith("update_"):
            table = _validate_table_name(operation[7:])
            return await self.execute_update(
                table=table,
                conditions=parameters.get("conditions", {}),
                data=parameters.get("data", {}),
            )
        elif operation.startswith("delete_"):
            table = _validate_table_name(operation[7:])
            return await self.execute_delete(
                table=table,
                conditions=parameters.get("conditions", {}),
            )
        else:
            raise ESAOperationError(
                operation=operation,
                system_id=self.system_id,
                reason=f"Unsupported operation type: {operation}",
            )

    # =========================================================================
    # Database Operations
    # =========================================================================

    async def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute a SELECT query.

        Args:
            query: SQL query to execute
            parameters: Query parameters (for filtering, pagination)

        Returns:
            List of result rows as dictionaries

        Raises:
            ESAOperationError: If query execution fails
        """
        parameters = parameters or {}

        try:
            # Parse query to extract tables and validate
            parse_result = self._parse_query(query)
            if not parse_result.is_safe:
                raise ESAOperationError(
                    operation="execute_query",
                    system_id=self.system_id,
                    reason=f"Query validation failed: {', '.join(parse_result.violations)}",
                )

            # Apply limit constraint
            limit = parameters.get("limit", 1000)
            limit = min(limit, self.max_row_limit)

            # Apply offset for pagination
            offset = parameters.get("offset", 0)

            # Add WHERE clause from filters
            filters = parameters.get("filters", {})
            where_clause, filter_values = self._build_where_clause(filters)

            # Modify query to include limit/offset
            if "LIMIT" not in query.upper():
                query = f"{query} {where_clause} LIMIT {limit} OFFSET {offset}"

            # Execute query with parameterized values
            if self.database_type == DatabaseType.POSTGRESQL:
                # Convert %s placeholders to $N for asyncpg
                pg_query = query
                for i in range(len(filter_values)):
                    pg_query = pg_query.replace("%s", f"${i + 1}", 1)
                async with self._pool.acquire() as conn:
                    rows = await conn.fetch(pg_query, *filter_values)
                    return [dict(row) for row in rows]

            elif self.database_type == DatabaseType.MYSQL:
                async with self._pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(query, filter_values or None)
                        rows = await cursor.fetchall()
                        columns = [d[0] for d in cursor.description]
                        return [dict(zip(columns, row)) for row in rows]

            elif self.database_type == DatabaseType.SQLITE:
                # Convert %s placeholders to ? for sqlite
                sqlite_query = query.replace("%s", "?")
                cursor = await self._connection.execute(sqlite_query, filter_values)
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

        except Exception as e:
            raise ESAOperationError(
                operation="execute_query",
                system_id=self.system_id,
                reason=str(e),
                original_error=e,
            )

    async def execute_insert(
        self,
        table: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute an INSERT operation.

        Args:
            table: Table name
            data: Data to insert (column: value pairs)

        Returns:
            Dictionary with 'affected_rows' and 'last_insert_id'

        Raises:
            ESAOperationError: If insert fails
        """
        try:
            # Validate table is allowed
            if self.allowed_tables and table not in self.allowed_tables:
                raise ESAOperationError(
                    operation="execute_insert",
                    system_id=self.system_id,
                    reason=f"Table '{table}' not in allowed tables list",
                )

            # Build INSERT query — validate column names
            _ident_re = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
            columns = list(data.keys())
            for col in columns:
                if not _ident_re.match(col):
                    raise ESAOperationError(
                        operation="execute_insert",
                        system_id=self.system_id,
                        reason=f"Invalid column name: {col!r}",
                    )
            placeholders = self._get_placeholders(len(columns))
            query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
            values = list(data.values())

            # Execute insert
            if self.database_type == DatabaseType.POSTGRESQL:
                async with self._pool.acquire() as conn:
                    result = await conn.execute(query, *values)
                    # Parse result: "INSERT 0 1" -> 1 row affected
                    affected = int(result.split()[-1])
                    return {"affected_rows": affected, "last_insert_id": None}

            elif self.database_type == DatabaseType.MYSQL:
                async with self._pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(query, values)
                        await conn.commit()
                        return {
                            "affected_rows": cursor.rowcount,
                            "last_insert_id": cursor.lastrowid,
                        }

            elif self.database_type == DatabaseType.SQLITE:
                cursor = await self._connection.execute(query, values)
                await self._connection.commit()
                return {
                    "affected_rows": cursor.rowcount,
                    "last_insert_id": cursor.lastrowid,
                }

        except Exception as e:
            raise ESAOperationError(
                operation="execute_insert",
                system_id=self.system_id,
                reason=str(e),
                original_error=e,
            )

    async def execute_update(
        self,
        table: str,
        conditions: Dict[str, Any],
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute an UPDATE operation.

        Args:
            table: Table name
            conditions: WHERE conditions (column: value pairs)
            data: Data to update (column: value pairs)

        Returns:
            Dictionary with 'affected_rows'

        Raises:
            ESAOperationError: If update fails
        """
        try:
            # Validate table is allowed
            if self.allowed_tables and table not in self.allowed_tables:
                raise ESAOperationError(
                    operation="execute_update",
                    system_id=self.system_id,
                    reason=f"Table '{table}' not in allowed tables list",
                )

            # Validate column names against injection
            _ident_re = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
            for col in list(data.keys()) + list(conditions.keys()):
                if not _ident_re.match(col):
                    raise ESAOperationError(
                        operation="execute_update",
                        system_id=self.system_id,
                        reason=f"Invalid column name: {col!r}",
                    )

            # Build UPDATE query
            set_clause = ", ".join([f"{col} = %s" for col in data.keys()])
            where_clause = self._build_where_clause(conditions)
            query = f"UPDATE {table} SET {set_clause} {where_clause}"
            values = list(data.values()) + list(conditions.values())

            # Execute update
            if self.database_type == DatabaseType.POSTGRESQL:
                # Use $1, $2 for asyncpg
                set_clause = ", ".join([f"{col} = ${i + 1}" for i, col in enumerate(data.keys())])
                where_conditions = " AND ".join(
                    [f"{col} = ${i + len(data) + 1}" for i, col in enumerate(conditions.keys())]
                )
                query = f"UPDATE {table} SET {set_clause} WHERE {where_conditions}"
                async with self._pool.acquire() as conn:
                    result = await conn.execute(query, *values)
                    affected = int(result.split()[-1])
                    return {"affected_rows": affected}

            elif self.database_type == DatabaseType.MYSQL:
                async with self._pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(query, values)
                        await conn.commit()
                        return {"affected_rows": cursor.rowcount}

            elif self.database_type == DatabaseType.SQLITE:
                cursor = await self._connection.execute(query, values)
                await self._connection.commit()
                return {"affected_rows": cursor.rowcount}

        except Exception as e:
            raise ESAOperationError(
                operation="execute_update",
                system_id=self.system_id,
                reason=str(e),
                original_error=e,
            )

    async def execute_delete(
        self,
        table: str,
        conditions: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute a DELETE operation.

        Args:
            table: Table name
            conditions: WHERE conditions (column: value pairs)

        Returns:
            Dictionary with 'affected_rows'

        Raises:
            ESAOperationError: If delete fails
        """
        try:
            # Validate table is allowed
            if self.allowed_tables and table not in self.allowed_tables:
                raise ESAOperationError(
                    operation="execute_delete",
                    system_id=self.system_id,
                    reason=f"Table '{table}' not in allowed tables list",
                )

            # Validate column names against injection
            _ident_re = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
            for col in conditions.keys():
                if not _ident_re.match(col):
                    raise ESAOperationError(
                        operation="execute_delete",
                        system_id=self.system_id,
                        reason=f"Invalid column name: {col!r}",
                    )

            # Build DELETE query
            where_clause = self._build_where_clause(conditions)
            query = f"DELETE FROM {table} {where_clause}"
            values = list(conditions.values())

            # Execute delete
            if self.database_type == DatabaseType.POSTGRESQL:
                where_conditions = " AND ".join([f"{col} = ${i + 1}" for i, col in enumerate(conditions.keys())])
                query = f"DELETE FROM {table} WHERE {where_conditions}"
                async with self._pool.acquire() as conn:
                    result = await conn.execute(query, *values)
                    affected = int(result.split()[-1])
                    return {"affected_rows": affected}

            elif self.database_type == DatabaseType.MYSQL:
                async with self._pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(query, values)
                        await conn.commit()
                        return {"affected_rows": cursor.rowcount}

            elif self.database_type == DatabaseType.SQLITE:
                cursor = await self._connection.execute(query, values)
                await self._connection.commit()
                return {"affected_rows": cursor.rowcount}

        except Exception as e:
            raise ESAOperationError(
                operation="execute_delete",
                system_id=self.system_id,
                reason=str(e),
                original_error=e,
            )

    # =========================================================================
    # Query Parsing and Validation
    # =========================================================================

    def _parse_query(self, query: str) -> QueryParseResult:
        """
        Parse and validate a SQL query.

        Args:
            query: SQL query to parse

        Returns:
            QueryParseResult with parse information
        """
        query_upper = query.upper().strip()
        violations = []

        # Determine query type
        if query_upper.startswith("SELECT"):
            query_type = "SELECT"
            operations = ["read"]
        elif query_upper.startswith("INSERT"):
            query_type = "INSERT"
            operations = ["write"]
        elif query_upper.startswith("UPDATE"):
            query_type = "UPDATE"
            operations = ["update"]
        elif query_upper.startswith("DELETE"):
            query_type = "DELETE"
            operations = ["delete"]
        else:
            return QueryParseResult(
                query_type="UNKNOWN",
                tables=[],
                operations=[],
                is_safe=False,
                violations=["Unsupported query type"],
            )

        # Extract tables (simple regex-based extraction)
        tables = self._extract_tables_from_query(query)

        # Validate tables against allowed list
        if self.allowed_tables:
            for table in tables:
                if table not in self.allowed_tables:
                    violations.append(f"Table '{table}' not in allowed tables list")

        # Check for dangerous patterns
        dangerous_patterns = [
            r"DROP\s+TABLE",
            r"DROP\s+DATABASE",
            r"TRUNCATE",
            r"ALTER\s+TABLE",
            r"CREATE\s+TABLE",
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, query_upper):
                violations.append(f"Dangerous SQL pattern detected: {pattern}")

        return QueryParseResult(
            query_type=query_type,
            tables=tables,
            operations=operations,
            is_safe=len(violations) == 0,
            violations=violations,
        )

    def _extract_tables_from_query(self, query: str) -> List[str]:
        """
        Extract table names from SQL query.

        Args:
            query: SQL query

        Returns:
            List of table names
        """
        # Simple regex to extract tables (not perfect, but good enough)
        patterns = [
            r"FROM\s+([a-zA-Z0-9_]+)",
            r"JOIN\s+([a-zA-Z0-9_]+)",
            r"INTO\s+([a-zA-Z0-9_]+)",
            r"UPDATE\s+([a-zA-Z0-9_]+)",
        ]

        tables = set()
        for pattern in patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            tables.update(matches)

        return list(tables)

    def _build_where_clause(self, conditions: Dict[str, Any]) -> Tuple[str, List[Any]]:
        """
        Build WHERE clause from conditions dictionary.

        Args:
            conditions: Column: value pairs

        Returns:
            Tuple of (WHERE clause string, list of parameter values)

        Raises:
            ESAOperationError: If column names contain invalid characters
        """
        if not conditions:
            return "", []

        _ident_re = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
        for col in conditions.keys():
            if not _ident_re.match(col):
                raise ESAOperationError(
                    operation="execute_query",
                    system_id=self.system_id,
                    reason=f"Invalid column name in filter: '{col}'",
                )

        where_parts = [f"{col} = %s" for col in conditions.keys()]
        return "WHERE " + " AND ".join(where_parts), list(conditions.values())

    def _get_placeholders(self, count: int) -> str:
        """
        Get placeholder string for SQL query.

        Args:
            count: Number of placeholders

        Returns:
            Placeholder string (e.g., "%s, %s, %s" or "$1, $2, $3")
        """
        if self.database_type == DatabaseType.POSTGRESQL:
            return ", ".join([f"${i + 1}" for i in range(count)])
        else:
            return ", ".join(["%s"] * count)

    # =========================================================================
    # Cleanup
    # =========================================================================

    async def __aenter__(self):
        """Async context manager entry."""
        await self._initialize_connection()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._close_connection()
