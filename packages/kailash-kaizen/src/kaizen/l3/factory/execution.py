# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Process-local execution ownership; cancellation is not remote rollback."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, Literal

Executable = Callable[[], Coroutine[Any, Any, Any]]


@dataclass(frozen=True)
class ExecutionSnapshot:
    """Observed local task state, independent of lifecycle metadata."""

    instance_id: str
    execution_id: str | None
    status: Literal[
        "metadata_only",
        "not_started",
        "never_started",
        "running",
        "still_running",
        "returned",
        "failed",
        "cancelled",
    ]
    local_stopped: bool | None
    remote_effects: Literal["not_started", "unknown"]


@dataclass(frozen=True)
class TerminationReport:
    """Deepest-first observations; only local_stopped=True proves local stop."""

    entries: tuple[ExecutionSnapshot, ...]


class OwnedExecution:
    """Exact async callable and its factory-owned task.

    ``result()`` preserves results/errors and shields work from cancellation
    of an observer. Stop requests belong to AgentFactory. Threads, subprocesses,
    detached tasks and remote side effects are outside this task's ownership.
    """

    def __init__(self, instance_id: str, executable: Executable) -> None:
        self._instance_id = instance_id
        self._execution_id = str(uuid.uuid4())
        self._executable = executable
        self._task: asyncio.Task[Any] | None = None
        self._started = False
        self._finalized = False
        self._settled: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._stop_requested = False

    @property
    def instance_id(self) -> str:
        return self._instance_id

    @property
    def execution_id(self) -> str:
        return self._execution_id

    @property
    def executable(self) -> Executable:
        return self._executable

    async def result(self) -> Any:
        """Await the original result without transferring cancellation ownership."""
        if self._task is None:
            raise RuntimeError("Execution has not been dispatched")
        try:
            result = await asyncio.shield(self._task)
        except BaseException:
            if self._task.done():
                await asyncio.shield(self._settled)
            raise
        await asyncio.shield(self._settled)
        return result

    def snapshot(self) -> ExecutionSnapshot:
        """Report task completion, never infer it from AgentInstance.state."""
        task = self._task
        stopped = task is not None and task.done()
        if not stopped:
            status = (
                "still_running"
                if self._stop_requested
                else "running" if self._started else "not_started"
            )
        elif task.cancelled():
            status = "cancelled" if self._started else "never_started"
        elif task.exception() is not None:
            status = "failed"
        else:
            status = "returned"
        return ExecutionSnapshot(
            self.instance_id,
            self.execution_id,
            status,
            stopped,
            "unknown" if self._started else "not_started",
        )
