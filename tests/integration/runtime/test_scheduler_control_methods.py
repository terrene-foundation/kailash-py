# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 wiring tests for ``WorkflowScheduler`` admin control methods (#913).

Covers ``pause`` / ``resume`` / ``update_cron`` end-to-end against a real
APScheduler ``AsyncIOScheduler`` with an in-memory job store. Per
``rules/testing.md`` Tier 2: NO mocking of the scheduler; assertions
observe externally-visible behaviour (fire counts, ``next_run_time``
deltas, raised exceptions). Per ``rules/orphan-detection.md`` Rule 2,
the new methods are wired into the framework's hot path
(``self._scheduler.pause_job`` / ``resume_job`` / ``reschedule_job``)
and Tier 2 MUST observe the externally-visible effect.

Skips if APScheduler is not installed.
"""

from __future__ import annotations

import asyncio

import pytest

apscheduler = pytest.importorskip(
    "apscheduler", reason="WorkflowScheduler requires APScheduler"
)


def _counter_workflow(counter_path: str):
    """Build a WorkflowBuilder whose every fire increments a tempfile counter.

    The counter file is the test's state surface; deterministic — no
    randomness, no clocks, no network. Reading the file at any point
    gives an exact fire count for assertions.
    """
    from kailash.workflow.builder import WorkflowBuilder

    code = (
        f"import os\n"
        f"_p = {counter_path!r}\n"
        f"_n = 0\n"
        f"if os.path.exists(_p):\n"
        f"    with open(_p) as _f:\n"
        f"        _n = int(_f.read().strip() or '0')\n"
        f"_n += 1\n"
        f"with open(_p, 'w') as _f:\n"
        f"    _f.write(str(_n))\n"
        f"result = {{'attempts': _n}}\n"
    )
    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "start", {"code": code})
    return builder


def _read_counter(counter_path: str) -> int:
    import os

    if not os.path.exists(counter_path):
        return 0
    with open(counter_path) as f:
        return int(f.read().strip() or "0")


async def _wait_until(predicate, *, timeout: float, poll: float = 0.05) -> bool:
    """Poll ``predicate`` until True or ``timeout`` expires.

    Bounded-timeout helper so tests never hang on a stuck scheduler.
    Returns True if the predicate became True before the timeout, False
    otherwise — caller asserts on the returned bool plus follow-up state.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(poll)
    return predicate()


@pytest.mark.integration
@pytest.mark.asyncio
class TestSchedulerControlMethods:
    """End-to-end tests for pause / resume / update_cron."""

    # ------------------------------------------------------------------
    # pause / resume — observable behaviour against a running scheduler
    # ------------------------------------------------------------------

    async def test_pause_skips_fires_resume_restarts(self, tmp_path):
        """Pause halts all fires; resume restarts cadence from now-forward."""
        from kailash.runtime.scheduler import WorkflowScheduler

        counter = str(tmp_path / "pause_resume.cnt")

        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()
        try:
            schedule_id = scheduler.schedule_interval(
                _counter_workflow(counter),
                seconds=0.5,
                name="pause-resume",
            )

            # Allow at least one fire so we have a non-zero baseline before pause.
            assert await _wait_until(
                lambda: _read_counter(counter) >= 1, timeout=3.0
            ), f"baseline fire never happened (counter={_read_counter(counter)})"
            baseline = _read_counter(counter)

            # Pause and observe: counter MUST NOT advance for ≥ 2× the cron interval
            # (1.0s for a 0.5s interval). We sample at the end so a single early
            # fire scheduled before pause cannot mask the assertion.
            scheduler.pause(schedule_id)
            await asyncio.sleep(1.2)
            after_pause = _read_counter(counter)
            assert after_pause == baseline, (
                f"pause did not halt fires: baseline={baseline}, "
                f"after_pause={after_pause} (interval=0.5s, slept 1.2s)"
            )

            # Resume; observable effect: at least one new fire within 2× interval.
            scheduler.resume(schedule_id)
            assert await _wait_until(
                lambda: _read_counter(counter) > after_pause, timeout=3.0
            ), (
                f"resume did not restart fires: after_pause={after_pause}, "
                f"current={_read_counter(counter)}"
            )

            scheduler.cancel(schedule_id)
        finally:
            scheduler.shutdown(wait=False)

    async def test_resume_recomputes_next_fire_from_now(self, tmp_path):
        """After pause, resume's next_run_time MUST be 'now' forward, not the paused-at instant."""
        from kailash.runtime.scheduler import WorkflowScheduler

        counter = str(tmp_path / "resume_recompute.cnt")

        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()
        try:
            schedule_id = scheduler.schedule_interval(
                _counter_workflow(counter),
                seconds=60,  # long interval so we observe the next_run_time, not fires
                name="resume-recompute",
            )

            # Capture the original next_run_time set at schedule time.
            before_pause = scheduler.list_schedules()
            before_paused_nft = next(
                s.next_run_time for s in before_pause if s.schedule_id == schedule_id
            )
            assert before_paused_nft is not None

            scheduler.pause(schedule_id)
            paused_state = scheduler.list_schedules()
            paused_nft = next(
                s.next_run_time for s in paused_state if s.schedule_id == schedule_id
            )
            assert paused_nft is None, "pause should clear next_run_time"

            # Sleep enough that the recomputed next_run_time MUST be later than
            # the original (which was 60s out from schedule-time).
            await asyncio.sleep(0.5)
            scheduler.resume(schedule_id)

            after_resume = scheduler.list_schedules()
            after_resume_nft = next(
                s.next_run_time for s in after_resume if s.schedule_id == schedule_id
            )
            assert after_resume_nft is not None, "resume should recompute next_run_time"
            # Recomputed time MUST be at or after the original (cadence advanced
            # from "now" forward, NOT from the paused-at instant). On a 60s
            # interval the recomputed time should be approx now+60s.
            assert after_resume_nft >= before_paused_nft, (
                f"resume did not recompute forward: "
                f"original={before_paused_nft} resumed={after_resume_nft}"
            )

            scheduler.cancel(schedule_id)
        finally:
            scheduler.shutdown(wait=False)

    async def test_pause_idempotent(self, tmp_path):
        """pause() twice on an already-paused schedule succeeds with no-op."""
        from kailash.runtime.scheduler import WorkflowScheduler

        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()
        try:
            schedule_id = scheduler.schedule_interval(
                _counter_workflow(str(tmp_path / "idem_pause.cnt")),
                seconds=60,
                name="idem-pause",
            )

            scheduler.pause(schedule_id)  # first
            scheduler.pause(schedule_id)  # second — MUST NOT raise

            state = next(
                s for s in scheduler.list_schedules() if s.schedule_id == schedule_id
            )
            assert state.enabled is False
            assert state.next_run_time is None

            scheduler.cancel(schedule_id)
        finally:
            scheduler.shutdown(wait=False)

    async def test_resume_idempotent(self, tmp_path):
        """resume() twice on a running schedule succeeds with no-op."""
        from kailash.runtime.scheduler import WorkflowScheduler

        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()
        try:
            schedule_id = scheduler.schedule_interval(
                _counter_workflow(str(tmp_path / "idem_resume.cnt")),
                seconds=60,
                name="idem-resume",
            )

            scheduler.resume(schedule_id)  # first — running already, no-op
            scheduler.resume(schedule_id)  # second — still no-op

            state = next(
                s for s in scheduler.list_schedules() if s.schedule_id == schedule_id
            )
            assert state.enabled is True
            assert state.next_run_time is not None

            scheduler.cancel(schedule_id)
        finally:
            scheduler.shutdown(wait=False)

    async def test_pause_unknown_schedule_raises_schedule_not_found(self):
        """pause() on an unknown schedule_id raises ScheduleNotFound."""
        from kailash.runtime.scheduler import WorkflowScheduler
        from kailash.sdk_exceptions import ScheduleNotFound

        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()
        try:
            with pytest.raises(ScheduleNotFound) as excinfo:
                scheduler.pause("sched-does-not-exist")
            assert excinfo.value.schedule_id == "sched-does-not-exist"
        finally:
            scheduler.shutdown(wait=False)

    async def test_resume_unknown_schedule_raises_schedule_not_found(self):
        """resume() on an unknown schedule_id raises ScheduleNotFound."""
        from kailash.runtime.scheduler import WorkflowScheduler
        from kailash.sdk_exceptions import ScheduleNotFound

        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()
        try:
            with pytest.raises(ScheduleNotFound) as excinfo:
                scheduler.resume("sched-also-missing")
            assert excinfo.value.schedule_id == "sched-also-missing"
        finally:
            scheduler.shutdown(wait=False)

    # ------------------------------------------------------------------
    # update_cron — replace trigger and recompute next-fire
    # ------------------------------------------------------------------

    async def test_update_cron_replaces_trigger(self, tmp_path):
        """update_cron swaps the trigger; subsequent fires use the new cron."""
        from kailash.runtime.scheduler import WorkflowScheduler

        counter = str(tmp_path / "update_cron.cnt")

        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()
        try:
            # Original cron: only fires once a year (deliberately rare so the
            # only fires we observe come from the post-update trigger).
            schedule_id = scheduler.schedule_cron(
                _counter_workflow(counter),
                "0 0 1 1 *",  # midnight Jan 1
                name="update-cron",
            )

            # No fires yet — the original cron's next instant is months/years out.
            assert _read_counter(counter) == 0

            # Update to "every minute" — APScheduler's CronTrigger will compute
            # the next fire to within ≤60s. We observe trigger_args change AND
            # the next_run_time advance to a much sooner instant.
            #
            # NOTE: list_schedules() returns the SAME ScheduleInfo objects it
            # caches — so we snapshot the field BEFORE updating, otherwise
            # the same object's `next_run_time` mutates underfoot.
            before_info = next(
                s for s in scheduler.list_schedules() if s.schedule_id == schedule_id
            )
            before_nft = before_info.next_run_time
            before_args = dict(before_info.trigger_args)
            assert before_args == {"cron_expression": "0 0 1 1 *"}

            scheduler.update_cron(schedule_id, "* * * * *")
            after_info = next(
                s for s in scheduler.list_schedules() if s.schedule_id == schedule_id
            )

            assert after_info.trigger_args == {
                "cron_expression": "* * * * *"
            }, f"trigger_args not updated: {after_info.trigger_args}"
            assert after_info.next_run_time is not None
            assert after_info.next_run_time < before_nft, (
                f"new cron did not bring next_run_time forward: "
                f"old={before_nft}, new={after_info.next_run_time}"
            )

            scheduler.cancel(schedule_id)
        finally:
            scheduler.shutdown(wait=False)

    async def test_update_cron_unknown_schedule_raises_schedule_not_found(self):
        """update_cron() on an unknown schedule_id raises ScheduleNotFound."""
        from kailash.runtime.scheduler import WorkflowScheduler
        from kailash.sdk_exceptions import ScheduleNotFound

        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()
        try:
            with pytest.raises(ScheduleNotFound) as excinfo:
                scheduler.update_cron("sched-missing", "0 0 * * *")
            assert excinfo.value.schedule_id == "sched-missing"
        finally:
            scheduler.shutdown(wait=False)

    async def test_update_cron_invalid_expr_raises_value_error(self, tmp_path):
        """update_cron() rejects malformed cron with ValueError('invalid cron')."""
        from kailash.runtime.scheduler import WorkflowScheduler

        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()
        try:
            schedule_id = scheduler.schedule_cron(
                _counter_workflow(str(tmp_path / "bad_cron.cnt")),
                "0 0 * * *",
                name="bad-cron",
            )

            # Wrong field count: 4 fields rather than 5.
            with pytest.raises(ValueError, match="invalid cron"):
                scheduler.update_cron(schedule_id, "0 0 * *")

            # Wrong field syntax: APScheduler's CronTrigger rejects "99" hour.
            with pytest.raises(ValueError, match="invalid cron"):
                scheduler.update_cron(schedule_id, "0 99 * * *")

            # Original schedule still intact after failed updates.
            state = next(
                s for s in scheduler.list_schedules() if s.schedule_id == schedule_id
            )
            assert state.trigger_args == {"cron_expression": "0 0 * * *"}, (
                f"failed update_cron should NOT mutate trigger_args: "
                f"{state.trigger_args}"
            )

            scheduler.cancel(schedule_id)
        finally:
            scheduler.shutdown(wait=False)
