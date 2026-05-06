"""Built-in workflow scheduler for the Kailash SDK.

This module provides a production-ready workflow scheduler that enables
cron-based, interval-based, and one-shot scheduling of workflow executions.
It uses APScheduler as an optional dependency with a SQLite job store for
persistence across process restarts.

Usage:
    >>> from kailash.runtime.scheduler import WorkflowScheduler
    >>> from kailash.workflow.builder import WorkflowBuilder
    >>>
    >>> scheduler = WorkflowScheduler()
    >>> scheduler.start()
    >>>
    >>> workflow = WorkflowBuilder()
    >>> workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
    >>>
    >>> schedule_id = scheduler.schedule_cron(workflow, "0 */6 * * *")
    >>> schedule_id = scheduler.schedule_interval(workflow, seconds=300)
    >>> schedule_id = scheduler.schedule_once(workflow, run_at=datetime(2026, 4, 1))
    >>>
    >>> scheduler.cancel(schedule_id)
    >>> schedules = scheduler.list_schedules()
    >>> scheduler.shutdown()

Graceful Degradation:
    If APScheduler is not installed, importing this module succeeds but
    instantiating WorkflowScheduler raises ImportError with installation
    instructions.

See Also:
    - WorkflowBuilder: Creates workflows to schedule
    - LocalRuntime: Executes scheduled workflows
    - AsyncLocalRuntime: Async execution of scheduled workflows

Version:
    Added in: v0.13.0
"""

import logging
import math
import os
import pickle
import stat
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from kailash.runtime.dispatcher import Dispatcher

logger = logging.getLogger(__name__)

__all__ = [
    "WorkflowScheduler",
    "ScheduleInfo",
    "ScheduleType",
]

# Lazy import check for APScheduler
_apscheduler_available: Optional[bool] = None


def _check_apscheduler() -> bool:
    """Check if APScheduler is available."""
    global _apscheduler_available
    if _apscheduler_available is None:
        try:
            import apscheduler  # noqa: F401

            _apscheduler_available = True
        except ImportError:
            _apscheduler_available = False
    return _apscheduler_available


class ScheduleType(str, Enum):
    """Type of schedule trigger."""

    CRON = "cron"
    INTERVAL = "interval"
    ONCE = "once"


@dataclass
class ScheduleInfo:
    """Information about a scheduled workflow execution.

    Attributes:
        schedule_id: Unique identifier for this schedule.
        schedule_type: The type of trigger (cron, interval, once).
        workflow_name: Optional human-readable name for the workflow.
        trigger_args: The trigger configuration (cron expression, interval, or run_at).
        created_at: When the schedule was created.
        next_run_time: When the next execution is expected (None if paused/completed).
        enabled: Whether the schedule is active.
        kwargs: Additional keyword arguments passed to the runtime on execution.
    """

    schedule_id: str
    schedule_type: ScheduleType
    workflow_name: str = ""
    trigger_args: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    next_run_time: Optional[datetime] = None
    enabled: bool = True
    kwargs: Dict[str, Any] = field(default_factory=dict)


class WorkflowScheduler:
    """Scheduler for recurring and one-shot workflow executions.

    Uses APScheduler's AsyncIOScheduler internally with a SQLite job store
    for persistence across restarts. If APScheduler is not installed, raises
    ImportError with helpful installation instructions.

    Args:
        job_store_path: Path to the SQLite database for job persistence.
            Defaults to "kailash_schedules.db" in the current directory.
            Set to None to use in-memory storage (no persistence).
        runtime_factory: Optional callable that returns a runtime instance.
            Defaults to creating a new LocalRuntime for each execution.
        timezone: Timezone for cron expressions. Defaults to UTC.
        dispatch_via: Optional :class:`~kailash.runtime.dispatcher.Dispatcher`.
            When provided, every fired trigger enqueues a Task to the
            dispatcher instead of executing the workflow in-process.
            Default ``None`` preserves the existing in-process behavior.

    Raises:
        ImportError: If APScheduler is not installed.

    Example:
        >>> scheduler = WorkflowScheduler(job_store_path="schedules.db")
        >>> scheduler.start()
        >>> sid = scheduler.schedule_interval(my_workflow, seconds=60)
        >>> scheduler.shutdown()

        # Multi-instance / worker-side resume:
        >>> from kailash.infrastructure.task_queue import SQLTaskQueueDispatcher
        >>> from kailash.db.connection import ConnectionManager
        >>> conn = ConnectionManager("postgresql://...")
        >>> await conn.initialize()
        >>> dispatcher = SQLTaskQueueDispatcher(conn)
        >>> scheduler = WorkflowScheduler(dispatch_via=dispatcher)
    """

    def __init__(
        self,
        job_store_path: Optional[str] = "kailash_schedules.db",
        runtime_factory: Optional[Callable] = None,
        timezone: str = "UTC",
        *,
        dispatch_via: Optional["Dispatcher"] = None,
    ) -> None:
        if not _check_apscheduler():
            raise ImportError(
                "APScheduler is required for WorkflowScheduler. "
                "Install it with: pip install 'kailash[scheduler]' "
                "or: pip install 'apscheduler>=3.10'"
            )

        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        jobstores = {}
        if job_store_path is not None:
            jobstores["default"] = SQLAlchemyJobStore(url=f"sqlite:///{job_store_path}")
            # Set owner-only permissions on the SQLite file (POSIX only)
            if os.name == "posix":
                try:
                    db_abs = os.path.abspath(job_store_path)
                    # Touch to ensure the file exists before setting permissions
                    open(db_abs, "a").close()  # noqa: WPS515
                    os.chmod(db_abs, stat.S_IRUSR | stat.S_IWUSR)
                except OSError:
                    logger.warning(
                        "Could not set scheduler job store file permissions to 0o600"
                    )

        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            timezone=timezone,
        )
        self._runtime_factory = runtime_factory
        self._schedules: Dict[str, ScheduleInfo] = {}
        self._timezone = timezone
        self._dispatcher: Optional["Dispatcher"] = dispatch_via

        # Per-job fire-time capture: APScheduler's EVENT_JOB_SUBMITTED listener
        # fires BEFORE the job callback with `event.scheduled_run_time`, the
        # ACTUAL fire instant for the currently-firing job. We record it here
        # keyed by job_id so `_planned_fire_time(schedule_id)` can return the
        # current fire time -- NOT `job.next_run_time`, which APScheduler has
        # already advanced to the NEXT scheduled fire by the time the callback
        # runs (interval/cron schedules drift by one interval otherwise).
        self._fire_times: Dict[str, datetime] = {}
        from apscheduler.events import (
            EVENT_JOB_ERROR,
            EVENT_JOB_EXECUTED,
            EVENT_JOB_SUBMITTED,
        )

        self._scheduler.add_listener(self._on_job_submitted, EVENT_JOB_SUBMITTED)
        self._scheduler.add_listener(
            self._on_job_done, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
        )

        logger.info(
            "WorkflowScheduler initialized (job_store=%s, timezone=%s, dispatch=%s)",
            job_store_path or "memory",
            timezone,
            "queue" if dispatch_via is not None else "in_process",
        )

    def start(self) -> None:
        """Start the scheduler.

        Must be called before any schedules will execute. Safe to call
        multiple times (idempotent if already running).
        """
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("WorkflowScheduler started")

    def shutdown(self, wait: bool = True) -> None:
        """Shut down the scheduler.

        Args:
            wait: If True, wait for running jobs to complete before shutting down.
        """
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            logger.info("WorkflowScheduler shut down (wait=%s)", wait)

    def schedule_cron(
        self,
        workflow_builder: Any,
        cron_expression: str,
        name: str = "",
        **kwargs: Any,
    ) -> str:
        """Schedule a workflow to run on a cron schedule.

        Args:
            workflow_builder: A WorkflowBuilder instance to execute on each trigger.
            cron_expression: A cron expression string with 5 fields
                (minute hour day_of_month month day_of_week).
            name: Optional human-readable name for this schedule.
            **kwargs: Additional keyword arguments passed to the runtime on execution.

        Returns:
            A unique schedule_id that can be used to cancel or query this schedule.

        Raises:
            ValueError: If the cron expression is invalid.

        Example:
            >>> sid = scheduler.schedule_cron(workflow, "0 */6 * * *")  # Every 6 hours
            >>> sid = scheduler.schedule_cron(workflow, "30 2 * * 1")   # Mon 2:30 AM
        """
        from apscheduler.triggers.cron import CronTrigger

        schedule_id = self._generate_schedule_id()
        parts = cron_expression.strip().split()
        if len(parts) != 5:
            raise ValueError(
                f"Cron expression must have exactly 5 fields "
                f"(minute hour day month weekday), got {len(parts)}: '{cron_expression}'"
            )

        trigger = CronTrigger.from_crontab(cron_expression, timezone=self._timezone)

        self._scheduler.add_job(
            self._execute_workflow,
            trigger=trigger,
            id=schedule_id,
            args=[workflow_builder, schedule_id],
            kwargs=kwargs,
            replace_existing=True,
        )

        info = ScheduleInfo(
            schedule_id=schedule_id,
            schedule_type=ScheduleType.CRON,
            workflow_name=name,
            trigger_args={"cron_expression": cron_expression},
            kwargs=kwargs,
        )
        self._schedules[schedule_id] = info

        logger.info(
            "Scheduled cron workflow: id=%s, cron='%s', name='%s'",
            schedule_id,
            cron_expression,
            name,
        )
        return schedule_id

    def schedule_interval(
        self,
        workflow_builder: Any,
        seconds: float,
        name: str = "",
        **kwargs: Any,
    ) -> str:
        """Schedule a workflow to run at a fixed interval.

        Args:
            workflow_builder: A WorkflowBuilder instance to execute on each trigger.
            seconds: Interval in seconds between executions.
            name: Optional human-readable name for this schedule.
            **kwargs: Additional keyword arguments passed to the runtime on execution.

        Returns:
            A unique schedule_id.

        Raises:
            ValueError: If seconds is not positive.

        Example:
            >>> sid = scheduler.schedule_interval(workflow, seconds=300)  # Every 5 min
        """
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError(
                f"Interval seconds must be a positive finite number, got {seconds}"
            )

        schedule_id = self._generate_schedule_id()

        self._scheduler.add_job(
            self._execute_workflow,
            trigger="interval",
            seconds=seconds,
            id=schedule_id,
            args=[workflow_builder, schedule_id],
            kwargs=kwargs,
            replace_existing=True,
        )

        info = ScheduleInfo(
            schedule_id=schedule_id,
            schedule_type=ScheduleType.INTERVAL,
            workflow_name=name,
            trigger_args={"seconds": seconds},
            kwargs=kwargs,
        )
        self._schedules[schedule_id] = info

        logger.info(
            "Scheduled interval workflow: id=%s, seconds=%s, name='%s'",
            schedule_id,
            seconds,
            name,
        )
        return schedule_id

    def schedule_once(
        self,
        workflow_builder: Any,
        run_at: datetime,
        name: str = "",
        **kwargs: Any,
    ) -> str:
        """Schedule a workflow to run once at a specific time.

        Args:
            workflow_builder: A WorkflowBuilder instance to execute.
            run_at: The datetime at which to execute the workflow.
            name: Optional human-readable name for this schedule.
            **kwargs: Additional keyword arguments passed to the runtime on execution.

        Returns:
            A unique schedule_id.

        Raises:
            ValueError: If run_at is in the past.

        Example:
            >>> from datetime import datetime, UTC
            >>> run_at = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
            >>> sid = scheduler.schedule_once(workflow, run_at=run_at)
        """
        schedule_id = self._generate_schedule_id()

        self._scheduler.add_job(
            self._execute_workflow,
            trigger="date",
            run_date=run_at,
            id=schedule_id,
            args=[workflow_builder, schedule_id],
            kwargs=kwargs,
            replace_existing=True,
        )

        info = ScheduleInfo(
            schedule_id=schedule_id,
            schedule_type=ScheduleType.ONCE,
            workflow_name=name,
            trigger_args={"run_at": run_at.isoformat()},
            next_run_time=run_at,
            kwargs=kwargs,
        )
        self._schedules[schedule_id] = info

        logger.info(
            "Scheduled one-shot workflow: id=%s, run_at=%s, name='%s'",
            schedule_id,
            run_at.isoformat(),
            name,
        )
        return schedule_id

    def cancel(self, schedule_id: str) -> None:
        """Cancel a scheduled workflow execution.

        Args:
            schedule_id: The ID returned by schedule_cron/interval/once.

        Raises:
            KeyError: If schedule_id is not found.
        """
        if schedule_id not in self._schedules:
            raise KeyError(f"Schedule '{schedule_id}' not found")

        self._scheduler.remove_job(schedule_id)
        del self._schedules[schedule_id]

        logger.info("Cancelled schedule: %s", schedule_id)

    def list_schedules(self) -> List[ScheduleInfo]:
        """List all active schedules.

        Returns:
            A list of ScheduleInfo objects for all registered schedules.
        """
        # Update next_run_time from the underlying scheduler
        for schedule_id, info in self._schedules.items():
            job = self._scheduler.get_job(schedule_id)
            if job is not None:
                info.next_run_time = job.next_run_time
                info.enabled = job.next_run_time is not None
            else:
                info.enabled = False
                info.next_run_time = None

        return list(self._schedules.values())

    async def _execute_workflow(
        self, workflow_builder: Any, schedule_id: str = "", **kwargs: Any
    ) -> None:
        """Execute a workflow from a scheduled trigger.

        This is the callback invoked by APScheduler at fire time. The
        behavior depends on whether the scheduler was constructed with
        ``dispatch_via=``:

        * **In-process (default, ``dispatch_via=None``):** builds the
          workflow and executes it via the configured runtime in the
          current process.
        * **Queue dispatch (``dispatch_via=<Dispatcher>``):** serializes
          the workflow into a :class:`~kailash.runtime.dispatcher.Task`
          and enqueues it via the dispatcher; a worker pool polls the
          queue and executes against its own runtime. ``task_id`` is
          ``compute_task_id(schedule_id, planned_fire_time)`` so a
          multi-instance scheduler that double-fires produces the same
          task_id and the queue dedups.

        Args:
            workflow_builder: The WorkflowBuilder to build and execute.
            schedule_id: The scheduler-assigned schedule identifier.
                Wired in by ``schedule_cron`` / ``schedule_interval`` /
                ``schedule_once`` when registering the APScheduler job.
            **kwargs: Additional runtime execution parameters (in-process
                path) or task kwargs (queue dispatch path).
        """
        run_id = str(uuid.uuid4())

        if self._dispatcher is not None:
            await self._dispatch_to_queue(
                workflow_builder=workflow_builder,
                schedule_id=schedule_id,
                run_id=run_id,
                **kwargs,
            )
            return

        # In-process fallback (existing behavior).
        logger.info("Scheduled execution starting: run_id=%s", run_id)
        try:
            workflow = workflow_builder.build()
            runtime = self._get_runtime()
            results, actual_run_id = runtime.execute(workflow, **kwargs)
            logger.info(
                "Scheduled execution completed: run_id=%s, results_count=%d",
                actual_run_id,
                len(results) if results else 0,
            )
        except Exception:
            logger.exception("Scheduled execution failed: run_id=%s", run_id)
            raise

    async def _dispatch_to_queue(
        self,
        *,
        workflow_builder: Any,
        schedule_id: str,
        run_id: str,
        **kwargs: Any,
    ) -> None:
        """Serialize the workflow and enqueue a Task via the dispatcher.

        Per architecture plan §3 invariant 1, ``task_id`` is the stable
        SHA-256 hash of ``(schedule_id, planned_fire_time_iso)``. The
        planned fire time is the trigger's intended fire instant -- not
        wall-clock now() -- so multi-instance scheduler double-fires
        produce the SAME task_id and the queue layer dedups.

        Per architecture plan §3 invariant 3, every enqueue failure
        logs at ERROR with grep-able schedule_id + task_id_hash before
        propagating to APScheduler (which records the missed-fire
        per its own retry/misfire policy).
        """
        # Lazy import to keep `from kailash.runtime.scheduler import ...`
        # path free of dispatcher dependencies for in-process-only users.
        import hashlib

        from kailash.runtime.dispatcher import Task, compute_task_id

        # APScheduler delivers the CURRENT fire time via the
        # EVENT_JOB_SUBMITTED listener (`event.scheduled_run_time`); see
        # ``_on_job_submitted`` for the capture point. Reading
        # ``job.next_run_time`` here would be wrong — by the time this
        # callback runs APScheduler has already advanced ``next_run_time``
        # to the NEXT scheduled fire, so the recorded ``planned_fire_time``
        # would drift by one interval on every cron/interval trigger.
        planned_fire_time = self._planned_fire_time(schedule_id)
        task_id = compute_task_id(schedule_id, planned_fire_time)
        task_id_hash = hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:8]

        logger.info(
            "scheduler.dispatch.start schedule_id=%s task_id_hash=%s run_id=%s",
            schedule_id,
            task_id_hash,
            run_id,
        )

        try:
            workflow = workflow_builder.build()
            workflow_blob = pickle.dumps(workflow)
        except Exception:
            logger.exception(
                "scheduler.dispatch.serialize_failed schedule_id=%s task_id_hash=%s",
                schedule_id,
                task_id_hash,
            )
            raise

        task = Task(
            task_id=task_id,
            schedule_id=schedule_id,
            workflow_blob=workflow_blob,
            planned_fire_time=planned_fire_time.isoformat(),
            kwargs=dict(kwargs),
        )

        try:
            await self._dispatcher.enqueue(task)  # type: ignore[union-attr]
        except Exception as exc:
            logger.error(
                "scheduler.dispatch.enqueue_failed schedule_id=%s task_id_hash=%s reason=%s",
                schedule_id,
                task_id_hash,
                type(exc).__name__,
            )
            raise

        logger.info(
            "scheduler.dispatch.enqueued schedule_id=%s task_id_hash=%s",
            schedule_id,
            task_id_hash,
        )

    def _on_job_submitted(self, event: Any) -> None:
        """APScheduler EVENT_JOB_SUBMITTED listener — record fire time.

        Fires BEFORE the job callback with
        ``event.scheduled_run_times: list[datetime]`` carrying the
        CURRENT trigger fire instant(s). The list typically holds one
        entry; under coalesce/misfire policies APScheduler may pass
        multiple. We record the LAST element — the most recent fire
        the trigger produced — so the dispatch callback can read the
        correct fire time without relying on ``job.next_run_time``
        (which APScheduler has already advanced to the next scheduled
        fire by the time the callback runs).

        We key by ``event.job_id`` (== ``schedule_id``).
        """
        run_times = event.scheduled_run_times
        if not run_times:
            # Empty list violates APScheduler's own dispatch contract;
            # raise so the failure surfaces at the listener boundary
            # instead of producing a silently-misrecorded fire time.
            raise RuntimeError(
                f"EVENT_JOB_SUBMITTED for job_id={event.job_id!r} carried "
                f"empty scheduled_run_times list — APScheduler internal "
                f"invariant violation"
            )
        self._fire_times[event.job_id] = run_times[-1]

    def _on_job_done(self, event: Any) -> None:
        """Cleanup the recorded fire time after the job finishes.

        Listens on ``EVENT_JOB_EXECUTED | EVENT_JOB_ERROR``. If the
        scheduler ever drops a job mid-flight without firing either
        event, the entry remains in ``_fire_times`` for the next
        successful submission to overwrite — bounded by the number of
        active schedules.
        """
        self._fire_times.pop(event.job_id, None)

    def _planned_fire_time(self, schedule_id: str) -> datetime:
        """Return the actual fire time of the currently-firing job.

        Reads from ``_fire_times``, populated by the
        ``EVENT_JOB_SUBMITTED`` listener (``_on_job_submitted``). This
        is the SCHEDULED fire instant the trigger fired for, NOT
        ``job.next_run_time`` — which APScheduler advances to the NEXT
        scheduled fire as soon as the current job is submitted.

        Stable across multi-instance schedulers: every instance receives
        the same ``scheduled_run_time`` from APScheduler for the same
        trigger fire, so ``compute_task_id(schedule_id, fire_time)``
        produces the SAME ``task_id`` and the queue layer dedups via PK.

        Raises:
            RuntimeError: if invoked for a ``schedule_id`` whose
                ``EVENT_JOB_SUBMITTED`` listener has not yet recorded a
                fire time. Falling back to ``datetime.now(UTC)`` would
                silently break the dedup invariant
                (``rules/zero-tolerance.md`` Rule 3).
        """
        fire_time = self._fire_times.get(schedule_id)
        if fire_time is None:
            raise RuntimeError(
                f"_planned_fire_time invoked for schedule_id={schedule_id!r} "
                f"but EVENT_JOB_SUBMITTED listener has not recorded a fire "
                f"time. Dispatch was called outside the APScheduler job-firing "
                f"path, or the listener was not registered. Refusing to fall "
                f"back to datetime.now(UTC) -- doing so would silently break "
                f"multi-instance dedup (each scheduler instance would compute "
                f"a different task_id for the same fire)."
            )
        return fire_time

    def _get_runtime(self) -> Any:
        """Get or create a runtime instance for execution.

        Returns:
            A runtime instance (LocalRuntime by default).
        """
        if self._runtime_factory is not None:
            return self._runtime_factory()

        from kailash.runtime.local import LocalRuntime

        return LocalRuntime()

    @staticmethod
    def _generate_schedule_id() -> str:
        """Generate a unique schedule ID.

        Returns:
            A UUID-based schedule identifier prefixed with 'sched-'.
        """
        return f"sched-{uuid.uuid4().hex[:12]}"
