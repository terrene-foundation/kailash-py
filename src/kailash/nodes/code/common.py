"""Common utilities for Python code execution nodes.

This module provides shared constants, utilities, and helper functions
used by both PythonCodeNode (sync) and AsyncPythonCodeNode (async) to
ensure consistent behavior, security policies, and feature parity.

Version: v0.9.30
Created: 2025-10-24
Purpose: Eliminate inconsistencies between sync and async code nodes
"""

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

# ===========================
# SHARED MODULE WHITELISTS
# ===========================

# Common modules allowed in BOTH sync and async
# These are safe, pure Python modules with no I/O or security risks
COMMON_ALLOWED_MODULES = {
    # Core data processing
    "math",
    "statistics",
    "datetime",
    "json",
    "random",
    "itertools",
    "collections",
    "functools",
    "string",
    "time",
    "re",
    # Type and utility modules
    "enum",
    "dataclasses",
    "typing",
    "types",  # For type checking and module filtering
    "copy",
    "uuid",
    "hashlib",
    "hmac",
    "secrets",
    "base64",
    # Data science (common use case)
    "pandas",
    "numpy",
    "scipy",
    "sklearn",
    # File operations (safe subset)
    "pathlib",
    "os",  # Limited to safe operations, monitored by AST checker
    "csv",
    "mimetypes",
    "glob",
    "xml",
    "tempfile",
    # Logging and monitoring
    "logging",
    "io",  # For logging handlers (StringIO, etc.)
    # Serialization
    "pickle",  # With caution
    "msgpack",
    "yaml",
    "toml",
    # Utilities
    "cachetools",
    "tenacity",
    "ratelimit",
    "structlog",
    "prometheus_client",
}

# Sync-specific modules (visualization, blocking I/O)
SYNC_SPECIFIC_MODULES = {
    "matplotlib",
    "seaborn",
    "plotly",
    "array",  # Required by numpy internally
}

# Async-specific modules (async I/O, async libraries)
ASYNC_SPECIFIC_MODULES = {
    # Core async
    "asyncio",
    "contextvars",
    "concurrent.futures",
    # Async HTTP
    "aiohttp",
    "httpx",
    "websockets",
    # Async databases
    "asyncpg",
    "aiomysql",
    "motor",
    "redis",
    "redis.asyncio",
    "aiosqlite",
    # Async file I/O
    "aiofiles",
    # Async message queues
    "aiokafka",
    "aio_pika",
    # Async cloud SDKs
    "aioboto3",
    "aioazure",
    # Fast JSON
    "orjson",
}

# Final module whitelists
ALLOWED_MODULES = COMMON_ALLOWED_MODULES | SYNC_SPECIFIC_MODULES
ALLOWED_ASYNC_MODULES = COMMON_ALLOWED_MODULES | ASYNC_SPECIFIC_MODULES

# ===========================
# SHARED BUILTIN FUNCTIONS
# ===========================

# Common builtins allowed in BOTH sync and async
# These are safe Python builtins with no security risks
COMMON_ALLOWED_BUILTINS = {
    # Type constructors
    "bool",
    "int",
    "float",
    "str",
    "list",
    "dict",
    "set",
    "tuple",
    "frozenset",
    "bytes",
    "bytearray",
    "complex",
    # Iteration
    "len",
    "range",
    "enumerate",
    "zip",
    "map",
    "filter",
    "reversed",
    "iter",  # CRITICAL: Iterator creation
    "next",  # CRITICAL: Iterator consumption
    "sorted",
    # Aggregation
    "sum",
    "min",
    "max",
    "all",
    "any",
    # Math
    "abs",
    "round",
    "divmod",
    "pow",
    # Conversion
    "hex",
    "oct",
    "bin",
    "format",
    "ord",
    "chr",
    "repr",
    # Inspection
    "isinstance",
    "hasattr",
    "getattr",
    "type",
    "callable",
    "hash",
    "vars",
    # Debugging
    "print",
    # Import control (controlled by whitelist)
    "__import__",  # Controlled by ALLOWED_MODULES whitelist
    # Exception classes (MUST BE IDENTICAL in both)
    "Exception",
    "ValueError",
    "TypeError",
    "KeyError",
    "NameError",  # CRITICAL for cycle patterns
    "AttributeError",
    "IndexError",
    "RuntimeError",
    "StopIteration",
    "ImportError",
    "OSError",
    "IOError",
    "FileNotFoundError",
    "ZeroDivisionError",
    "ArithmeticError",
    "AssertionError",
    "ConnectionError",  # For network operations
}

# Sync-specific builtins
SYNC_SPECIFIC_BUILTINS = {
    "open",  # File operations (sync only, async uses aiofiles)
}

# Async-specific builtins
ASYNC_SPECIFIC_BUILTINS = {
    "locals",  # Access to local scope (for debugging)
    "globals",  # Access to global scope (for debugging)
    "setattr",  # Attribute manipulation (for advanced patterns)
}

# Final builtin whitelists
ALLOWED_BUILTINS = COMMON_ALLOWED_BUILTINS | SYNC_SPECIFIC_BUILTINS
ALLOWED_ASYNC_BUILTINS = COMMON_ALLOWED_BUILTINS | ASYNC_SPECIFIC_BUILTINS

# ===========================
# DANGEROUS PATTERNS
# ===========================

# Global functions that are ALWAYS dangerous
DANGEROUS_GLOBAL_FUNCTIONS = {
    "eval",
    "exec",
    "compile",
    "__import__",  # Controlled separately
    "input",
    "raw_input",
}

# Module-specific dangerous functions
# These are allowed modules but specific functions are blocked
DANGEROUS_MODULE_FUNCTIONS = {
    "os": {"system", "popen", "execv", "execl", "execve", "spawn", "spawnl", "spawnv"},
    "subprocess": {"run", "call", "check_call", "Popen", "check_output"},
    "__builtin__": {"eval", "exec", "compile", "__import__"},
    "builtins": {"eval", "exec", "compile", "__import__"},
}

# Modules that are completely blocked
COMPLETELY_BLOCKED_MODULES = {
    "subprocess",
    "multiprocessing",
}

# Async-specific: Functions with async alternatives
ASYNC_FUNCTION_REPLACEMENTS = {
    "open": "Use 'aiofiles.open()' for async file operations",
}

# ===========================
# SERIALIZATION UTILITIES
# ===========================


def ensure_json_serializable(data: Any) -> Any:
    """Ensure data is JSON-serializable.

    This function recursively converts common Python types to JSON-safe
    equivalents. Used by both sync and async nodes to ensure output
    compatibility with JSON-based workflows and APIs.

    Args:
        data: Any Python object

    Returns:
        JSON-serializable version of the data

    Raises:
        None - converts non-serializable objects to strings

    Examples:
        >>> ensure_json_serializable(datetime(2025, 1, 24))
        '2025-01-24T00:00:00'

        >>> ensure_json_serializable(Decimal('3.14'))
        3.14

        >>> ensure_json_serializable({'date': datetime(2025, 1, 24)})
        {'date': '2025-01-24T00:00:00'}
    """
    if data is None:
        return None
    elif isinstance(data, (str, int, float, bool)):
        return data
    elif isinstance(data, (datetime, date)):
        return data.isoformat()
    elif isinstance(data, Decimal):
        return float(data)
    elif isinstance(data, dict):
        return {k: ensure_json_serializable(v) for k, v in data.items()}
    elif isinstance(data, (list, tuple)):
        return [ensure_json_serializable(item) for item in data]
    else:
        # Try native JSON serialization
        try:
            json.dumps(data)
            return data
        except (TypeError, ValueError):
            # Check for .to_dict() method (common pattern)
            if hasattr(data, "to_dict") and callable(getattr(data, "to_dict")):
                try:
                    dict_result = data.to_dict()
                    return ensure_json_serializable(dict_result)
                except (TypeError, ValueError, AttributeError):
                    pass
            # Fall back to string representation
            return str(data)


# ===========================
# ERROR MESSAGES
# ===========================


def format_module_not_allowed_error(module_name: str, is_async: bool = False) -> str:
    """Format consistent error message for disallowed module imports.

    Args:
        module_name: Name of the module that was blocked
        is_async: Whether this is for async context

    Returns:
        Formatted error message with suggestions
    """
    allowed_modules = ALLOWED_ASYNC_MODULES if is_async else ALLOWED_MODULES
    context = "async context" if is_async else "PythonCodeNode"

    error_msg = f"Import of module '{module_name}' is not allowed in {context}.\n\n"
    error_msg += f"Allowed modules: {', '.join(sorted(allowed_modules))}\n\n"

    # Add specific suggestions based on module
    suggestions = get_module_suggestions(module_name)
    if suggestions:
        error_msg += "Suggestions:\n"
        for suggestion in suggestions:
            error_msg += f"  - {suggestion}\n"

    return error_msg


def get_module_suggestions(module_name: str) -> list[str]:
    """Get helpful suggestions for blocked modules.

    Args:
        module_name: Name of the blocked module

    Returns:
        List of suggestion strings
    """
    suggestions = []

    if module_name == "subprocess":
        suggestions.append(
            "For file operations, use 'os' or 'pathlib' modules (with safe operations)"
        )
        suggestions.append(
            "For external processes, create a custom node with proper security controls"
        )
    elif module_name == "requests":
        suggestions.append("Use HTTPRequestNode for HTTP requests instead")
    elif module_name in ["sqlite3", "psycopg2", "pymongo", "mysql"]:
        suggestions.append(
            "Use SQLDatabaseNode or DataFlow for database operations instead"
        )
    elif module_name == "boto3":
        suggestions.append(
            "Use cloud-specific nodes or create a custom node for AWS operations"
        )
    elif module_name == "sys":
        suggestions.append(
            "Most sys operations are restricted for security. Use logging for stderr/stdout."
        )

    return suggestions


def format_dangerous_function_error(function_name: str, module_name: str = None) -> str:
    """Format consistent error message for dangerous function calls.

    Args:
        function_name: Name of the dangerous function
        module_name: Optional module name if from specific module

    Returns:
        Formatted error message with explanation
    """
    if module_name:
        error_msg = f"Call to '{module_name}.{function_name}' is not allowed for security reasons.\n\n"
    else:
        error_msg = (
            f"Call to '{function_name}' is not allowed for security reasons.\n\n"
        )

    # Add explanation
    if function_name in ["eval", "exec"]:
        error_msg += "Reason: Dynamic code execution is dangerous and can lead to arbitrary code execution.\n"
        error_msg += "Solution: Write explicit code instead of dynamic execution.\n"
    elif function_name == "compile":
        error_msg += "Reason: Compiling arbitrary code is a security risk.\n"
        error_msg += "Solution: Use standard Python code instead.\n"
    elif function_name in ["system", "popen"]:
        error_msg += "Reason: System command execution can lead to command injection vulnerabilities.\n"
        error_msg += "Solution: Use Python's built-in file/path operations instead.\n"
    elif function_name == "__import__":
        error_msg += "Reason: Dynamic imports bypass security controls.\n"
        error_msg += (
            "Solution: Use standard import statements at the top of your code.\n"
        )

    return error_msg


# ===========================
# VALIDATION UTILITIES
# ===========================


def validate_module_name(module_name: str, is_async: bool = False) -> tuple[bool, str]:
    """Validate if a module is allowed.

    Args:
        module_name: Module to check
        is_async: Whether this is async context

    Returns:
        Tuple of (is_allowed, error_message)
    """
    allowed = ALLOWED_ASYNC_MODULES if is_async else ALLOWED_MODULES

    if module_name in allowed:
        return True, ""
    else:
        error_msg = format_module_not_allowed_error(module_name, is_async)
        return False, error_msg


def is_dangerous_function(function_name: str, module_name: str = None) -> bool:
    """Check if a function call is dangerous.

    Args:
        function_name: Function name to check
        module_name: Optional module name

    Returns:
        True if dangerous, False if safe
    """
    # Check global dangerous functions
    if function_name in DANGEROUS_GLOBAL_FUNCTIONS:
        return True

    # Check module-specific dangerous functions
    if module_name and module_name in DANGEROUS_MODULE_FUNCTIONS:
        if function_name in DANGEROUS_MODULE_FUNCTIONS[module_name]:
            return True

    return False


# ===========================
# MODULE METADATA
# ===========================

__all__ = [
    # Module whitelists
    "ALLOWED_MODULES",
    "ALLOWED_ASYNC_MODULES",
    "COMMON_ALLOWED_MODULES",
    "SYNC_SPECIFIC_MODULES",
    "ASYNC_SPECIFIC_MODULES",
    # Builtin whitelists
    "ALLOWED_BUILTINS",
    "ALLOWED_ASYNC_BUILTINS",
    "COMMON_ALLOWED_BUILTINS",
    "SYNC_SPECIFIC_BUILTINS",
    "ASYNC_SPECIFIC_BUILTINS",
    # Dangerous patterns
    "DANGEROUS_GLOBAL_FUNCTIONS",
    "DANGEROUS_MODULE_FUNCTIONS",
    "COMPLETELY_BLOCKED_MODULES",
    "ASYNC_FUNCTION_REPLACEMENTS",
    # Utilities
    "ensure_json_serializable",
    "format_module_not_allowed_error",
    "format_dangerous_function_error",
    "get_module_suggestions",
    "validate_module_name",
    "is_dangerous_function",
]
