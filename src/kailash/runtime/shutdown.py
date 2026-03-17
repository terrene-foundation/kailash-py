"""Coordinated graceful shutdown across all subsystems.

This module provides ShutdownCoordinator, which sequences cleanup across
all registered subsystems by priority. Each subsystem registers a cleanup
handler with a priority level, and the coordinator executes them in order
during shutdown.

Priority levels (convention):
    - 0: Stop accepting new work (server, API gateway)
    - 1: Drain in-progress workflows (runtime, executors)
    - 2: Flush stores (event store, checkpoints, audit logs)
    - 3: Close connections (DB pools, Redis, circuit breakers)

Examples:
    Basic usage::

        coordinator = ShutdownCoordinator(timeout=30.0)
        coordinator.register("server", server.stop, priority=0)
        coordinator.register("runtime", runtime.close, priority=1)
        coordinator.register("db_pool", pool.dispose, priority=3)

        results = await coordinator.shutdown()
        # {"server": "ok", "runtime": "ok", "db_pool": "ok"}

    Signal handler installation::

        coordinator.install_signal_handlers(loop)
        # SIGTERM and SIGINT now trigger coordinated shutdown

    Double-shutdown protection::

        await coordinator.shutdown()  # executes all handlers
        await coordinator.shutdown()  # no-op, returns {}

Version:
    Added in: v0.12.0
    Part of: Production readiness (TODO-015)
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

__all__ = ["ShutdownCoordinator"]


class ShutdownCoordinator:
    """Sequences shutdown across all registered subsystems by priority.

    Handlers are executed in ascending priority order (lower number = earlier).
    Each handler gets an individual timeout derived from the total timeout
    divided by the number of handlers. If a handler times out or raises an
    exception, the coordinator logs the failure and continues to the next
    handler -- one failing subsystem never blocks shutdown of others.

    Attributes:
        is_shutting_down: Whether shutdown is currently in progress or complete.
    """

    def __init__(self, timeout: float = 30.0) -> None:
        """Initialize the shutdown coordinator.

        Args:
            timeout: Total time budget for all handlers in seconds.
                     Each handler gets ``timeout / handler_count`` seconds.
                     Must be positive.

        Raises:
            ValueError: If timeout is not positive or not finite.
        """
        import math

        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError(f"timeout must be a positive finite number, got {timeout}")

        self._handlers: List[Tuple[int, str, Callable]] = []
        self._timeout = timeout
        self._shutting_down = False

    def register(self, name: str, cleanup: Callable, priority: int = 3) -> None:
        """Register a cleanup handler with priority (lower = earlier).

        Args:
            name: Human-readable name for logging (e.g. ``"event_store"``).
            cleanup: Callable (sync or async) to invoke during shutdown.
                     Must accept no arguments.
            priority: Execution priority. Lower numbers run first.
                      Convention: 0=stop accepting, 1=drain, 2=flush, 3=close.

        Raises:
            ValueError: If name is empty or cleanup is not callable.
        """
        if not name:
            raise ValueError("Handler name must not be empty")
        if not callable(cleanup):
            raise ValueError(f"Handler '{name}' cleanup must be callable")

        self._handlers.append((priority, name, cleanup))
        self._handlers.sort(key=lambda x: (x[0], x[1]))
        logger.debug("Registered shutdown handler: %s (priority %d)", name, priority)

    @property
    def is_shutting_down(self) -> bool:
        """Whether shutdown is in progress or has completed."""
        return self._shutting_down

    async def shutdown(self) -> Dict[str, str]:
        """Execute all handlers in priority order.

        Returns a status dictionary mapping handler name to outcome:
        ``"ok"``, ``"timeout"``, or ``"error: <message>"``.

        If shutdown is already in progress (or complete), returns an empty
        dict immediately -- double-shutdown is a safe no-op.

        Returns:
            Dictionary of ``{handler_name: status_string}``.
        """
        if self._shutting_down:
            logger.warning("Shutdown already in progress or completed")
            return {}

        self._shutting_down = True
        results: Dict[str, str] = {}

        handler_count = len(self._handlers)
        if handler_count == 0:
            logger.info("Graceful shutdown: no handlers registered")
            return results

        per_handler_timeout = self._timeout / handler_count

        logger.info(
            "Starting graceful shutdown (%d handlers, %.1fs total timeout, "
            "%.1fs per handler)",
            handler_count,
            self._timeout,
            per_handler_timeout,
        )

        for priority, name, handler in self._handlers:
            try:
                logger.info("Shutdown [%d] %s...", priority, name)
                if asyncio.iscoroutinefunction(handler):
                    await asyncio.wait_for(handler(), timeout=per_handler_timeout)
                else:
                    # Run sync handler -- still respect timeout via executor
                    loop = asyncio.get_running_loop()
                    await asyncio.wait_for(
                        loop.run_in_executor(None, handler),
                        timeout=per_handler_timeout,
                    )
                results[name] = "ok"
                logger.info("Shutdown [%d] %s -- done", priority, name)
            except asyncio.TimeoutError:
                results[name] = "timeout"
                logger.error("Shutdown [%d] %s -- TIMEOUT", priority, name)
            except Exception as exc:
                results[name] = f"error: {exc}"
                logger.error("Shutdown [%d] %s -- ERROR: %s", priority, name, exc)

        logger.info("Graceful shutdown complete: %s", results)
        return results

    def install_signal_handlers(
        self, loop: Optional[asyncio.AbstractEventLoop] = None
    ) -> None:
        """Install SIGTERM/SIGINT handlers that trigger coordinated shutdown.

        This should be called once during application startup. The signal
        handlers schedule ``self.shutdown()`` as an asyncio task on the
        provided (or current) event loop.

        Args:
            loop: Event loop to install handlers on. Defaults to the
                  running loop.

        Raises:
            RuntimeError: If no event loop is available.

        Note:
            Signal handlers can only be installed on the main thread.
            On non-Unix platforms (Windows), only SIGINT is installed.
        """
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()

        def _trigger_shutdown() -> None:
            if not self._shutting_down:
                logger.info("Signal received, triggering coordinated shutdown")
                loop.create_task(self.shutdown())

        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, _trigger_shutdown)
            logger.debug("Installed signal handlers for SIGTERM and SIGINT")
        except NotImplementedError:
            # Windows does not support add_signal_handler for SIGTERM
            signal.signal(signal.SIGINT, lambda s, f: _trigger_shutdown())
            logger.debug("Installed fallback signal handler for SIGINT (Windows)")
