"""
Timeout interrupt handler.

Automatically triggers interrupt when execution time limit is exceeded.
"""

import logging

import anyio

from ..manager import InterruptManager
from ..types import InterruptMode, InterruptSource

logger = logging.getLogger(__name__)


class TimeoutInterruptHandler:
    """
    Automatically interrupt after time limit.

    Monitors execution time and triggers GRACEFUL interrupt when timeout exceeded.
    """

    def __init__(
        self,
        interrupt_manager: InterruptManager,
        timeout_seconds: float,
        warning_threshold: float = 0.8,
    ):
        """
        Initialize timeout handler.

        Args:
            interrupt_manager: InterruptManager to trigger interrupts
            timeout_seconds: Maximum execution time
            warning_threshold: Fraction of timeout at which to warn (0.8 = 80%)
        """
        self.interrupt_manager = interrupt_manager
        self.timeout_seconds = timeout_seconds
        self.warning_threshold = warning_threshold
        self._cancel_scope: anyio.CancelScope | None = None
        self._task_group: anyio.abc.TaskGroup | None = None
        self._warned = False

    async def start(self) -> None:
        """
        Start timeout monitoring.

        Creates background task that will trigger interrupt after timeout.
        """
        if self._cancel_scope:
            logger.warning("Timeout handler already started")
            return

        logger.info(f"Starting timeout monitor: {self.timeout_seconds}s")

        async def timeout_monitor():
            """Monitor timeout and trigger interrupt"""
            # Wait for warning threshold
            warning_time = self.timeout_seconds * self.warning_threshold
            await anyio.sleep(warning_time)

            if not self.interrupt_manager.is_interrupted():
                remaining = self.timeout_seconds - warning_time
                logger.warning(
                    f"Timeout warning: {remaining:.1f}s remaining "
                    f"({self.timeout_seconds}s total)"
                )
                self._warned = True

            # Wait for full timeout
            remaining_time = self.timeout_seconds - warning_time
            await anyio.sleep(remaining_time)

            # Trigger interrupt if not already interrupted
            if not self.interrupt_manager.is_interrupted():
                self.interrupt_manager.request_interrupt(
                    mode=InterruptMode.GRACEFUL,
                    source=InterruptSource.TIMEOUT,
                    message=f"Execution timeout exceeded ({self.timeout_seconds}s)",
                    metadata={"timeout_seconds": self.timeout_seconds},
                )

        # Start monitoring task
        try:
            async with anyio.create_task_group() as tg:
                self._task_group = tg
                tg.start_soon(timeout_monitor)
        except Exception as e:
            logger.error(f"Timeout monitor task failed: {e}")

    async def stop(self) -> None:
        """
        Stop timeout monitoring.

        Cancels background task if running.
        """
        if self._cancel_scope:
            self._cancel_scope.cancel()
            self._cancel_scope = None

        logger.info("Timeout monitor stopped")

    def get_elapsed_time(self) -> float:
        """
        Get elapsed time since start.

        Returns:
            Elapsed time in seconds (approximation)
        """
        # This is approximate - for precise timing, track start time
        return 0.0  # TODO: Implement precise timing

    def get_remaining_time(self) -> float:
        """
        Get remaining time before timeout.

        Returns:
            Remaining time in seconds
        """
        elapsed = self.get_elapsed_time()
        return max(0.0, self.timeout_seconds - elapsed)


# Export all public types
__all__ = [
    "TimeoutInterruptHandler",
]
