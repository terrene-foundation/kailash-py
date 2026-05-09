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

import asyncio
import builtins
import logging
import math
import os
import stat
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple, Type

if TYPE_CHECKING:
    from kailash.runtime.dispatcher import Dispatcher

logger = logging.getLogger(__name__)

__all__ = [
    "WorkflowScheduler",
    "ScheduleInfo",
    "ScheduleType",
    "RetrySpec",
]

# Internal kwargs key used to thread the per-job RetrySpec through APScheduler's
# `kwargs=` dict to ``_execute_workflow`` at fire time. Popped before the
# remaining kwargs are forwarded to the runtime so user code never sees it.
_RETRY_SPEC_KWARG = "_kailash_retry_spec"


@dataclass(frozen=True)
class RetrySpec:
    """Declarative per-job retry primitive (issue #910).

    Equivalent to celery's ``@shared_task(bind=True, autoretry_for=(...),
    retry_backoff=True, max_retries=N)`` directive: when a scheduled
    workflow raises a retryable exception, the scheduler re-runs it up to
    ``max_retries`` more times with a backoff delay between attempts.

    Attributes:
        max_retries: Maximum number of retry attempts AFTER the initial
            attempt fails. ``max_retries=0`` is the no-retry case
            (single attempt, original behavior). Total attempts =
            ``1 + max_retries``.
        backoff: ``"exponential"`` (default) doubles the delay each
            attempt: ``base * 2 ** (attempt - 1)``. ``"linear"`` adds the
            base each attempt: ``base * attempt``.
        backoff_base_seconds: Initial delay before the FIRST retry.
            Subsequent retries follow the ``backoff`` curve. Must be > 0.
        backoff_max_seconds: Upper bound on any single backoff delay.
            Prevents exponential backoff from blocking the scheduler for
            unbounded periods on long-lived schedules.
        retry_on: Tuple of exception types that ARE retryable. Defaults
            to ``(Exception,)`` — retry on any non-system exception.
            ``BaseException`` subclasses NOT in :class:`Exception` (e.g.
            ``KeyboardInterrupt``, ``SystemExit``) are never retried;
            this is intentional safety, not configurability.
        dont_retry_on: Tuple of exception types that are NEVER retried,
            even if they would match ``retry_on``. Checked first; useful
            for "retry transient failures but not validation errors".

    Examples:
        >>> # Retry up to 3 times, exponential backoff (1s, 2s, 4s)
        >>> spec = RetrySpec(max_retries=3)
        >>> # Retry only on transient network errors
        >>> spec = RetrySpec(max_retries=5, retry_on=(ConnectionError, TimeoutError))
        >>> # Retry on Exception except ValueError
        >>> spec = RetrySpec(max_retries=2, dont_retry_on=(ValueError,))

    Notes:
        **Cron-fire interaction**: a retry-bearing schedule with
        ``max_retries × backoff_max_seconds`` exceeding the schedule
        interval will block the next scheduled fire (APScheduler's
        ``max_instances=1`` default), triggering the misfire policy.
        Operators MUST size ``max_retries`` and ``backoff_max_seconds`` so
        the total worst-case retry budget fits within the interval, OR
        configure ``max_instances`` and ``misfire_grace_time`` on the job
        explicitly (these are forwarded as APScheduler kwargs).

        **Persistence stability**: when a scheduler is constructed with a
        SQLAlchemy job-store path (the default), APScheduler pickles the
        job kwargs — including the ``RetrySpec`` instance — to disk. This
        dataclass is frozen (``@dataclass(frozen=True)``) and its field
        set is part of the SDK's persistence contract: removing or
        renaming fields would break job-store reload across SDK versions.
        Field additions MUST default to backward-compatible values (the
        existing constructor signatures preserve unpickle behavior).
    """

    max_retries: int = 0
    backoff: str = "exponential"
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 60.0
    retry_on: Tuple[Type[BaseException], ...] = (Exception,)
    dont_retry_on: Tuple[Type[BaseException], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.max_retries, int) or self.max_retries < 0:
            raise ValueError(
                f"RetrySpec.max_retries must be a non-negative integer, "
                f"got {self.max_retries!r}"
            )
        if self.backoff not in ("linear", "exponential"):
            raise ValueError(
                f"RetrySpec.backoff must be 'linear' or 'exponential', "
                f"got {self.backoff!r}"
            )
        if (
            not isinstance(self.backoff_base_seconds, (int, float))
            or not math.isfinite(self.backoff_base_seconds)
            or self.backoff_base_seconds <= 0
        ):
            raise ValueError(
                f"RetrySpec.backoff_base_seconds must be a positive finite "
                f"number, got {self.backoff_base_seconds!r}"
            )
        if (
            not isinstance(self.backoff_max_seconds, (int, float))
            or not math.isfinite(self.backoff_max_seconds)
            or self.backoff_max_seconds < self.backoff_base_seconds
        ):
            raise ValueError(
                f"RetrySpec.backoff_max_seconds must be a finite number "
                f">= backoff_base_seconds ({self.backoff_base_seconds}), "
                f"got {self.backoff_max_seconds!r}"
            )
        for label, types in (
            ("retry_on", self.retry_on),
            ("dont_retry_on", self.dont_retry_on),
        ):
            if not isinstance(types, tuple) or not all(
                isinstance(t, type) and issubclass(t, BaseException) for t in types
            ):
                raise ValueError(
                    f"RetrySpec.{label} must be a tuple of BaseException "
                    f"subclasses, got {types!r}"
                )

    def is_retryable(self, exc: BaseException) -> bool:
        """Return True iff ``exc`` should trigger a retry under this spec.

        ``dont_retry_on`` is checked first; an exception matching it is
        NEVER retried even if it also matches ``retry_on``. ``BaseException``
        subclasses outside ``Exception`` (KeyboardInterrupt, SystemExit) are
        unconditionally non-retryable for safety — operators expect Ctrl+C
        and process-termination signals to halt the scheduler immediately.
        """
        if not isinstance(exc, Exception):
            return False
        if self.dont_retry_on and isinstance(exc, self.dont_retry_on):
            return False
        return isinstance(exc, self.retry_on)

    def compute_backoff_seconds(self, attempt: int) -> float:
        """Return the delay before retry attempt ``attempt`` (1-indexed).

        ``attempt=1`` is the first retry (after the initial run failed);
        ``attempt=2`` is the second retry; etc. The result is clamped at
        :attr:`backoff_max_seconds` to bound long exponential delays.
        """
        if attempt < 1:
            raise ValueError(f"attempt must be >= 1, got {attempt}")
        if self.backoff == "exponential":
            delay = self.backoff_base_seconds * (2 ** (attempt - 1))
        else:  # linear
            delay = self.backoff_base_seconds * attempt
        return min(delay, self.backoff_max_seconds)


# Lazy import check for APScheduler
# Bound on the per-job fire-time map below. Schedulers that submit and never
# clean up (cancelled mid-flight, EVENT_JOB_EXECUTED suppressed by listener
# error, etc.) would otherwise grow `_fire_times` without bound. 10_000 is
# the same default as `rules/infrastructure-sql.md` Rule 7 ("Bounded
# In-Memory Stores"); active-schedule counts in production are O(100s).
MAX_FIRE_TIMES = 10_000

# Cap on the JSON-encoded workflow blob the queue path serializes. Worker
# pools dequeue and `json.loads` the payload; without a cap, a workflow
# whose `to_dict()` produces multi-megabyte output (e.g. a node config
# carrying a large embedded model bundle) OOMs every dequeueing worker.
# Re-exported from `runtime/_workflow_blob.py` — that module is the
# canonical home so both scheduler.py AND durable.py route their
# workflow_blob serialization through `serialize_workflow_to_blob` and
# emit byte-identical output. The local re-export preserves callers
# that import `MAX_WORKFLOW_BLOB_BYTES` from `kailash.runtime.scheduler`.
# Note: the size-cap check now lives in the helper, so tests that need
# a smaller cap to exercise the size-cap path MUST patch
# `kailash.runtime._workflow_blob.MAX_WORKFLOW_BLOB_BYTES` (the helper
# reads its own module-scope binding), not this re-exported alias.
from kailash.runtime._workflow_blob import (  # noqa: E402
    MAX_WORKFLOW_BLOB_BYTES,
    serialize_workflow_to_blob,
)

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


def _secure_init_sqlite_jobstore(db_abs: str) -> None:
    """Atomically create the SQLite job-store file with 0o600 + symlink refusal,
    then pre-create WAL/SHM sidecars under the same restrictive mode.

    Closes two HIGH findings (issue #871):

    1. **TOCTOU on chmod.** ``os.open(..., O_RDWR|O_CREAT|O_NOFOLLOW, 0o600)``
       creates the file with restrictive mode in one syscall and refuses to
       follow a symlink. Replaces the prior ``open(...).close(); os.chmod(...)``
       race window where a parent-directory-controlling attacker could swap
       a target between the two calls.

    2. **WAL/SHM sidecars world-readable.** SQLAlchemy + SQLite in WAL mode
       creates ``<db>-wal`` and ``<db>-shm`` at first write with default
       umask. We force WAL mode + a write transaction here, then chmod the
       sidecars BEFORE APScheduler's engine ever opens the file — eliminating
       the window where job-data bytes (including serialized callback +
       kwargs) live world-readable on multi-user hosts.

    Behavior on non-POSIX platforms: caller MUST gate via ``os.name == "posix"``;
    this function assumes ``fchmod`` and ``O_NOFOLLOW`` are available.

    Raises:
        OSError: ``ELOOP`` if ``db_abs`` is a symlink (security: refuse).
            Other ``OSError`` propagate from the secure-init path; callers
            see the clear failure rather than a silently-degraded permission
            state.
    """
    import sqlite3

    fd = os.open(
        db_abs,
        os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
        0o600,
    )
    try:
        # Tighten existing files (created with default umask before this fix
        # was deployed) — new files are already 0o600 from os.open mode.
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
    finally:
        os.close(fd)

    # Force WAL mode + materialize sidecars now, while we own the connection
    # and can chmod the resulting files before any other process opens them.
    # SQLAlchemy will reuse the WAL configuration on subsequent connections
    # (journal_mode is persistent in the SQLite database header).
    with sqlite3.connect(db_abs) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        # A committed write is required to actually create -wal / -shm.
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _kailash_secure_init (k INTEGER PRIMARY KEY)"
        )
        conn.commit()

    # Sidecars were created by sqlite3 under the process umask; tighten them
    # to match the main DB. We just created these files ourselves so there
    # is no symlink-swap race here — chmod is the right tool.
    for suffix in ("-wal", "-shm"):
        sidecar = f"{db_abs}{suffix}"
        if os.path.exists(sidecar):
            os.chmod(sidecar, stat.S_IRUSR | stat.S_IWUSR)


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
    retry_spec: Optional[RetrySpec] = None


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
            if os.name == "posix":
                # Atomically create the job-store file with restrictive mode AND refuse
                # symlinks — closes the open-then-chmod TOCTOU window and pre-creates
                # the WAL/SHM sidecars with 0o600 BEFORE APScheduler's SQLAlchemy engine
                # ever opens the file. See `rules/security.md` § "Credential Decode
                # Helpers" for the structural-defense pattern.
                _secure_init_sqlite_jobstore(os.path.abspath(job_store_path))
            jobstores["default"] = SQLAlchemyJobStore(url=f"sqlite:///{job_store_path}")

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
        #
        # `OrderedDict` + LRU eviction at MAX_FIRE_TIMES per
        # `rules/infrastructure-sql.md` Rule 7. EVENT_JOB_EXECUTED |
        # EVENT_JOB_ERROR pop entries on the happy path; LRU eviction is
        # the safety net for jobs cancelled mid-flight where the cleanup
        # listener never fires. `cancel()` also pops the entry explicitly.
        self._fire_times: "OrderedDict[str, datetime]" = OrderedDict()
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
        *,
        retry: Optional[RetrySpec] = None,
        **kwargs: Any,
    ) -> str:
        """Schedule a workflow to run on a cron schedule.

        Args:
            workflow_builder: A WorkflowBuilder instance to execute on each trigger.
            cron_expression: A cron expression string with 5 fields
                (minute hour day_of_month month day_of_week).
            name: Optional human-readable name for this schedule.
            retry: Optional :class:`RetrySpec` (#910). When supplied, a fire
                that raises a retryable exception is retried up to
                ``spec.max_retries`` times with backoff before bubbling to
                APScheduler's job-error listener. ``None`` (default) preserves
                the original single-attempt behavior.
            **kwargs: Additional keyword arguments passed to the runtime on execution.

        Returns:
            A unique schedule_id that can be used to cancel or query this schedule.

        Raises:
            ValueError: If the cron expression is invalid.

        Example:
            >>> sid = scheduler.schedule_cron(workflow, "0 */6 * * *")  # Every 6 hours
            >>> sid = scheduler.schedule_cron(
            ...     workflow, "30 2 * * 1",
            ...     retry=RetrySpec(max_retries=3, retry_on=(ConnectionError,)),
            ... )
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

        job_kwargs = self._compose_job_kwargs(kwargs, retry)
        self._scheduler.add_job(
            self._execute_workflow,
            trigger=trigger,
            id=schedule_id,
            args=[workflow_builder, schedule_id],
            kwargs=job_kwargs,
            replace_existing=True,
        )

        info = ScheduleInfo(
            schedule_id=schedule_id,
            schedule_type=ScheduleType.CRON,
            workflow_name=name,
            trigger_args={"cron_expression": cron_expression},
            kwargs=kwargs,
            retry_spec=retry,
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
        *,
        retry: Optional[RetrySpec] = None,
        **kwargs: Any,
    ) -> str:
        """Schedule a workflow to run at a fixed interval.

        Args:
            workflow_builder: A WorkflowBuilder instance to execute on each trigger.
            seconds: Interval in seconds between executions.
            name: Optional human-readable name for this schedule.
            retry: Optional :class:`RetrySpec` (#910); see :meth:`schedule_cron`.
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

        job_kwargs = self._compose_job_kwargs(kwargs, retry)
        self._scheduler.add_job(
            self._execute_workflow,
            trigger="interval",
            seconds=seconds,
            id=schedule_id,
            args=[workflow_builder, schedule_id],
            kwargs=job_kwargs,
            replace_existing=True,
        )

        info = ScheduleInfo(
            schedule_id=schedule_id,
            schedule_type=ScheduleType.INTERVAL,
            workflow_name=name,
            trigger_args={"seconds": seconds},
            kwargs=kwargs,
            retry_spec=retry,
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
        *,
        retry: Optional[RetrySpec] = None,
        **kwargs: Any,
    ) -> str:
        """Schedule a workflow to run once at a specific time.

        Args:
            workflow_builder: A WorkflowBuilder instance to execute.
            run_at: The datetime at which to execute the workflow.
            name: Optional human-readable name for this schedule.
            retry: Optional :class:`RetrySpec` (#910); see :meth:`schedule_cron`.
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

        job_kwargs = self._compose_job_kwargs(kwargs, retry)
        self._scheduler.add_job(
            self._execute_workflow,
            trigger="date",
            run_date=run_at,
            id=schedule_id,
            args=[workflow_builder, schedule_id],
            kwargs=job_kwargs,
            replace_existing=True,
        )

        info = ScheduleInfo(
            schedule_id=schedule_id,
            schedule_type=ScheduleType.ONCE,
            workflow_name=name,
            trigger_args={"run_at": run_at.isoformat()},
            next_run_time=run_at,
            kwargs=kwargs,
            retry_spec=retry,
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
        # Drop the per-job fire-time entry. Cancellation can race the
        # EVENT_JOB_EXECUTED | EVENT_JOB_ERROR cleanup listener; explicit
        # pop here closes the leak window for jobs cancelled while
        # APScheduler considered them in-flight.
        self._fire_times.pop(schedule_id, None)

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

    def _compose_job_kwargs(
        self, user_kwargs: Dict[str, Any], retry: Optional[RetrySpec]
    ) -> Dict[str, Any]:
        """Merge a user-supplied kwargs dict with the internal retry spec key.

        Returns a NEW dict — does NOT mutate ``user_kwargs`` so the caller's
        ScheduleInfo.kwargs reflects only the user-visible kwargs (the
        ``_kailash_retry_spec`` key is internal and MUST NOT leak into
        :class:`ScheduleInfo` view).

        Refuses to silently overwrite a user-supplied key with the same name
        — this would be ``zero-tolerance.md`` Rule 3 silent fallback class.

        Raises ``ValueError`` when ``retry`` is supplied alongside
        ``dispatch_via=`` (queue-dispatch path): RetrySpec applies only to
        the in-process fire path; the queue-dispatch path is the
        dispatcher's domain (worker-side retry semantics owned by #911 /
        #912). Silently dropping the spec would be a ``zero-tolerance.md``
        Rule 3c violation (documented kwarg accepted but unused).
        """
        if _RETRY_SPEC_KWARG in user_kwargs:
            raise ValueError(
                f"kwarg name {_RETRY_SPEC_KWARG!r} is reserved for internal "
                f"use; rename your runtime kwarg to avoid the collision"
            )
        if retry is not None and self._dispatcher is not None:
            raise ValueError(
                "retry= is not supported when WorkflowScheduler was constructed "
                "with dispatch_via=<Dispatcher>. Worker-side retry semantics are "
                "the dispatcher's contract; pass retry=None and configure "
                "retries on the worker / dispatcher layer instead."
            )
        merged = dict(user_kwargs)
        if retry is not None:
            merged[_RETRY_SPEC_KWARG] = retry
        return merged

    async def _execute_workflow(
        self, workflow_builder: Any, schedule_id: str = "", **kwargs: Any
    ) -> None:
        """Execute a workflow from a scheduled trigger.

        This is the callback invoked by APScheduler at fire time. The
        behavior depends on whether the scheduler was constructed with
        ``dispatch_via=``:

        * **In-process (default, ``dispatch_via=None``):** builds the
          workflow and executes it via the configured runtime in the
          current process. When a :class:`RetrySpec` was supplied at
          schedule time (issue #910), the in-process path retries the
          workflow up to ``spec.max_retries`` times with backoff before
          re-raising the final exception to APScheduler's job-error
          listener.
        * **Queue dispatch (``dispatch_via=<Dispatcher>``):** serializes
          the workflow into a :class:`~kailash.runtime.dispatcher.Task`
          and enqueues it via the dispatcher; a worker pool polls the
          queue and executes against its own runtime. ``task_id`` is
          ``compute_task_id(schedule_id, planned_fire_time)`` so a
          multi-instance scheduler that double-fires produces the same
          task_id and the queue dedups. ``RetrySpec`` is NOT applied on
          the queue dispatch path — worker-side retry semantics are
          owned by the dispatcher contract, not the scheduler callback.

        Args:
            workflow_builder: The WorkflowBuilder to build and execute.
            schedule_id: The scheduler-assigned schedule identifier.
                Wired in by ``schedule_cron`` / ``schedule_interval`` /
                ``schedule_once`` when registering the APScheduler job.
            **kwargs: Additional runtime execution parameters (in-process
                path) or task kwargs (queue dispatch path). The internal
                ``_kailash_retry_spec`` key is popped here and never
                forwarded to user code.
        """
        run_id = str(uuid.uuid4())

        # Pop the internal retry spec before forwarding kwargs anywhere — keeps
        # `runtime.execute(**kwargs)` and the dispatcher Task kwargs free of
        # the internal threading key. Per `zero-tolerance.md` Rule 3c, this
        # kwarg is consumed: either by the retry loop below, or explicitly
        # ignored on the queue dispatch path with a documented rationale above.
        retry_spec: Optional[RetrySpec] = kwargs.pop(_RETRY_SPEC_KWARG, None)

        if self._dispatcher is not None:
            await self._dispatch_to_queue(
                workflow_builder=workflow_builder,
                schedule_id=schedule_id,
                run_id=run_id,
                **kwargs,
            )
            return

        # In-process fallback (existing behavior + retry primitive #910).
        logger.info("Scheduled execution starting: run_id=%s", run_id)
        max_attempts = 1 + (retry_spec.max_retries if retry_spec else 0)
        last_exc: Optional[BaseException] = None
        for attempt in range(1, max_attempts + 1):
            try:
                workflow = workflow_builder.build()
                runtime = self._get_runtime()
                results, actual_run_id = runtime.execute(workflow, **kwargs)
                # LocalRuntime swallows leaf-node failures into a result entry
                # of shape ``{"failed": True, "error": str, "error_type": str}``
                # rather than raising. For #910 the retry primitive MUST observe
                # that recorded failure as if it were a propagated exception —
                # otherwise a node-level raise on a scheduled job is invisible
                # to retry semantics. Synthesize a typed exception from the
                # first recorded failure so the retryable-classifier sees the
                # correct exception type.
                node_failure = self._extract_node_failure(results)
                if node_failure is not None:
                    raise node_failure
                logger.info(
                    "Scheduled execution completed: run_id=%s, results_count=%d, attempt=%d/%d",
                    actual_run_id,
                    len(results) if results else 0,
                    attempt,
                    max_attempts,
                )
                return
            except asyncio.CancelledError:
                # Scheduler shutdown / job cancellation MUST propagate cleanly —
                # the `except Exception` below would catch CancelledError on
                # Python 3.8+ (where it's an Exception subclass), letting the
                # retry loop swallow shutdown. Re-raise BEFORE the broad except.
                raise
            except Exception as exc:
                last_exc = exc
                # Non-retryable: skip ahead to the bubble-up below.
                if retry_spec is None or not retry_spec.is_retryable(exc):
                    break
                # Retryable AND budget remaining: DEBUG-level per-attempt log
                # (per `observability.md` MUST NOT § log-spam-in-hot-loops —
                # operators with `max_retries=10` would otherwise see 10 WARN
                # records per fire). Final-attempt summary WARN below covers
                # the operator-alert axis.
                if attempt < max_attempts:
                    backoff_seconds = retry_spec.compute_backoff_seconds(attempt)
                    logger.debug(
                        "Scheduled execution failed (attempt %d/%d): "
                        "run_id=%s schedule_id=%s exc_type=%s; retrying in %.2fs",
                        attempt,
                        max_attempts,
                        run_id,
                        schedule_id,
                        type(exc).__name__,
                        backoff_seconds,
                    )
                    await asyncio.sleep(backoff_seconds)
                    continue
                # Retryable but budget exhausted: fall through to bubble-up.
                break

        # Bubble the last exception so APScheduler's job-error listener fires
        # for the FINAL attempt only — intermediate retries do not surface as
        # job-error events, matching celery's autoretry semantics. Use an
        # explicit raise instead of `assert last_exc is not None` because
        # `python -O` strips asserts and would turn the loop-invariant
        # violation into `raise None` -> opaque TypeError.
        if last_exc is None:
            raise RuntimeError(
                "scheduler retry loop exited without an exception — "
                "internal invariant violated"
            )
        # Summary WARN at bubble-up time (per `observability.md` Rule 7
        # bulk-op pattern — one summary record per fire so aggregators see
        # the failure count, not N individual retry records). Matches the
        # original retry-attempt WARN content but emits exactly once.
        if retry_spec is not None and max_attempts > 1:
            logger.warning(
                "Scheduled execution exhausted retries: "
                "run_id=%s schedule_id=%s attempts=%d/%d final_exc=%s",
                run_id,
                schedule_id,
                max_attempts,
                max_attempts,
                type(last_exc).__name__,
            )
        logger.exception(
            "Scheduled execution failed (final): run_id=%s schedule_id=%s",
            run_id,
            schedule_id,
        )
        raise last_exc

    @staticmethod
    def _extract_node_failure(results: Optional[Dict[str, Any]]) -> Optional[Exception]:
        """Synthesize a typed exception from a LocalRuntime ``failed: True`` entry.

        ``LocalRuntime`` records leaf-node failures as a result-dict entry of
        shape ``{"failed": True, "error": str, "error_type": str}`` instead of
        raising. The retry primitive observes that recording and reconstitutes
        a Python exception of the same class (when importable from ``builtins``)
        so :meth:`RetrySpec.is_retryable` can filter on the original error
        type. Falls back to :class:`RuntimeError` carrying the recorded type
        name for user-defined exceptions whose class is not in builtins OR
        whose ``__init__`` rejects a single-string argument (e.g. ``OSError``
        which expects ``(errno, strerror, filename)``, or
        ``UnicodeDecodeError`` which requires 5-arg construction). Per
        ``zero-tolerance.md`` Rule 3, the constructor-failure fallback logs
        at WARN so the synthesis-divergence surfaces in operator dashboards
        instead of silently masking the original failure.
        """
        if not results:
            return None
        # Deterministic ordering: parallel-branch failures arrive in
        # node-execution order, which is non-deterministic across runs.
        # Sort by node_id so the retry-classifier sees the same failure on
        # every attempt of the same workflow shape — otherwise a transient
        # ConnectionError in branch A and a permanent ValueError in branch B
        # could flip the retry decision between attempts.
        for node_id in sorted(results.keys()):
            value = results[node_id]
            if not isinstance(value, dict) or not value.get("failed"):
                continue
            error_type_name = value.get("error_type") or "RuntimeError"
            error_message = value.get("error") or f"node {node_id!r} failed"
            # `builtins` is the canonical idiom; `__builtins__` is a
            # dual-shape attribute (module under module-import, dict under
            # exec) that triggers `zero-tolerance.md` Rule 3d (structural
            # guard on union return type). Importing `builtins` directly
            # eliminates the dual-shape branch.
            exc_cls = getattr(builtins, error_type_name, None)
            if not (isinstance(exc_cls, type) and issubclass(exc_cls, Exception)):
                exc_cls = RuntimeError
            payload = f"node {node_id!r}: {error_message}"
            try:
                return exc_cls(payload)
            except TypeError:
                # Builtin exceptions like OSError / UnicodeDecodeError require
                # multi-arg constructors and raise TypeError on single-string
                # invocation. Fall back to RuntimeError preserving the
                # original type name in the message for downstream triage.
                logger.warning(
                    "scheduler retry: failed to synthesize %s for node %r — "
                    "ctor rejected single-string arg; falling back to RuntimeError. "
                    "is_retryable filter will see RuntimeError, not %s.",
                    error_type_name,
                    node_id,
                    error_type_name,
                )
                return RuntimeError(f"[{error_type_name}] {payload}")
        return None

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
            # Canonical JSON serialization via shared helper —
            # byte-identical output across scheduler.py and durable.py
            # producer paths, which is the contract worker-side
            # `Workflow.from_dict(json.loads(blob.decode("utf-8")))`
            # depends on. See `runtime/_workflow_blob.py` for the full
            # rationale (no pickle / discriminator dispatch /
            # producer-boundary size cap).
            workflow_blob = serialize_workflow_to_blob(workflow)
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
        # Move-to-end semantics: re-submitting the same job_id refreshes
        # its LRU position so eviction targets truly stale entries.
        if event.job_id in self._fire_times:
            self._fire_times.move_to_end(event.job_id)
        self._fire_times[event.job_id] = run_times[-1]
        # LRU eviction safety net: bound at MAX_FIRE_TIMES per
        # `rules/infrastructure-sql.md` Rule 7. EVENT_JOB_EXECUTED |
        # EVENT_JOB_ERROR is the happy-path cleanup; this evicts when
        # those listeners drop fires (jobs cancelled mid-flight, listener
        # exceptions, etc.).
        while len(self._fire_times) > MAX_FIRE_TIMES:
            self._fire_times.popitem(last=False)

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
