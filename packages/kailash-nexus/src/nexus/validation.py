"""Unified input validation for all Nexus channels.

P0-5 FIX: Provides consistent security validation across API, MCP, and CLI channels.
This prevents security inconsistencies where some channels bypass validation.
"""

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Default maximum input size (10MB)
DEFAULT_MAX_INPUT_SIZE = 10 * 1024 * 1024

# Dangerous keys that could enable code injection or exploitation
DANGEROUS_KEYS = [
    "__class__",
    "__init__",
    "__dict__",
    "__reduce__",
    "__builtins__",
    "__import__",
    "__globals__",
    "eval",
    "exec",
    "compile",
    "__code__",
    "__name__",
    "__bases__",
]

# Maximum key length to prevent memory attacks
MAX_KEY_LENGTH = 256


def validate_workflow_inputs(
    inputs: Any, max_size: int = DEFAULT_MAX_INPUT_SIZE
) -> Dict[str, Any]:
    """
    Validate workflow inputs for security and size constraints.

    This function is used by ALL channels (API, MCP, CLI) to ensure
    consistent security posture across the platform.

    Args:
        inputs: Input data to validate (must be a dictionary)
        max_size: Maximum input size in bytes (default: 10MB)

    Returns:
        Validated inputs dictionary

    Raises:
        ValueError: If validation fails

    Security Checks:
        1. Type validation (must be dict)
        2. Size limit enforcement (prevents DoS)
        3. Dangerous key blocking (prevents injection)
        4. Key length validation (prevents memory attacks)

    Example:
        >>> # In API channel
        >>> validated = validate_workflow_inputs(request.json(), max_size=10_000_000)
        >>>
        >>> # In MCP channel
        >>> validated = validate_workflow_inputs(params, max_size=10_000_000)
        >>>
        >>> # In CLI channel
        >>> validated = validate_workflow_inputs(parsed_args, max_size=10_000_000)
    """
    # 1. Type validation
    if not isinstance(inputs, dict):
        raise ValueError(
            f"Inputs must be a dictionary, got {type(inputs).__name__}. "
            f"Ensure workflow inputs are properly structured as key-value pairs."
        )

    # 2. Size limit check (prevents DoS attacks via large payloads)
    try:
        inputs_size = len(json.dumps(inputs))
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"Inputs must be JSON-serializable. Error: {e}. "
            f"Check for non-serializable objects (file handles, functions, etc.)."
        ) from e

    if inputs_size > max_size:
        raise ValueError(
            f"Input data exceeds maximum size: {inputs_size} bytes > {max_size} bytes. "
            f"Reduce input size or increase max_size parameter if needed."
        )

    # 3. Dangerous key check (prevents code injection)
    found_dangerous = [key for key in inputs.keys() if key in DANGEROUS_KEYS]
    if found_dangerous:
        raise ValueError(
            f"Dangerous keys not allowed in inputs: {found_dangerous}. "
            f"These keys could enable code injection or exploitation. "
            f"Use regular parameter names instead."
        )

    # 4. Key length validation (prevents memory attacks)
    long_keys = [key for key in inputs.keys() if len(str(key)) > MAX_KEY_LENGTH]
    if long_keys:
        # Truncate for error message
        truncated_keys = [f"{str(key)[:50]}..." for key in long_keys]
        raise ValueError(
            f"Input keys exceed maximum length ({MAX_KEY_LENGTH} chars): {truncated_keys}. "
            f"Use shorter parameter names."
        )

    # 5. Check for keys starting with dunder (additional protection)
    dunder_keys = [key for key in inputs.keys() if str(key).startswith("__")]
    if dunder_keys:
        raise ValueError(
            f"Input keys starting with '__' (dunder) are not allowed: {dunder_keys}. "
            f"Dunder attributes are reserved for Python internals. "
            f"Use regular parameter names instead."
        )

    logger.debug(
        f"Input validation passed: {len(inputs)} parameters, {inputs_size} bytes"
    )

    return inputs


def validate_workflow_name(name: str) -> str:
    """
    Validate workflow name for security.

    Args:
        name: Workflow name to validate

    Returns:
        Validated workflow name

    Raises:
        ValueError: If validation fails

    Security Checks:
        1. Must be non-empty string
        2. Must not contain path separators (prevents directory traversal)
        3. Must not contain dangerous characters
        4. Must be reasonable length
    """
    if not isinstance(name, str):
        raise ValueError(f"Workflow name must be a string, got {type(name).__name__}")

    if not name or not name.strip():
        raise ValueError("Workflow name cannot be empty")

    # Check for path separators (prevents directory traversal)
    if "/" in name or "\\" in name:
        raise ValueError(
            f"Workflow name cannot contain path separators: {name}. "
            f"Use simple names like 'my_workflow' instead."
        )

    # Check for dangerous characters
    dangerous_chars = ["<", ">", "|", "&", ";", "$", "`", "!", "*", "?"]
    found_dangerous = [char for char in dangerous_chars if char in name]
    if found_dangerous:
        raise ValueError(
            f"Workflow name contains dangerous characters: {found_dangerous}. "
            f"Use alphanumeric characters, hyphens, and underscores only."
        )

    # Check length
    if len(name) > 128:
        raise ValueError(
            f"Workflow name too long: {len(name)} chars (max: 128). "
            f"Use a shorter name."
        )

    return name


def get_validation_summary() -> Dict[str, Any]:
    """
    Get summary of validation rules for documentation/debugging.

    Returns:
        Dictionary containing validation rules and limits
    """
    return {
        "max_input_size": DEFAULT_MAX_INPUT_SIZE,
        "max_key_length": MAX_KEY_LENGTH,
        "dangerous_keys": DANGEROUS_KEYS,
        "supported_types": ["dict"],
        "security_checks": [
            "Type validation",
            "Size limit enforcement",
            "Dangerous key blocking",
            "Key length validation",
            "Dunder attribute protection",
        ],
    }
