# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for the Delegate facade (S9: Delegate Reification).

Tests cover:
    - Delegate lifecycle (create, run, close)
    - Typed events (TextDelta, ToolCallStart, ToolCallEnd, TurnComplete)
    - Progressive disclosure (Layer 1/2/3)
    - Budget tracking and BudgetExhausted events
    - Backward compatibility with AgentLoop
    - Error handling
    - run_sync convenience wrapper
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen_agents.delegate.delegate import Delegate, _estimate_cost
from kaizen_agents.delegate.events import (
    BudgetExhausted,
    DelegateEvent,
    ErrorEvent,
    TextDelta,
    ToolCallEnd,
    ToolCallStart,
    TurnComplete,
)
from kaizen_agents.delegate.loop import AgentLoop, ToolRegistry, UsageTracker
from kaizen_agents.delegate.config.loader import KzConfig


# ---------------------------------------------------------------------------
# Helpers -- fake streaming adapter
# ---------------------------------------------------------------------------


class FakeStreamEvent:
    """Minimal stand-in for protocol.StreamEvent used only by the adapter."""

    def __init__(
        self,
        event_type: str = "text_delta",
        content: str = "",
        tool_calls: list[dict[str, Any]] | None = None,
        finish_reason: str | None = None,
        model: str = "test-model",
        usage: dict[str, int] | None = None,
        delta_text: str = "",
    ) -> None:
        self.event_type = event_type
        self.content = content
        self.tool_calls = tool_calls or []
        self.finish_reason = finish_reason
        self.model = model
        self.usage = usage or {}
        self.delta_text = delta_text


class FakeAdapter:
    """A fake StreamingChatAdapter that yields pre-configured events."""

    def __init__(self, events: list[FakeStreamEvent]) -> None:
        self._events = events

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[FakeStreamEvent]:  # type: ignore[override]
        for event in self._events:
            yield event  # type: ignore[misc]


def _text_stream_events(text: str, chunk_size: int = 5) -> list[FakeStreamEvent]:
    """Create stream events for a simple text response."""
    events: list[FakeStreamEvent] = []
    accumulated = ""
    for i in range(0, len(text), chunk_size):
        chunk = text[i : i + chunk_size]
        accumulated += chunk
        events.append(
            FakeStreamEvent(
                event_type="text_delta",
                content=accumulated,
                delta_text=chunk,
            )
        )

    # Done event with usage
    events.append(
        FakeStreamEvent(
            event_type="done",
            content=accumulated,
            finish_reason="stop",
            usage={
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            },
        )
    )
    return events


def _make_config(**overrides: Any) -> KzConfig:
    """Create a KzConfig for testing."""
    defaults = {
        "model": "test-model",
        "max_turns": 100,
        "temperature": 0.0,
        "max_tokens": 4096,
    }
    defaults.update(overrides)
    return KzConfig(**defaults)


# ---------------------------------------------------------------------------
# Event dataclass tests
# ---------------------------------------------------------------------------


class TestDelegateEvents:
    """Tests for the typed event system (S9-003)."""

    def test_text_delta_event_type(self) -> None:
        """TextDelta has the correct event_type."""
        event = TextDelta(text="hello")
        assert event.event_type == "text_delta"
        assert event.text == "hello"
        assert isinstance(event, DelegateEvent)

    def test_tool_call_start_event_type(self) -> None:
        """ToolCallStart has the correct event_type."""
        event = ToolCallStart(call_id="tc_1", name="read_file")
        assert event.event_type == "tool_call_start"
        assert event.call_id == "tc_1"
        assert event.name == "read_file"
        assert isinstance(event, DelegateEvent)

    def test_tool_call_end_event_type(self) -> None:
        """ToolCallEnd has the correct event_type."""
        event = ToolCallEnd(call_id="tc_1", name="read_file", result="file contents")
        assert event.event_type == "tool_call_end"
        assert event.result == "file contents"
        assert event.error == ""

    def test_tool_call_end_with_error(self) -> None:
        """ToolCallEnd can carry error information."""
        event = ToolCallEnd(call_id="tc_1", name="read_file", error="file not found")
        assert event.error == "file not found"
        assert event.result == ""

    def test_turn_complete_event_type(self) -> None:
        """TurnComplete has the correct event_type and carries usage."""
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        event = TurnComplete(text="hello world", usage=usage)
        assert event.event_type == "turn_complete"
        assert event.text == "hello world"
        assert event.usage == usage

    def test_budget_exhausted_event_type(self) -> None:
        """BudgetExhausted carries budget details."""
        event = BudgetExhausted(budget_usd=10.0, consumed_usd=10.5)
        assert event.event_type == "budget_exhausted"
        assert event.budget_usd == 10.0
        assert event.consumed_usd == 10.5

    def test_error_event_type(self) -> None:
        """ErrorEvent carries error details."""
        event = ErrorEvent(error="something failed", details={"code": 500})
        assert event.event_type == "error"
        assert event.error == "something failed"
        assert event.details == {"code": 500}

    def test_all_events_have_timestamp(self) -> None:
        """All events have a monotonic timestamp."""
        events = [
            TextDelta(text="a"),
            ToolCallStart(call_id="1", name="t"),
            ToolCallEnd(call_id="1", name="t"),
            TurnComplete(text="done"),
            BudgetExhausted(),
            ErrorEvent(error="e"),
        ]
        for event in events:
            assert event.timestamp > 0
            assert isinstance(event.timestamp, float)


# ---------------------------------------------------------------------------
# Delegate lifecycle tests
# ---------------------------------------------------------------------------


class TestDelegateLifecycle:
    """Tests for Delegate creation and lifecycle (S9-001)."""

    def test_layer1_minimal_construction(self) -> None:
        """Layer 1: Delegate can be created with just a model name."""
        adapter = FakeAdapter([])
        d = Delegate(model="test-model", adapter=adapter)
        assert repr(d) == "Delegate(model='test-model')"
        assert d.budget_usd is None
        assert d.consumed_usd == 0.0
        assert d.budget_remaining is None

    def test_layer2_configured_construction(self) -> None:
        """Layer 2: Delegate can be created with tools and system prompt."""
        registry = ToolRegistry()
        adapter = FakeAdapter([])
        d = Delegate(
            model="test-model",
            tools=registry,
            system_prompt="You are a test agent.",
            max_turns=20,
            adapter=adapter,
        )
        assert d.tool_registry is registry
        assert d.loop is not None

    def test_layer3_governed_construction(self) -> None:
        """Layer 3: Delegate can be created with a budget."""
        adapter = FakeAdapter([])
        d = Delegate(model="test-model", budget_usd=10.0, adapter=adapter)
        assert d.budget_usd == 10.0
        assert d.consumed_usd == 0.0
        assert d.budget_remaining == 10.0
        assert "budget=$10.00" in repr(d)

    def test_close_prevents_further_runs(self) -> None:
        """Closing the Delegate makes subsequent runs yield ErrorEvent."""
        adapter = FakeAdapter([])
        d = Delegate(model="test-model", adapter=adapter)
        d.close()

        async def _run() -> list[DelegateEvent]:
            events: list[DelegateEvent] = []
            async for event in d.run("hello"):
                events.append(event)
            return events

        events = asyncio.run(_run())
        assert len(events) == 1
        assert isinstance(events[0], ErrorEvent)
        assert "closed" in events[0].error

    def test_empty_prompt_yields_error(self) -> None:
        """An empty prompt yields an ErrorEvent."""
        adapter = FakeAdapter([])
        d = Delegate(model="test-model", adapter=adapter)

        async def _run() -> list[DelegateEvent]:
            events: list[DelegateEvent] = []
            async for event in d.run(""):
                events.append(event)
            return events

        events = asyncio.run(_run())
        assert len(events) == 1
        assert isinstance(events[0], ErrorEvent)
        assert "Empty" in events[0].error

    def test_budget_validation_nan(self) -> None:
        """NaN budget is rejected (NaN/Inf security rule)."""
        with pytest.raises(ValueError, match="finite"):
            Delegate(model="test-model", budget_usd=float("nan"))

    def test_budget_validation_inf(self) -> None:
        """Inf budget is rejected."""
        with pytest.raises(ValueError, match="finite"):
            Delegate(model="test-model", budget_usd=float("inf"))

    def test_budget_validation_negative(self) -> None:
        """Negative budget is rejected."""
        with pytest.raises(ValueError, match="non-negative"):
            Delegate(model="test-model", budget_usd=-1.0)

    def test_tools_as_list_creates_empty_registry(self) -> None:
        """Passing tool names as a list creates an empty ToolRegistry."""
        adapter = FakeAdapter([])
        d = Delegate(model="test-model", tools=["read_file"], adapter=adapter)
        assert isinstance(d.tool_registry, ToolRegistry)

    def test_tools_as_registry_is_used_directly(self) -> None:
        """Passing a ToolRegistry uses it directly."""
        registry = ToolRegistry()
        adapter = FakeAdapter([])
        d = Delegate(model="test-model", tools=registry, adapter=adapter)
        assert d.tool_registry is registry

    def test_config_override(self) -> None:
        """Passing a KzConfig overrides model/max_turns."""
        config = _make_config(model="custom-model", max_turns=5)
        adapter = FakeAdapter([])
        d = Delegate(config=config, adapter=adapter)
        assert "custom-model" in repr(d)


# ---------------------------------------------------------------------------
# Run and event streaming tests
# ---------------------------------------------------------------------------


class TestDelegateRun:
    """Tests for Delegate.run() typed event streaming."""

    def test_text_response_yields_text_deltas_and_turn_complete(self) -> None:
        """A simple text response yields TextDelta events then TurnComplete."""
        stream_events = _text_stream_events("Hello, world!")
        adapter = FakeAdapter(stream_events)
        d = Delegate(model="test-model", adapter=adapter)

        async def _run() -> list[DelegateEvent]:
            events: list[DelegateEvent] = []
            async for event in d.run("say hello"):
                events.append(event)
            return events

        events = asyncio.run(_run())

        # Should have TextDelta events followed by TurnComplete
        text_deltas = [e for e in events if isinstance(e, TextDelta)]
        turn_completes = [e for e in events if isinstance(e, TurnComplete)]

        assert len(text_deltas) > 0
        assert len(turn_completes) == 1

        # Accumulated text from deltas should match
        full_text = "".join(td.text for td in text_deltas)
        assert full_text == "Hello, world!"

        # TurnComplete should carry the full text
        assert turn_completes[0].text == "Hello, world!"

        # Usage should be populated
        assert turn_completes[0].usage["total_tokens"] > 0

    def test_exception_during_run_yields_error_event(self) -> None:
        """An exception during the loop yields an ErrorEvent."""

        class FailingAdapter:
            async def stream_chat(self, **kwargs: Any) -> AsyncIterator[FakeStreamEvent]:
                raise RuntimeError("API connection failed")
                yield  # noqa: unreachable -- makes this an async generator

        adapter = FailingAdapter()
        d = Delegate(model="test-model", adapter=adapter)  # type: ignore[arg-type]

        async def _run() -> list[DelegateEvent]:
            events: list[DelegateEvent] = []
            async for event in d.run("hello"):
                events.append(event)
            return events

        events = asyncio.run(_run())

        error_events = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert "RuntimeError" in error_events[0].error  # exception type is included
        assert "API connection failed" not in error_events[0].error  # raw message is sanitized
        assert error_events[0].details["exception_type"] == "RuntimeError"


# ---------------------------------------------------------------------------
# Tool call event emission tests (GH #159)
# ---------------------------------------------------------------------------


def _tool_call_stream_events(
    tool_calls: list[dict[str, Any]],
    final_text: str = "Done.",
) -> tuple[list[FakeStreamEvent], list[FakeStreamEvent]]:
    """Create stream events for a tool-call response followed by a text response.

    Returns (tool_turn_events, text_turn_events) — two turns that FakeAdapter
    should yield sequentially.
    """
    # Turn 1: tool call
    tool_turn: list[FakeStreamEvent] = []
    # The adapter emits tool_call_start for each tool, then done with tool_calls
    for tc in tool_calls:
        tool_turn.append(
            FakeStreamEvent(
                event_type="tool_call_start",
                content="",
                model="test-model",
            )
        )
    tool_turn.append(
        FakeStreamEvent(
            event_type="done",
            content="",
            tool_calls=tool_calls,
            finish_reason="tool_calls",
            usage={"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
        )
    )

    # Turn 2: text response after tool results
    text_turn = _text_stream_events(final_text)

    return tool_turn, text_turn


class _MultiTurnFakeAdapter:
    """FakeAdapter that serves multiple turns of events sequentially."""

    def __init__(self, *turns: list[FakeStreamEvent]) -> None:
        self._turns = list(turns)
        self._call_count = 0

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[FakeStreamEvent]:
        idx = min(self._call_count, len(self._turns) - 1)
        self._call_count += 1
        for event in self._turns[idx]:
            yield event  # type: ignore[misc]


class TestDelegateToolCallEvents:
    """Tests for ToolCallStart/ToolCallEnd event emission (GH #159)."""

    def test_single_tool_call_emits_start_and_end(self) -> None:
        """A single tool call yields ToolCallStart then ToolCallEnd."""
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path": "foo.py"}'},
            }
        ]
        tool_turn, text_turn = _tool_call_stream_events(tool_calls, "Here is the file.")

        adapter = _MultiTurnFakeAdapter(tool_turn, text_turn)
        registry = ToolRegistry()

        async def fake_read_file(path: str = "") -> str:
            return f"contents of {path}"

        registry.register(
            "read_file",
            "Read a file",
            {"type": "object", "properties": {"path": {"type": "string"}}},
            fake_read_file,
        )

        d = Delegate(model="test-model", tools=registry, adapter=adapter)

        async def _run() -> list[DelegateEvent]:
            events: list[DelegateEvent] = []
            async for event in d.run("read foo.py"):
                events.append(event)
            return events

        events = asyncio.run(_run())

        starts = [e for e in events if isinstance(e, ToolCallStart)]
        ends = [e for e in events if isinstance(e, ToolCallEnd)]

        assert len(starts) == 1
        assert starts[0].call_id == "call_1"
        assert starts[0].name == "read_file"

        assert len(ends) == 1
        assert ends[0].call_id == "call_1"
        assert ends[0].name == "read_file"
        assert "contents of foo.py" in ends[0].result
        assert ends[0].error == ""

    def test_parallel_tool_calls_emit_multiple_events(self) -> None:
        """Multiple tool calls yield multiple ToolCallStart/ToolCallEnd pairs."""
        tool_calls = [
            {
                "id": "call_a",
                "type": "function",
                "function": {"name": "tool_a", "arguments": "{}"},
            },
            {
                "id": "call_b",
                "type": "function",
                "function": {"name": "tool_b", "arguments": "{}"},
            },
        ]
        tool_turn, text_turn = _tool_call_stream_events(tool_calls, "Both done.")

        adapter = _MultiTurnFakeAdapter(tool_turn, text_turn)
        registry = ToolRegistry()

        async def tool_a_exec() -> str:
            return "result_a"

        async def tool_b_exec() -> str:
            return "result_b"

        registry.register("tool_a", "A", {"type": "object", "properties": {}}, tool_a_exec)
        registry.register("tool_b", "B", {"type": "object", "properties": {}}, tool_b_exec)

        d = Delegate(model="test-model", tools=registry, adapter=adapter)

        async def _run() -> list[DelegateEvent]:
            events: list[DelegateEvent] = []
            async for event in d.run("run both"):
                events.append(event)
            return events

        events = asyncio.run(_run())

        starts = [e for e in events if isinstance(e, ToolCallStart)]
        ends = [e for e in events if isinstance(e, ToolCallEnd)]

        assert len(starts) == 2
        assert {s.call_id for s in starts} == {"call_a", "call_b"}
        assert {s.name for s in starts} == {"tool_a", "tool_b"}

        assert len(ends) == 2
        assert {e.call_id for e in ends} == {"call_a", "call_b"}

    def test_tool_error_populates_error_field(self) -> None:
        """A failing tool yields ToolCallEnd with error field populated."""
        tool_calls = [
            {
                "id": "call_fail",
                "type": "function",
                "function": {"name": "failing", "arguments": "{}"},
            }
        ]
        tool_turn, text_turn = _tool_call_stream_events(tool_calls, "Tool failed.")

        adapter = _MultiTurnFakeAdapter(tool_turn, text_turn)
        registry = ToolRegistry()

        async def failing_tool() -> str:
            raise RuntimeError("Something broke")

        registry.register("failing", "Fails", {"type": "object", "properties": {}}, failing_tool)

        d = Delegate(model="test-model", tools=registry, adapter=adapter)

        async def _run() -> list[DelegateEvent]:
            events: list[DelegateEvent] = []
            async for event in d.run("try it"):
                events.append(event)
            return events

        events = asyncio.run(_run())

        ends = [e for e in events if isinstance(e, ToolCallEnd)]
        assert len(ends) == 1
        assert ends[0].call_id == "call_fail"
        assert "error" in ends[0].result  # error is in the JSON result string
        assert "RuntimeError" in ends[0].result  # exception type is included
        assert "Something broke" not in ends[0].result  # raw message is sanitized
        assert ends[0].name == "failing"

    def test_event_ordering_starts_before_ends(self) -> None:
        """All ToolCallStart events appear before any ToolCallEnd events."""
        tool_calls = [
            {
                "id": "call_x",
                "type": "function",
                "function": {"name": "tool_x", "arguments": "{}"},
            },
            {
                "id": "call_y",
                "type": "function",
                "function": {"name": "tool_y", "arguments": "{}"},
            },
        ]
        tool_turn, text_turn = _tool_call_stream_events(tool_calls, "OK")

        adapter = _MultiTurnFakeAdapter(tool_turn, text_turn)
        registry = ToolRegistry()

        async def tool_x() -> str:
            return "x"

        async def tool_y() -> str:
            return "y"

        registry.register("tool_x", "X", {"type": "object", "properties": {}}, tool_x)
        registry.register("tool_y", "Y", {"type": "object", "properties": {}}, tool_y)

        d = Delegate(model="test-model", tools=registry, adapter=adapter)

        async def _run() -> list[DelegateEvent]:
            events: list[DelegateEvent] = []
            async for event in d.run("go"):
                events.append(event)
            return events

        events = asyncio.run(_run())

        # Extract indices of tool events
        tool_events = [
            (i, e) for i, e in enumerate(events) if isinstance(e, (ToolCallStart, ToolCallEnd))
        ]
        start_indices = [i for i, e in tool_events if isinstance(e, ToolCallStart)]
        end_indices = [i for i, e in tool_events if isinstance(e, ToolCallEnd)]

        # All starts must come before all ends
        assert max(start_indices) < min(end_indices)

    def test_text_only_response_has_no_tool_events(self) -> None:
        """A text-only response yields no ToolCallStart/ToolCallEnd events."""
        stream_events = _text_stream_events("Just text, no tools.")
        adapter = FakeAdapter(stream_events)
        d = Delegate(model="test-model", adapter=adapter)

        async def _run() -> list[DelegateEvent]:
            events: list[DelegateEvent] = []
            async for event in d.run("hello"):
                events.append(event)
            return events

        events = asyncio.run(_run())

        starts = [e for e in events if isinstance(e, ToolCallStart)]
        ends = [e for e in events if isinstance(e, ToolCallEnd)]
        assert len(starts) == 0
        assert len(ends) == 0

        # Should still have text and turn complete
        assert any(isinstance(e, TextDelta) for e in events)
        assert any(isinstance(e, TurnComplete) for e in events)

    def test_run_sync_ignores_tool_events(self) -> None:
        """run_sync() returns text only — tool events are silently ignored."""
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "my_tool", "arguments": "{}"},
            }
        ]
        tool_turn, text_turn = _tool_call_stream_events(tool_calls, "Final answer.")

        adapter = _MultiTurnFakeAdapter(tool_turn, text_turn)
        registry = ToolRegistry()

        async def my_tool() -> str:
            return "tool result"

        registry.register("my_tool", "T", {"type": "object", "properties": {}}, my_tool)

        d = Delegate(model="test-model", tools=registry, adapter=adapter)
        result = d.run_sync("do it")

        assert result == "Final answer."
        assert "ToolCallStart" not in result
        assert "ToolCallEnd" not in result

    def test_multi_turn_event_sequence(self) -> None:
        """Multi-turn: tool turn followed by text turn produces correct event sequence."""
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "search", "arguments": '{"q": "test"}'},
            }
        ]
        tool_turn, text_turn = _tool_call_stream_events(tool_calls, "Found results.")

        adapter = _MultiTurnFakeAdapter(tool_turn, text_turn)
        registry = ToolRegistry()

        async def search(q: str = "") -> str:
            return f"results for {q}"

        registry.register(
            "search",
            "Search",
            {"type": "object", "properties": {"q": {"type": "string"}}},
            search,
        )

        d = Delegate(model="test-model", tools=registry, adapter=adapter)

        async def _run() -> list[DelegateEvent]:
            events: list[DelegateEvent] = []
            async for event in d.run("search for test"):
                events.append(event)
            return events

        events = asyncio.run(_run())

        # Should see: ToolCallStart, ToolCallEnd, TextDelta(s), TurnComplete
        event_types = [type(e).__name__ for e in events]
        assert "ToolCallStart" in event_types
        assert "ToolCallEnd" in event_types
        assert "TextDelta" in event_types
        assert "TurnComplete" in event_types

        # ToolCallStart must come before TextDelta from the second turn
        tc_start_idx = event_types.index("ToolCallStart")
        tc_end_idx = event_types.index("ToolCallEnd")
        last_text_idx = len(event_types) - 1 - event_types[::-1].index("TextDelta")

        assert tc_start_idx < tc_end_idx
        assert tc_end_idx < last_text_idx

    def test_consecutive_tool_turns_emit_events_for_each_batch(self) -> None:
        """Two consecutive tool turns (tool->tool->text) emit events for each batch."""
        tool_calls_1 = [
            {
                "id": "call_a",
                "type": "function",
                "function": {"name": "step_one", "arguments": "{}"},
            }
        ]
        tool_calls_2 = [
            {
                "id": "call_b",
                "type": "function",
                "function": {"name": "step_two", "arguments": "{}"},
            }
        ]

        # Turn 1: tool call
        turn1: list[FakeStreamEvent] = [
            FakeStreamEvent(event_type="tool_call_start", content="", model="test-model"),
            FakeStreamEvent(
                event_type="done",
                content="",
                tool_calls=tool_calls_1,
                finish_reason="tool_calls",
                usage={"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
            ),
        ]
        # Turn 2: another tool call
        turn2: list[FakeStreamEvent] = [
            FakeStreamEvent(event_type="tool_call_start", content="", model="test-model"),
            FakeStreamEvent(
                event_type="done",
                content="",
                tool_calls=tool_calls_2,
                finish_reason="tool_calls",
                usage={"prompt_tokens": 80, "completion_tokens": 30, "total_tokens": 110},
            ),
        ]
        # Turn 3: text response
        turn3 = _text_stream_events("All steps done.")

        adapter = _MultiTurnFakeAdapter(turn1, turn2, turn3)
        registry = ToolRegistry()

        async def step_one() -> str:
            return "step_one_result"

        async def step_two() -> str:
            return "step_two_result"

        registry.register("step_one", "S1", {"type": "object", "properties": {}}, step_one)
        registry.register("step_two", "S2", {"type": "object", "properties": {}}, step_two)

        d = Delegate(model="test-model", tools=registry, adapter=adapter)

        async def _run() -> list[DelegateEvent]:
            events: list[DelegateEvent] = []
            async for event in d.run("do both steps"):
                events.append(event)
            return events

        events = asyncio.run(_run())

        starts = [e for e in events if isinstance(e, ToolCallStart)]
        ends = [e for e in events if isinstance(e, ToolCallEnd)]

        # Should have 2 starts and 2 ends (one per tool batch)
        assert len(starts) == 2
        assert {s.name for s in starts} == {"step_one", "step_two"}

        assert len(ends) == 2
        assert {e.name for e in ends} == {"step_one", "step_two"}

        # Verify batch ordering: batch 1 events before batch 2 events
        start_names = [s.name for s in starts]
        end_names = [e.name for e in ends]
        assert start_names == ["step_one", "step_two"]
        assert end_names == ["step_one", "step_two"]


# ---------------------------------------------------------------------------
# Budget tracking tests
# ---------------------------------------------------------------------------


class TestDelegateBudget:
    """Tests for budget tracking (S9-004)."""

    def test_budget_remaining_decreases_after_run(self) -> None:
        """Budget remaining decreases after a run."""
        stream_events = _text_stream_events("Hello")
        adapter = FakeAdapter(stream_events)
        d = Delegate(model="test-model", budget_usd=100.0, adapter=adapter)

        async def _run() -> list[DelegateEvent]:
            events: list[DelegateEvent] = []
            async for event in d.run("hello"):
                events.append(event)
            return events

        events = asyncio.run(_run())
        # After a run with 100+50 tokens, some cost should be recorded
        assert d.consumed_usd > 0.0
        remaining = d.budget_remaining
        assert remaining is not None
        assert remaining < 100.0

    def test_budget_exhausted_before_run_yields_event(self) -> None:
        """If budget is already exhausted, run() yields BudgetExhausted immediately."""
        adapter = FakeAdapter([])
        d = Delegate(model="test-model", budget_usd=0.0, adapter=adapter)

        async def _run() -> list[DelegateEvent]:
            events: list[DelegateEvent] = []
            async for event in d.run("hello"):
                events.append(event)
            return events

        events = asyncio.run(_run())
        assert len(events) == 1
        assert isinstance(events[0], BudgetExhausted)
        assert events[0].budget_usd == 0.0

    def test_cost_estimation_function(self) -> None:
        """_estimate_cost produces reasonable values for known model prefixes."""
        # Claude model
        cost = _estimate_cost("claude-sonnet-4-20250514", 1000, 500)
        assert cost > 0.0

        # GPT-4o model
        cost_gpt = _estimate_cost("gpt-4o-latest", 1000, 500)
        assert cost_gpt > 0.0

        # Unknown model uses defaults
        cost_unknown = _estimate_cost("unknown-model", 1000, 500)
        assert cost_unknown > 0.0


# ---------------------------------------------------------------------------
# run_sync tests
# ---------------------------------------------------------------------------


class TestDelegateRunSync:
    """Tests for Delegate.run_sync() synchronous wrapper."""

    def test_run_sync_returns_complete_text(self) -> None:
        """run_sync collects all text and returns the complete response."""
        stream_events = _text_stream_events("Sync response works!")
        adapter = FakeAdapter(stream_events)
        d = Delegate(model="test-model", adapter=adapter)

        result = d.run_sync("test prompt")
        assert result == "Sync response works!"

    def test_run_sync_raises_on_budget_exhausted(self) -> None:
        """run_sync raises RuntimeError when budget is exhausted."""
        adapter = FakeAdapter([])
        d = Delegate(model="test-model", budget_usd=0.0, adapter=adapter)

        with pytest.raises(RuntimeError, match="Budget exhausted"):
            d.run_sync("test prompt")

    def test_run_sync_raises_on_error(self) -> None:
        """run_sync raises RuntimeError on ErrorEvent."""
        adapter = FakeAdapter([])
        d = Delegate(model="test-model", adapter=adapter)
        d.close()

        with pytest.raises(RuntimeError, match="closed"):
            d.run_sync("test prompt")


# ---------------------------------------------------------------------------
# Backward compatibility with AgentLoop
# ---------------------------------------------------------------------------


class TestAgentLoopCompat:
    """Tests for backward compatibility with AgentLoop."""

    def test_delegate_exposes_loop(self) -> None:
        """Delegate.loop provides direct access to the underlying AgentLoop."""
        adapter = FakeAdapter([])
        d = Delegate(model="test-model", adapter=adapter)
        assert isinstance(d.loop, AgentLoop)

    def test_delegate_loop_shares_tool_registry(self) -> None:
        """The Delegate's tool registry is the same instance used by the loop."""
        registry = ToolRegistry()
        adapter = FakeAdapter([])
        d = Delegate(model="test-model", tools=registry, adapter=adapter)
        # The loop uses the same registry (via internal reference)
        assert d.tool_registry is registry

    def test_interrupt_delegates_to_loop(self) -> None:
        """Delegate.interrupt() forwards to AgentLoop.interrupt()."""
        adapter = FakeAdapter([])
        d = Delegate(model="test-model", adapter=adapter)
        d.interrupt()
        # The loop's interrupted flag should be set
        assert d.loop._interrupted is True


# ---------------------------------------------------------------------------
# Import/export tests
# ---------------------------------------------------------------------------


class TestDelegateExports:
    """Tests for Delegate exports (S9-002)."""

    def test_import_from_delegate_package(self) -> None:
        """Delegate can be imported from kaizen_agents.delegate."""
        from kaizen_agents.delegate import Delegate as D

        assert D is Delegate

    def test_import_from_top_level(self) -> None:
        """Delegate can be imported from kaizen_agents."""
        from kaizen_agents import Delegate as D

        assert D is Delegate

    def test_event_imports_from_delegate_package(self) -> None:
        """Event classes can be imported from kaizen_agents.delegate."""
        from kaizen_agents.delegate import (
            BudgetExhausted as BE,
            DelegateEvent as DE,
            ErrorEvent as EE,
            TextDelta as TD,
            ToolCallEnd as TCE,
            ToolCallStart as TCS,
            TurnComplete as TC,
        )

        assert DE is DelegateEvent
        assert TD is TextDelta
        assert TCS is ToolCallStart
        assert TCE is ToolCallEnd
        assert TC is TurnComplete
        assert BE is BudgetExhausted
        assert EE is ErrorEvent
