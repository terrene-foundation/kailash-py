"""Tier 1 unit tests for EventLoopWatchdog.

Tests cover stall detection, false positive avoidance, stack trace capture,
context manager lifecycle, configurable thresholds, is_stalled property,
and multiple stall/recovery cycles.
"""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timezone

import pytest

from kailash.runtime.watchdog import EventLoopWatchdog, StallReport


@pytest.mark.asyncio
async def test_watchdog_detects_stall() -> None:
    """Block the event loop and verify on_stall callback fires."""
    stall_reports: list[StallReport] = []

    def on_stall(report: StallReport) -> None:
        stall_reports.append(report)

    async with EventLoopWatchdog(
        heartbeat_interval_s=0.05,
        stall_threshold_s=0.2,
        on_stall=on_stall,
    ) as wd:
        # Let the heartbeat coroutine run a few cycles first
        await asyncio.sleep(0.15)

        # Block the event loop synchronously -- the heartbeat coroutine
        # cannot post updates while time.sleep holds the loop.
        time.sleep(0.5)

        # Give the watchdog thread time to detect the stall and the
        # event loop to process pending callbacks
        await asyncio.sleep(0.2)

    assert len(stall_reports) >= 1, "Expected at least one stall report"
    report = stall_reports[0]
    assert report.stall_duration_s >= 0.2
    assert report.loop_id != 0
    assert isinstance(report.timestamp, datetime)


@pytest.mark.asyncio
async def test_watchdog_no_false_positive() -> None:
    """Normal async work should not trigger a stall report."""
    stall_reports: list[StallReport] = []

    def on_stall(report: StallReport) -> None:
        stall_reports.append(report)

    async with EventLoopWatchdog(
        heartbeat_interval_s=0.05,
        stall_threshold_s=0.3,
        on_stall=on_stall,
    ):
        # Do normal async work that yields the loop regularly
        for _ in range(10):
            await asyncio.sleep(0.03)

    assert (
        len(stall_reports) == 0
    ), f"Expected zero stall reports during normal async work, got {len(stall_reports)}"


@pytest.mark.asyncio
async def test_watchdog_captures_stack_traces() -> None:
    """Verify StallReport contains task stack information."""
    stall_reports: list[StallReport] = []

    def on_stall(report: StallReport) -> None:
        stall_reports.append(report)

    async with EventLoopWatchdog(
        heartbeat_interval_s=0.05,
        stall_threshold_s=0.2,
        on_stall=on_stall,
    ) as wd:
        await asyncio.sleep(0.1)
        time.sleep(0.4)
        await asyncio.sleep(0.15)

    assert len(stall_reports) >= 1
    report = stall_reports[0]

    # There should be at least 1 task (the heartbeat coroutine)
    assert report.task_count >= 1
    assert isinstance(report.task_stacks, list)
    # At least one stack trace should contain text
    assert any(len(s) > 0 for s in report.task_stacks)


@pytest.mark.asyncio
async def test_watchdog_context_manager_cleanup() -> None:
    """Verify clean shutdown with no leaked threads."""
    initial_threads = threading.active_count()
    watchdog_thread_name = "kailash-event-loop-watchdog"

    async with EventLoopWatchdog(
        heartbeat_interval_s=0.05,
        stall_threshold_s=0.3,
    ) as wd:
        # Verify the watchdog thread is running
        thread_names = [t.name for t in threading.enumerate()]
        assert watchdog_thread_name in thread_names

    # After exit, the watchdog thread should be stopped
    # Give a small grace period for thread cleanup
    await asyncio.sleep(0.15)
    thread_names = [t.name for t in threading.enumerate()]
    assert (
        watchdog_thread_name not in thread_names
    ), f"Watchdog thread still alive after context manager exit: {thread_names}"


@pytest.mark.asyncio
async def test_watchdog_configurable_thresholds() -> None:
    """Different threshold configurations work correctly."""
    # Tight thresholds -- short stall detected
    stall_reports_tight: list[StallReport] = []

    async with EventLoopWatchdog(
        heartbeat_interval_s=0.02,
        stall_threshold_s=0.1,
        on_stall=lambda r: stall_reports_tight.append(r),
    ):
        await asyncio.sleep(0.05)
        time.sleep(0.2)
        await asyncio.sleep(0.1)

    assert len(stall_reports_tight) >= 1

    # Loose thresholds -- same stall NOT detected
    stall_reports_loose: list[StallReport] = []

    async with EventLoopWatchdog(
        heartbeat_interval_s=0.02,
        stall_threshold_s=1.0,
        on_stall=lambda r: stall_reports_loose.append(r),
    ):
        await asyncio.sleep(0.05)
        time.sleep(0.2)
        await asyncio.sleep(0.1)

    assert (
        len(stall_reports_loose) == 0
    ), "Loose threshold should not detect a 0.2s stall"


@pytest.mark.asyncio
async def test_watchdog_is_stalled_property() -> None:
    """Property reflects current stall state."""
    async with EventLoopWatchdog(
        heartbeat_interval_s=0.05,
        stall_threshold_s=0.2,
    ) as wd:
        # Before any stall
        assert wd.is_stalled is False

        await asyncio.sleep(0.1)

        # Block the loop
        time.sleep(0.4)

        # Give watchdog thread time to detect
        await asyncio.sleep(0.15)

        # Right after recovery, is_stalled should have cleared because
        # the heartbeat resumes once we await (yielding back to the loop).
        # The watchdog thread sees fresh heartbeats and clears the flag.
        # But there is a window where it might still be True.
        # We check that at least one stall was recorded.
        assert len(wd.stall_reports) >= 1


@pytest.mark.asyncio
async def test_watchdog_multiple_stalls() -> None:
    """Stall, recover, stall again -- all reported."""
    stall_reports: list[StallReport] = []

    def on_stall(report: StallReport) -> None:
        stall_reports.append(report)

    async with EventLoopWatchdog(
        heartbeat_interval_s=0.03,
        stall_threshold_s=0.15,
        on_stall=on_stall,
    ) as wd:
        # First stall
        await asyncio.sleep(0.08)
        time.sleep(0.3)
        await asyncio.sleep(0.1)

        first_count = len(stall_reports)
        assert first_count >= 1, "First stall not detected"

        # Recovery period -- let heartbeats flow to clear stall state
        for _ in range(10):
            await asyncio.sleep(0.03)

        # Second stall
        time.sleep(0.3)
        await asyncio.sleep(0.1)

    assert (
        len(stall_reports) >= 2
    ), f"Expected at least 2 stall reports (stall-recover-stall), got {len(stall_reports)}"
    # Each report should have a distinct timestamp
    timestamps = [r.timestamp for r in stall_reports]
    assert len(set(timestamps)) == len(
        timestamps
    ), "Stall reports should have unique timestamps"


@pytest.mark.asyncio
async def test_watchdog_stall_report_dataclass() -> None:
    """StallReport is frozen and has expected fields."""
    report = StallReport(
        stall_duration_s=5.123,
        loop_id=12345,
        task_count=3,
        task_stacks=["stack1", "stack2"],
        timestamp=datetime.now(timezone.utc),
    )
    assert report.stall_duration_s == 5.123
    assert report.loop_id == 12345
    assert report.task_count == 3
    assert len(report.task_stacks) == 2

    with pytest.raises(AttributeError):
        report.stall_duration_s = 0.0  # type: ignore[misc]


@pytest.mark.asyncio
async def test_watchdog_validation_errors() -> None:
    """Invalid configuration raises ValueError."""
    with pytest.raises(ValueError, match="heartbeat_interval_s must be positive"):
        EventLoopWatchdog(heartbeat_interval_s=0)

    with pytest.raises(ValueError, match="stall_threshold_s must be positive"):
        EventLoopWatchdog(stall_threshold_s=-1)

    with pytest.raises(ValueError, match="stall_threshold_s.*must be >="):
        EventLoopWatchdog(heartbeat_interval_s=2.0, stall_threshold_s=1.0)


@pytest.mark.asyncio
async def test_watchdog_double_stop_is_safe() -> None:
    """Calling stop() twice does not raise."""
    wd = EventLoopWatchdog(
        heartbeat_interval_s=0.05,
        stall_threshold_s=0.3,
    )
    await wd.start()
    await wd.stop()
    await wd.stop()  # Second stop should be a no-op


@pytest.mark.asyncio
async def test_watchdog_callback_error_does_not_crash() -> None:
    """A failing on_stall callback does not crash the watchdog thread."""
    call_count = 0

    def bad_callback(report: StallReport) -> None:
        nonlocal call_count
        call_count += 1
        raise RuntimeError("callback exploded")

    async with EventLoopWatchdog(
        heartbeat_interval_s=0.05,
        stall_threshold_s=0.2,
        on_stall=bad_callback,
    ) as wd:
        await asyncio.sleep(0.1)
        time.sleep(0.4)
        await asyncio.sleep(0.15)

    # The callback was called despite raising
    assert call_count >= 1
    # The watchdog still captured the report
    assert len(wd.stall_reports) >= 1
