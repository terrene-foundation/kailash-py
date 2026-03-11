# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Capability Discovery for Enterprise System Agents.

Provides abstract base classes and concrete implementations for discovering
capabilities from various enterprise systems, including databases and APIs.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from eatp.chain import CapabilityType
from eatp.esa.base import CapabilityMetadata


class DiscoveryStatus(Enum):
    """Status of capability discovery operation."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class DiscoveryResult:
    """
    Result of a capability discovery operation.

    Attributes:
        capabilities: List of discovered capability names
        capability_metadata: Detailed metadata for each capability
        status: Discovery status
        error: Error message if discovery failed
        discovered_at: When discovery occurred
        discovery_duration_ms: Time taken for discovery
        cache_ttl_seconds: Recommended cache TTL
        metadata: Additional discovery context
    """

    capabilities: List[str]
    capability_metadata: Dict[str, CapabilityMetadata]
    status: DiscoveryStatus = DiscoveryStatus.SUCCESS
    error: Optional[str] = None
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    discovery_duration_ms: Optional[int] = None
    cache_ttl_seconds: int = 3600  # 1 hour default
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveryCache:
    """
    Cache for discovered capabilities.

    Attributes:
        capabilities: Cached capabilities
        cached_at: When cached
        expires_at: When cache expires
        metadata: Cache metadata (e.g., cache hits)
    """

    capabilities: List[str]
    capability_metadata: Dict[str, CapabilityMetadata]
    cached_at: datetime
    expires_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_valid(self) -> bool:
        """Check if cache is still valid."""
        return datetime.now(timezone.utc) < self.expires_at

    def remaining_ttl_seconds(self) -> int:
        """Get remaining cache TTL in seconds."""
        if not self.is_valid():
            return 0
        delta = self.expires_at - datetime.now(timezone.utc)
        return max(0, int(delta.total_seconds()))


class CapabilityDiscoverer(ABC):
    """
    Abstract base class for capability discoverers.

    Subclasses implement system-specific discovery logic for databases,
    REST APIs, SOAP services, etc.

    Example:
        class MyDiscoverer(CapabilityDiscoverer):
            async def discover_capabilities(self) -> DiscoveryResult:
                # Introspect system
                capabilities = ["read_users", "write_orders"]
                metadata = {
                    "read_users": CapabilityMetadata(
                        capability="read_users",
                        description="Read user records",
                        capability_type=CapabilityType.ACCESS,
                    )
                }
                return DiscoveryResult(
                    capabilities=capabilities,
                    capability_metadata=metadata,
                )
    """

    def __init__(
        self,
        cache_enabled: bool = True,
        cache_ttl_seconds: int = 3600,
    ):
        """
        Initialize capability discoverer.

        Args:
            cache_enabled: Whether to cache discovery results
            cache_ttl_seconds: Cache time-to-live in seconds
        """
        self.cache_enabled = cache_enabled
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: Optional[DiscoveryCache] = None

    @abstractmethod
    async def discover_capabilities(self) -> DiscoveryResult:
        """
        Discover capabilities from the underlying system.

        This method should introspect the system and return all available
        capabilities with their metadata.

        Returns:
            DiscoveryResult with capabilities and metadata

        Raises:
            ESAConnectionError: If system connection fails
            ESAOperationError: If discovery fails
        """
        pass

    async def get_capabilities(
        self,
        force_refresh: bool = False,
    ) -> DiscoveryResult:
        """
        Get capabilities, using cache if available.

        Args:
            force_refresh: Force cache refresh even if valid

        Returns:
            DiscoveryResult with capabilities
        """
        # Check cache
        if self.cache_enabled and not force_refresh and self._cache:
            if self._cache.is_valid():
                return DiscoveryResult(
                    capabilities=self._cache.capabilities,
                    capability_metadata=self._cache.capability_metadata,
                    status=DiscoveryStatus.SUCCESS,
                    discovered_at=self._cache.cached_at,
                    cache_ttl_seconds=self._cache.remaining_ttl_seconds(),
                    metadata={
                        "cached": True,
                        "cache_age_seconds": int(
                            (
                                datetime.now(timezone.utc) - self._cache.cached_at
                            ).total_seconds()
                        ),
                    },
                )

        # Perform discovery
        start_time = datetime.now(timezone.utc)
        result = await self.discover_capabilities()
        duration_ms = int(
            (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        )
        result.discovery_duration_ms = duration_ms

        # Update cache
        if self.cache_enabled and result.status == DiscoveryStatus.SUCCESS:
            self._cache = DiscoveryCache(
                capabilities=result.capabilities,
                capability_metadata=result.capability_metadata,
                cached_at=result.discovered_at,
                expires_at=result.discovered_at
                + timedelta(seconds=self.cache_ttl_seconds),
            )

        return result

    def clear_cache(self) -> None:
        """Clear the capability cache."""
        self._cache = None


class DatabaseCapabilityDiscoverer(CapabilityDiscoverer):
    """
    Discovers capabilities from database schemas.

    Introspects database metadata to discover:
    - Tables (read, insert, update, delete operations)
    - Views (read operations only)
    - Stored procedures/functions (execute operations)

    Example:
        discoverer = DatabaseCapabilityDiscoverer(
            db_connection=my_db,
            database_type=DatabaseType.POSTGRESQL,
        )
        result = await discoverer.discover_capabilities()
        print(result.capabilities)  # ["read_users", "write_orders", ...]
    """

    def __init__(
        self,
        db_connection: Any,
        database_type: str,
        include_views: bool = True,
        include_procedures: bool = False,
        table_filter: Optional[List[str]] = None,
        cache_enabled: bool = True,
        cache_ttl_seconds: int = 3600,
    ):
        """
        Initialize database capability discoverer.

        Args:
            db_connection: Database connection object
            database_type: Type of database (postgresql, mysql, sqlite)
            include_views: Include views in discovery
            include_procedures: Include stored procedures
            table_filter: Optional whitelist of table names
            cache_enabled: Whether to cache results
            cache_ttl_seconds: Cache TTL
        """
        super().__init__(cache_enabled, cache_ttl_seconds)
        self.db_connection = db_connection
        self.database_type = database_type.lower()
        self.include_views = include_views
        self.include_procedures = include_procedures
        self.table_filter = table_filter

    async def discover_capabilities(self) -> DiscoveryResult:
        """
        Discover capabilities from database schema.

        Returns:
            DiscoveryResult with discovered capabilities
        """
        try:
            capabilities = []
            capability_metadata = {}

            # Discover tables
            tables = await self._discover_tables()
            for table in tables:
                # Apply filter if specified
                if self.table_filter and table not in self.table_filter:
                    continue

                # Read capability
                read_cap = f"read_{table}"
                capabilities.append(read_cap)
                capability_metadata[read_cap] = CapabilityMetadata(
                    capability=read_cap,
                    description=f"Read records from {table} table",
                    capability_type=CapabilityType.ACCESS,
                    parameters={
                        "limit": {
                            "type": "integer",
                            "description": "Maximum rows to return",
                        },
                        "offset": {
                            "type": "integer",
                            "description": "Offset for pagination",
                        },
                        "filters": {
                            "type": "dict",
                            "description": "WHERE clause filters",
                        },
                    },
                    constraints=["read_only"],
                )

                # Insert capability
                insert_cap = f"insert_{table}"
                capabilities.append(insert_cap)
                capability_metadata[insert_cap] = CapabilityMetadata(
                    capability=insert_cap,
                    description=f"Insert records into {table} table",
                    capability_type=CapabilityType.ACTION,
                    parameters={
                        "data": {
                            "type": "dict",
                            "description": "Record data to insert",
                        },
                    },
                    constraints=["audit_required"],
                )

                # Update capability
                update_cap = f"update_{table}"
                capabilities.append(update_cap)
                capability_metadata[update_cap] = CapabilityMetadata(
                    capability=update_cap,
                    description=f"Update records in {table} table",
                    capability_type=CapabilityType.ACTION,
                    parameters={
                        "data": {"type": "dict", "description": "Data to update"},
                        "conditions": {
                            "type": "dict",
                            "description": "WHERE conditions",
                        },
                    },
                    constraints=["audit_required"],
                )

                # Delete capability
                delete_cap = f"delete_{table}"
                capabilities.append(delete_cap)
                capability_metadata[delete_cap] = CapabilityMetadata(
                    capability=delete_cap,
                    description=f"Delete records from {table} table",
                    capability_type=CapabilityType.ACTION,
                    parameters={
                        "conditions": {
                            "type": "dict",
                            "description": "WHERE conditions",
                        },
                    },
                    constraints=["audit_required", "soft_delete_preferred"],
                )

            # Discover views
            if self.include_views:
                views = await self._discover_views()
                for view in views:
                    read_cap = f"read_{view}"
                    capabilities.append(read_cap)
                    capability_metadata[read_cap] = CapabilityMetadata(
                        capability=read_cap,
                        description=f"Read from {view} view",
                        capability_type=CapabilityType.ACCESS,
                        parameters={
                            "limit": {"type": "integer", "description": "Maximum rows"},
                            "filters": {"type": "dict", "description": "Filters"},
                        },
                        constraints=["read_only", "view_access"],
                    )

            # Discover procedures
            if self.include_procedures:
                procedures = await self._discover_procedures()
                for proc in procedures:
                    exec_cap = f"execute_{proc}"
                    capabilities.append(exec_cap)
                    capability_metadata[exec_cap] = CapabilityMetadata(
                        capability=exec_cap,
                        description=f"Execute {proc} stored procedure",
                        capability_type=CapabilityType.ACTION,
                        parameters={
                            "parameters": {
                                "type": "dict",
                                "description": "Procedure parameters",
                            },
                        },
                        constraints=["audit_required", "procedure_execution"],
                    )

            return DiscoveryResult(
                capabilities=capabilities,
                capability_metadata=capability_metadata,
                status=DiscoveryStatus.SUCCESS,
                metadata={
                    "database_type": self.database_type,
                    "tables_count": len(tables),
                    "views_count": (
                        len(await self._discover_views()) if self.include_views else 0
                    ),
                    "procedures_count": (
                        len(await self._discover_procedures())
                        if self.include_procedures
                        else 0
                    ),
                },
            )

        except Exception as e:
            return DiscoveryResult(
                capabilities=[],
                capability_metadata={},
                status=DiscoveryStatus.FAILED,
                error=str(e),
            )

    async def _discover_tables(self) -> List[str]:
        """
        Discover tables from database.

        Returns:
            List of table names
        """
        if self.database_type == "postgresql":
            return await self._discover_postgres_tables()
        elif self.database_type == "mysql":
            return await self._discover_mysql_tables()
        elif self.database_type == "sqlite":
            return await self._discover_sqlite_tables()
        else:
            raise ValueError(f"Unsupported database type: {self.database_type}")

    async def _discover_postgres_tables(self) -> List[str]:
        """Discover PostgreSQL tables."""
        query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """
        rows = await self.db_connection.fetch(query)
        return [row["table_name"] for row in rows]

    async def _discover_mysql_tables(self) -> List[str]:
        """Discover MySQL tables."""
        query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """
        rows = await self.db_connection.fetch(query)
        return [row["table_name"] for row in rows]

    async def _discover_sqlite_tables(self) -> List[str]:
        """Discover SQLite tables."""
        query = """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """
        rows = await self.db_connection.fetch(query)
        return [row["name"] for row in rows]

    async def _discover_views(self) -> List[str]:
        """
        Discover views from database.

        Returns:
            List of view names
        """
        if self.database_type == "postgresql":
            query = """
                SELECT table_name
                FROM information_schema.views
                WHERE table_schema = 'public'
                ORDER BY table_name
            """
        elif self.database_type == "mysql":
            query = """
                SELECT table_name
                FROM information_schema.views
                WHERE table_schema = DATABASE()
                ORDER BY table_name
            """
        elif self.database_type == "sqlite":
            query = """
                SELECT name
                FROM sqlite_master
                WHERE type = 'view'
                ORDER BY name
            """
        else:
            return []

        rows = await self.db_connection.fetch(query)
        return [
            (
                row[0]
                if isinstance(row, tuple)
                else row["table_name"] if "table_name" in row else row["name"]
            )
            for row in rows
        ]

    async def _discover_procedures(self) -> List[str]:
        """
        Discover stored procedures from database.

        Returns:
            List of procedure names
        """
        if self.database_type == "postgresql":
            query = """
                SELECT routine_name
                FROM information_schema.routines
                WHERE routine_schema = 'public'
                AND routine_type = 'FUNCTION'
                ORDER BY routine_name
            """
        elif self.database_type == "mysql":
            query = """
                SELECT routine_name
                FROM information_schema.routines
                WHERE routine_schema = DATABASE()
                AND routine_type = 'PROCEDURE'
                ORDER BY routine_name
            """
        elif self.database_type == "sqlite":
            # SQLite doesn't have stored procedures
            return []
        else:
            return []

        try:
            rows = await self.db_connection.fetch(query)
            return [
                row[0] if isinstance(row, tuple) else row["routine_name"]
                for row in rows
            ]
        except Exception:
            return []


class APICapabilityDiscoverer(CapabilityDiscoverer):
    """
    Discovers capabilities from REST API specifications.

    Parses OpenAPI/Swagger specifications to discover available endpoints
    and operations.

    Example:
        discoverer = APICapabilityDiscoverer(
            openapi_spec=my_spec,
        )
        result = await discoverer.discover_capabilities()
    """

    def __init__(
        self,
        openapi_spec: Dict[str, Any],
        base_url: Optional[str] = None,
        cache_enabled: bool = True,
        cache_ttl_seconds: int = 3600,
    ):
        """
        Initialize API capability discoverer.

        Args:
            openapi_spec: OpenAPI/Swagger specification
            base_url: Optional base URL for API
            cache_enabled: Whether to cache results
            cache_ttl_seconds: Cache TTL
        """
        super().__init__(cache_enabled, cache_ttl_seconds)
        self.openapi_spec = openapi_spec
        self.base_url = base_url

    async def discover_capabilities(self) -> DiscoveryResult:
        """
        Discover capabilities from OpenAPI specification.

        Returns:
            DiscoveryResult with discovered capabilities
        """
        try:
            capabilities = []
            capability_metadata = {}

            paths = self.openapi_spec.get("paths", {})
            for path, operations in paths.items():
                for method, operation_spec in operations.items():
                    if method.lower() not in ["get", "post", "put", "patch", "delete"]:
                        continue

                    # Create capability name
                    operation_id = operation_spec.get(
                        "operationId", f"{method}_{path.replace('/', '_')}"
                    )
                    capability = operation_id

                    # Determine capability type
                    cap_type = (
                        CapabilityType.ACCESS
                        if method.lower() == "get"
                        else CapabilityType.ACTION
                    )

                    # Extract parameters
                    parameters = {}
                    for param in operation_spec.get("parameters", []):
                        param_name = param.get("name")
                        param_schema = param.get("schema", {})
                        parameters[param_name] = {
                            "type": param_schema.get("type", "string"),
                            "description": param.get("description", ""),
                            "required": param.get("required", False),
                        }

                    # Determine constraints
                    constraints = []
                    if method.lower() == "get":
                        constraints.append("read_only")
                    else:
                        constraints.append("audit_required")

                    capabilities.append(capability)
                    capability_metadata[capability] = CapabilityMetadata(
                        capability=capability,
                        description=operation_spec.get(
                            "summary", f"{method.upper()} {path}"
                        ),
                        capability_type=cap_type,
                        parameters=parameters,
                        constraints=constraints,
                        examples=[
                            {
                                "method": method.upper(),
                                "path": path,
                                "description": operation_spec.get("description", ""),
                            }
                        ],
                    )

            return DiscoveryResult(
                capabilities=capabilities,
                capability_metadata=capability_metadata,
                status=DiscoveryStatus.SUCCESS,
                metadata={
                    "base_url": self.base_url,
                    "openapi_version": self.openapi_spec.get("openapi", "unknown"),
                    "endpoints_count": len(paths),
                },
            )

        except Exception as e:
            return DiscoveryResult(
                capabilities=[],
                capability_metadata={},
                status=DiscoveryStatus.FAILED,
                error=str(e),
            )
