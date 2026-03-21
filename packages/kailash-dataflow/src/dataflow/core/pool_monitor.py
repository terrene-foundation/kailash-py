# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Pool utilization monitor and connection leak detector.

Provides:
- ``PoolMonitor``: daemon thread that samples pool stats and logs at thresholds
- ``pool_stats()``: public API returning real-time pool utilization
- Leak detection: tracks connection checkout time and logs warnings with
  checkout tracebacks when connections are held too long

Wires up ``MonitoringConfig`` flags:
- ``connection_metrics=True`` enables ``pool_stats()`` collection
- ``alert_on_connection_exhaustion=True`` enables ERROR logs at >= 95%
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
from collections import deque
from typing import Any, Callable, Dict, Optional, Protocol

logger = logging.getLogger(__name__)

__all__ = [
    "PoolMonitor",
    "PoolStatsProvider",
    "pool_stats_dict",
]


class PoolStatsProvider(Protocol):
    """Protocol for pool stat providers across different pool types."""

    def get_pool_stats(self) -> Dict[str, Any]:
        """Return pool stats dict with keys: active, idle, max, overflow, max_overflow."""
        ...


def pool_stats_dict(
    active: int = 0,
    idle: int = 0,
    max_size: int = 0,
    overflow: int = 0,
    max_overflow: int = 0,
) -> Dict[str, Any]:
    """Create a standardized pool stats dictionary."""
    total_capacity = max_size + max_overflow
    utilization = active / total_capacity if total_capacity > 0 else 0.0
    return {
        "active": active,
        "idle": idle,
        "max": max_size,
        "overflow": overflow,
        "max_overflow": max_overflow,
        "utilization": round(utilization, 4),
    }


class _TrackedConnection:
    """Tracks a checked-out connection for leak detection."""

    __slots__ = ("connection_id", "checkout_time", "checkout_traceback")

    def __init__(self, connection_id: int, tb: list):
        self.connection_id = connection_id
        self.checkout_time = time.monotonic()
        self.checkout_traceback = tb


class PoolMonitor:
    """Background daemon thread that monitors pool utilization and detects leaks.

    Args:
        stats_provider: Callable that returns pool stats dict.
        interval_secs: Seconds between monitoring cycles. Default: 10.
        alert_on_exhaustion: Enable ERROR logs at >= 95% utilization.
        leak_detection_enabled: Enable connection leak detection.
        leak_threshold_secs: Seconds before a held connection triggers WARNING.
    """

    def __init__(
        self,
        stats_provider: Callable[[], Dict[str, Any]],
        interval_secs: float = 10.0,
        alert_on_exhaustion: bool = True,
        leak_detection_enabled: bool = True,
        leak_threshold_secs: float = 30.0,
    ):
        self._stats_provider = stats_provider
        if interval_secs <= 0:
            logger.warning(
                "Pool monitor interval_secs=%s clamped to 1.0 (minimum)",
                interval_secs,
            )
            interval_secs = 1.0
        self._interval = interval_secs
        self._alert_on_exhaustion = alert_on_exhaustion
        self._leak_detection_enabled = leak_detection_enabled
        self._leak_threshold = leak_threshold_secs if leak_threshold_secs > 0 else 30.0
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_stats: Dict[str, Any] = pool_stats_dict()

        # Leak detection tracking — bounded per infrastructure-sql.md Rule 7
        self._tracked_connections: Dict[int, _TrackedConnection] = {}
        self._tracked_lock = threading.Lock()
        self._max_tracked = 10_000

    def start(self) -> None:
        """Start the monitoring daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop,
            name="dataflow-pool-monitor",
            daemon=True,
        )
        self._thread.start()
        logger.debug("Pool monitor started (interval=%ss)", self._interval)

    def stop(self) -> None:
        """Stop the monitoring daemon thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.debug("Pool monitor stopped")

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def get_stats(self) -> Dict[str, Any]:
        """Return the last collected pool stats (thread-safe)."""
        return dict(self._last_stats)

    # -- Leak detection callbacks --

    def on_checkout(self, connection_id: int) -> None:
        """Called when a connection is checked out of the pool."""
        if not self._leak_detection_enabled:
            return

        tb = traceback.extract_stack(limit=10)
        tracked = _TrackedConnection(connection_id, tb)

        with self._tracked_lock:
            # Bounded collection — evict oldest if at capacity
            if len(self._tracked_connections) >= self._max_tracked:
                oldest_key = next(iter(self._tracked_connections))
                del self._tracked_connections[oldest_key]
            self._tracked_connections[connection_id] = tracked

    def on_checkin(self, connection_id: int) -> None:
        """Called when a connection is returned to the pool."""
        if not self._leak_detection_enabled:
            return

        with self._tracked_lock:
            self._tracked_connections.pop(connection_id, None)

    # -- Internal --

    def _monitor_loop(self) -> None:
        """Main monitoring loop (runs in daemon thread)."""
        while not self._stop_event.is_set():
            try:
                self._monitor_cycle()
            except Exception:
                logger.debug("Pool monitor cycle error", exc_info=True)

            # At >= 95%, check twice as fast
            utilization = self._last_stats.get("utilization", 0)
            wait = self._interval / 2 if utilization >= 0.95 else self._interval
            self._stop_event.wait(timeout=wait)

    def _monitor_cycle(self) -> None:
        """Single monitoring cycle: collect stats, log thresholds, check leaks."""
        # Collect stats
        try:
            stats = self._stats_provider()
            self._last_stats = stats
        except Exception:
            logger.debug("Failed to collect pool stats", exc_info=True)
            return

        utilization = stats.get("utilization", 0)
        active = stats.get("active", 0)
        idle = stats.get("idle", 0)
        max_size = stats.get("max", 0)
        overflow = stats.get("overflow", 0)
        max_overflow = stats.get("max_overflow", 0)

        # Threshold-based logging
        if utilization >= 0.95 and self._alert_on_exhaustion:
            logger.error(
                "[POOL] utilization=%.0f%% active=%d idle=%d max=%d "
                "overflow=%d max_overflow=%d — EXHAUSTION IMMINENT",
                utilization * 100,
                active,
                idle,
                max_size,
                overflow,
                max_overflow,
            )
        elif utilization >= 0.80:
            logger.warning(
                "[POOL] utilization=%.0f%% active=%d idle=%d max=%d "
                "overflow=%d max_overflow=%d — approaching pool exhaustion",
                utilization * 100,
                active,
                idle,
                max_size,
                overflow,
                max_overflow,
            )
        elif utilization >= 0.70:
            logger.info(
                "[POOL] utilization=%.0f%% active=%d idle=%d max=%d",
                utilization * 100,
                active,
                idle,
                max_size,
            )

        # Leak detection
        if self._leak_detection_enabled:
            self._check_leaks()

    def _check_leaks(self) -> None:
        """Check tracked connections for potential leaks."""
        now = time.monotonic()
        with self._tracked_lock:
            for tracked in list(self._tracked_connections.values()):
                held = now - tracked.checkout_time
                if held > self._leak_threshold * 3:
                    tb_str = self._format_traceback(tracked.checkout_traceback)
                    logger.error(
                        "[POOL] ERROR: Connection held for %.1fs "
                        "(threshold: %.0fs) — PROBABLE LEAK\n"
                        "  Checked out at:\n%s",
                        held,
                        self._leak_threshold,
                        tb_str,
                    )
                elif held > self._leak_threshold:
                    tb_str = self._format_traceback(tracked.checkout_traceback)
                    logger.warning(
                        "[POOL] WARNING: Connection held for %.1fs "
                        "(threshold: %.0fs)\n"
                        "  Checked out at:\n%s",
                        held,
                        self._leak_threshold,
                        tb_str,
                    )

    @staticmethod
    def _format_traceback(tb: list) -> str:
        """Format a traceback extract into readable lines."""
        lines = []
        # Show top 5 user-relevant frames (skip internal/test framework frames)
        for frame in tb[-5:]:
            lines.append(
                f'    File "{frame.filename}", line {frame.lineno}, '
                f"in {frame.name}\n      {frame.line}"
            )
        return "\n".join(lines)
