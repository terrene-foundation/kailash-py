"""
Unit tests for the typed port system.

Tests Task 3.1: Port System Design
- InputPort and OutputPort classes
- Generic type support
- Port declaration in nodes
- IDE autocomplete support
- Type validation and constraints
"""

from typing import Any, Dict, List, Optional, Union
from unittest.mock import Mock

import pytest
from kailash.nodes.ports import (
    BoolOutput,
    BoolPort,
    DictOutput,
    DictPort,
    FloatOutput,
    FloatPort,
    InputPort,
    IntOutput,
    IntPort,
    ListOutput,
    ListPort,
    OutputPort,
    Port,
    PortMetadata,
    PortRegistry,
    StringOutput,
    StringPort,
    get_port_registry,
)


class TestPortMetadata:
    """Test PortMetadata functionality."""

    def test_basic_metadata_creation(self):
        """Test creating basic port metadata."""
        metadata = PortMetadata(
            name="test_port",
            description="A test port",
            required=True,
            default="default_value",
        )

        assert metadata.name == "test_port"
        assert metadata.description == "A test port"
        assert metadata.required is True
        assert metadata.default == "default_value"
        assert metadata.constraints == {}
        assert metadata.examples == []

    def test_metadata_serialization(self):
        """Test metadata to_dict conversion."""
        metadata = PortMetadata(
            name="test_port",
            description="Test description",
            constraints={"min_length": 5},
            examples=["example1", "example2"],
        )

        result = metadata.to_dict()

        assert result["name"] == "test_port"
        assert result["description"] == "Test description"
        assert result["constraints"]["min_length"] == 5
        assert result["examples"] == ["example1", "example2"]


class TestInputPort:
    """Test InputPort functionality."""

    def test_basic_input_port_creation(self):
        """Test creating a basic input port."""
        port = InputPort[str](
            name="text_input",
            description="Text input port",
            required=True,
            default="default_text",
        )

        assert port.name == "text_input"
        assert port.metadata.description == "Text input port"
        assert port.metadata.required is True
        assert port.metadata.default == "default_text"

    def test_input_port_type_validation(self):
        """Test type validation for input ports."""
        port = InputPort[int]("number_input")
        port._type_hint = int  # Set type hint manually for test

        # Valid type
        assert port.validate_type(42) is True

        # Invalid type
        assert port.validate_type("not a number") is False

        # None handling
        port_optional = InputPort[int]("optional_input", required=False)
        port_optional._type_hint = int
        assert port_optional.validate_type(None) is True

        port_required = InputPort[int]("required_input", required=True)
        port_required._type_hint = int
        assert port_required.validate_type(None) is False

    def test_input_port_set_get(self):
        """Test setting and getting values from input ports."""
        port = InputPort[str]("text_input", default="default")

        # Test default value
        assert port.get() == "default"

        # Test setting value
        port.set("new_value")
        assert port.get() == "new_value"

        # Test is_connected
        assert port.is_connected() is True

    def test_input_port_required_validation(self):
        """Test required port validation."""
        port = InputPort[str]("required_input", required=True)

        # Should raise error if no value and no default
        with pytest.raises(
            ValueError, match="Required input port 'required_input' has no value"
        ):
            port.get()

    def test_input_port_type_error(self):
        """Test type error when setting wrong type."""
        port = InputPort[int]("number_input")

        with pytest.raises(TypeError, match="expects int, got str"):
            port.set("not a number")

    def test_input_port_constraints(self):
        """Test input port constraint validation."""
        port = InputPort[str](
            "text_input", constraints={"min_length": 5, "max_length": 10}
        )

        # Valid value
        port.set("hello")
        assert port.get() == "hello"

        # Too short
        with pytest.raises(ValueError, match="constraint violation"):
            port.set("hi")

        # Too long
        with pytest.raises(ValueError, match="constraint violation"):
            port.set("this is too long")

    def test_input_port_numeric_constraints(self):
        """Test numeric constraint validation."""
        port = InputPort[int](
            "number_input", constraints={"min_value": 0, "max_value": 100}
        )

        # Valid value
        port.set(50)
        assert port.get() == 50

        # Too small
        with pytest.raises(ValueError, match="constraint violation"):
            port.set(-1)

        # Too large
        with pytest.raises(ValueError, match="constraint violation"):
            port.set(101)

    def test_input_port_pattern_constraint(self):
        """Test pattern constraint validation."""
        port = InputPort[str](
            "email_input",
            constraints={
                "pattern": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            },
        )

        # Valid email
        port.set("test@example.com")
        assert port.get() == "test@example.com"

        # Invalid email
        with pytest.raises(ValueError, match="constraint violation"):
            port.set("not-an-email")


class TestOutputPort:
    """Test OutputPort functionality."""

    def test_basic_output_port_creation(self):
        """Test creating a basic output port."""
        port = OutputPort[str](name="text_output", description="Text output port")

        assert port.name == "text_output"
        assert port.metadata.description == "Text output port"
        assert port.metadata.required is False  # Output ports are never required

    def test_output_port_type_validation(self):
        """Test type validation for output ports."""
        port = OutputPort[int]("number_output")

        # Valid type
        assert port.validate_type(42) is True

        # Invalid type
        assert port.validate_type("not a number") is False

    def test_output_port_set_get(self):
        """Test setting and getting values from output ports."""
        port = OutputPort[str]("text_output")

        # Initially no value
        assert port.has_value() is False

        with pytest.raises(ValueError, match="has no value"):
            port.get()

        # Set and get value
        port.set("output_value")
        assert port.has_value() is True
        assert port.get() == "output_value"

    def test_output_port_type_error(self):
        """Test type error when setting wrong type."""
        port = OutputPort[int]("number_output")

        with pytest.raises(TypeError, match="expects int, got str"):
            port.set("not a number")

    def test_output_port_constraints(self):
        """Test output port constraint validation."""
        port = OutputPort[str](
            "text_output", constraints={"min_length": 3, "max_length": 10}
        )

        # Valid value
        port.set("hello")
        assert port.get() == "hello"

        # Too short
        with pytest.raises(ValueError, match="constraint violation"):
            port.set("hi")


class TestComplexTypes:
    """Test ports with complex type hints."""

    def test_list_type_port(self):
        """Test port with List type."""
        port = InputPort[List[str]]("string_list")

        # Valid list
        port.set(["a", "b", "c"])
        assert port.get() == ["a", "b", "c"]

        # Invalid - not a list
        assert port.validate_type("not a list") is False

        # Invalid - wrong element type
        assert port.validate_type([1, 2, 3]) is False

    def test_dict_type_port(self):
        """Test port with Dict type."""
        port = InputPort[Dict[str, int]]("string_int_dict")

        # Valid dict
        port.set({"a": 1, "b": 2})
        assert port.get() == {"a": 1, "b": 2}

        # Invalid - not a dict
        assert port.validate_type(["not", "a", "dict"]) is False

        # Invalid - wrong value type
        assert port.validate_type({"a": "not_int"}) is False

    def test_union_type_port(self):
        """Test port with Union type."""
        port = InputPort[Union[str, int]]("string_or_int")

        # Valid string
        port.set("hello")
        assert port.get() == "hello"

        # Valid int
        port.set(42)
        assert port.get() == 42

        # Invalid type
        assert port.validate_type([1, 2, 3]) is False

    def test_optional_type_port(self):
        """Test port with Optional type."""
        port = InputPort[Optional[str]]("optional_string", required=False)

        # Valid string
        port.set("hello")
        assert port.get() == "hello"

        # Valid None
        port.set(None)
        assert port.get() is None

        # Should accept None
        assert port.validate_type(None) is True


class TestPortDescriptor:
    """Test port descriptor protocol."""

    def test_port_descriptor_binding(self):
        """Test that ports bind correctly to class instances."""

        class TestNode:
            text_input = InputPort[str]("text_input")
            number_output = OutputPort[int]("number_output")

        # Class-level access returns the port
        assert isinstance(TestNode.text_input, InputPort)
        assert isinstance(TestNode.number_output, OutputPort)

        # Instance-level access returns bound port
        node = TestNode()
        bound_input = node.text_input
        bound_output = node.number_output

        assert isinstance(bound_input, InputPort)
        assert isinstance(bound_output, OutputPort)
        assert bound_input._node_instance is node
        assert bound_output._node_instance is node

    def test_port_name_inference(self):
        """Test that port names are inferred from attribute names."""

        class TestNode:
            my_input = InputPort[str]("different_name")

        # Should use attribute name, not constructor name
        port = TestNode.my_input
        assert port.name == "my_input"


class TestPortRegistry:
    """Test PortRegistry functionality."""

    def test_port_registry_scanning(self):
        """Test that registry correctly scans for ports."""

        class TestNode:
            input1 = InputPort[str]("input1")
            input2 = InputPort[int]("input2")
            output1 = OutputPort[str]("output1")
            output2 = OutputPort[float]("output2")
            not_a_port = "regular_attribute"

        registry = PortRegistry(TestNode)

        assert len(registry.input_ports) == 2
        assert len(registry.output_ports) == 2

        assert "input1" in registry.input_ports
        assert "input2" in registry.input_ports
        assert "output1" in registry.output_ports
        assert "output2" in registry.output_ports

    def test_port_registry_validation(self):
        """Test port registry input/output validation."""

        class TestNode:
            text_input = InputPort[str]("text_input", required=True)
            number_input = InputPort[int]("number_input", default=42)
            text_output = OutputPort[str]("text_output")

        registry = PortRegistry(TestNode)

        # Valid inputs
        errors = registry.validate_input_types(
            {"text_input": "hello", "number_input": 10}
        )
        assert len(errors) == 0

        # Missing required input
        errors = registry.validate_input_types({"number_input": 10})
        assert len(errors) == 1
        assert "required" in errors[0].lower()

        # Set type hints for test
        TestNode.text_input._type_hint = str
        TestNode.number_input._type_hint = int
        TestNode.text_output._type_hint = str

        # Wrong type
        errors = registry.validate_input_types({"text_input": 123})
        assert len(errors) == 1
        assert "expects str, got int" in errors[0]

        # Valid outputs
        errors = registry.validate_output_types({"text_output": "result"})
        assert len(errors) == 0

        # Wrong output type
        errors = registry.validate_output_types({"text_output": 123})
        assert len(errors) == 1
        assert "expects str, got int" in errors[0]

    def test_port_schema_generation(self):
        """Test port schema generation."""

        class TestNode:
            text_input = InputPort[str](
                "text_input", description="Text input", required=True
            )
            result_output = OutputPort[int](
                "result_output", description="Result output"
            )

        registry = PortRegistry(TestNode)
        schema = registry.get_port_schema()

        assert "input_ports" in schema
        assert "output_ports" in schema

        input_schema = schema["input_ports"]["text_input"]
        assert input_schema["name"] == "text_input"
        assert input_schema["type"] == "str"
        assert input_schema["metadata"]["description"] == "Text input"
        assert input_schema["metadata"]["required"] is True

        output_schema = schema["output_ports"]["result_output"]
        assert output_schema["name"] == "result_output"
        assert output_schema["type"] == "int"
        assert output_schema["metadata"]["description"] == "Result output"

    def test_get_port_registry_caching(self):
        """Test that port registry is cached per class."""

        class TestNode:
            input1 = InputPort[str]("input1")

        registry1 = get_port_registry(TestNode)
        registry2 = get_port_registry(TestNode)

        # Should return the same instance
        assert registry1 is registry2
        assert hasattr(TestNode, "_port_registry")


class TestConvenienceTypes:
    """Test convenience type aliases."""

    def test_string_port_alias(self):
        """Test StringPort convenience alias."""
        port = StringPort("text", description="Text input")

        assert isinstance(port, InputPort)
        assert port.validate_type("hello") is True
        assert port.validate_type(123) is False

    def test_int_port_alias(self):
        """Test IntPort convenience alias."""
        port = IntPort("number", description="Number input")

        assert isinstance(port, InputPort)
        assert port.validate_type(42) is True
        assert port.validate_type("not a number") is False

    def test_output_aliases(self):
        """Test output port convenience aliases."""
        string_out = StringOutput("text_out")
        int_out = IntOutput("number_out")

        assert isinstance(string_out, OutputPort)
        assert isinstance(int_out, OutputPort)

        assert string_out.validate_type("hello") is True
        assert int_out.validate_type(42) is True


class TestTypeHints:
    """Test type hint extraction and validation."""

    def test_type_hint_extraction(self):
        """Test extraction of type hints from class annotations."""

        class TestNode:
            text_input: InputPort[str] = InputPort[str]("text_input")
            number_input: InputPort[int] = InputPort[int]("number_input")

        # Type hints should be extracted
        assert TestNode.text_input._type_hint == str
        assert TestNode.number_input._type_hint == int

    def test_type_name_generation(self):
        """Test human-readable type name generation."""
        string_port = InputPort[str]("text")
        string_port._type_hint = str
        assert string_port.get_type_name() == "str"

        list_port = InputPort[List[str]]("text_list")
        list_port._type_hint = List[str]
        type_name = list_port.get_type_name()
        assert "List" in type_name or "list" in type_name


class TestPortSerialization:
    """Test port serialization functionality."""

    def test_port_to_dict(self):
        """Test port serialization to dictionary."""
        port = InputPort[str](
            "text_input",
            description="Text input port",
            required=True,
            default="default",
            constraints={"min_length": 5},
            examples=["example1", "example2"],
        )
        port._type_hint = str

        result = port.to_dict()

        assert result["name"] == "text_input"
        assert result["type"] == "str"
        assert result["port_type"] == "InputPort"
        assert result["metadata"]["description"] == "Text input port"
        assert result["metadata"]["required"] is True
        assert result["metadata"]["default"] == "default"
        assert result["metadata"]["constraints"]["min_length"] == 5
        assert result["metadata"]["examples"] == ["example1", "example2"]
