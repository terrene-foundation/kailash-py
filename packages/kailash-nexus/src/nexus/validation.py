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

# Characters permitted in a workflow name. This is the MCP tool-name charset
# (SEP-986) and is also safe as an HTTP path segment, an ``AnyUrl`` authority
# in ``workflow://<name>``, and a CLI argument — the four surfaces a
# registered name has to travel through. Membership is checked per character
# so the error message can name exactly which characters were rejected.
_WORKFLOW_NAME_ALLOWED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ" "abcdefghijklmnopqrstuvwxyz" "0123456789" "_-."
).__contains__


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
    Validate workflow name for security and multi-channel addressability.

    A registered name is simultaneously (a) an HTTP path segment
    (``/workflows/{name}/execute``), (b) an MCP tool name, (c) an MCP
    resource URI authority (``workflow://{name}``), and (d) a CLI
    subcommand argument. The only character set safe in all four is the
    MCP tool-name charset from SEP-986: ``A-Z a-z 0-9 _ . -``. Anything
    outside it is rejected here so the failure surfaces once, at
    registration, with the offending characters named — instead of as an
    opaque third-party URL-parser error or as a workflow that registers
    successfully and then 400s on every execute request.

    Args:
        name: Workflow name to validate

    Returns:
        Validated workflow name

    Raises:
        ValueError: If validation fails

    Security Checks:
        1. Must be a non-empty string
        2. Must be a reasonable length (<= 128 chars)
        3. Must not contain path separators (prevents directory traversal)
        4. Must contain only SEP-986 tool-name characters
    """
    if not isinstance(name, str):
        raise ValueError(f"Workflow name must be a string, got {type(name).__name__}")

    if not name or not name.strip():
        raise ValueError("Workflow name cannot be empty")

    # Check length
    if len(name) > 128:
        raise ValueError(
            f"Workflow name too long: {len(name)} chars (max: 128). Use a shorter name."
        )

    # Check for path separators first — the traversal case gets its own
    # message because "use a different charset" is unhelpful advice for
    # someone who typed a path.
    if "/" in name or "\\" in name:
        raise ValueError(
            f"Workflow name cannot contain path separators: {name}. "
            f"Use simple names like 'my_workflow' instead."
        )

    # Allowlist, not a blocklist. A blocklist of "dangerous" shell
    # metacharacters lets through characters that are equally fatal
    # downstream: a space or '^' aborts ``AnyUrl("workflow://<name>")``
    # inside the MCP resource registration, and a non-ASCII character is
    # silently percent-encoded there so the resource no longer round-trips
    # to the registered name.
    invalid = sorted({char for char in name if not _WORKFLOW_NAME_ALLOWED(char)})
    if invalid:
        raise ValueError(
            f"Workflow name contains invalid characters: {invalid}. "
            f"Use letters, digits, and the characters '_', '-', '.' only "
            f"(MCP tool-name charset, SEP-986)."
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
