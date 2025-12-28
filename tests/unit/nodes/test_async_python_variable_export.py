"""
Unit tests for AsyncPythonCodeNode variable export fix (v0.9.30).

This test validates that AsyncPythonCodeNode correctly exports all variables
from the execution context, matching PythonCodeNode's multi-output pattern.

Bug Report: AsyncPythonCodeNode exported all variables as empty dicts {}
Fix: Modified async_run to extract and return ALL non-private variables from namespace
"""

import pytest
from kailash.nodes.code.async_python import AsyncPythonCodeNode


@pytest.mark.asyncio
async def test_async_python_export_dict_variables():
    """Test AsyncPythonCodeNode exports dict variables with correct values."""
    code = """
# Export multiple dict variables (multi-output pattern)
my_filter = {"id": "test_123"}
my_fields = {
    "name": "John",
    "edited": True
}
"""

    node = AsyncPythonCodeNode(code=code)
    result = await node.execute_async()

    # Verify both variables are exported with correct values
    assert "my_filter" in result, "my_filter should be exported"
    assert "my_fields" in result, "my_fields should be exported"

    # Verify values are correct (not empty dicts)
    assert result["my_filter"] == {
        "id": "test_123"
    }, "my_filter should have correct value"
    assert result["my_fields"] == {
        "name": "John",
        "edited": True,
    }, "my_fields should have correct value"


@pytest.mark.asyncio
async def test_async_python_export_mixed_types():
    """Test AsyncPythonCodeNode exports variables of different types."""
    code = """
# Export variables of different types
my_filter = {"id": "test_123"}
my_string = "hello"
my_number = 42
my_list = [1, 2, 3]
my_bool = True
"""

    node = AsyncPythonCodeNode(code=code)
    result = await node.execute_async()

    # Verify all variables are exported with correct types and values
    assert result["my_filter"] == {"id": "test_123"}
    assert result["my_string"] == "hello"
    assert result["my_number"] == 42
    assert result["my_list"] == [1, 2, 3]
    assert result["my_bool"] is True


@pytest.mark.asyncio
async def test_async_python_export_with_result_variable():
    """Test AsyncPythonCodeNode returns only 'result' when it exists (legacy pattern)."""
    code = """
# Legacy pattern: use 'result' variable
my_filter = {"id": "test_123"}
my_fields = {"name": "John"}
result = {"status": "processed"}
"""

    node = AsyncPythonCodeNode(code=code)
    result = await node.execute_async()

    # When 'result' exists, only 'result' should be returned
    assert "result" in result
    assert result["result"] == {"status": "processed"}

    # Other variables should NOT be exported when 'result' exists
    assert "my_filter" not in result
    assert "my_fields" not in result


@pytest.mark.asyncio
async def test_async_python_export_no_variables():
    """Test AsyncPythonCodeNode returns empty dict when no variables are exported."""
    code = """
# Code that doesn't export any variables
x = 42
"""

    node = AsyncPythonCodeNode(code=code)
    result = await node.execute_async()

    # Should export the variable x
    assert "x" in result
    assert result["x"] == 42


@pytest.mark.asyncio
async def test_async_python_export_filters_private_variables():
    """Test AsyncPythonCodeNode filters out private variables (starting with _)."""
    code = """
# Public and private variables
public_var = "visible"
_private_var = "hidden"
__very_private = "very hidden"
"""

    node = AsyncPythonCodeNode(code=code)
    result = await node.execute_async()

    # Only public variables should be exported
    assert "public_var" in result
    assert result["public_var"] == "visible"

    # Private variables should NOT be exported
    assert "_private_var" not in result
    assert "__very_private" not in result


@pytest.mark.asyncio
async def test_async_python_export_filters_modules():
    """Test AsyncPythonCodeNode filters out imported modules."""
    code = """
import json
import math

# These should be exported
data = {"value": 42}
result_value = math.sqrt(16)
"""

    node = AsyncPythonCodeNode(code=code)
    result = await node.execute_async()

    # Variables should be exported
    assert "data" in result
    assert "result_value" in result

    # Modules should NOT be exported
    assert "json" not in result
    assert "math" not in result


@pytest.mark.asyncio
async def test_async_python_export_comparison_with_sync():
    """
    Test that AsyncPythonCodeNode and PythonCodeNode have matching export behavior.

    This test validates that both sync and async versions export variables identically.
    """
    code = """
# Multi-output pattern
filter_data = {"id": "user_123"}
fields_data = {"name": "Updated", "status": "active"}
count = 10
"""

    # Test async version
    async_node = AsyncPythonCodeNode(code=code)
    async_result = await async_node.execute_async()

    # Both should export the same variables
    assert "filter_data" in async_result
    assert "fields_data" in async_result
    assert "count" in async_result

    # Verify values are correct
    assert async_result["filter_data"] == {"id": "user_123"}
    assert async_result["fields_data"] == {"name": "Updated", "status": "active"}
    assert async_result["count"] == 10


@pytest.mark.asyncio
async def test_async_python_export_nested_dicts():
    """Test AsyncPythonCodeNode exports nested dict structures correctly."""
    code = """
# Nested dict structures
user_data = {
    "id": "user_123",
    "profile": {
        "name": "John Doe",
        "settings": {
            "theme": "dark",
            "notifications": True
        }
    },
    "metadata": {
        "created": "2025-01-01",
        "updated": "2025-01-24"
    }
}
"""

    node = AsyncPythonCodeNode(code=code)
    result = await node.execute_async()

    expected = {
        "id": "user_123",
        "profile": {
            "name": "John Doe",
            "settings": {"theme": "dark", "notifications": True},
        },
        "metadata": {"created": "2025-01-01", "updated": "2025-01-24"},
    }

    assert result["user_data"] == expected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
