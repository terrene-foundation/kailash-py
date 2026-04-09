"""
Deprecation utilities for Kaizen framework.

Provides a @deprecated decorator compatible with Python 3.11+ (since
warnings.deprecated is only available in Python 3.13+).

Copyright 2025 Terrene Foundation (Singapore CLG)
Licensed under Apache-2.0
"""

import functools
import warnings
from typing import Optional


def deprecated(message: str, *, since: Optional[str] = None):
    """
    Mark a function or method as deprecated.

    Emits a DeprecationWarning when the decorated function is called.
    The warning is emitted once per call site (Python default behavior).

    Args:
        message: Explanation of what to use instead.
        since: Optional version string when deprecation was introduced.

    Returns:
        Decorator that wraps the function with a deprecation warning.

    Example:
        >>> @deprecated("Use composition wrappers instead.", since="2.5.0")
        ... def _default_signature(self):
        ...     ...
    """
    if since:
        full_message = f"Deprecated since v{since}: {message}"
    else:
        full_message = f"Deprecated: {message}"

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            warnings.warn(full_message, DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)

        # Mark the wrapper so tests can detect deprecation
        wrapper._deprecated = True
        wrapper._deprecated_message = full_message
        return wrapper

    return decorator
