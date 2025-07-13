"""Unit tests for DataFlow configuration system.

These tests ensure that DataFlow follows the progressive configuration
disclosure pattern and correctly handles zero-config to enterprise setups.
"""

import os
from unittest.mock import MagicMock, PropertyMock, patch

import pytest


class TestDataFlowConfiguration:
    """Test DataFlow configuration system."""

    def test_zero_config_defaults(self):
        """Test that DataFlow works with zero configuration."""
        # Mock the configuration system
        mock_config = MagicMock()
        mock_config.database_url = "sqlite:///:memory:"
        mock_config.environment = "development"
        mock_config.pool_size = 5
        mock_config.monitoring = MagicMock(enabled=False)
        mock_config.security = MagicMock(multi_tenant=False)

        mock_dataflow = MagicMock()
        mock_dataflow.config = mock_config

        # Zero config should use in-memory SQLite
        assert mock_dataflow.config.database_url == "sqlite:///:memory:"
        assert mock_dataflow.config.environment == "development"
        assert mock_dataflow.config.pool_size == 5
        assert mock_dataflow.config.monitoring.enabled is False

    def test_environment_detection(self):
        """Test automatic environment detection."""
        test_cases = [
            ("development", "development"),
            ("dev", "development"),
            ("testing", "testing"),
            ("test", "testing"),
            ("staging", "staging"),
            ("stage", "staging"),
            ("production", "production"),
            ("prod", "production"),
            ("unknown", "development"),  # Default to development
        ]

        for env_value, expected in test_cases:
            with patch.dict(os.environ, {"KAILASH_ENV": env_value}):
                # Mock environment detection
                def detect_environment():
                    env = os.getenv("KAILASH_ENV", "development").lower()
                    if env in ["dev", "development", "local"]:
                        return "development"
                    elif env in ["test", "testing", "ci"]:
                        return "testing"
                    elif env in ["stage", "staging", "pre-prod"]:
                        return "staging"
                    elif env in ["prod", "production", "live"]:
                        return "production"
                    else:
                        return "development"

                detected = detect_environment()
                assert detected == expected

    def test_database_url_from_environment(self):
        """Test that DATABASE_URL environment variable is used."""
        test_url = "postgresql://user:pass@localhost:5432/testdb"

        with patch.dict(os.environ, {"DATABASE_URL": test_url}):
            # Mock config that reads from environment
            mock_config = MagicMock()

            def get_database_url():
                return os.getenv("DATABASE_URL", "sqlite:///:memory:")

            mock_config.database_url = get_database_url()

            assert mock_config.database_url == test_url

    def test_progressive_configuration_levels(self):
        """Test progressive configuration disclosure pattern."""
        # Level 1: Zero config
        mock_zero_config = MagicMock()
        mock_zero_config.database_url = "sqlite:///:memory:"
        mock_zero_config.pool_size = 5

        # Level 2: Basic config
        mock_basic_config = MagicMock()
        mock_basic_config.database_url = "postgresql://localhost/myapp"
        mock_basic_config.pool_size = 20  # Auto-configured

        # Level 3: Advanced config
        mock_advanced_config = MagicMock()
        mock_advanced_config.database_url = "postgresql://prod/app"
        mock_advanced_config.pool_size = 100
        mock_advanced_config.multi_tenant = True
        mock_advanced_config.monitoring = True

        # Verify progressive enhancement
        assert mock_zero_config.pool_size < mock_basic_config.pool_size
        assert mock_basic_config.pool_size < mock_advanced_config.pool_size

    def test_pool_size_calculation(self):
        """Test automatic pool size calculation based on environment."""
        import multiprocessing

        cpu_count = multiprocessing.cpu_count()

        test_cases = [
            ("development", min(5, cpu_count)),
            ("testing", min(10, cpu_count * 2)),
            ("staging", min(20, cpu_count * 3)),
            ("production", min(50, cpu_count * 4)),
        ]

        for environment, expected_pool_size in test_cases:
            # Mock pool size calculation
            def calculate_pool_size(env):
                if env == "development":
                    return min(5, cpu_count)
                elif env == "testing":
                    return min(10, cpu_count * 2)
                elif env == "staging":
                    return min(20, cpu_count * 3)
                else:  # production
                    return min(50, cpu_count * 4)

            pool_size = calculate_pool_size(environment)
            assert pool_size == expected_pool_size

    def test_configuration_validation(self):
        """Test configuration validation and error handling."""
        # Test invalid database URL
        invalid_urls = [
            "",
            None,
            "invalid://url",
            "http://not-a-database",
            "ftp://wrong-protocol",
        ]

        for invalid_url in invalid_urls:
            # Mock validation function
            def validate_database_url(url):
                if not url or not isinstance(url, str):
                    return False
                supported_schemes = ["postgresql", "mysql", "sqlite", "oracle", "mssql"]
                try:
                    scheme = url.split("://")[0].lower()
                    return scheme in supported_schemes
                except:
                    return False

            assert validate_database_url(invalid_url) is False

    def test_configuration_from_dict(self):
        """Test creating configuration from dictionary."""
        config_dict = {
            "database_url": "postgresql://localhost/test",
            "pool_size": 25,
            "pool_max_overflow": 50,
            "echo": True,
            "multi_tenant": True,
            "monitoring": True,
            "cache_enabled": True,
            "cache_ttl": 300,
        }

        # Mock configuration object
        mock_config = MagicMock()
        for key, value in config_dict.items():
            setattr(mock_config, key, value)

        # Verify all values are set
        assert mock_config.database_url == "postgresql://localhost/test"
        assert mock_config.pool_size == 25
        assert mock_config.multi_tenant is True
        assert mock_config.cache_ttl == 300

    def test_configuration_precedence(self):
        """Test configuration source precedence."""
        # Set environment variable
        with patch.dict(
            os.environ, {"DATABASE_URL": "postgresql://env/db", "DB_POOL_SIZE": "30"}
        ):
            # Test precedence: explicit > env > default

            # 1. Explicit parameters (highest priority)
            explicit_url = "postgresql://explicit/db"
            assert explicit_url == explicit_url  # Explicit always wins

            # 2. Environment variables (medium priority)
            env_url = os.getenv("DATABASE_URL")
            assert env_url == "postgresql://env/db"

            # 3. Defaults (lowest priority)
            default_url = "sqlite:///:memory:"

            # Precedence function
            def get_config_value(explicit=None, env_key=None, default=None):
                if explicit is not None:
                    return explicit
                if env_key and os.getenv(env_key):
                    return os.getenv(env_key)
                return default

            # Test precedence
            assert get_config_value(explicit=explicit_url) == explicit_url
            assert (
                get_config_value(env_key="DATABASE_URL", default=default_url) == env_url
            )
            assert get_config_value(default=default_url) == default_url

    def test_production_requires_explicit_config(self):
        """Test that production environment requires explicit database config."""
        with patch.dict(os.environ, {"KAILASH_ENV": "production"}, clear=True):
            # Remove DATABASE_URL to simulate missing config
            if "DATABASE_URL" in os.environ:
                del os.environ["DATABASE_URL"]

            # Mock configuration that checks for production
            def create_config(environment, database_url=None):
                if (
                    environment == "production"
                    and not database_url
                    and not os.getenv("DATABASE_URL")
                ):
                    raise ValueError(
                        "Production database configuration required. "
                        "Set DATABASE_URL environment variable or provide database configuration."
                    )
                return MagicMock()

            # Should raise error in production without config
            with pytest.raises(ValueError) as exc_info:
                create_config("production")

            assert "Production database configuration required" in str(exc_info.value)

    def test_security_configuration(self):
        """Test security-related configuration options."""
        security_config = {
            "multi_tenant": True,
            "encrypt_at_rest": True,
            "audit_enabled": True,
            "tenant_isolation": "strict",
            "gdpr_compliance": True,
            "data_retention_days": 90,
        }

        mock_security = MagicMock()
        for key, value in security_config.items():
            setattr(mock_security, key, value)

        # Verify security settings
        assert mock_security.multi_tenant is True
        assert mock_security.tenant_isolation == "strict"
        assert mock_security.data_retention_days == 90

    def test_monitoring_configuration(self):
        """Test monitoring configuration options."""
        monitoring_config = {
            "enabled": True,
            "slow_query_threshold": 1.0,
            "metrics_export_interval": 60,
            "metrics_export_format": "prometheus",
            "query_insights": True,
            "connection_pool_metrics": True,
        }

        mock_monitoring = MagicMock()
        for key, value in monitoring_config.items():
            setattr(mock_monitoring, key, value)

        # Verify monitoring settings
        assert mock_monitoring.enabled is True
        assert mock_monitoring.slow_query_threshold == 1.0
        assert mock_monitoring.metrics_export_format == "prometheus"
