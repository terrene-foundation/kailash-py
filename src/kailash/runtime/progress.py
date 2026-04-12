"""Progress reporting for long-running node operations.

This module provides a structured progress reporting system that nodes can use
to emit intermediate status updates during execution. The system is designed to
be fully backward compatible — existing nodes work without changes because
report_progress() is a no-op when no registry is active.

Key Components:
- ProgressUpdate: Immutable progress report from a running node
- ProgressRegistry: Thread-safe registry of progress callbacks
- report_progress(): Convenience function for use inside Node.run()

Usage in a custom node::

    from kailash.runtime.progress import report_progress

    class MyLongRunningNode(Node):
        def run(self, **kwargs):
            items = kwargs["items"]
            for i, item in enumerate(items):
                process(item)
                report_progress(current=i + 1, total=len(items), message=f"Processed {item}")
            return {"processed": len(items)}

Usage by a runtime or UI consumer::

    from kailash.runtime.progress import ProgressRegistry, ProgressUpdate

    registry = ProgressRegistry()
    registry.register(lambda update: print(f"{update.node_id}: {update.fraction:.0%}"))
    # ... pass registry into execution context ...
"""

import contextvars
import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Callable

logger = logging.getLogger(__name__)

# Maximum number of callbacks per registry to prevent unbounded growth
_MAX_CALLBACKS = 10000


@dataclass(frozen=True)
class ProgressUpdate:
    """Immutable progress report from a running node.

    Attributes:
        node_id: Identifier of the node emitting the update.
        current: Current progress count (e.g., items processed).
        total: Total expected count, or None for indeterminate progress.
        message: Optional human-readable status message.
        timestamp: When this update was created (defaults to now).
    """

    node_id: str
    current: int
    total: int | None = None
    message: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def fraction(self) -> float | None:
        """Return progress as 0.0-1.0 if total is known, else None.

        Returns None when total is None (indeterminate) or zero (division guard).
        """
        if self.total is None or self.total == 0:
            return None
        return self.current / self.total


ProgressCallback = Callable[[ProgressUpdate], None]


class ProgressRegistry:
    """Thread-safe registry of progress callbacks for active workflow execution.

    Callbacks are invoked synchronously on the thread that calls emit().
    Register/unregister/emit are all safe to call from multiple threads.

    The registry uses a bounded deque internally to prevent unbounded memory
    growth if callbacks are registered without being unregistered.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._callbacks: deque[ProgressCallback] = deque(maxlen=_MAX_CALLBACKS)

    def register(self, callback: ProgressCallback) -> None:
        """Register a callback to receive progress updates.

        Args:
            callback: Function that accepts a ProgressUpdate. Will be called
                synchronously on emit().
        """
        with self._lock:
            self._callbacks.append(callback)

    def unregister(self, callback: ProgressCallback) -> None:
        """Remove a previously registered callback.

        If the callback is not found, this is a no-op (no error raised).

        Args:
            callback: The same function object passed to register().
        """
        with self._lock:
            try:
                self._callbacks.remove(callback)
            except ValueError:
                pass  # Callback already unregistered; silently ignore duplicate removal

    def emit(self, update: ProgressUpdate) -> None:
        """Emit a progress update to all registered callbacks.

        Each callback is invoked synchronously. If a callback raises an
        exception, it is logged at WARNING level and the remaining callbacks
        still receive the update.

        Args:
            update: The progress update to broadcast.
        """
        with self._lock:
            callbacks = list(self._callbacks)
        for cb in callbacks:
            try:
                cb(update)
            except Exception:
                logger.warning(
                    "progress.callback.error",
                    exc_info=True,
                )

    def clear(self) -> None:
        """Remove all registered callbacks."""
        with self._lock:
            self._callbacks.clear()


# Context variables for progress reporting during node execution.
# These are set by Node.execute() so that report_progress() can discover
# the active registry and node_id without requiring explicit passing.
_current_progress_registry: contextvars.ContextVar[ProgressRegistry | None] = (
    contextvars.ContextVar("_current_progress_registry", default=None)
)

_current_node_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_current_node_id", default=None
)


def report_progress(current: int, total: int | None = None, message: str = "") -> None:
    """Report progress from within a running node.

    This is the primary API for node authors. Call it from inside Node.run()
    to emit progress updates to any registered listeners (UIs, loggers, etc.).

    If no progress registry is active (e.g., the node is being executed in a
    context that does not set up progress tracking), this function is a silent
    no-op for full backward compatibility.

    Args:
        current: Current progress count (e.g., items processed so far).
        total: Total expected count. Pass None for indeterminate progress.
        message: Optional human-readable status message.
    """
    registry = _current_progress_registry.get()
    if registry is None:
        return

    node_id = _current_node_id.get()
    if node_id is None:
        return

    update = ProgressUpdate(
        node_id=node_id,
        current=current,
        total=total,
        message=message,
    )
    registry.emit(update)
