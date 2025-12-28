"""Test output schema validation functionality."""

from typing import Any

import pytest
from kailash.nodes.base import Node, NodeMetadata, NodeParameter
from kailash.sdk_exceptions import NodeValidationError


class NodeWithSchemaTest(Node):
    """Test node with output schema defined."""

    metadata = NodeMetadata(
        name="NodeWithSchemaTest", description="Test node with output schema"
    )

    def configure(self, **kwargs):
        # Provide default config if not specified
        if "input_value" not in kwargs:
            kwargs["input_value"] = 42
        super().configure(**kwargs)

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "input_value": NodeParameter(
                name="input_value",
                type=int,
                required=True,
                description="Input integer value",
            )
        }

    def get_output_schema(self) -> dict[str, NodeParameter]:
        return {
            "result": NodeParameter(
                name="result", type=int, required=True, description="Processed result"
            ),
            "status": NodeParameter(
                name="status", type=str, required=True, description="Processing status"
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=False,
                description="Optional metadata",
            ),
        }

    def run(self, input_value: int) -> dict[str, Any]:
        return {"result": input_value * 2, "status": "success"}


class NodeWithoutSchemaTest(Node):
    """Test node without output schema (default behavior)."""

    metadata = NodeMetadata(
        name="NodeWithoutSchemaTest", description="Test node without output schema"
    )

    def configure(self, **kwargs):
        # Provide default config if not specified
        if "input_value" not in kwargs:
            kwargs["input_value"] = 42
        super().configure(**kwargs)

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "input_value": NodeParameter(
                name="input_value",
                type=int,
                required=True,
                description="Input integer value",
            )
        }

    def run(self, input_value: int) -> dict[str, Any]:
        return {
            "result": input_value * 2,
            "status": "success",
            "extra_field": "not in schema",
        }


def test_output_schema_validation():
    """Test output schema validation functionality."""
    print("Testing output schema validation...")

    # Test 1: Valid outputs with schema
    print("\n1. Testing valid outputs with schema...")
    try:
        node = NodeWithSchemaTest()
        outputs = {"result": 42, "status": "success"}
        validated = node.validate_outputs(outputs)
        print(f"✓ Valid outputs accepted: {validated}")
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Test 2: Missing required output
    print("\n2. Testing missing required output...")
    try:
        node = NodeWithSchemaTest()
        outputs = {"result": 42}  # Missing required 'status'
        validated = node.validate_outputs(outputs)
        print("✗ Should have failed for missing required output")
        return False
    except NodeValidationError as e:
        print(f"✓ Correctly caught validation error: {e}")

    # Test 3: Type conversion in outputs
    print("\n3. Testing type conversion in outputs...")
    try:
        node = NodeWithSchemaTest()
        outputs = {"result": "42", "status": "success"}  # String instead of int
        validated = node.validate_outputs(outputs)
        print(f"✓ Type conversion successful: {validated}")
        assert validated["result"] == 42  # Converted to int
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False

    # Test 4: Invalid type that can't be converted
    print("\n4. Testing invalid type conversion...")
    try:
        node = NodeWithSchemaTest()
        outputs = {"result": "not_a_number", "status": "success"}
        validated = node.validate_outputs(outputs)
        print("✗ Should have failed for invalid type conversion")
        return False
    except NodeValidationError as e:
        print(f"✓ Correctly caught type error: {e}")

    # Test 5: Optional output handling
    print("\n5. Testing optional output handling...")
    try:
        node = NodeWithSchemaTest()
        outputs = {"result": 42, "status": "success", "metadata": None}
        validated = node.validate_outputs(outputs)
        print(f"✓ Optional None value accepted: {validated}")
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False

    # Test 6: Extra outputs not in schema
    print("\n6. Testing extra outputs not in schema...")
    try:
        node = NodeWithSchemaTest()
        outputs = {
            "result": 42,
            "status": "success",
            "extra_field": "not in schema",
            "another_extra": 123,
        }
        validated = node.validate_outputs(outputs)
        print(f"✓ Extra fields preserved: {validated}")
        assert "extra_field" in validated
        assert "another_extra" in validated
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False

    # Test 7: Node without schema (default behavior)
    print("\n7. Testing node without output schema...")
    try:
        node = NodeWithoutSchemaTest()
        outputs = node.execute(input_value=21)
        validated = node.validate_outputs(outputs)
        print(f"✓ No schema validation, only JSON check: {validated}")
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False

    # Test 8: Non-JSON-serializable output
    print("\n8. Testing non-JSON-serializable output...")
    try:
        node = NodeWithoutSchemaTest()
        outputs = {
            "result": 42,
            "bad_value": lambda x: x,
        }  # Function is not serializable
        validated = node.validate_outputs(outputs)
        print("✗ Should have failed for non-serializable value")
        return False
    except NodeValidationError as e:
        print(f"✓ Correctly caught serialization error: {e}")

    print("\n✅ All output schema validation tests passed!")


# Test the actual node execution with output validation
def test_node_execution_with_output_validation():
    """Test full node execution with output validation."""
    print("\n\nTesting node execution with output validation...")

    class TestExecutionNode(Node):
        """Node that tests execution with output validation."""

        metadata = NodeMetadata(
            name="TestExecutionNode",
            description="Test execution with output validation",
        )

        def configure(self, **kwargs):
            if "value" not in kwargs:
                kwargs["value"] = 5
            super().configure(**kwargs)

        def get_parameters(self) -> dict[str, NodeParameter]:
            return {"value": NodeParameter(name="value", type=int, required=True)}

        def get_output_schema(self) -> dict[str, NodeParameter]:
            return {
                "doubled": NodeParameter(name="doubled", type=int, required=True),
                "squared": NodeParameter(name="squared", type=int, required=True),
            }

        def run(self, value: int) -> dict[str, Any]:
            return {"doubled": value * 2, "squared": value**2}

    try:
        node = TestExecutionNode(value=5)

        # This should use the full execution pipeline
        result = node.execute()

        print(f"✓ Execution successful with output validation: {result}")
        assert result["doubled"] == 10
        assert result["squared"] == 25

        print("✅ Node execution with output validation works correctly!")

    except Exception as e:
        print(f"✗ Execution failed: {e}")
        import traceback

        traceback.print_exc()
        pytest.fail(f"Node execution failed: {e}")


# Test a node that violates its output schema during execution
def test_schema_violation_during_execution():
    """Test that schema violations are caught during execution."""
    print("\n\nTesting schema violation during execution...")

    class BrokenOutputNode(Node):
        """Node that produces outputs violating its schema."""

        metadata = NodeMetadata(
            name="BrokenOutputNode", description="Node with broken outputs"
        )

        def configure(self, **kwargs):
            if "value" not in kwargs:
                kwargs["value"] = 5
            super().configure(**kwargs)

        def get_parameters(self) -> dict[str, NodeParameter]:
            return {"value": NodeParameter(name="value", type=int, required=True)}

        def get_output_schema(self) -> dict[str, NodeParameter]:
            return {
                "number": NodeParameter(name="number", type=int, required=True),
                "text": NodeParameter(name="text", type=str, required=True),
            }

        def run(self, value: int) -> dict[str, Any]:
            # This violates the schema - missing required 'text' field
            return {"number": value}

    try:
        node = BrokenOutputNode(value=5)

        # This should fail during execution
        node.execute()
        pytest.fail("Should have failed for schema violation")

    except NodeValidationError as e:
        print(f"✓ Correctly caught schema violation during execution: {e}")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        pytest.fail(f"Unexpected error: {e}")


# Remove main execution block for pytest compatibility
