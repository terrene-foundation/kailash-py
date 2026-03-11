"""
Test Environment Setup for PostgreSQL-Only DataFlow Testing

Sets up Docker PostgreSQL instance for integration and E2E tests.
NO MOCKING policy enforced - all services are real.
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict

import asyncpg

try:
    from docker.errors import DockerException

    import docker
except ImportError:
    docker = None
    DockerException = Exception  # Fallback for when Docker is not installed

logger = logging.getLogger(__name__)


def create_test_table(connection, table_name: str = "test_table"):
    """Create a test table for integration tests."""
    sql = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255),
        value INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    if hasattr(connection, "execute"):
        # Sync connection
        cursor = connection.cursor()
        cursor.execute(sql)
        connection.commit()
        cursor.close()
    else:
        # Async connection
        return connection.execute(sql)


def execute_sql(connection, sql: str, params=None):
    """Execute SQL query on the test database."""
    if hasattr(connection, "cursor"):
        # Sync connection
        cursor = connection.cursor()
        cursor.execute(sql, params or ())
        if sql.strip().upper().startswith("SELECT"):
            result = cursor.fetchall()
        else:
            result = cursor.rowcount
            connection.commit()
        cursor.close()
        return result
    else:
        # Async connection
        return connection.execute(sql, params)


def verify_table_exists(connection, table_name: str) -> bool:
    """Verify if a table exists in the database."""
    sql = """
    SELECT EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name = %s
    )
    """
    result = execute_sql(connection, sql, (table_name,))
    return bool(result[0][0]) if result else False


def verify_column_exists(connection, table_name: str, column_name: str) -> bool:
    """Verify if a column exists in a table."""
    sql = """
    SELECT EXISTS (
        SELECT FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = %s
        AND column_name = %s
    )
    """
    result = execute_sql(connection, sql, (table_name, column_name))
    return bool(result[0][0]) if result else False


class PostgreSQLTestEnvironment:
    """Manages PostgreSQL Docker container for testing."""

    def __init__(self):
        self.client = None
        self.container = None
        self.connection_config = {
            "host": "localhost",
            "port": 5433,  # Use different port to avoid conflicts
            "database": "dataflow_test",
            "user": "dataflow_test",
            "password": "dataflow_test_password",
        }

    async def start(self) -> bool:
        """Start PostgreSQL Docker container."""
        try:
            self.client = docker.from_env()

            # Check if container already exists
            try:
                existing_container = self.client.containers.get(
                    "dataflow_test_postgres"
                )
                if existing_container.status == "running":
                    logger.info("PostgreSQL test container already running")
                    return await self._wait_for_ready()
                else:
                    existing_container.remove(force=True)
            except docker.errors.NotFound:
                pass

            # Start new PostgreSQL container
            logger.info("Starting PostgreSQL test container...")
            self.container = self.client.containers.run(
                "postgres:15",
                name="dataflow_test_postgres",
                environment={
                    "POSTGRES_DB": self.connection_config["database"],
                    "POSTGRES_USER": self.connection_config["user"],
                    "POSTGRES_PASSWORD": self.connection_config["password"],
                    "POSTGRES_HOST_AUTH_METHOD": "trust",
                },
                ports={5432: self.connection_config["port"]},
                detach=True,
                remove=False,
            )

            # Wait for PostgreSQL to be ready
            return await self._wait_for_ready()

        except DockerException as e:
            logger.error(f"Failed to start PostgreSQL container: {e}")
            return False

    async def stop(self):
        """Stop PostgreSQL Docker container."""
        if self.container:
            try:
                self.container.stop()
                self.container.remove()
                logger.info("PostgreSQL test container stopped")
            except Exception as e:
                logger.warning(f"Error stopping container: {e}")

    async def _wait_for_ready(self, max_retries: int = 30) -> bool:
        """Wait for PostgreSQL to be ready to accept connections."""
        for attempt in range(max_retries):
            try:
                conn = await asyncpg.connect(
                    host=self.connection_config["host"],
                    port=self.connection_config["port"],
                    database=self.connection_config["database"],
                    user=self.connection_config["user"],
                    password=self.connection_config["password"],
                )
                await conn.close()
                logger.info("PostgreSQL test database ready")
                return True
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(
                        f"PostgreSQL not ready after {max_retries} attempts: {e}"
                    )
                    return False
                await asyncio.sleep(1)

        return False

    async def get_connection(self):
        """Get PostgreSQL connection for testing."""
        return await asyncpg.connect(
            host=self.connection_config["host"],
            port=self.connection_config["port"],
            database=self.connection_config["database"],
            user=self.connection_config["user"],
            password=self.connection_config["password"],
        )

    async def cleanup_database(self):
        """Clean all test data from database."""
        conn = await self.get_connection()
        try:
            # Drop all tables except system tables
            await conn.execute(
                """
                DO $$ DECLARE
                    r RECORD;
                BEGIN
                    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                        EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
                    END LOOP;
                END $$;
            """
            )
            logger.info("Test database cleaned")
        finally:
            await conn.close()

    async def status(self) -> Dict[str, Any]:
        """Get status of test environment."""
        status = {
            "container_running": False,
            "database_ready": False,
            "connection_config": self.connection_config,
        }

        if self.container:
            try:
                self.container.reload()
                status["container_running"] = self.container.status == "running"
            except Exception:
                pass

        # Test database connection
        try:
            conn = await self.get_connection()
            await conn.close()
            status["database_ready"] = True
        except Exception:
            pass

        return status


# Global test environment instance
test_env = PostgreSQLTestEnvironment()


async def setup_test_environment():
    """Setup test environment for integration tests."""
    success = await test_env.start()
    if not success:
        raise RuntimeError("Failed to start PostgreSQL test environment")
    return test_env


async def teardown_test_environment():
    """Teardown test environment."""
    await test_env.stop()


async def get_test_connection():
    """Get test database connection."""
    return await test_env.get_connection()


async def cleanup_test_data():
    """Clean all test data."""
    await test_env.cleanup_database()
