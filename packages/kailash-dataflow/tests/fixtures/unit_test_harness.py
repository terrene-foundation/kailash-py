#!/usr/bin/env python3
"""
DataFlow Unit Test Harness (Tier 1)

Provides standardized infrastructure and utilities for DataFlow unit tests,
following the IntegrationTestSuite patterns but adapted for unit testing.

This module follows the Tier 1 testing policy:
- ✅ SQLite databases (both :memory: and file-based)
- ✅ Mocks and stubs for external services
- ❌ PostgreSQL connections (use integration tests instead)

Based on tests/infrastructure/test_harness.py but adapted for unit testing constraints.
"""

import asyncio
import logging
import os
import tempfile
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional
from unittest.mock import MagicMock, patch

import aiosqlite
from dataflow import DataFlow

logger = logging.getLogger(__name__)


@dataclass
class UnitTestDatabaseConfig:
    """Centralized database configuration for unit tests (Tier 1 only)."""

    url: str
    type: str
    file_path: Optional[str] = None
    in_memory: bool = True

    @classmethod
    def memory_database(cls) -> "UnitTestDatabaseConfig":
        """Create in-memory SQLite configuration for fast unit tests."""
        return cls(url=":memory:", type="sqlite", in_memory=True)

    @classmethod
    def file_database(cls, suffix: str = ".db") -> "UnitTestDatabaseConfig":
        """Create file-based SQLite configuration for persistent unit tests."""
        temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        file_path = temp_file.name
        temp_file.close()

        return cls(
            url=f"sqlite:///{file_path}",
            type="sqlite",
            file_path=file_path,
            in_memory=False,
        )

    def cleanup(self):
        """Clean up file-based database if exists."""
        if not self.in_memory and self.file_path and os.path.exists(self.file_path):
            try:
                os.unlink(self.file_path)
                logger.debug(f"✅ Cleaned up database file: {self.file_path}")
            except Exception as e:
                logger.warning(
                    f"Failed to clean up database file {self.file_path}: {e}"
                )


class SQLiteUnitTestInfrastructure:
    """Manages SQLite infrastructure for unit tests."""

    def __init__(self, config: UnitTestDatabaseConfig):
        self.config = config
        self._connection: Optional[aiosqlite.Connection] = None
        self._initialized = False

    async def initialize(self):
        """Initialize SQLite infrastructure."""
        if self._initialized:
            return

        if self.config.in_memory:
            self._connection = await aiosqlite.connect(":memory:")
        else:
            self._connection = await aiosqlite.connect(self.config.file_path)

        # Enable foreign key support
        await self._connection.execute("PRAGMA foreign_keys = ON")
        await self._connection.commit()

        self._initialized = True
        logger.debug(
            f"✅ SQLite unit test infrastructure initialized: {self.config.type}"
        )

    async def get_connection(self) -> aiosqlite.Connection:
        """Get the SQLite connection."""
        if not self._initialized:
            await self.initialize()
        return self._connection

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Context manager for database connections."""
        if not self._initialized:
            await self.initialize()
        yield self._connection

    async def cleanup(self):
        """Clean up SQLite infrastructure."""
        if self._connection:
            await self._connection.close()
            self._connection = None

        self.config.cleanup()
        self._initialized = False
        logger.debug("✅ SQLite unit test infrastructure cleaned up")


class UnitTestTableFactory:
    """Factory for creating standardized test tables in SQLite."""

    def __init__(self, infrastructure: SQLiteUnitTestInfrastructure):
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
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
            await conn.commit()

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
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    active BOOLEAN DEFAULT 1
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
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE,
                    age INTEGER CHECK (age >= 0 AND age <= 150),
                    category_id INTEGER REFERENCES {category_table}(id),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
            await conn.commit()

        self._created_tables.extend([category_table, main_table])
        return {"main_table": main_table, "category_table": category_table}

    async def cleanup_all(self):
        """Clean up all created tables."""
        if not self._created_tables:
            return

        async with self.infrastructure.connection() as conn:
            # Drop tables in reverse order (handles foreign key dependencies)
            for table_name in reversed(self._created_tables):
                try:
                    await conn.execute(f"DROP TABLE IF EXISTS {table_name}")
                except Exception as e:
                    logger.warning(f"Failed to drop table {table_name}: {e}")
            await conn.commit()

        table_count = len(self._created_tables)
        self._created_tables.clear()
        logger.debug(f"✅ Cleaned up {table_count} unit test tables")


class MockingUtilities:
    """Utilities for creating standardized mocks in unit tests."""

    @staticmethod
    def mock_connection_manager(database_url: str = ":memory:") -> MagicMock:
        """Create mock connection manager for unit testing."""
        from unittest.mock import AsyncMock

        mock_manager = MagicMock()
        mock_manager.database_url = database_url
        # Make get_connection async
        mock_manager.get_connection = AsyncMock(return_value=AsyncMock())
        mock_manager.close.return_value = None
        return mock_manager

    @staticmethod
    def mock_migration_executor() -> MagicMock:
        """Create mock migration executor for unit testing."""
        mock_executor = MagicMock()
        mock_executor.migrations = []
        mock_executor.executed_migrations = []
        mock_executor.add_migration.return_value = None
        mock_executor.execute_migration.return_value = {
            "success": True,
            "duration": 0.1,
        }
        mock_executor.rollback_migration.return_value = {"success": True}
        return mock_executor

    @staticmethod
    def mock_dataflow_engine() -> MagicMock:
        """Create mock DataFlow engine for unit testing."""
        mock_engine = MagicMock()
        mock_engine.initialize.return_value = None
        mock_engine.get_models.return_value = {}
        mock_engine.discover_schema.return_value = {}
        return mock_engine

    @staticmethod
    @asynccontextmanager
    async def mock_async_context_manager():
        """Create a mock async context manager."""
        yield MagicMock()


class DataFlowUnitTestHarness:
    """Unit test harness for DataFlow testing."""

    def __init__(self, infrastructure: SQLiteUnitTestInfrastructure):
        self.infrastructure = infrastructure
        self.table_factory = UnitTestTableFactory(infrastructure)
        self._dataflow_instances = []  # Track DataFlow instances for cleanup

    def create_dataflow(self, **kwargs) -> DataFlow:
        """Create DataFlow instance with SQLite test database configuration."""
        config = {
            "auto_migrate": kwargs.get("auto_migrate", False),
            "existing_schema_mode": kwargs.get("existing_schema_mode", True),
            **kwargs,
        }
        dataflow = DataFlow(self.infrastructure.config.url, **config)
        self._dataflow_instances.append(dataflow)  # Track for cleanup
        return dataflow

    async def cleanup(self):
        """Clean up DataFlow unit test resources."""
        # Clean up DataFlow instances
        for dataflow in self._dataflow_instances:
            try:
                # Close any open connections in DataFlow instances
                if (
                    hasattr(dataflow, "_connection_manager")
                    and dataflow._connection_manager
                ):
                    if hasattr(dataflow._connection_manager, "cleanup"):
                        await dataflow._connection_manager.cleanup()
            except Exception as e:
                logger.warning(f"Error cleaning up DataFlow instance: {e}")

        self._dataflow_instances.clear()
        await self.table_factory.cleanup_all()
        logger.debug("✅ DataFlow unit test harness cleaned up")


class UnitTestSuite:
    """Complete unit test suite with all harnesses (Tier 1)."""

    def __init__(
        self, config: Optional[UnitTestDatabaseConfig] = None, use_memory: bool = True
    ):
        self.config = config or (
            UnitTestDatabaseConfig.memory_database()
            if use_memory
            else UnitTestDatabaseConfig.file_database()
        )
        self.infrastructure = SQLiteUnitTestInfrastructure(self.config)
        self.dataflow_harness = DataFlowUnitTestHarness(self.infrastructure)
        self.mocking = MockingUtilities()

    async def initialize(self):
        """Initialize the complete unit test suite."""
        await self.infrastructure.initialize()
        logger.debug("🚀 Unit test suite initialized")

    async def cleanup(self):
        """Clean up the complete unit test suite."""
        await self.dataflow_harness.cleanup()
        await self.infrastructure.cleanup()
        logger.debug("✅ Unit test suite cleaned up")

    @asynccontextmanager
    async def session(self):
        """Context manager for unit test session lifecycle."""
        await self.initialize()
        try:
            yield self
        finally:
            await self.cleanup()

    def get_connection(self):
        """Get a database connection.

        Returns a context manager that yields an aiosqlite connection.
        This delegates to the infrastructure's connection method.
        """
        return self.infrastructure.connection()


# Unit test decorators and utilities


def requires_sqlite(test_func):
    """Decorator to mark tests that require SQLite."""
    import pytest

    return pytest.mark.unit(test_func)


def sqlite_memory_test(test_func):
    """Decorator for SQLite memory-based unit tests."""
    import pytest

    return pytest.mark.unit(pytest.mark.sqlite_memory(test_func))


def sqlite_file_test(test_func):
    """Decorator for SQLite file-based unit tests."""
    import pytest

    return pytest.mark.unit(pytest.mark.sqlite_file(test_func))


# Standard fixtures that can be used across unit tests


class StandardUnitFixtures:
    """Standard fixtures for unit tests."""

    @staticmethod
    def memory_test_suite():
        """Create a standard memory-based unit test suite."""
        return UnitTestSuite(use_memory=True)

    @staticmethod
    def file_test_suite():
        """Create a standard file-based unit test suite."""
        return UnitTestSuite(use_memory=False)

    @staticmethod
    def mock_postgresql_config():
        """Create mock PostgreSQL config for unit tests that need to simulate it."""
        mock_config = MagicMock()
        mock_config.url = "postgresql://mock:mock@localhost:5432/mock"
        mock_config.type = "postgresql"
        mock_config.host = "localhost"
        mock_config.port = 5432
        return mock_config
