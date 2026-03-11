#!/usr/bin/env python3
"""
Integration test for Model Registry with proper migration system initialization.
Tests Bug 007 fix with real PostgreSQL infrastructure.
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest

# Add source paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "src"))

from dataflow.core.engine import DataFlow
from dataflow.core.model_registry import ModelRegistry


@pytest.fixture
def test_database_url():
    """Get test database URL from environment or use default."""
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://dataflow_test:dataflow_test_password@localhost:5434/dataflow_test",
    )


@pytest.fixture
def ensure_migration_system(test_database_url):
    """Ensure migration tables exist before running tests."""
    # Create a DataFlow instance with auto_migrate=True and migration_enabled=True
    # This will trigger migration table creation
    dataflow = DataFlow(
        database_url=test_database_url,
        auto_migrate=True,
        migration_enabled=True,
        enable_model_persistence=True,
    )

    @dataflow.model
    class DummyModel:
        id: int
        name: str

    # Create tables including migration tables
    dataflow.create_tables()

    yield dataflow

    # Cleanup is handled by the test framework


@pytest.mark.integration
@pytest.mark.timeout(10)
class TestModelRegistryIntegration:
    """Test model registry with real PostgreSQL database."""

    def test_model_registry_initialization(
        self, test_database_url, ensure_migration_system
    ):
        """Test that model registry initializes with migration tables."""
        # Create DataFlow instance
        dataflow = DataFlow(database_url=test_database_url, auto_migrate=True)

        # Create model registry
        registry = ModelRegistry(dataflow)

        # Initialize should succeed now that migration tables exist
        success = registry.initialize()
        assert success is True
        assert registry._initialized is True

    def test_register_and_discover_models(
        self, test_database_url, ensure_migration_system
    ):
        """Test registering and discovering models."""
        # Create DataFlow instance
        dataflow = DataFlow(database_url=test_database_url, auto_migrate=True)
        registry = ModelRegistry(dataflow)

        # Initialize registry
        assert registry.initialize() is True

        # Register a test model
        model_name = "TestUser"
        fields = {
            "id": {"type": "int", "primary_key": True},
            "name": {"type": "str", "required": True},
            "email": {"type": "str", "unique": True},
            "active": {"type": "bool", "default": True},
        }
        options = {"multi_tenant": True}

        # Register model
        success = registry.register_model(model_name, fields, options)
        assert success is True

        # Discover models
        discovered = registry.discover_models()
        assert model_name in discovered
        assert discovered[model_name]["fields"]["name"]["type"] == "str"
        assert discovered[model_name]["options"]["multi_tenant"] is True

    def test_multi_application_sync(self, test_database_url, ensure_migration_system):
        """Test multi-application model synchronization - Bug 007 fix."""
        # App 1: Register models
        dataflow1 = DataFlow(database_url=test_database_url, auto_migrate=True)
        registry1 = ModelRegistry(dataflow1)
        registry1.initialize()

        # Define models in App 1
        user_fields = {
            "id": {"type": "int", "primary_key": True},
            "username": {"type": "str", "required": True},
            "email": {"type": "str", "unique": True},
        }

        project_fields = {
            "id": {"type": "int", "primary_key": True},
            "name": {"type": "str", "required": True},
            "owner_id": {"type": "int", "foreign_key": "users.id"},
        }

        # Register models
        assert registry1.register_model("User", user_fields, {}) is True
        assert (
            registry1.register_model("Project", project_fields, {"timestamps": True})
            is True
        )

        # App 2: Discover and sync models
        dataflow2 = DataFlow(database_url=test_database_url, auto_migrate=True)
        registry2 = ModelRegistry(dataflow2)
        registry2.initialize()

        # Discover models from App 1
        discovered = registry2.discover_models()
        assert "User" in discovered
        assert "Project" in discovered

        # Sync models to App 2
        added, updated = registry2.sync_models()
        assert added >= 2  # At least User and Project

        # Verify models are available in App 2's DataFlow instance
        assert "User" in dataflow2._models
        assert "Project" in dataflow2._models

    def test_model_evolution_tracking(self, test_database_url, ensure_migration_system):
        """Test model version tracking and evolution."""
        dataflow = DataFlow(database_url=test_database_url, auto_migrate=True)
        registry = ModelRegistry(dataflow)
        registry.initialize()

        model_name = "EvolvingModel"

        # Version 1: Basic model
        v1_fields = {
            "id": {"type": "int", "primary_key": True},
            "name": {"type": "str"},
        }
        registry.register_model(model_name, v1_fields, {})

        # Check version
        version = registry.get_model_version(model_name)
        assert version == 1

        # Version 2: Add field
        v2_fields = {
            "id": {"type": "int", "primary_key": True},
            "name": {"type": "str"},
            "description": {"type": "str", "nullable": True},
        }
        registry.register_model(model_name, v2_fields, {})

        # Version should increase
        version = registry.get_model_version(model_name)
        assert version == 2

        # Get history
        history = registry.get_model_history(model_name)
        assert len(history) == 2

        # Verify different checksums
        checksums = [h["checksum"] for h in history]
        assert len(set(checksums)) == 2  # All unique

    def test_consistency_validation(self, test_database_url, ensure_migration_system):
        """Test cross-application consistency validation."""
        # App 1 with specific environment
        dataflow1 = DataFlow(database_url=test_database_url, auto_migrate=True)
        dataflow1.config.environment = "app1"
        registry1 = ModelRegistry(dataflow1)
        registry1.initialize()

        # App 2 with different environment
        dataflow2 = DataFlow(database_url=test_database_url, auto_migrate=True)
        dataflow2.config.environment = "app2"
        registry2 = ModelRegistry(dataflow2)
        registry2.initialize()

        # Both register same model with same definition
        model_name = "SharedModel"
        fields = {
            "id": {"type": "int", "primary_key": True},
            "name": {"type": "str", "required": True},
        }

        registry1.register_model(model_name, fields, {})
        registry2.register_model(model_name, fields, {})

        # Consistency check should pass
        issues = registry1.validate_consistency()

        # Since both have same definition, no issues
        if model_name in issues:
            # If there are issues, they should be about application differences, not schema
            assert "application" in str(issues[model_name])

    def test_model_reconstruction_with_complex_types(
        self, test_database_url, ensure_migration_system
    ):
        """Test model reconstruction with various field types."""
        dataflow1 = DataFlow(database_url=test_database_url, auto_migrate=True)
        registry1 = ModelRegistry(dataflow1)
        registry1.initialize()

        # Register complex model
        model_name = "ComplexModel"
        fields = {
            "id": {"type": "int", "primary_key": True},
            "name": {"type": "str", "required": True},
            "price": {"type": "float", "default": 0.0},
            "active": {"type": "bool", "default": True},
            "metadata": {"type": "json", "default": {}},
            "tags": {"type": "jsonb", "default": []},
            "created_at": {"type": "datetime", "auto_now_add": True},
        }
        options = {"multi_tenant": True, "soft_delete": True}

        success = registry1.register_model(model_name, fields, options)
        assert success is True

        # Create new DataFlow instance and sync
        dataflow2 = DataFlow(database_url=test_database_url, auto_migrate=True)
        registry2 = ModelRegistry(dataflow2)
        registry2.initialize()

        # Sync models
        added, updated = registry2.sync_models()
        assert added >= 1

        # Verify model reconstructed correctly
        assert model_name in dataflow2._models

        # Check model class has correct attributes
        model_class = dataflow2._models[model_name]
        assert hasattr(model_class, "__annotations__")
        assert model_class.__annotations__["name"] == str
        assert model_class.__annotations__["price"] == float
        assert model_class.__annotations__["active"] == bool

    def test_transaction_safety(self, test_database_url, ensure_migration_system):
        """Test transaction safety of registry operations."""
        dataflow = DataFlow(database_url=test_database_url, auto_migrate=True)
        registry = ModelRegistry(dataflow)
        registry.initialize()

        # Test concurrent registration attempts
        model_name = "ConcurrentModel"
        fields = {"id": {"type": "int"}, "name": {"type": "str"}}

        # Multiple registration attempts should be safe
        results = []
        for _ in range(3):
            success = registry.register_model(model_name, fields, {})
            results.append(success)

        # All should succeed (idempotent)
        assert all(results)

        # But version should be 1 (no duplicates)
        version = registry.get_model_version(model_name)
        assert version == 1


if __name__ == "__main__":
    # Run with real PostgreSQL on port 5434
    pytest.main([__file__, "-v", "-s", "--tb=short"])
