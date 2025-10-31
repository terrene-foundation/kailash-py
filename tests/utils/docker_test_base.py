"""Base class for Docker-based integration tests following NO MOCKING policy."""

import asyncio
import os
from typing import Any, Dict, Optional

import asyncpg
import httpx

# Import core nodes to ensure they're registered
import kailash.nodes.ai
import kailash.nodes.code
import kailash.nodes.data
import kailash.nodes.logic
import kailash.nodes.security
import pymysql
import pytest
import pytest_asyncio
import redis
from kailash.nodes.base import NodeRegistry

from tests.utils.docker_config import (
    DATABASE_CONFIG,
    MYSQL_CONFIG,
    OLLAMA_CONFIG,
    REDIS_CONFIG,
    ensure_docker_services,
    get_mysql_connection_string,
    get_postgres_connection_string,
    get_redis_url,
)


class DockerIntegrationTestBase:
    """Base class for integration tests using real Docker services.

    This base class follows the NO MOCKING policy for integration tests.
    All services (PostgreSQL, Redis, MySQL, etc.) are real Docker containers.
    """

    @pytest.fixture(autouse=True, scope="function")
    def verify_docker_services(self):
        """Verify Docker services are available before running tests."""
        import asyncio

        services_ok = asyncio.run(ensure_docker_services())
        if not services_ok:
            pytest.skip("Required Docker services not available. Run './test-env up'")

    @pytest.fixture(autouse=True, scope="function")
    def manage_node_registry(self):
        """Smart node registry management to handle test interdependencies."""
        # Capture initial state - save the actual registry state
        initial_registry = NodeRegistry.list_nodes().copy()
        initial_nodes = set(initial_registry.keys())

        # Also capture the exact state of the _nodes dictionary
        import copy

        initial_nodes_dict = copy.deepcopy(NodeRegistry._nodes)

        yield

        # After test, restore to exact initial state
        current_nodes = set(NodeRegistry.list_nodes().keys())

        # If registry has changed at all, restore it completely
        if current_nodes != initial_nodes:
            # Clear the registry
            NodeRegistry.clear()

            # Restore exact initial state by directly setting _nodes
            NodeRegistry._nodes = initial_nodes_dict

            # Verify restoration
            if set(NodeRegistry.list_nodes().keys()) != initial_nodes:
                # If still not restored, try manual registration
                for name, node_class in initial_registry.items():
                    if name not in NodeRegistry._nodes:
                        try:
                            NodeRegistry.register(node_class, name)
                        except Exception:
                            pass

    @pytest_asyncio.fixture
    async def postgres_conn(self):
        """Provide a real PostgreSQL connection."""
        conn = await asyncpg.connect(get_postgres_connection_string())
        try:
            yield conn
        finally:
            await conn.close()

    @pytest.fixture
    def redis_client(self):
        """Provide a real Redis client."""
        client = redis.Redis(**REDIS_CONFIG, decode_responses=True)
        try:
            # Clear test namespace
            for key in client.scan_iter("test:*"):
                client.delete(key)
            yield client
        finally:
            # Cleanup test data
            for key in client.scan_iter("test:*"):
                client.delete(key)

    @pytest.fixture
    def mysql_conn(self):
        """Provide a real MySQL connection."""
        conn = pymysql.connect(
            host=MYSQL_CONFIG["host"],
            port=MYSQL_CONFIG["port"],
            user=MYSQL_CONFIG["user"],
            password=MYSQL_CONFIG["password"],
            database=MYSQL_CONFIG["database"],
            cursorclass=pymysql.cursors.DictCursor,
        )
        try:
            yield conn
        finally:
            conn.close()

    @pytest.fixture
    async def http_client(self):
        """Provide HTTP client for API testing."""
        async with httpx.AsyncClient() as client:
            yield client

    @pytest_asyncio.fixture
    async def ollama_client(self):
        """Provide Ollama client for AI testing - returns None if unavailable."""
        base_url = f"http://{OLLAMA_CONFIG['host']}:{OLLAMA_CONFIG['port']}"
        async with httpx.AsyncClient(base_url=base_url) as client:
            # Verify Ollama is available
            try:
                response = await client.get("/api/tags")
                if response.status_code != 200:
                    yield None
                    return
            except Exception:
                yield None
                return
            yield client

    @pytest_asyncio.fixture
    async def test_database(self, postgres_conn):
        """Create and cleanup a test database."""
        test_db_name = f"test_db_{os.getpid()}_{id(self)}"

        # Create test database
        await postgres_conn.execute(f"CREATE DATABASE {test_db_name}")

        # Get connection to test database
        test_conn = await asyncpg.connect(
            get_postgres_connection_string(database=test_db_name)
        )

        try:
            yield test_conn
        finally:
            await test_conn.close()
            await postgres_conn.execute(f"DROP DATABASE IF EXISTS {test_db_name}")

    @pytest.fixture
    def workflow_db_config(self):
        """Provide database configuration for workflow nodes."""
        return {
            "type": "postgresql",
            "host": DATABASE_CONFIG["host"],
            "port": DATABASE_CONFIG["port"],
            "database": DATABASE_CONFIG["database"],
            "user": DATABASE_CONFIG["user"],
            "password": DATABASE_CONFIG["password"],
        }

    @pytest.fixture
    def redis_config(self):
        """Provide Redis configuration for workflow nodes."""
        return REDIS_CONFIG.copy()

    @pytest.fixture
    def mysql_config(self):
        """Provide MySQL configuration for workflow nodes."""
        return {
            "type": "mysql",
            "host": MYSQL_CONFIG["host"],
            "port": MYSQL_CONFIG["port"],
            "database": MYSQL_CONFIG["database"],
            "user": MYSQL_CONFIG["user"],
            "password": MYSQL_CONFIG["password"],
        }

    async def create_test_table(self, conn: asyncpg.Connection, table_name: str):
        """Helper to create a test table in PostgreSQL."""
        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255),
                value JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

    async def insert_test_data(
        self, conn: asyncpg.Connection, table_name: str, data: list[dict]
    ):
        """Helper to insert test data into PostgreSQL."""
        for item in data:
            await conn.execute(
                f"""
                INSERT INTO {table_name} (name, value)
                VALUES ($1, $2)
                """,
                item.get("name", "test"),
                item.get("value", {}),
            )

    def create_redis_test_data(self, client: redis.Redis, prefix: str = "test"):
        """Helper to create test data in Redis."""
        test_data = {
            f"{prefix}:string": "test_value",
            f"{prefix}:number": "42",
            f"{prefix}:json": '{"key": "value"}',
        }

        for key, value in test_data.items():
            client.set(key, value)

        # Add to a set
        client.sadd(f"{prefix}:set", "item1", "item2", "item3")

        # Add to a list
        client.rpush(f"{prefix}:list", "first", "second", "third")

        # Add to a hash
        client.hset(f"{prefix}:hash", mapping={"field1": "value1", "field2": "value2"})

        return test_data

    async def verify_ollama_model(
        self, client: httpx.AsyncClient, model: str = "llama3.2:1b"
    ):
        """Verify an Ollama model is available - returns False if unavailable."""
        if client is None:
            return False
        response = await client.get("/api/tags")
        if response.status_code == 200:
            models = response.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            return model in model_names
        else:
            return False


class AsyncDockerTestBase(DockerIntegrationTestBase):
    """Base class for async integration tests."""

    @pytest.fixture
    def event_loop(self):
        """Create an instance of the default event loop for the test session."""
        loop = asyncio.get_event_loop_policy().new_event_loop()
        yield loop
        loop.close()
