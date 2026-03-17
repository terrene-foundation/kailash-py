"""Workflow signal and query system for external interaction with running workflows.

This module provides SignalChannel and QueryRegistry, enabling external callers
to send signals to and query the state of running workflows. Signals are queued
messages that nodes can wait for, while queries are synchronous inspections of
workflow state.

Architecture:
    - SignalChannel: Async queue-based signal delivery between external callers
      and workflow nodes. Each signal name gets its own queue, allowing multiple
      independent signal streams within a single workflow.
    - QueryRegistry: Registry of named query handlers that return workflow state.
      Handlers are registered by nodes or the runtime and invoked by external callers.

Usage:
    Sending a signal to a running workflow::

        >>> runtime = LocalRuntime()
        >>> # Start workflow in background (contains a SignalWaitNode)
        >>> # ... then from another coroutine or thread:
        >>> runtime.signal(workflow_id, "approval", {"approved": True})

    Querying workflow state::

        >>> result = await runtime.query(workflow_id, "progress")

See Also:
    - SignalWaitNode: Node that blocks until a named signal is received
    - LocalRuntime.signal: Runtime method for sending signals
    - LocalRuntime.query: Runtime method for querying workflow state
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class SignalChannel:
    """Channel for sending signals to and receiving signals from a running workflow.

    A SignalChannel provides named signal queues for asynchronous communication
    between external callers and workflow nodes. Each signal name maps to an
    independent asyncio.Queue, allowing multiple signal streams.

    Signals are fire-and-forget from the sender's perspective. The receiver
    (typically a SignalWaitNode) awaits the signal asynchronously with an
    optional timeout.

    Thread Safety:
        The send() method is safe to call from any thread because
        asyncio.Queue.put_nowait() is thread-safe for adding items.
        The wait_for() method must be called from within an async context.

    Example:
        >>> channel = SignalChannel()
        >>> channel.send("approval", {"approved": True, "reviewer": "alice"})
        >>> data = await channel.wait_for("approval", timeout=30.0)
        >>> print(data)  # {"approved": True, "reviewer": "alice"}
    """

    def __init__(self) -> None:
        self._signals: Dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()

    def _ensure_queue(self, signal_name: str) -> asyncio.Queue:
        """Get or create a queue for the given signal name.

        This method is not async-safe for concurrent creation of the same
        signal name. Use _ensure_queue_safe for async contexts where
        concurrent creation is possible.

        Args:
            signal_name: The signal name to get or create a queue for.

        Returns:
            The asyncio.Queue for the signal name.
        """
        return self._signals.setdefault(signal_name, asyncio.Queue(maxsize=10000))

    async def _ensure_queue_safe(self, signal_name: str) -> asyncio.Queue:
        """Get or create a queue for the given signal name (async-safe).

        Uses an asyncio.Lock to prevent race conditions when multiple
        coroutines attempt to create the same signal queue simultaneously.

        Args:
            signal_name: The signal name to get or create a queue for.

        Returns:
            The asyncio.Queue for the signal name.
        """
        async with self._lock:
            return self._ensure_queue(signal_name)

    def send(self, signal_name: str, data: Any = None) -> None:
        """Send a signal (non-blocking). Creates queue if it does not exist.

        The signal data is enqueued immediately. If no receiver is waiting,
        the data remains in the queue until a receiver calls wait_for().

        Args:
            signal_name: Name of the signal to send.
            data: Arbitrary data payload to send with the signal.
                  Can be any type; the receiver gets exactly what is sent.

        Example:
            >>> channel.send("user_input", {"text": "hello"})
            >>> channel.send("shutdown")  # data defaults to None
        """
        queue = self._ensure_queue(signal_name)
        try:
            queue.put_nowait(data)
        except asyncio.QueueFull:
            logger.warning(
                "Signal queue '%s' full (maxsize=%d), dropping oldest item",
                signal_name,
                queue.maxsize,
            )
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            queue.put_nowait(data)
        logger.debug("Signal '%s' sent (queue depth: %d)", signal_name, queue.qsize())

    async def wait_for(self, signal_name: str, timeout: Optional[float] = None) -> Any:
        """Wait for a signal (async blocking). Returns the signal data.

        Blocks the calling coroutine until a signal with the given name is
        available, or until the timeout expires.

        Args:
            signal_name: Name of the signal to wait for.
            timeout: Maximum seconds to wait. None means wait indefinitely.

        Returns:
            The data payload sent with the signal.

        Raises:
            TimeoutError: If timeout expires before a signal is received.

        Example:
            >>> try:
            ...     data = await channel.wait_for("approval", timeout=60.0)
            ...     print(f"Approved: {data}")
            ... except TimeoutError:
            ...     print("Timed out waiting for approval")
        """
        queue = await self._ensure_queue_safe(signal_name)

        try:
            result = await asyncio.wait_for(queue.get(), timeout=timeout)
            logger.debug("Signal '%s' received", signal_name)
            return result
        except asyncio.TimeoutError:
            raise TimeoutError(f"Timed out waiting for signal '{signal_name}'")

    def has_pending(self, signal_name: str) -> bool:
        """Check if there are pending (unread) signals for the given name.

        Args:
            signal_name: Name of the signal to check.

        Returns:
            True if at least one signal is queued and unread, False otherwise.

        Example:
            >>> channel.send("data_ready", {"batch": 1})
            >>> assert channel.has_pending("data_ready")
            >>> assert not channel.has_pending("nonexistent")
        """
        return signal_name in self._signals and not self._signals[signal_name].empty()

    def pending_count(self, signal_name: str) -> int:
        """Return the number of pending signals for the given name.

        Args:
            signal_name: Name of the signal to check.

        Returns:
            Number of queued signals. Returns 0 if the signal name has no queue.
        """
        if signal_name not in self._signals:
            return 0
        return self._signals[signal_name].qsize()

    @property
    def signal_names(self) -> List[str]:
        """Return list of all signal names that have been used.

        Returns:
            List of signal name strings.
        """
        return list(self._signals.keys())


class QueryRegistry:
    """Registry for query handlers on a running workflow.

    A QueryRegistry allows nodes and the runtime to register named query
    handlers that external callers can invoke to inspect workflow state.
    Query handlers are simple callables (sync or async) that accept keyword
    arguments and return a result.

    Example:
        >>> registry = QueryRegistry()
        >>> registry.register("progress", lambda: {"completed": 5, "total": 10})
        >>> result = await registry.query("progress")
        >>> print(result)  # {"completed": 5, "total": 10}
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, Callable] = {}

    def register(self, query_name: str, handler: Callable) -> None:
        """Register a query handler.

        If a handler with the same name already exists, it is replaced.

        Args:
            query_name: Name of the query (used as the lookup key).
            handler: Callable that implements the query. Can be sync or async.
                     Receives keyword arguments from the query() call.

        Example:
            >>> def get_status():
            ...     return {"status": "running", "iteration": 42}
            >>> registry.register("status", get_status)
        """
        self._handlers[query_name] = handler
        logger.debug("Query handler registered: '%s'", query_name)

    def unregister(self, query_name: str) -> None:
        """Remove a registered query handler.

        Args:
            query_name: Name of the query handler to remove.

        Raises:
            KeyError: If no handler is registered with the given name.
        """
        if query_name not in self._handlers:
            raise KeyError(f"No handler registered for query '{query_name}'")
        del self._handlers[query_name]
        logger.debug("Query handler unregistered: '%s'", query_name)

    async def query(self, query_name: str, **kwargs: Any) -> Any:
        """Execute a registered query handler.

        Invokes the handler registered under query_name, passing any keyword
        arguments. Supports both synchronous and asynchronous handlers.

        Args:
            query_name: Name of the query to execute.
            **kwargs: Keyword arguments passed to the handler.

        Returns:
            The return value of the query handler.

        Raises:
            KeyError: If no handler is registered for the given query name.

        Example:
            >>> result = await registry.query("status")
            >>> result = await registry.query("node_output", node_id="processor")
        """
        if query_name not in self._handlers:
            raise KeyError(f"No handler registered for query '{query_name}'")

        handler = self._handlers[query_name]
        if asyncio.iscoroutinefunction(handler):
            return await handler(**kwargs)
        return handler(**kwargs)

    @property
    def registered_queries(self) -> List[str]:
        """Return list of all registered query names.

        Returns:
            List of query name strings.
        """
        return list(self._handlers.keys())

    def has_handler(self, query_name: str) -> bool:
        """Check if a handler is registered for the given query name.

        Args:
            query_name: Name of the query to check.

        Returns:
            True if a handler exists, False otherwise.
        """
        return query_name in self._handlers
