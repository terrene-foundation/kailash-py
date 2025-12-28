"""Tests for template utilities module."""

import pytest
from kailash.utils.templates import NodeTemplate, TemplateManager


class TestNodeTemplate:
    """Test NodeTemplate functionality."""

    def test_node_template_creation(self):
        """Test creating a NodeTemplate."""
        template = NodeTemplate(name="TestNode", description="A test node template")

        assert template.name == "TestNode"
        assert template.description == "A test node template"
        assert template.base_class == "Node"

    def test_node_template_with_custom_base(self):
        """Test NodeTemplate with custom base class."""
        template = NodeTemplate(
            name="CustomNode", description="Custom node", base_class="AsyncNode"
        )

        assert template.name == "CustomNode"
        assert template.base_class == "AsyncNode"

    def test_add_input_parameter(self):
        """Test adding input parameters to template."""
        template = NodeTemplate("TestNode", "Test")

        # Test that method exists and can be called
        result = template.add_input_parameter(
            name="input1", param_type="str", required=True, description="Test input"
        )

        # Method should return self for chaining
        assert result is template
        assert len(template.input_params) == 1

    def test_add_output_parameter(self):
        """Test adding output parameters to template."""
        template = NodeTemplate("TestNode", "Test")

        # Test that method exists and can be called
        result = template.add_output_parameter(
            name="output1", param_type="dict", description="Test output"
        )

        # Method should return self for chaining
        assert result is template
        assert len(template.output_params) == 1


class TestTemplateManager:
    """Test TemplateManager functionality."""

    def test_template_manager_creation(self):
        """Test creating a TemplateManager."""
        manager = TemplateManager()
        assert manager is not None

    def test_template_manager_methods_exist(self):
        """Test that TemplateManager has expected methods."""
        manager = TemplateManager()

        # Test that basic methods exist
        assert hasattr(manager, "create_project")
        assert hasattr(manager, "get_template")
        assert hasattr(manager, "templates")
        assert hasattr(manager, "export_templates")
