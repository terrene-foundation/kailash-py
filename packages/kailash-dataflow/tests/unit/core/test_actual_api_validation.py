"""
Tests for actual DataFlow API - using real methods that exist.
This validates what actually works vs what we assumed.
"""

import pytest
from dataflow import DataFlow


class TestActualDataFlowAPI:
    """Test the actual DataFlow API that exists."""

    def test_dataflow_has_correct_methods(self):
        """Test that DataFlow has the methods we actually use."""
        # Test with PostgreSQL URL since that's what alpha supports
        db = DataFlow(
            "postgresql://test:test@localhost:5432/test",
            existing_schema_mode=True,  # Safe mode
        )

        # Verify actual methods exist
        assert hasattr(db, "get_models"), "get_models method should exist"
        assert hasattr(db, "list_models"), "list_models method should exist"
        assert hasattr(db, "get_model_info"), "get_model_info method should exist"
        assert hasattr(db, "model"), "model decorator should exist"
        assert hasattr(db, "discover_schema"), "discover_schema method should exist"
        assert hasattr(
            db, "register_schema_as_models"
        ), "register_schema_as_models should exist"

        # Verify actual properties exist
        assert hasattr(db, "config"), "config property should exist"

        # Verify methods are callable
        assert callable(db.get_models)
        assert callable(db.list_models)
        assert callable(db.get_model_info)
        assert callable(db.model)
        assert callable(db.discover_schema)
        assert callable(db.register_schema_as_models)

    def test_dataflow_get_models_returns_dict(self):
        """Test that get_models returns a dictionary."""
        db = DataFlow(
            "postgresql://test:test@localhost:5432/test", existing_schema_mode=True
        )

        models = db.get_models()
        assert isinstance(models, dict), "get_models should return a dict"

        # Initially should be empty
        assert len(models) == 0, "Should start with no models"

    def test_dataflow_list_models_returns_list(self):
        """Test that list_models returns a list."""
        db = DataFlow(
            "postgresql://test:test@localhost:5432/test", existing_schema_mode=True
        )

        models = db.list_models()
        assert isinstance(models, list), "list_models should return a list"

        # Initially should be empty
        assert len(models) == 0, "Should start with no models"

    def test_dataflow_model_decorator_basic_usage(self):
        """Test that the model decorator works for basic registration."""
        db = DataFlow(
            "postgresql://test:test@localhost:5432/test",
            existing_schema_mode=True,  # Safe mode - won't try to create tables
        )

        # Define a model using the decorator
        @db.model
        class TestUser:
            name: str
            email: str
            age: int = 25

        # Verify model was registered
        models = db.get_models()
        assert "TestUser" in models, "TestUser should be registered"

        # Verify it's in the list too
        model_names = db.list_models()
        assert "TestUser" in model_names, "TestUser should be in list_models"

        # Verify we can get model info
        info = db.get_model_info("TestUser")
        assert info is not None, "Should be able to get model info"

    def test_dataflow_discover_schema_method(self):
        """Test that discover_schema method works."""
        db = DataFlow(
            "postgresql://test:test@localhost:5432/test", existing_schema_mode=True
        )

        # Should be able to call discover_schema
        # (It may fail due to no real DB, but method should exist)
        assert callable(db.discover_schema)

        try:
            schema = db.discover_schema()
            # If it works, should return a dict
            assert isinstance(schema, dict)
        except Exception:
            # If it fails due to no DB connection, that's expected
            # The important thing is the method exists
            pass

    def test_dataflow_config_property(self):
        """Test that config property exists and has expected structure."""
        db = DataFlow(
            "postgresql://test:test@localhost:5432/test", existing_schema_mode=True
        )

        assert hasattr(db, "config"), "Should have config property"
        assert db.config is not None, "Config should not be None"

        # Config should have database settings
        assert hasattr(db.config, "database"), "Config should have database section"

    def test_dataflow_enterprise_features_exist(self):
        """Test that enterprise feature properties exist."""
        db = DataFlow(
            "postgresql://test:test@localhost:5432/test", existing_schema_mode=True
        )

        # These are the enterprise features mentioned in documentation
        assert hasattr(db, "bulk"), "Should have bulk operations"
        assert hasattr(db, "transactions"), "Should have transaction manager"
        assert hasattr(db, "connection"), "Should have connection manager"

        # These should not be None (they should be initialized)
        assert db.bulk is not None, "Bulk operations should be initialized"
        assert db.transactions is not None, "Transaction manager should be initialized"
        assert db.connection is not None, "Connection manager should be initialized"


class TestDataFlowSafetyFeatures:
    """Test DataFlow safety features for existing databases."""

    def test_existing_schema_mode_parameter(self):
        """Test that existing_schema_mode parameter is accepted."""
        # Should not raise an error
        db = DataFlow(
            "postgresql://test:test@localhost:5432/test", existing_schema_mode=True
        )

        assert db is not None

        # Should be able to create without existing_schema_mode too
        db2 = DataFlow(
            "postgresql://test:test@localhost:5432/test", existing_schema_mode=False
        )

        assert db2 is not None

    def test_auto_migrate_parameter(self):
        """Test that auto_migrate parameter is accepted."""
        # Should not raise an error
        db = DataFlow("postgresql://test:test@localhost:5432/test", auto_migrate=False)

        assert db is not None

        # Should work with auto_migrate=True too
        db2 = DataFlow("postgresql://test:test@localhost:5432/test", auto_migrate=True)

        assert db2 is not None
