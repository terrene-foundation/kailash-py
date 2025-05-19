"""Tests for the base node class."""

import pytest
from typing import Dict, Any
from datetime import datetime

from kailash.nodes.base import Node, NodeParameter
from kailash.sdk_exceptions import NodeValidationError, NodeConfigurationError


class SimpleNode(Node):
    """Simple node for testing."""
    
    INPUT_SCHEMA = {"type": "object", "properties": {"x": {"type": "number"}}}
    OUTPUT_SCHEMA = {"type": "object", "properties": {"y": {"type": "number"}}}
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters."""
        return {
            "x": NodeParameter(
                name="x",
                type=float,
                required=True,
                description="Input value"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the node's logic."""
        x = kwargs.get("x", 0)
        return {"y": x * 2}


class NodeWithoutSchemas(Node):
    """Node without schemas for testing defaults."""
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters."""
        return {}
    
    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the node's logic."""
        return kwargs


class NodeWithError(Node):
    """Node that raises errors for testing."""
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters."""
        return {}
    
    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the node's logic."""
        raise ValueError("Processing error")


class TestNodeConfig:
    """Test NodeConfig class."""
    
    def test_node_config_creation(self):
        """Test creating a node configuration."""
        config = NodeConfig(
            node_id="test-node",
            name="Test Node",
            version="1.0.0",
            description="A test node",
            dependencies=["dep1", "dep2"]
        )
        
        assert config.node_id == "test-node"
        assert config.name == "Test Node"
        assert config.version == "1.0.0"
        assert config.description == "A test node"
        assert config.dependencies == ["dep1", "dep2"]
    
    def test_node_config_defaults(self):
        """Test default values in node configuration."""
        config = NodeConfig(node_id="test", name="Test")
        
        assert config.version == "1.0.0"
        assert config.description == ""
        assert config.dependencies == []
    
    def test_node_config_dict_conversion(self):
        """Test converting config to/from dict."""
        config = NodeConfig(
            node_id="test",
            name="Test",
            version="2.0.0",
            description="Test node"
        )
        
        config_dict = config.dict()
        assert config_dict["node_id"] == "test"
        assert config_dict["version"] == "2.0.0"
        
        # Test recreating from dict
        new_config = NodeConfig(**config_dict)
        assert new_config == config


class TestBaseNode:
    """Test BaseNode class."""
    
    def test_node_creation_with_params(self):
        """Test creating a node with parameters."""
        node = SimpleNode(node_id="test", name="Test Node")
        
        assert node.node_id == "test"
        assert node.name == "Test Node"
        assert node.version == "1.0.0"
        assert node.description == ""
    
    def test_node_creation_with_config(self):
        """Test creating a node with configuration."""
        config = NodeConfig(
            node_id="test",
            name="Test Node",
            version="2.0.0",
            description="A test"
        )
        node = SimpleNode(config=config)
        
        assert node.node_id == "test"
        assert node.name == "Test Node"
        assert node.version == "2.0.0"
        assert node.description == "A test"
    
    def test_invalid_creation(self):
        """Test invalid node creation."""
        # Must provide either parameters or config
        with pytest.raises(KailashConfigError):
            SimpleNode()
        
        # Cannot provide both
        config = NodeConfig(node_id="test", name="Test")
        with pytest.raises(KailashConfigError):
            SimpleNode(config=config, node_id="test2", name="Test2")
    
    def test_default_schemas(self):
        """Test default input/output schemas."""
        node = NodeWithoutSchemas(node_id="test", name="Test")
        
        # Should have default empty object schemas
        assert node.INPUT_SCHEMA == {"type": "object"}
        assert node.OUTPUT_SCHEMA == {"type": "object"}
    
    def test_validate_input_success(self):
        """Test successful input validation."""
        node = SimpleNode(node_id="test", name="Test")
        
        # Valid input
        node.validate_input({"x": 42})
        node.validate_input({"x": 3.14})
        node.validate_input({"x": -10})
    
    def test_validate_input_failure(self):
        """Test input validation failures."""
        node = SimpleNode(node_id="test", name="Test")
        
        # Invalid type
        with pytest.raises(KailashValidationError):
            node.validate_input({"x": "not a number"})
        
        # Missing required field
        with pytest.raises(KailashValidationError):
            node.validate_input({})
        
        # Invalid structure
        with pytest.raises(KailashValidationError):
            node.validate_input("not an object")
    
    def test_validate_output_success(self):
        """Test successful output validation."""
        node = SimpleNode(node_id="test", name="Test")
        
        # Valid output
        node.validate_output({"y": 42})
        node.validate_output({"y": 3.14})
    
    def test_validate_output_failure(self):
        """Test output validation failures."""
        node = SimpleNode(node_id="test", name="Test")
        
        # Invalid type
        with pytest.raises(KailashValidationError):
            node.validate_output({"y": "not a number"})
        
        # Missing required field
        with pytest.raises(KailashValidationError):
            node.validate_output({})
    
    def test_execute_success(self):
        """Test successful node execution."""
        node = SimpleNode(node_id="test", name="Test")
        
        result = node.execute({"x": 21})
        assert result == {"y": 42}
        
        # Test with float
        result = node.execute({"x": 3.5})
        assert result == {"y": 7.0}
    
    def test_execute_with_invalid_input(self):
        """Test execution with invalid input."""
        node = SimpleNode(node_id="test", name="Test")
        
        with pytest.raises(KailashValidationError):
            node.execute({"x": "invalid"})
    
    def test_execute_with_invalid_output(self):
        """Test execution that produces invalid output."""
        class BadOutputNode(BaseNode):
            OUTPUT_SCHEMA = {"type": "object", "properties": {"y": {"type": "string"}}}
            
            def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
                return {"y": 42}  # Returns number instead of string
        
        node = BadOutputNode(node_id="test", name="Test")
        
        with pytest.raises(KailashValidationError):
            node.execute({})
    
    def test_execute_with_error(self):
        """Test execution that raises an error."""
        node = NodeWithError(node_id="test", name="Test")
        
        with pytest.raises(ValueError, match="Processing error"):
            node.execute({})
    
    def test_get_metadata(self):
        """Test getting node metadata."""
        node = SimpleNode(
            node_id="test",
            name="Test Node",
            version="1.5.0",
            description="Test description"
        )
        
        metadata = node.get_metadata()
        
        assert metadata["node_id"] == "test"
        assert metadata["name"] == "Test Node"
        assert metadata["node_type"] == "SimpleNode"
        assert metadata["version"] == "1.5.0"
        assert metadata["description"] == "Test description"
        assert metadata["input_schema"] == node.INPUT_SCHEMA
        assert metadata["output_schema"] == node.OUTPUT_SCHEMA
        assert "created_at" in metadata
        
        # Verify created_at is a valid timestamp
        created_at = datetime.fromisoformat(metadata["created_at"])
        assert isinstance(created_at, datetime)
    
    def test_node_equality(self):
        """Test node equality comparison."""
        node1 = SimpleNode(node_id="test", name="Test")
        node2 = SimpleNode(node_id="test", name="Test")
        node3 = SimpleNode(node_id="different", name="Test")
        
        assert node1 == node2  # Same ID
        assert node1 != node3  # Different ID
        assert node1 != "not a node"  # Different type


class TestNodeIntegration:
    """Integration tests for node functionality."""
    
    def test_complex_node_workflow(self):
        """Test a complex node with multiple features."""
        class ComplexNode(BaseNode):
            INPUT_SCHEMA = {
                "type": "object",
                "properties": {
                    "numbers": {
                        "type": "array",
                        "items": {"type": "number"}
                    },
                    "operation": {
                        "type": "string",
                        "enum": ["sum", "product"]
                    }
                },
                "required": ["numbers", "operation"]
            }
            OUTPUT_SCHEMA = {
                "type": "object",
                "properties": {
                    "result": {"type": "number"},
                    "count": {"type": "integer"}
                }
            }
            
            def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
                numbers = data["numbers"]
                operation = data["operation"]
                
                if operation == "sum":
                    result = sum(numbers)
                else:
                    result = 1
                    for num in numbers:
                        result *= num
                
                return {
                    "result": result,
                    "count": len(numbers)
                }
        
        node = ComplexNode(node_id="complex", name="Complex Node")
        
        # Test sum operation
        result = node.execute({
            "numbers": [1, 2, 3, 4],
            "operation": "sum"
        })
        assert result["result"] == 10
        assert result["count"] == 4
        
        # Test product operation
        result = node.execute({
            "numbers": [2, 3, 4],
            "operation": "product"
        })
        assert result["result"] == 24
        assert result["count"] == 3
        
        # Test with invalid operation
        with pytest.raises(KailashValidationError):
            node.execute({
                "numbers": [1, 2],
                "operation": "invalid"
            })
    
    def test_node_inheritance(self):
        """Test node inheritance patterns."""
        class BaseProcessor(BaseNode):
            """Base processor node."""
            
            INPUT_SCHEMA = {"type": "object", "properties": {"data": {"type": "string"}}}
            
            def preprocess(self, data: str) -> str:
                """Preprocess data."""
                return data.strip().lower()
        
        class SpecificProcessor(BaseProcessor):
            """Specific processor extending base."""
            
            OUTPUT_SCHEMA = {"type": "object", "properties": {"processed": {"type": "string"}}}
            
            def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
                """Process data with preprocessing."""
                processed = self.preprocess(data["data"])
                return {"processed": processed.upper()}
        
        node = SpecificProcessor(node_id="specific", name="Specific Processor")
        
        result = node.execute({"data": "  HELLO WORLD  "})
        assert result["processed"] == "HELLO WORLD"