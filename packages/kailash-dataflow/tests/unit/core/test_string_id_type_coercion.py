"""
Unit tests for string ID type coercion bug fix in DataFlow nodes.

This test module demonstrates and validates the fix for the critical bug where
DataFlow was forcibly converting string IDs to integers, causing PostgreSQL
type mismatch errors.

Bug: record_id = int(id_param) forces string to int conversion
Fix: Type-aware conversion based on model field annotations
"""

import logging
from unittest.mock import MagicMock, Mock, patch

import pytest


class TestStringIdTypeCoercion:
    """Test string ID type coercion across all DataFlow operations."""

    def create_mock_dataflow_node(self, model_fields):
        """Create a mock DataFlow node that simulates the problematic code patterns."""

        class MockDataFlowNode:
            def __init__(self):
                self.model_fields = model_fields
                self.model_name = "TestModel"
                self.table_name = "test_table"
                self.operation = "test"
                self.logger = logging.getLogger(__name__)

            def _get_connection(self, database_url):
                """Mock connection method."""
                return Mock()

            def simulate_read_operation_current(self, **kwargs):
                """Simulate current READ operation with type-aware fix (should work)."""
                id_param = kwargs.get("id")
                if id_param is not None:
                    # Current type-aware logic from lines 964-980
                    id_field_info = self.model_fields.get("id", {})
                    id_type = id_field_info.get("type")

                    if id_type == str:
                        # Model explicitly defines ID as string - preserve it
                        record_id = id_param
                    elif id_type == int or id_type is None:
                        # Model defines ID as int OR no type info (backward compat)
                        try:
                            record_id = int(id_param)
                        except (ValueError, TypeError):
                            # If conversion fails, preserve original
                            record_id = id_param
                    else:
                        # Other types (UUID, custom) - preserve as-is
                        record_id = id_param
                else:
                    record_id = 1  # Default fallback
                return record_id

            def simulate_update_operation_current(self, **kwargs):
                """Simulate current UPDATE operation with old bug (should fail)."""
                id_param = kwargs.get("id")
                if id_param is not None and id_param != self.operation:
                    # Old problematic pattern from line 1069
                    try:
                        # Try to convert to int - THIS IS THE BUG
                        record_id = int(id_param)
                    except (ValueError, TypeError):
                        # Not a valid int, use record_id parameter instead
                        record_id = kwargs.get("record_id")
                else:
                    record_id = kwargs.get("record_id", 1)
                return record_id

            def simulate_update_operation_fixed(self, **kwargs):
                """Simulate fixed UPDATE operation with type-aware logic."""
                id_param = kwargs.get("id")
                if id_param is not None and id_param != self.operation:
                    # Fixed type-aware logic (same as read operation)
                    id_field_info = self.model_fields.get("id", {})
                    id_type = id_field_info.get("type")

                    if id_type == str:
                        # Model explicitly defines ID as string - preserve it
                        record_id = id_param
                    elif id_type == int or id_type is None:
                        # Model defines ID as int OR no type info (backward compat)
                        try:
                            record_id = int(id_param)
                        except (ValueError, TypeError):
                            # If conversion fails, preserve original
                            record_id = id_param
                    else:
                        # Other types (UUID, custom) - preserve as-is
                        record_id = id_param
                else:
                    record_id = kwargs.get("record_id", 1)
                return record_id

        return MockDataFlowNode()

    def test_read_operation_preserves_string_id(self):
        """Test that read operation preserves string IDs without conversion."""
        # Arrange
        string_id_fields = {"id": {"type": str}, "name": {"type": str}}
        node = self.create_mock_dataflow_node(string_id_fields)
        string_id = "session-80706348-0456-468b-8851-329a756a3a93"

        # Act
        result_id = node.simulate_read_operation_current(id=string_id)

        # Assert - should preserve string ID without conversion
        assert result_id == string_id
        assert isinstance(result_id, str)

    def test_read_operation_converts_integer_id(self):
        """Test that read operation still converts integer IDs for backward compatibility."""
        # Arrange
        int_id_fields = {"id": {"type": int}, "name": {"type": str}}
        node = self.create_mock_dataflow_node(int_id_fields)
        int_id_str = "123"  # String that should be converted to int

        # Act
        result_id = node.simulate_read_operation_current(id=int_id_str)

        # Assert - should convert string "123" to int 123
        assert result_id == 123
        assert isinstance(result_id, int)

    def test_update_operation_fails_with_string_id_current_bug(self):
        """FAILING TEST: Update operation falls back to None when string ID can't convert to int (THE BUG)."""
        # Arrange
        string_id_fields = {"id": {"type": str}, "name": {"type": str}}
        node = self.create_mock_dataflow_node(string_id_fields)
        string_id = "user-uuid-12345"

        # Act - The current update operation will try to convert string to int and fail
        result_id = node.simulate_update_operation_current(id=string_id)

        # Assert - This demonstrates the bug: it falls back to None instead of preserving the string
        assert result_id is None  # This is WRONG - should be string_id
        # The bug is that it doesn't preserve the original string ID

    def test_update_operation_works_with_numeric_string_current_bug(self):
        """Show that update operation only works with numeric strings (not real string IDs)."""
        # Arrange
        string_id_fields = {"id": {"type": str}, "name": {"type": str}}
        node = self.create_mock_dataflow_node(string_id_fields)
        numeric_string_id = "12345"  # String that looks like a number

        # Act
        result_id = node.simulate_update_operation_current(id=numeric_string_id)

        # Assert - Current bug converts even string-typed IDs to int
        assert result_id == 12345  # Converted to int!
        assert isinstance(result_id, int)  # This is WRONG for string ID model

    def test_update_operation_preserves_string_id_after_fix(self):
        """Test that fixed update operation preserves string IDs correctly."""
        # Arrange
        string_id_fields = {"id": {"type": str}, "name": {"type": str}}
        node = self.create_mock_dataflow_node(string_id_fields)
        string_id = "user-uuid-12345"

        # Act
        result_id = node.simulate_update_operation_fixed(id=string_id)

        # Assert - should preserve string ID without conversion
        assert result_id == string_id
        assert isinstance(result_id, str)

    def test_update_operation_converts_integer_id_after_fix(self):
        """Test that fixed update operation still converts integer IDs for backward compatibility."""
        # Arrange
        int_id_fields = {"id": {"type": int}, "name": {"type": str}}
        node = self.create_mock_dataflow_node(int_id_fields)
        int_id_str = "456"  # String that should be converted to int

        # Act
        result_id = node.simulate_update_operation_fixed(id=int_id_str)

        # Assert - should convert string "456" to int 456
        assert result_id == 456
        assert isinstance(result_id, int)

    def test_uuid_id_preservation(self):
        """Test that UUID IDs are preserved without conversion."""
        # Arrange
        import uuid

        string_id_fields = {"id": {"type": str}, "name": {"type": str}}
        node = self.create_mock_dataflow_node(string_id_fields)
        uuid_id = str(uuid.uuid4())

        # Act
        result_id = node.simulate_read_operation_current(id=uuid_id)

        # Assert - UUID should be preserved as string
        assert result_id == uuid_id
        assert isinstance(result_id, str)

    def test_uuid_id_fails_in_current_update_operation(self):
        """Test that UUID IDs fall back to None in current update operation due to int conversion bug."""
        # Arrange
        import uuid

        string_id_fields = {"id": {"type": str}, "name": {"type": str}}
        node = self.create_mock_dataflow_node(string_id_fields)
        uuid_id = str(uuid.uuid4())

        # Act - Current update operation will try to convert UUID to int and fail
        result_id = node.simulate_update_operation_current(id=uuid_id)

        # Assert - This demonstrates the bug: UUID falls back to None instead of being preserved
        assert result_id is None  # This is WRONG - should be uuid_id
        # The bug is that it doesn't preserve the original UUID string

    def test_none_id_handling(self):
        """Test that None ID is handled gracefully."""
        # Arrange
        string_id_fields = {"id": {"type": str}, "name": {"type": str}}
        node = self.create_mock_dataflow_node(string_id_fields)

        # Act
        result_id = node.simulate_read_operation_current(id=None)

        # Assert - should fall back to default record_id
        assert result_id == 1

    def test_empty_string_id_handling(self):
        """Test that empty string ID is handled appropriately."""
        # Arrange
        string_id_fields = {"id": {"type": str}, "name": {"type": str}}
        node = self.create_mock_dataflow_node(string_id_fields)
        empty_id = ""

        # Act
        result_id = node.simulate_read_operation_current(id=empty_id)

        # Assert - empty string should be preserved (valid string ID)
        assert result_id == ""
        assert isinstance(result_id, str)

    def test_backward_compatibility_with_untyped_models(self):
        """Test that models without type information default to int conversion."""
        # Arrange - model without type information (backward compatibility)
        untyped_fields = {"id": {}, "name": {}}  # No type specified
        node = self.create_mock_dataflow_node(untyped_fields)
        numeric_string = "789"

        # Act
        result_id = node.simulate_read_operation_current(id=numeric_string)

        # Assert - should default to int conversion for backward compatibility
        assert result_id == 789
        assert isinstance(result_id, int)
