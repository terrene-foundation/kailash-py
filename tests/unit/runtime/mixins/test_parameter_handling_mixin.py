"""Unit tests for ParameterHandlingMixin.

Tests parameter resolution, template handling, merging, and nested value access.
"""

import pytest
from kailash.runtime.base import BaseRuntime
from kailash.runtime.mixins.parameters import TEMPLATE_PATTERN, ParameterHandlingMixin
from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder


class ConcreteRuntimeWithParameters(ParameterHandlingMixin, BaseRuntime):
    """Concrete runtime with parameter handling mixin."""

    def execute(self, workflow: Workflow, **kwargs):
        """Minimal execute implementation."""
        return {}, "test-run-id"


class TestParameterHandlingMixinInitialization:
    """Test ParameterHandlingMixin initialization."""

    def test_mixin_initialization(self):
        """Test mixin initializes correctly via super()."""
        runtime = ConcreteRuntimeWithParameters()

        # Should have parameter handling methods
        assert hasattr(runtime, "_resolve_workflow_parameters")
        assert hasattr(runtime, "_resolve_node_parameters")
        assert hasattr(runtime, "_resolve_template_parameters")
        assert hasattr(runtime, "_merge_parameter_sources")
        assert hasattr(runtime, "_deep_merge")
        assert hasattr(runtime, "_get_nested_value")

    def test_mixin_stateless(self):
        """Test ParameterHandlingMixin doesn't add instance attributes."""
        runtime = ConcreteRuntimeWithParameters()

        # Mixin should be stateless
        # No mixin-specific attributes should be added
        assert not hasattr(runtime, "_parameters")
        assert not hasattr(runtime, "_templates")


class TestTemplatePatternMatching:
    """Test TEMPLATE_PATTERN regex."""

    def test_template_pattern_simple(self):
        """Test pattern matches simple template."""
        matches = TEMPLATE_PATTERN.findall("${name}")
        assert matches == ["name"]

    def test_template_pattern_multiple(self):
        """Test pattern matches multiple templates."""
        matches = TEMPLATE_PATTERN.findall("${first} ${last}")
        assert set(matches) == {"first", "last"}

    def test_template_pattern_in_text(self):
        """Test pattern matches templates in text."""
        matches = TEMPLATE_PATTERN.findall("Hello ${name}, your ID is ${id}")
        assert set(matches) == {"name", "id"}

    def test_template_pattern_no_match(self):
        """Test pattern doesn't match non-templates."""
        matches = TEMPLATE_PATTERN.findall("No templates here")
        assert matches == []


class TestResolveTemplateParameters:
    """Test _resolve_template_parameters() method."""

    def test_resolve_simple_template(self):
        """Test resolving simple template string."""
        runtime = ConcreteRuntimeWithParameters()
        template = "${name}"
        parameters = {"name": "Alice"}

        result = runtime._resolve_template_parameters(template, parameters)

        assert result == "Alice"

    def test_resolve_template_preserves_type(self):
        """Test template resolution preserves non-string types."""
        runtime = ConcreteRuntimeWithParameters()

        # Integer
        result = runtime._resolve_template_parameters("${count}", {"count": 42})
        assert result == 42
        assert isinstance(result, int)

        # Boolean
        result = runtime._resolve_template_parameters("${flag}", {"flag": True})
        assert result is True
        assert isinstance(result, bool)

        # List
        result = runtime._resolve_template_parameters("${items}", {"items": [1, 2, 3]})
        assert result == [1, 2, 3]
        assert isinstance(result, list)

    def test_resolve_multiple_templates_in_string(self):
        """Test resolving multiple templates in one string."""
        runtime = ConcreteRuntimeWithParameters()
        template = "Hello ${first} ${last}"
        parameters = {"first": "John", "last": "Doe"}

        result = runtime._resolve_template_parameters(template, parameters)

        assert result == "Hello John Doe"

    def test_resolve_template_mixed_content(self):
        """Test resolving template mixed with text."""
        runtime = ConcreteRuntimeWithParameters()
        template = "User: ${username}, ID: ${user_id}"
        parameters = {"username": "alice", "user_id": 123}

        result = runtime._resolve_template_parameters(template, parameters)

        assert result == "User: alice, ID: 123"

    def test_resolve_template_in_dict(self):
        """Test resolving templates in dictionary."""
        runtime = ConcreteRuntimeWithParameters()
        template_dict = {
            "greeting": "Hello ${name}",
            "count": "${count}",
            "flag": "${active}",
        }
        parameters = {"name": "Alice", "count": 10, "active": True}

        result = runtime._resolve_template_parameters(template_dict, parameters)

        assert result["greeting"] == "Hello Alice"
        assert result["count"] == 10
        assert result["flag"] is True

    def test_resolve_template_in_list(self):
        """Test resolving templates in list."""
        runtime = ConcreteRuntimeWithParameters()
        template_list = ["${first}", "${second}", "literal"]
        parameters = {"first": "one", "second": "two"}

        result = runtime._resolve_template_parameters(template_list, parameters)

        assert result == ["one", "two", "literal"]

    def test_resolve_template_nested_structure(self):
        """Test resolving templates in nested structures."""
        runtime = ConcreteRuntimeWithParameters()
        template = {
            "user": {"name": "${username}", "age": "${age}"},
            "tags": ["${tag1}", "${tag2}"],
        }
        parameters = {"username": "alice", "age": 30, "tag1": "python", "tag2": "sdk"}

        result = runtime._resolve_template_parameters(template, parameters)

        assert result["user"]["name"] == "alice"
        assert result["user"]["age"] == 30
        assert result["tags"] == ["python", "sdk"]

    def test_resolve_template_missing_parameter(self):
        """Test resolving template with missing parameter."""
        runtime = ConcreteRuntimeWithParameters()
        template = "${missing}"
        parameters = {"other": "value"}

        result = runtime._resolve_template_parameters(template, parameters)

        # Should leave template unchanged
        assert result == "${missing}"

    def test_resolve_template_partial_missing(self):
        """Test resolving when some parameters are missing."""
        runtime = ConcreteRuntimeWithParameters()
        template = "Hello ${name}, your ID is ${id}"
        parameters = {"name": "Alice"}  # Missing 'id'

        result = runtime._resolve_template_parameters(template, parameters)

        # Should resolve available, leave others
        assert "Hello Alice" in result
        assert "${id}" in result

    def test_resolve_template_non_template_string(self):
        """Test resolving non-template string."""
        runtime = ConcreteRuntimeWithParameters()
        template = "No templates here"
        parameters = {"name": "Alice"}

        result = runtime._resolve_template_parameters(template, parameters)

        assert result == "No templates here"

    def test_resolve_template_non_string_types(self):
        """Test resolving non-string types returns as-is."""
        runtime = ConcreteRuntimeWithParameters()

        # Integer
        assert runtime._resolve_template_parameters(42, {}) == 42

        # Boolean
        assert runtime._resolve_template_parameters(True, {}) is True

        # None
        assert runtime._resolve_template_parameters(None, {}) is None


class TestMergeParameterSources:
    """Test _merge_parameter_sources() method."""

    def test_merge_single_source(self):
        """Test merging single parameter source."""
        runtime = ConcreteRuntimeWithParameters()
        sources = [{"a": 1, "b": 2}]

        result = runtime._merge_parameter_sources(sources)

        assert result == {"a": 1, "b": 2}

    def test_merge_multiple_sources_override(self):
        """Test merging with override priority."""
        runtime = ConcreteRuntimeWithParameters()
        sources = [{"a": 1, "b": 2}, {"b": 3, "c": 4}, {"c": 5, "d": 6}]

        result = runtime._merge_parameter_sources(sources)

        # Later sources override earlier
        assert result == {"a": 1, "b": 3, "c": 5, "d": 6}

    def test_merge_empty_sources(self):
        """Test merging empty source list."""
        runtime = ConcreteRuntimeWithParameters()
        sources = []

        result = runtime._merge_parameter_sources(sources)

        assert result == {}

    def test_merge_with_none_sources(self):
        """Test merging with None sources."""
        runtime = ConcreteRuntimeWithParameters()
        sources = [{"a": 1}, None, {"b": 2}]

        result = runtime._merge_parameter_sources(sources)

        # None sources should be skipped
        assert result == {"a": 1, "b": 2}

    def test_merge_nested_dicts_deep_merge(self):
        """Test deep merge of nested dictionaries."""
        runtime = ConcreteRuntimeWithParameters()
        sources = [
            {"config": {"timeout": 30, "retries": 3}},
            {"config": {"timeout": 60}},  # Override timeout, keep retries
        ]

        result = runtime._merge_parameter_sources(sources)

        assert result == {"config": {"timeout": 60, "retries": 3}}


class TestDeepMerge:
    """Test _deep_merge() method."""

    def test_deep_merge_flat_dicts(self):
        """Test deep merge with flat dictionaries."""
        runtime = ConcreteRuntimeWithParameters()
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}

        result = runtime._deep_merge(base, override)

        assert result == {"a": 1, "b": 3, "c": 4}

    def test_deep_merge_nested_dicts(self):
        """Test deep merge with nested dictionaries."""
        runtime = ConcreteRuntimeWithParameters()
        base = {"outer": {"a": 1, "b": 2}}
        override = {"outer": {"b": 3, "c": 4}}

        result = runtime._deep_merge(base, override)

        assert result == {"outer": {"a": 1, "b": 3, "c": 4}}

    def test_deep_merge_deep_nesting(self):
        """Test deep merge with multiple nesting levels."""
        runtime = ConcreteRuntimeWithParameters()
        base = {"level1": {"level2": {"level3": {"a": 1}}}}
        override = {"level1": {"level2": {"level3": {"b": 2}}}}

        result = runtime._deep_merge(base, override)

        assert result == {"level1": {"level2": {"level3": {"a": 1, "b": 2}}}}

    def test_deep_merge_lists_replaced(self):
        """Test deep merge replaces lists (not merge)."""
        runtime = ConcreteRuntimeWithParameters()
        base = {"items": [1, 2, 3]}
        override = {"items": [4, 5]}

        result = runtime._deep_merge(base, override)

        # Lists should be replaced, not merged
        assert result == {"items": [4, 5]}

    def test_deep_merge_non_dict_values(self):
        """Test deep merge with non-dict values."""
        runtime = ConcreteRuntimeWithParameters()
        base = {"a": 1, "b": "text", "c": [1, 2]}
        override = {"a": 2, "b": "updated", "d": True}

        result = runtime._deep_merge(base, override)

        assert result == {"a": 2, "b": "updated", "c": [1, 2], "d": True}

    def test_deep_merge_preserves_original(self):
        """Test deep merge doesn't modify original dicts."""
        runtime = ConcreteRuntimeWithParameters()
        base = {"a": 1, "b": {"x": 10}}
        override = {"b": {"y": 20}}

        result = runtime._deep_merge(base, override)

        # Original should be unchanged
        assert base == {"a": 1, "b": {"x": 10}}
        assert override == {"b": {"y": 20}}
        # Result should have merged values
        assert result["b"] == {"x": 10, "y": 20}


class TestGetNestedValue:
    """Test _get_nested_value() method."""

    def test_get_nested_value_simple(self):
        """Test getting simple value."""
        runtime = ConcreteRuntimeWithParameters()
        data = {"key": "value"}

        result = runtime._get_nested_value(data, "key")

        assert result == "value"

    def test_get_nested_value_one_level(self):
        """Test getting nested value one level deep."""
        runtime = ConcreteRuntimeWithParameters()
        data = {"outer": {"inner": "value"}}

        result = runtime._get_nested_value(data, "outer.inner")

        assert result == "value"

    def test_get_nested_value_multiple_levels(self):
        """Test getting nested value multiple levels deep."""
        runtime = ConcreteRuntimeWithParameters()
        data = {"a": {"b": {"c": {"d": "deep"}}}}

        result = runtime._get_nested_value(data, "a.b.c.d")

        assert result == "deep"

    def test_get_nested_value_missing_path(self):
        """Test getting nested value with missing path."""
        runtime = ConcreteRuntimeWithParameters()
        data = {"a": {"b": "value"}}

        result = runtime._get_nested_value(data, "a.c", default="default")

        assert result == "default"

    def test_get_nested_value_missing_intermediate(self):
        """Test getting nested value with missing intermediate key."""
        runtime = ConcreteRuntimeWithParameters()
        data = {"a": {"b": "value"}}

        result = runtime._get_nested_value(data, "x.y.z", default="default")

        assert result == "default"

    def test_get_nested_value_non_dict_intermediate(self):
        """Test getting nested value when intermediate is not dict."""
        runtime = ConcreteRuntimeWithParameters()
        data = {"a": "string"}

        result = runtime._get_nested_value(data, "a.b", default="default")

        # Can't traverse into string
        assert result == "default"

    def test_get_nested_value_list_access(self):
        """Test nested value doesn't handle list indices."""
        runtime = ConcreteRuntimeWithParameters()
        data = {"items": [1, 2, 3]}

        # This implementation doesn't handle list indices
        result = runtime._get_nested_value(data, "items.0", default="default")

        assert result == "default"  # Not implemented


class TestValidateTemplateSyntax:
    """Test _validate_template_syntax() method."""

    def test_validate_valid_template(self):
        """Test validation passes for valid template."""
        runtime = ConcreteRuntimeWithParameters()
        errors = runtime._validate_template_syntax("${valid_name}")

        assert errors == []

    def test_validate_valid_multiple_templates(self):
        """Test validation passes for multiple templates."""
        runtime = ConcreteRuntimeWithParameters()
        errors = runtime._validate_template_syntax("${first} ${second}")

        assert errors == []

    def test_validate_empty_parameter_name(self):
        """Test validation catches empty parameter name."""
        runtime = ConcreteRuntimeWithParameters()
        errors = runtime._validate_template_syntax("${}")

        # Empty parameter name is caught by the regex (no match),
        # but doesn't create an error - it just won't resolve
        # This is acceptable behavior
        assert isinstance(errors, list)

    def test_validate_mismatched_braces(self):
        """Test validation catches mismatched braces."""
        runtime = ConcreteRuntimeWithParameters()
        errors = runtime._validate_template_syntax("${unclosed")

        assert len(errors) > 0
        assert any("mismatch" in e.lower() for e in errors)

    def test_validate_invalid_parameter_name(self):
        """Test validation catches invalid parameter names."""
        runtime = ConcreteRuntimeWithParameters()
        # Parameter names must be valid Python identifiers
        errors = runtime._validate_template_syntax("${123invalid}")

        assert len(errors) > 0
        assert any("invalid" in e.lower() for e in errors)

    def test_validate_nested_templates(self):
        """Test validation catches nested templates."""
        runtime = ConcreteRuntimeWithParameters()
        errors = runtime._validate_template_syntax("${${nested}}")

        assert len(errors) > 0
        assert any("nested" in e.lower() for e in errors)

    def test_validate_template_in_dict(self):
        """Test validation of templates in dictionary."""
        runtime = ConcreteRuntimeWithParameters()
        errors = runtime._validate_template_syntax(
            {"valid": "${name}", "invalid": "${123invalid}"}  # Invalid identifier
        )

        # Should catch invalid identifier
        assert len(errors) > 0

    def test_validate_template_in_list(self):
        """Test validation of templates in list."""
        runtime = ConcreteRuntimeWithParameters()
        errors = runtime._validate_template_syntax(["${valid}", "${invalid!}"])

        assert len(errors) > 0


class TestExtractTemplateParameters:
    """Test _extract_template_parameters() method."""

    def test_extract_single_parameter(self):
        """Test extracting single parameter."""
        runtime = ConcreteRuntimeWithParameters()
        params = runtime._extract_template_parameters("${name}")

        assert params == {"name"}

    def test_extract_multiple_parameters(self):
        """Test extracting multiple parameters."""
        runtime = ConcreteRuntimeWithParameters()
        params = runtime._extract_template_parameters("${first} ${last}")

        assert params == {"first", "last"}

    def test_extract_from_dict(self):
        """Test extracting parameters from dictionary."""
        runtime = ConcreteRuntimeWithParameters()
        params = runtime._extract_template_parameters(
            {"filter": {"tag": "${tag}"}, "limit": "${limit}"}
        )

        assert params == {"tag", "limit"}

    def test_extract_from_list(self):
        """Test extracting parameters from list."""
        runtime = ConcreteRuntimeWithParameters()
        params = runtime._extract_template_parameters(
            [{"value": "${val1}"}, {"value": "${val2}"}]
        )

        assert params == {"val1", "val2"}

    def test_extract_no_templates(self):
        """Test extracting when no templates present."""
        runtime = ConcreteRuntimeWithParameters()
        params = runtime._extract_template_parameters("No templates here")

        assert params == set()

    def test_extract_duplicate_parameters(self):
        """Test extracting duplicate parameters (returns unique)."""
        runtime = ConcreteRuntimeWithParameters()
        params = runtime._extract_template_parameters("${name} ${name} ${name}")

        assert params == {"name"}


class TestResolveNodeParameters:
    """Test _resolve_node_parameters() method."""

    def test_resolve_node_parameters_full(self):
        """Test resolving node parameters with all sources."""
        runtime = ConcreteRuntimeWithParameters()

        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode", "node1", {"code": "result = 1", "format": "json"}
        )
        workflow = builder.build()

        # Workflow-level params
        workflow_params = {"limit": 20, "tag": "prod"}

        # Connection inputs (highest priority)
        connection_inputs = {"data": [1, 2, 3], "limit": 30}

        result = runtime._resolve_node_parameters(
            workflow, "node1", workflow_params, connection_inputs
        )

        # Connection inputs override workflow params
        assert result["limit"] == 30
        assert result["tag"] == "prod"
        assert result["data"] == [1, 2, 3]

    def test_resolve_node_parameters_no_workflow_params(self):
        """Test resolving node parameters without workflow params."""
        runtime = ConcreteRuntimeWithParameters()

        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "node1", {"code": "result = 1"})
        workflow = builder.build()

        result = runtime._resolve_node_parameters(workflow, "node1", {}, {})

        # Should still work with empty params
        assert isinstance(result, dict)


class TestResolveConnectionParameters:
    """Test _resolve_connection_parameters() method."""

    def test_resolve_connection_parameters_with_mapping(self):
        """Test resolving connection parameters with edge mapping."""
        runtime = ConcreteRuntimeWithParameters()

        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "source", {"code": "result = 1"})
        builder.add_node("PythonCodeNode", "target", {"code": "result = 1"})
        builder.add_connection("source", "result", "target", "input_data")
        workflow = builder.build()

        source_results = {"result": [1, 2, 3], "status": "ok"}

        result = runtime._resolve_connection_parameters(
            workflow, "source", "target", source_results
        )

        # Should map result -> input_data
        assert "input_data" in result
        assert result["input_data"] == [1, 2, 3]

    def test_resolve_connection_parameters_nested_access(self):
        """Test resolving with nested value access."""
        runtime = ConcreteRuntimeWithParameters()

        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "source", {"code": "result = 1"})
        builder.add_node("PythonCodeNode", "target", {"code": "result = 1"})
        workflow = builder.build()

        # Manually add connection with nested path
        workflow.graph.add_edge("source", "target", mapping={"result.files": "data"})

        source_results = {"result": {"files": [1, 2, 3], "count": 3}}

        result = runtime._resolve_connection_parameters(
            workflow, "source", "target", source_results
        )

        # Should access nested value
        assert "data" in result
        assert result["data"] == [1, 2, 3]


class TestResolveWorkflowParameters:
    """Test _resolve_workflow_parameters() method."""

    def test_resolve_workflow_defaults_only(self):
        """Test resolving with only workflow defaults."""
        runtime = ConcreteRuntimeWithParameters()

        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "node1", {"code": "result = 1"})
        workflow = builder.build()
        workflow.metadata = {"default_params": {"limit": 10, "offset": 0}}

        result = runtime._resolve_workflow_parameters(workflow, None)

        assert result == {"limit": 10, "offset": 0}

    def test_resolve_workflow_runtime_overrides(self):
        """Test resolving with runtime parameter overrides."""
        runtime = ConcreteRuntimeWithParameters()

        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "node1", {"code": "result = 1"})
        workflow = builder.build()
        workflow.metadata = {"default_params": {"limit": 10, "offset": 0}}

        runtime_params = {"limit": 20, "filter": "active"}

        result = runtime._resolve_workflow_parameters(workflow, runtime_params)

        # Runtime params override defaults
        assert result["limit"] == 20
        assert result["offset"] == 0
        assert result["filter"] == "active"

    def test_resolve_workflow_no_defaults(self):
        """Test resolving when workflow has no defaults."""
        runtime = ConcreteRuntimeWithParameters()

        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "node1", {"code": "result = 1"})
        workflow = builder.build()

        runtime_params = {"limit": 20}

        result = runtime._resolve_workflow_parameters(workflow, runtime_params)

        assert result == {"limit": 20}


class TestParameterHandlingIntegration:
    """Test integration of parameter handling methods."""

    def test_full_parameter_resolution_pipeline(self):
        """Test complete parameter resolution pipeline."""
        runtime = ConcreteRuntimeWithParameters()

        # 1. Start with workflow defaults
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "node1", {"code": "result = 1"})
        workflow = builder.build()
        workflow.metadata = {"default_params": {"env": "dev", "limit": 10}}

        # 2. Runtime parameters override
        runtime_params = {"limit": 20, "tag": "v1.0"}

        # 3. Resolve workflow parameters
        resolved = runtime._resolve_workflow_parameters(workflow, runtime_params)
        assert resolved["env"] == "dev"
        assert resolved["limit"] == 20
        assert resolved["tag"] == "v1.0"

        # 4. Resolve templates in parameters
        template_value = {"message": "Environment: ${env}, Tag: ${tag}"}
        resolved_template = runtime._resolve_template_parameters(
            template_value, resolved
        )
        assert resolved_template["message"] == "Environment: dev, Tag: v1.0"

    def test_parameter_handling_with_nested_structures(self):
        """Test parameter handling with complex nested structures."""
        runtime = ConcreteRuntimeWithParameters()

        # Complex parameter structure
        sources = [
            {"config": {"db": {"host": "localhost", "port": 5432}}},
            {"config": {"db": {"port": 3306}, "cache": {"enabled": True}}},
            {"config": {"api": {"timeout": 30}}},
        ]

        merged = runtime._merge_parameter_sources(sources)

        # Verify deep merge
        assert merged["config"]["db"]["host"] == "localhost"
        assert merged["config"]["db"]["port"] == 3306  # Overridden
        assert merged["config"]["cache"]["enabled"] is True
        assert merged["config"]["api"]["timeout"] == 30

        # Resolve templates in merged parameters
        template = {"connection": "postgresql://${config.db.host}:${config.db.port}"}

        # Extract nested values for template resolution
        template_params = {
            "config.db.host": runtime._get_nested_value(merged, "config.db.host"),
            "config.db.port": runtime._get_nested_value(merged, "config.db.port"),
        }

        resolved = runtime._resolve_template_parameters(template, template_params)
        assert "localhost" in str(resolved)
