"""Tests for the base node class."""

from typing import Any

import pytest
from kailash.nodes.base import Node, NodeMetadata, NodeParameter
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


class SimpleNode(Node):
    """Simple node for testing."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define input parameters."""
        return {
            "x": NodeParameter(
                name="x",
                type=float,
                required=True,
                description="Input value",
                default=0.0,
            )
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute the node's logic."""
        x = kwargs.get("x", 0)
        return {"y": x * 2}


class NodeWithOptionalParams(Node):
    """Node with optional parameters for testing."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define input parameters."""
        return {
            "x": NodeParameter(
                name="x", type=float, required=True, description="Required input"
            ),
            "y": NodeParameter(
                name="y",
                type=float,
                required=False,
                default=1.0,
                description="Optional input",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute the node's logic."""
        x = kwargs.get("x")
        y = kwargs.get("y", 1.0)
        return {"result": x * y}


class NodeWithoutParams(Node):
    """Node without parameters for testing."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define input parameters."""
        return {}

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute the node's logic."""
        return {"message": "Hello, World!"}


class NodeWithError(Node):
    """Node that raises errors for testing."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define input parameters."""
        return {}

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute the node's logic."""
        raise ValueError("Processing error")


class NodeWithOutputSchema(Node):
    """Node with output schema validation."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define input parameters."""
        return {
            "value": NodeParameter(
                name="value", type=int, required=True, description="Input value"
            )
        }

    def get_output_schema(self) -> dict[str, NodeParameter]:
        """Define output schema."""
        return {
            "double": NodeParameter(
                name="double",
                type=int,
                required=True,
                description="Double the input value",
            ),
            "square": NodeParameter(
                name="square",
                type=int,
                required=True,
                description="Square the input value",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute the node's logic."""
        value = kwargs.get("value", 0)
        return {"double": value * 2, "square": value * value}


class TestBaseNode:
    """Test base node functionality."""

    def test_node_creation_with_params(self):
        """Test creating a node with parameters."""
        # Node with required parameter must provide it at init or runtime
        node = SimpleNode(name="Test Node", x=5.0)
        assert node.metadata.name == "Test Node"
        assert node.config.get("x") == 5.0

    def test_node_creation_without_required_params(self):
        """Test that node creation without required params succeeds (Session 061 behavior)."""
        # NEW BEHAVIOR: Node creation succeeds without required params
        node = SimpleNode(name="Test Node")  # Missing required 'x' parameter - OK
        assert node.metadata.name == "Test Node"

        # Node can run because SimpleNode provides default value in kwargs.get("x", 0)
        # This is the new flexible behavior - nodes handle missing params gracefully
        result = node.execute()  # Works fine with default
        assert result == {"y": 0}  # x defaults to 0, so y = 0 * 2 = 0

    def test_node_with_optional_params(self):
        """Test node with optional parameters."""
        node = NodeWithOptionalParams(name="Test", x=2.0)
        assert node.config.get("x") == 2.0
        assert node.config.get("y") == 1.0  # Default value

        # Test with explicit optional param
        node2 = NodeWithOptionalParams(name="Test", x=3.0, y=4.0)
        assert node2.config.get("y") == 4.0

    def test_node_without_params(self):
        """Test node without parameters."""
        node = NodeWithoutParams(name="No Params")
        assert node.metadata.name == "No Params"
        result = node.execute()
        assert result == {"message": "Hello, World!"}

    def test_validate_inputs_success(self):
        """Test successful input validation."""
        node = SimpleNode(name="Test", x=1.0)
        validated = node.validate_inputs(x=5.0)
        assert validated == {"x": 5.0}

        # Test type conversion
        validated = node.validate_inputs(x="10.5")
        assert validated == {"x": 10.5}
        assert isinstance(validated["x"], float)

    def test_validate_inputs_failure(self):
        """Test input validation failures."""
        node = SimpleNode(name="Test", x=1.0)

        # Test with a node that has no default (create a test case)
        class NodeWithoutDefault(Node):
            def get_parameters(self):
                return {
                    "required_param": NodeParameter(
                        name="required_param",
                        type=str,
                        required=True,
                        description="Required without default",
                    )
                }

            def run(self, **kwargs):
                return {"result": kwargs.get("required_param", "")}

        test_node = NodeWithoutDefault(name="Test")
        with pytest.raises(NodeValidationError) as exc_info:
            test_node.validate_inputs()  # Missing 'required_param'
        assert "Required parameter 'required_param' not provided" in str(exc_info.value)

        # Invalid type that can't be converted
        with pytest.raises(NodeValidationError) as exc_info:
            node.validate_inputs(x="not a number")
        assert "must be of type float" in str(exc_info.value)

    def test_validate_outputs_success(self):
        """Test successful output validation."""
        node = SimpleNode(name="Test", x=1.0)
        outputs = {"y": 10.0}
        validated = node.validate_outputs(outputs)
        assert validated == outputs

    def test_validate_outputs_with_schema(self):
        """Test output validation with schema."""
        node = NodeWithOutputSchema(name="Test", value=5)

        # Valid outputs
        outputs = {"double": 10, "square": 25}
        validated = node.validate_outputs(outputs)
        assert validated == outputs

        # Missing required output
        with pytest.raises(NodeValidationError) as exc_info:
            node.validate_outputs({"double": 10})  # Missing 'square'
        assert "Required output 'square' not provided" in str(exc_info.value)

        # Invalid type
        with pytest.raises(NodeValidationError) as exc_info:
            node.validate_outputs({"double": "ten", "square": 25})
        assert "Output 'double' must be of type int" in str(exc_info.value)

    def test_validate_outputs_json_serializable(self):
        """Test that outputs must be JSON-serializable."""
        node = SimpleNode(name="Test", x=1.0)

        # Non-serializable object
        class NonSerializable:
            pass

        with pytest.raises(NodeValidationError) as exc_info:
            node.validate_outputs({"obj": NonSerializable()})
        assert "must be JSON-serializable" in str(exc_info.value)

    def test_execute_success(self):
        """Test successful node execution."""
        node = SimpleNode(name="Test", x=2.0)

        # Execute with config value
        result = node.execute()
        assert result == {"y": 4.0}

        # Execute with runtime override
        result = node.execute(x=3.0)
        assert result == {"y": 6.0}

    def test_execute_with_invalid_input(self):
        """Test execution with invalid input."""
        node = SimpleNode(name="Test", x=1.0)

        with pytest.raises(NodeValidationError):
            node.execute(x="invalid")

    def test_execute_with_error(self):
        """Test execution that raises an error."""
        node = NodeWithError(name="Error Node")

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute()
        assert "Processing error" in str(exc_info.value)

    def test_get_metadata(self):
        """Test getting node metadata."""
        node = SimpleNode(
            name="Test Node",
            x=1.0,
            description="A test node",
            version="2.0.0",
            author="Test Author",
            tags={"test", "example"},
        )

        metadata = node.metadata
        assert isinstance(metadata, NodeMetadata)
        assert metadata.name == "Test Node"
        assert metadata.description == "A test node"
        assert metadata.version == "2.0.0"
        assert metadata.author == "Test Author"
        assert metadata.tags == {"test", "example"}

    def test_node_to_dict(self):
        """Test converting node to dictionary."""
        node = SimpleNode(name="Test", x=1.0)
        node_dict = node.to_dict()

        assert node_dict["type"] == "SimpleNode"
        assert node_dict["id"] == node.id
        assert "metadata" in node_dict
        assert "config" in node_dict
        assert "parameters" in node_dict

        # Check parameter conversion
        assert node_dict["parameters"]["x"]["type"] == "float"
        assert node_dict["parameters"]["x"]["required"] is True

    def test_node_id_generation(self):
        """Test automatic node ID generation."""
        # Default ID is class name
        node1 = SimpleNode(name="Test", x=1.0)
        assert node1.id == "SimpleNode"

        # Custom ID
        node2 = SimpleNode(_node_id="custom_id", name="Test", x=1.0)
        assert node2.id == "custom_id"


class TestNodeIntegration:
    """Test node integration scenarios."""

    def test_complex_node_workflow(self):
        """Test a more complex node implementation."""

        class DataProcessor(Node):
            """Process data with multiple steps."""

            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "data": NodeParameter(
                        name="data",
                        type=list,
                        required=True,
                        description="Input data list",
                    ),
                    "operation": NodeParameter(
                        name="operation",
                        type=str,
                        required=False,
                        default="sum",
                        description="Operation to perform",
                    ),
                }

            def get_output_schema(self) -> dict[str, NodeParameter]:
                return {
                    "result": NodeParameter(
                        name="result",
                        type=float,
                        required=True,
                        description="Processing result",
                    ),
                    "count": NodeParameter(
                        name="count",
                        type=int,
                        required=True,
                        description="Number of items processed",
                    ),
                }

            def run(self, **kwargs) -> dict[str, Any]:
                data = kwargs.get("data", [])
                operation = kwargs.get("operation", "sum")

                if operation == "sum":
                    result = sum(data)
                elif operation == "mean":
                    result = sum(data) / len(data) if data else 0
                elif operation == "max":
                    result = max(data) if data else 0
                else:
                    raise ValueError(f"Unknown operation: {operation}")

                return {"result": float(result), "count": len(data)}

        # Test the processor
        processor = DataProcessor(name="Processor", data=[1, 2, 3, 4, 5])

        # Test sum operation (default)
        result = processor.execute()
        assert result["result"] == 15.0
        assert result["count"] == 5

        # Test mean operation
        result = processor.execute(operation="mean")
        assert result["result"] == 3.0

        # Test with runtime data override
        result = processor.execute(data=[10, 20, 30], operation="max")
        assert result["result"] == 30.0
        assert result["count"] == 3

    def test_node_inheritance(self):
        """Test node inheritance patterns."""

        class BaseProcessor(Node):
            """Base processor with common functionality."""

            def get_parameters(self) -> dict[str, NodeParameter]:
                params = {
                    "input_data": NodeParameter(
                        name="input_data",
                        type=Any,
                        required=True,
                        description="Input data",
                    )
                }
                # Allow subclasses to add parameters
                params.update(self._get_additional_parameters())
                return params

            def _get_additional_parameters(self) -> dict[str, NodeParameter]:
                """Override in subclasses to add parameters."""
                return {}

            def run(self, **kwargs) -> dict[str, Any]:
                input_data = kwargs.get("input_data")
                processed = self._process(input_data, **kwargs)
                return {"output": processed}

            def _process(self, data: Any, **kwargs) -> Any:
                """Override in subclasses."""
                raise NotImplementedError()

        class StringProcessor(BaseProcessor):
            """Process string data."""

            def _get_additional_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "uppercase": NodeParameter(
                        name="uppercase",
                        type=bool,
                        required=False,
                        default=False,
                        description="Convert to uppercase",
                    )
                }

            def _process(self, data: Any, **kwargs) -> Any:
                result = str(data)
                if kwargs.get("uppercase", False):
                    result = result.upper()
                return result

        # Test the inherited node
        processor = StringProcessor(name="String Proc", input_data="hello")
        result = processor.execute()
        assert result["output"] == "hello"

        result = processor.execute(uppercase=True)
        assert result["output"] == "HELLO"
