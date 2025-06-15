"""Test DataTransformer nested mapping functionality."""

import pytest

from kailash.nodes.code import PythonCodeNode
from kailash.nodes.transform import DataTransformer
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow


def test_datatransformer_dict_mapping():
    """Test that DataTransformer correctly receives dict inputs."""

    # Create a workflow that produces a dict
    workflow = Workflow("test_dict_mapping", "Test DataTransformer Dict Mapping")

    # Source node that produces a dict
    source = PythonCodeNode.from_function(
        name="source",
        func=lambda: {
            "files": ["a.txt", "b.txt"],
            "count": 2,
            "metadata": {"type": "test"},
        },
    )
    workflow.add_node("source", source)

    # DataTransformer that should receive the dict
    transformer = DataTransformer(
        transformations=[
            """
# Check that we received the dict correctly
assert isinstance(data, dict), f"Expected dict, got {type(data)}"
assert "files" in data, f"Missing 'files' key in data: {data}"
assert "count" in data, f"Missing 'count' key in data: {data}"
assert "metadata" in data, f"Missing 'metadata' key in data: {data}"

result = {"bug_detected": False, "data_type": type(data).__name__}
"""
        ]
    )
    workflow.add_node("transformer", transformer)

    # Connect passing the entire dict wrapped in result
    workflow.connect("source", "transformer", mapping={"result": "data"})

    # Run the workflow
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow)

    # Verify the bug is fixed
    transformer_result = results.get("transformer", {}).get("result", {})
    assert not transformer_result.get(
        "bug_detected", True
    ), "DataTransformer bug still present"
    assert transformer_result.get("data_type") == "dict", "Expected dict type"


def test_datatransformer_nested_mapping():
    """Test DataTransformer with nested field mapping."""

    workflow = Workflow("test_nested_mapping", "Test DataTransformer Nested Mapping")

    # Source node that produces a dict
    source = PythonCodeNode.from_function(
        name="source",
        func=lambda: {
            "files": ["a.txt", "b.txt"],
            "count": 2,
            "metadata": {"type": "test"},
        },
    )
    workflow.add_node("source", source)

    # DataTransformer with direct field mapping
    transformer = DataTransformer(
        transformations=[
            """
# Check that nested mapping worked
assert "files" in locals(), "Nested mapping failed: 'files' not in locals"
assert "count" in locals(), "Nested mapping failed: 'count' not in locals"
assert "metadata" in locals(), "Nested mapping failed: 'metadata' not in locals"

assert files == ["a.txt", "b.txt"], f"Unexpected files value: {files}"
assert count == 2, f"Unexpected count value: {count}"
assert metadata == {"type": "test"}, f"Unexpected metadata value: {metadata}"

# Process the data
file_count = len(files)
meta_type = metadata.get("type", "unknown")

result = {
    "file_count": file_count,
    "metadata_type": meta_type,
    "mapping_success": True
}
"""
        ]
    )
    workflow.add_node("transformer", transformer)

    # Connect with nested field mapping (e.g., "result.files" -> "files")
    workflow.connect(
        "source",
        "transformer",
        mapping={
            "result.files": "files",
            "result.count": "count",
            "result.metadata": "metadata",
        },
    )

    # Run the workflow
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow)

    # Verify nested mapping worked
    result = results.get("transformer", {}).get("result", {})
    assert result.get("mapping_success", False), "Nested mapping failed"
    assert (
        result.get("file_count") == 2
    ), f"Expected file_count=2, got {result.get('file_count')}"
    assert (
        result.get("metadata_type") == "test"
    ), f"Expected metadata_type='test', got {result.get('metadata_type')}"


def test_datatransformer_direct_execution():
    """Test DataTransformer with direct execution and nested dict access."""

    # Direct test of DataTransformer
    transformer = DataTransformer(
        transformations=[
            """
# Test nested dict access
assert "complex_data" in locals(), "Missing 'complex_data' in locals"

# Access nested fields
user_name = complex_data.get("user", {}).get("name", "unknown")
items = complex_data.get("items", [])
item_count = len(items)

result = {
    "user_name": user_name,
    "item_count": item_count,
    "first_item": items[0] if items else None
}
"""
        ]  # Multi-line transformation with proper indentation
    )

    # Test with complex nested data
    test_data = {
        "complex_data": {
            "user": {"name": "Alice", "id": 123},
            "items": ["apple", "banana", "cherry"],
            "metadata": {"timestamp": "2025-06-13"},
        }
    }

    result = transformer.execute(**test_data)

    # Verify result structure
    assert isinstance(
        result.get("result"), dict
    ), f"Expected dict result, got {type(result.get('result'))}: {result}"
    assert result["result"]["user_name"] == "Alice", "Expected user_name='Alice'"
    assert result["result"]["item_count"] == 3, "Expected item_count=3"
    assert result["result"]["first_item"] == "apple", "Expected first_item='apple'"


def test_datatransformer_multiple_nested_paths():
    """Test LocalRuntime handles multiple levels of nested paths."""

    workflow = Workflow("test_deep_nesting", "Test Deep Nested Mapping")

    # Source with deeply nested structure
    source = PythonCodeNode.from_function(
        name="source",
        func=lambda: {
            "data": {"level1": {"level2": {"value": 42, "items": ["x", "y", "z"]}}}
        },
    )
    workflow.add_node("source", source)

    # Transformer expecting nested values
    transformer = DataTransformer(
        transformations=[
            """
assert "value" in locals(), "Deep nested mapping failed for 'value'"
assert "items" in locals(), "Deep nested mapping failed for 'items'"

assert value == 42, f"Expected value=42, got {value}"
assert items == ["x", "y", "z"], f"Expected items=['x', 'y', 'z'], got {items}"

result = {"deep_mapping_success": True, "value": value, "item_count": len(items)}
"""
        ]
    )
    workflow.add_node("transformer", transformer)

    # Connect with deep nested paths
    workflow.connect(
        "source",
        "transformer",
        mapping={
            "result.data.level1.level2.value": "value",
            "result.data.level1.level2.items": "items",
        },
    )

    # Run and verify
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow)

    result = results.get("transformer", {}).get("result", {})
    assert result.get("deep_mapping_success", False), "Deep nested mapping failed"
    assert result.get("value") == 42, "Value mapping failed"
    assert result.get("item_count") == 3, "Items mapping failed"
