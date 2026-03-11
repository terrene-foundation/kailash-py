#!/usr/bin/env python3
"""
Correct DataFlow Initialization Pattern for Tests

This example demonstrates the proper way to initialize DataFlow for integration tests,
ensuring that migration tables are created before using the ModelRegistry.
"""

import asyncio

import pytest
from dataflow.core.config import DatabaseConfig, DataFlowConfig
from dataflow.core.engine import DataFlow
from dataflow.core.models import Environment


def correct_dataflow_initialization_pattern():
    """Demonstrates the correct DataFlow initialization sequence."""

    # Test database URL (replace with your actual test database)
    test_database_url = (
        "postgresql://dataflow_test:dataflow_test_password@localhost:5433/dataflow_test"
    )

    # Method 1: Using structured config (RECOMMENDED)
    config = DataFlowConfig(
        database=DatabaseConfig(url=test_database_url), environment=Environment.TESTING
    )

    # Initialize DataFlow with migration system enabled
    dataflow = DataFlow(
        config=config,
        auto_migrate=True,  # Enable auto-migration
        migration_enabled=True,  # Enable migration system
        enable_model_persistence=True,  # Enable model registry
    )

    # Register a model to trigger migration system initialization
    @dataflow.model
    class TestUser:
        id: int
        name: str
        email: str

    # Ensure model registry is initialized
    if hasattr(dataflow, "_model_registry"):
        success = dataflow._model_registry.initialize()
        print(f"Model registry initialized: {success}")

    return dataflow


def alternative_initialization_pattern():
    """Alternative pattern using direct database_url."""

    test_database_url = (
        "postgresql://dataflow_test:dataflow_test_password@localhost:5433/dataflow_test"
    )

    # Method 2: Direct database_url initialization
    dataflow = DataFlow(
        database_url=test_database_url,
        auto_migrate=True,
        migration_enabled=True,
        enable_model_persistence=True,
    )

    # Register a dummy model to ensure tables are created
    @dataflow.model
    class DummyModel:
        id: int
        name: str

    # Initialize registry explicitly
    if hasattr(dataflow, "_model_registry"):
        dataflow._model_registry.initialize()

    return dataflow


@pytest.fixture
async def proper_dataflow_fixture(test_database_url):
    """Proper fixture for DataFlow initialization in tests."""

    # Create config
    config = DataFlowConfig(
        database=DatabaseConfig(url=test_database_url), environment=Environment.TESTING
    )

    # Initialize DataFlow
    dataflow = DataFlow(config=config, auto_migrate=True, migration_enabled=True)

    # Register initialization model to create migration tables
    @dataflow.model
    class InitModel:
        id: int
        name: str

    # Initialize model registry
    if hasattr(dataflow, "_model_registry"):
        dataflow._model_registry.initialize()

    yield dataflow

    # Cleanup can be added here if needed


# Example test using the proper pattern
@pytest.mark.asyncio
async def test_with_proper_initialization(proper_dataflow_fixture):
    """Example test using properly initialized DataFlow."""
    dataflow = proper_dataflow_fixture

    # Now you can safely use the model registry
    registry = dataflow._model_registry

    # Register a test model
    model_name = "TestModel"
    fields = {
        "id": {"type": "int", "primary_key": True},
        "name": {"type": "str", "required": True},
    }

    success = registry.register_model(model_name, fields, {})
    assert success is True

    # Verify model is discoverable
    discovered = registry.discover_models()
    assert model_name in discovered


if __name__ == "__main__":
    print("Testing DataFlow initialization patterns...")

    # Test correct initialization
    try:
        dataflow1 = correct_dataflow_initialization_pattern()
        print("✅ Method 1 (structured config): SUCCESS")
    except Exception as e:
        print(f"❌ Method 1 failed: {e}")

    try:
        dataflow2 = alternative_initialization_pattern()
        print("✅ Method 2 (direct database_url): SUCCESS")
    except Exception as e:
        print(f"❌ Method 2 failed: {e}")
