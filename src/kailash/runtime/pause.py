"""Pause/resume controller for cooperative workflow execution control.

This module provides a PauseController that allows external callers to
pause and resume a running workflow. The runtime checks the controller
between node executions, blocking if paused. When paused, the current
node is allowed to complete before the execution loop blocks.

Usage:
    >>> from kailash.runtime.pause import PauseController
    >>> controller = PauseController()
    >>> # Pass to runtime execution
    >>> runtime.execute(workflow, pause_controller=controller)
    >>> # From another thread or coroutine:
    >>> controller.pause(reason="User requested pause")
    >>> # Later:
    >>> controller.resume()

See Also:
    - CancellationToken: Similar cooperative mechanism for cancellation
    - ShutdownCoordinator: Coordinated graceful shutdown

Version:
    Added in: v0.12.0
    Part of: Production readiness (TODO-022)
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import UTC, datetime
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = ["PauseController"]


class PauseController:
    """Thread-safe pause/resume controller for cooperative workflow pausing.

    The controller is checked between node executions by the runtime.
    When paused, the currently executing node is allowed to complete,
    then the execution loop blocks until resumed.

    Thread Safety:
        All methods are thread-safe. The controller can be paused/resumed
        from any thread while the runtime checks it from the execution
        thread/loop. Cross-thread resume uses ``call_soon_threadsafe``
        to wake the event loop reliably.

    Attributes:
        reason: Human-readable reason for the most recent pause (None if never paused).
        paused_at: Timestamp of the most recent pause (None if not currently paused).
        resumed_at: Timestamp of the most recent resume (None if never resumed).
    """

    def __init__(self) -> None:
        """Initialize pause controller in non-paused state."""
        # threading.Event for thread-safe state tracking
        self._thread_event = threading.Event()
        self._thread_event.set()  # SET = not paused

        # asyncio.Event for async waiting (created lazily per-loop)
        self._async_event: Optional[asyncio.Event] = None
        self._async_loop: Optional[asyncio.AbstractEventLoop] = None

        self._reason: Optional[str] = None
        self._paused_at: Optional[datetime] = None
        self._resumed_at: Optional[datetime] = None
        self._pause_count: int = 0
        self._lock = threading.Lock()

    def _get_or_create_async_event(self) -> asyncio.Event:
        """Get or create the asyncio.Event for the current event loop.

        Must be called from within an async context (i.e., from the
        event loop thread).
        """
        loop = asyncio.get_event_loop()
        if self._async_event is None or self._async_loop is not loop:
            self._async_event = asyncio.Event()
            self._async_loop = loop
            # Sync state: if thread_event is set (not paused), async should be set too
            if self._thread_event.is_set():
                self._async_event.set()
            else:
                self._async_event.clear()
        return self._async_event

    @property
    def is_paused(self) -> bool:
        """Check if the controller is currently in paused state.

        This is a lightweight check suitable for high-frequency polling
        in the execution loop.

        Returns:
            True if pause() has been called and resume() has not yet
            been called.
        """
        return not self._thread_event.is_set()

    @property
    def reason(self) -> Optional[str]:
        """Get the reason for the most recent pause, if any."""
        with self._lock:
            return self._reason

    @property
    def paused_at(self) -> Optional[datetime]:
        """Get the timestamp of the most recent pause, if currently paused."""
        with self._lock:
            return self._paused_at

    @property
    def resumed_at(self) -> Optional[datetime]:
        """Get the timestamp of the most recent resume, if any."""
        with self._lock:
            return self._resumed_at

    @property
    def pause_count(self) -> int:
        """Get the total number of times pause() has been called."""
        with self._lock:
            return self._pause_count

    def pause(self, reason: str = "Pause requested") -> None:
        """Request the workflow to pause after the current node completes.

        This method is idempotent -- calling it while already paused
        updates the reason but does not reset the pause timestamp.

        Args:
            reason: Human-readable reason for pausing.

        Thread Safety:
            Safe to call from any thread.
        """
        with self._lock:
            already_paused = not self._thread_event.is_set()
            self._reason = reason
            if not already_paused:
                self._paused_at = datetime.now(UTC)
                self._resumed_at = None
                self._pause_count += 1
            self._thread_event.clear()
            # Also clear the async event if it exists
            if self._async_event is not None:
                if self._async_loop is not None:
                    try:
                        self._async_loop.call_soon_threadsafe(self._async_event.clear)
                    except RuntimeError:
                        # Loop is closed or not running
                        self._async_event.clear()
                else:
                    self._async_event.clear()
            if not already_paused:
                logger.info("Workflow paused: %s", reason)
            else:
                logger.debug("Pause reason updated (already paused): %s", reason)

    def resume(self) -> None:
        """Resume workflow execution after a pause.

        This method is idempotent -- calling it while not paused is a no-op.

        Thread Safety:
            Safe to call from any thread. Uses ``call_soon_threadsafe``
            to wake the asyncio event loop when called from a non-loop thread.
        """
        with self._lock:
            if not self._thread_event.is_set():
                self._resumed_at = datetime.now(UTC)
                self._thread_event.set()
                # Wake the async event on the correct loop
                if self._async_event is not None and self._async_loop is not None:
                    try:
                        self._async_loop.call_soon_threadsafe(self._async_event.set)
                    except RuntimeError:
                        # Loop is closed or not running
                        self._async_event.set()
                logger.info("Workflow resumed (was paused: %s)", self._reason)

    async def wait_if_paused(self) -> None:
        """Block until the controller is not paused.

        This method is intended to be called between node executions
        in the runtime's execution loop. If the controller is not paused,
        this returns immediately. If paused, it blocks until resume()
        is called.

        This is a coroutine so it yields control to the event loop
        while waiting, allowing other tasks (including the one that
        will call resume()) to run.
        """
        if self._thread_event.is_set():
            # Fast path: not paused, return immediately
            return

        logger.debug("Execution blocked - waiting for resume...")
        async_event = self._get_or_create_async_event()
        await async_event.wait()
        logger.debug("Execution resumed - continuing")

    def reset(self) -> None:
        """Reset the controller to its initial non-paused state.

        This is primarily useful for testing. In production, create a new
        controller for each workflow execution.
        """
        with self._lock:
            self._thread_event.set()
            if self._async_event is not None:
                if self._async_loop is not None:
                    try:
                        self._async_loop.call_soon_threadsafe(self._async_event.set)
                    except RuntimeError:
                        self._async_event.set()
                else:
                    self._async_event.set()
            self._reason = None
            self._paused_at = None
            self._resumed_at = None
            self._pause_count = 0
