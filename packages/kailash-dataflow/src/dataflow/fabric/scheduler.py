# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
FabricScheduler — cron-based product refresh scheduling.

Manages one supervised asyncio.Task per scheduled product. Each task
sleeps until the next cron trigger, then calls the ``on_schedule``
callback to enqueue the product for pipeline re-execution.

Tasks are individually supervised: a crash in one schedule loop does NOT
affect siblings (same pattern as ChangeDetector — doc runtime-redteam RT-1).

Requires ``croniter`` for cron expression parsing (lazy import so the
scheduler module can be imported without croniter installed).

Usage::

    scheduler = FabricScheduler(
        products=registered_products,
        on_schedule=runtime._on_source_change,
    )
    await scheduler.start()
    # ... later ...
    await scheduler.stop()

Design reference: TODO-28 in M5-M6 milestones.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "FabricScheduler",
]

_RESTART_DELAY_SECONDS = 5.0
_MAX_SLEEP_SECONDS = 3600.0  # Cap single sleep to 1 hour for clock-drift safety


class FabricScheduler:
    """Cron-based product refresh scheduler.

    Filters products that declare a ``schedule`` (cron expression) and
    runs one supervised asyncio task per product. Each task calculates
    the next trigger time via ``croniter``, sleeps until then, and calls
    the ``on_schedule`` callback.

    Args:
        products: Mapping of product name to ``ProductRegistration``. Only
            products with a non-``None`` ``schedule`` attribute are
            scheduled.
        on_schedule: Async callback invoked when a schedule fires.
            Receives the product name as its sole argument. Typically
            wired to ``FabricRuntime._on_source_change``.
    """

    def __init__(
        self,
        products: Dict[str, Any],
        on_schedule: Callable[[str], Awaitable[None]],
    ) -> None:
        self._products = products
        self._on_schedule = on_schedule
        self._tasks: List[asyncio.Task[None]] = []
        self._shutting_down = False

        # Build the set of scheduled products at init time
        self._scheduled: Dict[str, str] = {}
        for name, registration in products.items():
            schedule = getattr(registration, "schedule", None)
            if schedule is not None:
                self._scheduled[name] = schedule

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start one supervised task per scheduled product.

        If no products have a schedule, this is a no-op.
        """
        if not self._scheduled:
            logger.debug("FabricScheduler: no scheduled products — nothing to start")
            return

        # Validate croniter is available before starting any tasks
        try:
            from croniter import croniter as _croniter  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "croniter is required for scheduled products. "
                "Install with: pip install croniter"
            ) from exc

        self._shutting_down = False

        for product_name, cron_expr in self._scheduled.items():
            task = asyncio.create_task(
                self._supervised(
                    product_name,
                    lambda pn=product_name, ce=cron_expr: self._schedule_loop(pn, ce),
                ),
                name=f"fabric_scheduler:{product_name}",
            )
            self._tasks.append(task)
            logger.info(
                "FabricScheduler: started schedule for '%s' (cron=%s)",
                product_name,
                cron_expr,
            )

    async def stop(self) -> None:
        """Cancel all schedule tasks and wait for clean shutdown."""
        self._shutting_down = True

        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()
        logger.info("FabricScheduler: all schedule tasks stopped")

    @property
    def running(self) -> bool:
        """True if any schedule tasks are still running."""
        return any(not t.done() for t in self._tasks)

    @property
    def scheduled_products(self) -> Dict[str, str]:
        """Mapping of product name to cron expression for scheduled products."""
        return dict(self._scheduled)

    @property
    def task_count(self) -> int:
        """Number of managed tasks (running or finished)."""
        return len(self._tasks)

    # ------------------------------------------------------------------
    # Supervised execution (RT-1 pattern — same as ChangeDetector)
    # ------------------------------------------------------------------

    async def _supervised(
        self,
        name: str,
        coro_fn: Callable[[], Any],
    ) -> None:
        """Run a background coroutine forever, restarting on failure.

        On ``CancelledError``, the loop exits cleanly (no restart).
        On any other exception, the error is logged and the coroutine
        restarts after a delay.
        """
        while not self._shutting_down:
            try:
                await coro_fn()
                break  # Normal return ends the loop
            except asyncio.CancelledError:
                raise  # CancelledError MUST be re-raised, never swallowed
            except Exception:
                if self._shutting_down:
                    break
                logger.exception(
                    "FabricScheduler: schedule loop '%s' crashed; "
                    "restarting in %.0fs",
                    name,
                    _RESTART_DELAY_SECONDS,
                )
                await asyncio.sleep(_RESTART_DELAY_SECONDS)

    # ------------------------------------------------------------------
    # Schedule loop
    # ------------------------------------------------------------------

    async def _schedule_loop(self, product_name: str, cron_expr: str) -> None:
        """Sleep until the next cron trigger, fire callback, repeat.

        Uses ``croniter`` to calculate the next run time from UTC now.
        The sleep duration is capped at ``_MAX_SLEEP_SECONDS`` to guard
        against clock drift on long intervals — the loop re-checks the
        cron schedule after each sleep.

        Args:
            product_name: Name of the product to refresh.
            cron_expr: Cron expression (5 or 6 field).
        """
        from croniter import croniter

        logger.debug(
            "FabricScheduler: schedule loop '%s' entering main loop (cron=%s)",
            product_name,
            cron_expr,
        )

        while not self._shutting_down:
            now = datetime.now(timezone.utc)
            cron = croniter(cron_expr, now)
            next_run: datetime = cron.get_next(datetime)

            # Ensure next_run is timezone-aware (croniter may return naive)
            if next_run.tzinfo is None:
                next_run = next_run.replace(tzinfo=timezone.utc)

            delay_seconds = (next_run - now).total_seconds()

            # Validate delay is finite and positive
            if not math.isfinite(delay_seconds) or delay_seconds < 0:
                logger.warning(
                    "FabricScheduler: invalid delay %.2f for '%s'; "
                    "using fallback of 60s",
                    delay_seconds,
                    product_name,
                )
                delay_seconds = 60.0

            # Cap sleep to guard against clock drift
            sleep_time = min(delay_seconds, _MAX_SLEEP_SECONDS)

            logger.debug(
                "FabricScheduler: '%s' next run at %s (sleeping %.1fs)",
                product_name,
                next_run.isoformat(),
                sleep_time,
            )

            await asyncio.sleep(sleep_time)

            # If we capped the sleep, re-check whether it is actually time
            if sleep_time < delay_seconds:
                continue

            if self._shutting_down:
                break

            # Fire the callback
            try:
                await self._on_schedule(product_name)
                logger.info(
                    "FabricScheduler: triggered product '%s' (cron=%s)",
                    product_name,
                    cron_expr,
                )
            except Exception:
                logger.exception(
                    "FabricScheduler: on_schedule callback failed for '%s'",
                    product_name,
                )
