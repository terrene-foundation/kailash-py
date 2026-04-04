# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
ChangeDetector — supervised poll loops for source change detection.

Manages one asyncio.Task per source, each running a poll loop that calls
``detect_change()`` on the source adapter. When a change is detected, all
affected products (those whose ``depends_on`` includes the source) are
enqueued for pipeline re-execution.

Tasks are individually supervised: a crash in one poll loop does NOT
affect siblings (doc runtime-redteam RT-1). Crashed tasks auto-restart
with a 5-second delay.

Design references:
- TODO-12 in ``workspaces/data-fabric-engine/todos/active/02-products-and-pipeline.md``
- doc runtime-redteam RT-1 (supervised tasks, NOT TaskGroup)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional

from dataflow.adapters.source_adapter import BaseSourceAdapter

logger = logging.getLogger(__name__)

__all__ = [
    "ChangeDetector",
]

_RESTART_DELAY_SECONDS = 5.0


class ChangeDetector:
    """Supervised poll loops for detecting source data changes.

    Each registered source gets its own ``asyncio.Task`` running a poll loop.
    When ``detect_change()`` returns ``True`` for a source, all products that
    depend on that source are enqueued for pipeline re-execution via the
    provided ``on_change`` callback.

    Args:
        sources: Mapping of source name to source adapter instance.
        products: Mapping of product name to product registration dict. Each
            registration must have a ``depends_on`` key (list of source names).
        pipeline_executor: The :class:`PipelineExecutor` (or any object with
            a ``_queue`` attribute) to receive change notifications. Currently
            the change detector calls the ``on_change`` callback directly.
        dev_mode: Unused currently; reserved for future dev-specific behaviour.
    """

    def __init__(
        self,
        sources: Dict[str, BaseSourceAdapter],
        products: Dict[str, Dict[str, Any]],
        pipeline_executor: Any,
        dev_mode: bool = False,
    ) -> None:
        self._sources = sources
        self._products = products
        self._pipeline_executor = pipeline_executor
        self._dev_mode = dev_mode

        self._tasks: List[asyncio.Task[None]] = []
        self._shutting_down = False

        # Optional callback for when a change triggers product re-execution.
        # Signature: async fn(product_name: str, triggered_by: str) -> None
        self._on_change: Optional[Callable[[str, str], Coroutine[Any, Any, None]]] = (
            None
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_on_change(
        self, callback: Callable[[str, str], Coroutine[Any, Any, None]]
    ) -> None:
        """Register a callback invoked when a change triggers product refresh.

        The callback receives ``(product_name, triggered_by_source)`` and
        should be an async function (typically enqueues into PipelineExecutor).
        """
        self._on_change = callback

    async def start(self) -> None:
        """Start all poll loops as individually supervised asyncio Tasks.

        One task per source. Tasks are NOT started via ``TaskGroup`` to ensure
        crash isolation (RT-1): a failure in one loop does not cancel siblings.
        """
        self._shutting_down = False
        for source_name, adapter in self._sources.items():
            poll_interval = self._get_poll_interval(adapter)
            task = asyncio.create_task(
                self._supervised(
                    source_name,
                    lambda sn=source_name, ad=adapter, pi=poll_interval: self._poll_loop(
                        sn, ad, pi
                    ),
                ),
                name=f"change_detector:{source_name}",
            )
            self._tasks.append(task)
            logger.debug(
                "ChangeDetector: started poll loop for '%s' (interval=%.1fs)",
                source_name,
                poll_interval,
            )

    async def stop(self) -> None:
        """Stop all poll loops gracefully.

        Sets the shutdown flag, cancels all tasks, and gathers with
        ``return_exceptions=True`` to avoid propagating ``CancelledError``.
        """
        self._shutting_down = True

        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()
        logger.debug("ChangeDetector: all poll loops stopped")

    @property
    def running(self) -> bool:
        """True if any poll loop tasks are still running."""
        return any(not t.done() for t in self._tasks)

    @property
    def task_count(self) -> int:
        """Number of managed tasks (running or finished)."""
        return len(self._tasks)

    # ------------------------------------------------------------------
    # Supervised execution (RT-1 pattern)
    # ------------------------------------------------------------------

    async def _supervised(
        self,
        name: str,
        coro_fn: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        """Run a background coroutine forever, restarting on failure.

        On ``CancelledError``, the loop exits cleanly (no restart).
        On any other exception, the error is logged and the coroutine
        restarts after a 5-second delay.

        This is the exact supervised-task pattern from RT-1 resolution:
        individual tasks, not TaskGroup, with per-task crash isolation.
        """
        while not self._shutting_down:
            try:
                await coro_fn()
                # If coro_fn returns normally, the loop ends.
                break
            except asyncio.CancelledError:
                # CancelledError MUST be re-raised, never swallowed.
                raise
            except Exception:
                if self._shutting_down:
                    break
                logger.exception(
                    "ChangeDetector: poll loop '%s' crashed; restarting in %.0fs",
                    name,
                    _RESTART_DELAY_SECONDS,
                )
                await asyncio.sleep(_RESTART_DELAY_SECONDS)

    # ------------------------------------------------------------------
    # Poll loop
    # ------------------------------------------------------------------

    async def _poll_loop(
        self,
        source_name: str,
        adapter: BaseSourceAdapter,
        poll_interval: float,
    ) -> None:
        """Continuously poll a source for changes and trigger affected products.

        Uses ``safe_detect_change()`` which integrates the circuit breaker.
        When a change is detected, all products whose ``depends_on`` includes
        ``source_name`` are dispatched via the on_change callback.
        """
        logger.debug("ChangeDetector: poll loop '%s' entering main loop", source_name)

        while not self._shutting_down:
            try:
                changed = await adapter.safe_detect_change()
            except Exception:
                # safe_detect_change raises when the circuit breaker trips.
                # The supervised wrapper will handle restart if this propagates,
                # but we prefer to keep polling (the circuit breaker already
                # blocks requests while open, so next iteration will return
                # False until the probe interval elapses).
                logger.warning(
                    "ChangeDetector: change detection failed for '%s'",
                    source_name,
                    exc_info=True,
                )
                await asyncio.sleep(poll_interval)
                continue

            if changed:
                affected = self._get_affected_products(source_name)
                if affected:
                    logger.debug(
                        "ChangeDetector: source '%s' changed — triggering %d product(s): %s",
                        source_name,
                        len(affected),
                        affected,
                    )
                    for product_name in affected:
                        await self._dispatch_product(product_name, source_name)
                else:
                    logger.debug(
                        "ChangeDetector: source '%s' changed but no products depend on it",
                        source_name,
                    )

            await asyncio.sleep(poll_interval)

    # ------------------------------------------------------------------
    # Product dependency resolution
    # ------------------------------------------------------------------

    def _get_affected_products(self, source_name: str) -> List[str]:
        """Return product names whose ``depends_on`` includes ``source_name``."""
        affected: List[str] = []
        for product_name, registration in self._products.items():
            # Support both ProductRegistration dataclass (attribute access)
            # and plain dicts (legacy / tests).
            if hasattr(registration, "depends_on"):
                depends_on = registration.depends_on
            elif isinstance(registration, dict):
                depends_on = registration.get("depends_on", [])
            else:
                depends_on = []
            if source_name in depends_on:
                affected.append(product_name)
        return affected

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def _dispatch_product(self, product_name: str, triggered_by: str) -> None:
        """Dispatch a product for re-execution.

        If an ``on_change`` callback is registered, it is called. Otherwise,
        the change event is placed on the pipeline executor's queue.
        """
        if self._on_change is not None:
            try:
                await self._on_change(product_name, triggered_by)
            except Exception:
                logger.exception(
                    "ChangeDetector: on_change callback failed for product '%s'",
                    product_name,
                )
            return

        # Fallback: push to the pipeline executor queue if it has one.
        queue = getattr(self._pipeline_executor, "_queue", None)
        if queue is not None:
            msg = {
                "product_name": product_name,
                "triggered_by": triggered_by,
                "detected_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                queue.put_nowait(msg)
            except asyncio.QueueFull:
                logger.warning(
                    "ChangeDetector: pipeline queue full — dropping change event "
                    "for product '%s' (triggered by '%s')",
                    product_name,
                    triggered_by,
                )
        else:
            logger.warning(
                "ChangeDetector: no dispatch target for product '%s' "
                "(no on_change callback and no pipeline queue)",
                product_name,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_poll_interval(adapter: Any) -> float:
        """Extract poll interval from the adapter's config or use default.

        Handles both ``BaseSourceAdapter`` instances and legacy dict
        source info (extracting the adapter from the ``"adapter"`` key
        if necessary).
        """
        # If a dict was passed (shouldn't happen after #253 fix, but
        # be defensive), extract the real adapter from it.
        if isinstance(adapter, dict):
            adapter = adapter.get("adapter")
            if adapter is None:
                return 60.0

        # Source adapters may store their config in various attributes.
        config = getattr(adapter, "_config", None) or getattr(adapter, "config", None)
        if config is not None:
            interval = getattr(config, "poll_interval", None)
            if interval is not None and isinstance(interval, (int, float)):
                return float(interval)
        return 60.0  # Default 60s poll interval
