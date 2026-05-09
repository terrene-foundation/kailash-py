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
            # WARN-level retry log fired at least twice (after attempts 1 and 2).
            retry_warns = [
                r
                for r in caplog.records
                if r.levelno == logging.WARNING and "retrying" in r.getMessage().lower()
            ]
            assert len(retry_warns) >= 2, (
                f"expected >= 2 retry WARN logs; got {len(retry_warns)}: "
                f"{[r.getMessage() for r in retry_warns]}"
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
