"""Updated tests for base node functionality using current API."""

import pytest
from typing import Dict, Any
from datetime import datetime

from kailash.nodes.base import Node, NodeParameter, NodeMetadata, NodeRegistry, register_node
from kailash.sdk_exceptions import (
    NodeValidationError,
    NodeExecutionError,
    NodeConfigurationError
)


class TestNodeMetadata:
    """Test NodeMetadata class."""
    
    def test_metadata_creation(self):
        """Test creating metadata with default values."""
        metadata = NodeMetadata(name="TestNode")
        
        assert metadata.name == "TestNode"
        assert metadata.description == ""
        assert metadata.version == "1.0.0"
        assert metadata.author == ""
        assert isinstance(metadata.created_at, datetime)
        assert metadata.tags == set()
    
    def test_metadata_with_custom_values(self):
        """Test creating metadata with custom values."""
        metadata = NodeMetadata(
            id="test-node-1",
            name="Test Node",
            description="A test node",
            version="2.0.0",
            author="Test Author",
            tags={"test", "example"}
        )
        
        assert metadata.id == "test-node-1"
        assert metadata.name == "Test Node"
        assert metadata.description == "A test node"
        assert metadata.version == "2.0.0"
        assert metadata.author == "Test Author"
        assert metadata.tags == {"test", "example"}


class TestNodeParameter:
    """Test NodeParameter class."""
    
    def test_required_parameter(self):
        """Test creating a required parameter."""
        param = NodeParameter(
            name="input_data",
            type=str,
            required=True,
            description="Input data parameter"
        )
        
        assert param.name == "input_data"
        assert param.type == str
        assert param.required is True
        assert param.default is None
        assert param.description == "Input data parameter"
    
    def test_optional_parameter_with_default(self):
        """Test creating an optional parameter with default value."""
        param = NodeParameter(
            name="threshold",
            type=float,
            required=False,
            default=0.5,
            description="Threshold value"
        )
        
        assert param.name == "threshold"
        assert param.type == float
        assert param.required is False
        assert param.default == 0.5
        assert param.description == "Threshold value"


class SimpleTestNode(Node):
    """Simple test node for testing base functionality."""
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "text": NodeParameter(
                name="text",
                type=str,
                required=True,
                description="Input text"
            ),
            "multiplier": NodeParameter(
                name="multiplier",
                type=int,
                required=False,
                default=1,
                description="Text repetition multiplier"
            )
        }
    
    def get_output_schema(self) -> Dict[str, NodeParameter]:
        return {
            "result": NodeParameter(
                name="result",
                type=str,
                required=True,
                description="Processed text result"
            ),
            "length": NodeParameter(
                name="length",
                type=int,
                required=True,
                description="Length of result"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        text = kwargs["text"]
        multiplier = kwargs.get("multiplier", 1)
        result = text * multiplier
        
        return {
            "result": result,
            "length": len(result)
        }


class ErrorTestNode(Node):
    """Node that raises errors for testing error handling."""
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "should_fail": NodeParameter(
                name="should_fail",
                type=bool,
                required=False,
                default=False,
                description="Whether to raise an error"
            )
        }
    
    def get_output_schema(self) -> Dict[str, NodeParameter]:
        return {
            "status": NodeParameter(
                name="status",
                type=str,
                required=True,
                description="Execution status"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        if kwargs.get("should_fail", False):
            raise RuntimeError("Intentional test error")
        
        return {"status": "success"}


class TestNode:
    """Test the base Node class functionality."""
    
    def test_node_initialization_minimal(self):
        """Test node initialization with minimal parameters."""
        node = SimpleTestNode(text="hello")
        
        assert node.id == "SimpleTestNode"
        assert node.metadata.name == "SimpleTestNode"
        assert "text" in node.config
        assert node.config["text"] == "hello"
    
    def test_node_initialization_with_metadata(self):
        """Test node initialization with custom metadata."""
        node = SimpleTestNode(
            text="hello",
            id="custom-node",
            name="Custom Node",
            description="A custom test node",
            version="1.2.3",
            author="Test Author"
        )
        
        assert node.id == "custom-node"
        assert node.metadata.name == "Custom Node"
        assert node.metadata.description == "A custom test node"
        assert node.metadata.version == "1.2.3"
        assert node.metadata.author == "Test Author"
    
    def test_node_initialization_missing_required_parameter(self):
        """Test that missing required parameters raise configuration error."""
        with pytest.raises(NodeConfigurationError) as exc_info:
            SimpleTestNode()  # Missing required 'text' parameter
        
        assert "Required parameter 'text' not provided" in str(exc_info.value)
    
    def test_node_execution_success(self):
        """Test successful node execution."""
        node = SimpleTestNode(text="hello")
        result = node.execute(multiplier=3)
        
        assert result["result"] == "hellohellohello"
        assert result["length"] == 15
    
    def test_node_execution_with_defaults(self):
        """Test node execution using default parameter values."""
        node = SimpleTestNode(text="test")
        result = node.execute()
        
        assert result["result"] == "test"
        assert result["length"] == 4
    
    def test_node_execution_runtime_inputs_override(self):
        """Test that runtime inputs override configuration."""
        node = SimpleTestNode(text="hello", multiplier=1)
        result = node.execute(text="world", multiplier=2)
        
        assert result["result"] == "worldworld"
        assert result["length"] == 10
    
    def test_node_execution_with_nested_config(self):
        """Test execution with nested config parameters."""
        node = SimpleTestNode(text="base")
        result = node.execute(config={"text": "nested", "multiplier": 2})
        
        assert result["result"] == "nestednested"
        assert result["length"] == 12
    
    def test_node_execution_error_handling(self):
        """Test that execution errors are properly wrapped."""
        node = ErrorTestNode()
        
        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(should_fail=True)
        
        assert "Intentional test error" in str(exc_info.value)
    
    def test_node_input_validation(self):
        """Test input validation."""
        node = SimpleTestNode(text="test")
        
        # Test missing required input
        with pytest.raises(NodeValidationError) as exc_info:
            node.validate_inputs()
        
        assert "Required input 'text' not provided" in str(exc_info.value)
        
        # Test valid inputs
        validated = node.validate_inputs(text="hello", multiplier=2)
        assert validated["text"] == "hello"
        assert validated["multiplier"] == 2
    
    def test_node_output_validation(self):
        """Test output validation."""
        node = SimpleTestNode(text="test")
        
        # Test valid outputs
        outputs = {"result": "test", "length": 4}
        validated = node.validate_outputs(outputs)
        assert validated == outputs
        
        # Test missing required output
        with pytest.raises(NodeValidationError) as exc_info:
            node.validate_outputs({"result": "test"})  # Missing 'length'
        
        assert "Required output 'length' not provided" in str(exc_info.value)
    
    def test_node_serialization(self):
        """Test node serialization to dictionary."""
        node = SimpleTestNode(
            text="hello",
            id="test-node",
            name="Test Node",
            description="A test node"
        )
        
        node_dict = node.to_dict()
        
        assert node_dict["id"] == "test-node"
        assert node_dict["type"] == "SimpleTestNode"
        assert node_dict["metadata"]["name"] == "Test Node"
        assert node_dict["metadata"]["description"] == "A test node"
        assert node_dict["config"]["text"] == "hello"


@register_node()
class RegisteredTestNode(Node):
    """Test node for registry testing."""
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "value": NodeParameter(
                name="value",
                type=int,
                required=True,
                description="Test value"
            )
        }
    
    def get_output_schema(self) -> Dict[str, NodeParameter]:
        return {
            "doubled": NodeParameter(
                name="doubled",
                type=int,
                required=True,
                description="Value doubled"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"doubled": kwargs["value"] * 2}


class TestNodeRegistry:
    """Test NodeRegistry functionality."""
    
    def test_node_registration(self):
        """Test manual node registration."""
        registry = NodeRegistry()
        registry.register(SimpleTestNode, alias="SimpleNode")
        
        assert "SimpleNode" in NodeRegistry._nodes
        assert NodeRegistry._nodes["SimpleNode"] == SimpleTestNode
    
    def test_decorator_registration(self):
        """Test that @register_node decorator works."""
        # RegisteredTestNode should be automatically registered
        assert "RegisteredTestNode" in NodeRegistry._nodes
        assert NodeRegistry._nodes["RegisteredTestNode"] == RegisteredTestNode
    
    def test_get_registered_node(self):
        """Test getting registered node class."""
        registry = NodeRegistry()
        node_class = registry.get("RegisteredTestNode")
        
        assert node_class == RegisteredTestNode
    
    def test_list_nodes(self):
        """Test listing all registered nodes."""
        registry = NodeRegistry()
        nodes = registry.list_nodes()
        
        assert "RegisteredTestNode" in nodes
        assert isinstance(nodes, dict)
        assert all(issubclass(cls, Node) for cls in nodes.values())
    
    def test_get_nonexistent_node(self):
        """Test getting a node that doesn't exist."""
        registry = NodeRegistry()
        
        with pytest.raises(NodeConfigurationError) as exc_info:
            registry.get("NonExistentNode")
        
        assert "not found in registry" in str(exc_info.value)
        assert "Available nodes:" in str(exc_info.value)
    
    def test_singleton_behavior(self):
        """Test that NodeRegistry is a singleton."""
        registry1 = NodeRegistry()
        registry2 = NodeRegistry()
        
        assert registry1 is registry2


class TestParameterTypes:
    """Test various parameter types and validation."""
    
    def test_list_parameter(self):
        """Test list parameter validation."""
        class ListNode(Node):
            def get_parameters(self) -> Dict[str, NodeParameter]:
                return {
                    "items": NodeParameter(
                        name="items",
                        type=list,
                        required=True,
                        description="List of items"
                    )
                }
            
            def get_output_schema(self) -> Dict[str, NodeParameter]:
                return {
                    "count": NodeParameter(
                        name="count",
                        type=int,
                        required=True,
                        description="Number of items"
                    )
                }
            
            def run(self, **kwargs) -> Dict[str, Any]:
                return {"count": len(kwargs["items"])}
        
        node = ListNode(items=[1, 2, 3])
        result = node.execute()
        assert result["count"] == 3
    
    def test_dict_parameter(self):
        """Test dict parameter validation."""
        class DictNode(Node):
            def get_parameters(self) -> Dict[str, NodeParameter]:
                return {
                    "data": NodeParameter(
                        name="data",
                        type=dict,
                        required=True,
                        description="Dictionary data"
                    )
                }
            
            def get_output_schema(self) -> Dict[str, NodeParameter]:
                return {
                    "keys": NodeParameter(
                        name="keys",
                        type=list,
                        required=True,
                        description="Dictionary keys"
                    )
                }
            
            def run(self, **kwargs) -> Dict[str, Any]:
                return {"keys": list(kwargs["data"].keys())}
        
        node = DictNode(data={"a": 1, "b": 2})
        result = node.execute()
        assert set(result["keys"]) == {"a", "b"}


class TestNodeErrorHandling:
    """Test comprehensive error handling scenarios."""
    
    def test_invalid_configuration_type(self):
        """Test that invalid types are handled during execution."""
        # Note: Type validation may be flexible at init, strict at runtime
        node = SimpleTestNode(text=123)  # Integer instead of string
        # Should work since string conversion is possible
        result = node.execute()
        assert isinstance(result["result"], str)
    
    def test_validation_error_propagation(self):
        """Test that validation errors are properly propagated."""
        # Create a node with missing required parameter
        class StrictNode(Node):
            def get_parameters(self) -> Dict[str, NodeParameter]:
                return {
                    "required_param": NodeParameter(
                        name="required_param",
                        type=str,
                        required=True,
                        description="Required parameter"
                    )
                }
            
            def get_output_schema(self) -> Dict[str, NodeParameter]:
                return {
                    "result": NodeParameter(
                        name="result",
                        type=str,
                        required=True,
                        description="Result"
                    )
                }
            
            def run(self, **kwargs) -> Dict[str, Any]:
                return {"result": kwargs["required_param"]}
        
        # Test missing required parameter at initialization
        with pytest.raises(NodeConfigurationError):
            StrictNode()  # Missing required parameter
    
    def test_execution_error_wrapping(self):
        """Test that runtime errors are wrapped appropriately."""
        node = ErrorTestNode()
        
        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(should_fail=True)
        
        # Check that original error is preserved
        assert "Intentional test error" in str(exc_info.value)
        assert exc_info.value.__cause__.__class__.__name__ == "RuntimeError"


if __name__ == "__main__":
    pytest.main([__file__])