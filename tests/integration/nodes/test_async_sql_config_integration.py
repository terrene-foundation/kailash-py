"""Unit tests for AsyncSQLDatabaseNode configuration management."""

import os
import tempfile
from unittest.mock import patch

import pytest
import yaml
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode, DatabaseConfigManager
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


class TestDatabaseConfigManager:
    """Test DatabaseConfigManager functionality."""

    def test_default_config_path(self):
        """Test default configuration file path."""
        manager = DatabaseConfigManager()
        assert manager.config_path == "database.yaml"

    def test_custom_config_path(self):
        """Test custom configuration file path."""
        manager = DatabaseConfigManager("/path/to/config.yaml")
        assert manager.config_path == "/path/to/config.yaml"

    def test_load_valid_config(self):
        """Test loading valid YAML configuration."""
        config_data = {
            "databases": {
                "production": {
                    "connection_string": "postgresql://user:pass@localhost/prod_db",
                    "pool_size": 20,
                    "timeout": 30.0,
                },
                "test": {
                    "url": "postgresql://user:pass@localhost/test_db",
                    "pool_size": 5,
                },
                "default": {
                    "connection_string": "sqlite:///default.db",
                },
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            manager = DatabaseConfigManager(temp_path)

            # Test production config
            conn_str, config = manager.get_database_config("production")
            assert conn_str == "postgresql://user:pass@localhost/prod_db"
            assert config["pool_size"] == 20
            assert config["timeout"] == 30.0

            # Test config with 'url' key
            conn_str, config = manager.get_database_config("test")
            assert conn_str == "postgresql://user:pass@localhost/test_db"
            assert config["pool_size"] == 5

            # Test default fallback
            conn_str, config = manager.get_database_config("nonexistent")
            assert conn_str == "sqlite:///default.db"

        finally:
            os.unlink(temp_path)

    def test_missing_config_file(self):
        """Test behavior with missing config file."""
        manager = DatabaseConfigManager("/nonexistent/config.yaml")

        # Should raise error when trying to get config
        with pytest.raises(NodeExecutionError, match="not found in configuration"):
            manager.get_database_config("test")

    def test_invalid_yaml(self):
        """Test handling of invalid YAML."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: ][")
            temp_path = f.name

        try:
            manager = DatabaseConfigManager(temp_path)
            with pytest.raises(NodeValidationError, match="Invalid YAML"):
                manager.get_database_config("test")
        finally:
            os.unlink(temp_path)

    def test_env_var_substitution_full(self):
        """Test environment variable substitution with ${VAR} format."""
        config_data = {
            "databases": {
                "test": {
                    "connection_string": "${DB_CONNECTION_STRING}",
                    "user": "${DB_USER}",
                    "password": "${DB_PASSWORD}",
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            # Set environment variables
            os.environ["DB_CONNECTION_STRING"] = "postgresql://localhost/testdb"
            os.environ["DB_USER"] = "testuser"
            os.environ["DB_PASSWORD"] = "testpass"

            manager = DatabaseConfigManager(temp_path)
            conn_str, config = manager.get_database_config("test")

            assert conn_str == "postgresql://localhost/testdb"
            assert config["user"] == "testuser"
            assert config["password"] == "testpass"

        finally:
            os.unlink(temp_path)
            # Clean up env vars
            for var in ["DB_CONNECTION_STRING", "DB_USER", "DB_PASSWORD"]:
                os.environ.pop(var, None)

    def test_env_var_substitution_inline(self):
        """Test environment variable substitution with $VAR format in strings."""
        config_data = {
            "databases": {
                "test": {
                    "connection_string": "postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME",
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            # Set environment variables
            os.environ["DB_USER"] = "myuser"
            os.environ["DB_PASSWORD"] = "mypass"
            os.environ["DB_HOST"] = "localhost"
            os.environ["DB_PORT"] = "5432"
            os.environ["DB_NAME"] = "mydb"

            manager = DatabaseConfigManager(temp_path)
            conn_str, config = manager.get_database_config("test")

            assert conn_str == "postgresql://myuser:mypass@localhost:5432/mydb"

        finally:
            os.unlink(temp_path)
            # Clean up env vars
            for var in ["DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME"]:
                os.environ.pop(var, None)

    def test_missing_env_var(self):
        """Test error when environment variable is not found."""
        config_data = {
            "databases": {
                "test": {
                    "connection_string": "${MISSING_VAR}",
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            manager = DatabaseConfigManager(temp_path)
            with pytest.raises(
                NodeExecutionError, match="Environment variable 'MISSING_VAR' not found"
            ):
                manager.get_database_config("test")
        finally:
            os.unlink(temp_path)

    def test_list_connections(self):
        """Test listing available connections."""
        config_data = {
            "databases": {
                "production": {"url": "postgresql://localhost/prod"},
                "staging": {"url": "postgresql://localhost/stage"},
                "test": {"url": "postgresql://localhost/test"},
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            manager = DatabaseConfigManager(temp_path)
            connections = manager.list_connections()

            assert set(connections) == {"production", "staging", "test"}

        finally:
            os.unlink(temp_path)

    def test_validate_config(self):
        """Test configuration validation."""
        # Valid config
        valid_config = {
            "databases": {
                "test": {"connection_string": "postgresql://localhost/test"},
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(valid_config, f)
            temp_path = f.name

        try:
            manager = DatabaseConfigManager(temp_path)
            manager.validate_config()  # Should not raise
        finally:
            os.unlink(temp_path)

        # Invalid config - no connection string
        invalid_config = {
            "databases": {
                "test": {"pool_size": 10},  # Missing connection_string/url
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(invalid_config, f)
            temp_path = f.name

        try:
            manager = DatabaseConfigManager(temp_path)
            with pytest.raises(
                NodeValidationError, match="must have 'connection_string' or 'url'"
            ):
                manager.validate_config()
        finally:
            os.unlink(temp_path)

    def test_config_caching(self):
        """Test that configurations are cached."""
        config_data = {
            "databases": {
                "test": {
                    "connection_string": "postgresql://localhost/test",
                    "pool_size": 10,
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            manager = DatabaseConfigManager(temp_path)

            # First call
            conn_str1, config1 = manager.get_database_config("test")

            # Modify the file
            config_data["databases"]["test"]["pool_size"] = 20
            with open(temp_path, "w") as f:
                yaml.dump(config_data, f)

            # Second call should return cached value
            conn_str2, config2 = manager.get_database_config("test")

            assert config1["pool_size"] == config2["pool_size"] == 10

        finally:
            os.unlink(temp_path)


class TestAsyncSQLDatabaseNodeConfig:
    """Test AsyncSQLDatabaseNode configuration integration."""

    def test_load_config_from_file(self):
        """Test loading database configuration from file."""
        config_data = {
            "databases": {
                "myapp": {
                    "connection_string": "postgresql://user:pass@localhost:5432/myapp_db",
                    "pool_size": 15,
                    "max_pool_size": 30,
                    "timeout": 45.0,
                    "database_type": "postgresql",
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            node = AsyncSQLDatabaseNode(
                name="test_node",
                connection_name="myapp",
                config_file=temp_path,
                query="SELECT 1",
            )

            # Check that config was loaded
            assert (
                node.config["connection_string"]
                == "postgresql://user:pass@localhost:5432/myapp_db"
            )
            # Config file values should override defaults
            assert node.config["pool_size"] == 15
            assert node.config["max_pool_size"] == 30
            assert node.config["timeout"] == 45.0
            assert node.config["database_type"] == "postgresql"

        finally:
            os.unlink(temp_path)

    def test_config_file_overrides(self):
        """Test that explicit parameters override config file values."""
        config_data = {
            "databases": {
                "test": {
                    "connection_string": "postgresql://localhost/from_file",
                    "pool_size": 10,
                    "database_type": "postgresql",
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            node = AsyncSQLDatabaseNode(
                name="test_node",
                connection_name="test",
                config_file=temp_path,
                pool_size=20,  # Override file value
                query="SELECT 1",
            )

            # Explicit parameter should win
            assert node.config["pool_size"] == 20
            # File values should be used for non-overridden params
            assert (
                node.config["connection_string"] == "postgresql://localhost/from_file"
            )

        finally:
            os.unlink(temp_path)

    def test_missing_connection_name(self):
        """Test error when connection name not found in config."""
        config_data = {
            "databases": {
                "existing": {"connection_string": "postgresql://localhost/test"}
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            from kailash.sdk_exceptions import NodeConfigurationError

            with pytest.raises(
                NodeConfigurationError, match="Failed to load config 'nonexistent'"
            ):
                AsyncSQLDatabaseNode(
                    name="test_node",
                    connection_name="nonexistent",
                    config_file=temp_path,
                    query="SELECT 1",
                )
        finally:
            os.unlink(temp_path)

    def test_env_var_in_config_file(self):
        """Test environment variable substitution in config file."""
        config_data = {
            "databases": {
                "test": {
                    "connection_string": "${TEST_DB_URL}",
                    "database_type": "postgresql",
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            os.environ["TEST_DB_URL"] = (
                "postgresql://testuser:testpass@testhost:5432/testdb"
            )

            node = AsyncSQLDatabaseNode(
                name="test_node",
                connection_name="test",
                config_file=temp_path,
                query="SELECT 1",
            )

            assert (
                node.config["connection_string"]
                == "postgresql://testuser:testpass@testhost:5432/testdb"
            )

        finally:
            os.unlink(temp_path)
            os.environ.pop("TEST_DB_URL", None)
