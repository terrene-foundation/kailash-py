# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""DerivedModelEngine -- application-layer materialized views for DataFlow.

Supports ``refresh="scheduled"``, ``refresh="manual"``, and
``refresh="on_source_change"`` modes.  Derived models declare source
models and a ``compute()`` static method that transforms source data
into derived records.

``on_source_change`` subscribes to Core SDK EventBus write events for
each source model and triggers an asynchronous, debounced recompute.

.. warning::

    DerivedModel loads **all** source records into memory via
    ``db.express.list(src, limit=None)``.  For tables exceeding available
    RAM, use SQL materialized views directly.  Streaming/incremental
    compute is planned for v2.

Access via ``db.derived_model_status()`` and ``db.refresh_derived(name)``.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "DerivedModelEngine",
    "DerivedModelMeta",
    "DerivedModelRefreshScheduler",
    "RefreshResult",
]

# ---------------------------------------------------------------------------
# Interval parsing
# ---------------------------------------------------------------------------

_INTERVAL_RE = re.compile(
    r"^every\s+(\d+)\s*(s|sec|second|seconds|m|min|minute|minutes|h|hr|hour|hours)$",
    re.IGNORECASE,
)

_UNIT_TO_SECONDS = {
    "s": 1,
    "sec": 1,
    "second": 1,
    "seconds": 1,
    "m": 60,
    "min": 60,
    "minute": 60,
    "minutes": 60,
    "h": 3600,
    "hr": 3600,
    "hour": 3600,
    "hours": 3600,
}


def _parse_interval(schedule: str) -> Optional[float]:
    """Parse a human-readable interval string like ``'every 6h'``.

    Returns seconds as a float, or ``None`` if the string is not a
    recognized interval format.
    """
    m = _INTERVAL_RE.match(schedule.strip())
    if m is None:
        return None
    value = int(m.group(1))
    unit = m.group(2).lower()
    return float(value * _UNIT_TO_SECONDS[unit])


def _next_cron_fire(schedule: str, after: datetime) -> Optional[datetime]:
    """Compute the next fire time for a cron expression.

    Requires the optional ``croniter`` package.  Returns ``None`` if
    ``croniter`` is not installed.
    """
    try:
        from croniter import croniter  # type: ignore[import-untyped]

        cron = croniter(schedule, after)
        return cron.get_next(datetime)
    except ImportError:
        return None
    except (ValueError, KeyError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DerivedModelMeta:
    """Metadata for a single derived model."""

    model_name: str
    sources: List[str]
    refresh: Literal["scheduled", "manual", "on_source_change"]
    schedule: Optional[str]  # cron string or "every Nh/Nm"
    compute_fn: Callable[[Dict[str, List[Dict[str, Any]]]], List[Dict[str, Any]]]
    debounce_ms: float = 100.0  # Debounce window for on_source_change (ms)
    last_refreshed: Optional[datetime] = None
    next_scheduled: Optional[datetime] = None
    status: str = "pending"  # pending | refreshing | ok | error
    last_error: Optional[str] = None


@dataclass
class RefreshResult:
    """Outcome of refreshing a derived model."""

    model_name: str
    records_upserted: int
    duration_ms: float
    sources_queried: Dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Circular dependency detection
# ---------------------------------------------------------------------------


class CircularDependencyError(Exception):
    """Raised when derived model sources form a cycle."""

    pass


def _detect_cycles(models: Dict[str, DerivedModelMeta]) -> Optional[List[str]]:
    """DFS cycle detection on the source-to-derived graph.

    Returns a cycle path list if a cycle is found, else ``None``.
    """
    # Build adjacency: source -> [derived models that depend on it]
    # But for cycle detection we need: derived -> sources
    # A cycle exists if model A sources model B and model B sources model A (transitively).

    # adjacency: model_name -> list of source model names
    adjacency: Dict[str, List[str]] = {}
    for name, meta in models.items():
        adjacency[name] = list(meta.sources)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = {name: WHITE for name in adjacency}
    path: List[str] = []

    def dfs(node: str) -> Optional[List[str]]:
        color[node] = GRAY
        path.append(node)
        for dep in adjacency.get(node, []):
            if dep not in color:
                # dep is not a derived model -- skip (it's a plain model)
                continue
            if color[dep] == GRAY:
                # Found cycle: extract cycle from path
                cycle_start = path.index(dep)
                return path[cycle_start:] + [dep]
            if color[dep] == WHITE:
                result = dfs(dep)
                if result is not None:
                    return result
        path.pop()
        color[node] = BLACK
        return None

    for node in adjacency:
        if color[node] == WHITE:
            cycle = dfs(node)
            if cycle is not None:
                return cycle
    return None


# ---------------------------------------------------------------------------
# DerivedModelEngine
# ---------------------------------------------------------------------------


class DerivedModelEngine:
    """Manages derived model registration, refresh, and status.

    .. warning::

        DerivedModel loads all source records into memory.  For tables
        exceeding available RAM, use SQL materialized views directly.
    """

    def __init__(self, dataflow_instance: Any) -> None:
        self._db = dataflow_instance
        self._models: Dict[str, DerivedModelMeta] = {}
        self._scheduler: Optional[DerivedModelRefreshScheduler] = None
        # TSG-101: Debounce timers for on_source_change mode
        self._debounce_handles: Dict[str, asyncio.TimerHandle] = {}
        self._event_subscriptions_active: bool = False

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, meta: DerivedModelMeta) -> None:
        """Register a derived model.

        Raises:
            ValueError: If the model name is already registered as derived.
        """
        if meta.model_name in self._models:
            raise ValueError(
                f"Derived model '{meta.model_name}' is already registered."
            )
        self._models[meta.model_name] = meta
        logger.info(
            "Registered derived model '%s' (sources=%s, refresh=%s, schedule=%s)",
            meta.model_name,
            meta.sources,
            meta.refresh,
            meta.schedule,
        )

    def validate_dependencies(self) -> None:
        """Validate there are no circular dependencies among derived models.

        Should be called at ``db.initialize()`` time.

        Raises:
            CircularDependencyError: If a cycle is detected.
        """
        cycle = _detect_cycles(self._models)
        if cycle is not None:
            cycle_str = " -> ".join(cycle)
            raise CircularDependencyError(
                f"Circular dependency detected among derived models: {cycle_str}"
            )

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    async def refresh(self, model_name: str) -> RefreshResult:
        """Execute the compute pipeline for a derived model.

        1. Query all source models via ``db.express.list(src, limit=None)``
        2. Call the derived model's ``compute()`` with source data
        3. Bulk-create the derived records (clear + insert strategy)

        Args:
            model_name: The name of the derived model to refresh.

        Returns:
            RefreshResult with upsert count, timings, and error info.
        """
        if model_name not in self._models:
            return RefreshResult(
                model_name=model_name,
                records_upserted=0,
                duration_ms=0.0,
                error=f"Derived model '{model_name}' is not registered.",
            )

        meta = self._models[model_name]
        meta.status = "refreshing"
        meta.last_error = None
        start = time.monotonic()

        try:
            # Step 1: Gather source data
            sources: Dict[str, List[Dict[str, Any]]] = {}
            for src_name in meta.sources:
                records = await self._db.express.list(src_name, limit=10_000_000)
                sources[src_name] = records

            sources_queried = {src: len(recs) for src, recs in sources.items()}

            # Step 2: Compute derived data
            derived_records = meta.compute_fn(sources)

            # Step 3: Upsert derived records (delete-then-create per record)
            records_upserted = 0
            if derived_records:
                # Delete existing records one by one to avoid filter issues
                for record in derived_records:
                    record_id = record.get("id")
                    if record_id is not None:
                        try:
                            await self._db.express.delete(model_name, str(record_id))
                        except Exception:
                            pass  # Record may not exist yet -- that's fine

                # Bulk create the new records
                await self._db.express.bulk_create(model_name, derived_records)
                records_upserted = len(derived_records)

            elapsed_ms = (time.monotonic() - start) * 1000
            meta.status = "ok"
            meta.last_refreshed = datetime.now(timezone.utc)

            # Update next_scheduled for scheduled models
            if meta.refresh == "scheduled" and meta.schedule:
                meta.next_scheduled = self._compute_next_fire(meta)

            return RefreshResult(
                model_name=model_name,
                records_upserted=records_upserted,
                duration_ms=elapsed_ms,
                sources_queried=sources_queried,
            )

        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            meta.status = "error"
            meta.last_error = str(exc)
            logger.error("Refresh of derived model '%s' failed: %s", model_name, exc)
            return RefreshResult(
                model_name=model_name,
                records_upserted=0,
                duration_ms=elapsed_ms,
                sources_queried={},
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, DerivedModelMeta]:
        """Return metadata for all registered derived models."""
        return dict(self._models)

    # ------------------------------------------------------------------
    # Scheduler management
    # ------------------------------------------------------------------

    async def start_scheduler(self) -> None:
        """Start background scheduler for all scheduled derived models."""
        scheduled = {
            name: meta
            for name, meta in self._models.items()
            if meta.refresh == "scheduled"
        }
        if not scheduled:
            logger.debug("No scheduled derived models -- skipping scheduler start.")
            return

        # Compute initial next_scheduled times
        for meta in scheduled.values():
            if meta.next_scheduled is None:
                meta.next_scheduled = self._compute_next_fire(meta)

        self._scheduler = DerivedModelRefreshScheduler(self)
        await self._scheduler.start()

    async def stop_scheduler(self) -> None:
        """Stop the background scheduler if running."""
        if self._scheduler is not None:
            await self._scheduler.stop()
            self._scheduler = None

    # ------------------------------------------------------------------
    # TSG-101: on_source_change event subscriptions
    # ------------------------------------------------------------------

    def setup_event_subscriptions(self) -> int:
        """Subscribe to source model write events for on_source_change models.

        Subscribes to all 8 WRITE_OPERATIONS per source model per derived
        model.  Uses exact event types (no wildcards -- R1-1).

        Must be called after ``db.initialize()`` when the event bus is
        available.

        Returns:
            Number of subscriptions created.
        """
        from dataflow.core.events import WRITE_OPERATIONS

        if self._event_subscriptions_active:
            return 0

        event_bus = getattr(self._db, "_event_bus", None)
        if event_bus is None:
            logger.debug(
                "DerivedModelEngine: No event bus available -- "
                "skipping on_source_change subscriptions."
            )
            return 0

        subscription_count = 0
        for meta in self._models.values():
            if meta.refresh != "on_source_change":
                continue
            for source in meta.sources:
                for op in WRITE_OPERATIONS:
                    event_type = f"dataflow.{source}.{op}"
                    # Bind meta to the lambda via default argument to avoid
                    # late-binding closure issue.
                    event_bus.subscribe(
                        event_type,
                        lambda event, m=meta: self._on_source_change(m, event),
                    )
                    subscription_count += 1

        if subscription_count > 0:
            self._event_subscriptions_active = True
            logger.info(
                "DerivedModelEngine: %d event subscriptions created for "
                "on_source_change derived models.",
                subscription_count,
            )
        return subscription_count

    def _on_source_change(self, meta: DerivedModelMeta, event: Any) -> None:
        """Debounced handler for source model change events.

        Cancels any pending debounce timer for this derived model and
        schedules a new recompute after the debounce window.  The
        recompute is dispatched via ``asyncio.create_task()``
        (fire-and-forget, non-blocking to the write path).
        """
        key = meta.model_name
        # Cancel existing debounce timer
        if key in self._debounce_handles:
            self._debounce_handles[key].cancel()

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # No running event loop -- log and skip
            logger.debug(
                "DerivedModelEngine: No event loop for on_source_change "
                "handler of '%s'.",
                key,
            )
            return

        # Schedule recompute after debounce window
        self._debounce_handles[key] = loop.call_later(
            meta.debounce_ms / 1000.0,
            lambda m=meta: asyncio.ensure_future(self._safe_refresh(m)),
        )

    async def _safe_refresh(self, meta: DerivedModelMeta) -> None:
        """Fire-and-forget refresh with error capture.

        Failed recomputes update ``meta.last_error`` and ``meta.status``
        so that ``db.derived_model_status()`` reflects the failure.
        """
        try:
            await self.refresh(meta.model_name)
        except Exception as exc:
            meta.last_error = str(exc)
            meta.status = "error"
            logger.error(
                "Derived model '%s' on_source_change refresh failed: %s",
                meta.model_name,
                exc,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_next_fire(self, meta: DerivedModelMeta) -> Optional[datetime]:
        """Compute the next fire time for a scheduled derived model."""
        if meta.schedule is None:
            return None

        now = datetime.now(timezone.utc)

        # Try fixed interval first
        interval_secs = _parse_interval(meta.schedule)
        if interval_secs is not None:
            return now + timedelta(seconds=interval_secs)

        # Try cron expression
        next_cron = _next_cron_fire(meta.schedule, now)
        if next_cron is not None:
            return next_cron

        logger.warning(
            "Cannot parse schedule '%s' for derived model '%s'. "
            "Install 'croniter' for cron support or use 'every Nh/Nm/Ns' format.",
            meta.schedule,
            meta.model_name,
        )
        return None


# ---------------------------------------------------------------------------
# DerivedModelRefreshScheduler
# ---------------------------------------------------------------------------


class DerivedModelRefreshScheduler:
    """Background scheduler that fires refresh for scheduled derived models.

    Creates one ``asyncio.Task`` per scheduled derived model. Each task
    sleeps until the model's ``next_scheduled`` time, refreshes, then
    re-schedules.
    """

    def __init__(self, engine: DerivedModelEngine) -> None:
        self._engine = engine
        self._tasks: Dict[str, asyncio.Task[None]] = {}
        self._running = False

    async def start(self) -> None:
        """Start background tasks for all scheduled derived models."""
        self._running = True
        for name, meta in self._engine._models.items():
            if meta.refresh == "scheduled":
                task = asyncio.create_task(
                    self._schedule_loop(meta), name=f"derived-refresh-{name}"
                )
                self._tasks[name] = task
        logger.info(
            "DerivedModelRefreshScheduler started with %d scheduled model(s).",
            len(self._tasks),
        )

    async def stop(self) -> None:
        """Cancel all background tasks."""
        self._running = False
        for name, task in self._tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        logger.info("DerivedModelRefreshScheduler stopped.")

    async def _schedule_loop(self, meta: DerivedModelMeta) -> None:
        """Per-model loop: sleep until next scheduled time, refresh, repeat."""
        while self._running:
            try:
                sleep_secs = self._seconds_until_next(meta)
                if sleep_secs is None:
                    logger.warning(
                        "No next_scheduled for derived model '%s' -- stopping loop.",
                        meta.model_name,
                    )
                    break

                if sleep_secs > 0:
                    await asyncio.sleep(sleep_secs)

                if not self._running:
                    break

                logger.info(
                    "Scheduled refresh firing for derived model '%s'.",
                    meta.model_name,
                )
                await self._engine.refresh(meta.model_name)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(
                    "Scheduler loop error for derived model '%s': %s",
                    meta.model_name,
                    exc,
                )
                # Back off on error to avoid tight loop
                await asyncio.sleep(5.0)

    @staticmethod
    def _seconds_until_next(meta: DerivedModelMeta) -> Optional[float]:
        """Compute seconds to sleep until the next scheduled refresh."""
        if meta.next_scheduled is None:
            return None
        now = datetime.now(timezone.utc)
        delta = (meta.next_scheduled - now).total_seconds()
        return max(0.0, delta)
