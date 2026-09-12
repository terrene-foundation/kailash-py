"""
Deprecation utilities for Kaizen framework.

Provides a @deprecated decorator compatible with Python 3.11+ (since
warnings.deprecated is only available in Python 3.13+).

Copyright 2025 Terrene Foundation (Singapore CLG)
Licensed under Apache-2.0
"""

import functools
import warnings
from typing import Any, Callable, Optional


def format_deprecation_message(message: str, *, since: Optional[str] = None) -> str:
    """Build the canonical deprecation text used by every Kaizen warning.

    Single source of truth for the wording, so a warning emitted outside the
    ``@deprecated`` wrapper cannot drift from one emitted by it.
    """
    if since:
        return f"Deprecated since v{since}: {message}"
    return f"Deprecated: {message}"


def warn_deprecated(
    message: str, *, since: Optional[str] = None, stacklevel: int = 2
) -> None:
    """Emit the same DeprecationWarning ``@deprecated`` emits, without wrapping.

    For call sites that must decide at runtime whether a deprecated surface is
    actually in use (e.g. a framework dispatching to a caller's override of a
    deprecated extension point).

    Args:
        message: Explanation of what to use instead.
        since: Optional version string when deprecation was introduced.
        stacklevel: Passed through to ``warnings.warn`` so the warning is
            attributed to the caller rather than to this helper.
    """
    warnings.warn(
        format_deprecation_message(message, since=since),
        DeprecationWarning,
        stacklevel=stacklevel,
    )


def resolve_deprecated_hook(
    instance: Any, defining_class: type, name: str
) -> Optional[Callable]:
    """Return a caller-supplied override of a deprecated hook, else ``None``.

    A deprecated extension point that the framework itself must call leaves the
    framework no way to run without warning its own users. This resolves the
    question the framework actually needs answered: *has anyone overridden this
    hook?* If yes, the override is returned and MUST still be called — silently
    skipping a caller's override would be a behaviour regression. If no, the
    framework may take its internal path and stay silent.

    Detection covers both subclass overrides and per-instance monkeypatching.

    Args:
        instance: The object whose hook is being resolved.
        defining_class: The class carrying the deprecated default implementation.
        name: Attribute name of the hook.

    Returns:
        The override callable, or ``None`` when the deprecated default is in place.
    """
    base_impl = getattr(defining_class, name, None)
    candidate = getattr(instance, name, None)
    if candidate is None or base_impl is None:
        return None

    candidate_func = getattr(candidate, "__func__", candidate)
    base_func = getattr(base_impl, "__func__", base_impl)
    if candidate_func is base_func:
        return None
    return candidate


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
    full_message = format_deprecation_message(message, since=since)

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
