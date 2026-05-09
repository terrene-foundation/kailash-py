# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 wiring tests for ``WorkflowScheduler`` retry primitives (#910).

Per ``rules/testing.md`` Tier 2: NO mocking; uses a real APScheduler
``AsyncIOScheduler`` with an in-memory job store and a real
``PythonCodeNode`` workflow. Per ``rules/orphan-detection.md`` Rule 2:
the retry primitive is wired into the framework's hot path
(``_execute_workflow``), so Tier 2 MUST observe the externally-visible
effect (workflow ran N times, WARN log per retry).

Skips if APScheduler is not installed.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

logger = logging.getLogger(__name__)

apscheduler = pytest.importorskip(
    "apscheduler", reason="WorkflowScheduler requires APScheduler"
)


def _attempts_state_workflow(*, fail_first_n: int, counter_path: str):
    """Build a WorkflowBuilder whose attempt count is persisted to ``counter_path``.

    The PythonCodeNode increments a tempfile counter and raises
    ``RuntimeError`` for the first ``fail_first_n`` attempts; after that,
    succeeds. The tempfile is the test's state surface — the sandbox
    permits ``os`` / ``pathlib`` for file IO but blocks ``tests.*`` imports.
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
        f"if _n <= {fail_first_n}:\n"
        f"    raise RuntimeError('attempt %d failure' % _n)\n"
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


@pytest.mark.integration
@pytest.mark.asyncio
class TestSchedulerRetryPrimitives:
    """Verify WorkflowScheduler honors RetrySpec end-to-end."""

    async def test_retry_spec_validation_rejects_invalid_inputs(self):
        """RetrySpec validates max_retries, backoff, base, retry_on types."""
        from kailash.runtime.scheduler import RetrySpec

        with pytest.raises(ValueError, match="max_retries"):
            RetrySpec(max_retries=-1)
        with pytest.raises(ValueError, match="backoff"):
            RetrySpec(max_retries=1, backoff="cubic")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="backoff_base_seconds"):
            RetrySpec(max_retries=1, backoff_base_seconds=0)
        with pytest.raises(ValueError, match="backoff_max_seconds"):
            RetrySpec(max_retries=1, backoff_base_seconds=10, backoff_max_seconds=1)
        with pytest.raises(ValueError, match="retry_on"):
            RetrySpec(max_retries=1, retry_on=(int,))  # type: ignore[arg-type]

    async def test_retryable_classification(self):
        """is_retryable: dont_retry_on wins; non-Exception base classes never retry."""
        from kailash.runtime.scheduler import RetrySpec

        spec = RetrySpec(
            max_retries=2,
            retry_on=(ValueError, KeyError),
            dont_retry_on=(KeyError,),
        )
        assert spec.is_retryable(ValueError("ok"))
        assert not spec.is_retryable(KeyError("denied"))  # dont_retry_on overrides
        assert not spec.is_retryable(TypeError("not in retry_on"))
        assert not spec.is_retryable(KeyboardInterrupt())  # never retry signals

    async def test_backoff_curves(self):
        """Exponential doubles; linear adds; both clamped at max."""
        from kailash.runtime.scheduler import RetrySpec

        exp = RetrySpec(
            max_retries=4,
            backoff="exponential",
            backoff_base_seconds=1.0,
            backoff_max_seconds=10.0,
        )
        assert exp.compute_backoff_seconds(1) == 1.0
        assert exp.compute_backoff_seconds(2) == 2.0
        assert exp.compute_backoff_seconds(3) == 4.0
        assert exp.compute_backoff_seconds(4) == 8.0
        assert exp.compute_backoff_seconds(5) == 10.0  # clamped (would be 16)

        lin = RetrySpec(
            max_retries=4,
            backoff="linear",
            backoff_base_seconds=2.0,
            backoff_max_seconds=100.0,
        )
        assert lin.compute_backoff_seconds(1) == 2.0
        assert lin.compute_backoff_seconds(3) == 6.0

    async def test_workflow_retries_then_succeeds(self, tmp_path):
        """A workflow that fails attempt 1, succeeds attempt 2 — runs twice."""
        from kailash.runtime.scheduler import RetrySpec, WorkflowScheduler

        counter = str(tmp_path / "retry_then_succeed.cnt")

        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()
        try:
            schedule_id = scheduler.schedule_interval(
                _attempts_state_workflow(fail_first_n=1, counter_path=counter),
                seconds=1,
                name="retry-then-succeed",
                retry=RetrySpec(
                    max_retries=2,
                    backoff_base_seconds=0.1,
                    backoff_max_seconds=0.5,
                ),
            )

            # Wait up to 5s for at least 2 attempts (fail + success).
            for _ in range(50):
                if _read_counter(counter) >= 2:
                    break
                await asyncio.sleep(0.1)

            scheduler.cancel(schedule_id)
            attempts = _read_counter(counter)
            assert (
                attempts == 2
            ), f"expected exactly 2 attempts (1 fail + 1 retry-success); got {attempts}"
        finally:
            scheduler.shutdown(wait=False)

    async def test_workflow_exhausts_max_retries(self, tmp_path, caplog):
        """A workflow that always fails uses 1 + max_retries attempts."""
        from kailash.runtime.scheduler import RetrySpec, WorkflowScheduler

        counter = str(tmp_path / "always_fail.cnt")

        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()
        # Set propagation BEFORE start so log records from the in-loop coroutine
        # are seen by pytest's caplog handler. ``at_level(... logger=)`` does
        # not always propagate from sub-loggers in async contexts.
        caplog.set_level(logging.WARNING)
        try:
            schedule_id = scheduler.schedule_interval(
                _attempts_state_workflow(fail_first_n=1_000_000, counter_path=counter),
                seconds=1,
                name="always-fail",
                retry=RetrySpec(
                    max_retries=2,
                    backoff_base_seconds=0.05,
                    backoff_max_seconds=0.2,
                ),
            )

            # Wait for one full fire cycle to exhaust 1 + max_retries = 3 attempts.
            for _ in range(80):
                if _read_counter(counter) >= 3:
                    break
                await asyncio.sleep(0.1)

            scheduler.cancel(schedule_id)

            # All 1+max_retries attempts ran for at least one fire cycle.
            attempts = _read_counter(counter)
            assert (
                attempts >= 3
            ), f"expected at least 3 attempts (1 + max_retries=2); got {attempts}"
            # Per-fire summary WARN fires once when retries are exhausted —
            # per-attempt logs are at DEBUG to avoid log-spam in hot loops
            # (`observability.md` MUST NOT § log-spam-in-hot-loops).
            summary_warns = [
                r
                for r in caplog.records
                if r.levelno == logging.WARNING
                and "exhausted retries" in r.getMessage().lower()
            ]
            assert len(summary_warns) >= 1, (
                f"expected >= 1 'exhausted retries' summary WARN; "
                f"got {len(summary_warns)}: "
                f"{[r.getMessage() for r in summary_warns]}"
            )
        finally:
            scheduler.shutdown(wait=False)

    async def test_dont_retry_on_filter(self, tmp_path):
        """A workflow raising RuntimeError is NOT retried when retry_on=(KeyError,)."""
        from kailash.runtime.scheduler import RetrySpec, WorkflowScheduler

        counter = str(tmp_path / "non_retryable.cnt")

        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()
        try:
            schedule_id = scheduler.schedule_interval(
                # Workflow raises RuntimeError; we filter to KeyError-only.
                _attempts_state_workflow(fail_first_n=10, counter_path=counter),
                seconds=1,
                name="non-retryable-error",
                retry=RetrySpec(
                    max_retries=5,
                    retry_on=(KeyError,),  # excludes RuntimeError
                    backoff_base_seconds=0.05,
                ),
            )

            # First fire happens within 2s; non-retryable failure returns quickly,
            # so attempt count stays at 1 even after a few fires of the same job.
            await asyncio.sleep(2.0)
            scheduler.cancel(schedule_id)

            attempts = _read_counter(counter)
            # Each schedule fire is one attempt because the error is non-retryable.
            # Multiple fires may have happened (interval=1s) but each ONE is single-attempt.
            # Conservatively: ≤ 3 fires possible in 2s (at 0s, 1s, 2s); ≥ 1.
            assert 1 <= attempts <= 3, (
                f"expected 1..3 single-attempt fires in 2s; got {attempts} "
                f"(would be much higher if retry filter were broken)"
            )
        finally:
            scheduler.shutdown(wait=False)

    async def test_reserved_kwarg_collision_raises(self, tmp_path):
        """User MUST NOT supply the internal `_kailash_retry_spec` kwarg name."""
        from kailash.runtime.scheduler import WorkflowScheduler

        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()
        try:
            wf = _attempts_state_workflow(
                fail_first_n=0, counter_path=str(tmp_path / "never.cnt")
            )
            with pytest.raises(ValueError, match="reserved"):
                scheduler.schedule_interval(wf, seconds=60, _kailash_retry_spec="x")
        finally:
            scheduler.shutdown(wait=False)

    async def test_dispatcher_path_rejects_retry_spec(self, tmp_path):
        """retry= MUST raise on a queue-dispatch scheduler (Rule 3c silent-drop)."""
        from kailash.runtime.scheduler import RetrySpec, WorkflowScheduler

        # Construct a stand-in dispatcher (deterministic, satisfies the truthy
        # `dispatch_via=` branch). The error is raised at schedule_* time
        # BEFORE any dispatcher method is called, so any truthy object works.
        sentinel_dispatcher = object()
        scheduler = WorkflowScheduler(
            job_store_path=None,
            dispatch_via=sentinel_dispatcher,  # type: ignore[arg-type]
        )
        try:
            wf = _attempts_state_workflow(
                fail_first_n=0, counter_path=str(tmp_path / "never.cnt")
            )
            for method, args in (
                ("schedule_interval", (wf, 60)),
                ("schedule_cron", (wf, "0 0 * * *")),
            ):
                with pytest.raises(ValueError, match="dispatch_via"):
                    getattr(scheduler, method)(*args, retry=RetrySpec(max_retries=1))
        finally:
            # Don't actually start; sentinel_dispatcher cannot serve fires.
            pass

    async def test_extract_node_failure_deterministic_ordering(self):
        """Multiple failed nodes — _extract_node_failure picks deterministically."""
        from kailash.runtime.scheduler import WorkflowScheduler

        # Out-of-order keys: insertion-order would surface "z_node" first.
        # Sorted-key order surfaces "a_node" first — deterministic across runs.
        results = {
            "z_node": {"failed": True, "error_type": "ValueError", "error": "later"},
            "a_node": {
                "failed": True,
                "error_type": "ConnectionError",
                "error": "earlier",
            },
            "m_node": {"failed": True, "error_type": "KeyError", "error": "middle"},
        }
        exc = WorkflowScheduler._extract_node_failure(results)
        assert exc is not None
        assert isinstance(exc, ConnectionError), (
            f"expected ConnectionError (a_node, sorted-first); got "
            f"{type(exc).__name__}"
        )
        assert "a_node" in str(exc)

    async def test_extract_node_failure_multiarg_ctor_fallback(self):
        """Multi-arg-ctor types fall back to RuntimeError gracefully.

        ``UnicodeDecodeError`` requires 5 args (encoding, object, start, end,
        reason); single-string invocation raises ``TypeError``. The fallback
        MUST yield a ``RuntimeError`` carrying the original type name in the
        message so the original failure surfaces in downstream triage.
        """
        from kailash.runtime.scheduler import WorkflowScheduler

        results = {
            "node_x": {
                "failed": True,
                "error_type": "UnicodeDecodeError",
                "error": "invalid start byte at position 0",
            }
        }
        exc = WorkflowScheduler._extract_node_failure(results)
        assert exc is not None
        assert isinstance(exc, RuntimeError)
        assert "UnicodeDecodeError" in str(exc)
        assert "invalid start byte" in str(exc)

    async def test_linear_backoff_end_to_end(self, tmp_path, caplog):
        """Linear backoff exercises the schedule_*->_execute_workflow path."""
        from kailash.runtime.scheduler import RetrySpec, WorkflowScheduler

        counter = str(tmp_path / "linear.cnt")
        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()
        caplog.set_level(logging.WARNING)
        try:
            schedule_id = scheduler.schedule_interval(
                _attempts_state_workflow(fail_first_n=2, counter_path=counter),
                seconds=1,
                name="linear-backoff",
                retry=RetrySpec(
                    max_retries=2,
                    backoff="linear",
                    backoff_base_seconds=0.05,
                    backoff_max_seconds=1.0,
                ),
            )
            for _ in range(50):
                if _read_counter(counter) >= 3:
                    break
                await asyncio.sleep(0.1)
            scheduler.cancel(schedule_id)
            assert _read_counter(counter) == 3, (
                f"expected exactly 3 attempts (1 fail + 2 retries succeed on the "
                f"3rd); got {_read_counter(counter)}"
            )
        finally:
            scheduler.shutdown(wait=False)

    async def test_dont_retry_on_overrides_retry_on_end_to_end(self, tmp_path):
        """dont_retry_on takes precedence end-to-end (not just unit-level)."""
        from kailash.runtime.scheduler import RetrySpec, WorkflowScheduler

        counter = str(tmp_path / "dont_retry.cnt")
        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()
        try:
            # Workflow raises RuntimeError; retry_on includes it BUT
            # dont_retry_on excludes it. dont_retry_on MUST win → no retry.
            schedule_id = scheduler.schedule_interval(
                _attempts_state_workflow(fail_first_n=10, counter_path=counter),
                seconds=1,
                name="dont-retry-overrides",
                retry=RetrySpec(
                    max_retries=5,
                    retry_on=(Exception,),  # would retry RuntimeError
                    dont_retry_on=(RuntimeError,),  # but this overrides
                    backoff_base_seconds=0.05,
                ),
            )
            await asyncio.sleep(2.0)
            scheduler.cancel(schedule_id)
            attempts = _read_counter(counter)
            # Single-attempt fires only — retry filter blocks the retry path.
            # ≤ 3 fires possible in 2s (at 0s, 1s, 2s).
            assert 1 <= attempts <= 3, (
                f"expected 1..3 single-attempt fires (dont_retry_on overrides "
                f"retry_on); got {attempts}"
            )
        finally:
            scheduler.shutdown(wait=False)

    @pytest.mark.parametrize(
        "method_name",
        ["schedule_cron", "schedule_interval", "schedule_once"],
    )
    async def test_retry_threading_across_all_schedule_methods(
        self, tmp_path, method_name
    ):
        """retry= MUST land on ScheduleInfo for every schedule_* variant."""
        from datetime import UTC, datetime, timedelta

        from kailash.runtime.scheduler import RetrySpec, WorkflowScheduler

        scheduler = WorkflowScheduler(job_store_path=None)
        scheduler.start()
        try:
            spec = RetrySpec(max_retries=4, backoff_base_seconds=0.1)
            wf = _attempts_state_workflow(
                fail_first_n=0, counter_path=str(tmp_path / "never.cnt")
            )
            method = getattr(scheduler, method_name)
            if method_name == "schedule_cron":
                schedule_id = method(wf, "0 0 1 1 *", retry=spec)
            elif method_name == "schedule_interval":
                schedule_id = method(wf, 3600, retry=spec)
            else:  # schedule_once
                schedule_id = method(
                    wf, datetime.now(UTC) + timedelta(hours=1), retry=spec
                )
            info = scheduler._schedules[schedule_id]
            assert info.retry_spec is spec, (
                f"{method_name} did not persist retry_spec on ScheduleInfo "
                f"(structural threading drift)"
            )
        finally:
            scheduler.shutdown(wait=False)


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.asyncio
async def test_issue_910_quickstart_executes_end_to_end(tmp_path):
    """Tier-2 regression: the brief's minimal-repro pipeline runs end-to-end.

    Per ``rules/testing.md`` § "End-to-End Pipeline Regression Above Unit +
    Integration", the canonical brief example MUST have a docstring-exact
    test exercising the public composition. Pure-primitive tests cannot
    catch handoff-shape regressions between :class:`RetrySpec`,
    :meth:`schedule_*`, and :meth:`_execute_workflow`.
    """
    from kailash.runtime.scheduler import RetrySpec, WorkflowScheduler
    from kailash.workflow.builder import WorkflowBuilder

    counter = str(tmp_path / "quickstart.cnt")

    # Brief #910's minimal repro shape, adapted to a 2-attempt success path
    # so the test asserts the user-visible outcome (workflow ran twice
    # before scheduler considered the fire complete).
    code = (
        "import os\n"
        f"_p = {counter!r}\n"
        f"_n = 0\n"
        f"if os.path.exists(_p):\n"
        f"    with open(_p) as _f: _n = int(_f.read().strip() or '0')\n"
        f"_n += 1\n"
        f"with open(_p, 'w') as _f: _f.write(str(_n))\n"
        f"if _n <= 1:\n"
        f"    raise RuntimeError('transient')\n"
        f"result = {{'attempts': _n}}\n"
    )
    wf = WorkflowBuilder()
    wf.add_node("PythonCodeNode", "fail", {"code": code})

    scheduler = WorkflowScheduler(job_store_path=None)
    scheduler.start()
    try:
        # Brief uses cron; we use interval=1s for fast test execution
        # — the threading path through schedule_cron is covered by the
        # parametrized test_retry_threading_across_all_schedule_methods.
        schedule_id = scheduler.schedule_interval(
            wf,
            seconds=1,
            retry=RetrySpec(
                max_retries=3,
                backoff="exponential",
                retry_on=(RuntimeError,),
                backoff_base_seconds=0.1,
                backoff_max_seconds=0.5,
            ),
        )
        for _ in range(50):
            if _read_counter(counter) >= 2:
                break
            await asyncio.sleep(0.1)
        scheduler.cancel(schedule_id)
        attempts = _read_counter(counter)
        # Exactly the brief's promise: workflow ran twice (1 fail + 1 retry-success).
        assert (
            attempts == 2
        ), f"quickstart pipeline failed: expected 2 attempts (1 fail + 1 retry); got {attempts}"
    finally:
        scheduler.shutdown(wait=False)
