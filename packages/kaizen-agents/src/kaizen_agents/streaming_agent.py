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
from typing import Any, AsyncIterator, Dict, Optional

from kaizen.core.base_agent import BaseAgent
from kaizen_agents.events import (
    BudgetExhausted,
    ErrorEvent,
    StreamBufferOverflow,
    StreamEvent,
    StreamTimeoutError,
    TextDelta,
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

            # Execute the inner agent
            self._inner_called = True
            result = await asyncio.wait_for(
                self._inner.run_async(**kwargs),
                timeout=self._timeout_seconds,
            )

            # Emit text content as a delta if present
            text = ""
            if isinstance(result, dict):
                # Extract text from common result keys
                for key in ("answer", "response", "text", "output", "content"):
                    if key in result and isinstance(result[key], str):
                        text = result[key]
                        break

            if text:
                if event_count < self._buffer_size:
                    event_count += 1
                    yield TextDelta(text=text)
                else:
                    dropped_count += 1
                    if oldest_dropped == 0.0:
                        oldest_dropped = time.monotonic()

            # Emit turn complete
            usage = {}
            structured = None
            if isinstance(result, dict):
                usage = result.get("usage", {})
                if not isinstance(usage, dict):
                    usage = {}
                structured = result.get("structured", None)

            if event_count < self._buffer_size:
                event_count += 1
                yield TurnComplete(
                    text=text,
                    usage=usage,
                    structured=structured,
                    iterations=1,
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

        except asyncio.TimeoutError:
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

    async def run_async(self, **inputs: Any) -> Dict[str, Any]:
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
                result: Dict[str, Any] = {"text": event.text}
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

    def run(self, **inputs: Any) -> Dict[str, Any]:
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
