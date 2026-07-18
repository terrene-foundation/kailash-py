# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for StreamingAgent wrapper — streaming events, timeout, buffer.

Covers:
- Batch fallback emits correct event sequence
- Timeout enforcement
- Buffer overflow detection
- Budget exhaustion propagation
- to_workflow() raises NotImplementedError
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen_agents.events import (
    BudgetExhausted,
    ErrorEvent,
    StreamBufferOverflow,
    TextDelta,
    TurnComplete,
)
from kaizen_agents.streaming_agent import (
    StreamingAgent,
    _resolve_streaming_client,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _BatchAgent(BaseAgent):
    """Agent that returns a canned result (no streaming provider)."""

    def __init__(self, result: dict[str, Any] | None = None, **kw: Any) -> None:
        config = BaseAgentConfig()
        super().__init__(config=config, mcp_servers=[], **kw)
        self._result = result or {"answer": "hello world"}

    def run(self, **inputs: Any) -> dict[str, Any]:
        return self._result

    async def run_async(self, **inputs: Any) -> dict[str, Any]:
        return self._result


class _SlowAgent(BaseAgent):
    """Agent that sleeps longer than the timeout."""

    def __init__(self, delay: float = 10.0) -> None:
        config = BaseAgentConfig()
        super().__init__(config=config, mcp_servers=[])
        self._delay = delay

    def run(self, **inputs: Any) -> dict[str, Any]:
        return {}

    async def run_async(self, **inputs: Any) -> dict[str, Any]:
        await asyncio.sleep(self._delay)
        return {"answer": "too late"}


class _BudgetExplodingAgent(BaseAgent):
    """Agent that raises BudgetExhaustedError."""

    def __init__(self) -> None:
        config = BaseAgentConfig()
        super().__init__(config=config, mcp_servers=[])

    def run(self, **inputs: Any) -> dict[str, Any]:
        raise RuntimeError("sync not supported")

    async def run_async(self, **inputs: Any) -> dict[str, Any]:
        from kaizen_agents.monitored_agent import BudgetExhaustedError

        raise BudgetExhaustedError(budget_usd=1.0, consumed_usd=1.5)


# ---------------------------------------------------------------------------
# Basic event emission (batch fallback path)
# ---------------------------------------------------------------------------


class TestBatchFallback:
    async def test_emits_text_delta_and_turn_complete(self) -> None:
        agent = _BatchAgent(result={"answer": "hello"})
        streaming = StreamingAgent(agent, mcp_servers=[])

        events = []
        async for event in streaming.run_stream(prompt="test"):
            events.append(event)

        types = [type(e).__name__ for e in events]
        assert "TextDelta" in types
        assert "TurnComplete" in types

        text_delta = next(e for e in events if isinstance(e, TextDelta))
        assert text_delta.text == "hello"

        turn = next(e for e in events if isinstance(e, TurnComplete))
        assert turn.text == "hello"

    async def test_emits_turn_complete_with_usage(self) -> None:
        agent = _BatchAgent(
            result={
                "answer": "ok",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
        )
        streaming = StreamingAgent(agent, mcp_servers=[])

        events = []
        async for event in streaming.run_stream(prompt="test"):
            events.append(event)

        turn = next(e for e in events if isinstance(e, TurnComplete))
        assert turn.usage["prompt_tokens"] == 10

    async def test_empty_result_still_emits_turn_complete(self) -> None:
        agent = _BatchAgent(result={})
        streaming = StreamingAgent(agent, mcp_servers=[])

        events = []
        async for event in streaming.run_stream(prompt="test"):
            events.append(event)

        assert any(isinstance(e, TurnComplete) for e in events)

    async def test_run_async_collects_events(self) -> None:
        agent = _BatchAgent(result={"answer": "collected"})
        streaming = StreamingAgent(agent, mcp_servers=[])

        result = await streaming.run_async(prompt="test")
        assert result["text"] == "collected"


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


class TestTimeout:
    async def test_timeout_emits_error_event(self) -> None:
        agent = _SlowAgent(delay=10.0)
        streaming = StreamingAgent(agent, timeout_seconds=0.1, mcp_servers=[])

        events = []
        async for event in streaming.run_stream(prompt="test"):
            events.append(event)

        assert any(isinstance(e, ErrorEvent) for e in events)
        error = next(e for e in events if isinstance(e, ErrorEvent))
        assert "timed out" in error.error.lower()


# ---------------------------------------------------------------------------
# Buffer overflow
# ---------------------------------------------------------------------------


class TestBufferOverflow:
    async def test_small_buffer_emits_overflow(self) -> None:
        # Result with many tool calls to overflow a tiny buffer
        tool_calls = [{"id": f"call_{i}", "name": f"tool_{i}"} for i in range(10)]
        agent = _BatchAgent(result={"answer": "done", "tool_calls": tool_calls})
        streaming = StreamingAgent(agent, buffer_size=5, mcp_servers=[])

        events = []
        async for event in streaming.run_stream(prompt="test"):
            events.append(event)

        assert any(isinstance(e, StreamBufferOverflow) for e in events)


# ---------------------------------------------------------------------------
# Budget exhaustion
# ---------------------------------------------------------------------------


class TestBudgetExhaustion:
    async def test_budget_exhausted_propagates(self) -> None:
        agent = _BudgetExplodingAgent()
        streaming = StreamingAgent(agent, mcp_servers=[])

        events = []
        async for event in streaming.run_stream(prompt="test"):
            events.append(event)

        assert any(isinstance(e, BudgetExhausted) for e in events)
        budget_event = next(e for e in events if isinstance(e, BudgetExhausted))
        assert budget_event.budget_usd == 1.0
        assert budget_event.consumed_usd == 1.5


# ---------------------------------------------------------------------------
# to_workflow
# ---------------------------------------------------------------------------


class TestToWorkflow:
    def test_raises_not_implemented(self) -> None:
        agent = _BatchAgent()
        streaming = StreamingAgent(agent, mcp_servers=[])
        with pytest.raises(NotImplementedError, match="TAOD loop is dynamic"):
            streaming.to_workflow()


# ---------------------------------------------------------------------------
# Four-axis LlmClient streaming cutover (#1720 Wave-2b)
# ---------------------------------------------------------------------------


class _ConfiguredAgent(BaseAgent):
    """Inner agent with a config that resolves to an OpenAiChat deployment.

    ``llm_provider="openai"`` + a model + a (placeholder, non-secret) api_key
    is exactly what ``_resolve_streaming_client`` needs to build a four-axis
    ``LlmClient`` via ``resolve_deployment_for``. The model literal follows the
    established ``mock-model`` test convention; the transport is the offline
    deterministic ``MockLlmHttpClient`` so no network I/O and no real key are
    involved.
    """

    def __init__(self, **kw: Any) -> None:
        config = BaseAgentConfig(
            llm_provider="openai",
            model="mock-model",
            api_key="sk-test-not-a-real-key",
            temperature=0.0,
        )
        super().__init__(config=config, mcp_servers=[], **kw)

    def run(self, **inputs: Any) -> dict[str, Any]:
        raise RuntimeError("streaming path should not call run()")

    async def run_async(self, **inputs: Any) -> dict[str, Any]:
        raise RuntimeError("streaming path should not call run_async()")


def _mock_transport() -> Any:
    from kaizen.llm.testing import MockLlmHttpClient

    return MockLlmHttpClient()


class TestFourAxisStreaming:
    def test_resolve_streaming_client_none_without_model(self) -> None:
        # BaseAgentConfig() has no model -> no client -> batch fallback path.
        agent = _BatchAgent()
        assert _resolve_streaming_client(agent) is None

    def test_resolve_streaming_client_builds_llmclient(self) -> None:
        from kaizen.llm.client import LlmClient

        agent = _ConfiguredAgent()
        client = _resolve_streaming_client(agent)
        assert isinstance(client, LlmClient)
        # The deployment is a real OpenAiChat wire (NOT the mock preset) — the
        # cutover goes through the production resolution path.
        assert client.deployment is not None
        assert client.deployment.preset_name != "mock"

    async def test_streams_tokens_incrementally(self) -> None:
        # "step by step" triggers the multi-line reasoning response in the
        # deterministic transport, split into many whitespace-preserving
        # pieces -> many TextDelta events (real streaming, not one blob).
        agent = _ConfiguredAgent()
        streaming = StreamingAgent(agent, mcp_servers=[], http_client=_mock_transport())

        events = []
        async for event in streaming.run_stream(
            prompt="explain your reasoning step by step"
        ):
            events.append(event)

        text_deltas = [e for e in events if isinstance(e, TextDelta)]
        # Real token streaming: MANY deltas, not a single accumulated blob.
        assert len(text_deltas) > 1

        turn = next(e for e in events if isinstance(e, TurnComplete))
        # Concatenation of every delta reconstructs the full turn text.
        assert "".join(d.text for d in text_deltas) == turn.text
        assert turn.text != ""
        # The final chunk carried usage through to TurnComplete.
        assert turn.usage.get("total_tokens")

    async def test_stream_via_client_sets_inner_called(self) -> None:
        agent = _ConfiguredAgent()
        streaming = StreamingAgent(agent, mcp_servers=[], http_client=_mock_transport())
        events = [e async for e in streaming.run_stream(prompt="hello there")]
        assert any(isinstance(e, TurnComplete) for e in events)
        assert getattr(streaming, "_inner_called", False) is True

    async def test_run_async_collects_streamed_text(self) -> None:
        agent = _ConfiguredAgent()
        streaming = StreamingAgent(agent, mcp_servers=[], http_client=_mock_transport())
        result = await streaming.run_async(prompt="explain step by step please")
        assert result["text"] != ""
        assert result.get("usage")

    async def test_stream_error_event_scrubs_credentials(self) -> None:
        """#1720 Wave-2b security: a stream transport error whose message embeds
        a credential (e.g. a base_url with userinfo, rendered by a raw
        httpx.HTTPError) MUST be scrubbed via sanitize_provider_error before it
        reaches the user-facing ErrorEvent — parity with the batch path."""
        from kaizen.llm.testing import MockLlmHttpClient

        class _CredLeakTransport(MockLlmHttpClient):
            async def stream_lines(self, *args: Any, **kwargs: Any):
                raise RuntimeError(
                    "connection to https://svc:supersecretpw@proxy.internal/v1 failed"
                )
                yield  # pragma: no cover - makes this an async generator

        agent = _ConfiguredAgent()
        streaming = StreamingAgent(
            agent, mcp_servers=[], http_client=_CredLeakTransport()
        )
        events = [e async for e in streaming.run_stream(prompt="hello")]

        errors = [e for e in events if isinstance(e, ErrorEvent)]
        assert errors, "an ErrorEvent should be emitted on transport failure"
        joined = " ".join(e.error for e in errors)
        # The credential must NOT survive into the user-facing stream.
        assert "supersecretpw" not in joined
        assert "svc:supersecretpw@" not in joined
        # It went through sanitize_provider_error (scrubbed form).
        assert "[REDACTED]" in joined
