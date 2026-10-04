"""Coroutine-function compatibility without deprecated asyncio predicates."""

import asyncio.coroutines
import inspect
from typing import Any

# Keep historical asyncio-marked sync factories on the async dispatch path.
# The marker is an identity token, not a truthy user-controlled flag.
_LEGACY_COROUTINE_MARKER = getattr(asyncio.coroutines, "_is_coroutine", None)


def is_coroutine_function(function: Any) -> bool:
    """Match native/inspect markers and the historical asyncio marker."""
    return inspect.iscoroutinefunction(function) or (
        _LEGACY_COROUTINE_MARKER is not None
        and getattr(function, "_is_coroutine", None) is _LEGACY_COROUTINE_MARKER
    )
