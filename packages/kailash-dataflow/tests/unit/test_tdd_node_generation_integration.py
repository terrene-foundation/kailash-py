"""
Unit tests for TDD Node Generation Integration.

Tests the core functionality of auto-generated DataFlow nodes working
with TDD infrastructure, focusing on the NodeGenerator modifications.
"""

import os
from unittest.mock import Mock, patch

import pytest

# Set TDD mode for this test
os.environ["DATAFLOW_TDD_MODE"] = "true"

from dataflow.core.engine import DataFlow
from dataflow.core.nodes import NodeGenerator
from dataflow.testing.tdd_support import TDDTestContext


class TestTDDNodeGenerationIntegration:
    """Test TDD integration with auto-generated nodes."""

    def test_node_generator_tdd_mode_detection(self):
        """Test that NodeGenerator detects TDD mode from DataFlow instance."""
        # Create mock DataFlow instance with TDD mode
        mock_dataflow = Mock()
        mock_dataflow._tdd_mode = True
        mock_dataflow._test_context = Mock()
        mock_dataflow._test_context.test_id = "test_123"

        # Create NodeGenerator
        generator = NodeGenerator(mock_dataflow)

        # Verify TDD mode detection
        assert generator._tdd_mode
        assert generator._test_context == mock_dataflow._test_context

    def test_node_generator_non_tdd_mode(self):
        """Test that NodeGenerator works normally without TDD mode."""
        # Create mock DataFlow instance without TDD mode
        mock_dataflow = Mock()
        mock_dataflow._tdd_mode = False
        mock_dataflow._test_context = None

        # Create NodeGenerator
        generator = NodeGenerator(mock_dataflow)

        # Verify non-TDD mode
        assert not generator._tdd_mode
        assert generator._test_context is None

    def test_generated_node_tdd_context_inheritance(self):
        """Test that generated nodes inherit TDD context from NodeGenerator."""
        # Create mock DataFlow instance with TDD context
        mock_dataflow = Mock()
        mock_dataflow._tdd_mode = True
        mock_test_context = Mock()
        mock_test_context.test_id = "test_inheritance"
        mock_dataflow._test_context = mock_test_context

        # Mock required methods
        mock_dataflow.get_model_fields.return_value = {
            "name": {"type": str, "required": True},
            "email": {"type": str, "required": True},
        }
        mock_dataflow.config.security.multi_tenant = False

        # Create NodeGenerator with proper mock setup
        generator = NodeGenerator(mock_dataflow)

        # Mock the normalize method to return actual types, not Mock objects
        def mock_normalize(type_annotation):
            if type_annotation == str:
                return str
            return str  # fallback

        generator._normalize_type_annotation = mock_normalize
        # Ensure the mock dataflow has the generator reference for generated nodes
        mock_dataflow._node_generator = generator
        fields = {"name": {"type": str, "required": True}}

        # Generate a create node
        NodeClass = generator._create_node_class("User", "create", fields)

        # Create instance and verify TDD context inheritance
        node_instance = NodeClass()
        assert hasattr(node_instance, "_tdd_mode")
        assert node_instance._tdd_mode
        assert hasattr(node_instance, "_test_context")
        assert node_instance._test_context == mock_test_context

    def test_tdd_connection_override(self):
        """Test that TDD nodes have access to TDD connection info."""
        # Create mock DataFlow instance with TDD connection
        mock_dataflow = Mock()
        mock_dataflow._tdd_mode = True
        mock_test_context = Mock()
        mock_test_context.test_id = "test_connection"
        mock_dataflow._test_context = mock_test_context
        mock_dataflow._tdd_connection = Mock()

        # Mock connection parameters
        mock_params = Mock()
        mock_params.user = "test_user"
        mock_params.password = "test_pass"
        mock_params.host = "localhost"
        mock_params.server_hostname = "localhost"  # Our fix checks this first
        mock_params.port = 5434
        mock_params.database = "test_db"
        mock_dataflow._tdd_connection._params = mock_params

        # Mock other required methods
        mock_dataflow.get_model_fields.return_value = {
            "name": {"type": str, "required": True}
        }
        mock_dataflow.config.security.multi_tenant = False
        mock_dataflow.config.database.get_connection_url.return_value = (
            "postgresql://prod"
        )
        mock_dataflow._detect_database_type.return_value = "postgresql"
        mock_dataflow._generate_insert_sql.return_value = "INSERT INTO users..."

        # Create NodeGenerator and generate node
        generator = NodeGenerator(mock_dataflow)

        # Mock the normalize method to return actual types, not Mock objects
        def mock_normalize(type_annotation):
            if type_annotation == str:
                return str
            return str  # fallback

        generator._normalize_type_annotation = mock_normalize
        # Ensure the mock dataflow has the generator reference for generated nodes
        mock_dataflow._node_generator = generator
        fields = {"name": {"type": str, "required": True}}
        NodeClass = generator._create_node_class("User", "create", fields)

        # Create node instance and verify TDD connection info is accessible
        node_instance = NodeClass()

        # Verify TDD mode is detected
        assert node_instance._tdd_mode is True

        # Verify TDD connection info method exists and returns expected value
        assert hasattr(node_instance, "_get_tdd_connection_info")
        connection_info = node_instance._get_tdd_connection_info()
        expected_connection = "postgresql://test_user:test_pass@localhost:5434/test_db"
        assert connection_info == expected_connection

    def test_tdd_connection_fallback(self):
        """Test TDD connection fallback when connection info unavailable."""
        # Create mock DataFlow instance with TDD mode but no connection params
        mock_dataflow = Mock()
        mock_dataflow._tdd_mode = True
        mock_test_context = Mock()
        mock_test_context.test_id = "test_fallback"
        mock_dataflow._test_context = mock_test_context
        mock_dataflow._tdd_connection = Mock()

        # Mock connection without _params (should trigger fallback)
        del mock_dataflow._tdd_connection._params

        # Mock other required methods
        mock_dataflow.get_model_fields.return_value = {
            "name": {"type": str, "required": True}
        }
        mock_dataflow.config.security.multi_tenant = False

        # Create NodeGenerator and generate node
        generator = NodeGenerator(mock_dataflow)
        fields = {"name": {"type": str, "required": True}}
        NodeClass = generator._create_node_class("User", "read", fields)

        # Create node instance
        node_instance = NodeClass()

        # Test the TDD connection info extraction
        connection_info = node_instance._get_tdd_connection_info()

        # Should fall back to TEST_DATABASE_URL environment variable
        expected_fallback = "postgresql://dataflow_test:dataflow_test_password@localhost:5434/dataflow_test"
        assert connection_info == expected_fallback

    def test_all_node_types_tdd_aware(self):
        """Test that all 11 node types are TDD-aware (7 CRUD + 4 Bulk)."""
        # Create mock DataFlow instance with TDD context
        mock_dataflow = Mock()
        mock_dataflow._tdd_mode = True
        mock_test_context = Mock()
        mock_test_context.test_id = "test_all_types"
        mock_dataflow._test_context = mock_test_context
        mock_dataflow._nodes = {}

        # Mock required methods for node registration
        mock_dataflow.get_model_fields.return_value = {
            "name": {"type": str, "required": True},
            "email": {"type": str, "required": True},
        }

        # Create NodeGenerator
        generator = NodeGenerator(mock_dataflow)

        # Mock the normalize method to return actual types, not Mock objects
        def mock_normalize(type_annotation):
            if type_annotation == str:
                return str
            return str  # fallback

        generator._normalize_type_annotation = mock_normalize
        # Ensure the mock dataflow has the generator reference for generated nodes
        mock_dataflow._node_generator = generator
        fields = {"name": {"type": str, "required": True}}

        # Generate CRUD nodes
        with patch("kailash.nodes.base.NodeRegistry.register"):
            crud_nodes = generator.generate_crud_nodes("TestModel", fields)
            bulk_nodes = generator.generate_bulk_nodes("TestModel", fields)

        # Verify all 11 node types were generated (7 CRUD + 4 Bulk)
        expected_crud_nodes = [
            "TestModelCreateNode",
            "TestModelReadNode",
            "TestModelUpdateNode",
            "TestModelDeleteNode",
            "TestModelListNode",
            "TestModelUpsertNode",
            "TestModelCountNode",
        ]

        expected_bulk_nodes = [
            "TestModelBulkCreateNode",
            "TestModelBulkUpdateNode",
            "TestModelBulkDeleteNode",
            "TestModelBulkUpsertNode",
        ]

        assert len(crud_nodes) == 7
        assert len(bulk_nodes) == 4

        for node_name in expected_crud_nodes:
            assert node_name in crud_nodes

        for node_name in expected_bulk_nodes:
            assert node_name in bulk_nodes

        # Verify all generated nodes are TDD-aware
        all_nodes = {**crud_nodes, **bulk_nodes}
        for node_name, node_class in all_nodes.items():
            # Mock the type normalization for this node class
            with patch.object(
                generator, "_normalize_type_annotation", return_value=str
            ):
                node_instance = node_class()
                assert hasattr(node_instance, "_tdd_mode")
                assert node_instance._tdd_mode
                assert hasattr(node_instance, "_test_context")
                assert node_instance._test_context == mock_test_context

    def test_dataflow_tdd_integration_initialization(self):
        """Test DataFlow initialization with TDD mode."""
        with patch.dict(os.environ, {"DATAFLOW_TDD_MODE": "true"}):
            # Create DataFlow with TDD context
            test_context = TDDTestContext(test_id="init_test")

            db = DataFlow(
                database_url="postgresql://test:pass@localhost:5432/testdb",
                tdd_mode=True,
                test_context=test_context,
                auto_migrate=False,
                existing_schema_mode=True,
            )

            # Verify TDD mode was set
            assert db._tdd_mode
            assert db._test_context == test_context

            # Verify NodeGenerator was created with TDD context
            assert db._node_generator._tdd_mode
            assert db._node_generator._test_context == test_context

    def test_model_registration_tdd_logging(self):
        """Test that model registration includes TDD logging."""
        with patch.dict(os.environ, {"DATAFLOW_TDD_MODE": "true"}):
            # Create DataFlow with TDD context
            test_context = TDDTestContext(test_id="logging_test")

            db = DataFlow(
                database_url="postgresql://test:pass@localhost:5432/testdb",
                tdd_mode=True,
                test_context=test_context,
                auto_migrate=False,
                existing_schema_mode=True,
            )

            # Mock the logger to capture log messages
            with patch("dataflow.core.engine.logger") as mock_logger:
                # Register a model
                @db.model
                class LoggingTest:
                    name: str
                    value: int

                # Verify TDD logging was called
                mock_logger.debug.assert_called()

                # Check that TDD-specific log messages were generated
                debug_calls = [call[0][0] for call in mock_logger.debug.call_args_list]
                tdd_logs = [
                    msg
                    for msg in debug_calls
                    if "TDD-aware" in msg and "logging_test" in msg
                ]

                # Should have logs for both CRUD and bulk node generation
                assert len(tdd_logs) >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
