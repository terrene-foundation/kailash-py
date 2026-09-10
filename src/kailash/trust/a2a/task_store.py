# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
In-memory task store for the A2A 1.0 task lifecycle.

``SendMessage`` creates tasks; ``GetTask`` reads them back. Something has to
hold them in between, and it has to be bounded — an unbounded task map in a
long-lived agent process is a memory-exhaustion vector
(``trust-plane-security.md`` MUST-4).

Eviction is oldest-first by insertion order, and only ever evicts TERMINAL
tasks while any non-terminal task remains: dropping a task that is still
running would make ``GetTask`` report ``TASK_NOT_FOUND`` for live work, which
a client cannot distinguish from a task that never existed. When every task is
non-terminal the oldest is evicted anyway rather than growing without bound —
the bound is the invariant that must hold, and the eviction is logged at WARN
so the capacity problem is visible rather than silent.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from typing import Optional

from kailash.trust.a2a.messaging import Task

logger = logging.getLogger(__name__)

__all__ = ["InMemoryTaskStore", "DEFAULT_MAX_TASKS"]

#: Default capacity. Chosen to match the bounded-collection floor used across
#: the trust plane (``trust-plane-security.md`` MUST-4).
DEFAULT_MAX_TASKS = 10_000


class InMemoryTaskStore:
    """Bounded, thread-safe task store keyed by task id.

    Not durable. An agent that must survive restart supplies its own store
    with the same ``get`` / ``put`` surface.
    """

    def __init__(self, max_tasks: int = DEFAULT_MAX_TASKS):
        if max_tasks < 1:
            raise ValueError(f"max_tasks must be >= 1 (got {max_tasks})")
        self._max_tasks = max_tasks
        self._tasks: "OrderedDict[str, Task]" = OrderedDict()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._tasks)

    @property
    def max_tasks(self) -> int:
        return self._max_tasks

    def get(self, task_id: str) -> Optional[Task]:
        """Return the task, or ``None`` if it is not held."""
        with self._lock:
            return self._tasks.get(task_id)

    def put(self, task: Task) -> None:
        """Store a task, replacing any existing entry, evicting if over capacity."""
        with self._lock:
            if task.id in self._tasks:
                # Replace in place; keep original insertion position so an
                # actively-updated task does not become immortal.
                self._tasks[task.id] = task
                return
            self._tasks[task.id] = task
            while len(self._tasks) > self._max_tasks:
                self._evict_one_locked()

    def _evict_one_locked(self) -> None:
        """Evict the oldest terminal task; fall back to the oldest task."""
        for task_id, held in self._tasks.items():
            if held.is_terminal:
                del self._tasks[task_id]
                logger.debug(
                    "a2a.task_store.evict",
                    extra={"task_id": task_id, "reason": "capacity", "terminal": True},
                )
                return

        task_id, _ = self._tasks.popitem(last=False)
        logger.warning(
            "a2a.task_store.evict_non_terminal",
            extra={
                "task_id": task_id,
                "reason": "capacity",
                "terminal": False,
                "max_tasks": self._max_tasks,
            },
        )
