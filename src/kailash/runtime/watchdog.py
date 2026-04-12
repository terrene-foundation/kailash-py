"""Event loop watchdog for detecting asyncio stalls.

This module provides EventLoopWatchdog, which monitors an asyncio event loop
for stalls -- situations where the loop stops processing callbacks within a
configurable threshold. This is the primary diagnostic tool for hung workflows
in LocalRuntime, where a blocking node can silently freeze the event loop with
no signal to operators.

The watchdog uses a two-part architecture:
    1. A heartbeat coroutine running inside the event loop that posts
       timestamps at a regular interval.
    2. A watchdog thread running outside the event loop that checks whether
       heartbeats are arriving on time.

When the gap between heartbeats exceeds the stall threshold, the watchdog
captures task stack traces and fires an on_stall callback with a StallReport.

Examples:
    Basic usage with context manager::

        async with EventLoopWatchdog(stall_threshold_s=3.0) as wd:
            await run_long_workflow()
            if wd.is_stalled:
                print("Loop is currently stalled")

    With custom callback::

        def handle_stall(report: StallReport):
            alert_ops_team(report.stall_duration_s, report.task_stacks)

        async with EventLoopWatchdog(on_stall=handle_stall) as wd:
            await run_long_workflow()

Version:
    Added in: v2.9.0
    Closes: #370
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Deque, List, Optional

logger = logging.getLogger(__name__)

__all__ = ["EventLoopWatchdog", "StallReport"]


@dataclass(frozen=True)
class StallReport:
    """Immutable report generated when an event loop stall is detected.

    Contains diagnostic information about the stall including duration,
    loop identity, active task count, and stack traces of all tasks running
    in the stalled loop at detection time.
    """

    stall_duration_s: float
    loop_id: int
    task_count: int
    task_stacks: List[str]
    timestamp: datetime


class EventLoopWatchdog:
    """Monitors an asyncio event loop for stalls.

    Uses a heartbeat coroutine inside the loop and a watchdog thread outside
    the loop to detect when the loop stops processing callbacks. On stall
    detection, captures stack traces and logs a structured warning.

    Thread-safe: the watchdog thread coordinates with the async loop via
    a threading.Event for shutdown and atomic float reads for heartbeat
    timestamps.
    """

    _closed: bool = False

    def __init__(
        self,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        heartbeat_interval_s: float = 1.0,
        stall_threshold_s: float = 5.0,
        on_stall: Optional[Callable[[StallReport], None]] = None,
    ) -> None:
        if heartbeat_interval_s <= 0:
            raise ValueError(
                f"heartbeat_interval_s must be positive, got {heartbeat_interval_s}"
            )
        if stall_threshold_s <= 0:
            raise ValueError(
                f"stall_threshold_s must be positive, got {stall_threshold_s}"
            )
        if stall_threshold_s < heartbeat_interval_s:
            raise ValueError(
                f"stall_threshold_s ({stall_threshold_s}) must be >= "
                f"heartbeat_interval_s ({heartbeat_interval_s})"
            )

        self._loop = loop
        self._heartbeat_interval_s = heartbeat_interval_s
        self._stall_threshold_s = stall_threshold_s
        self._on_stall = on_stall

        # Heartbeat timestamp written by the async coroutine, read by the
        # watchdog thread. Float assignment is atomic on CPython so no lock
        # is needed for reads.
        self._last_heartbeat: float = 0.0
        self._heartbeat_lock = threading.Lock()

        # Shutdown coordination
        self._stop_event = threading.Event()
        self._heartbeat_task: Optional[asyncio.Task[None]] = None
        self._watchdog_thread: Optional[threading.Thread] = None

        # Stall state
        self._is_stalled = False
        self._stall_reports: Deque[StallReport] = deque(maxlen=100)

    @property
    def is_stalled(self) -> bool:
        """Whether the monitored loop is currently considered stalled."""
        return self._is_stalled

    @property
    def stall_reports(self) -> List[StallReport]:
        """List of stall reports captured during this watchdog's lifetime."""
        return list(self._stall_reports)

    async def __aenter__(self) -> EventLoopWatchdog:
        await self.start()
        return self

    async def __aexit__(
        self, exc_type: object, exc_val: object, exc_tb: object
    ) -> None:
        await self.stop()

    async def start(self) -> None:
        """Start the heartbeat coroutine and watchdog thread."""
        if self._loop is None:
            self._loop = asyncio.get_running_loop()

        self._stop_event.clear()
        self._is_stalled = False

        # Record initial heartbeat so the watchdog thread does not
        # immediately fire a false positive before the coroutine runs.
        with self._heartbeat_lock:
            self._last_heartbeat = time.monotonic()

        self._heartbeat_task = self._loop.create_task(self._heartbeat_loop())

        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            name="kailash-event-loop-watchdog",
            daemon=True,
        )
        self._watchdog_thread.start()

        logger.info(
            "watchdog.started",
            extra={
                "loop_id": id(self._loop),
                "heartbeat_interval_s": self._heartbeat_interval_s,
                "stall_threshold_s": self._stall_threshold_s,
            },
        )

    async def stop(self) -> None:
        """Stop the watchdog cleanly, joining the thread and cancelling the task."""
        if self._closed:
            return
        self._closed = True

        self._stop_event.set()

        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        if self._watchdog_thread is not None and self._watchdog_thread.is_alive():
            # The thread checks _stop_event every check_interval, so it will
            # exit promptly. We give it a bounded join.
            self._watchdog_thread.join(timeout=self._heartbeat_interval_s * 2)
            self._watchdog_thread = None

        logger.info(
            "watchdog.stopped",
            extra={"loop_id": id(self._loop) if self._loop else 0},
        )

    async def _heartbeat_loop(self) -> None:
        """Coroutine that posts heartbeat timestamps at regular intervals."""
        while not self._stop_event.is_set():
            with self._heartbeat_lock:
                self._last_heartbeat = time.monotonic()
            try:
                await asyncio.sleep(self._heartbeat_interval_s)
            except asyncio.CancelledError:
                break

    def _watchdog_loop(self) -> None:
        """Thread that checks heartbeat freshness and fires stall reports.

        Runs until _stop_event is set. Checks heartbeat at half the stall
        threshold interval to ensure timely detection.
        """
        check_interval = min(
            self._heartbeat_interval_s,
            self._stall_threshold_s / 2,
        )

        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=check_interval)
            if self._stop_event.is_set():
                break

            with self._heartbeat_lock:
                last_hb = self._last_heartbeat

            now = time.monotonic()
            gap = now - last_hb

            if gap >= self._stall_threshold_s:
                if not self._is_stalled:
                    self._is_stalled = True
                    report = self._capture_stall_report(gap)
                    self._stall_reports.append(report)
                    self._log_stall(report)
                    if self._on_stall is not None:
                        try:
                            self._on_stall(report)
                        except Exception:
                            # Cleanup/hook path: callback failure is logged
                            # but must not crash the watchdog thread.
                            logger.warning(
                                "watchdog.on_stall_callback_error",
                                exc_info=True,
                            )
            else:
                # Heartbeat is fresh -- clear stall state if previously stalled
                if self._is_stalled:
                    self._is_stalled = False
                    logger.info(
                        "watchdog.stall_recovered",
                        extra={
                            "loop_id": id(self._loop) if self._loop else 0,
                            "recovery_gap_s": round(gap, 3),
                        },
                    )

    def _capture_stall_report(self, stall_duration: float) -> StallReport:
        """Build a StallReport with current task stack traces."""
        loop = self._loop
        task_stacks: List[str] = []
        task_count = 0

        if loop is not None:
            try:
                all_tasks = asyncio.all_tasks(loop)
                task_count = len(all_tasks)
                for task in all_tasks:
                    frames = task.get_stack(limit=20)
                    if frames:
                        # Build FrameSummary objects directly to avoid
                        # Python 3.13 StackSummary.extract() unpacking issues.
                        summary = traceback.StackSummary()
                        for f in frames:
                            summary.append(
                                traceback.FrameSummary(
                                    f.f_code.co_filename,
                                    f.f_lineno,
                                    f.f_code.co_name,
                                    lookup_line=False,
                                )
                            )
                        stack_lines = summary.format()
                        task_name = (
                            task.get_name() if hasattr(task, "get_name") else repr(task)
                        )
                        header = f"Task: {task_name}\n"
                        task_stacks.append(header + "".join(stack_lines))
            except RuntimeError:
                # Loop may be closed or in an unexpected state; capture
                # what we can and continue.
                logger.debug("watchdog.task_capture_error", exc_info=True)

        return StallReport(
            stall_duration_s=round(stall_duration, 3),
            loop_id=id(loop) if loop else 0,
            task_count=task_count,
            task_stacks=task_stacks,
            timestamp=datetime.now(timezone.utc),
        )

    def _log_stall(self, report: StallReport) -> None:
        """Emit a structured WARNING log for an event loop stall."""
        stack_summary = "\n---\n".join(report.task_stacks[:5])
        if len(report.task_stacks) > 5:
            stack_summary += f"\n... and {len(report.task_stacks) - 5} more tasks"

        logger.warning(
            "watchdog.stall_detected",
            extra={
                "stall_duration_s": report.stall_duration_s,
                "loop_id": report.loop_id,
                "task_count": report.task_count,
                "timestamp": report.timestamp.isoformat(),
                "task_stacks": stack_summary,
            },
        )

    def __del__(self, _warn_mod=None) -> None:
        """Issue ResourceWarning if the watchdog was not stopped cleanly."""
        if (
            not getattr(self, "_closed", True)
            and getattr(self, "_watchdog_thread", None) is not None
        ):
            import warnings

            _mod = _warn_mod or warnings
            _mod.warn_explicit(
                message=(
                    f"EventLoopWatchdog (loop_id={id(self._loop) if self._loop else 0}) "
                    f"was not stopped before garbage collection. "
                    f"Use 'async with EventLoopWatchdog() as wd: ...' for clean lifecycle."
                ),
                category=ResourceWarning,
                filename=__file__,
                lineno=0,
            )
            # Best-effort cleanup: signal the thread to stop
            self._stop_event.set()
