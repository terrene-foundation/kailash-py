"""
Unit tests for template parameter resolution utility functions.

Tests the resolve_templates() function for recursive template substitution.
AsyncLocalRuntime execution tests moved to
tests/tier2_integration/runtime/test_template_parameter_resolution_async.py.

Version: v0.9.30
Created: 2025-10-24
"""

import pytest


class TestRecursiveTemplateResolution:
    """Test recursive template resolution utility function."""

    def test_resolve_templates_top_level(self):
        """Test template resolution at top level."""
        from kailash.runtime.template_resolver import resolve_templates

        params = {"limit": "${limit}", "offset": "${offset}"}

        inputs = {"limit": 10, "offset": 0}

        resolved = resolve_templates(params, inputs)

        assert resolved["limit"] == 10
        assert resolved["offset"] == 0

    def test_resolve_templates_nested_dict(self):
        """Test template resolution in nested dictionaries."""
        from kailash.runtime.template_resolver import resolve_templates

        params = {
            "filter": {"run_tag": "${tag}", "status": "${status}"},
            "limit": "${limit}",
        }

        inputs = {"tag": "local", "status": "active", "limit": 10}

        resolved = resolve_templates(params, inputs)

        assert resolved["filter"]["run_tag"] == "local"
        assert resolved["filter"]["status"] == "active"
        assert resolved["limit"] == 10

    def test_resolve_templates_nested_list(self):
        """Test template resolution in lists."""
        from kailash.runtime.template_resolver import resolve_templates

        params = {
            "filters": [{"field": "status", "value": "${status}"}],
            "limit": "${limit}",
        }

        inputs = {"status": "active", "limit": 10}

        resolved = resolve_templates(params, inputs)

        assert resolved["filters"][0]["value"] == "active"
        assert resolved["limit"] == 10

    def test_resolve_templates_deeply_nested(self):
        """Test template resolution in deeply nested structures."""
        from kailash.runtime.template_resolver import resolve_templates

        params = {
            "config": {
                "database": {
                    "connection": {"url": "${db_url}"},
                    "pool_size": "${pool_size}",
                },
                "api": {"endpoint": "${api_endpoint}"},
            }
        }

        inputs = {
            "db_url": "postgresql://localhost",
            "pool_size": 10,
            "api_endpoint": "https://api.example.com",
        }

        resolved = resolve_templates(params, inputs)

        assert (
            resolved["config"]["database"]["connection"]["url"]
            == "postgresql://localhost"
        )
        assert resolved["config"]["database"]["pool_size"] == 10
        assert resolved["config"]["api"]["endpoint"] == "https://api.example.com"

    def test_resolve_templates_missing_input(self):
        """Test that missing inputs are left as templates."""
        from kailash.runtime.template_resolver import resolve_templates

        params = {"value": "${missing_param}"}

        inputs = {}

        resolved = resolve_templates(params, inputs)

        # Should leave template unchanged if input not found
        assert resolved["value"] == "${missing_param}"

    def test_resolve_templates_preserves_non_templates(self):
        """Test that non-template values are preserved."""
        from kailash.runtime.template_resolver import resolve_templates

        params = {
            "static_string": "hello",
            "static_int": 42,
            "static_dict": {"key": "value"},
            "template": "${dynamic}",
        }

        inputs = {"dynamic": "resolved"}

        resolved = resolve_templates(params, inputs)

        assert resolved["static_string"] == "hello"
        assert resolved["static_int"] == 42
        assert resolved["static_dict"] == {"key": "value"}
        assert resolved["template"] == "resolved"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
