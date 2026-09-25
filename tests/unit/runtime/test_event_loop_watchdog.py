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
from types import SimpleNamespace

import pytest

import kailash.runtime.watchdog as watchdog_module
from kailash.runtime.watchdog import EventLoopWatchdog, StallReport


def _block_until_stall(reported: threading.Event) -> None:
    """Keep the loop blocked until the monitoring thread observes the stall."""
    assert reported.wait(timeout=5.0), "Watchdog did not report the blocked loop"


async def _wait_for_recovery(wd: EventLoopWatchdog) -> None:
    """Yield to heartbeats until the monitoring thread acknowledges recovery."""

    async def recovered() -> None:
        while wd.is_stalled:
            await asyncio.sleep(0.01)

    await asyncio.wait_for(recovered(), timeout=5.0)


@pytest.mark.asyncio
async def test_watchdog_detects_stall() -> None:
    """Block the event loop and verify on_stall callback fires."""
    stall_reports: list[StallReport] = []
    reported = threading.Event()

    def on_stall(report: StallReport) -> None:
        stall_reports.append(report)
        reported.set()

    async with EventLoopWatchdog(
        heartbeat_interval_s=0.05,
        stall_threshold_s=0.2,
        on_stall=on_stall,
    ) as wd:
        _block_until_stall(reported)

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
    reported = threading.Event()

    def on_stall(report: StallReport) -> None:
        stall_reports.append(report)
        reported.set()

    async with EventLoopWatchdog(
        heartbeat_interval_s=0.05,
        stall_threshold_s=0.2,
        on_stall=on_stall,
    ) as wd:
        _block_until_stall(reported)

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
    reported = threading.Event()

    def on_stall(report: StallReport) -> None:
        stall_reports_tight.append(report)
        reported.set()

    async with EventLoopWatchdog(
        heartbeat_interval_s=0.02,
        stall_threshold_s=0.1,
        on_stall=on_stall,
    ):
        _block_until_stall(reported)

    assert len(stall_reports_tight) >= 1
    assert stall_reports_tight[0].stall_duration_s >= 0.1

    # Loose thresholds -- a 0.2s stall is below the threshold
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


@pytest.mark.parametrize("threshold, expected_reports", [(0.1, 1), (1.0, 0)])
def test_watchdog_threshold_decision(
    monkeypatch: pytest.MonkeyPatch, threshold: float, expected_reports: int
) -> None:
    """The same sampled 0.25s gap crosses only the configured tight threshold."""
    wd = EventLoopWatchdog(
        heartbeat_interval_s=0.02,
        stall_threshold_s=threshold,
    )
    wd._last_heartbeat = 10.0
    waits = 0

    def wait_for_one_sample(timeout: float) -> bool:
        nonlocal waits
        waits += 1
        if waits > 1:
            wd._stop_event.set()
        return wd._stop_event.is_set()

    # Exercise the production sampling decision once, with no thread scheduling
    # or wall-clock upper bound. The real-thread tests cover delivery and cleanup.
    with monkeypatch.context() as sample:
        sample.setattr(wd._stop_event, "wait", wait_for_one_sample)
        sample.setattr(
            watchdog_module, "time", SimpleNamespace(monotonic=lambda: 10.25)
        )
        wd._watchdog_loop()

    assert len(wd.stall_reports) == expected_reports
    assert wd.is_stalled is bool(expected_reports)
    if expected_reports:
        assert wd.stall_reports[0].stall_duration_s == 0.25


@pytest.mark.asyncio
async def test_watchdog_is_stalled_property() -> None:
    """Property reflects current stall state."""
    reported = threading.Event()
    async with EventLoopWatchdog(
        heartbeat_interval_s=0.05,
        stall_threshold_s=0.2,
        on_stall=lambda report: reported.set(),
    ) as wd:
        assert wd.is_stalled is False
        _block_until_stall(reported)
        assert wd.is_stalled is True
        assert len(wd.stall_reports) >= 1
        await _wait_for_recovery(wd)
        assert wd.is_stalled is False


@pytest.mark.asyncio
async def test_watchdog_multiple_stalls() -> None:
    """Stall, recover, stall again -- all reported."""
    stall_reports: list[StallReport] = []
    reported = threading.Event()

    def on_stall(report: StallReport) -> None:
        stall_reports.append(report)
        reported.set()

    async with EventLoopWatchdog(
        heartbeat_interval_s=0.03,
        stall_threshold_s=0.15,
        on_stall=on_stall,
    ) as wd:
        # First stall
        _block_until_stall(reported)

        first_count = len(stall_reports)
        assert first_count >= 1, "First stall not detected"

        await _wait_for_recovery(wd)
        assert wd.is_stalled is False
        reported.clear()

        # Second stall
        _block_until_stall(reported)

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
    reported = threading.Event()

    def bad_callback(report: StallReport) -> None:
        nonlocal call_count
        call_count += 1
        reported.set()
        raise RuntimeError("callback exploded")

    async with EventLoopWatchdog(
        heartbeat_interval_s=0.05,
        stall_threshold_s=0.2,
        on_stall=bad_callback,
    ) as wd:
        _block_until_stall(reported)
        await _wait_for_recovery(wd)
        reported.clear()
        _block_until_stall(reported)

    # The callback was called despite raising
    assert call_count >= 1
    # The watchdog still captured the report
    assert len(wd.stall_reports) >= 1

    assert call_count == 2
    assert len(wd.stall_reports) == 2
