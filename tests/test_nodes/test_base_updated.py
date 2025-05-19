"""Tests for the base node class with updated implementation."""

import pytest
from typing import Dict, Any
from datetime import datetime

from kailash.nodes.base import Node, NodeParameter, NodeMetadata
from kailash.sdk_exceptions import NodeValidationError, NodeConfigurationError, NodeExecutionError

# Import PythonCodeNode to ensure it's available
from kailash.nodes.code.python import PythonCodeNode


class SimpleNode(Node):
    """Simple node for testing."""
    
    def __init__(self, **kwargs):
        """Initialize with test metadata."""
        # Add the required parameter with a default to avoid validation errors at init
        if 'x' not in kwargs:
            kwargs['x'] = 0  # Default value for testing
            
        metadata = NodeMetadata(
            name="SimpleNode",
            description="A simple test node"
        )
        super().__init__(metadata=metadata, **kwargs)
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters."""
        return {
            "x": NodeParameter(
                name="x",
                type=float,
                required=True,
                description="Input value",
                default=0  # Add default
            )
        }
    
    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define output schema."""
        return {
            "y": NodeParameter(
                name="y",
                type=float,
                required=True,
                description="Output value"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the node's logic."""
        x = kwargs.get("x", 0)
        return {"y": x * 2}


class NodeWithoutSchemas(Node):
    """Node without schemas for testing defaults."""
    
    def __init__(self, **kwargs):
        """Initialize with test metadata."""
        metadata = NodeMetadata(
            name="NodeWithoutSchemas",
            description="A node without schemas"
        )
        super().__init__(metadata=metadata, **kwargs)
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters."""
        return {}
    
    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the node's logic."""
        return kwargs


class NodeWithError(Node):
    """Node that raises errors for testing."""
    
    def __init__(self, **kwargs):
        """Initialize with test metadata."""
        metadata = NodeMetadata(
            name="NodeWithError",
            description="A node that raises errors"
        )
        super().__init__(metadata=metadata, **kwargs)
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters."""
        return {}
    
    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the node's logic."""
        raise ValueError("Processing error")


class TestBaseNode:
    """Test base node functionality."""
    
    def test_node_creation(self):
        """Test creating a node."""
        node = SimpleNode()
        
        assert node.metadata.name == "SimpleNode"
        assert node.metadata.description == "A simple test node"
        assert isinstance(node.metadata.created_at, datetime)
    
    def test_node_with_config(self):
        """Test creating a node with configuration."""
        node = SimpleNode(output_format="json")
        
        assert node.config["output_format"] == "json"
        assert node.config["x"] == 0  # Default value
    
    def test_get_parameters(self):
        """Test getting node parameters."""
        node = SimpleNode()
        params = node.get_parameters()
        
        assert "x" in params
        assert params["x"].name == "x"
        assert params["x"].type == float
        assert params["x"].required == True
    
    def test_get_output_schema(self):
        """Test getting output schema."""
        node = SimpleNode()
        schema = node.get_output_schema()
        
        assert "y" in schema
        assert schema["y"].name == "y"
        assert schema["y"].type == float
        assert schema["y"].required == True
    
    def test_node_without_schemas(self):
        """Test node without defined schemas."""
        node = NodeWithoutSchemas()
        
        assert node.get_parameters() == {}
        assert node.get_output_schema() == {}
    
    def test_execute_success(self):
        """Test successful node execution."""
        node = SimpleNode(x=42.0)
        result = node.execute()
        
        assert result["y"] == 84.0
    
    def test_execute_with_type_conversion(self):
        """Test execution with automatic type conversion."""
        node = SimpleNode(x="42")  # String will be converted to float
        result = node.execute()
        
        assert result["y"] == 84.0
    
    def test_execute_validation_error(self):
        """Test execution with validation error."""
        # Invalid type that can't be converted
        with pytest.raises(NodeConfigurationError):
            node = SimpleNode(x="not a number")
    
    def test_execute_runtime_error(self):
        """Test execution with runtime error."""
        node = NodeWithError()
        
        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute()
        
        assert "Processing error" in str(exc_info.value)
    
    def test_output_validation(self):
        """Test output validation against schema."""
        node = SimpleNode()
        
        # Valid output
        validated = node.validate_outputs({"y": 42.0})
        assert validated["y"] == 42.0
        
        # Missing required output
        with pytest.raises(NodeValidationError):
            node.validate_outputs({})
        
        # Wrong type
        with pytest.raises(NodeValidationError):
            node.validate_outputs({"y": "not a number"})
    
    def test_to_dict(self):
        """Test node serialization."""
        node = SimpleNode(output_format="json")
        node_dict = node.to_dict()
        
        assert node_dict["type"] == "SimpleNode"
        assert node_dict["metadata"]["name"] == "SimpleNode"
        assert node_dict["config"]["output_format"] == "json"
        assert "parameters" in node_dict
    
    def test_python_code_node_exists(self):
        """Test that PythonCodeNode is available."""
        # Simple function to wrap
        def add(x: int, y: int) -> int:
            return x + y
        
        # Create node from function
        node = PythonCodeNode.from_function(add, name="adder")
        result = node.execute(x=1, y=2)
        
        assert result["result"] == 3  # PythonCodeNode returns {"result": value}
    
    def test_python_code_node_with_schemas(self):
        """Test PythonCodeNode with explicit schemas."""
        def process(data: dict) -> dict:
            return {"count": len(data)}
        
        input_schema = {
            "data": NodeParameter(
                name="data",
                type=dict,
                required=True,
                description="Input data"
            )
        }
        
        output_schema = {
            "count": NodeParameter(
                name="count",
                type=int,
                required=True,
                description="Number of items"
            )
        }
        
        node = PythonCodeNode.from_function(
            process, 
            name="counter",
            input_schema=input_schema,
            output_schema=output_schema
        )
        
        result = node.execute(data={"a": 1, "b": 2})
        assert result["count"] == 2