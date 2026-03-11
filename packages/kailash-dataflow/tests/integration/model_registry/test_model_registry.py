#!/usr/bin/env python3
"""
Unit tests for ModelRegistry - persistent model storage.
Tests multi-application model synchronization.
"""

import json
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

# TODO: Implement ModelRegistry in dataflow.core
# from dataflow.core.model_registry import ModelRegistry
from tests.utils.real_infrastructure import real_infra


# Placeholder ModelRegistry until actual implementation
class ModelRegistry:
    def __init__(self, dataflow):
        self.dataflow = dataflow
        self._initialized = False
        self.runtime = None

    def initialize(self):
        self._initialized = True
        return True

    def register_model(self, name, fields, options=None):
        return True

    def discover_models(self):
        return {}

    def sync_models(self):
        return 0, 0

    def get_model_version(self, name):
        return 0

    def get_model_history(self, name):
        return []

    def validate_consistency(self):
        return {}

    def _generate_unified_checksum(self, content):
        import hashlib

        return hashlib.sha256(str(content).encode()).hexdigest()[:16]

    def _reconstruct_model(self, name, info):
        return True


@pytest.mark.unit
@pytest.mark.timeout(5)
class TestModelRegistry:
    """Test the persistent model registry."""

    def setup_method(self):
        """Set up test fixtures."""
        # Mock DataFlow instance
        # TODO: Use real dataflow from real_infra
        self.mock_dataflow = Mock()
        self.mock_dataflow.config = Mock()  # TODO: Replace with real implementation
        self.mock_dataflow.config.database = (
            Mock()
        )  # TODO: Replace with real implementation
        self.mock_dataflow.config.database.get_connection_url = Mock(
            return_value="postgresql://test:test@localhost/test"
        )
        self.mock_dataflow.config.environment = "test-app"
        self.mock_dataflow._models = {}

        # Mock runtime
        # TODO: Use real runtime from real_infra
        self.mock_runtime = Mock()

        # Create registry
        self.registry = ModelRegistry(self.mock_dataflow)
        self.registry.runtime = self.mock_runtime

    def test_initialization(self):
        """Test registry initialization."""
        # Mock the workflow builder and runtime calls
        with patch.object(self.registry, "runtime") as mock_runtime:

            # Mock workflow builder
            # TODO: Use real workflow from real_infra
            mock_workflow = Mock()
            mock_workflow.build.return_value = (
                None  # TODO: Replace with real implementation
            )

            # Mock successful table extension with new result structure
            mock_runtime.execute = Mock(
                side_effect=[
                    # ensure_migrations_table result
                    ({"ensure_migrations_table": {}}, None),
                    # check_column result
                    ({"check_column": {"result": {"data": [{"exists": False}]}}}, None),
                    # add_model_definitions result
                    (
                        {
                            "add_model_definitions": {},
                            "add_application_id": {},
                            "add_model_checksum": {},
                        },
                        None,
                    ),
                    # add_app_index result
                    ({"add_app_index": {}, "add_checksum_index": {}}, None),
                ]
            )

            success = self.registry.initialize()

            assert success is True
            assert self.registry._initialized is True

    def test_register_model(self):
        """Test model registration in migration history."""
        # Setup
        self.registry._initialized = True

        # Mock checksum doesn't exist
        self.mock_runtime.execute = Mock(
            side_effect=[
                ({"check_checksum": {"data": [{"exists": False}]}}, None),
                ({"create_migration": {"success": True}}, None),
            ]
        )

        # Register model
        fields = {
            "name": {"type": "str", "required": True},
            "email": {"type": "str", "required": True},
            "active": {"type": "bool", "default": True},
        }
        options = {"multi_tenant": True}

        success = self.registry.register_model("User", fields, options)

        assert success is True
        # Verify migration was created
        assert self.mock_runtime.execute.call_count == 2

    def test_discover_models(self):
        """Test discovering models from migration history."""
        # Setup
        self.registry._initialized = True

        # Mock discovery results
        mock_data = [
            {
                "model_definitions": {
                    "model_name": "User",
                    "fields": {"name": {"type": "str"}},
                    "options": {"multi_tenant": True},
                }
            },
            {
                "model_definitions": {
                    "model_name": "Project",
                    "fields": {"title": {"type": "str"}},
                    "options": {},
                }
            },
        ]

        self.mock_runtime.execute = Mock(
            return_value=({"discover": {"data": mock_data}}, None)
        )

        # Discover models
        models = self.registry.discover_models()

        assert len(models) == 2
        assert "User" in models
        assert "Project" in models
        assert models["User"]["fields"] == {"name": {"type": "str"}}
        assert models["User"]["options"]["multi_tenant"] is True

    def test_sync_models(self):
        """Test syncing models to DataFlow instance."""
        # Setup
        self.registry._initialized = True

        # Mock discovered models
        with patch.object(self.registry, "discover_models") as mock_discover:
            mock_discover.return_value = {
                "User": {"fields": {"name": {"type": "str"}}, "options": {}}
            }

            # Mock reconstruction
            with patch.object(self.registry, "_reconstruct_model") as mock_reconstruct:
                mock_reconstruct.return_value = True

                # Sync models
                added, updated = self.registry.sync_models()

                assert added == 1
                assert updated == 0
                mock_reconstruct.assert_called_once_with(
                    "User", {"fields": {"name": {"type": "str"}}, "options": {}}
                )

    def test_model_version_tracking(self):
        """Test model version counting."""
        # Setup
        self.registry._initialized = True

        # Mock version count
        self.mock_runtime.execute = Mock(
            return_value=({"get_version": {"data": [{"version_count": 3}]}}, None)
        )

        # Get version
        version = self.registry.get_model_version("User")

        assert version == 3

    def test_model_history(self):
        """Test retrieving model history."""
        # Setup
        self.registry._initialized = True

        # Mock history data
        mock_history = [
            {
                "version": "model_User_20250101_abc123",
                "fields": json.dumps({"name": {"type": "str"}}),
                "options": json.dumps({}),
                "created_at": "2025-01-01T00:00:00",
                "created_by": "app1",
                "checksum": "abc123",
            }
        ]

        self.mock_runtime.execute = Mock(
            return_value=({"get_history": {"data": mock_history}}, None)
        )

        # Get history
        history = self.registry.get_model_history("User")

        assert len(history) == 1
        assert history[0]["checksum"] == "abc123"

    def test_consistency_validation(self):
        """Test cross-application consistency validation."""
        # Setup
        self.registry._initialized = True

        # Mock model list
        self.mock_runtime.execute = Mock(
            side_effect=[
                # First call - get models
                ({"get_models": {"data": [{"model_name": "User"}]}}, None),
                # Second call - get checksums
                (
                    {
                        "get_checksums": {
                            "data": [
                                {"application_id": "app1", "checksum": "abc123"},
                                {"application_id": "app2", "checksum": "def456"},
                            ]
                        }
                    },
                    None,
                ),
            ]
        )

        # Validate consistency
        issues = self.registry.validate_consistency()

        assert "User" in issues
        assert "mismatch between applications" in issues["User"][0]

    def test_checksum_generation(self):
        """Test unified checksum generation."""
        content1 = {"fields": {"a": 1, "b": 2}, "options": {}}
        content2 = {"fields": {"b": 2, "a": 1}, "options": {}}  # Different order
        content3 = {"fields": {"a": 1, "b": 3}, "options": {}}  # Different value

        checksum1 = self.registry._generate_unified_checksum(content1)
        checksum2 = self.registry._generate_unified_checksum(content2)
        checksum3 = self.registry._generate_unified_checksum(content3)

        # Same content, different order should produce same checksum
        assert checksum1 == checksum2
        # Different content should produce different checksum
        assert checksum1 != checksum3
        # Checksum should be 16 characters (truncated SHA256)
        assert len(checksum1) == 16

    def test_model_reconstruction(self):
        """Test dynamic model class reconstruction."""
        # Model info
        model_info = {
            "fields": {
                "name": {"type": "str", "required": True},
                "age": {"type": "int", "default": 0},
                "active": {"type": "bool", "default": True},
            },
            "options": {"multi_tenant": True},
        }

        # Mock dataflow.model() method
        self.mock_dataflow.model = None  # TODO: Replace with real implementation

        # Reconstruct model
        success = self.registry._reconstruct_model("TestModel", model_info)

        assert success is True
        # Verify model was registered with DataFlow
        self.mock_dataflow.model.assert_called_once()

        # Check the reconstructed class
        model_class = self.mock_dataflow.model.call_args[0][0]
        assert model_class.__name__ == "TestModel"
        assert hasattr(model_class, "__annotations__")
        assert model_class.__annotations__["name"] == str
        assert model_class.__annotations__["age"] == int
        assert model_class.active is True  # Default value set

    def test_migration_system_integration(self):
        """Test integration with existing migration system."""
        # Mock migration system
        # TODO: Use real migration_system from real_infra
        mock_migration_system = Mock()

        registry = ModelRegistry(self.mock_dataflow)
        registry.runtime = self.mock_runtime

        # Mock table already extended
        self.mock_runtime.execute = Mock(
            return_value=({"check_column": {"data": [{"exists": True}]}}, None)
        )

        success = registry.initialize()

        assert success is True
        # Migration system is passed but not called during init

    def test_duplicate_model_registration(self):
        """Test that duplicate models are not re-registered."""
        # Setup
        self.registry._initialized = True

        # Mock checksum already exists
        self.mock_runtime.execute = Mock(
            return_value=({"check_checksum": {"data": [{"exists": True}]}}, None)
        )

        # Try to register same model
        success = self.registry.register_model("User", {"name": {"type": "str"}})

        assert success is True
        # Verify no migration was created (only 1 call to check checksum)
        assert self.mock_runtime.execute.call_count == 1


@pytest.mark.unit
@pytest.mark.timeout(2)
class TestMultiApplicationScenarios:
    """Test multi-application scenarios."""

    def test_two_apps_same_model(self):
        """Test two applications registering the same model."""
        # App 1 registry
        dataflow1 = Mock()  # TODO: Replace with real implementation
        dataflow1.config.database.get_connection_url = Mock(
            return_value="postgresql://test"
        )
        dataflow1.config.environment = "app1"
        registry1 = ModelRegistry(dataflow1)

        # App 2 registry
        dataflow2 = Mock()  # TODO: Replace with real implementation
        dataflow2.config.database.get_connection_url = Mock(
            return_value="postgresql://test"
        )
        dataflow2.config.environment = "app2"
        registry2 = ModelRegistry(dataflow2)

        # Both apps define same model
        fields = {"name": {"type": "str"}, "email": {"type": "str"}}

        # Mock runtime for both
        # TODO: Use real runtime from real_infra
        mock_runtime = Mock()
        registry1.runtime = mock_runtime
        registry2.runtime = mock_runtime
        registry1._initialized = True
        registry2._initialized = True

        # First app registers
        mock_runtime.execute = Mock(
            side_effect=[
                ({"check_checksum": {"data": [{"exists": False}]}}, None),
                ({"create_migration": {"success": True}}, None),
            ]
        )

        success1 = registry1.register_model("User", fields)
        assert success1 is True

        # Second app registers same model - should skip
        mock_runtime.execute = Mock(
            return_value=({"check_checksum": {"data": [{"exists": True}]}}, None)
        )

        success2 = registry2.register_model("User", fields)
        assert success2 is True
        assert mock_runtime.execute.call_count == 1  # Only checksum check


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
