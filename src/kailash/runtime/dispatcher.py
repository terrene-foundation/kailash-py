# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Dispatcher protocol for workflow scheduling.

Defines the abstract base class :class:`Dispatcher` that connects
:class:`~kailash.runtime.scheduler.WorkflowScheduler` to a task queue,
plus the canonical :class:`Task` dataclass workers consume.

When a scheduler is constructed with ``dispatch_via=<dispatcher>``, the
fire-time callback enqueues a Task instead of executing in-process.
A worker pool can then poll the dispatcher and execute the workflow
against its own runtime.

Idempotency is enforced at the queue layer via ``task_id``: a stable
hash of ``(schedule_id, planned_fire_time_iso)``. A multi-instance
scheduler that double-fires produces the SAME ``task_id`` -- the queue
adapter MUST treat the duplicate as "already enqueued, skip" without
raising to the caller.

Resume contract (informational, NOT a hard coupling):
    Workers SHOULD pass ``task_id`` as the ``idempotency_key`` to
    ``runtime.execute(...)`` when paired with a checkpoint store.
    This enables resume-from-checkpoint semantics on crash recovery.
    See ``specs/scheduling.md`` for the full contract.

Module: ``kailash.runtime.dispatcher``
Added in: v0.13.x (issue #859)
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Dict, Optional

__all__ = [
    "Dispatcher",
    "Task",
    "compute_task_id",
]


def compute_task_id(schedule_id: str, planned_fire_time: datetime) -> str:
    """Compute the stable, deterministic ``task_id`` for a fire event.

    The task_id is a SHA-256 hash of ``schedule_id || planned_fire_time_iso``,
    truncated to 32 hex chars (128 bits of collision resistance). The
    same (schedule_id, planned_fire_time) pair ALWAYS produces the same
    task_id; this is what makes queue-layer dedup work for multi-instance
    scheduler double-fire scenarios.

    Parameters
    ----------
    schedule_id:
        The scheduler-assigned schedule identifier (e.g. "sched-abc123").
    planned_fire_time:
        The cron/interval/once trigger's planned fire time. MUST be the
        scheduler-computed fire time, NOT the wall-clock time when
        the callback ran (those drift under load).

    Returns
    -------
    str
        A 32-character lowercase hex string. Suitable for use as a
        PRIMARY KEY in the task queue table.

    Notes
    -----
    The ISO 8601 representation is used because it's the canonical
    cross-language wire format and preserves microsecond precision
    when present. Naive datetimes (without tzinfo) and aware datetimes
    in different timezones produce different task_ids -- callers MUST
    be consistent about timezone awareness within a single schedule.
    """
    payload = f"{schedule_id}|{planned_fire_time.isoformat()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


@dataclass
class Task:
    """A scheduled workflow task ready for dispatch.

    The ``Task`` is the unit of work passed from the scheduler to the
    dispatcher and from the dispatcher to a worker. It carries enough
    context for the worker to execute the workflow and ack/nack the
    result, including the deterministic ``task_id`` used for both
    queue-layer dedup AND (informationally) for runtime-side
    idempotency on the worker.

    Attributes
    ----------
    task_id:
        Stable hash of ``(schedule_id, planned_fire_time_iso)``.
        Used as the queue's PRIMARY KEY for idempotent enqueue
        AND as the canonical ``idempotency_key`` workers SHOULD
        pass to ``runtime.execute(...)`` when paired with a
        checkpoint store.
    schedule_id:
        The scheduler-assigned schedule identifier.
    workflow_blob:
        The serialized workflow (pickled WorkflowBuilder or its
        ``.build()`` output). Workers deserialize this and execute.
    planned_fire_time:
        The trigger's intended fire time (UTC ISO 8601 string).
    queue_name:
        Logical queue name for routing (default ``"default"``).
    kwargs:
        Additional kwargs forwarded to ``runtime.execute(...)``.
    """

    task_id: str
    schedule_id: str
    workflow_blob: bytes
    planned_fire_time: str
    queue_name: str = "default"
    kwargs: Dict[str, Any] = field(default_factory=dict)


class Dispatcher(ABC):
    """Abstract base class for workflow dispatchers.

    A Dispatcher routes a fire-time :class:`Task` to a queue (or other
    transport) so that one or more workers can poll, execute, and
    acknowledge. The contract is intentionally minimal: enqueue is
    idempotent on ``task_id``; poll yields claimed tasks one at a
    time; ack marks a task complete; nack returns it for retry or
    dead-letters it.

    Implementers MUST:

    1. Make :meth:`enqueue` idempotent on ``task_id`` -- a duplicate
       enqueue with the same ``task_id`` MUST be a silent no-op
       (no exception to the caller).
    2. Make :meth:`poll` atomic -- two concurrent workers polling the
       same queue MUST NOT receive the same task.
    3. On :meth:`nack`, decide based on attempt count whether to
       requeue (transient failure) or dead-letter (max attempts
       exceeded).

    Reference implementation: :class:`~kailash.infrastructure.task_queue.SQLTaskQueue`.
    """

    @abstractmethod
    async def enqueue(self, task: Task) -> None:
        """Add a task to the queue.

        MUST be idempotent on ``task.task_id``. Duplicate enqueue with
        the same task_id is a silent no-op -- the dispatcher catches
        the PRIMARY KEY constraint violation and returns success.

        Parameters
        ----------
        task:
            The task to enqueue.

        Raises
        ------
        Exception
            On any non-duplicate failure (connectivity, serialization).
            Callers (e.g. ``WorkflowScheduler.fire``) MUST log this at
            ERROR with ``schedule_id`` + ``task_id`` and propagate or
            inline-retry per their misfire policy.
        """

    @abstractmethod
    def poll(self, queue_name: str = "default") -> AsyncIterator[Task]:
        """Yield tasks claimed from the queue, one at a time.

        Each yielded task is in ``processing`` status and locked to the
        polling worker. The worker MUST eventually call :meth:`ack`
        (success) or :meth:`nack` (failure) for each task to release
        the lock.

        Parameters
        ----------
        queue_name:
            Queue to poll. Defaults to ``"default"``.

        Returns
        -------
        AsyncIterator[Task]
            Async iterator yielding claimed tasks. Implementations
            MAY block briefly between yields when the queue is empty,
            or return an async generator that completes once the
            worker is shut down.
        """

    @abstractmethod
    async def ack(self, task_id: str) -> None:
        """Mark a task as completed.

        Parameters
        ----------
        task_id:
            The task to ack.
        """

    @abstractmethod
    async def nack(self, task_id: str, *, reason: str) -> None:
        """Mark a task as failed.

        If the task has exceeded its max_attempts, the dispatcher
        MUST move it to dead-letter status. Otherwise, the dispatcher
        MUST requeue the task for another attempt.

        Parameters
        ----------
        task_id:
            The task that failed.
        reason:
            A short error description for diagnostics. MUST NOT
            contain secrets or PII (callers' responsibility per
            ``rules/security.md`` § "No secrets in logs").
        """
