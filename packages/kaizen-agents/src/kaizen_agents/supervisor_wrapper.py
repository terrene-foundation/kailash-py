# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""SupervisorWrapper -- composition wrapper for task delegation.

Unlike the pattern-based ``SupervisorAgent`` (which inherits ``BaseAgent``
directly and uses ``SharedMemoryPool`` for coordination), this is a
composition wrapper built on ``WrapperBase`` that can be stacked in the
canonical wrapper order::

    BaseAgent -> L3GovernedAgent -> MonitoredAgent
              -> SupervisorWrapper -> StreamingAgent

The wrapper holds a pool of worker ``BaseAgent`` instances and uses
``LLMBased`` routing to pick the best worker for each task.

Usage::

    from kaizen_agents.supervisor_wrapper import SupervisorWrapper
    from kaizen_agents.patterns.llm_routing import LLMBased

    inner = MyAgent(config=cfg)
    workers = [Worker1(cfg), Worker2(cfg)]
    supervised = SupervisorWrapper(inner, workers, routing=LLMBased())
    result = supervised.run(task="translate this document")
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import time
import uuid
from typing import Any, Optional

from kaizen.core.base_agent import BaseAgent

from kaizen_agents.patterns.llm_routing import LLMBased
from kaizen_agents.wrapper_base import WrapperBase

logger = logging.getLogger(__name__)

__all__ = [
    "SupervisorWrapper",
]


class SupervisorWrapper(WrapperBase):
    """Supervisor wrapper that delegates sub-tasks to worker agents.

    Unlike the pattern-based ``SupervisorAgent`` (which inherits
    ``BaseAgent``), this is a composition wrapper that can be stacked
    in the canonical wrapper order::

        BaseAgent -> GovernedAgent -> MonitoredAgent
                  -> SupervisorWrapper -> StreamingAgent

    Parameters
    ----------
    inner:
        The agent to wrap.  Used as the supervisor's own reasoning
        engine when no worker matches the task.
    workers:
        Pool of worker ``BaseAgent`` instances to delegate tasks to.
    routing:
        Optional ``LLMBased`` routing strategy for worker selection.
        When ``None``, a default ``LLMBased()`` instance is created.
    **kwargs:
        Passed through to ``WrapperBase.__init__``.
    """

    def __init__(
        self,
        inner: BaseAgent,
        workers: list[BaseAgent],
        *,
        routing: Optional[LLMBased] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(inner, **kwargs)
        self._workers = list(workers)
        self._routing = routing or LLMBased()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def workers(self) -> list[BaseAgent]:
        """Return the pool of worker agents."""
        return list(self._workers)

    def run(self, **inputs: Any) -> dict[str, Any]:
        """Synchronous execution -- select worker and delegate.

        Uses ``LLMBased.select_best()`` to pick a worker for the task,
        delegates to the worker, and returns the worker's result.  Falls
        back to the inner agent when no workers are available.
        """
        self._inner_called = True
        correlation_id = f"supwrap_{uuid.uuid4().hex[:8]}"
        t0 = time.monotonic()

        # Determine task text from inputs for routing
        task_text = self._extract_task_text(inputs)

        if not self._workers:
            logger.info(
                "supervisor_wrapper.no_workers",
                extra={"correlation_id": correlation_id},
            )
            return self._inner.run(**inputs)

        # Select worker via LLM routing
        worker = self._select_worker_sync(task_text, correlation_id)

        if worker is None:
            logger.info(
                "supervisor_wrapper.fallback_to_inner",
                extra={"correlation_id": correlation_id},
            )
            return self._inner.run(**inputs)

        logger.info(
            "supervisor_wrapper.delegating",
            extra={
                "correlation_id": correlation_id,
                "worker_id": getattr(worker, "agent_id", None),
                "worker_type": type(worker).__name__,
            },
        )

        result = worker.run(**inputs)

        latency_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "supervisor_wrapper.ok",
            extra={
                "correlation_id": correlation_id,
                "latency_ms": latency_ms,
            },
        )
        return result

    async def run_async(self, **inputs: Any) -> dict[str, Any]:
        """Asynchronous execution -- select worker and delegate.

        Uses ``LLMBased.select_best()`` to pick a worker for the task,
        delegates to the worker, and returns the worker's result.
        """
        self._inner_called = True
        correlation_id = f"supwrap_{uuid.uuid4().hex[:8]}"
        t0 = time.monotonic()

        task_text = self._extract_task_text(inputs)

        if not self._workers:
            logger.info(
                "supervisor_wrapper.no_workers",
                extra={"correlation_id": correlation_id},
            )
            return await self._inner.run_async(**inputs)

        # select_best is async
        worker = await self._routing.select_best(
            task_text,
            self._workers,
            correlation_id=correlation_id,
        )

        if worker is None:
            logger.info(
                "supervisor_wrapper.fallback_to_inner",
                extra={"correlation_id": correlation_id},
            )
            return await self._inner.run_async(**inputs)

        logger.info(
            "supervisor_wrapper.delegating",
            extra={
                "correlation_id": correlation_id,
                "worker_id": getattr(worker, "agent_id", None),
                "worker_type": type(worker).__name__,
            },
        )

        result = await worker.run_async(**inputs)

        latency_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "supervisor_wrapper.ok",
            extra={
                "correlation_id": correlation_id,
                "latency_ms": latency_ms,
            },
        )
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_task_text(inputs: dict[str, Any]) -> str:
        """Extract a task description string from inputs for routing.

        Checks common field names; falls back to a joined string of all
        values so the LLM always has something to reason about.
        """
        for key in ("task", "task_description", "request", "query", "message", "input"):
            val = inputs.get(key)
            if val and isinstance(val, str):
                return val
        # Fallback: join all string values
        parts = [str(v) for v in inputs.values() if v]
        return " ".join(parts) if parts else ""

    def _select_worker_sync(
        self,
        task_text: str,
        correlation_id: str,
    ) -> Optional[BaseAgent]:
        """Run async ``select_best`` from a sync context."""
        coro = self._routing.select_best(
            task_text,
            self._workers,
            correlation_id=correlation_id,
        )
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coro).result()
