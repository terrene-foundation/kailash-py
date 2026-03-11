"""
Async-Safe Execution Utilities for DataFlow.

This module provides context-aware async execution utilities that work correctly
in all environments: FastAPI/Uvicorn, Docker containers, Jupyter notebooks,
and traditional sync CLI scripts.

The primary utility `async_safe_run()` replaces unsafe `asyncio.run()` calls
that fail when an event loop is already running.

Example:
    # Instead of this (fails in FastAPI):
    result = asyncio.run(some_async_function())

    # Use this (works everywhere):
    from dataflow.core.async_utils import async_safe_run
    result = async_safe_run(some_async_function())

See: Phase 6 - Async-Safe Auto-Migrate (TODO-159)
"""

import asyncio
import logging
import os
import sys
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any, Callable, Coroutine, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Thread-local storage for tracking nested calls
_thread_local = threading.local()

# Shared thread pool for async execution (lazy initialization)
_thread_pool: Optional[ThreadPoolExecutor] = None
_thread_pool_lock = threading.Lock()


def _get_thread_pool() -> ThreadPoolExecutor:
    """Get or create the shared thread pool for async execution."""
    global _thread_pool
    if _thread_pool is None:
        with _thread_pool_lock:
            if _thread_pool is None:
                # Pool size must be > MAX_RECURSION_DEPTH to prevent deadlock
                # in nested async_safe_run() scenarios
                _thread_pool = ThreadPoolExecutor(
                    max_workers=_MAX_RECURSION_DEPTH + 2,
                    thread_name_prefix="dataflow_async_",
                )
    return _thread_pool


def is_event_loop_running() -> bool:
    """
    Check if an event loop is currently running in the current thread.

    Returns:
        True if an event loop is running, False otherwise.

    Example:
        if is_event_loop_running():
            # We're in an async context (FastAPI, Jupyter, etc.)
            pass
        else:
            # Safe to use asyncio.run()
            pass
    """
    try:
        loop = asyncio.get_running_loop()
        return loop.is_running()
    except RuntimeError:
        return False


def get_execution_context() -> str:
    """
    Detect the current execution context.

    Returns:
        One of:
        - 'fastapi': Running in FastAPI/Uvicorn server
        - 'jupyter': Running in Jupyter notebook
        - 'docker_async': Running in Docker with async server
        - 'async': Running in an async context (generic)
        - 'sync': Standard synchronous context

    Example:
        context = get_execution_context()
        if context == 'fastapi':
            # Use FastAPI-specific optimizations
            pass
    """
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            # Check for common async frameworks
            if "uvicorn" in sys.modules or "starlette" in sys.modules:
                return "fastapi"
            if "IPython" in sys.modules or "ipykernel" in sys.modules:
                return "jupyter"
            # Check for Docker container indicator
            if os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER"):
                return "docker_async"
            return "async"
    except RuntimeError:
        pass
    return "sync"


# Global depth counter for cross-thread tracking
_global_depth = 0
_global_depth_lock = threading.Lock()
_MAX_RECURSION_DEPTH = 10


def async_safe_run(coro: Coroutine[Any, Any, T], timeout: Optional[float] = None) -> T:
    """
    Execute a coroutine safely in any context.

    This function intelligently handles async/sync boundaries:
    - If no event loop is running: uses asyncio.run() (standard sync context)
    - If event loop is running: uses thread pool with separate event loop

    This replaces unsafe `asyncio.run()` calls that fail in FastAPI/Docker.

    Args:
        coro: The coroutine to execute
        timeout: Optional timeout in seconds (default: None = no timeout)

    Returns:
        The result of the coroutine

    Raises:
        RuntimeError: If unable to execute in any context
        TimeoutError: If execution exceeds timeout
        Exception: Any exception raised by the coroutine

    Example:
        async def fetch_data():
            return await some_async_operation()

        # Works in FastAPI endpoint, Docker container, CLI script, or Jupyter
        result = async_safe_run(fetch_data())

    Note:
        For code already in an async context, prefer `await` directly.
        This function is for bridging sync->async boundaries.
    """
    global _global_depth

    # Check recursion depth with thread-safe counter
    with _global_depth_lock:
        if _global_depth >= _MAX_RECURSION_DEPTH:
            raise RuntimeError(
                "async_safe_run() called recursively too many times. "
                "This may indicate an infinite loop or circular dependency."
            )
        _global_depth += 1

    try:
        try:
            loop = asyncio.get_running_loop()
            loop_is_running = loop.is_running()
        except RuntimeError:
            loop_is_running = False
            loop = None

        if not loop_is_running:
            # No event loop running - safe to use asyncio.run()
            context = get_execution_context()
            logger.debug(
                f"async_safe_run: No running loop, using asyncio.run() [context={context}]"
            )

            if timeout is not None:

                async def with_timeout():
                    return await asyncio.wait_for(coro, timeout=timeout)

                return asyncio.run(with_timeout())
            else:
                return asyncio.run(coro)

        # Event loop is running - need to use thread pool
        context = get_execution_context()
        logger.debug(
            f"async_safe_run: Loop running, using thread pool [context={context}]"
        )

        return _run_in_thread_pool(coro, timeout=timeout)
    finally:
        with _global_depth_lock:
            _global_depth = max(0, _global_depth - 1)


def _run_in_thread_pool(
    coro: Coroutine[Any, Any, T], timeout: Optional[float] = None
) -> T:
    """
    Run coroutine in a thread pool with its own event loop.

    This is used when an event loop is already running and we need to
    execute async code synchronously without blocking the main loop.

    Args:
        coro: The coroutine to execute
        timeout: Optional timeout in seconds

    Returns:
        The result of the coroutine

    Raises:
        TimeoutError: If execution exceeds timeout
        Exception: Any exception raised by the coroutine
    """
    result_container = {"result": None, "exception": None}

    def run_coro_in_new_loop():
        """Execute coroutine in a new event loop in this thread."""
        try:
            # Create new event loop for this thread
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                if timeout is not None:

                    async def with_timeout():
                        return await asyncio.wait_for(coro, timeout=timeout)

                    result_container["result"] = new_loop.run_until_complete(
                        with_timeout()
                    )
                else:
                    result_container["result"] = new_loop.run_until_complete(coro)
            finally:
                # Clean up: cancel pending tasks and close loop
                try:
                    _cancel_all_tasks(new_loop)
                except Exception as e:
                    logger.warning(f"Error cancelling tasks: {e}")
                new_loop.close()
        except Exception as e:
            result_container["exception"] = e

    # Use thread pool for efficiency
    pool = _get_thread_pool()
    future: Future = pool.submit(run_coro_in_new_loop)

    # Wait for completion with optional timeout
    thread_timeout = (
        timeout * 2 if timeout else None
    )  # Give extra time for thread overhead
    try:
        future.result(timeout=thread_timeout)
    except TimeoutError:
        raise TimeoutError(
            f"async_safe_run() timed out after {timeout}s. "
            "The async operation took too long to complete."
        )

    if result_container["exception"] is not None:
        raise result_container["exception"]

    return result_container["result"]


def _cancel_all_tasks(loop: asyncio.AbstractEventLoop) -> None:
    """Cancel all pending tasks in the event loop."""
    try:
        tasks = asyncio.all_tasks(loop)
    except RuntimeError:
        # Loop is closed or not running
        return

    for task in tasks:
        task.cancel()

    if tasks:
        loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))


async def ensure_async(value_or_coro: Any) -> Any:
    """
    Ensure a value is awaited if it's a coroutine.

    Useful for handling APIs that may return either sync or async values.

    Args:
        value_or_coro: A value or coroutine

    Returns:
        The awaited result if coroutine, otherwise the value unchanged

    Example:
        async def maybe_async():
            result = some_api_call()  # Might return value or coroutine
            return await ensure_async(result)
    """
    if asyncio.iscoroutine(value_or_coro):
        return await value_or_coro
    return value_or_coro


def run_sync(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., T]:
    """
    Decorator to create a sync wrapper for an async function.

    The decorated function can be called from sync code and will
    automatically handle the async/sync boundary.

    Args:
        func: An async function

    Returns:
        A sync function that calls the async function safely

    Example:
        @run_sync
        async def fetch_data():
            return await some_async_operation()

        # Can now call from sync code
        result = fetch_data()  # Works in any context
    """

    def wrapper(*args, **kwargs):
        return async_safe_run(func(*args, **kwargs))

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    wrapper.__wrapped__ = func
    return wrapper


@contextmanager
def async_context():
    """
    Context manager for tracking async execution context.

    Provides debugging information about nested async_safe_run calls.

    Example:
        with async_context():
            result = async_safe_run(some_coroutine())
    """
    global _global_depth
    with _global_depth_lock:
        _global_depth += 1
        depth = _global_depth
    try:
        yield depth
    finally:
        with _global_depth_lock:
            _global_depth = max(0, _global_depth - 1)


# Track if SQLite warning has been shown (show only once per session)
_sqlite_async_warning_shown = False
_sqlite_warning_lock = threading.Lock()


def warn_sqlite_async_limitation(database_url: str) -> None:
    """
    Warn users about SQLite limitations in async contexts.

    SQLite has thread-affinity constraints - connections created in one thread
    cannot be used in another. While DataFlow handles this with check_same_thread=False,
    :memory: databases still have isolation issues in async contexts.

    This warning is shown once per session when SQLite :memory: is detected
    in an async context (FastAPI, pytest-asyncio, etc.).

    Args:
        database_url: The database URL being used

    Note:
        - File-based SQLite works correctly with check_same_thread=False
        - :memory: SQLite creates separate databases per thread
        - PostgreSQL is recommended for production async applications
    """
    global _sqlite_async_warning_shown

    # Only warn for :memory: in async contexts
    if not database_url:
        return

    is_memory = database_url == ":memory:" or ":memory:" in database_url.lower()
    is_async = is_event_loop_running()

    if is_memory and is_async:
        with _sqlite_warning_lock:
            if not _sqlite_async_warning_shown:
                _sqlite_async_warning_shown = True
                logger.warning(
                    "\n"
                    "╔══════════════════════════════════════════════════════════════════════════╗\n"
                    "║  ⚠️  SQLite :memory: Database in Async Context                           ║\n"
                    "╠══════════════════════════════════════════════════════════════════════════╣\n"
                    "║  SQLite :memory: databases have thread-affinity constraints.             ║\n"
                    "║  Each thread gets a SEPARATE in-memory database.                         ║\n"
                    "║                                                                          ║\n"
                    "║  This may cause issues in FastAPI/pytest-asyncio environments.           ║\n"
                    "║                                                                          ║\n"
                    "║  Recommendations:                                                        ║\n"
                    "║  • Use file-based SQLite: sqlite:///./app.db                             ║\n"
                    "║  • Use PostgreSQL for production: postgresql://user:pass@host/db         ║\n"
                    "║  • For testing: :memory: works in pure sync contexts                     ║\n"
                    "╚══════════════════════════════════════════════════════════════════════════╝\n"
                )


def cleanup_thread_pool() -> None:
    """
    Clean up the shared thread pool.

    Call this during application shutdown to ensure clean exit.

    Example:
        import atexit
        atexit.register(cleanup_thread_pool)
    """
    global _thread_pool
    if _thread_pool is not None:
        with _thread_pool_lock:
            if _thread_pool is not None:
                _thread_pool.shutdown(wait=True)
                _thread_pool = None
                logger.debug("async_utils thread pool cleaned up")


# Register cleanup on module unload
import atexit

atexit.register(cleanup_thread_pool)


__all__ = [
    "async_safe_run",
    "is_event_loop_running",
    "get_execution_context",
    "ensure_async",
    "run_sync",
    "async_context",
    "cleanup_thread_pool",
    "warn_sqlite_async_limitation",
]
