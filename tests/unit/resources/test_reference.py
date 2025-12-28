"""
Unit tests for Resource References.

Tests ResourceReference and helper functions for:
- JSON serialization/deserialization
- Reference creation helpers
- Validation
"""

import json

import pytest
from kailash.resources.reference import (
    ResourceReference,
    create_cache_reference,
    create_database_reference,
    create_http_client_reference,
    create_message_queue_reference,
)


class TestResourceReference:
    """Test ResourceReference functionality."""

    def test_basic_reference_creation(self):
        """Test basic reference creation."""
        ref = ResourceReference(
            type="database",
            config={"host": "localhost", "database": "test"},
            credentials_ref="db_creds",
        )

        assert ref.type == "database"
        assert ref.config == {"host": "localhost", "database": "test"}
        assert ref.credentials_ref == "db_creds"
        assert ref.name is None

    def test_named_reference_creation(self):
        """Test named reference creation."""
        ref = ResourceReference(type="registered", config={}, name="main_db")

        assert ref.type == "registered"
        assert ref.config == {}
        assert ref.name == "main_db"
        assert ref.credentials_ref is None

    def test_to_dict(self):
        """Test conversion to dictionary."""
        ref = ResourceReference(
            type="database",
            config={"host": "localhost", "port": 5432},
            credentials_ref="db_creds",
            name="test_db",
        )

        data = ref.to_dict()
        expected = {
            "type": "database",
            "config": {"host": "localhost", "port": 5432},
            "credentials_ref": "db_creds",
            "name": "test_db",
        }

        assert data == expected

    def test_to_dict_minimal(self):
        """Test conversion to dictionary with minimal data."""
        ref = ResourceReference(type="cache", config={"backend": "memory"})

        data = ref.to_dict()
        expected = {"type": "cache", "config": {"backend": "memory"}}

        assert data == expected
        assert "credentials_ref" not in data
        assert "name" not in data

    def test_to_json(self):
        """Test JSON serialization."""
        ref = ResourceReference(
            type="http_client",
            config={"base_url": "https://api.example.com"},
            credentials_ref="api_key",
        )

        json_str = ref.to_json()
        data = json.loads(json_str)

        expected = {
            "type": "http_client",
            "config": {"base_url": "https://api.example.com"},
            "credentials_ref": "api_key",
        }

        assert data == expected

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "type": "database",
            "config": {"host": "localhost", "database": "test"},
            "credentials_ref": "db_creds",
        }

        ref = ResourceReference.from_dict(data)

        assert ref.type == "database"
        assert ref.config == {"host": "localhost", "database": "test"}
        assert ref.credentials_ref == "db_creds"
        assert ref.name is None

    def test_from_dict_minimal(self):
        """Test creation from minimal dictionary."""
        data = {"type": "cache", "config": {"backend": "memory"}}

        ref = ResourceReference.from_dict(data)

        assert ref.type == "cache"
        assert ref.config == {"backend": "memory"}
        assert ref.credentials_ref is None
        assert ref.name is None

    def test_from_json(self):
        """Test creation from JSON string."""
        json_data = {
            "type": "message_queue",
            "config": {"backend": "rabbitmq", "host": "localhost"},
            "credentials_ref": "mq_creds",
            "name": "main_queue",
        }
        json_str = json.dumps(json_data)

        ref = ResourceReference.from_json(json_str)

        assert ref.type == "message_queue"
        assert ref.config == {"backend": "rabbitmq", "host": "localhost"}
        assert ref.credentials_ref == "mq_creds"
        assert ref.name == "main_queue"

    def test_for_registered_resource(self):
        """Test shorthand for registered resources."""
        ref = ResourceReference.for_registered_resource("main_db")

        assert ref.type == "registered"
        assert ref.config == {}
        assert ref.name == "main_db"
        assert ref.credentials_ref is None

    def test_roundtrip_serialization(self):
        """Test round-trip serialization."""
        original = ResourceReference(
            type="database",
            config={
                "backend": "postgresql",
                "host": "db.example.com",
                "port": 5432,
                "database": "production",
            },
            credentials_ref="prod_db_creds",
        )

        # Convert to JSON and back
        json_str = original.to_json()
        restored = ResourceReference.from_json(json_str)

        assert restored.type == original.type
        assert restored.config == original.config
        assert restored.credentials_ref == original.credentials_ref
        assert restored.name == original.name


class TestReferenceHelpers:
    """Test reference creation helper functions."""

    def test_create_database_reference(self):
        """Test database reference helper."""
        ref = create_database_reference(
            host="db.example.com",
            database="myapp",
            backend="postgresql",
            port=5433,
            credentials_ref="db_creds",
            ssl_mode="require",
        )

        assert ref.type == "database"
        assert ref.config["backend"] == "postgresql"
        assert ref.config["host"] == "db.example.com"
        assert ref.config["database"] == "myapp"
        assert ref.config["port"] == 5433
        assert ref.config["ssl_mode"] == "require"
        assert ref.credentials_ref == "db_creds"

    def test_create_database_reference_defaults(self):
        """Test database reference with defaults."""
        ref = create_database_reference(host="localhost", database="test")

        assert ref.type == "database"
        assert ref.config["backend"] == "postgresql"
        assert ref.config["host"] == "localhost"
        assert ref.config["database"] == "test"
        assert "port" not in ref.config  # Should not include None port
        assert ref.credentials_ref is None

    def test_create_http_client_reference(self):
        """Test HTTP client reference helper."""
        ref = create_http_client_reference(
            base_url="https://api.example.com",
            backend="httpx",
            timeout=60,
            credentials_ref="api_key",
            headers={"User-Agent": "MyApp/1.0"},
            verify_ssl=False,
        )

        assert ref.type == "http_client"
        assert ref.config["backend"] == "httpx"
        assert ref.config["base_url"] == "https://api.example.com"
        assert ref.config["timeout"] == 60
        assert ref.config["headers"] == {"User-Agent": "MyApp/1.0"}
        assert ref.config["verify_ssl"] is False
        assert ref.credentials_ref == "api_key"

    def test_create_http_client_reference_defaults(self):
        """Test HTTP client reference with defaults."""
        ref = create_http_client_reference(base_url="https://api.example.com")

        assert ref.type == "http_client"
        assert ref.config["backend"] == "aiohttp"
        assert ref.config["base_url"] == "https://api.example.com"
        assert ref.config["timeout"] == 30
        assert ref.credentials_ref is None

    def test_create_cache_reference(self):
        """Test cache reference helper."""
        ref = create_cache_reference(
            backend="redis",
            host="cache.example.com",
            port=6380,
            db=1,
            max_connections=20,
        )

        assert ref.type == "cache"
        assert ref.config["backend"] == "redis"
        assert ref.config["host"] == "cache.example.com"
        assert ref.config["port"] == 6380
        assert ref.config["db"] == 1
        assert ref.config["max_connections"] == 20

    def test_create_cache_reference_defaults(self):
        """Test cache reference with defaults."""
        ref = create_cache_reference()

        assert ref.type == "cache"
        assert ref.config["backend"] == "redis"
        assert ref.config["host"] == "localhost"
        assert "port" not in ref.config  # Should not include None port

    def test_create_message_queue_reference(self):
        """Test message queue reference helper."""
        ref = create_message_queue_reference(
            backend="rabbitmq",
            host="mq.example.com",
            port=5673,
            credentials_ref="mq_creds",
            virtual_host="/myapp",
            heartbeat=60,
        )

        assert ref.type == "message_queue"
        assert ref.config["backend"] == "rabbitmq"
        assert ref.config["host"] == "mq.example.com"
        assert ref.config["port"] == 5673
        assert ref.config["virtual_host"] == "/myapp"
        assert ref.config["heartbeat"] == 60
        assert ref.credentials_ref == "mq_creds"

    def test_create_message_queue_reference_defaults(self):
        """Test message queue reference with defaults."""
        ref = create_message_queue_reference(backend="kafka")

        assert ref.type == "message_queue"
        assert ref.config["backend"] == "kafka"
        assert ref.config["host"] == "localhost"
        assert "port" not in ref.config  # Should not include None port
        assert ref.credentials_ref is None
