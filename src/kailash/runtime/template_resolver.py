"""Template parameter resolution for workflow execution.

This module provides utilities for resolving ${param} template syntax
in workflow parameters. It supports recursive resolution in nested
dictionaries and lists.

Version: v0.9.30
Created: 2025-10-24
Purpose: Enable dynamic parameter injection in nested node configurations

Example Usage:
    Basic template resolution:
    ```python
    from kailash.runtime.template_resolver import resolve_templates

    params = {
        "filter": {"run_tag": "${tag}"},
        "limit": "${limit}"
    }

    inputs = {"tag": "local", "limit": 10}

    resolved = resolve_templates(params, inputs)
    # Returns: {"filter": {"run_tag": "local"}, "limit": 10}
    ```

    With DataFlow:
    ```python
    workflow.add_node("WorkflowRunListNode", "filter_runs", {
        "filter": {"run_tag": "${tag}", "status": "${status}"},
        "limit": "${limit}"
    })

    result = await runtime.execute_workflow_async(
        workflow.build(),
        inputs={"tag": "local", "status": "active", "limit": 10}
    )
    # filter parameter automatically resolves to: {"run_tag": "local", "status": "active"}
    ```
"""

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Template pattern: ${param_name}
TEMPLATE_PATTERN = re.compile(r"\$\{([^}]+)\}")


def resolve_templates(obj: Any, inputs: Dict[str, Any]) -> Any:
    """Recursively resolve ${param} templates in nested structures.

    This function traverses dictionaries, lists, and strings to find and
    replace template parameters with their actual values from the inputs dict.

    Template Syntax:
        - `"${param_name}"` - Resolves to `inputs["param_name"]`
        - Case-sensitive parameter names
        - Missing parameters remain as templates

    Args:
        obj: Object to process (can be dict, list, str, or any other type)
        inputs: Dictionary of input values for template resolution

    Returns:
        Object with all templates resolved

    Examples:
        >>> resolve_templates("${name}", {"name": "John"})
        'John'

        >>> resolve_templates({"id": "${user_id}"}, {"user_id": 123})
        {'id': 123}

        >>> resolve_templates(
        ...     {"filter": {"status": "${status}"}},
        ...     {"status": "active"}
        ... )
        {'filter': {'status': 'active'}}

        >>> # Missing parameters remain as templates
        >>> resolve_templates("${missing}", {})
        '${missing}'

        >>> # Multiple templates in one string
        >>> resolve_templates("${first}-${last}", {"first": "John", "last": "Doe"})
        'John-Doe'
    """
    if isinstance(obj, dict):
        # Recursively resolve all values in dictionary
        return {key: resolve_templates(value, inputs) for key, value in obj.items()}

    elif isinstance(obj, list):
        # Recursively resolve all items in list
        return [resolve_templates(item, inputs) for item in obj]

    elif isinstance(obj, str):
        # Check if this is a pure template (entire string is "${param}")
        if obj.startswith("${") and obj.endswith("}") and obj.count("${") == 1:
            # Pure template - extract parameter name
            param_name = obj[2:-1]  # Remove "${" and "}"

            # Return actual value if found, preserving type
            if param_name in inputs:
                return inputs[param_name]
            else:
                # Parameter not found - leave template unchanged
                logger.debug(
                    f"Template parameter '${{{param_name}}}' not found in inputs. "
                    f"Available: {list(inputs.keys())}"
                )
                return obj

        # Check if string contains multiple templates or mixed content
        elif "${" in obj:
            # Multiple templates or template mixed with text
            # Replace all ${param} occurrences with string values
            def replace_template(match):
                param_name = match.group(1)
                if param_name in inputs:
                    value = inputs[param_name]
                    # Convert value to string for substitution
                    return str(value)
                else:
                    # Leave unresolved templates as-is
                    return match.group(0)

            resolved = TEMPLATE_PATTERN.sub(replace_template, obj)
            return resolved

        else:
            # Not a template - return as-is
            return obj

    else:
        # Not a container or string - return as-is
        return obj


def validate_template_syntax(obj: Any) -> List[str]:
    """Validate template syntax in parameters.

    Checks for common template errors like:
    - Mismatched braces
    - Invalid parameter names
    - Nested templates

    Args:
        obj: Object to validate (dict, list, str, etc.)

    Returns:
        List of error messages (empty if valid)

    Examples:
        >>> validate_template_syntax("${valid_name}")
        []

        >>> validate_template_syntax("${}")  # Empty parameter name
        ['Empty parameter name in template: ${}']

        >>> validate_template_syntax("${unclosed")  # Missing }
        ['Malformed template: ${unclosed (missing closing brace)']
    """
    errors = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            errors.extend(validate_template_syntax(value))

    elif isinstance(obj, list):
        for item in obj:
            errors.extend(validate_template_syntax(item))

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


def extract_template_parameters(obj: Any) -> set[str]:
    """Extract all template parameter names from an object.

    Useful for analyzing what inputs are needed for a workflow.

    Args:
        obj: Object to scan (dict, list, str, etc.)

    Returns:
        Set of parameter names found in templates

    Examples:
        >>> extract_template_parameters("${name}")
        {'name'}

        >>> extract_template_parameters({"filter": {"tag": "${tag}"}, "limit": "${limit}"})
        {'tag', 'limit'}

        >>> extract_template_parameters([{"value": "${val1}"}, {"value": "${val2}"}])
        {'val1', 'val2'}
    """
    params = set()

    if isinstance(obj, dict):
        for value in obj.values():
            params.update(extract_template_parameters(value))

    elif isinstance(obj, list):
        for item in obj:
            params.update(extract_template_parameters(item))

    elif isinstance(obj, str):
        # Find all template parameters
        matches = TEMPLATE_PATTERN.findall(obj)
        params.update(matches)

    return params


__all__ = [
    "resolve_templates",
    "validate_template_syntax",
    "extract_template_parameters",
    "TEMPLATE_PATTERN",
]
