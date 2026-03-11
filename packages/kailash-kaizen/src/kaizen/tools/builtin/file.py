"""
File Security Validation for Kaizen Built-in Tools

Provides security validation functions for file-related operations:
- Path traversal protection (blocks ".." patterns)
- System path blocking (blocks /etc, /sys, /proc, /dev, /boot, /root)
- Optional sandboxing with allowed_base parameter

Usage:
    >>> from kaizen.tools.builtin.file import validate_safe_path

    # Basic path validation
    >>> is_valid, error = validate_safe_path("/tmp/data.txt")
    >>> assert is_valid is True

    >>> is_valid, error = validate_safe_path("/etc/passwd")
    >>> assert is_valid is False  # System path blocked

    >>> is_valid, error = validate_safe_path("../../../etc/passwd")
    >>> assert is_valid is False  # Path traversal blocked

    # With sandboxing
    >>> is_valid, error = validate_safe_path("/tmp/data.txt", allowed_base="/tmp")
    >>> assert is_valid is True  # Within sandbox

    >>> is_valid, error = validate_safe_path("/var/data.txt", allowed_base="/tmp")
    >>> assert is_valid is False  # Outside sandbox
"""

import os
from typing import Optional, Tuple

# System paths that are always blocked
BLOCKED_SYSTEM_PATHS = frozenset(
    {
        "/etc",
        "/sys",
        "/proc",
        "/dev",
        "/boot",
        "/root",
    }
)


def validate_safe_path(
    path: str, allowed_base: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate file path for security.

    Validates that:
    1. Path is not empty
    2. Path does not contain ".." (path traversal)
    3. Path does not start with blocked system paths
    4. If allowed_base is provided, path must be within that directory

    Args:
        path: The file path to validate
        allowed_base: Optional base directory to restrict paths to (sandboxing)

    Returns:
        Tuple of (is_valid, error_message):
        - (True, None) if valid
        - (False, error_message) if invalid

    Examples:
        >>> validate_safe_path("/tmp/data.txt")
        (True, None)

        >>> validate_safe_path("/etc/passwd")
        (False, 'System path /etc is not allowed')

        >>> validate_safe_path("../../../etc/passwd")
        (False, 'Path traversal detected (..)')

        >>> validate_safe_path("/tmp/data.txt", allowed_base="/tmp")
        (True, None)

        >>> validate_safe_path("/var/data.txt", allowed_base="/tmp")
        (False, 'Path is outside allowed base directory /tmp')
    """
    # Check for empty path
    if not path:
        return False, "Path cannot be empty"

    # Normalize the path for consistent checking
    # Replace backslashes with forward slashes for Windows-style paths
    normalized = path.replace("\\", "/")

    # Check for path traversal patterns
    # This catches: "..", "../", "/..", etc.
    if ".." in normalized:
        return False, "Path traversal detected (..)"

    # Get absolute path for system path checking
    # Note: We use the original path for abspath to handle OS-specific behavior
    try:
        abs_path = os.path.abspath(path)
    except Exception as e:
        return False, f"Invalid path: {e}"

    # Check for blocked system paths
    for blocked in BLOCKED_SYSTEM_PATHS:
        if abs_path == blocked or abs_path.startswith(blocked + "/"):
            return False, f"System path {blocked} is not allowed"

    # Sandboxing check
    if allowed_base is not None:
        try:
            abs_base = os.path.abspath(allowed_base)
            # Ensure the path is within the allowed base
            # Use os.path.commonpath for secure comparison
            if not (abs_path == abs_base or abs_path.startswith(abs_base + os.sep)):
                return False, f"Path is outside allowed base directory {allowed_base}"
        except Exception as e:
            return False, f"Invalid allowed_base: {e}"

    return True, None
