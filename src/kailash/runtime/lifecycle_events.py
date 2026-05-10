# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Typed lifecycle event payloads for Worker + WorkflowScheduler hooks.

Issue #914: handlers receive a typed event payload, not a raw dict, so callers
can route task / job lifecycle events to external alerters (Slack, Discord,
Sentry, custom HTTP) without parsing dict shapes that drift across releases.

Public API
----------

- :class:`TaskEvent` — payload for ``Worker.on_task_*`` hooks.
- :class:`JobEvent` — payload for ``WorkflowScheduler.on_job_*`` hooks.
- :data:`TaskEventHandler` — sync OR async callable accepting a :class:`TaskEvent`.
- :data:`JobEventHandler` — sync callable accepting a :class:`JobEvent`.

The dataclasses are ``frozen=True`` so handlers cannot mutate the event in
ways that affect later handlers in the dispatch chain.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Awaitable, Callable, Optional, Union

__all__ = [
    "TaskEvent",
    "JobEvent",
    "TaskEventHandler",
    "JobEventHandler",
]


@dataclass(frozen=True)
class TaskEvent:
    """Lifecycle event for a distributed-runtime task.

    Attributes:
        task_id: Unique identifier of the task (== the workflow run_id).
        workflow_name: ``Workflow.name`` extracted from the serialized
            ``workflow_data`` payload. ``None`` when the producer did not
            populate ``workflow_data["name"]``.
        attempt: Current delivery attempt count (1-indexed at first run).
        max_attempts: Maximum delivery attempts before dead-lettering.
        worker_id: Identifier of the :class:`Worker` that processed the task.
        elapsed_ms: Wall-clock duration in milliseconds. ``None`` for
            ``on_task_prerun`` (the task has not run yet).
        exception: The exception that caused the task to fail or retry.
            ``None`` for success / prerun / postrun events that did not
            observe a failure.
        queue_name: Logical queue the task was dequeued from (issue #911
            Shard 2). Populated from ``TaskMessage.queue_name``; defaults
            to ``"default"`` for back-compat with single-queue Workers
            and pre-#911 producers whose messages omit the field.
        timestamp: Unix timestamp the event was constructed.
    """

    task_id: str
    workflow_name: Optional[str]
    attempt: int
    max_attempts: int
    worker_id: str
    elapsed_ms: Optional[float] = None
    exception: Optional[BaseException] = None
    queue_name: str = "default"
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class JobEvent:
    """Lifecycle event for a :class:`WorkflowScheduler` job.

    Attributes:
        schedule_id: Unique identifier of the schedule (== APScheduler ``job_id``).
        schedule_name: Human-readable schedule name supplied by the caller.
            ``None`` when the schedule was registered without a ``name``.
        scheduled_run_time: The trigger fire instant the event was produced
            for. ``None`` when APScheduler did not provide one (e.g. the
            ``EVENT_JOB_MISSED`` event for a missed schedule may carry only
            the missed-time field on some APScheduler builds; consumers
            tolerate ``None``).
        exception: The exception that caused ``EVENT_JOB_ERROR``. ``None``
            on success / missed events.
        timestamp: Unix timestamp the event was constructed.
    """

    schedule_id: str
    schedule_name: Optional[str]
    scheduled_run_time: Optional[datetime]
    exception: Optional[BaseException] = None
    timestamp: float = field(default_factory=time.time)


# Sync OR async — Worker awaits coroutine handlers; sync handlers run inline.
TaskEventHandler = Callable[[TaskEvent], Union[None, Awaitable[None]]]

# Sync only — APScheduler listener context is synchronous; async handlers
# would require event-loop wrangling per `patterns.md` § Paired Public Surface.
JobEventHandler = Callable[[JobEvent], None]
