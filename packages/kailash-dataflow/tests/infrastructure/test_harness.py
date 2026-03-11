#!/usr/bin/env python3
"""
DataFlow Integration Test Harness

Provides comprehensive infrastructure abstractions and utilities for DataFlow
integration tests, eliminating hardcoded database configurations and patterns.

This module follows the NO MOCKING policy for integration tests and provides
centralized database configuration management.
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import asyncpg
from dataflow import DataFlow

logger = logging.getLogger(__name__)


@dataclass
class DatabaseConfig:
    """Centralized database configuration for integration tests."""

    url: str
    type: str
    host: str = "localhost"
    port: int = 5434
    user: str = "test_user"
    password: str = "test_password"
    database: str = "kailash_test"

    @classmethod
    def from_environment(cls) -> "DatabaseConfig":
        """Create configuration from environment variables."""
        if os.getenv("TEST_DATABASE_URL"):
            return cls(url=os.getenv("TEST_DATABASE_URL"), type="custom")

        # Standard SDK Docker infrastructure (port 5434)
        host = os.getenv("DB_HOST", "localhost")
        port = int(os.getenv("DB_PORT", "5434"))
        user = os.getenv("DB_USER", "test_user")
        password = os.getenv("DB_PASSWORD", "test_password")
        database = os.getenv("DB_NAME", "kailash_test")

        url = f"postgresql://{user}:{password}@{host}:{port}/{database}"

        return cls(
            url=url,
            type="postgresql",
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
        )


class DatabaseInfrastructure:
    """Manages database infrastructure for integration tests."""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._pool: Optional[asyncpg.Pool] = None
        self._verified = False

    async def initialize(self):
        """Initialize and verify database infrastructure."""
        if self._verified:
            return

        # Test connection first
        try:
            test_conn = await asyncpg.connect(self.config.url)
            await test_conn.fetchval("SELECT 1")
            await test_conn.close()
            logger.info(
                f"✅ Database connection verified: {self.config.type} on port {self.config.port}"
            )
        except Exception as e:
            raise ConnectionError(
                f"Cannot connect to test database: {e}. Ensure PostgreSQL is running on port {self.config.port}"
            )

        # Create connection pool with very conservative settings
        # to avoid exhausting PostgreSQL connections during test runs
        self._pool = await asyncpg.create_pool(
            self.config.url,
            min_size=1,  # Further reduced
            max_size=5,  # Further reduced for test isolation
            command_timeout=30,
            max_inactive_connection_lifetime=3.0,  # Close idle connections after 3 seconds
        )

        self._verified = True
        logger.info(
            f"✅ Connection pool created with {self._pool._minsize}-{self._pool._maxsize} connections"
        )

    async def get_connection(self) -> asyncpg.Connection:
        """Get a connection from the pool."""
        if not self._pool:
            await self.initialize()
        return await self._pool.acquire()

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """Context manager for database connections."""
        if not self._pool:
            await self.initialize()
        async with self._pool.acquire() as conn:
            yield conn

    async def cleanup(self):
        """Clean up database infrastructure."""
        if self._pool:
            await self._pool.close()
            self._pool = None
        logger.info("✅ Database infrastructure cleaned up")


class TestTableFactory:
    """Factory for creating standardized test tables."""

    def __init__(self, infrastructure: DatabaseInfrastructure):
        self.infrastructure = infrastructure
        self._created_tables: List[str] = []

    def generate_unique_name(self, prefix: str = "test") -> str:
        """Generate unique table name for test isolation."""
        return f"{prefix}_{int(time.time() * 1000000)}"

    async def create_basic_table(self, name: Optional[str] = None) -> str:
        """Create basic test table with standard schema."""
        table_name = name or self.generate_unique_name("basic_test")

        async with self.infrastructure.connection() as conn:
            await conn.execute(
                f"""
                CREATE TABLE {table_name} (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    email VARCHAR(255) UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Insert standard test data
            await conn.execute(
                f"""
                INSERT INTO {table_name} (name, email) VALUES
                ('Alice', 'alice@example.com'),
                ('Bob', 'bob@example.com'),
                ('Charlie', 'charlie@example.com')
            """
            )

        self._created_tables.append(table_name)
        return table_name

    async def create_constrained_table(self) -> Dict[str, str]:
        """Create test table with various constraint types."""
        main_table = self.generate_unique_name("constrained_test")
        category_table = self.generate_unique_name("categories")

        async with self.infrastructure.connection() as conn:
            # Create category table first
            await conn.execute(
                f"""
                CREATE TABLE {category_table} (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(50) NOT NULL UNIQUE,
                    active BOOLEAN DEFAULT true
                )
            """
            )

            # Insert categories
            await conn.execute(
                f"""
                INSERT INTO {category_table} (name) VALUES ('general'), ('premium'), ('vip')
            """
            )

            # Create main table with constraints
            await conn.execute(
                f"""
                CREATE TABLE {main_table} (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    email VARCHAR(255) UNIQUE,
                    age INTEGER CHECK (age >= 0 AND age <= 150),
                    category_id INTEGER REFERENCES {category_table}(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Insert test data with category references
            await conn.execute(
                f"""
                INSERT INTO {main_table} (name, email, age, category_id) VALUES
                ('Alice', 'alice@example.com', 25, 1),
                ('Bob', 'bob@example.com', 30, 2),
                ('Charlie', 'charlie@example.com', 35, 1)
            """
            )

        self._created_tables.extend([category_table, main_table])
        return {"main_table": main_table, "category_table": category_table}

    async def create_large_table(self, rows: int = 10000) -> str:
        """Create large test table for performance testing."""
        table_name = self.generate_unique_name("large_test")

        async with self.infrastructure.connection() as conn:
            await conn.execute(
                f"""
                CREATE TABLE {table_name} (
                    id SERIAL PRIMARY KEY,
                    data VARCHAR(100),
                    value INTEGER
                )
            """
            )

            # Insert test data in batches for performance
            batch_size = 1000
            for batch_start in range(0, rows, batch_size):
                batch_end = min(batch_start + batch_size, rows)
                values = ", ".join(
                    [f"('data_{i}', {i % 100})" for i in range(batch_start, batch_end)]
                )
                await conn.execute(
                    f"INSERT INTO {table_name} (data, value) VALUES {values}"
                )

        self._created_tables.append(table_name)
        logger.info(f"✅ Created large test table '{table_name}' with {rows} rows")
        return table_name

    async def cleanup_all(self):
        """Clean up all created tables."""
        if not self._created_tables:
            return

        async with self.infrastructure.connection() as conn:
            # Drop tables in reverse order (handles foreign key dependencies)
            for table_name in reversed(self._created_tables):
                try:
                    await conn.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
                except Exception as e:
                    logger.warning(f"Failed to drop table {table_name}: {e}")

        table_count = len(self._created_tables)
        self._created_tables.clear()
        logger.info(f"✅ Cleaned up {table_count} test tables")


class NotNullTestHarness:
    """Specialized test harness for NOT NULL column addition functionality."""

    def __init__(self, infrastructure: DatabaseInfrastructure):
        self.infrastructure = infrastructure
        self.table_factory = TestTableFactory(infrastructure)
        # self._handlers: List[NotNullColumnHandler] = []  # Disabled - module not available

    def create_connection_manager(self) -> "StandardConnectionManager":
        """Create standardized connection manager for NOT NULL handler."""
        return StandardConnectionManager(self.infrastructure.config.url)

    # def create_handler(self) -> NotNullColumnHandler:
    #     """Create NOT NULL column handler with proper connection management."""
    #     manager = self.create_connection_manager()
    #     handler = NotNullColumnHandler(manager)
    #     self._handlers.append(handler)
    #     return handler

    # def create_strategy_manager(self) -> DefaultValueStrategyManager:
    #     """Create default value strategy manager."""
    #     return DefaultValueStrategyManager()

    # def create_constraint_validator(self) -> ConstraintValidator:
    #     """Create constraint validator with proper connection management."""
    #     manager = self.create_connection_manager()
    #     return ConstraintValidator(manager)

    # # Standard column definitions for consistent testing
    # @staticmethod
    # def static_column(name: str = "test_col", value: Any = "test_value") -> ColumnDefinition:
    #     """Create standard static default column definition."""
    #     return ColumnDefinition(
    #         name=name,
    #         data_type="VARCHAR(100)",
    #         default_value=value,
    #         default_type=DefaultValueType.STATIC
    #     )

    # @staticmethod
    # def computed_column(name: str = "computed_col", expression: str = "CASE WHEN id > 2 THEN 'high' ELSE 'low' END") -> ColumnDefinition:
    #     """Create standard computed default column definition."""
    #     return ColumnDefinition(
    #         name=name,
    #         data_type="VARCHAR(20)",
    #         default_expression=expression,
    #         default_type=DefaultValueType.COMPUTED
    #     )

    # @staticmethod
    # def function_column(name: str = "timestamp_col", function: str = "CURRENT_TIMESTAMP") -> ColumnDefinition:
    #     """Create standard function default column definition."""
    #     return ColumnDefinition(
    #         name=name,
    #         data_type="TIMESTAMP",
    #         default_expression=function,
    #         default_type=DefaultValueType.FUNCTION
    # )

    async def cleanup(self):
        """Clean up all test resources."""
        # # Close handlers
        # for handler in self._handlers:
        #     if hasattr(handler, 'connection_manager'):
        #         await handler.connection_manager.close()
        # self._handlers.clear()

        # Clean up tables
        await self.table_factory.cleanup_all()
        logger.info("✅ NOT NULL test harness cleaned up")


class StandardConnectionManager:
    """Standardized connection manager compatible with NOT NULL handler."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._connection: Optional[asyncpg.Connection] = None

    async def get_connection(self) -> asyncpg.Connection:
        """Get database connection."""
        if self._connection is None or self._connection.is_closed():
            self._connection = await asyncpg.connect(self.database_url)
        return self._connection

    async def close(self):
        """Close database connection."""
        if self._connection and not self._connection.is_closed():
            await self._connection.close()


class DataFlowTestHarness:
    """Test harness for DataFlow integration testing."""

    def __init__(self, infrastructure: DatabaseInfrastructure):
        self.infrastructure = infrastructure
        self.table_factory = TestTableFactory(infrastructure)
        self._dataflow_instances = []  # Track DataFlow instances for cleanup

    def create_dataflow(self, **kwargs) -> DataFlow:
        """Create DataFlow instance with test database configuration."""
        config = {
            "auto_migrate": kwargs.get("auto_migrate", False),
            "existing_schema_mode": kwargs.get("existing_schema_mode", True),
            **kwargs,
        }
        dataflow = DataFlow(self.infrastructure.config.url, **config)
        self._dataflow_instances.append(dataflow)  # Track for cleanup
        return dataflow

    async def cleanup(self):
        """Clean up DataFlow test resources."""
        # Clean up DataFlow instances and their connection pools
        for dataflow in self._dataflow_instances:
            try:
                # Try to access the connection manager and close it
                if (
                    hasattr(dataflow, "_connection_manager")
                    and dataflow._connection_manager
                ):
                    if hasattr(dataflow._connection_manager, "close_all_pools"):
                        await dataflow._connection_manager.close_all_pools()
                    elif hasattr(dataflow._connection_manager, "cleanup"):
                        await dataflow._connection_manager.cleanup()
            except Exception as e:
                logger.warning(f"Error cleaning up DataFlow instance: {e}")

        self._dataflow_instances.clear()
        await self.table_factory.cleanup_all()
        logger.info("✅ DataFlow test harness cleaned up")


class IntegrationTestSuite:
    """Complete integration test suite with all harnesses."""

    def __init__(self, config: Optional[DatabaseConfig] = None):
        self.config = config or DatabaseConfig.from_environment()
        self.infrastructure = DatabaseInfrastructure(self.config)
        # self.not_null_harness = NotNullTestHarness(self.infrastructure)  # Disabled - modules not available
        self.dataflow_harness = DataFlowTestHarness(self.infrastructure)

    async def initialize(self):
        """Initialize the complete test suite."""
        await self.infrastructure.initialize()
        logger.info("🚀 Integration test suite initialized")

    async def cleanup(self):
        """Clean up the complete test suite."""
        # await self.not_null_harness.cleanup()  # Disabled - modules not available
        await self.dataflow_harness.cleanup()
        await self.infrastructure.cleanup()
        logger.info("✅ Integration test suite cleaned up")

    @asynccontextmanager
    async def session(self):
        """Context manager for test session lifecycle."""
        await self.initialize()
        try:
            yield self
        finally:
            await self.cleanup()

    def get_connection(self):
        """Get a database connection from the pool.

        Returns a context manager that yields an asyncpg connection.
        This delegates to the infrastructure's connection method.
        """
        return self.infrastructure.connection()


# Performance testing utilities


@dataclass
class PerformanceMetrics:
    """Standardized performance metrics collection."""

    operation: str
    duration: float
    rows_affected: int
    memory_peak: Optional[float] = None
    batch_size: Optional[int] = None

    @property
    def throughput(self) -> float:
        """Calculate throughput (rows/second)."""
        return self.rows_affected / self.duration if self.duration > 0 else 0.0


class PerformanceMeasurement:
    """Utilities for performance measurement in tests."""

    @staticmethod
    def assert_performance_bounds(
        actual_duration: float,
        max_expected: float,
        operation_name: str,
        row_count: int = 0,
    ):
        """Assert performance is within expected bounds."""
        assert actual_duration <= max_expected, (
            f"{operation_name} took {actual_duration:.2f}s but expected ≤ {max_expected:.2f}s"
            f"{f' for {row_count} rows' if row_count else ''}"
        )

        if actual_duration > max_expected * 0.8:
            logger.warning(
                f"⚠️ {operation_name} approaching performance limit: {actual_duration:.2f}s/{max_expected:.2f}s"
            )

    @staticmethod
    def assert_throughput_minimum(
        rows: int, duration: float, min_rows_per_second: float, operation_name: str
    ):
        """Assert minimum throughput requirements."""
        actual_throughput = rows / duration if duration > 0 else 0
        assert (
            actual_throughput >= min_rows_per_second
        ), f"{operation_name} throughput {actual_throughput:.0f} rows/s below minimum {min_rows_per_second} rows/s"


# Integration test decorators and markers


def requires_postgres(test_func):
    """Decorator to mark tests that require PostgreSQL."""
    import pytest

    return pytest.mark.integration(test_func)


def performance_test(timeout_seconds: int = 30, max_rows: int = 100000):
    """Decorator for performance-focused tests."""
    import pytest

    def decorator(test_func):
        return pytest.mark.timeout(timeout_seconds)(pytest.mark.performance(test_func))

    return decorator
