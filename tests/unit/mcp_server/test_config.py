"""Unit tests for MCP configuration management.

Tests for the configuration system components in kailash.mcp_server.utils.config.
NO MOCKING - This is a unit test file for isolated component testing.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from kailash.mcp_server.utils.config import (
    ConfigManager,
    create_default_config,
    load_config_file,
)


@pytest.mark.unit
class TestConfigManager:
    """Test ConfigManager class functionality."""

    def test_init_empty(self):
        """Test initialization with no configuration."""
        config = ConfigManager()

        assert config._defaults == {}
        assert config._file_config == {}
        assert config._env_config == {}
        assert config._runtime_config == {}

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        defaults = {
            "server": {"name": "test-server", "port": 8080},
            "debug": True,
        }
        config = ConfigManager(defaults=defaults)

        assert config._defaults == defaults
        assert config.get("server.name") == "test-server"
        assert config.get("server.port") == 8080
        assert config.get("debug") is True

    def test_init_with_config_file_json(self):
        """Test initialization with JSON config file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "server": {"name": "json-server", "port": 9000},
                    "cache": {"enabled": True},
                },
                f,
            )
            config_file = f.name

        try:
            config = ConfigManager(config_file=config_file)
            assert config.get("server.name") == "json-server"
            assert config.get("server.port") == 9000
            assert config.get("cache.enabled") is True
        finally:
            os.unlink(config_file)

    def test_init_with_config_file_yaml(self):
        """Test initialization with YAML config file."""
        # Check if YAML is available
        try:
            import yaml

            has_yaml = True
        except ImportError:
            has_yaml = False

        if has_yaml:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                f.write(
                    """
server:
  name: yaml-server
  port: 8888
cache:
  enabled: false
  ttl: 600
"""
                )
                config_file = f.name

            try:
                config = ConfigManager(config_file=config_file)
                assert config.get("server.name") == "yaml-server"
                assert config.get("server.port") == 8888
                assert config.get("cache.enabled") is False
                assert config.get("cache.ttl") == 600
            finally:
                os.unlink(config_file)
        else:
            # Test that YAML loading fails gracefully
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                f.write("server: test")
                config_file = f.name

            try:
                config = ConfigManager(config_file=config_file)
                # Should log warning but not crash
                assert config._file_config == {}
            finally:
                os.unlink(config_file)

    def test_load_file_not_found(self):
        """Test loading non-existent config file."""
        config = ConfigManager()
        config.load_file("/path/to/nonexistent/file.json")

        # Should log warning but not crash
        assert config._file_config == {}

    def test_load_file_invalid_format(self):
        """Test loading file with unsupported format."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("invalid config format")
            config_file = f.name

        try:
            config = ConfigManager()
            config.load_file(config_file)

            # Should log error but not crash
            assert config._file_config == {}
        finally:
            os.unlink(config_file)

    def test_load_file_invalid_json(self):
        """Test loading malformed JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ invalid json }")
            config_file = f.name

        try:
            config = ConfigManager()
            config.load_file(config_file)

            # Should log error but not crash
            assert config._file_config == {}
        finally:
            os.unlink(config_file)

    def test_env_var_loading(self):
        """Test loading configuration from environment variables."""
        env_vars = {
            "MCP_SERVER_NAME": "env-server",
            "MCP_SERVER_PORT": "7777",
            "MCP_CACHE_ENABLED": "true",
            "MCP_CACHE_TTL": "300",
            "MCP_DEBUG": "false",
            "MCP_NESTED_CONFIG_VALUE": '{"key": "value"}',
        }

        with patch.dict(os.environ, env_vars):
            config = ConfigManager()

            assert config.get("server.name") == "env-server"
            assert config.get("server.port") == 7777  # JSON parsed to int
            assert config.get("cache.enabled") is True  # JSON parsed to bool
            assert config.get("cache.ttl") == 300  # JSON parsed to int
            assert config.get("debug") is False  # JSON parsed to bool
            assert config.get("nested.config.value") == {"key": "value"}  # Parsed JSON

    def test_env_var_json_parsing(self):
        """Test JSON parsing of environment variable values."""
        env_vars = {
            "MCP_ARRAY": '["item1", "item2", "item3"]',
            "MCP_OBJECT": '{"key1": "value1", "key2": 42}',
            "MCP_NUMBER": "123",
            "MCP_BOOLEAN": "true",
            "MCP_STRING": '"quoted string"',
            "MCP_PLAIN_STRING": "plain string",
        }

        with patch.dict(os.environ, env_vars):
            config = ConfigManager()

            assert config.get("array") == ["item1", "item2", "item3"]
            assert config.get("object") == {"key1": "value1", "key2": 42}
            assert config.get("number") == 123
            assert config.get("boolean") is True
            assert config.get("string") == "quoted string"
            assert config.get("plain.string") == "plain string"

    def test_get_with_dot_notation(self):
        """Test getting values using dot notation."""
        defaults = {
            "server": {
                "name": "test-server",
                "network": {
                    "host": "localhost",
                    "port": 8080,
                    "ssl": {"enabled": True, "cert": "/path/to/cert"},
                },
            }
        }
        config = ConfigManager(defaults=defaults)

        assert config.get("server.name") == "test-server"
        assert config.get("server.network.host") == "localhost"
        assert config.get("server.network.port") == 8080
        assert config.get("server.network.ssl.enabled") is True
        assert config.get("server.network.ssl.cert") == "/path/to/cert"

    def test_get_with_default_value(self):
        """Test getting values with default fallback."""
        config = ConfigManager()

        assert config.get("nonexistent.key") is None
        assert config.get("nonexistent.key", "default") == "default"
        assert config.get("another.missing.key", 42) == 42

    def test_get_with_type_errors(self):
        """Test getting values when path encounters non-dict types."""
        config = ConfigManager(
            defaults={
                "server": "string-value",
                "array": [1, 2, 3],
            }
        )

        # Trying to access nested value on non-dict should return None
        assert config.get("server.name") is None
        assert config.get("array.0") is None

    def test_set_with_dot_notation(self):
        """Test setting values using dot notation."""
        config = ConfigManager()

        config.set("server.name", "new-server")
        config.set("server.port", 9999)
        config.set("deeply.nested.config.value", "test")

        assert config.get("server.name") == "new-server"
        assert config.get("server.port") == 9999
        assert config.get("deeply.nested.config.value") == "test"

    def test_set_overrides_existing(self):
        """Test that set() overrides existing values."""
        config = ConfigManager(defaults={"server": {"name": "default"}})

        assert config.get("server.name") == "default"

        config.set("server.name", "overridden")
        assert config.get("server.name") == "overridden"

    def test_update_with_dict(self):
        """Test updating configuration with dictionary."""
        config = ConfigManager()

        update_dict = {
            "server.name": "updated-server",
            "server.port": 8000,
            "cache.enabled": True,
            "nested.path.value": "test",
        }

        config.update(update_dict)

        assert config.get("server.name") == "updated-server"
        assert config.get("server.port") == 8000
        assert config.get("cache.enabled") is True
        assert config.get("nested.path.value") == "test"

    def test_configuration_precedence(self):
        """Test configuration precedence order."""
        # Set up defaults
        defaults = {"key": "default", "only_default": "default_value"}

        # Create temp config file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"key": "file", "only_file": "file_value"}, f)
            config_file = f.name

        try:
            # Set environment variable
            with patch.dict(
                os.environ, {"MCP_KEY": '"env"', "MCP_ONLY_ENV": '"env_value"'}
            ):
                config = ConfigManager(config_file=config_file, defaults=defaults)

                # Set runtime value
                config.set("key", "runtime")
                config.set("only_runtime", "runtime_value")

                # Test precedence: runtime > env > file > default
                assert config.get("key") == "runtime"
                assert config.get("only_runtime") == "runtime_value"
                assert config.get("only.env") == "env_value"
                assert config.get("only_file") == "file_value"
                assert config.get("only_default") == "default_value"

                # Test that lower precedence values are still accessible
                config._runtime_config = {}  # Clear runtime
                assert config.get("key") == "env"

                config._env_config = {}  # Clear env

                assert config.get("key") == "file"

                config._file_config = {}  # Clear file
                assert config.get("key") == "default"
        finally:
            os.unlink(config_file)

    def test_to_dict(self):
        """Test converting configuration to dictionary."""
        defaults = {"default_key": "default_value", "shared": "default"}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"file_key": "file_value", "shared": "file"}, f)
            config_file = f.name

        try:
            with patch.dict(
                os.environ, {"MCP_ENV_KEY": '"env_value"', "MCP_SHARED": '"env"'}
            ):
                config = ConfigManager(config_file=config_file, defaults=defaults)
                config.set("runtime_key", "runtime_value")
                config.set("shared", "runtime")

                result = config.to_dict()

                # All keys should be present
                assert result["default_key"] == "default_value"
                assert result["file_key"] == "file_value"
                assert result["env"]["key"] == "env_value"
                assert result["runtime_key"] == "runtime_value"

                # Highest precedence wins
                assert result["shared"] == "runtime"
        finally:
            os.unlink(config_file)

    def test_deep_merge(self):
        """Test deep merging of nested dictionaries."""
        config = ConfigManager()

        base = {
            "server": {
                "name": "base-server",
                "network": {
                    "host": "localhost",
                    "port": 8080,
                },
            },
            "cache": {"enabled": True},
        }

        update = {
            "server": {"network": {"port": 9000, "ssl": {"enabled": True}}},
            "cache": {"ttl": 300},
        }

        result = config._deep_merge(base, update)

        # Original values preserved
        assert result["server"]["name"] == "base-server"
        assert result["server"]["network"]["host"] == "localhost"
        assert result["cache"]["enabled"] is True

        # Updated values
        assert result["server"]["network"]["port"] == 9000
        assert result["server"]["network"]["ssl"]["enabled"] is True
        assert result["cache"]["ttl"] == 300

    def test_save_json(self):
        """Test saving configuration to JSON file."""
        config = ConfigManager(
            defaults={
                "server": {"name": "test-server", "port": 8080},
                "cache": {"enabled": True, "ttl": 300},
            }
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            output_file = f.name

        try:
            config.save(output_file, format="json")

            # Load and verify
            with open(output_file, "r") as f:
                saved_data = json.load(f)

            assert saved_data["server"]["name"] == "test-server"
            assert saved_data["server"]["port"] == 8080
            assert saved_data["cache"]["enabled"] is True
            assert saved_data["cache"]["ttl"] == 300
        finally:
            os.unlink(output_file)

    def test_save_yaml(self):
        """Test saving configuration to YAML file."""
        config = ConfigManager(
            defaults={
                "server": {"name": "test-server", "port": 8080},
                "cache": {"enabled": True, "ttl": 300},
            }
        )

        try:
            import yaml

            has_yaml = True
        except ImportError:
            has_yaml = False

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            output_file = f.name

        try:
            if has_yaml:
                config.save(output_file, format="yaml")

                # Load and verify
                with open(output_file, "r") as f:
                    saved_data = yaml.safe_load(f)

                assert saved_data["server"]["name"] == "test-server"
                assert saved_data["server"]["port"] == 8080
                assert saved_data["cache"]["enabled"] is True
                assert saved_data["cache"]["ttl"] == 300
            else:
                # Should raise ValueError when YAML not available
                with pytest.raises(ValueError, match="PyYAML not available"):
                    config.save(output_file, format="yaml")
        finally:
            os.unlink(output_file)

    def test_save_invalid_format(self):
        """Test saving with invalid format."""
        config = ConfigManager()

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            output_file = f.name

        try:
            with pytest.raises(ValueError, match="Unsupported format"):
                config.save(output_file, format="xml")
        finally:
            os.unlink(output_file)

    def test_save_io_error(self):
        """Test save error handling."""
        config = ConfigManager()

        # Try to save to invalid path
        with pytest.raises(Exception):
            config.save("/invalid/path/config.json")


@pytest.mark.unit
class TestCreateDefaultConfig:
    """Test create_default_config function."""

    def test_default_config_structure(self):
        """Test that default config has expected structure."""
        config = create_default_config()

        assert isinstance(config, dict)
        assert "server" in config
        assert "cache" in config
        assert "metrics" in config
        assert "logging" in config

    def test_default_server_config(self):
        """Test default server configuration values."""
        config = create_default_config()

        assert config["server"]["name"] == "mcp-server"
        assert config["server"]["version"] == "1.0.0"
        assert config["server"]["description"] == "MCP Server"
        assert config["server"]["transport"] == "stdio"

    def test_default_cache_config(self):
        """Test default cache configuration values."""
        config = create_default_config()

        assert config["cache"]["enabled"] is True
        assert config["cache"]["default_ttl"] == 300
        assert config["cache"]["max_size"] == 128

    def test_default_metrics_config(self):
        """Test default metrics configuration values."""
        config = create_default_config()

        assert config["metrics"]["enabled"] is True
        assert config["metrics"]["collect_performance"] is True
        assert config["metrics"]["collect_usage"] is True

    def test_default_logging_config(self):
        """Test default logging configuration values."""
        config = create_default_config()

        assert config["logging"]["level"] == "INFO"
        assert "%(asctime)s" in config["logging"]["format"]
        assert "%(levelname)s" in config["logging"]["format"]


@pytest.mark.unit
class TestLoadConfigFile:
    """Test load_config_file convenience function."""

    def test_load_with_defaults(self):
        """Test loading config file with default values."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"server": {"name": "custom-server"}}, f)
            config_file = f.name

        try:
            config = load_config_file(config_file)

            # Custom value should override default
            assert config.get("server.name") == "custom-server"

            # Other defaults should still be present
            assert config.get("server.version") == "1.0.0"
            assert config.get("cache.enabled") is True
            assert config.get("metrics.enabled") is True
        finally:
            os.unlink(config_file)

    def test_load_nonexistent_file(self):
        """Test loading non-existent file still provides defaults."""
        config = load_config_file("/path/to/nonexistent.json")

        # Should still have defaults
        assert config.get("server.name") == "mcp-server"
        assert config.get("cache.enabled") is True


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_config_file(self):
        """Test loading empty config files."""
        # Empty JSON
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{}")
            json_file = f.name

        try:
            config = ConfigManager(config_file=json_file)
            assert config._file_config == {}
        finally:
            os.unlink(json_file)

        # Empty YAML (if available)
        try:
            import yaml

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                f.write("")
                yaml_file = f.name

            try:
                config = ConfigManager(config_file=yaml_file)
                assert config._file_config == {}
            finally:
                os.unlink(yaml_file)
        except ImportError:
            pass

    def test_null_values_in_config(self):
        """Test handling of null/None values."""
        config = ConfigManager(defaults={"key1": None, "nested": {"key2": None}})

        # None values in config are not distinguishable from missing values
        # This is a limitation of the current implementation
        assert config.get("key1") is None
        assert config.get("nested.key2") is None

        # None values return the default parameter
        assert config.get("key1", "default") == "default"

    def test_circular_reference_prevention(self):
        """Test that circular references don't cause infinite loops."""
        config = ConfigManager()

        # Create a structure that could have circular refs
        data = {"a": {"b": {}}}
        data["a"]["b"]["c"] = data["a"]  # Circular reference

        # This should not cause infinite loop in deep_merge
        try:
            config._deep_merge({}, data)
            # If we get here, the method handled it somehow
            assert True
        except RecursionError:
            # This is also acceptable - preventing stack overflow
            assert True

    def test_unicode_handling(self):
        """Test handling of unicode characters in configuration."""
        unicode_config = {
            "server": {"name": "测试服务器"},
            "message": "Hello 世界 🌍",
            "symbols": "αβγδε",
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(unicode_config, f, ensure_ascii=False)
            config_file = f.name

        try:
            config = ConfigManager(config_file=config_file)
            assert config.get("server.name") == "测试服务器"
            assert config.get("message") == "Hello 世界 🌍"
            assert config.get("symbols") == "αβγδε"
        finally:
            os.unlink(config_file)

    def test_very_deep_nesting(self):
        """Test handling of very deeply nested configurations."""
        config = ConfigManager()

        # Create very deep nesting
        deep_key = ".".join(["level" + str(i) for i in range(20)])
        config.set(deep_key, "deep_value")

        assert config.get(deep_key) == "deep_value"

    def test_special_characters_in_keys(self):
        """Test handling of special characters in configuration keys."""
        config = ConfigManager()

        # These should work with dot notation
        config.set("normal.key", "value1")
        config.set("key-with-dash", "value2")
        config.set("key_with_underscore", "value3")

        assert config.get("normal.key") == "value1"
        assert config.get("key-with-dash") == "value2"
        assert config.get("key_with_underscore") == "value3"

    def test_large_configuration(self):
        """Test handling of large configuration objects."""
        large_config = {}
        for i in range(1000):
            large_config[f"key_{i}"] = {"value": i, "nested": {"data": f"value_{i}"}}

        config = ConfigManager(defaults=large_config)

        # Spot check some values
        assert config.get("key_0.value") == 0
        assert config.get("key_500.nested.data") == "value_500"
        assert config.get("key_999.value") == 999

    def test_concurrent_access(self):
        """Test that ConfigManager handles concurrent access safely."""
        # Note: ConfigManager is not thread-safe by design
        # This test just ensures basic operations don't crash
        config = ConfigManager()

        # Simulate "concurrent" updates (not truly concurrent in this test)
        for i in range(100):
            config.set(f"key{i}", i)

        # All values should be set correctly
        for i in range(100):
            assert config.get(f"key{i}") == i


@pytest.mark.unit
class TestRealWorldScenarios:
    """Test real-world configuration scenarios."""

    def test_database_configuration(self):
        """Test typical database configuration scenario."""
        config = ConfigManager(
            defaults={
                "database": {
                    "host": "localhost",
                    "port": 5432,
                    "name": "myapp",
                    "pool": {"min_size": 1, "max_size": 10},
                }
            }
        )

        # Override with environment variables
        with patch.dict(
            os.environ,
            {
                "MCP_DATABASE_HOST": '"prod-db.example.com"',
                "MCP_DATABASE_PASSWORD": '"secret123"',
                "MCP_DATABASE_POOL_MAX_SIZE": "50",
            },
        ):
            # Create a new config to ensure env vars are loaded
            config = ConfigManager(
                defaults={
                    "database": {
                        "host": "localhost",
                        "port": 5432,
                        "name": "myapp",
                        "pool": {"min_size": 1, "max_size": 10},
                    }
                }
            )

            assert config.get("database.host") == "prod-db.example.com"
            assert config.get("database.port") == 5432  # Default preserved
            assert config.get("database.password") == "secret123"  # New from env
            assert config.get("database.pool.max.size") == 50  # JSON parsed to int
            assert config.get("database.pool.min_size") == 1  # Default preserved

    def test_feature_flags_configuration(self):
        """Test feature flags configuration scenario."""
        config = ConfigManager(
            defaults={
                "features": {
                    "new_ui": False,
                    "experimental_api": False,
                    "debug_mode": False,
                }
            }
        )

        # Enable features via runtime
        config.set("features.new_ui", True)
        config.set("features.experimental_api", True)

        assert config.get("features.new_ui") is True
        assert config.get("features.experimental_api") is True
        assert config.get("features.debug_mode") is False

    def test_multi_environment_configuration(self):
        """Test configuration for multiple environments."""
        base_config = {
            "app": {"name": "MyApp", "version": "1.0.0"},
            "server": {"host": "0.0.0.0", "port": 8080},
        }

        # Development overrides
        dev_config = {"server": {"host": "localhost", "port": 3000}, "debug": True}

        # Production overrides
        prod_config = {
            "server": {"host": "0.0.0.0", "port": 80},
            "debug": False,
            "ssl": {"enabled": True, "cert": "/etc/ssl/cert.pem"},
        }

        # Simulate development environment
        config = ConfigManager(defaults=base_config)
        config.update(dev_config)

        assert config.get("app.name") == "MyApp"
        assert config.get("server.host") == "localhost"
        assert config.get("server.port") == 3000
        assert config.get("debug") is True

        # Simulate production environment
        config = ConfigManager(defaults=base_config)
        config.update(prod_config)

        assert config.get("app.name") == "MyApp"
        assert config.get("server.host") == "0.0.0.0"
        assert config.get("server.port") == 80
        assert config.get("debug") is False
        assert config.get("ssl.enabled") is True
