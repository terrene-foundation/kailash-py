"""Cancellation token for cooperative workflow cancellation.

This module provides a thread-safe, asyncio-compatible cancellation token
that allows external callers to request cancellation of a running workflow.
The runtime checks the token between node executions, providing a cooperative
cancellation mechanism that lets the current node complete before stopping.

Usage:
    >>> from kailash.runtime.cancellation import CancellationToken
    >>> token = CancellationToken()
    >>> # Pass to runtime execution
    >>> runtime.execute(workflow, cancellation_token=token)
    >>> # From another thread or coroutine:
    >>> token.cancel(reason="User requested stop")

See Also:
    - DurableRequest: Uses CancellationToken internally for cancel() support
    - WorkflowCancelledError: Raised when cancellation is detected
"""

import logging
import threading
from datetime import UTC, datetime
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = ["CancellationToken"]


class CancellationToken:
    """Thread-safe cancellation token for cooperative workflow cancellation.

    The token is checked between node executions by the runtime. When cancelled,
    the currently executing node is allowed to complete (grace period), then the
    workflow raises WorkflowCancelledError with details about completed nodes.

    Thread Safety:
        All methods are thread-safe. The token can be cancelled from any thread
        while the runtime checks it from the execution thread/loop.

    Attributes:
        reason: Human-readable reason for cancellation (set when cancel() is called).
        cancelled_at: Timestamp of cancellation (None if not cancelled).
    """

    def __init__(self) -> None:
        """Initialize cancellation token in non-cancelled state."""
        self._cancelled = threading.Event()
        self._reason: Optional[str] = None
        self._cancelled_at: Optional[datetime] = None
        self._lock = threading.Lock()

    @property
    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested.

        This is a lightweight check (no lock acquisition) suitable for
        high-frequency polling in the execution loop.

        Returns:
            True if cancel() has been called.
        """
        return self._cancelled.is_set()

    @property
    def reason(self) -> Optional[str]:
        """Get the cancellation reason, if any."""
        with self._lock:
            return self._reason

    @property
    def cancelled_at(self) -> Optional[datetime]:
        """Get the cancellation timestamp, if any."""
        with self._lock:
            return self._cancelled_at

    def cancel(self, reason: str = "Cancellation requested") -> None:
        """Request cancellation of the workflow.

        This method is idempotent -- calling it multiple times has no additional
        effect beyond the first call. The reason from the first call is preserved.

        Args:
            reason: Human-readable reason for cancellation.

        Thread Safety:
            Safe to call from any thread.
        """
        with self._lock:
            if self._cancelled.is_set():
                # Already cancelled, ignore subsequent calls
                return
            self._reason = reason
            self._cancelled_at = datetime.now(UTC)
            self._cancelled.set()
            logger.info("Cancellation requested: %s", reason)

    def check(self) -> None:
        """Check if cancellation is requested and raise if so.

        This is a convenience method for the runtime execution loop.
        It combines the check and raise into a single call.

        Raises:
            WorkflowCancelledError: If cancellation has been requested.
        """
        if self._cancelled.is_set():
            from kailash.sdk_exceptions import WorkflowCancelledError

            raise WorkflowCancelledError(
                f"Workflow cancelled: {self._reason or 'no reason provided'}"
            )

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for cancellation to be requested.

        Args:
            timeout: Maximum seconds to wait. None means wait indefinitely.

        Returns:
            True if cancellation was requested, False if timeout elapsed.
        """
        return self._cancelled.wait(timeout=timeout)

    def reset(self) -> None:
        """Reset the token to non-cancelled state.

        This is primarily useful for testing. In production, create a new
        token for each workflow execution.
        """
        with self._lock:
            self._cancelled.clear()
            self._reason = None
            self._cancelled_at = None
