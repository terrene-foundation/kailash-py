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

Streaming is driven by the four-axis :class:`kaizen.llm.client.LlmClient`
(``client.stream(...)``).  The innermost agent's config (``model`` /
``llm_provider`` / ``api_key`` / ``base_url`` / ``ungoverned``) is resolved to
an ``LlmDeployment`` via ``resolve_deployment_for`` — the SAME path
``BaseAgent._simple_execute_async`` uses for ``complete()`` — and tokens are
streamed incrementally from the LLM.  The batch fallback
(:meth:`_stream_batch_fallback`) fires ONLY in the genuine "no model / no
four-axis deployment for the inner provider" case; it logs at WARN and is never
the default path when a client can be built (#1720 Wave-2b streaming cutover).
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


def _innermost_agent(agent: BaseAgent) -> BaseAgent:
    """Walk the wrapper stack to the innermost non-wrapper agent."""
    current = agent
    while isinstance(current, WrapperBase):
        current = current._inner
    return current


def _resolve_streaming_client(agent: BaseAgent) -> Any | None:
    """Walk to the innermost agent and build a four-axis ``LlmClient`` from
    its config.

    The four-axis ``LlmClient`` is NOT a ``StreamingProvider`` — it is the
    single provider-abstraction surface for real token streaming
    (``client.stream(...)``).  The innermost agent's config
    (``model`` / ``llm_provider`` / ``api_key`` / ``base_url`` / ``ungoverned``)
    is resolved to an ``LlmDeployment`` via ``resolve_deployment_for`` — the
    SAME chokepoint ``BaseAgent._simple_execute_async`` uses for ``complete()``
    — then wrapped in an ``LlmClient`` honoring the #1779 governance posture
    (``ungoverned`` passed through UNCHANGED; never forced to ``True``).

    Returns the ``LlmClient`` when one can be built, or ``None`` in the genuine
    "no model / no four-axis deployment for the inner provider" case (the ONLY
    case that routes ``run_stream`` to the batch fallback).  A
    ``governance_required`` refusal (``UngovernedEgressRefused``) is NEVER
    swallowed into a silent batch fallback — it propagates so the caller sees
    the real refusal (``rules/zero-tolerance.md`` Rule 3).
    """
    innermost = _innermost_agent(agent)
    config = innermost.config
    model = getattr(config, "model", None) if config else None
    if not model:
        return None

    provider = getattr(config, "llm_provider", None) or "openai"

    from kaizen.llm.client import LlmClient
    from kaizen.llm.deployment_resolver import (
        UnsupportedDeploymentProvider,
        resolve_deployment_for,
    )

    try:
        deployment = resolve_deployment_for(
            provider,
            model=model,
            api_key=getattr(config, "api_key", None),
            base_url=getattr(config, "base_url", None),
        )
    except UnsupportedDeploymentProvider as exc:
        # A KNOWN provider with no confirmed four-axis wire (e.g.
        # azure_ai_foundry). Not a stub, not a governance refusal — a genuine
        # "cannot build a streaming client" case; fall back to batch (WARN).
        logger.warning(
            "streaming_agent.client_resolution_unsupported",
            extra={"model": model, "provider": provider, "error": str(exc)},
        )
        return None

    if deployment is None:
        # provider unmapped, or a required api_key/base_url is missing — the
        # resolver already logged the reason at DEBUG. Batch fallback.
        return None

    # Honor the agent's #1779 governance opt-out at the four-axis chokepoint.
    # A governance_required refusal raised HERE propagates (never converted to
    # a silent batch fallback).
    return LlmClient.from_deployment(
        deployment, ungoverned=getattr(config, "ungoverned", False)
    )


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
    http_client:
        Optional pre-constructed ``LlmHttpClient``-compatible transport
        threaded into ``LlmClient.stream(http_client=...)``.  Advanced-caller /
        test affordance mirroring ``LlmClient``'s own ``http_client=`` seam:
        share an HTTP pool across calls, or inject the deterministic offline
        ``kaizen.llm.testing.MockLlmHttpClient`` for a real streaming test with
        zero network I/O.  ``None`` (default) lets ``LlmClient`` construct and
        close its own SSRF-safe transport per stream.
    """

    def __init__(
        self,
        inner: BaseAgent,
        *,
        buffer_size: int = _DEFAULT_BUFFER_SIZE,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        http_client: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(inner, **kwargs)
        self._buffer_size = buffer_size
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client

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

        If a four-axis ``LlmClient`` can be built from the inner agent's config
        (``_resolve_streaming_client``), tokens are streamed incrementally via
        ``client.stream()``.  Otherwise falls back to batch execution and
        synthesises events from the result.

        Parameters
        ----------
        **kwargs:
            Input parameters passed to the inner agent.

        Yields
        ------
        StreamEvent
            Typed events: ``TextDelta``, ``TurnComplete``, ``BudgetExhausted``,
            ``ErrorEvent``, ``StreamBufferOverflow``, ``ToolCallStart``,
            ``ToolCallEnd``.
        """
        client = _resolve_streaming_client(self._inner)
        if client is not None:
            logger.info(
                "streaming_agent.stream_via_llmclient",
                extra={"path": "streaming"},
            )
            async for event in self._stream_with_client(client, **kwargs):
                yield event
        else:
            logger.warning(
                "streaming_agent.fallback_batch",
                extra={
                    "reason": "no model configured, or no four-axis deployment "
                    "for the inner agent's provider",
                    "path": "batch_fallback",
                },
            )
            async for event in self._stream_batch_fallback(**kwargs):
                yield event

    async def _stream_with_client(
        self, client: Any, **kwargs: Any
    ) -> AsyncIterator[StreamEvent]:
        """Real streaming path — yields events as tokens arrive from the LLM
        via the four-axis ``LlmClient.stream()``.

        Maps each parsed stream chunk dict (the shaper's ``parse_response``
        output: ``{text, usage, stop_reason, model, tool_calls?}``) onto typed
        ``StreamEvent`` instances, preserving the per-event timeout check, the
        buffer-overflow accounting, ``accumulated_text``, and ``usage``
        bookkeeping of the pre-cutover provider path. Tool-call de-duplication
        uses ``emitted_tool_call_ids``.
        """
        start_time = time.monotonic()
        event_count = 0
        dropped_count = 0
        oldest_dropped: float = 0.0
        accumulated_text = ""
        iterations = 1
        usage: dict[str, int] = {}
        emitted_tool_call_ids: set[str] = set()

        # Build the messages list from kwargs for the client
        messages = self._build_messages(**kwargs)

        # Resolve model / sampling config from the innermost agent. The
        # four-axis client takes temperature / max_tokens as direct kwargs
        # (not a legacy generation_config dict).
        innermost = _innermost_agent(self._inner)
        config = innermost.config
        stream_kwargs: dict[str, Any] = {}
        if config and getattr(config, "model", None):
            stream_kwargs["model"] = config.model
        if config and getattr(config, "temperature", None) is not None:
            stream_kwargs["temperature"] = config.temperature
        if config and getattr(config, "max_tokens", None):
            stream_kwargs["max_tokens"] = config.max_tokens
        if self._http_client is not None:
            stream_kwargs["http_client"] = self._http_client

        try:
            self._inner_called = True

            # Iterate the client's parsed-chunk async iterator with per-event
            # timeout checks. Each chunk is the shaper's parse of one wire line.
            async for chunk in client.stream(messages, **stream_kwargs):
                elapsed = time.monotonic() - start_time
                if elapsed > self._timeout_seconds:
                    raise StreamTimeoutError(
                        f"Stream timed out after {elapsed:.1f}s "
                        f"(limit: {self._timeout_seconds:.1f}s)"
                    )
                if not isinstance(chunk, dict):
                    continue

                # Token text: each streaming chunk's `text` is the incremental
                # delta (OpenAI `delta.content` / Ollama per-line content); on
                # the streaming.enabled=False buffered path it is the full text.
                delta_text = chunk.get("text") or ""
                if delta_text:
                    accumulated_text += delta_text
                    if event_count < self._buffer_size:
                        event_count += 1
                        yield TextDelta(text=delta_text)
                    else:
                        dropped_count += 1
                        if oldest_dropped == 0.0:
                            oldest_dropped = time.monotonic()

                # Usage: the final chunk carries it; retain the latest chunk
                # whose usage has any non-None value.
                chunk_usage = chunk.get("usage")
                if isinstance(chunk_usage, dict) and any(
                    v is not None for v in chunk_usage.values()
                ):
                    usage = {k: v for k, v in chunk_usage.items() if v is not None}

                # Tool calls: the canonical shape
                # [{"id", "type": "function", "function": {"name", "arguments"}}].
                # Emit ToolCallStart/End once per NEW call id with a resolved
                # name (dedupes partial streaming fragments AND the single
                # full list on the buffered-complete path).
                chunk_tool_calls = chunk.get("tool_calls")
                if isinstance(chunk_tool_calls, list):
                    for tc in chunk_tool_calls:
                        if not isinstance(tc, dict):
                            continue
                        call_id = str(tc.get("id", ""))
                        fn = tc.get("function", {})
                        tool_name = (
                            str(fn.get("name", "")) if isinstance(fn, dict) else ""
                        )
                        if not tool_name or call_id in emitted_tool_call_ids:
                            continue
                        emitted_tool_call_ids.add(call_id)
                        if event_count < self._buffer_size:
                            event_count += 1
                            yield ToolCallStart(call_id=call_id, name=tool_name)
                        else:
                            dropped_count += 1
                            if oldest_dropped == 0.0:
                                oldest_dropped = time.monotonic()
                        if event_count < self._buffer_size:
                            event_count += 1
                            yield ToolCallEnd(
                                call_id=call_id,
                                name=tool_name,
                                result="",
                                error="",
                            )
                        else:
                            dropped_count += 1
                            if oldest_dropped == 0.0:
                                oldest_dropped = time.monotonic()

            # Emit turn complete
            if event_count < self._buffer_size:
                event_count += 1
                yield TurnComplete(
                    text=accumulated_text,
                    usage=usage,
                    iterations=iterations,
                )
            else:
                dropped_count += 1
                if oldest_dropped == 0.0:
                    oldest_dropped = time.monotonic()

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
            # #1779: a lazy-re-check governance refusal (posture flipped ON
            # after client construction) propagates UNWRAPPED — never softened
            # into an ErrorEvent that hides the refusal (mirrors
            # BaseAgent._simple_execute_async).
            from kailash.trust.pact import UngovernedEgressRefused

            if isinstance(exc, UngovernedEgressRefused):
                raise

            from kaizen_agents.monitored_agent import BudgetExhaustedError

            if isinstance(exc, BudgetExhaustedError):
                yield BudgetExhausted(
                    budget_usd=exc.budget_usd,
                    consumed_usd=exc.consumed_usd,
                )
            else:
                # Sink-side credential scrub (parity with the batch path's
                # sanitize_provider_error at base_agent._simple_execute_async):
                # a raw httpx.HTTPError renders request.url, so a base_url with
                # embedded userinfo would otherwise reach the user-facing stream.
                # Lazy import — module-scope would re-pull the kaizen.nodes.ai
                # tree the #1720 Wave-2b circular-import fix removed.
                from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error

                yield ErrorEvent(
                    error=sanitize_provider_error(exc, "stream"),
                    details={"type": type(exc).__name__},
                )

    def _build_messages(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Build a messages list from the kwargs for direct provider streaming.

        If the inner agent has a system prompt or signature, prepend it.
        Then use the first string kwarg as the user message.
        """
        messages: list[dict[str, Any]] = []

        # Try to get a system prompt from the innermost agent
        innermost = self._inner
        while isinstance(innermost, WrapperBase):
            innermost = innermost._inner
        system_prompt = getattr(innermost, "system_prompt", None) or getattr(
            innermost, "_system_prompt", None
        )
        if system_prompt:
            messages.append({"role": "system", "content": str(system_prompt)})

        # Find user content from kwargs
        user_content = ""
        for key in ("prompt", "message", "query", "input", "text", "question"):
            if key in kwargs and isinstance(kwargs[key], str):
                user_content = kwargs[key]
                break
        if not user_content:
            # Fall back to joining all string kwargs
            parts = [str(v) for v in kwargs.values() if isinstance(v, str)]
            user_content = " ".join(parts) if parts else ""

        if user_content:
            messages.append({"role": "user", "content": user_content})

        return messages

    async def _stream_batch_fallback(self, **kwargs: Any) -> AsyncIterator[StreamEvent]:
        """Batch fallback — calls inner agent and synthesises events.

        Used when the provider does not implement StreamingProvider.
        """
        start_time = time.monotonic()
        event_count = 0
        dropped_count = 0
        oldest_dropped: float = 0.0

        try:
            elapsed = time.monotonic() - start_time
            if elapsed > self._timeout_seconds:
                raise StreamTimeoutError(
                    f"Stream timed out after {elapsed:.1f}s "
                    f"(limit: {self._timeout_seconds:.1f}s)"
                )

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
                for key in ("answer", "response", "text", "output", "content"):
                    if key in result and isinstance(result[key], str):
                        text = result[key]
                        break

                raw_tool_calls = result.get("tool_calls") or result.get(
                    "tool_call_history"
                )
                if isinstance(raw_tool_calls, list):
                    tool_calls_list = [
                        tc for tc in raw_tool_calls if isinstance(tc, dict)
                    ]

                raw_iterations = result.get("iterations") or result.get("cycles")
                if isinstance(raw_iterations, int) and raw_iterations > 0:
                    iterations = raw_iterations

                raw_usage = result.get("usage", {})
                if isinstance(raw_usage, dict):
                    usage = raw_usage
                structured = result.get("structured", None)

            # Emit per-tool-call events
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
            from kaizen_agents.monitored_agent import BudgetExhaustedError

            if isinstance(exc, BudgetExhaustedError):
                yield BudgetExhausted(
                    budget_usd=exc.budget_usd,
                    consumed_usd=exc.consumed_usd,
                )
            else:
                # Sink-side credential scrub (parity with the batch path's
                # sanitize_provider_error at base_agent._simple_execute_async):
                # a raw httpx.HTTPError renders request.url, so a base_url with
                # embedded userinfo would otherwise reach the user-facing stream.
                # Lazy import — module-scope would re-pull the kaizen.nodes.ai
                # tree the #1720 Wave-2b circular-import fix removed.
                from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error

                yield ErrorEvent(
                    error=sanitize_provider_error(exc, "stream"),
                    details={"type": type(exc).__name__},
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
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, self.run_async(**inputs))
                return future.result(timeout=self._timeout_seconds + 5)
        else:
            return asyncio.run(self.run_async(**inputs))
