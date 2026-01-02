"""
Unit tests for the TypedNode base class.

Tests Task 3.2: Node Migration Framework
- TypedNode base class functionality
- Port to parameter conversion
- Enhanced validation
- Backward compatibility
- IDE support features
"""

from typing import Any, Dict, List, Optional, Union
from unittest.mock import Mock

import pytest
from kailash.nodes.base import NodeParameter, TypedNode
from kailash.nodes.ports import InputPort, IntPort, OutputPort, StringPort
from kailash.sdk_exceptions import NodeValidationError


class TestTypedNodeBasics:
    """Test basic TypedNode functionality."""

    def test_simple_typed_node_creation(self):
        """Test creating a simple typed node."""

        class SimpleTypedNode(TypedNode):
            text_input = InputPort[str]("text_input", description="Text input")
            result_output = OutputPort[str](
                "result_output", description="Result output"
            )

            def run(self, **kwargs):
                text = self.text_input.get()
                return {"result_output": text.upper()}

        node = SimpleTypedNode()

        assert hasattr(node, "text_input")
        assert hasattr(node, "result_output")
        assert hasattr(node, "_port_registry")

        # Check port registry
        assert len(node._port_registry.input_ports) == 1
        assert len(node._port_registry.output_ports) == 1
        assert "text_input" in node._port_registry.input_ports
        assert "result_output" in node._port_registry.output_ports

    def test_typed_node_with_config(self):
        """Test typed node initialization with config values."""

        class ConfigTypedNode(TypedNode):
            count = InputPort[int]("count", default=5, description="Count value")
            name = InputPort[str]("name", description="Name value")

            def run(self, **kwargs):
                return {"count": self.count.get(), "name": self.name.get()}

        # Test with config values
        node = ConfigTypedNode(count=10, name="test")

        # Config should be stored
        assert node.config["count"] == 10
        # Note: 'name' goes to metadata, not config due to Node base class handling
        assert node.metadata.name == "test"

    def test_get_parameters_from_ports(self):
        """Test automatic parameter generation from ports."""

        class ParameterTestNode(TypedNode):
            required_text = InputPort[str]("required_text", description="Required text")
            optional_count = InputPort[int](
                "optional_count",
                default=1,
                required=False,
                description="Optional count",
            )
            data_list = InputPort[List[str]]("data_list", description="List of strings")

            def run(self, **kwargs):
                return {}

        node = ParameterTestNode()
        params = node.get_parameters()

        # Check all ports are converted to parameters
        assert len(params) == 3
        assert "required_text" in params
        assert "optional_count" in params
        assert "data_list" in params

        # Check parameter properties
        required_param = params["required_text"]
        assert required_param.name == "required_text"
        assert required_param.type == str
        assert required_param.required is True
        assert required_param.description == "Required text"

        optional_param = params["optional_count"]
        assert optional_param.name == "optional_count"
        assert optional_param.type == int
        assert optional_param.required is False
        assert optional_param.default == 1
        assert optional_param.description == "Optional count"

        list_param = params["data_list"]
        assert list_param.name == "data_list"
        # Note: Generic types are converted to their origin type for NodeParameter compatibility
        assert list_param.type == list

    def test_get_output_schema_from_ports(self):
        """Test automatic output schema generation from ports."""

        class OutputTestNode(TypedNode):
            input_data = InputPort[str]("input_data", description="Input")
            result = OutputPort[str]("result", description="Processed result")
            count = OutputPort[int]("count", description="Result count")
            metadata = OutputPort[Dict[str, Any]](
                "metadata", description="Processing metadata"
            )

            def run(self, **kwargs):
                return {}

        node = OutputTestNode()
        schema = node.get_output_schema()

        # Check all output ports are in schema
        assert len(schema) == 3  # Only output ports
        assert "result" in schema
        assert "count" in schema
        assert "metadata" in schema
        assert "input_data" not in schema  # Input port should not be in output schema

        # Check schema properties
        result_param = schema["result"]
        assert result_param.name == "result"
        assert result_param.type == str
        assert result_param.required is False  # Output ports are not "required"
        assert result_param.description == "Processed result"


class TestTypedNodeValidation:
    """Test enhanced validation features."""

    def test_input_validation_with_ports(self):
        """Test enhanced input validation using ports."""

        class ValidationTestNode(TypedNode):
            text_input = InputPort[str]("text_input", description="Text input")
            number_input = InputPort[int]("number_input", description="Number input")
            optional_input = InputPort[str](
                "optional_input", required=False, description="Optional"
            )

            def run(self, **kwargs):
                return {}

        node = ValidationTestNode()

        # Valid inputs
        validated = node.validate_inputs(text_input="hello", number_input=42)
        assert validated["text_input"] == "hello"
        assert validated["number_input"] == 42

        # Test type conversion
        validated = node.validate_inputs(text_input="hello", number_input="42")
        assert validated["number_input"] == 42  # Should be converted to int

        # Test missing required parameter
        with pytest.raises(
            NodeValidationError, match="Required parameter 'text_input' not provided"
        ):
            node.validate_inputs(number_input=42)

        # Test optional parameter
        validated = node.validate_inputs(
            text_input="hello", number_input=42, optional_input=None
        )
        assert "optional_input" not in validated  # None values should be filtered out

    def test_output_validation_with_ports(self):
        """Test enhanced output validation using ports."""

        class OutputValidationNode(TypedNode):
            input_data = InputPort[str]("input_data")
            result = OutputPort[str]("result", description="String result")
            count = OutputPort[int]("count", description="Integer count")

            def run(self, **kwargs):
                return {}

        node = OutputValidationNode()

        # Valid outputs
        outputs = {"result": "hello", "count": 42}
        validated = node.validate_outputs(outputs)
        assert validated == outputs

        # Test type conversion in outputs
        outputs = {"result": "hello", "count": "42"}
        validated = node.validate_outputs(outputs)
        assert validated["count"] == 42  # Should be converted to int

        # Test invalid output type that can't be converted
        outputs = {"result": "hello", "count": "not_a_number"}
        with pytest.raises(
            NodeValidationError, match="Output 'count' must be of type int"
        ):
            node.validate_outputs(outputs)

    def test_port_constraints_validation(self):
        """Test port constraint validation."""

        class ConstraintTestNode(TypedNode):
            text_input = InputPort[str](
                "text_input",
                constraints={"min_length": 3, "max_length": 10},
                description="Text with length constraints",
            )
            number_input = InputPort[int](
                "number_input",
                constraints={"min_value": 0, "max_value": 100},
                description="Number with range constraints",
            )

            def run(self, **kwargs):
                return {}

        node = ConstraintTestNode()

        # Valid inputs within constraints
        validated = node.validate_inputs(text_input="hello", number_input=50)
        assert validated["text_input"] == "hello"
        assert validated["number_input"] == 50

        # Text too short
        with pytest.raises(NodeValidationError):
            node.validate_inputs(text_input="hi", number_input=50)

        # Text too long
        with pytest.raises(NodeValidationError):
            node.validate_inputs(text_input="this is too long", number_input=50)

        # Number too small
        with pytest.raises(NodeValidationError):
            node.validate_inputs(text_input="hello", number_input=-1)

        # Number too large
        with pytest.raises(NodeValidationError):
            node.validate_inputs(text_input="hello", number_input=101)


class TestTypedNodeExecution:
    """Test execution with port system integration."""

    def test_typed_node_execution_flow(self):
        """Test complete execution flow with ports."""

        class ExecutionTestNode(TypedNode):
            text_input = InputPort[str]("text_input", description="Input text")
            multiplier = InputPort[int](
                "multiplier", default=2, description="Multiplier"
            )
            result = OutputPort[str]("result", description="Result")
            length = OutputPort[int]("length", description="Result length")

            def run(self, **kwargs):
                # Access inputs through ports
                text = self.text_input.get()
                mult = self.multiplier.get()

                # Process
                result_text = text * mult

                # Set outputs through ports (optional, can also return dict)
                self.result.set(result_text)
                self.length.set(len(result_text))

                # Return traditional dict format
                return {"result": result_text, "length": len(result_text)}

        node = ExecutionTestNode()

        # Execute with valid inputs
        result = node.execute(text_input="hello", multiplier=3)

        assert result["result"] == "hellohellohello"
        assert result["length"] == 15

        # Test with default multiplier
        result = node.execute(text_input="hi")
        assert result["result"] == "hihi"
        assert result["length"] == 4

    def test_port_access_during_execution(self):
        """Test accessing port values during execution."""

        class PortAccessNode(TypedNode):
            data = InputPort[str]("data", description="Data input")
            flag = InputPort[bool]("flag", default=True, description="Flag input")
            result = OutputPort[str]("result", description="Result")

            def run(self, **kwargs):
                # Direct port access should work
                data_value = self.data.get()
                flag_value = self.flag.get()

                if flag_value:
                    result_value = data_value.upper()
                else:
                    result_value = data_value.lower()

                return {"result": result_value}

        node = PortAccessNode()

        # Test with flag=True
        result = node.execute(data="Hello World", flag=True)
        assert result["result"] == "HELLO WORLD"

        # Test with flag=False
        result = node.execute(data="Hello World", flag=False)
        assert result["result"] == "hello world"

        # Test with default flag
        result = node.execute(data="Hello World")
        assert result["result"] == "HELLO WORLD"


class TestTypedNodeBackwardCompatibility:
    """Test backward compatibility with existing Node patterns."""

    def test_traditional_parameter_access(self):
        """Test that traditional parameter access still works."""

        class HybridNode(TypedNode):
            port_input = InputPort[str]("port_input", description="Port-based input")

            def get_parameters(self):
                # Override to add traditional parameters alongside ports
                port_params = super().get_parameters()
                port_params.update(
                    {
                        "traditional_param": NodeParameter(
                            name="traditional_param",
                            type=str,
                            required=True,
                            description="Traditional parameter",
                        )
                    }
                )
                return port_params

            def run(self, **kwargs):
                # Should be able to access both port and traditional params
                port_value = self.port_input.get()
                traditional_value = kwargs.get("traditional_param")

                return {
                    "port_result": port_value,
                    "traditional_result": traditional_value,
                }

        node = HybridNode()

        result = node.execute(
            port_input="port_data", traditional_param="traditional_data"
        )

        assert result["port_result"] == "port_data"
        assert result["traditional_result"] == "traditional_data"

    def test_config_initialization_compatibility(self):
        """Test that config-based initialization still works."""

        class ConfigCompatNode(TypedNode):
            param1 = InputPort[str]("param1", description="Parameter 1")
            param2 = InputPort[int]("param2", default=10, description="Parameter 2")

            def run(self, **kwargs):
                return {"param1": self.param1.get(), "param2": self.param2.get()}

        # Initialize with config values
        node = ConfigCompatNode(param1="config_value", param2=20)

        # Should be able to execute without additional parameters
        result = node.execute()
        assert result["param1"] == "config_value"
        assert result["param2"] == 20

        # Runtime parameters should override config
        result = node.execute(param1="runtime_value", param2=30)
        assert result["param1"] == "runtime_value"
        assert result["param2"] == 30


class TestTypedNodeAdvancedFeatures:
    """Test advanced features of TypedNode."""

    def test_complex_type_support(self):
        """Test support for complex types."""

        class ComplexTypeNode(TypedNode):
            string_list = InputPort[List[str]](
                "string_list", description="List of strings"
            )
            optional_data = InputPort[Optional[str]](
                "optional_data", required=False, description="Optional string"
            )
            union_input = InputPort[Union[str, int]](
                "union_input", description="String or int"
            )
            dict_data = InputPort[Dict[str, Any]](
                "dict_data", description="Dictionary data"
            )

            result = OutputPort[Dict[str, Any]](
                "result", description="Processed result"
            )

            def run(self, **kwargs):
                return {
                    "result": {
                        "list_length": len(self.string_list.get()),
                        "optional_provided": (
                            self.optional_data.get() is not None
                            if hasattr(self.optional_data, "_value")
                            and self.optional_data._value is not None
                            else False
                        ),
                        "union_type": type(self.union_input.get()).__name__,
                        "dict_keys": list(self.dict_data.get().keys()),
                    }
                }

        node = ComplexTypeNode()

        result = node.execute(
            string_list=["a", "b", "c"],
            union_input=42,
            dict_data={"key1": "value1", "key2": "value2"},
        )

        expected = {
            "list_length": 3,
            "optional_provided": False,
            "union_type": "int",
            "dict_keys": ["key1", "key2"],
        }
        assert result["result"] == expected

    def test_convenience_port_types(self):
        """Test convenience port type functions."""

        class ConvenienceNode(TypedNode):
            text = StringPort("text", description="String input")
            count = IntPort("count", default=1, description="Integer input")

            def run(self, **kwargs):
                return {"text": self.text.get(), "count": self.count.get()}

        node = ConvenienceNode()

        result = node.execute(text="hello", count=5)
        assert result["text"] == "hello"
        assert result["count"] == 5

        # Test type validation
        result = node.execute(text="hello", count="5")  # Should convert string to int
        assert result["count"] == 5

    def test_port_schema_generation(self):
        """Test port schema generation for tooling."""

        class SchemaNode(TypedNode):
            input1 = InputPort[str](
                "input1",
                description="First input",
                constraints={"min_length": 1},
                examples=["example1"],
            )
            input2 = InputPort[int]("input2", default=10, description="Second input")
            output1 = OutputPort[str]("output1", description="First output")

            def run(self, **kwargs):
                return {"output1": "result"}

        node = SchemaNode()
        schema = node.get_port_schema()

        assert "input_ports" in schema
        assert "output_ports" in schema

        # Check input port schema
        input1_schema = schema["input_ports"]["input1"]
        assert input1_schema["name"] == "input1"
        assert input1_schema["type"] == "str"
        assert input1_schema["metadata"]["description"] == "First input"
        assert input1_schema["metadata"]["constraints"]["min_length"] == 1
        assert input1_schema["metadata"]["examples"] == ["example1"]

        # Check output port schema
        output1_schema = schema["output_ports"]["output1"]
        assert output1_schema["name"] == "output1"
        assert output1_schema["type"] == "str"
        assert output1_schema["metadata"]["description"] == "First output"

    def test_enhanced_serialization(self):
        """Test enhanced node serialization with port information."""

        class SerializationNode(TypedNode):
            input_param = InputPort[str]("input_param", description="Input parameter")
            output_param = OutputPort[int](
                "output_param", description="Output parameter"
            )

            def run(self, **kwargs):
                return {"output_param": 42}

        node = SerializationNode(name="TestNode", description="Test node")
        node_dict = node.to_dict()

        # Check base serialization
        assert node_dict["id"] == "SerializationNode"
        assert node_dict["type"] == "SerializationNode"
        assert node_dict["metadata"]["name"] == "TestNode"

        # Check port schema is included
        assert "port_schema" in node_dict
        assert "input_ports" in node_dict["port_schema"]
        assert "output_ports" in node_dict["port_schema"]
        assert "input_param" in node_dict["port_schema"]["input_ports"]
        assert "output_param" in node_dict["port_schema"]["output_ports"]


class TestErrorHandling:
    """Test error handling in TypedNode."""

    def test_port_validation_errors(self):
        """Test that port validation errors are properly handled."""

        class ErrorTestNode(TypedNode):
            strict_input = InputPort[int]("strict_input", description="Must be integer")

            def run(self, **kwargs):
                return {"result": self.strict_input.get()}

        node = ErrorTestNode()

        # Test type conversion failure
        with pytest.raises(
            NodeValidationError, match="Input 'strict_input' must be of type int"
        ):
            node.execute(strict_input="not_a_number")

    def test_port_access_errors(self):
        """Test errors when accessing unset ports."""

        class AccessErrorNode(TypedNode):
            required_input = InputPort[str](
                "required_input", description="Required input"
            )

            def run(self, **kwargs):
                # This should fail because required_input wasn't provided
                return {"result": self.required_input.get()}

        node = AccessErrorNode()

        with pytest.raises(
            NodeValidationError,
            match="Required parameter 'required_input' not provided",
        ):
            node.execute()  # No inputs provided
