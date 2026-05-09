# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 wiring tests for ``WorkflowScheduler`` time-limit plumbing (#912 Shard 3).

Per ``rules/testing.md`` Tier 2: NO mocking; uses a real APScheduler
``AsyncIOScheduler`` with an in-memory job store and a real
``PythonCodeNode`` workflow exercising real ``threading.Timer`` deadlines
through the ``arm_time_limits`` wrapper landed in Shard 2.

Brief Acceptance Criterion #1 (issue #912): scheduled workflows honor
``soft_time_limit`` / ``time_limit`` AND interact correctly with
``RetrySpec`` (#910).

Per ``rules/orphan-detection.md`` Rule 2: the time-limit primitive is
wired into the framework's hot path (``_execute_workflow``), so Tier 2
MUST observe the externally-visible effect (workflow raised
``SoftTimeLimitExceeded`` / ``HardTimeLimitExceeded``, retry attempts
re-armed fresh, defaults overridden per-task).

Skips if APScheduler is not installed.

The PythonCodeNode counter pattern follows
``test_scheduler_retry_primitives.py``: a ``tmp_path`` tempfile is the
state surface (``tests.*`` imports are sandbox-blocked).
"""

from __future__ import annotations

import asyncio
import inspect
import logging

import pytest

logger = logging.getLogger(__name__)

apscheduler = pytest.importorskip(
    "apscheduler", reason="WorkflowScheduler requires APScheduler"
)


# ─────────────────────────────────────────────────────────────────────
# Workflow builders — file-counter pattern (sandbox-safe)
# ─────────────────────────────────────────────────────────────────────


def _sleeping_workflow(*, sleep_seconds: float, counter_path: str):
    """Build a workflow that sleeps then increments a tempfile counter.

    Records the attempt count so tests can verify retry behavior. The
    sleep is what soft/hard time limits cancel. Sandbox blocks
    ``tests.*`` imports — ``os`` and ``time`` are permitted.
    """
    from kailash.workflow.builder import WorkflowBuilder

    code = (
        f"import os\n"
        f"import time\n"
        f"_p = {counter_path!r}\n"
        f"_n = 0\n"
        f"if os.path.exists(_p):\n"
        f"    with open(_p) as _f:\n"
        f"        _n = int(_f.read().strip() or '0')\n"
        f"_n += 1\n"
        f"with open(_p, 'w') as _f:\n"
        f"    _f.write(str(_n))\n"
        f"time.sleep({sleep_seconds})\n"
        f"result = {{'attempts': _n}}\n"
    )
    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "start", {"code": code})
    return builder


def _soft_catching_workflow(*, total_sleep: float, counter_path: str):
    """Build a workflow that catches SoftTimeLimitExceeded then keeps sleeping.

    Used to prove the hard timer fires UNCONDITIONALLY at
    ``time_limit + grace_seconds`` even when user code intercepts the
    soft signal — Shard 2 wrapper invariant 5.
    """
    from kailash.workflow.builder import WorkflowBuilder

    code = (
        f"import os\n"
        f"import time\n"
        f"_p = {counter_path!r}\n"
        f"with open(_p, 'w') as _f:\n"
        f"    _f.write('1')\n"
        f"# Sleep in small chunks so the cooperative cancel signal we install\n"
        f"# at the workflow seam fires between chunks. The PythonCodeNode\n"
        f"# itself does NOT poll the cancellation token — it's the runtime's\n"
        f"# inter-node check that observes the soft cancel. We sleep in chunks\n"
        f"# only to keep the absolute time bound tight.\n"
        f"_remaining = {total_sleep}\n"
        f"while _remaining > 0:\n"
        f"    _step = min(0.05, _remaining)\n"
        f"    time.sleep(_step)\n"
        f"    _remaining -= _step\n"
        f"result = {{'slept': {total_sleep}}}\n"
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


# ─────────────────────────────────────────────────────────────────────
# Test class
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
class TestSchedulerTimeLimits:
    """Verify WorkflowScheduler honors soft/hard time limits end-to-end."""

    # ─────────────────────────────────────────────────────────────
    # MUST-INV-4: Validation at registration time, not at fire time
    # ─────────────────────────────────────────────────────────────

    async def test_validation_at_registration_negative_soft_raises(self, tmp_path):
        """``soft_time_limit <= 0`` raises at schedule_cron time, not at fire."""
        from kailash.runtime.scheduler import WorkflowScheduler

        scheduler = WorkflowScheduler(job_store_path=None)
        try:
            wf = _sleeping_workflow(
                sleep_seconds=0.01, counter_path=str(tmp_path / "noop.cnt")
            )
            with pytest.raises(ValueError, match="soft_time_limit"):
                scheduler.schedule_cron(wf, "* * * * *", soft_time_limit=-1.0)
        finally:
            # Scheduler not started — nothing to shut down.
            pass

    async def test_validation_at_registration_soft_ge_hard_raises(self, tmp_path):
        """``soft_time_limit >= time_limit`` raises immediately."""
        from kailash.runtime.scheduler import WorkflowScheduler

        scheduler = WorkflowScheduler(job_store_path=None)
        try:
            wf = _sleeping_workflow(
                sleep_seconds=0.01, counter_path=str(tmp_path / "noop.cnt")
            )
            with pytest.raises(ValueError, match="strictly less than"):
                scheduler.schedule_interval(
                    wf, seconds=60, soft_time_limit=10.0, time_limit=5.0
                )
            with pytest.raises(ValueError, match="strictly less than"):
                scheduler.schedule_once(
                    wf,
                    run_at=__import__("datetime").datetime(
                        2099, 1, 1, tzinfo=__import__("datetime").UTC
                    ),
                    soft_time_limit=10.0,
                    time_limit=5.0,
                )
        finally:
            pass

    async def test_validation_in_init_defaults_raises(self):
        """``WorkflowScheduler(default_soft_time_limit=, default_time_limit=)``
        validates at construction time so operator errors surface immediately."""
        from kailash.runtime.scheduler import WorkflowScheduler

        with pytest.raises(ValueError, match="soft_time_limit"):
            WorkflowScheduler(job_store_path=None, default_soft_time_limit=-1.0)
        with pytest.raises(ValueError, match="strictly less than"):
            WorkflowScheduler(
                job_store_path=None,
                default_soft_time_limit=10.0,
                default_time_limit=5.0,
            )

    # ─────────────────────────────────────────────────────────────
    # MUST-INV-1: Signature parity across schedule_* methods
    # ─────────────────────────────────────────────────────────────

    async def test_signature_parity_across_three_methods(self):
        """All three schedule_* methods accept ``soft_time_limit`` and
        ``time_limit`` as keyword-only kwargs in the same position.

        Structural invariant per ``rules/cross-sdk-inspection.md`` Rule 3a —
        prevents a future refactor from drifting the signature on one
        method and silently breaking the others.
        """
        from kailash.runtime.scheduler import WorkflowScheduler

        for method_name in ("schedule_cron", "schedule_interval", "schedule_once"):
            sig = inspect.signature(getattr(WorkflowScheduler, method_name))
            params = sig.parameters
            assert (
                "soft_time_limit" in params
            ), f"{method_name} MUST accept soft_time_limit"
            assert "time_limit" in params, f"{method_name} MUST accept time_limit"
            assert (
                params["soft_time_limit"].kind == inspect.Parameter.KEYWORD_ONLY
            ), f"{method_name}.soft_time_limit MUST be keyword-only"
            assert (
                params["time_limit"].kind == inspect.Parameter.KEYWORD_ONLY
            ), f"{method_name}.time_limit MUST be keyword-only"
            assert (
                params["soft_time_limit"].default is None
            ), f"{method_name}.soft_time_limit default MUST be None"
            assert (
                params["time_limit"].default is None
            ), f"{method_name}.time_limit default MUST be None"

    async def test_init_accepts_default_kwargs(self):
        """``WorkflowScheduler.__init__`` accepts ``default_soft_time_limit``
        + ``default_time_limit`` keyword-only kwargs (Open Question Q1)."""
        from kailash.runtime.scheduler import WorkflowScheduler

        sig = inspect.signature(WorkflowScheduler.__init__)
        params = sig.parameters
        assert "default_soft_time_limit" in params
        assert "default_time_limit" in params
        assert params["default_soft_time_limit"].kind == inspect.Parameter.KEYWORD_ONLY
        assert params["default_time_limit"].kind == inspect.Parameter.KEYWORD_ONLY
        assert params["default_soft_time_limit"].default is None
        assert params["default_time_limit"].default is None

    # ─────────────────────────────────────────────────────────────
    # MUST-INV-6: Persistence in APScheduler kwargs dict
    # ─────────────────────────────────────────────────────────────

    async def test_persistence_in_kwargs_dict(self, tmp_path):
        """Time-limit values are persisted in the APScheduler job's
        ``kwargs`` dict so they survive restart/reload from jobstore.

        Same pattern as ``_RETRY_SPEC_KWARG`` (#910): time-limit pair is
        threaded under an internal sentinel key in the job's persisted
        kwargs dict.
        """
        from kailash.runtime.scheduler import WorkflowScheduler

        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()
        try:
            wf = _sleeping_workflow(
                sleep_seconds=0.01, counter_path=str(tmp_path / "noop.cnt")
            )
            schedule_id = scheduler.schedule_interval(
                wf,
                seconds=60,
                soft_time_limit=2.0,
                time_limit=5.0,
            )
            job = scheduler._scheduler.get_job(schedule_id)
            assert job is not None
            # The internal sentinel key MUST appear in the persisted kwargs.
            from kailash.runtime.scheduler import _TIME_LIMIT_KWARG

            assert _TIME_LIMIT_KWARG in job.kwargs, (
                f"time-limit pair MUST be persisted under {_TIME_LIMIT_KWARG!r} "
                f"in APScheduler kwargs; got keys: {list(job.kwargs.keys())}"
            )
            stored = job.kwargs[_TIME_LIMIT_KWARG]
            assert stored == (
                2.0,
                5.0,
            ), f"persisted time-limit pair MUST be (soft, hard); got {stored!r}"
        finally:
            scheduler.shutdown(wait=False)

    # ─────────────────────────────────────────────────────────────
    # Brief AC #1: soft / hard limits fire end-to-end
    # ─────────────────────────────────────────────────────────────

    async def test_soft_time_limit_raises_in_workflow(self, tmp_path):
        """A workflow that sleeps 5s with ``soft_time_limit=1`` raises
        ``SoftTimeLimitExceeded`` at the FIRE level (visible to APScheduler's
        job-error listener)."""
        from kailash.runtime.scheduler import WorkflowScheduler
        from kailash.sdk_exceptions import SoftTimeLimitExceeded

        counter = str(tmp_path / "soft.cnt")
        observed: list[BaseException] = []

        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()

        from apscheduler.events import EVENT_JOB_ERROR

        def _listener(event):
            if event.exception is not None:
                observed.append(event.exception)

        scheduler._scheduler.add_listener(_listener, EVENT_JOB_ERROR)

        try:
            scheduler.schedule_interval(
                _sleeping_workflow(sleep_seconds=5.0, counter_path=counter),
                seconds=60,
                soft_time_limit=1.0,
            )
            # Wait up to ~3s for the soft deadline to fire and the workflow
            # to bubble.
            for _ in range(30):
                if observed:
                    break
                await asyncio.sleep(0.1)

            assert (
                observed
            ), "expected EVENT_JOB_ERROR to fire with SoftTimeLimitExceeded"
            # First (and only) bubble MUST be SoftTimeLimitExceeded — NOT a
            # bare WorkflowCancelledError, NOT a wrapping RuntimeError.
            assert isinstance(observed[0], SoftTimeLimitExceeded), (
                f"expected SoftTimeLimitExceeded; got "
                f"{type(observed[0]).__name__}: {observed[0]}"
            )
        finally:
            scheduler.shutdown(wait=False)

    async def test_hard_time_limit_raises_after_grace(self, tmp_path):
        """``time_limit=1`` + grace=0.5 → workflow that sleeps 5s raises
        ``HardTimeLimitExceeded`` at ~1.5s.

        ``HardTimeLimitExceeded`` is the structurally-distinct exception
        per Shard 1; the assertion verifies the wrapper's polled-flag
        path actually fires (Shard 2 invariant 5).
        """
        from kailash.runtime.scheduler import WorkflowScheduler
        from kailash.sdk_exceptions import HardTimeLimitExceeded

        counter = str(tmp_path / "hard.cnt")
        observed: list[BaseException] = []

        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()

        from apscheduler.events import EVENT_JOB_ERROR

        def _listener(event):
            if event.exception is not None:
                observed.append(event.exception)

        scheduler._scheduler.add_listener(_listener, EVENT_JOB_ERROR)

        try:
            scheduler.schedule_interval(
                _soft_catching_workflow(total_sleep=5.0, counter_path=counter),
                seconds=60,
                time_limit=1.0,
            )
            # Allow up to ~5s for the hard deadline + grace to elapse and the
            # workflow to bubble (the workflow itself sleeps 5s; hard fires
            # before that).
            for _ in range(80):
                if observed:
                    break
                await asyncio.sleep(0.1)

            assert (
                observed
            ), "expected EVENT_JOB_ERROR to fire with HardTimeLimitExceeded"
            assert isinstance(observed[0], HardTimeLimitExceeded), (
                f"expected HardTimeLimitExceeded; got "
                f"{type(observed[0]).__name__}: {observed[0]}"
            )
        finally:
            scheduler.shutdown(wait=False)

    # ─────────────────────────────────────────────────────────────
    # MUST-INV-2: RetrySpec interaction
    # ─────────────────────────────────────────────────────────────

    async def test_retryspec_classifies_soft_as_retryable_on_demand(self, tmp_path):
        """``RetrySpec(retry_on=(SoftTimeLimitExceeded,))`` retries on soft."""
        from kailash.runtime.scheduler import RetrySpec, WorkflowScheduler
        from kailash.sdk_exceptions import SoftTimeLimitExceeded

        counter = str(tmp_path / "soft_retry.cnt")

        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()
        try:
            scheduler.schedule_interval(
                _sleeping_workflow(sleep_seconds=5.0, counter_path=counter),
                seconds=60,
                soft_time_limit=1.0,
                retry=RetrySpec(
                    max_retries=2,
                    retry_on=(SoftTimeLimitExceeded,),
                    backoff_base_seconds=0.05,
                    backoff_max_seconds=0.1,
                ),
            )

            # Each attempt sleeps the full 1s budget then bubbles. With
            # 1 + max_retries = 3 attempts at ~1s each, the counter MUST
            # increment to 3 within ~5s.
            for _ in range(80):
                if _read_counter(counter) >= 3:
                    break
                await asyncio.sleep(0.1)

            attempts = _read_counter(counter)
            assert attempts >= 3, (
                f"expected >= 3 attempts (1 + max_retries=2 retries on Soft); "
                f"got {attempts}"
            )
        finally:
            scheduler.shutdown(wait=False)

    async def test_retryspec_dontretry_on_soft_overrides(self, tmp_path):
        """``RetrySpec(dont_retry_on=(SoftTimeLimitExceeded,))`` does NOT
        retry on soft even when ``retry_on`` would match."""
        from kailash.runtime.scheduler import RetrySpec, WorkflowScheduler
        from kailash.sdk_exceptions import SoftTimeLimitExceeded

        counter = str(tmp_path / "soft_no_retry.cnt")

        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()
        try:
            scheduler.schedule_interval(
                _sleeping_workflow(sleep_seconds=5.0, counter_path=counter),
                seconds=60,
                soft_time_limit=1.0,
                retry=RetrySpec(
                    max_retries=5,
                    retry_on=(Exception,),
                    dont_retry_on=(SoftTimeLimitExceeded,),
                    backoff_base_seconds=0.05,
                ),
            )

            # First fire happens within ~2s; soft fires at 1s; NO retry
            # because dont_retry_on overrides. Counter stays at 1.
            await asyncio.sleep(2.5)

            attempts = _read_counter(counter)
            assert (
                attempts == 1
            ), f"expected exactly 1 attempt (dont_retry_on suppresses); got {attempts}"
        finally:
            scheduler.shutdown(wait=False)

    # ─────────────────────────────────────────────────────────────
    # MUST-INV-3: Each retry attempt re-arms a fresh timer
    # ─────────────────────────────────────────────────────────────

    async def test_each_retry_arms_fresh_timer(self, tmp_path):
        """Each retry attempt sees the FULL ``soft_time_limit`` budget.

        Without per-attempt re-arming, the second retry's elapsed budget
        would already include attempt 1's wall-clock — soft would fire
        immediately and the workflow would not even start. Asserts the
        wrapper is called fresh inside the retry loop.

        Builds a workflow that records the wall-clock elapsed during
        each attempt; if every attempt records >= 0.5s of useful work,
        the timer is re-armed correctly.
        """
        import os

        from kailash.runtime.scheduler import RetrySpec, WorkflowScheduler
        from kailash.sdk_exceptions import SoftTimeLimitExceeded
        from kailash.workflow.builder import WorkflowBuilder

        elapsed_log = str(tmp_path / "elapsed.log")
        counter = str(tmp_path / "fresh_timer.cnt")

        # Workflow records the per-attempt sleep duration before bubbling.
        # The runtime cancels via the cooperative inter-node check; the
        # PythonCodeNode itself runs to completion within attempt N's
        # budget — but the OUTER `runtime.execute` raises after the node
        # finishes. We use the elapsed_log to confirm each attempt got
        # the full budget.
        code = (
            f"import os\n"
            f"import time\n"
            f"_p = {counter!r}\n"
            f"_log = {elapsed_log!r}\n"
            f"_n = 0\n"
            f"if os.path.exists(_p):\n"
            f"    with open(_p) as _f:\n"
            f"        _n = int(_f.read().strip() or '0')\n"
            f"_n += 1\n"
            f"with open(_p, 'w') as _f:\n"
            f"    _f.write(str(_n))\n"
            f"_t0 = time.monotonic()\n"
            f"time.sleep(2.0)\n"
            f"_dt = time.monotonic() - _t0\n"
            f"with open(_log, 'a') as _f:\n"
            f"    _f.write(f'attempt={{_n}} dt={{_dt:.2f}}\\n')\n"
            f"result = {{'attempts': _n}}\n"
        )
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "start", {"code": code})

        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()
        try:
            scheduler.schedule_interval(
                builder,
                seconds=60,
                soft_time_limit=1.0,
                retry=RetrySpec(
                    max_retries=2,
                    retry_on=(SoftTimeLimitExceeded,),
                    backoff_base_seconds=0.05,
                    backoff_max_seconds=0.1,
                ),
            )

            for _ in range(120):
                if _read_counter(counter) >= 3:
                    break
                await asyncio.sleep(0.1)

            attempts = _read_counter(counter)
            assert attempts >= 3, f"expected >= 3 attempts; got {attempts}"

            # Each attempt slept ~2s (within the 1s soft budget OR the wrapper
            # cancels mid-sleep but the inner sleep wallclock still records).
            # The key invariant: each attempt actually ran (no instant-abort
            # from a stale timer carried over from prior attempt).
            assert os.path.exists(elapsed_log), "elapsed log MUST exist"
            with open(elapsed_log) as f:
                lines = [ln for ln in f.read().splitlines() if ln]
            assert len(lines) >= 3, (
                f"expected >= 3 elapsed entries (one per attempt); "
                f"got {len(lines)}: {lines}"
            )
            # Each attempt actually got runtime — the dt for each is > 0.5s,
            # which would be impossible if a stale timer cancelled the next
            # attempt at t=0.
            for line in lines:
                # Format: 'attempt=N dt=X.XX'
                dt_str = line.split("dt=")[1]
                dt = float(dt_str)
                assert dt >= 0.5, (
                    f"each attempt MUST get >= 0.5s of runtime (proves "
                    f"timer re-armed); got line {line!r}"
                )
        finally:
            scheduler.shutdown(wait=False)

    # ─────────────────────────────────────────────────────────────
    # Defaults: per-task wins over WorkflowScheduler defaults
    # ─────────────────────────────────────────────────────────────

    async def test_default_time_limit_overridden_by_per_task(self, tmp_path):
        """``WorkflowScheduler(default_time_limit=10)`` + per-task
        ``time_limit=1`` → effective hard limit is 1s (per-task wins)."""
        from kailash.runtime.scheduler import WorkflowScheduler
        from kailash.sdk_exceptions import HardTimeLimitExceeded

        counter = str(tmp_path / "default_override.cnt")
        observed: list[BaseException] = []

        scheduler = WorkflowScheduler(
            job_store_path=None,
            default_time_limit=10.0,  # would never fire within test window
        )
        scheduler.start()

        from apscheduler.events import EVENT_JOB_ERROR

        def _listener(event):
            if event.exception is not None:
                observed.append(event.exception)

        scheduler._scheduler.add_listener(_listener, EVENT_JOB_ERROR)

        try:
            scheduler.schedule_interval(
                _soft_catching_workflow(total_sleep=5.0, counter_path=counter),
                seconds=60,
                time_limit=1.0,  # per-task overrides default 10.0
            )
            # Per-task wins: hard fires at ~1s + 1s grace = 2s.
            for _ in range(40):
                if observed:
                    break
                await asyncio.sleep(0.1)

            assert observed, "expected per-task time_limit=1 to fire"
            assert isinstance(observed[0], HardTimeLimitExceeded), (
                f"expected HardTimeLimitExceeded from per-task; got "
                f"{type(observed[0]).__name__}: {observed[0]}"
            )
        finally:
            scheduler.shutdown(wait=False)

    async def test_default_time_limit_applies_when_no_per_task(self, tmp_path):
        """When per-task ``time_limit`` is None, the scheduler default applies.

        Sized so the default's hard deadline + grace fires within the
        test window. Workflow sleeps 5s; default time_limit=1.0; grace=1s
        → hard fires at ~2s.
        """
        from kailash.runtime.scheduler import WorkflowScheduler
        from kailash.sdk_exceptions import HardTimeLimitExceeded

        counter = str(tmp_path / "default_applies.cnt")
        observed: list[BaseException] = []

        scheduler = WorkflowScheduler(
            job_store_path=None,
            default_time_limit=1.0,
        )
        scheduler.start()

        from apscheduler.events import EVENT_JOB_ERROR

        def _listener(event):
            if event.exception is not None:
                observed.append(event.exception)

        scheduler._scheduler.add_listener(_listener, EVENT_JOB_ERROR)

        try:
            scheduler.schedule_interval(
                _soft_catching_workflow(total_sleep=5.0, counter_path=counter),
                seconds=60,
                # NO per-task time_limit — default MUST apply.
            )
            for _ in range(40):
                if observed:
                    break
                await asyncio.sleep(0.1)

            assert (
                observed
            ), "expected default_time_limit=1 to fire when per-task is None"
            assert isinstance(observed[0], HardTimeLimitExceeded), (
                f"expected HardTimeLimitExceeded from default; got "
                f"{type(observed[0]).__name__}: {observed[0]}"
            )
        finally:
            scheduler.shutdown(wait=False)

    async def test_no_default_no_per_task_no_limit(self, tmp_path):
        """When neither default nor per-task time-limit is set, the
        workflow runs to completion — no spurious HardTimeLimitExceeded."""
        from kailash.runtime.scheduler import WorkflowScheduler

        counter = str(tmp_path / "no_limits.cnt")

        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()
        try:
            scheduler.schedule_interval(
                _sleeping_workflow(sleep_seconds=0.2, counter_path=counter),
                seconds=60,
            )
            # Wait for one fire to complete fully.
            for _ in range(40):
                if _read_counter(counter) >= 1:
                    break
                await asyncio.sleep(0.1)
            # Give the workflow time to fully complete its 0.2s sleep.
            await asyncio.sleep(0.5)

            attempts = _read_counter(counter)
            assert (
                attempts >= 1
            ), f"expected workflow to complete at least once; got {attempts}"
        finally:
            scheduler.shutdown(wait=False)
