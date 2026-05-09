# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 wiring tests for ``WorkflowScheduler.on_job_*`` lifecycle hooks (#914).

Per ``rules/testing.md`` Tier 2: NO mocking; uses a real APScheduler
``AsyncIOScheduler`` with an in-memory job store. The success / error paths
fire on real scheduler ticks; the missed path is exercised by invoking
``_on_job_lifecycle_event`` with a constructed APScheduler event object —
this verifies the dispatch routing without manipulating system time.

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


def _build_workflow_builder(*, raises: bool = False):
    """Return a WorkflowBuilder; the scheduler calls .build() at fire time."""
    from kailash.workflow.builder import WorkflowBuilder

    builder = WorkflowBuilder()
    code = "raise ZeroDivisionError('intentional')" if raises else "result = 7"
    builder.add_node("PythonCodeNode", "start", {"code": code})
    return builder


@pytest.mark.integration
@pytest.mark.asyncio
class TestSchedulerLifecycleHooksWiring:
    """Verify WorkflowScheduler dispatches job lifecycle events to handlers."""

    async def test_success_event_fires_handler_with_typed_payload(self):
        """A successful run fires ``on_job_success`` with a JobEvent payload."""
        from kailash.runtime.lifecycle_events import JobEvent
        from kailash.runtime.scheduler import WorkflowScheduler

        scheduler = WorkflowScheduler(job_store_path=None)  # in-memory
        events: list[JobEvent] = []
        errors: list[JobEvent] = []
        scheduler.on_job_success(lambda e: events.append(e))
        scheduler.on_job_error(lambda e: errors.append(e))

        scheduler.start()
        try:
            schedule_id = scheduler.schedule_interval(
                _build_workflow_builder(),
                seconds=1,
                name="hooks-success-schedule",
            )

            # Wait up to ~3s for the first fire.
            for _ in range(30):
                if events:
                    break
                await asyncio.sleep(0.1)

            assert events, "on_job_success MUST fire after the schedule runs"
            assert not errors, f"no error expected; got {errors}"

            evt = events[0]
            assert isinstance(evt, JobEvent)
            assert evt.schedule_id == schedule_id
            assert evt.schedule_name == "hooks-success-schedule"
            assert evt.exception is None

            scheduler.cancel(schedule_id)
        finally:
            scheduler.shutdown(wait=False)

    async def test_error_event_dispatch_via_synthetic_event(self):
        """The error path routes through ``_on_job_lifecycle_event``.

        ``LocalRuntime.execute`` catches node-level failures internally and
        returns a result, so APScheduler reports ``EVENT_JOB_EXECUTED`` for
        a workflow whose nodes raise — only scheduler-internal exceptions
        produce ``EVENT_JOB_ERROR``. Verifying the dispatch routing
        structurally (synthetic event) is the load-bearing assertion; the
        real-APScheduler firing path is covered by the success test above.
        """
        from datetime import UTC, datetime

        from apscheduler.events import EVENT_JOB_ERROR

        from kailash.runtime.lifecycle_events import JobEvent
        from kailash.runtime.scheduler import (
            ScheduleInfo,
            ScheduleType,
            WorkflowScheduler,
        )

        scheduler = WorkflowScheduler(job_store_path=None)
        error_events: list[JobEvent] = []
        scheduler.on_job_error(lambda e: error_events.append(e))

        scheduler._schedules["sched-err"] = ScheduleInfo(
            schedule_id="sched-err",
            schedule_type=ScheduleType.INTERVAL,
            workflow_name="error-test-schedule",
        )

        injected = ZeroDivisionError("intentional")

        class _StubErrorEvent:
            code = EVENT_JOB_ERROR
            job_id = "sched-err"
            scheduled_run_time = datetime.now(UTC)
            exception = injected

        scheduler._on_job_lifecycle_event(_StubErrorEvent())

        assert len(error_events) == 1
        evt = error_events[0]
        assert isinstance(evt, JobEvent)
        assert evt.schedule_id == "sched-err"
        assert evt.schedule_name == "error-test-schedule"
        assert evt.exception is injected

    async def test_missed_event_dispatch_via_synthetic_event(self):
        """The missed-job path routes through `_on_job_lifecycle_event`.

        Avoids time manipulation by feeding a synthetic APScheduler event
        directly. The structural contract — ``EVENT_JOB_MISSED`` produces
        a JobEvent with ``exception=None`` — is the load-bearing assertion.
        """
        from datetime import UTC, datetime

        from apscheduler.events import EVENT_JOB_MISSED

        from kailash.runtime.lifecycle_events import JobEvent
        from kailash.runtime.scheduler import (
            ScheduleInfo,
            ScheduleType,
            WorkflowScheduler,
        )

        scheduler = WorkflowScheduler(job_store_path=None)
        missed_events: list[JobEvent] = []
        scheduler.on_job_missed(lambda e: missed_events.append(e))

        # Pre-populate _schedules so the listener can resolve schedule_name.
        scheduler._schedules["sched-x"] = ScheduleInfo(
            schedule_id="sched-x",
            schedule_type=ScheduleType.INTERVAL,
            workflow_name="missed-test-schedule",
        )

        # Construct a minimal stand-in for APScheduler's JobExecutionEvent.
        # APScheduler reads `code`, `job_id`, and `scheduled_run_time` off the
        # event object; we satisfy that contract structurally.
        class _StubMissedEvent:
            code = EVENT_JOB_MISSED
            job_id = "sched-x"
            scheduled_run_time = datetime.now(UTC)

        scheduler._on_job_lifecycle_event(_StubMissedEvent())

        assert len(missed_events) == 1
        evt = missed_events[0]
        assert isinstance(evt, JobEvent)
        assert evt.schedule_id == "sched-x"
        assert evt.schedule_name == "missed-test-schedule"
        assert evt.exception is None
        assert evt.scheduled_run_time is not None

    async def test_handler_exception_does_not_block_scheduler(self):
        """A raising handler MUST NOT prevent later handlers from running."""
        from datetime import UTC, datetime

        from apscheduler.events import EVENT_JOB_EXECUTED

        from kailash.runtime.lifecycle_events import JobEvent
        from kailash.runtime.scheduler import (
            ScheduleInfo,
            ScheduleType,
            WorkflowScheduler,
        )

        scheduler = WorkflowScheduler(job_store_path=None)
        observed: list[str] = []

        def bad(_e: JobEvent) -> None:
            raise RuntimeError("handler exploded")

        scheduler.on_job_success(bad)  # raises
        scheduler.on_job_success(lambda e: observed.append("after-bad"))

        scheduler._schedules["sched-y"] = ScheduleInfo(
            schedule_id="sched-y",
            schedule_type=ScheduleType.INTERVAL,
            workflow_name="resilient-schedule",
        )

        class _StubSuccessEvent:
            code = EVENT_JOB_EXECUTED
            job_id = "sched-y"
            scheduled_run_time = datetime.now(UTC)

        scheduler._on_job_lifecycle_event(_StubSuccessEvent())

        assert (
            "after-bad" in observed
        ), "later handlers MUST fire even after an earlier handler raised"
