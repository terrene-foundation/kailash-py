"""Integration tests for AsyncSQLDatabaseNode configuration with REAL PostgreSQL."""

import os
import tempfile

import pytest
import pytest_asyncio
import yaml
from tests.utils.docker_config import get_postgres_connection_string

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

# Mark all tests as requiring postgres and as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.requires_postgres]


class TestAsyncSQLConfigIntegration:
    """Test configuration functionality with REAL PostgreSQL database."""

    @pytest_asyncio.fixture
    async def setup_database(self):
        """Set up test database."""
        conn_string = get_postgres_connection_string()

        # Create test table
        setup_node = AsyncSQLDatabaseNode(
            name="setup",
            database_type="postgresql",
            connection_string=conn_string,
            allow_admin=True,
        )

        await setup_node.execute_async(query="DROP TABLE IF EXISTS config_test")
        await setup_node.execute_async(
            query="""
            CREATE TABLE config_test (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                value INTEGER
            )
        """
        )

        yield conn_string

        # Cleanup
        await setup_node.execute_async(query="DROP TABLE IF EXISTS config_test")
        await setup_node.cleanup()

    @pytest.mark.asyncio
    async def test_config_file_connection(self, setup_database):
        """Test connecting to database using config file."""
        conn_string = setup_database

        # Create config file
        config_data = {
            "databases": {
                "test_db": {
                    "connection_string": conn_string,
                    "database_type": "postgresql",
                    "pool_size": 5,
                    "max_pool_size": 10,
                    "timeout": 30.0,
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            # Create node using config file
            node = AsyncSQLDatabaseNode(
                name="config_node",
                connection_name="test_db",
                config_file=config_path,
            )

            # Test query execution
            result = await node.execute_async(
                query="INSERT INTO config_test (name, value) VALUES (:name, :value) RETURNING id",
                params={"name": "ConfigTest", "value": 42},
            )

            assert len(result["result"]["data"]) == 1
            assert result["result"]["data"][0]["id"] > 0

            # Verify pool configuration was applied
            pool_info = node.get_pool_info()
            assert pool_info["pool_key"] is not None  # Pool should be created

            await node.cleanup()

        finally:
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_multiple_connections_in_config(self, setup_database):
        """Test using multiple database connections from same config file."""
        conn_string = setup_database

        # Create config with multiple connections
        config_data = {
            "databases": {
                "primary": {
                    "connection_string": conn_string,
                    "database_type": "postgresql",
                    "pool_size": 10,
                },
                "secondary": {
                    "connection_string": conn_string,  # Same DB for testing
                    "database_type": "postgresql",
                    "pool_size": 5,
                },
                "default": {
                    "connection_string": conn_string,
                    "database_type": "postgresql",
                    "pool_size": 3,
                },
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            # Create nodes for different connections
            primary_node = AsyncSQLDatabaseNode(
                name="primary_node",
                connection_name="primary",
                config_file=config_path,
            )

            secondary_node = AsyncSQLDatabaseNode(
                name="secondary_node",
                connection_name="secondary",
                config_file=config_path,
            )

            # Test both connections work
            await primary_node.execute_async(
                query="INSERT INTO config_test (name, value) VALUES ('Primary', 1)"
            )

            await secondary_node.execute_async(
                query="INSERT INTO config_test (name, value) VALUES ('Secondary', 2)"
            )

            # Verify data from both
            result = await primary_node.execute_async(
                query="SELECT name, value FROM config_test ORDER BY value"
            )

            assert len(result["result"]["data"]) == 2
            assert result["result"]["data"][0]["name"] == "Primary"
            assert result["result"]["data"][1]["name"] == "Secondary"

            # Test default fallback
            default_node = AsyncSQLDatabaseNode(
                name="default_node",
                connection_name="nonexistent",  # Should fall back to default
                config_file=config_path,
            )

            result = await default_node.execute_async(
                query="SELECT COUNT(*) as count FROM config_test"
            )

            assert result["result"]["data"][0]["count"] == 2

            # Cleanup
            await primary_node.cleanup()
            await secondary_node.cleanup()
            await default_node.cleanup()

        finally:
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_env_var_substitution_integration(self, setup_database):
        """Test environment variable substitution in real scenario."""
        conn_string = setup_database

        # Parse connection string to extract components
        # Format: postgresql://user:password@host:port/database
        import re

        match = re.match(
            r"postgresql://(?P<user>[^:]+):(?P<password>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)/(?P<database>.+)",
            conn_string,
        )

        if match:
            parts = match.groupdict()

            # Set environment variables
            os.environ["TEST_DB_USER"] = parts["user"]
            os.environ["TEST_DB_PASSWORD"] = parts["password"]
            os.environ["TEST_DB_HOST"] = parts["host"]
            os.environ["TEST_DB_PORT"] = parts["port"]
            os.environ["TEST_DB_NAME"] = parts["database"]

            # Create config with env vars
            config_data = {
                "databases": {
                    "env_test": {
                        "connection_string": "postgresql://$TEST_DB_USER:$TEST_DB_PASSWORD@$TEST_DB_HOST:$TEST_DB_PORT/$TEST_DB_NAME",
                        "database_type": "postgresql",
                    }
                }
            }

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                yaml.dump(config_data, f)
                config_path = f.name

            try:
                # Create node with env var config
                node = AsyncSQLDatabaseNode(
                    name="env_node",
                    connection_name="env_test",
                    config_file=config_path,
                )

                # Test connection works
                result = await node.execute_async(
                    query="SELECT current_database() as db_name"
                )

                assert result["result"]["data"][0]["db_name"] == parts["database"]

                await node.cleanup()

            finally:
                os.unlink(config_path)
                # Clean up env vars
                for var in [
                    "TEST_DB_USER",
                    "TEST_DB_PASSWORD",
                    "TEST_DB_HOST",
                    "TEST_DB_PORT",
                    "TEST_DB_NAME",
                ]:
                    os.environ.pop(var, None)

    @pytest.mark.asyncio
    async def test_config_with_advanced_settings(self, setup_database):
        """Test advanced configuration settings from file."""
        conn_string = setup_database

        # Create config with advanced settings
        config_data = {
            "databases": {
                "advanced": {
                    "connection_string": conn_string,
                    "database_type": "postgresql",
                    "pool_size": 2,
                    "max_pool_size": 5,
                    "timeout": 10.0,
                    "transaction_mode": "manual",
                    "share_pool": False,
                    "validate_queries": True,
                    "allow_admin": False,
                    "retry_config": {
                        "max_retries": 5,
                        "initial_delay": 0.5,
                        "retryable_errors": ["deadlock", "serialization failure"],
                    },
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            # Create node with advanced config
            node = AsyncSQLDatabaseNode(
                name="advanced_node",
                connection_name="advanced",
                config_file=config_path,
            )

            # Verify settings were applied
            assert node.config["transaction_mode"] == "manual"
            assert node.config["share_pool"] is False
            assert node.config["validate_queries"] is True
            assert node.config["allow_admin"] is False

            # Test manual transaction mode
            await node.begin_transaction()

            await node.execute_async(
                query="INSERT INTO config_test (name, value) VALUES ('TX1', 100)"
            )

            await node.execute_async(
                query="INSERT INTO config_test (name, value) VALUES ('TX2', 200)"
            )

            await node.commit()

            # Verify both inserts succeeded
            result = await node.execute_async(
                query="SELECT COUNT(*) as count FROM config_test WHERE name IN ('TX1', 'TX2')"
            )

            assert result["result"]["data"][0]["count"] == 2

            # Test query validation blocks admin commands
            from kailash.sdk_exceptions import NodeExecutionError

            with pytest.raises(NodeExecutionError, match="administrative command"):
                await node.execute_async(query="CREATE TABLE should_fail (id INT)")

            await node.cleanup()

        finally:
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_config_inheritance_and_override(self, setup_database):
        """Test config file values with parameter overrides."""
        conn_string = setup_database

        # Create base config
        config_data = {
            "databases": {
                "base": {
                    "connection_string": conn_string,
                    "database_type": "postgresql",
                    "pool_size": 10,
                    "timeout": 60.0,
                    "validate_queries": False,
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            # Create node with overrides
            node = AsyncSQLDatabaseNode(
                name="override_node",
                connection_name="base",
                config_file=config_path,
                pool_size=20,  # Override config file value
                timeout=30.0,  # Override config file value
                transaction_mode="none",  # Add new value
            )

            # Verify overrides
            assert node.config["pool_size"] == 20  # Overridden
            assert node.config["timeout"] == 30.0  # Overridden
            assert node.config["transaction_mode"] == "none"  # Added
            assert node.config["validate_queries"] is False  # From file

            # Test execution works
            result = await node.execute_async(
                query="SELECT :value::int * 2 as result", params={"value": 21}
            )

            assert result["result"]["data"][0]["result"] == 42

            await node.cleanup()

        finally:
            os.unlink(config_path)
