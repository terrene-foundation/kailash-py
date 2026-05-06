# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for the Dispatcher ABC + WorkflowScheduler dispatch_via=.

Covers per ``rules/testing.md`` § "One Direct Test Per Variant":

* Dispatcher ABC structural contract (4 abstract methods, instantiation refused).
* compute_task_id stability + sensitivity to inputs.
* WorkflowScheduler in-process fallback (dispatch_via=None) preserves behavior.
* WorkflowScheduler queue-dispatch path (dispatch_via=<Protocol-satisfying adapter>).
* Error log on non-PK enqueue failure.

Per ``rules/testing.md`` Tier 1 contract, deterministic Protocol-satisfying
adapters are NOT mocks — they are the canonical Tier-1 substitution for
real infrastructure. The adapter classes here record calls and return
deterministic results without hitting any external service.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, AsyncIterator, List

import pytest

from kailash.runtime.dispatcher import Dispatcher, Task, compute_task_id

# ---------------------------------------------------------------------------
# Dispatcher ABC structural tests
# ---------------------------------------------------------------------------


class TestDispatcherAbcContract:
    """Validate the Dispatcher ABC contract per architecture plan §3."""

    def test_dispatcher_abc_requires_four_methods(self) -> None:
        """Direct subclass missing any of the 4 methods raises at instantiation."""

        # All four methods present -> instantiable.
        class FullDispatcher(Dispatcher):
            async def enqueue(self, task: Task) -> None:
                return None

            def poll(self, queue_name: str = "default") -> AsyncIterator[Task]:
                async def _gen() -> AsyncIterator[Task]:
                    if False:
                        yield  # pragma: no cover

                return _gen()

            async def ack(self, task_id: str) -> None:
                return None

            async def nack(self, task_id: str, *, reason: str) -> None:
                return None

        FullDispatcher()  # MUST NOT raise

        # Drop one method at a time -> TypeError on instantiation.
        for missing in ("enqueue", "poll", "ack", "nack"):
            ns = {
                "enqueue": FullDispatcher.enqueue,
                "poll": FullDispatcher.poll,
                "ack": FullDispatcher.ack,
                "nack": FullDispatcher.nack,
            }
            del ns[missing]
            cls = type(f"Partial_{missing}", (Dispatcher,), ns)
            with pytest.raises(TypeError, match="abstract"):
                cls()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# compute_task_id determinism tests
# ---------------------------------------------------------------------------


class TestComputeTaskId:
    """Validate task_id stability per architecture plan §3 invariant 1."""

    def test_compute_task_id_stable_across_calls(self) -> None:
        """Same (schedule_id, planned_fire_time) -> same task_id."""
        ft = datetime(2026, 5, 6, 12, 0, 0, tzinfo=UTC)
        a = compute_task_id("sched-abc", ft)
        b = compute_task_id("sched-abc", ft)
        assert a == b
        assert len(a) == 32  # 32 hex chars per dispatcher.py contract

    def test_compute_task_id_differs_on_schedule_id(self) -> None:
        ft = datetime(2026, 5, 6, 12, 0, 0, tzinfo=UTC)
        assert compute_task_id("sched-1", ft) != compute_task_id("sched-2", ft)

    def test_compute_task_id_differs_on_fire_time(self) -> None:
        a = compute_task_id("sched-1", datetime(2026, 5, 6, 12, 0, 0, tzinfo=UTC))
        b = compute_task_id("sched-1", datetime(2026, 5, 6, 12, 0, 1, tzinfo=UTC))
        assert a != b


# ---------------------------------------------------------------------------
# Protocol-satisfying deterministic Dispatcher adapter for scheduler tests
# (NOT a mock per `rules/testing.md` § "Protocol Adapters")
# ---------------------------------------------------------------------------


class _RecordingDispatcher(Dispatcher):
    """Records calls + raises configured exceptions deterministically.

    Used to verify scheduler.dispatch_via= wires through to the dispatcher
    contract without spinning up a real database. Per the Protocol Adapters
    exception in ``rules/testing.md``, a class satisfying a Protocol /
    ABC at runtime with deterministic output is NOT a mock — there is no
    `unittest.mock` import, no `MagicMock`, no `@patch`.
    """

    def __init__(self) -> None:
        self.enqueued: List[Task] = []
        self.acked: List[str] = []
        self.nacked: List[tuple[str, str]] = []
        self.enqueue_raises: BaseException | None = None

    async def enqueue(self, task: Task) -> None:
        if self.enqueue_raises is not None:
            raise self.enqueue_raises
        self.enqueued.append(task)

    def poll(self, queue_name: str = "default") -> AsyncIterator[Task]:
        async def _gen() -> AsyncIterator[Task]:
            for t in list(self.enqueued):
                yield t

        return _gen()

    async def ack(self, task_id: str) -> None:
        self.acked.append(task_id)

    async def nack(self, task_id: str, *, reason: str) -> None:
        self.nacked.append((task_id, reason))


# ---------------------------------------------------------------------------
# Minimal builder + workflow shim — Protocol-satisfying deterministic adapters
# ---------------------------------------------------------------------------


class _RecordingWorkflow:
    """A picklable, runtime-executable workflow stand-in."""

    def __init__(self, name: str = "wf") -> None:
        self.name = name


class _RecordingBuilder:
    def __init__(self, name: str = "wf") -> None:
        self.name = name

    def build(self) -> _RecordingWorkflow:
        return _RecordingWorkflow(self.name)


class _RecordingRuntime:
    """A runtime that records execute() calls for in-process fallback testing."""

    def __init__(self) -> None:
        self.calls: List[Any] = []

    def execute(self, workflow: Any, **kwargs: Any) -> tuple[dict, str]:
        self.calls.append((workflow, kwargs))
        return ({"ok": True}, "run-deterministic")


# ---------------------------------------------------------------------------
# WorkflowScheduler dispatch_via= tests
# ---------------------------------------------------------------------------

apscheduler = pytest.importorskip(
    "apscheduler", reason="WorkflowScheduler requires APScheduler"
)


class TestWorkflowSchedulerDispatchVia:
    """Validate the dispatch_via= contract per architecture plan §3."""

    def _make_scheduler(self, dispatcher: Dispatcher | None) -> Any:
        from kailash.runtime.scheduler import WorkflowScheduler

        rt = _RecordingRuntime()
        return (
            WorkflowScheduler(
                job_store_path=None,  # in-memory, no SQLite file
                runtime_factory=lambda: rt,
                dispatch_via=dispatcher,
            ),
            rt,
        )

    @pytest.mark.asyncio
    async def test_in_process_fallback_executes_workflow(self) -> None:
        """dispatch_via=None preserves existing in-process execution."""
        scheduler, rt = self._make_scheduler(dispatcher=None)
        builder = _RecordingBuilder("test-wf")

        await scheduler._execute_workflow(builder, schedule_id="sched-x")

        assert len(rt.calls) == 1, "in-process runtime MUST be invoked exactly once"
        executed_workflow, _kw = rt.calls[0]
        assert executed_workflow.name == "test-wf"

    @pytest.mark.asyncio
    async def test_dispatch_via_calls_enqueue_with_stable_task_id(self) -> None:
        """dispatch_via=<Dispatcher> enqueues a Task with stable task_id."""
        dispatcher = _RecordingDispatcher()
        scheduler, rt = self._make_scheduler(dispatcher=dispatcher)
        builder = _RecordingBuilder("test-wf")

        # Patch the planned-fire-time lookup to be deterministic. This is
        # NOT a mock of the unit under test — it pins external clock-state.
        fixed_ft = datetime(2026, 5, 6, 12, 0, 0, tzinfo=UTC)
        scheduler._planned_fire_time = lambda sid: fixed_ft

        await scheduler._execute_workflow(builder, schedule_id="sched-stable")

        assert (
            len(dispatcher.enqueued) == 1
        ), "dispatch_via path MUST enqueue exactly one Task"
        assert (
            len(rt.calls) == 0
        ), "in-process runtime MUST NOT fire when dispatch_via is set"

        task = dispatcher.enqueued[0]
        assert task.schedule_id == "sched-stable"
        assert task.task_id == compute_task_id("sched-stable", fixed_ft)
        assert task.planned_fire_time == fixed_ft.isoformat()

    @pytest.mark.asyncio
    async def test_dispatch_failure_logs_at_error_and_raises(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Non-PK enqueue failure logs ERROR with task_id_hash + raises."""
        dispatcher = _RecordingDispatcher()
        dispatcher.enqueue_raises = RuntimeError("network unreachable")
        scheduler, _rt = self._make_scheduler(dispatcher=dispatcher)
        builder = _RecordingBuilder("test-wf")

        fixed_ft = datetime(2026, 5, 6, 12, 0, 0, tzinfo=UTC)
        scheduler._planned_fire_time = lambda sid: fixed_ft

        with caplog.at_level(logging.ERROR, logger="kailash.runtime.scheduler"):
            with pytest.raises(RuntimeError, match="network unreachable"):
                await scheduler._execute_workflow(builder, schedule_id="sched-err")

        # ERROR log MUST cite schedule_id + task_id_hash per arch plan §3 inv 3.
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, "expected ERROR log on enqueue failure"
        msg = " ".join(r.getMessage() for r in error_records)
        assert "sched-err" in msg
        assert "task_id_hash=" in msg
        assert "RuntimeError" in msg


# ---------------------------------------------------------------------------
# EVENT_JOB_SUBMITTED listener fire-time capture (closes F1 + F2)
# ---------------------------------------------------------------------------


class _SubmitEventStub:
    """Minimal APScheduler-event-shaped record for the submit listener.

    The listener only reads `event.job_id` and `event.scheduled_run_time`;
    a small struct-like helper is sufficient to exercise the path
    deterministically in Tier 1.
    """

    def __init__(self, job_id: str, scheduled_run_time: datetime) -> None:
        self.job_id = job_id
        self.scheduled_run_time = scheduled_run_time


class TestPlannedFireTimeListener:
    """Validate _on_job_submitted/_planned_fire_time semantics (F1 + F2)."""

    def _make_scheduler(self) -> Any:
        from kailash.runtime.scheduler import WorkflowScheduler

        return WorkflowScheduler(job_store_path=None)

    def test_planned_fire_time_returns_listener_recorded_time(self) -> None:
        """_on_job_submitted records; _planned_fire_time reads it back."""
        scheduler = self._make_scheduler()
        fire_time = datetime(2026, 5, 7, 9, 30, 0, tzinfo=UTC)

        scheduler._on_job_submitted(_SubmitEventStub("sched-listener", fire_time))

        assert scheduler._planned_fire_time("sched-listener") == fire_time

    def test_planned_fire_time_raises_when_no_submit_recorded(self) -> None:
        """No silent now() fallback (rules/zero-tolerance.md Rule 3)."""
        scheduler = self._make_scheduler()

        with pytest.raises(RuntimeError, match="EVENT_JOB_SUBMITTED listener"):
            scheduler._planned_fire_time("sched-never-fired")

    def test_on_job_done_clears_recorded_fire_time(self) -> None:
        """Cleanup listener removes the entry after the job finishes."""
        scheduler = self._make_scheduler()
        fire_time = datetime(2026, 5, 7, 9, 30, 0, tzinfo=UTC)

        scheduler._on_job_submitted(_SubmitEventStub("sched-cleanup", fire_time))
        assert scheduler._planned_fire_time("sched-cleanup") == fire_time

        scheduler._on_job_done(_SubmitEventStub("sched-cleanup", fire_time))

        with pytest.raises(RuntimeError, match="EVENT_JOB_SUBMITTED listener"):
            scheduler._planned_fire_time("sched-cleanup")
