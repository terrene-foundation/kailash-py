"""
Parameter handling mixin for runtime parameter resolution.

Provides parameter resolution logic for workflows including template
resolution, parameter merging, and multi-source parameter handling.

Version: v0.10.0
Created: 2025-10-25
Purpose: Extract parameter handling logic for sync/async runtime sharing
"""

import copy
import logging
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from kailash.workflow import Workflow

logger = logging.getLogger(__name__)

# Template pattern: ${param_name}
TEMPLATE_PATTERN = re.compile(r"\$\{([^}]+)\}")


class ParameterHandlingMixin:
    """
    Parameter resolution and handling for workflow runtimes.

    This mixin provides comprehensive parameter handling including:
    - Template resolution (${param} syntax)
    - Multi-source parameter merging
    - Connection parameter mapping
    - Nested parameter resolution

    All parameter handling logic is pure computation with no I/O,
    making it 100% shared between sync and async runtimes.

    Shared Logic (100%):
        All 5 parameter methods are pure logic performing:
        - String template resolution
        - Dictionary merging
        - Recursive parameter resolution
        No sync/async variants needed.

    Dependencies:
        - No dependencies on other mixins
        - Works with BaseRuntime and ValidationMixin
        - Can be used standalone

    Usage:
        class LocalRuntime(BaseRuntime, ParameterHandlingMixin):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)

            def execute(self, workflow, parameters=None):
                # Resolve parameters
                resolved = self._resolve_workflow_parameters(
                    workflow, parameters
                )
                # Use resolved parameters
                pass

    Examples:
        # Template resolution
        template = "Hello ${name}"
        params = {"name": "Alice"}
        result = runtime._resolve_template_parameters(template, params)
        # result: "Hello Alice"

        # Parameter merging (workflow + runtime + node)
        merged = runtime._merge_parameter_sources([
            {"a": 1, "b": 2},  # Workflow-level
            {"b": 3, "c": 4},  # Runtime-level (overrides)
            {"c": 5, "d": 6},  # Node-level (highest priority)
        ])
        # merged: {"a": 1, "b": 3, "c": 5, "d": 6}

    See Also:
        - ValidationMixin: Parameter validation
        - template_resolver.py: Original template resolution implementation
        - ADR-XXX: Runtime Refactoring

    Version:
        Added in: v0.10.0
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize parameter handling mixin.

        IMPORTANT: Calls super().__init__() for MRO chain.
        """
        super().__init__(*args, **kwargs)

    def _resolve_workflow_parameters(
        self, workflow: "Workflow", runtime_parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Resolve workflow-level parameters.

        Merges parameters from multiple sources in priority order:
        1. Workflow defaults (lowest priority)
        2. Runtime-provided parameters (highest priority)

        Args:
            workflow: The workflow to resolve parameters for
            runtime_parameters: Parameters provided at runtime

        Returns:
            Merged and resolved parameters

        Implementation Notes:
            100% shared logic - pure dictionary merging and resolution.

        Examples:
            >>> # Workflow with defaults
            >>> workflow.metadata = {"default_params": {"limit": 10, "offset": 0}}
            >>> runtime_params = {"limit": 20, "filter": "active"}
            >>> resolved = self._resolve_workflow_parameters(workflow, runtime_params)
            >>> resolved
            {'limit': 20, 'offset': 0, 'filter': 'active'}
        """
        # Start with workflow defaults
        workflow_defaults = {}
        if hasattr(workflow, "metadata") and workflow.metadata:
            workflow_defaults = workflow.metadata.get("default_params", {})

        # Merge with runtime parameters (runtime overrides defaults)
        parameter_sources = [workflow_defaults]
        if runtime_parameters:
            parameter_sources.append(runtime_parameters)

        return self._merge_parameter_sources(parameter_sources)

    def _resolve_node_parameters(
        self,
        workflow: "Workflow",
        node_id: str,
        workflow_parameters: Dict[str, Any],
        connection_inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Resolve parameters for a specific node.

        Merges parameters from multiple sources in priority order:
        1. Node configuration (lowest)
        2. Workflow parameters
        3. Connection inputs (highest)

        Args:
            workflow: The workflow
            node_id: ID of node to resolve parameters for
            workflow_parameters: Resolved workflow-level parameters
            connection_inputs: Parameters from incoming connections

        Returns:
            Fully resolved node parameters

        Examples:
            >>> # Node with config: {"limit": 10, "format": "json"}
            >>> # Workflow params: {"limit": 20, "tag": "prod"}
            >>> # Connection inputs: {"data": [...], "limit": 30}
            >>> resolved = self._resolve_node_parameters(
            ...     workflow, "node1",
            ...     {"limit": 20, "tag": "prod"},
            ...     {"data": [...], "limit": 30}
            ... )
            >>> resolved
            {'limit': 30, 'format': 'json', 'tag': 'prod', 'data': [...]}
        """
        # Get node configuration from workflow
        node_config = {}
        if hasattr(workflow, "nodes") and node_id in workflow.nodes:
            node_data = workflow.nodes[node_id]
            # Extract config from node metadata
            if isinstance(node_data, dict):
                node_config = node_data.get("config", {})

        # Merge in priority order: node config -> workflow params -> connection inputs
        parameter_sources = [node_config]

        # Add workflow-level parameters
        if workflow_parameters:
            parameter_sources.append(workflow_parameters)

        # Add connection inputs (highest priority)
        if connection_inputs:
            parameter_sources.append(connection_inputs)

        merged = self._merge_parameter_sources(parameter_sources)

        # Resolve templates in merged parameters using workflow parameters as inputs
        if workflow_parameters:
            merged = self._resolve_template_parameters(merged, workflow_parameters)

        return merged

    def _resolve_connection_parameters(
        self,
        workflow: "Workflow",
        source_node_id: str,
        target_node_id: str,
        source_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Resolve parameters from connection mapping.

        Maps outputs from source node to inputs for target node
        based on connection configuration.

        Args:
            workflow: The workflow
            source_node_id: Source node ID
            target_node_id: Target node ID
            source_results: Results from source node execution

        Returns:
            Mapped parameters for target node

        Examples:
            >>> # Connection mapping: {"result": "input_data", "status": "check_status"}
            >>> # Source results: {"result": [1,2,3], "status": "ok", "meta": {...}}
            >>> mapped = self._resolve_connection_parameters(
            ...     workflow, "source", "target",
            ...     {"result": [1,2,3], "status": "ok", "meta": {...}}
            ... )
            >>> mapped
            {'input_data': [1, 2, 3], 'check_status': 'ok'}
        """
        mapped_params = {}

        # Get connection mapping from workflow graph
        if hasattr(workflow, "graph") and workflow.graph.has_edge(
            source_node_id, target_node_id
        ):
            # Get edge data which contains the mapping
            edge_data = workflow.graph.get_edge_data(source_node_id, target_node_id)
            mapping = edge_data.get("mapping", {})

            # Apply mapping to source results
            for source_key, target_key in mapping.items():
                # Handle nested output access (e.g., "result.files")
                value = self._get_nested_value(source_results, source_key)

                if value is not None:
                    mapped_params[target_key] = value
                else:
                    logger.debug(
                        f"Source output '{source_key}' not found in node '{source_node_id}'. "
                        f"Available outputs: {list(source_results.keys())}"
                    )

        return mapped_params

    def _resolve_template_parameters(
        self, value: Any, parameters: Dict[str, Any]
    ) -> Any:
        """
        Resolve template strings with ${param} syntax.

        Recursively resolves templates in:
        - Strings: "Hello ${name}" → "Hello Alice"
        - Lists: ["${a}", "${b}"] → [1, 2]
        - Dicts: {"key": "${value}"} → {"key": "resolved"}

        Args:
            value: Value to resolve (string, list, dict, or other)
            parameters: Available parameters for resolution

        Returns:
            Resolved value with templates replaced

        Examples:
            >>> _resolve_template_parameters("${name}", {"name": "Alice"})
            "Alice"
            >>> _resolve_template_parameters(
            ...     {"msg": "Hello ${name}"},
            ...     {"name": "Bob"}
            ... )
            {"msg": "Hello Bob"}
            >>> # Multiple templates in one string
            >>> _resolve_template_parameters(
            ...     "${first}-${last}",
            ...     {"first": "John", "last": "Doe"}
            ... )
            "John-Doe"
            >>> # Nested template resolution
            >>> _resolve_template_parameters(
            ...     {"filter": {"status": "${status}"}, "limit": "${limit}"},
            ...     {"status": "active", "limit": 10}
            ... )
            {"filter": {"status": "active"}, "limit": 10}
        """
        if isinstance(value, dict):
            # Recursively resolve all values in dictionary
            return {
                key: self._resolve_template_parameters(val, parameters)
                for key, val in value.items()
            }

        elif isinstance(value, list):
            # Recursively resolve all items in list
            return [
                self._resolve_template_parameters(item, parameters) for item in value
            ]

        elif isinstance(value, str):
            # Check if this is a pure template (entire string is "${param}")
            if (
                value.startswith("${")
                and value.endswith("}")
                and value.count("${") == 1
            ):
                # Pure template - extract parameter name
                param_name = value[2:-1]  # Remove "${" and "}"

                # Return actual value if found, preserving type
                if param_name in parameters:
                    return parameters[param_name]
                else:
                    # Parameter not found - leave template unchanged
                    logger.debug(
                        f"Template parameter '${{{param_name}}}' not found in parameters. "
                        f"Available: {list(parameters.keys())}"
                    )
                    return value

            # Check if string contains multiple templates or mixed content
            elif "${" in value:
                # Multiple templates or template mixed with text
                # Replace all ${param} occurrences with string values
                def replace_template(match):
                    param_name = match.group(1)
                    if param_name in parameters:
                        val = parameters[param_name]
                        # Convert value to string for substitution
                        return str(val)
                    else:
                        # Leave unresolved templates as-is
                        return match.group(0)

                resolved = TEMPLATE_PATTERN.sub(replace_template, value)
                return resolved

            else:
                # Not a template - return as-is
                return value

        else:
            # Not a container or string - return as-is
            return value

    def _merge_parameter_sources(
        self, parameter_sources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Merge parameters from multiple sources.

        Later sources override earlier sources. Supports deep merge for nested
        dictionaries.

        Args:
            parameter_sources: List of parameter dictionaries
                              (lowest to highest priority)

        Returns:
            Merged parameters

        Examples:
            >>> _merge_parameter_sources([
            ...     {"a": 1, "b": 2},
            ...     {"b": 3, "c": 4}
            ... ])
            {"a": 1, "b": 3, "c": 4}
            >>> # Deep merge example
            >>> _merge_parameter_sources([
            ...     {"config": {"timeout": 30, "retries": 3}},
            ...     {"config": {"timeout": 60}}
            ... ])
            {"config": {"timeout": 60, "retries": 3}}
        """
        if not parameter_sources:
            return {}

        # Start with empty dict
        merged = {}

        # Merge each source in order (later sources override earlier)
        for source in parameter_sources:
            if not source:
                continue

            merged = self._deep_merge(merged, source)

        return merged

    def _deep_merge(
        self, base: Dict[str, Any], override: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Deep merge two dictionaries.

        Recursively merges nested dictionaries. Lists and other types
        are replaced (not merged).

        Args:
            base: Base dictionary
            override: Dictionary with override values

        Returns:
            Merged dictionary

        Examples:
            >>> _deep_merge(
            ...     {"a": 1, "b": {"x": 10, "y": 20}},
            ...     {"b": {"x": 30, "z": 40}, "c": 3}
            ... )
            {"a": 1, "b": {"x": 30, "y": 20, "z": 40}, "c": 3}
        """
        result = copy.deepcopy(base)

        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                # Both are dicts - recursively merge
                result[key] = self._deep_merge(result[key], value)
            else:
                # Override the value
                result[key] = copy.deepcopy(value)

        return result

    def _get_nested_value(
        self, data: Dict[str, Any], path: str, default: Any = None
    ) -> Any:
        """
        Get a nested value using dot notation.

        Supports accessing nested dictionary values using dot-separated paths.

        Args:
            data: Dictionary to access
            path: Dot-separated path (e.g., "result.files.count")
            default: Default value if path not found

        Returns:
            Value at the specified path or default if not found

        Examples:
            >>> data = {"result": {"files": [1, 2, 3], "count": 3}}
            >>> _get_nested_value(data, "result.files")
            [1, 2, 3]
            >>> _get_nested_value(data, "result.count")
            3
            >>> _get_nested_value(data, "result.missing", default="N/A")
            "N/A"
            >>> # Direct key access (no dots)
            >>> _get_nested_value(data, "result")
            {"files": [1, 2, 3], "count": 3}
        """
        if "." not in path:
            # Simple lookup
            return data.get(path, default)

        # Navigate nested structure
        parts = path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default

        return current

    def _validate_template_syntax(self, obj: Any) -> List[str]:
        """
        Validate template syntax in parameters.

        Checks for common template errors like:
        - Mismatched braces
        - Invalid parameter names
        - Nested templates

        Args:
            obj: Object to validate (dict, list, str, etc.)

        Returns:
            List of error messages (empty if valid)

        Examples:
            >>> _validate_template_syntax("${valid_name}")
            []
            >>> _validate_template_syntax("${}")  # Empty parameter name
            ['Empty parameter name in template: ${}']
            >>> _validate_template_syntax("${unclosed")  # Missing }
            ['Malformed template: ${unclosed (missing closing brace)']
        """
        errors = []

        if isinstance(obj, dict):
            for key, value in obj.items():
                errors.extend(self._validate_template_syntax(value))

        elif isinstance(obj, list):
            for item in obj:
                errors.extend(self._validate_template_syntax(item))

        elif isinstance(obj, str):
            # Check for malformed templates
            if "${" in obj:
                # Count opening and closing braces
                open_count = obj.count("${")
                close_count = obj.count("}")

                if open_count != close_count:
                    errors.append(
                        f"Mismatched template braces in '{obj}' "
                        f"({open_count} opening, {close_count} closing)"
                    )

                # Find all template matches
                matches = TEMPLATE_PATTERN.findall(obj)
                for param_name in matches:
                    if not param_name:
                        errors.append(
                            f"Empty parameter name in template: ${{{param_name}}}"
                        )
                    elif not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", param_name):
                        errors.append(
                            f"Invalid parameter name in template: ${{{param_name}}} "
                            f"(must be valid Python identifier)"
                        )

                # Check for nested templates (not supported)
                if obj.count("${") > 1 and "${${" in obj:
                    errors.append(f"Nested templates not supported: {obj}")

        return errors

    def _extract_template_parameters(self, obj: Any) -> set:
        """
        Extract all template parameter names from an object.

        Useful for analyzing what inputs are needed for a workflow.

        Args:
            obj: Object to scan (dict, list, str, etc.)

        Returns:
            Set of parameter names found in templates

        Examples:
            >>> _extract_template_parameters("${name}")
            {'name'}
            >>> _extract_template_parameters({
            ...     "filter": {"tag": "${tag}"},
            ...     "limit": "${limit}"
            ... })
            {'tag', 'limit'}
            >>> _extract_template_parameters([
            ...     {"value": "${val1}"},
            ...     {"value": "${val2}"}
            ... ])
            {'val1', 'val2'}
        """
        params = set()

        if isinstance(obj, dict):
            for value in obj.values():
                params.update(self._extract_template_parameters(value))

        elif isinstance(obj, list):
            for item in obj:
                params.update(self._extract_template_parameters(item))

        elif isinstance(obj, str):
            # Find all template parameters
            matches = TEMPLATE_PATTERN.findall(obj)
            params.update(matches)

        return params


__all__ = ["ParameterHandlingMixin", "TEMPLATE_PATTERN"]
