"""Tests for PauseController (TODO-022: Workflow Pause/Resume).

Verifies:
- Initial state is not paused
- pause() sets paused state with reason and timestamp
- resume() clears paused state with timestamp
- is_paused property reflects current state
- wait_if_paused() returns immediately when not paused
- wait_if_paused() blocks when paused and unblocks on resume
- Idempotent pause (double-pause keeps original timestamp)
- Idempotent resume (double-resume is no-op)
- pause_count tracks total pauses
- reset() restores initial state
- Thread safety: pause/resume from different thread
"""

import asyncio
import threading
import time

import pytest

from kailash.runtime.pause import PauseController


# ---------------------------------------------------------------------------
# Construction / Initial State
# ---------------------------------------------------------------------------


class TestConstruction:
    """PauseController initialization."""

    def test_initial_state_not_paused(self):
        ctrl = PauseController()
        assert not ctrl.is_paused

    def test_initial_reason_is_none(self):
        ctrl = PauseController()
        assert ctrl.reason is None

    def test_initial_paused_at_is_none(self):
        ctrl = PauseController()
        assert ctrl.paused_at is None

    def test_initial_resumed_at_is_none(self):
        ctrl = PauseController()
        assert ctrl.resumed_at is None

    def test_initial_pause_count_is_zero(self):
        ctrl = PauseController()
        assert ctrl.pause_count == 0


# ---------------------------------------------------------------------------
# Pause
# ---------------------------------------------------------------------------


class TestPause:
    """Pausing behavior."""

    def test_pause_sets_is_paused(self):
        ctrl = PauseController()
        ctrl.pause()
        assert ctrl.is_paused

    def test_pause_sets_reason(self):
        ctrl = PauseController()
        ctrl.pause(reason="maintenance window")
        assert ctrl.reason == "maintenance window"

    def test_pause_default_reason(self):
        ctrl = PauseController()
        ctrl.pause()
        assert ctrl.reason == "Pause requested"

    def test_pause_sets_paused_at(self):
        ctrl = PauseController()
        ctrl.pause()
        assert ctrl.paused_at is not None

    def test_pause_increments_count(self):
        ctrl = PauseController()
        ctrl.pause()
        assert ctrl.pause_count == 1

    def test_double_pause_updates_reason(self):
        ctrl = PauseController()
        ctrl.pause(reason="first")
        original_ts = ctrl.paused_at
        ctrl.pause(reason="second")
        # Reason updated, but timestamp preserved (idempotent)
        assert ctrl.reason == "second"
        assert ctrl.paused_at == original_ts

    def test_double_pause_does_not_increment_count(self):
        ctrl = PauseController()
        ctrl.pause()
        ctrl.pause()
        assert ctrl.pause_count == 1


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------


class TestResume:
    """Resuming behavior."""

    def test_resume_clears_is_paused(self):
        ctrl = PauseController()
        ctrl.pause()
        ctrl.resume()
        assert not ctrl.is_paused

    def test_resume_sets_resumed_at(self):
        ctrl = PauseController()
        ctrl.pause()
        ctrl.resume()
        assert ctrl.resumed_at is not None

    def test_resume_preserves_reason(self):
        """Reason from last pause is preserved after resume for diagnostics."""
        ctrl = PauseController()
        ctrl.pause(reason="check something")
        ctrl.resume()
        assert ctrl.reason == "check something"

    def test_double_resume_is_noop(self):
        ctrl = PauseController()
        ctrl.pause()
        ctrl.resume()
        ts = ctrl.resumed_at
        ctrl.resume()
        # Second resume should not change the timestamp
        assert ctrl.resumed_at == ts

    def test_resume_when_not_paused_is_noop(self):
        ctrl = PauseController()
        ctrl.resume()
        assert not ctrl.is_paused
        assert ctrl.resumed_at is None


# ---------------------------------------------------------------------------
# Pause/Resume Cycle
# ---------------------------------------------------------------------------


class TestPauseResumeCycle:
    """Multiple pause/resume cycles."""

    def test_pause_resume_pause(self):
        ctrl = PauseController()
        ctrl.pause(reason="first")
        ctrl.resume()
        ctrl.pause(reason="second")
        assert ctrl.is_paused
        assert ctrl.reason == "second"
        assert ctrl.pause_count == 2

    def test_multiple_cycles_count(self):
        ctrl = PauseController()
        for i in range(5):
            ctrl.pause(reason=f"cycle {i}")
            ctrl.resume()
        assert ctrl.pause_count == 5
        assert not ctrl.is_paused


# ---------------------------------------------------------------------------
# wait_if_paused (async)
# ---------------------------------------------------------------------------


class TestWaitIfPaused:
    """Async wait_if_paused behavior."""

    @pytest.mark.asyncio
    async def test_returns_immediately_when_not_paused(self):
        ctrl = PauseController()
        # Should complete instantly
        await asyncio.wait_for(ctrl.wait_if_paused(), timeout=1.0)

    @pytest.mark.asyncio
    async def test_blocks_when_paused(self):
        ctrl = PauseController()
        ctrl.pause()

        # Start wait_if_paused - it should block
        task = asyncio.create_task(ctrl.wait_if_paused())
        await asyncio.sleep(0.05)
        assert not task.done()

        # Resume should unblock
        ctrl.resume()
        await asyncio.wait_for(task, timeout=1.0)
        assert task.done()

    @pytest.mark.asyncio
    async def test_blocks_then_unblocks_timing(self):
        ctrl = PauseController()
        ctrl.pause()

        unblocked = asyncio.Event()

        async def waiter():
            await ctrl.wait_if_paused()
            unblocked.set()

        task = asyncio.create_task(waiter())

        # Should still be blocked
        await asyncio.sleep(0.05)
        assert not unblocked.is_set()

        # Resume
        ctrl.resume()
        await asyncio.wait_for(unblocked.wait(), timeout=1.0)
        assert unblocked.is_set()
        await task

    @pytest.mark.asyncio
    async def test_multiple_waiters_all_unblock(self):
        ctrl = PauseController()
        ctrl.pause()

        results = []

        async def waiter(idx: int):
            await ctrl.wait_if_paused()
            results.append(idx)

        tasks = [asyncio.create_task(waiter(i)) for i in range(3)]
        await asyncio.sleep(0.05)
        assert len(results) == 0

        ctrl.resume()
        await asyncio.gather(*tasks)
        assert sorted(results) == [0, 1, 2]


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


class TestReset:
    """Reset behavior."""

    def test_reset_clears_pause(self):
        ctrl = PauseController()
        ctrl.pause()
        ctrl.reset()
        assert not ctrl.is_paused

    def test_reset_clears_all_state(self):
        ctrl = PauseController()
        ctrl.pause(reason="test")
        ctrl.resume()
        ctrl.reset()
        assert ctrl.reason is None
        assert ctrl.paused_at is None
        assert ctrl.resumed_at is None
        assert ctrl.pause_count == 0

    @pytest.mark.asyncio
    async def test_reset_unblocks_waiters(self):
        ctrl = PauseController()
        ctrl.pause()

        task = asyncio.create_task(ctrl.wait_if_paused())
        await asyncio.sleep(0.05)
        assert not task.done()

        ctrl.reset()
        await asyncio.wait_for(task, timeout=1.0)
        assert task.done()


# ---------------------------------------------------------------------------
# Thread Safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    """Cross-thread pause/resume."""

    @pytest.mark.asyncio
    async def test_pause_from_another_thread(self):
        ctrl = PauseController()

        def pause_from_thread():
            time.sleep(0.05)
            ctrl.pause(reason="background thread")

        t = threading.Thread(target=pause_from_thread)
        t.start()
        t.join(timeout=2.0)

        assert ctrl.is_paused
        assert ctrl.reason == "background thread"

    @pytest.mark.asyncio
    async def test_resume_from_another_thread(self):
        ctrl = PauseController()
        ctrl.pause()

        unblocked = asyncio.Event()

        async def waiter():
            await ctrl.wait_if_paused()
            unblocked.set()

        task = asyncio.create_task(waiter())

        def resume_from_thread():
            time.sleep(0.1)
            ctrl.resume()

        t = threading.Thread(target=resume_from_thread)
        t.start()

        await asyncio.wait_for(unblocked.wait(), timeout=2.0)
        assert unblocked.is_set()
        t.join(timeout=2.0)
        await task
