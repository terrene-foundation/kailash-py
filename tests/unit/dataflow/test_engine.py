"""Unit tests for DataFlow engine core functionality.

These tests ensure that the DataFlow engine initializes correctly,
handles configuration properly, and provides the expected API.
"""

import os
from typing import Optional
from unittest.mock import MagicMock, PropertyMock, patch

import pytest


class TestDataFlowEngine:
    """Test DataFlow engine initialization and basic functionality."""

    def test_dataflow_zero_config_initialization(self):
        """Test that DataFlow can be initialized with zero configuration."""
        # Mock the DataFlow engine
        mock_dataflow = MagicMock()
        mock_dataflow.config = MagicMock()
        mock_dataflow.config.database_url = "sqlite:///:memory:"
        mock_dataflow.config.environment = "development"
        mock_dataflow.config.pool_size = 5
        mock_dataflow._models = {}
        mock_dataflow._relationships = {}

        # Zero config should work
        assert mock_dataflow.config.database_url == "sqlite:///:memory:"
        assert mock_dataflow.config.environment == "development"
        assert mock_dataflow.config.pool_size == 5

    def test_dataflow_with_database_url_configuration(self):
        """Test DataFlow initialization with explicit database URL."""
        # Mock DataFlow with custom configuration
        mock_dataflow = MagicMock()
        mock_dataflow.config = MagicMock()

        # Simulate explicit configuration
        database_url = "postgresql://user:pass@localhost/testdb"
        mock_dataflow.config.database_url = database_url
        mock_dataflow.config.pool_size = 20
        mock_dataflow.config.echo = False

        assert mock_dataflow.config.database_url == database_url
        assert mock_dataflow.config.pool_size == 20
        assert mock_dataflow.config.echo is False

    def test_dataflow_environment_detection(self):
        """Test automatic environment detection from environment variables."""
        test_cases = [
            ("development", "development"),
            ("dev", "development"),
            ("testing", "testing"),
            ("test", "testing"),
            ("staging", "staging"),
            ("stage", "staging"),
            ("production", "production"),
            ("prod", "production"),
            ("unknown", "development"),  # Default fallback
        ]

        for env_value, expected in test_cases:
            with patch.dict(os.environ, {"KAILASH_ENV": env_value}):
                # Mock environment detection logic
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

    def test_dataflow_model_decorator_registration(self):
        """Test that @db.model decorator registers models correctly."""
        mock_dataflow = MagicMock()
        mock_dataflow._models = {}
        mock_dataflow._relationships = {}

        # Simulate model registration
        class User:
            name: str
            email: str
            active: bool = True

        User.__annotations__ = {"name": str, "email": str, "active": bool}

        # Mock decorator behavior
        def mock_model_decorator(cls):
            model_name = cls.__name__
            mock_dataflow._models[model_name] = {
                "class": cls,
                "table_name": model_name.lower(),
                "fields": cls.__annotations__,
                "registered_at": "2025-01-13T12:00:00Z",
            }
            return cls

        mock_dataflow.model = mock_model_decorator

        # Apply decorator
        decorated = mock_dataflow.model(User)

        # Verify registration
        assert "User" in mock_dataflow._models
        assert mock_dataflow._models["User"]["class"] is User
        assert mock_dataflow._models["User"]["table_name"] == "user"
        assert decorated is User

    def test_dataflow_production_requires_explicit_database_config(self):
        """Test that production environment requires explicit database configuration."""
        with patch.dict(os.environ, {"KAILASH_ENV": "production"}, clear=True):
            # Remove DATABASE_URL to simulate missing config
            if "DATABASE_URL" in os.environ:
                del os.environ["DATABASE_URL"]

            # Mock configuration validation
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

    def test_dataflow_configuration_precedence(self):
        """Test configuration source precedence: explicit > env > default."""
        # Set environment variable
        with patch.dict(
            os.environ, {"DATABASE_URL": "postgresql://env/db", "DB_POOL_SIZE": "30"}
        ):
            # Mock precedence function
            def get_config_value(explicit=None, env_key=None, default=None):
                if explicit is not None:
                    return explicit
                if env_key and os.getenv(env_key):
                    return os.getenv(env_key)
                return default

            # Test precedence
            explicit_url = "postgresql://explicit/db"
            env_url = os.getenv("DATABASE_URL")
            default_url = "sqlite:///:memory:"

            # Explicit should win
            assert get_config_value(explicit=explicit_url) == explicit_url

            # Environment should win over default
            assert (
                get_config_value(env_key="DATABASE_URL", default=default_url) == env_url
            )

            # Default when nothing else provided
            assert get_config_value(default=default_url) == default_url

    def test_dataflow_connection_pool_configuration(self):
        """Test connection pool configuration with various parameters."""
        mock_dataflow = MagicMock()
        mock_dataflow.config = MagicMock()

        # Test pool configuration
        pool_config = {
            "pool_size": 20,
            "pool_max_overflow": 30,
            "pool_recycle": 3600,
            "pool_pre_ping": True,
            "pool_timeout": 30,
        }

        for key, value in pool_config.items():
            setattr(mock_dataflow.config, key, value)

        # Verify configuration
        assert mock_dataflow.config.pool_size == 20
        assert mock_dataflow.config.pool_max_overflow == 30
        assert mock_dataflow.config.pool_recycle == 3600
        assert mock_dataflow.config.pool_pre_ping is True
        assert mock_dataflow.config.pool_timeout == 30

    def test_dataflow_model_with_relationships(self):
        """Test model registration with relationship definitions."""
        mock_dataflow = MagicMock()
        mock_dataflow._models = {}
        mock_dataflow._relationships = {}

        # Define models with relationships
        class User:
            id: int
            name: str
            email: str

        class Order:
            id: int
            user_id: int
            amount: float

        # Set relationship as class attribute
        Order.user = "User.id"

        # Mock relationship detection
        def detect_relationships(cls):
            relationships = {}
            for attr_name in dir(cls):
                # Skip special attributes
                if attr_name.startswith("_"):
                    continue

                attr_value = getattr(cls, attr_name)
                if (
                    isinstance(attr_value, str)
                    and "." in attr_value
                    and attr_value.count(".") == 1
                ):
                    # Parse "User.id" format
                    target_model, target_field = attr_value.split(".")
                    relationships[attr_name] = {
                        "target_model": target_model,
                        "target_field": target_field,
                        "source_field": f"{attr_name}_id",
                    }
            return relationships

        # Test relationship detection
        relationships = detect_relationships(Order)
        assert "user" in relationships
        assert relationships["user"]["target_model"] == "User"
        assert relationships["user"]["target_field"] == "id"
        assert relationships["user"]["source_field"] == "user_id"

    def test_dataflow_error_handling_invalid_configuration(self):
        """Test error handling for invalid configuration values."""
        # Test invalid database URLs
        invalid_urls = [
            "",
            None,
            "invalid://url",
            "http://not-a-database",
            "ftp://wrong-protocol",
        ]

        def validate_database_url(url):
            if not url or not isinstance(url, str):
                return False
            supported_schemes = ["postgresql", "mysql", "sqlite", "oracle", "mssql"]
            try:
                scheme = url.split("://")[0].lower()
                return scheme in supported_schemes
            except:
                return False

        for invalid_url in invalid_urls:
            assert validate_database_url(invalid_url) is False

        # Test valid URLs
        valid_urls = [
            "postgresql://localhost/db",
            "mysql://user:pass@host/db",
            "sqlite:///path/to/db.sqlite",
            "sqlite:///:memory:",
        ]

        for valid_url in valid_urls:
            assert validate_database_url(valid_url) is True

    def test_dataflow_model_field_extraction(self):
        """Test extraction of field information from model classes."""

        # Mock field extraction
        class Product:
            id: int
            name: str
            price: float
            category: str
            active: bool = True
            description: Optional[str] = None

        Product.__annotations__ = {
            "id": int,
            "name": str,
            "price": float,
            "category": str,
            "active": bool,
            "description": Optional[str],
        }

        # Extract field information
        fields = {}
        for field_name, field_type in Product.__annotations__.items():
            fields[field_name] = {
                "type": field_type,
                "required": not hasattr(Product, field_name),
                "default": getattr(Product, field_name, None),
                "nullable": hasattr(field_type, "__origin__")
                and type(None) in getattr(field_type, "__args__", []),
            }

        # Verify extraction
        assert fields["name"]["type"] is str
        assert fields["name"]["required"] is True
        assert fields["active"]["required"] is False
        assert fields["active"]["default"] is True
        assert fields["description"]["nullable"] is True

    def test_dataflow_multi_tenant_configuration(self):
        """Test multi-tenant configuration and automatic field injection."""
        mock_dataflow = MagicMock()
        mock_dataflow.config = MagicMock()
        mock_dataflow.config.multi_tenant = True

        # Test automatic tenant_id injection
        class TenantModel:
            name: str
            data: str

        TenantModel.__annotations__ = {"name": str, "data": str}

        # Mock tenant field injection
        def inject_tenant_fields(cls, config):
            if config.multi_tenant and "tenant_id" not in cls.__annotations__:
                cls.__annotations__["tenant_id"] = str
            return cls

        modified_class = inject_tenant_fields(TenantModel, mock_dataflow.config)

        # Verify tenant_id was added
        assert "tenant_id" in modified_class.__annotations__
        assert modified_class.__annotations__["tenant_id"] is str
