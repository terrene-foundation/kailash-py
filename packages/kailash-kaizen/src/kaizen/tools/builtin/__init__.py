"""
Kaizen Built-in Tools Security Validation

This module provides security validation functions for built-in tools:
- HTTP/API security (URL validation, SSRF protection, timeout validation)
- File security (path traversal protection, system path blocking, sandboxing)

Usage:
    >>> from kaizen.tools.builtin import validate_url, validate_timeout, validate_safe_path

    # URL validation with SSRF protection
    >>> is_valid, error = validate_url("https://example.com")
    >>> if not is_valid:
    ...     raise ValueError(error)

    # Timeout validation
    >>> is_valid, error = validate_timeout(30)
    >>> if not is_valid:
    ...     raise ValueError(error)

    # File path validation with optional sandboxing
    >>> is_valid, error = validate_safe_path("/tmp/data.txt", allowed_base="/tmp")
    >>> if not is_valid:
    ...     raise ValueError(error)

Security Features:
    - SSRF protection: Blocks localhost, private IPs, link-local addresses
    - Path traversal protection: Blocks ".." patterns in file paths
    - System path blocking: Blocks /etc, /sys, /proc, /dev, /boot, /root
    - Sandboxing: Optional restriction to allowed base directory
"""

from kaizen.tools.builtin.api import validate_timeout, validate_url
from kaizen.tools.builtin.file import validate_safe_path

__all__ = [
    "validate_url",
    "validate_timeout",
    "validate_safe_path",
]
