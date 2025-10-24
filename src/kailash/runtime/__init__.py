"""Runtime engines for the Kailash SDK."""

import asyncio
import logging
from typing import Optional, Union

from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime
from kailash.runtime.parallel_cyclic import ParallelCyclicRuntime
from kailash.runtime.runner import WorkflowRunner

logger = logging.getLogger(__name__)

__all__ = [
    "LocalRuntime",
    "AsyncLocalRuntime",
    "ParallelCyclicRuntime",
    "WorkflowRunner",
    "get_runtime",
]


def get_runtime(
    context: Optional[str] = None, **kwargs
) -> Union[AsyncLocalRuntime, LocalRuntime]:
    """
    Get the recommended runtime for the specified context.

    P0-4 FIX: Auto-detects runtime context when context=None (default).
    This prevents production crashes from wrong-context selection.

    This helper function simplifies runtime selection for common deployment scenarios.
    Use 'async' for web servers (FastAPI, aiohttp, Docker) and 'sync' for CLI/scripts.

    Args:
        context: Runtime context - 'async', 'sync', or None for auto-detection (default: None)
        **kwargs: Additional arguments passed to runtime constructor

    Returns:
        Appropriate runtime instance (AsyncLocalRuntime or LocalRuntime)

    Example:
        >>> # Auto-detect context (RECOMMENDED - P0-4 fix)
        >>> runtime = get_runtime()  # Detects async if event loop running
        >>>
        >>> # Explicit async context (Docker/FastAPI)
        >>> runtime = get_runtime("async")
        >>>
        >>> # Explicit sync context (CLI scripts)
        >>> runtime = get_runtime("sync")
        >>>
        >>> # With custom configuration
        >>> runtime = get_runtime(max_concurrent_nodes=20)

    Security Notes:
        - Auto-detection prevents timing-dependent production crashes
        - Safe for all deployment scenarios (Docker, FastAPI, CLI, batch jobs)
        - Logs detected context for debugging
    """
    # P0-4: Auto-detect context when not specified
    if context is None:
        try:
            # Try to get running event loop
            asyncio.get_running_loop()
            context = "async"
            logger.debug("Runtime auto-detected: async context (event loop is running)")
        except RuntimeError:
            # No event loop running
            context = "sync"
            logger.debug("Runtime auto-detected: sync context (no event loop running)")

    if context == "async":
        return AsyncLocalRuntime(**kwargs)
    elif context == "sync":
        return LocalRuntime(**kwargs)
    else:
        raise ValueError(
            f"Invalid context '{context}'. Use 'async', 'sync', or None for auto-detection."
        )
