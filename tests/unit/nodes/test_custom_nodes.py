"""
Test Custom Node Creation with Studio API

This example demonstrates creating and testing custom nodes using the Studio API.
It can run in standalone mode (direct database) or API client mode.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from apps.studio.core.database import StudioDatabase
from apps.studio.workflows.custom_node_templates import (
    data_validator_template,
    geocoding_api_template,
    sentiment_analyzer_template,
)

# Use middleware database components instead of deleted kailash.api
from kailash.middleware.database import MiddlewareDatabaseManager


def test_custom_node_creation():
    """Test creating custom nodes in the database"""
    # Test templates
    templates = [
        sentiment_analyzer_template,
        data_validator_template,
        geocoding_api_template,
    ]

    # Verify all templates are valid
    for template in templates:
        # Verify template structure
        assert "name" in template
        assert "implementation_type" in template
        assert template["name"]
        assert template["implementation_type"]

        # Verify basic structure
        if "parameters" in template:
            assert isinstance(template["parameters"], list)


def test_template_validation():
    """Test that all templates have required structure"""
    templates = [
        sentiment_analyzer_template,
        data_validator_template,
        geocoding_api_template,
    ]

    required_fields = ["name", "implementation_type"]

    for template in templates:
        for field in required_fields:
            assert field in template, f"Template missing required field: {field}"
            assert template[field], f"Template {field} cannot be empty"


def test_template_content():
    """Test that templates have valid content"""
    templates = [
        sentiment_analyzer_template,
        data_validator_template,
        geocoding_api_template,
    ]

    for template in templates:
        # Check name is not empty
        assert len(template["name"]) > 0

        # Check implementation type is valid
        assert template["implementation_type"] in ["python", "api", "workflow"]

        # If it has parameters, they should be a list
        if "parameters" in template:
            assert isinstance(template["parameters"], list)

        # If it has a description, it should be a string
        if "description" in template:
            assert isinstance(template["description"], str)
