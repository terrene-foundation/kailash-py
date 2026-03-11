"""
Real infrastructure utilities for integration and E2E tests.

Provides Docker container management and database connections for tests.
"""

import os
import subprocess
import time
from typing import Any, Dict, List, Optional

import asyncpg
import pytest

try:
    import docker
except ImportError:
    docker = None


class RealInfrastructure:
    """Manages real infrastructure for testing."""

    def __init__(self):
        """Initialize infrastructure manager."""
        self.docker_client = None
        self.containers = {}

    def start_postgres(self, port: int = 5434) -> Dict[str, str]:
        """Use shared SDK Docker PostgreSQL instead of creating new containers."""
        # Always return the shared SDK Docker configuration
        # This prevents port conflicts and ensures all tests use the same infrastructure
        return {
            "host": "localhost",
            "port": "5434",  # Shared SDK Docker PostgreSQL port
            "database": "kailash_test",
            "user": "test_user",
            "password": "test_password",
        }

    def _check_postgres_ready(self, port: int) -> bool:
        """Check if PostgreSQL is ready to accept connections."""
        try:
            result = subprocess.run(
                ["pg_isready", "-h", "localhost", "-p", str(port)],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except:
            return False

    def stop_all(self):
        """Stop all test containers."""
        if self.docker_client:
            for container in self.containers.values():
                try:
                    container.stop(timeout=5)
                    container.remove()
                except:
                    pass

    def get_postgres_url(self, port: int = 5434) -> str:
        """Get PostgreSQL connection URL."""
        config = self.start_postgres(port)
        return f"postgresql://{config['user']}:{config['password']}@{config['host']}:{config['port']}/{config['database']}"

    def get_sqlite_memory_db(self):
        """Get SQLite in-memory database for testing."""
        from dataflow import DataFlow

        return DataFlow(":memory:")

    def get_postgresql_test_db(self):
        """Get PostgreSQL test database using existing test infrastructure."""
        from dataflow import DataFlow

        # Use the shared SDK Docker PostgreSQL
        url = "postgresql://test_user:test_password@localhost:5434/kailash_test"
        try:
            return DataFlow(url, existing_schema_mode=True)
        except Exception as e:
            print(f"Failed to connect to PostgreSQL test infrastructure: {e}")
            return None

    def get_mysql_test_db(self):
        """Get MySQL test database (placeholder)."""
        # MySQL support not yet implemented
        return None


# Global instance
real_infra = RealInfrastructure()


# Pytest fixtures
@pytest.fixture(scope="session")
def postgres_container():
    """Start PostgreSQL container for testing session."""
    config = real_infra.start_postgres()
    yield config
    # Cleanup handled by real_infra at session end


@pytest.fixture
def postgres_url(postgres_container):
    """Get PostgreSQL URL for tests."""
    return real_infra.get_postgres_url()


class PostgreSQLTestManager:
    """Manages PostgreSQL test databases for E2E tests."""

    def __init__(self, config: Optional[Dict[str, str]] = None):
        self.config = config or real_infra.start_postgres()
        self._pool: Optional[asyncpg.Pool] = None

    @property
    def url(self) -> str:
        return (
            f"postgresql://{self.config['user']}:{self.config['password']}"
            f"@{self.config['host']}:{self.config['port']}/{self.config['database']}"
        )

    async def initialize(self):
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.url, min_size=1, max_size=5, command_timeout=30
            )

    async def execute(self, sql: str):
        await self.initialize()
        async with self._pool.acquire() as conn:
            await conn.execute(sql)

    async def fetch(self, sql: str):
        await self.initialize()
        async with self._pool.acquire() as conn:
            return await conn.fetch(sql)

    async def cleanup(self):
        if self._pool:
            await self._pool.close()
            self._pool = None


async def setup_test_database(db_name: str = "e2e_test") -> Dict[str, Any]:
    """Set up a test database and return connection config dict."""
    config = real_infra.start_postgres()
    # Verify connection
    try:
        conn = await asyncpg.connect(
            host=config["host"],
            port=int(config["port"]),
            user=config["user"],
            password=config["password"],
            database=config["database"],
        )
        await conn.fetchval("SELECT 1")
        await conn.close()
    except Exception as e:
        pytest.skip(f"PostgreSQL not available: {e}")
    return config


async def create_test_tables(config: Dict[str, Any], sql_statements: List[str]):
    """Create test tables using the provided SQL statements."""
    conn = await asyncpg.connect(
        host=config["host"],
        port=int(config["port"]),
        user=config["user"],
        password=config["password"],
        database=config["database"],
    )
    try:
        for sql in sql_statements:
            await conn.execute(sql)
    finally:
        await conn.close()


async def insert_test_data(config: Dict[str, Any], sql_statements: List[str]):
    """Insert test data using the provided SQL statements."""
    conn = await asyncpg.connect(
        host=config["host"],
        port=int(config["port"]),
        user=config["user"],
        password=config["password"],
        database=config["database"],
    )
    try:
        for sql in sql_statements:
            await conn.execute(sql)
    finally:
        await conn.close()


async def cleanup_test_database(config: Dict[str, Any]):
    """Clean up test tables created during E2E tests."""
    conn = await asyncpg.connect(
        host=config["host"],
        port=int(config["port"]),
        user=config["user"],
        password=config["password"],
        database=config["database"],
    )
    try:
        # Drop known test tables in dependency order
        for table in ["order_items", "orders", "customers", "customer_preferences"]:
            await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    finally:
        await conn.close()
