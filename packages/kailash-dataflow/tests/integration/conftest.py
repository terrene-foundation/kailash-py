"""
Configuration for integration tests.
Provides fixtures for database connections and test environments.

NO MOCKING POLICY: All integration tests must use real infrastructure.
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional

import asyncpg
import pytest

# Configure test logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def test_database_config() -> Dict[str, Any]:
    """Provide centralized database configuration for integration tests."""
    # Primary configuration from environment
    if os.getenv("TEST_DATABASE_URL"):
        return {"url": os.getenv("TEST_DATABASE_URL"), "type": "custom"}

    # Standard SDK Docker infrastructure (port 5434)
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5434")  # SDK standard port
    db_user = os.getenv("DB_USER", "test_user")
    db_password = os.getenv("DB_PASSWORD", "test_password")
    db_name = os.getenv("DB_NAME", "kailash_test")

    return {
        "url": f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}",
        "type": "postgresql",
        "host": db_host,
        "port": int(db_port),
        "user": db_user,
        "password": db_password,
        "database": db_name,
    }


@pytest.fixture(scope="session")
async def db_url(test_database_config):
    """Provide database URL for integration tests."""
    return test_database_config["url"]


@pytest.fixture(scope="function")
async def shared_connection_pool(test_database_config):
    """Create connection pool for integration tests with proper cleanup."""
    try:
        # Test connection first
        test_conn = await asyncpg.connect(test_database_config["url"])
        await test_conn.fetchval("SELECT 1")
        await test_conn.close()

        logger.info(
            f"Connected to test database: {test_database_config['type']} on port {test_database_config.get('port', 'unknown')}"
        )

        # Create connection pool with smaller size for better isolation
        pool = await asyncpg.create_pool(
            test_database_config["url"], min_size=1, max_size=5, command_timeout=10
        )

        yield pool

        # Ensure all connections are closed
        await pool.close()

    except Exception as e:
        pytest.skip(
            f"Cannot connect to test database: {e}. Ensure PostgreSQL is running on port {test_database_config.get('port', 5434)}"
        )


@pytest.fixture
async def postgres_connection(shared_connection_pool):
    """Provide individual PostgreSQL connection for each test."""
    async with shared_connection_pool.acquire() as connection:
        yield connection


class DatabaseConnectionManager:
    """Standardized connection manager for NOT NULL handler integration tests."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._connection = None

    async def get_connection(self) -> asyncpg.Connection:
        """Get database connection."""
        if self._connection is None or self._connection.is_closed():
            self._connection = await asyncpg.connect(self.database_url)
        return self._connection

    async def close(self):
        """Close database connection."""
        if self._connection and not self._connection.is_closed():
            await self._connection.close()


@pytest.fixture
async def connection_manager(db_url):
    """Create connection manager for NOT NULL handler tests."""
    manager = DatabaseConnectionManager(db_url)
    yield manager
    await manager.close()


@pytest.fixture
async def unique_table_name():
    """Generate unique table name for test isolation."""
    return f"test_table_{int(time.time() * 1000000)}"


@pytest.fixture
async def clean_test_table(postgres_connection, unique_table_name):
    """Create and clean up a basic test table with standard schema."""
    table_name = unique_table_name

    # Create standard test table
    await postgres_connection.execute(
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
    await postgres_connection.execute(
        f"""
        INSERT INTO {table_name} (name, email) VALUES
        ('Alice', 'alice@example.com'),
        ('Bob', 'bob@example.com'),
        ('Charlie', 'charlie@example.com')
    """
    )

    yield table_name

    # Clean up
    await postgres_connection.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")


@pytest.fixture
async def test_table_with_constraints(postgres_connection):
    """Create test table with various constraint types."""
    table_name = f"constrained_test_{int(time.time() * 1000000)}"
    category_table = f"categories_{int(time.time() * 1000000)}"

    # Create category table first
    await postgres_connection.execute(
        f"""
        CREATE TABLE {category_table} (
            id SERIAL PRIMARY KEY,
            name VARCHAR(50) NOT NULL UNIQUE,
            active BOOLEAN DEFAULT true
        )
    """
    )

    # Insert categories
    await postgres_connection.execute(
        f"""
        INSERT INTO {category_table} (name) VALUES ('general'), ('premium'), ('vip')
    """
    )

    # Create main table with constraints
    await postgres_connection.execute(
        f"""
        CREATE TABLE {table_name} (
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
    await postgres_connection.execute(
        f"""
        INSERT INTO {table_name} (name, email, age, category_id) VALUES
        ('Alice', 'alice@example.com', 25, 1),
        ('Bob', 'bob@example.com', 30, 2),
        ('Charlie', 'charlie@example.com', 35, 1)
    """
    )

    yield {"main_table": table_name, "category_table": category_table}

    # Clean up (order matters due to foreign key)
    await postgres_connection.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
    await postgres_connection.execute(f"DROP TABLE IF EXISTS {category_table} CASCADE")


@pytest.fixture
async def large_test_table(postgres_connection):
    """Create large test table for performance testing."""
    table_name = f"large_test_{int(time.time() * 1000000)}"

    await postgres_connection.execute(
        f"""
        CREATE TABLE {table_name} (
            id SERIAL PRIMARY KEY,
            data VARCHAR(100),
            value INTEGER
        )
    """
    )

    # Insert test data in batches for performance
    for batch_start in range(0, 10000, 1000):
        values = ", ".join(
            [
                f"('data_{i}', {i % 100})"
                for i in range(batch_start, min(batch_start + 1000, 10000))
            ]
        )
        await postgres_connection.execute(
            f"INSERT INTO {table_name} (data, value) VALUES {values}"
        )

    yield table_name

    # Clean up
    await postgres_connection.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")


# Performance testing utilities


@pytest.fixture
def performance_timeout():
    """Standard performance timeout for integration tests."""
    return 30  # seconds


@pytest.fixture
def batch_size_config():
    """Standard batch size configuration for testing."""
    return {"small": 100, "medium": 1000, "large": 10000}


@pytest.fixture
async def postgresql_db_url(test_database_config):
    """Provide PostgreSQL database URL for integration tests."""
    return test_database_config["url"]
