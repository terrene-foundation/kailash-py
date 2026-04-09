# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""StreamingAgent -- outermost wrapper that owns the TAOD loop and event stream.

Sits at the top of the canonical stacking order::

    BaseAgent -> L3GovernedAgent -> MonitoredAgent -> StreamingAgent

StreamingAgent wraps the full execution pipeline and emits typed
``StreamEvent`` instances as an async iterator.  It is the primary
interface for UIs and CLI tools that need incremental output.

StreamingAgent cannot be converted to a static workflow because streaming
is inherently dynamic (TAOD loop iteration count is unknown at build time).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from kaizen.core.base_agent import BaseAgent
from kaizen_agents.events import (
    BudgetExhausted,
    ErrorEvent,
    StreamBufferOverflow,
    StreamEvent,
    StreamTimeoutError,
    TextDelta,
    ToolCallEnd,
    ToolCallStart,
    TurnComplete,
)
from kaizen_agents.wrapper_base import WrapperBase

logger = logging.getLogger(__name__)

__all__ = [
    "StreamingAgent",
]

_DEFAULT_BUFFER_SIZE = 256
_DEFAULT_TIMEOUT_SECONDS = 300.0


class StreamingAgent(WrapperBase):
    """Streaming wrapper -- owns the TAOD loop and typed event emission.

    Parameters
    ----------
    inner:
        The agent to wrap (typically a ``MonitoredAgent`` or ``L3GovernedAgent``).
    buffer_size:
        Maximum number of events buffered before overflow events are emitted.
        Defaults to 256.
    timeout_seconds:
        Maximum wall-clock time for a single ``run_stream`` call.
        Defaults to 300 seconds (5 minutes).
    """

    def __init__(
        self,
        inner: BaseAgent,
        *,
        buffer_size: int = _DEFAULT_BUFFER_SIZE,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        **kwargs: Any,
    ) -> None:
        super().__init__(inner, **kwargs)
        self._buffer_size = buffer_size
        self._timeout_seconds = timeout_seconds

    def to_workflow(self) -> Any:
        """StreamingAgent cannot be converted to a static workflow.

        The TAOD loop's iteration count is unknown at build time, making
        static workflow representation impossible.
        """
        raise NotImplementedError(
            "StreamingAgent cannot be converted to a static workflow. "
            "The TAOD loop is dynamic -- use run_stream() instead."
        )

    async def run_stream(self, **kwargs: Any) -> AsyncIterator[StreamEvent]:
        """Execute with streaming events.

        Yields typed ``StreamEvent`` instances as the inner agent executes.
        The inner agent's ``run_async`` is called, and the result is
        decomposed into streaming events.

        Parameters
        ----------
        **kwargs:
            Input parameters passed to the inner agent.

        Yields
        ------
        StreamEvent
            Typed events: ``TextDelta``, ``TurnComplete``, ``BudgetExhausted``,
            ``ErrorEvent``, ``StreamBufferOverflow``.
        """
        start_time = time.monotonic()
        event_count = 0
        dropped_count = 0
        oldest_dropped: float = 0.0

        try:
            # Check timeout before starting
            elapsed = time.monotonic() - start_time
            if elapsed > self._timeout_seconds:
                raise StreamTimeoutError(
                    f"Stream timed out after {elapsed:.1f}s "
                    f"(limit: {self._timeout_seconds:.1f}s)"
                )

            # Execute the inner agent (runs the full TAOD loop via the strategy)
            self._inner_called = True
            result = await asyncio.wait_for(
                self._inner.run_async(**kwargs),
                timeout=self._timeout_seconds,
            )

            # Extract result fields
            text = ""
            tool_calls_list: list[dict[str, Any]] = []
            iterations = 1
            usage: dict[str, int] = {}
            structured: Any = None
            if isinstance(result, dict):
                # Extract text from common result keys
                for key in ("answer", "response", "text", "output", "content"):
                    if key in result and isinstance(result[key], str):
                        text = result[key]
                        break

                # Extract tool call trace if the inner agent recorded it
                raw_tool_calls = result.get("tool_calls") or result.get(
                    "tool_call_history"
                )
                if isinstance(raw_tool_calls, list):
                    tool_calls_list = [
                        tc for tc in raw_tool_calls if isinstance(tc, dict)
                    ]

                # Extract iteration count from loop metadata
                raw_iterations = result.get("iterations") or result.get("cycles")
                if isinstance(raw_iterations, int) and raw_iterations > 0:
                    iterations = raw_iterations

                raw_usage = result.get("usage", {})
                if isinstance(raw_usage, dict):
                    usage = raw_usage
                structured = result.get("structured", None)

            # Emit per-tool-call events so consumers see the Act/Observe steps
            for call in tool_calls_list:
                if event_count >= self._buffer_size:
                    dropped_count += 1
                    if oldest_dropped == 0.0:
                        oldest_dropped = time.monotonic()
                    continue
                event_count += 1
                call_id = str(call.get("id") or call.get("call_id") or "")
                tool_name = str(call.get("name") or call.get("tool_name") or "")
                yield ToolCallStart(call_id=call_id, name=tool_name)

                if event_count >= self._buffer_size:
                    dropped_count += 1
                    if oldest_dropped == 0.0:
                        oldest_dropped = time.monotonic()
                    continue
                event_count += 1
                tool_result = call.get("result") or call.get("output") or ""
                tool_error = call.get("error") or ""
                yield ToolCallEnd(
                    call_id=call_id,
                    name=tool_name,
                    result=(
                        tool_result
                        if isinstance(tool_result, str)
                        else str(tool_result)
                    ),
                    error=(
                        tool_error if isinstance(tool_error, str) else str(tool_error)
                    ),
                )

            # Emit the final text delta
            if text:
                if event_count < self._buffer_size:
                    event_count += 1
                    yield TextDelta(text=text)
                else:
                    dropped_count += 1
                    if oldest_dropped == 0.0:
                        oldest_dropped = time.monotonic()

            if event_count < self._buffer_size:
                event_count += 1
                yield TurnComplete(
                    text=text,
                    usage=usage,
                    structured=structured,
                    iterations=iterations,
                )
            else:
                dropped_count += 1
                if oldest_dropped == 0.0:
                    oldest_dropped = time.monotonic()

            # Emit buffer overflow warning if events were dropped
            if dropped_count > 0:
                yield StreamBufferOverflow(
                    dropped_count=dropped_count,
                    oldest_timestamp=oldest_dropped,
                )

        except TimeoutError:
            yield ErrorEvent(
                error=f"Stream timed out after {self._timeout_seconds:.1f}s",
                details={"timeout_seconds": self._timeout_seconds},
            )
        except StreamTimeoutError as exc:
            yield ErrorEvent(
                error=str(exc),
                details={"timeout_seconds": self._timeout_seconds},
            )
        except Exception as exc:
            # Import here to avoid circular dependency at module level
            from kaizen_agents.monitored_agent import BudgetExhaustedError

            if isinstance(exc, BudgetExhaustedError):
                yield BudgetExhausted(
                    budget_usd=exc.budget_usd,
                    consumed_usd=exc.consumed_usd,
                )
            else:
                yield ErrorEvent(
                    error=str(exc),
                    details={
                        "type": type(exc).__name__,
                    },
                )

    async def run_async(self, **inputs: Any) -> dict[str, Any]:
        """Execute and collect all events into a result dict.

        For callers that want the streaming wrapper's guarantees (timeout,
        buffer management) but prefer a single result dict.
        """
        events: list[StreamEvent] = []
        async for event in self.run_stream(**inputs):
            events.append(event)

        # Find the TurnComplete event for the result
        for event in events:
            if isinstance(event, TurnComplete):
                result: dict[str, Any] = {"text": event.text}
                if event.usage:
                    result["usage"] = event.usage
                if event.structured is not None:
                    result["structured"] = event.structured
                result["iterations"] = event.iterations
                return result

        # If no TurnComplete, check for errors
        for event in events:
            if isinstance(event, ErrorEvent):
                return {"error": event.error, "details": event.details}
            if isinstance(event, BudgetExhausted):
                return {
                    "error": "Budget exhausted",
                    "budget_usd": event.budget_usd,
                    "consumed_usd": event.consumed_usd,
                }

        return {"text": "", "events": [type(e).__name__ for e in events]}

    def run(self, **inputs: Any) -> dict[str, Any]:
        """Synchronous execution -- runs the async stream to completion."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            # Already inside an event loop; use a thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, self.run_async(**inputs))
                return future.result(timeout=self._timeout_seconds + 5)
        else:
            return asyncio.run(self.run_async(**inputs))
