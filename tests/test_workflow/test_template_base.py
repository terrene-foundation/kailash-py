"""Tests for workflow template base classes."""

import pytest

from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow
from kailash.workflow.templates.base import TemplateParameter, WorkflowTemplate


class TestTemplateParameter:
    """Test TemplateParameter with Pydantic V2."""

    def test_basic_parameter(self):
        """Test basic parameter creation."""
        param = TemplateParameter(
            name="input_file", type=str, description="Input file path"
        )

        assert param.name == "input_file"
        assert param.type is str
        assert param.description == "Input file path"
        assert param.required is True
        assert param.default is None
        assert param.choices is None

    def test_parameter_with_defaults(self):
        """Test parameter with default value."""
        param = TemplateParameter(
            name="threshold",
            type=float,
            description="Relevance threshold",
            required=False,
            default=0.7,
        )

        assert param.default == 0.7
        assert param.required is False

    def test_parameter_with_choices(self):
        """Test parameter with constrained choices."""
        param = TemplateParameter(
            name="strategy",
            type=str,
            description="Processing strategy",
            choices=["fast", "balanced", "thorough"],
            default="balanced",
        )

        assert param.choices == ["fast", "balanced", "thorough"]
        assert param.default == "balanced"

    def test_parameter_validation(self):
        """Test parameter value validation."""
        param = TemplateParameter(
            name="count", type=int, description="Item count", choices=[1, 2, 3]
        )

        # Valid value
        assert param.validate_value(2) is True

        # Invalid type
        with pytest.raises(ValueError, match="expects type"):
            param.validate_value("2")

        # Invalid choice
        with pytest.raises(ValueError, match="must be one of"):
            param.validate_value(4)

    def test_default_type_validation(self):
        """Test that default value type is validated."""
        # Valid default
        param = TemplateParameter(
            name="value", type=int, description="Integer value", default=42
        )
        assert param.default == 42

        # Invalid default type
        with pytest.raises(ValueError, match="does not match expected type"):
            TemplateParameter(
                name="value",
                type=int,
                description="Integer value",
                default="42",  # Wrong type
            )

    def test_custom_validation_function(self):
        """Test custom validation function."""

        def validate_positive(value):
            return value > 0

        param = TemplateParameter(
            name="age",
            type=int,
            description="Person's age",
            validation_func=validate_positive,
        )

        # Valid
        assert param.validate_value(25) is True

        # Invalid
        with pytest.raises(ValueError, match="failed custom validation"):
            param.validate_value(-5)


class TestWorkflowTemplate:
    """Test WorkflowTemplate functionality."""

    def test_template_creation(self):
        """Test basic template creation."""
        template = WorkflowTemplate(
            template_id="test_template",
            name="Test Template",
            description="A test workflow template",
            category="testing",
            version="1.0.0",
            author="Test Author",
            tags=["test", "example"],
        )

        assert template.template_id == "test_template"
        assert template.name == "Test Template"
        assert template.category == "testing"
        assert template.version == "1.0.0"
        assert template.author == "Test Author"
        assert template.tags == ["test", "example"]

    def test_add_parameters(self):
        """Test adding parameters to template."""
        template = WorkflowTemplate(
            template_id="param_test",
            name="Parameter Test",
            description="Testing parameters",
        )

        # Add parameters
        param1 = TemplateParameter(
            name="input_path", type=str, description="Input file path"
        )
        param2 = TemplateParameter(
            name="output_path", type=str, description="Output file path"
        )

        template.add_parameter(param1)
        template.add_parameter(param2)

        assert len(template.parameters) == 2
        assert "input_path" in template.parameters
        assert "output_path" in template.parameters

    def test_parameter_validation(self):
        """Test template parameter validation."""
        template = WorkflowTemplate(
            template_id="validation_test",
            name="Validation Test",
            description="Testing validation",
        )

        # Add parameters with different requirements
        template.add_parameter(
            TemplateParameter(
                name="required_param", type=str, description="Required parameter"
            )
        )
        template.add_parameter(
            TemplateParameter(
                name="optional_param",
                type=int,
                description="Optional parameter",
                required=False,
                default=10,
            )
        )

        # Valid parameters
        validated = template.validate_parameters({"required_param": "test"})
        assert validated["required_param"] == "test"
        assert validated["optional_param"] == 10  # Default applied

        # Missing required parameter
        with pytest.raises(ValueError, match="Required parameter"):
            template.validate_parameters({})

        # Unexpected parameter
        with pytest.raises(ValueError, match="Unexpected parameters"):
            template.validate_parameters(
                {"required_param": "test", "unknown_param": "value"}
            )

    def test_workflow_instantiation(self):
        """Test instantiating workflow from template."""
        template = WorkflowTemplate(
            template_id="workflow_test",
            name="Workflow Test",
            description="Testing workflow creation",
        )

        # Add parameter
        template.add_parameter(
            TemplateParameter(
                name="message", type=str, description="Message to process"
            )
        )

        # Define workflow factory
        def create_workflow(message: str) -> Workflow:
            builder = WorkflowBuilder()
            builder.add_node(
                "PythonCodeNode",
                "processor",
                config={"name": "processor", "code": f"print('{message}')"},
            )
            return builder.build(name="Test Workflow")

        template.set_workflow_factory(create_workflow)

        # Instantiate workflow
        workflow = template.instantiate(message="Hello, World!")

        assert workflow is not None
        assert len(workflow.nodes) == 1
        assert "processor" in workflow.nodes

    def test_template_serialization(self):
        """Test template serialization to dict."""
        template = WorkflowTemplate(
            template_id="serial_test",
            name="Serialization Test",
            description="Testing serialization",
            tags=["serialize", "test"],
        )

        template.add_parameter(
            TemplateParameter(
                name="param1",
                type=str,
                description="First parameter",
                choices=["a", "b", "c"],
                default="a",
            )
        )

        # Serialize
        data = template.to_dict()

        assert data["template_id"] == "serial_test"
        assert data["name"] == "Serialization Test"
        assert data["tags"] == ["serialize", "test"]
        assert "param1" in data["parameters"]
        assert data["parameters"]["param1"]["type"] == "str"
        assert data["parameters"]["param1"]["choices"] == ["a", "b", "c"]
        assert data["parameters"]["param1"]["default"] == "a"

    def test_template_deserialization(self):
        """Test creating template from dict."""
        data = {
            "template_id": "deserial_test",
            "name": "Deserialization Test",
            "description": "Testing deserialization",
            "category": "testing",
            "version": "2.0.0",
            "tags": ["load", "test"],
            "parameters": {
                "input": {
                    "type": "str",
                    "description": "Input parameter",
                    "required": True,
                },
                "count": {
                    "type": "int",
                    "description": "Count parameter",
                    "required": False,
                    "default": 5,
                },
            },
        }

        # Create from dict
        template = WorkflowTemplate.from_dict(data)

        assert template.template_id == "deserial_test"
        assert template.version == "2.0.0"
        assert len(template.parameters) == 2
        assert template.parameters["input"].type is str
        assert template.parameters["count"].default == 5

    def test_base_config(self):
        """Test base configuration merging."""
        template = WorkflowTemplate(
            template_id="config_test",
            name="Config Test",
            description="Testing base config",
        )

        # Set base config
        template.set_base_config({"model": "gpt-4", "temperature": 0.7})

        # Add parameter that can override
        template.add_parameter(
            TemplateParameter(
                name="temperature",
                type=float,
                description="Model temperature",
                required=False,
            )
        )

        # Factory that uses config
        def create_workflow(**params) -> Workflow:
            builder = WorkflowBuilder()
            # params will have merged config
            assert "model" in params
            assert params["model"] == "gpt-4"
            return builder.build()

        template.set_workflow_factory(create_workflow)

        # Instantiate without override
        template.instantiate()

        # Instantiate with override
        template.instantiate(temperature=0.3)
