"""Runtime engines for the Kailash SDK."""

from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime
from kailash.runtime.parallel_cyclic import ParallelCyclicRuntime
from kailash.runtime.runner import WorkflowRunner

__all__ = [
    "LocalRuntime",
    "AsyncLocalRuntime",
    "ParallelCyclicRuntime",
    "WorkflowRunner",
    "get_runtime",
]


def get_runtime(context: str = "async", **kwargs):
    """
    Get the recommended runtime for the specified context.

    This helper function simplifies runtime selection for common deployment scenarios.
    Use 'async' for web servers (FastAPI, aiohttp, Docker) and 'sync' for CLI/scripts.

    Args:
        context: Runtime context - 'async' for web servers, 'sync' for CLI/scripts
        **kwargs: Additional arguments passed to runtime constructor

    Returns:
        Appropriate runtime instance (AsyncLocalRuntime or LocalRuntime)

    Example:
        >>> # For Docker/FastAPI deployment (recommended)
        >>> runtime = get_runtime("async")
        >>>
        >>> # For CLI scripts
        >>> runtime = get_runtime("sync")
        >>>
        >>> # With custom configuration
        >>> runtime = get_runtime("async", max_concurrent_nodes=20)
    """
    if context == "async":
        return AsyncLocalRuntime(**kwargs)
    elif context == "sync":
        return LocalRuntime(**kwargs)
    else:
        raise ValueError(
            f"Invalid context '{context}'. Use 'async' for web servers "
            f"or 'sync' for CLI/scripts."
        )
