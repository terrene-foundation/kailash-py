"""
Simple tests for TDD Node Generation Integration.

Focuses on the core TDD functionality without complex mocking.
"""

import os
from unittest.mock import Mock

import pytest

# Set TDD mode for this test
os.environ["DATAFLOW_TDD_MODE"] = "true"

from dataflow.core.nodes import NodeGenerator
from dataflow.testing.tdd_support import TDDTestContext


class TestTDDNodeGenerationSimple:
    """Simple tests for TDD integration with auto-generated nodes."""

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

    def test_tdd_context_inheritance_in_closure(self):
        """Test that TDD context is stored in closure for node generation."""
        # Create mock DataFlow instance with TDD context
        mock_dataflow = Mock()
        mock_dataflow._tdd_mode = True
        mock_test_context = Mock()
        mock_test_context.test_id = "test_closure"
        mock_dataflow._test_context = mock_test_context

        # Create NodeGenerator
        generator = NodeGenerator(mock_dataflow)

        # Verify closure stores TDD context
        assert generator._tdd_mode
        assert generator._test_context == mock_test_context

    def test_tdd_connection_info_method_exists(self):
        """Test that generated nodes have _get_tdd_connection_info method."""
        # Create mock DataFlow instance with TDD context
        mock_dataflow = Mock()
        mock_dataflow._tdd_mode = True
        mock_test_context = Mock()
        mock_test_context.test_id = "test_method"
        mock_dataflow._test_context = mock_test_context

        # Create NodeGenerator and generate a simple node class
        generator = NodeGenerator(mock_dataflow)
        fields = {"name": {"type": str, "required": True}}

        # Create the node class
        NodeClass = generator._create_node_class("TestModel", "create", fields)

        # Check that the class has the TDD connection method
        assert hasattr(NodeClass, "__name__")
        assert "TestModel" in NodeClass.__name__
        assert "CreateNode" in NodeClass.__name__

        # Verify that the async_run method includes TDD logic (since run is just a wrapper)
        import inspect

        # Check async_run method which contains the actual logic
        async_run_method_source = inspect.getsource(NodeClass.async_run)
        assert "_get_tdd_connection_info" in async_run_method_source
        assert "TDD mode:" in async_run_method_source

    def test_tdd_context_propagation(self):
        """Test that TDD context is properly propagated to generated nodes."""
        # Create test context
        test_context = TDDTestContext(test_id="propagation_test")

        # Create mock DataFlow instance
        mock_dataflow = Mock()
        mock_dataflow._tdd_mode = True
        mock_dataflow._test_context = test_context

        # Create NodeGenerator
        generator = NodeGenerator(mock_dataflow)

        # Verify generator has the context
        assert generator._tdd_mode
        assert generator._test_context == test_context
        assert generator._test_context.test_id == "propagation_test"

    def test_generated_node_class_naming(self):
        """Test that generated node classes have correct names."""
        # Create mock DataFlow instance
        mock_dataflow = Mock()
        mock_dataflow._tdd_mode = True
        mock_dataflow._test_context = Mock()

        # Create NodeGenerator
        generator = NodeGenerator(mock_dataflow)
        fields = {"name": {"type": str, "required": True}}

        # Test different operation types
        operations = ["create", "read", "update", "delete", "list"]
        for operation in operations:
            NodeClass = generator._create_node_class("User", operation, fields)
            expected_name = (
                f"User{operation.replace('_', ' ').title().replace(' ', '')}Node"
            )
            assert NodeClass.__name__ == expected_name

    def test_bulk_operation_node_naming(self):
        """Test that bulk operation nodes have correct names."""
        # Create mock DataFlow instance
        mock_dataflow = Mock()
        mock_dataflow._tdd_mode = True
        mock_dataflow._test_context = Mock()

        # Create NodeGenerator
        generator = NodeGenerator(mock_dataflow)
        fields = {"name": {"type": str, "required": True}}

        # Test bulk operations
        bulk_operations = ["bulk_create", "bulk_update", "bulk_delete", "bulk_upsert"]
        for operation in bulk_operations:
            NodeClass = generator._create_node_class("Product", operation, fields)
            expected_name = (
                f"Product{operation.replace('_', ' ').title().replace(' ', '')}Node"
            )
            assert NodeClass.__name__ == expected_name

    def test_tdd_mode_environment_variable(self):
        """Test that TDD mode can be detected from environment variable."""
        # Test with TDD mode enabled
        with pytest.MonkeyPatch().context() as m:
            m.setenv("DATAFLOW_TDD_MODE", "true")

            from dataflow.testing.tdd_support import is_tdd_mode

            assert is_tdd_mode()

        # Test with TDD mode disabled
        with pytest.MonkeyPatch().context() as m:
            m.setenv("DATAFLOW_TDD_MODE", "false")

            from dataflow.testing.tdd_support import is_tdd_mode

            assert not is_tdd_mode()

    def test_node_generator_initialization_with_tdd(self):
        """Test NodeGenerator initialization preserves TDD context."""
        # Create a real TDD test context
        test_context = TDDTestContext(
            test_id="init_test",
            isolation_level="READ COMMITTED",
            rollback_on_error=True,
        )

        # Create mock DataFlow with the real context
        mock_dataflow = Mock()
        mock_dataflow._tdd_mode = True
        mock_dataflow._test_context = test_context

        # Initialize NodeGenerator
        generator = NodeGenerator(mock_dataflow)

        # Verify initialization
        assert generator.dataflow_instance == mock_dataflow
        assert generator._tdd_mode
        assert generator._test_context == test_context
        assert generator._test_context.test_id == "init_test"
        assert generator._test_context.isolation_level == "READ COMMITTED"
        assert generator._test_context.rollback_on_error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
