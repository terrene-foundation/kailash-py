# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for incremental streaming in AgentLoop (S6).

Tests cover:
    - Text tokens are yielded incrementally (multiple small chunks, not one large blob)
    - Tool-call turns still work correctly
    - Pre-tool-call text (reasoning/thinking) is yielded before tool execution
    - Backward compatibility: joined chunks produce the same final text
    - Conversation history is correct after incremental streaming
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import pytest

from kaizen_agents.delegate.loop import AgentLoop, Conversation, ToolRegistry
from kaizen_agents.delegate.config.loader import KzConfig


# ---------------------------------------------------------------------------
# Helpers -- fake OpenAI streaming responses (reuse patterns from test_loop.py)
# ---------------------------------------------------------------------------


@dataclass
class FakeFunctionCall:
    """Mimics openai.types.chat.chat_completion_chunk.ChoiceDeltaToolCallFunction."""

    name: str | None = None
    arguments: str | None = None


@dataclass
class FakeToolCallDelta:
    """Mimics openai.types.chat.chat_completion_chunk.ChoiceDeltaToolCall."""

    index: int
    id: str | None = None
    type: str | None = None
    function: FakeFunctionCall | None = None


@dataclass
class FakeDelta:
    """Mimics openai.types.chat.chat_completion_chunk.ChoiceDelta."""

    content: str | None = None
    tool_calls: list[FakeToolCallDelta] | None = None


@dataclass
class FakeChoice:
    """Mimics openai.types.chat.chat_completion_chunk.Choice."""

    delta: FakeDelta
    finish_reason: str | None = None


@dataclass
class FakeUsage:
    """Mimics openai.types.CompletionUsage."""

    prompt_tokens: int = 10
    completion_tokens: int = 5
    total_tokens: int = 15


@dataclass
class FakeChunk:
    """Mimics openai.types.chat.ChatCompletionChunk."""

    choices: list[FakeChoice] = field(default_factory=list)
    model: str = "test-model"
    usage: FakeUsage | None = None


class FakeAsyncStream:
    """An async iterable that yields FakeChunk objects, mimicking AsyncStream."""

    def __init__(self, chunks: list[FakeChunk]) -> None:
        self._chunks = chunks

    def __aiter__(self) -> AsyncIterator[FakeChunk]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[FakeChunk]:
        for chunk in self._chunks:
            yield chunk


def _text_chunks(text: str, chunk_size: int = 5) -> list[FakeChunk]:
    """Create a sequence of fake chunks that stream a text response.

    Each chunk contains ``chunk_size`` characters of text, simulating
    token-level streaming from the LLM.
    """
    chunks: list[FakeChunk] = []
    for i in range(0, len(text), chunk_size):
        chunk_text = text[i : i + chunk_size]
        chunks.append(
            FakeChunk(
                choices=[FakeChoice(delta=FakeDelta(content=chunk_text))],
            )
        )

    # Final chunk with finish reason
    chunks.append(
        FakeChunk(
            choices=[FakeChoice(delta=FakeDelta(), finish_reason="stop")],
        )
    )

    # Usage chunk (no choices)
    chunks.append(FakeChunk(choices=[], usage=FakeUsage()))

    return chunks


def _tool_call_chunks(
    tool_calls: list[dict[str, Any]],
    *,
    text_before: str = "",
) -> list[FakeChunk]:
    """Create fake chunks for a response that includes tool calls.

    Parameters
    ----------
    tool_calls:
        List of dicts with 'id', 'name', 'arguments' keys.
    text_before:
        Optional text content emitted before the tool calls (reasoning text).
    """
    chunks: list[FakeChunk] = []

    # Optional reasoning/thinking text before tool calls
    if text_before:
        for i in range(0, len(text_before), 5):
            chunk_text = text_before[i : i + 5]
            chunks.append(
                FakeChunk(choices=[FakeChoice(delta=FakeDelta(content=chunk_text))])
            )

    # Tool call deltas
    for idx, tc in enumerate(tool_calls):
        # First delta: id, name
        chunks.append(
            FakeChunk(
                choices=[
                    FakeChoice(
                        delta=FakeDelta(
                            tool_calls=[
                                FakeToolCallDelta(
                                    index=idx,
                                    id=tc["id"],
                                    type="function",
                                    function=FakeFunctionCall(name=tc["name"], arguments=""),
                                )
                            ]
                        )
                    )
                ]
            )
        )

        # Second delta: arguments
        chunks.append(
            FakeChunk(
                choices=[
                    FakeChoice(
                        delta=FakeDelta(
                            tool_calls=[
                                FakeToolCallDelta(
                                    index=idx,
                                    function=FakeFunctionCall(arguments=tc["arguments"]),
                                )
                            ]
                        )
                    )
                ]
            )
        )

    # Finish with tool_calls reason
    chunks.append(
        FakeChunk(
            choices=[FakeChoice(delta=FakeDelta(), finish_reason="tool_calls")],
        )
    )

    # Usage chunk
    chunks.append(FakeChunk(choices=[], usage=FakeUsage()))

    return chunks


def _make_fake_client(*call_responses: list[FakeChunk]) -> Any:
    """Create a mock AsyncOpenAI client that returns the given chunk sequences.

    Each argument is a list of chunks for one call to chat.completions.create().
    """
    from unittest.mock import AsyncMock

    client = AsyncMock()
    side_effects = [FakeAsyncStream(chunks) for chunks in call_responses]
    client.chat.completions.create = AsyncMock(side_effect=side_effects)
    return client


def _make_config(**overrides: Any) -> KzConfig:
    """Create a KzConfig for testing."""
    defaults: dict[str, Any] = {
        "model": "test-model",
        "max_turns": 100,
        "temperature": 0.0,
        "max_tokens": 4096,
    }
    defaults.update(overrides)
    return KzConfig(**defaults)


# ---------------------------------------------------------------------------
# S6-001 / S6-002: Incremental text streaming
# ---------------------------------------------------------------------------


class TestIncrementalStreaming:
    """Test that run_turn() yields text deltas incrementally, not as one blob."""

    async def test_multiple_chunks_yielded(self) -> None:
        """Text response is yielded as multiple small chunks, not one large string."""
        response_text = "Hello! How can I help you today?"
        # chunk_size=5 means each chunk has at most 5 characters
        chunks = _text_chunks(response_text, chunk_size=5)
        client = _make_fake_client(chunks)
        config = _make_config()
        tools = ToolRegistry()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="Test")

        collected: list[str] = []
        async for chunk in loop.run_turn("Hi"):
            collected.append(chunk)

        # Multiple chunks were yielded (not a single blob)
        assert len(collected) > 1, (
            f"Expected multiple chunks, got {len(collected)}: {collected}"
        )

        # Each chunk should be small (at most chunk_size characters)
        for chunk in collected:
            assert len(chunk) <= 5, f"Chunk too large: {chunk!r}"

    async def test_single_char_chunks(self) -> None:
        """Character-level streaming yields one chunk per character."""
        response_text = "ABCDE"
        chunks = _text_chunks(response_text, chunk_size=1)
        client = _make_fake_client(chunks)
        config = _make_config()
        tools = ToolRegistry()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        collected: list[str] = []
        async for chunk in loop.run_turn("Go"):
            collected.append(chunk)

        assert collected == ["A", "B", "C", "D", "E"]

    async def test_empty_response_yields_nothing(self) -> None:
        """An empty text response yields no chunks."""
        # Stream with finish reason but no content
        chunks = [
            FakeChunk(choices=[FakeChoice(delta=FakeDelta(), finish_reason="stop")]),
            FakeChunk(choices=[], usage=FakeUsage()),
        ]
        client = _make_fake_client(chunks)
        config = _make_config()
        tools = ToolRegistry()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        collected: list[str] = []
        async for chunk in loop.run_turn("Empty"):
            collected.append(chunk)

        assert collected == []


# ---------------------------------------------------------------------------
# S6-004: Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Joined chunks produce the same final text as the old buffered approach."""

    async def test_joined_chunks_equal_full_text(self) -> None:
        """Concatenating all yielded chunks gives the complete response text."""
        response_text = "The quick brown fox jumps over the lazy dog."
        chunks = _text_chunks(response_text, chunk_size=7)
        client = _make_fake_client(chunks)
        config = _make_config()
        tools = ToolRegistry()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        collected: list[str] = []
        async for chunk in loop.run_turn("Test"):
            collected.append(chunk)

        full_text = "".join(collected)
        assert full_text == response_text

    async def test_run_print_returns_full_text(self) -> None:
        """run_print() still returns the complete response text (compatibility)."""
        response_text = "The answer is 42."
        chunks = _text_chunks(response_text)
        client = _make_fake_client(chunks)
        config = _make_config()
        tools = ToolRegistry()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        result = await loop.run_print("What is the answer?")
        assert result == response_text

    async def test_conversation_history_correct_after_streaming(self) -> None:
        """Conversation history matches the full response, not partial chunks."""
        response_text = "Complete answer here."
        chunks = _text_chunks(response_text, chunk_size=4)
        client = _make_fake_client(chunks)
        config = _make_config()
        tools = ToolRegistry()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="Sys")

        async for _ in loop.run_turn("Question"):
            pass

        msgs = loop.conversation.messages
        assert len(msgs) == 3  # system + user + assistant
        assert msgs[2]["role"] == "assistant"
        assert msgs[2]["content"] == response_text

    async def test_usage_tracked_with_incremental_streaming(self) -> None:
        """Token usage is correctly tracked with incremental streaming."""
        chunks = _text_chunks("Short text")
        client = _make_fake_client(chunks)
        config = _make_config()
        tools = ToolRegistry()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        async for _ in loop.run_turn("Test"):
            pass

        assert loop.usage.turns == 1
        assert loop.usage.total_tokens == 15  # from FakeUsage defaults


# ---------------------------------------------------------------------------
# S6-003: Tool-call turns with pre-tool-call text
# ---------------------------------------------------------------------------


class TestToolCallStreaming:
    """Test tool-call turns with incremental streaming."""

    async def test_tool_call_then_text_response(self) -> None:
        """Tool call -> execute -> final text response is streamed incrementally."""
        tools = ToolRegistry()

        async def list_files(path: str = ".") -> str:
            return "file1.py\nfile2.py"

        tools.register(
            name="list_files",
            description="List files in a directory",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
            executor=list_files,
        )

        # First call: model requests tool call (no text)
        tool_chunks = _tool_call_chunks(
            [{"id": "call_001", "name": "list_files", "arguments": '{"path": "."}'}]
        )
        # Second call: model responds with text after seeing tool result
        final_text = "Found 2 files: file1.py and file2.py"
        final_chunks = _text_chunks(final_text, chunk_size=6)

        client = _make_fake_client(tool_chunks, final_chunks)
        config = _make_config()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        collected: list[str] = []
        async for chunk in loop.run_turn("List files"):
            collected.append(chunk)

        # Final text is streamed as multiple chunks
        assert len(collected) > 1
        full_text = "".join(collected)
        assert full_text == final_text

    async def test_pre_tool_call_text_is_yielded(self) -> None:
        """Reasoning/thinking text before tool calls is yielded incrementally.

        Models like GPT-5 emit thinking text before tool calls. S6-003 requires
        that this text is NOT suppressed.
        """
        tools = ToolRegistry()

        async def search(query: str = "") -> str:
            return "result for: " + query

        tools.register(
            name="search",
            description="Search",
            parameters={"type": "object", "properties": {"query": {"type": "string"}}},
            executor=search,
        )

        # First call: model emits thinking text + tool call
        thinking_text = "Let me search for that..."
        tool_chunks = _tool_call_chunks(
            [{"id": "call_1", "name": "search", "arguments": '{"query": "test"}'}],
            text_before=thinking_text,
        )

        # Second call: model responds with final text
        final_text = "Here are the results."
        final_chunks = _text_chunks(final_text, chunk_size=5)

        client = _make_fake_client(tool_chunks, final_chunks)
        config = _make_config()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        collected: list[str] = []
        async for chunk in loop.run_turn("Search for something"):
            collected.append(chunk)

        full_text = "".join(collected)

        # The pre-tool-call thinking text should be in the output
        assert thinking_text in full_text, (
            f"Pre-tool-call text not found in output: {full_text!r}"
        )
        # The final text response should also be there
        assert final_text in full_text

    async def test_parallel_tool_calls_with_streaming(self) -> None:
        """Multiple parallel tool calls work correctly with incremental streaming."""
        tools = ToolRegistry()

        async def tool_a(x: str = "") -> str:
            return f"result_a({x})"

        async def tool_b(y: str = "") -> str:
            return f"result_b({y})"

        tools.register(
            "tool_a", "Tool A",
            {"type": "object", "properties": {"x": {"type": "string"}}},
            tool_a,
        )
        tools.register(
            "tool_b", "Tool B",
            {"type": "object", "properties": {"y": {"type": "string"}}},
            tool_b,
        )

        # Model requests both tools in one response
        parallel_chunks = _tool_call_chunks([
            {"id": "call_a", "name": "tool_a", "arguments": '{"x": "hello"}'},
            {"id": "call_b", "name": "tool_b", "arguments": '{"y": "world"}'},
        ])

        final_text = "Both tools completed successfully."
        final_chunks = _text_chunks(final_text, chunk_size=8)

        client = _make_fake_client(parallel_chunks, final_chunks)
        config = _make_config()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        collected: list[str] = []
        async for chunk in loop.run_turn("Run both"):
            collected.append(chunk)

        full_text = "".join(collected)
        assert full_text == final_text

        # Verify both tool results are in conversation
        tool_msgs = [m for m in loop.conversation.messages if m["role"] == "tool"]
        assert len(tool_msgs) == 2

    async def test_tool_error_handled_with_streaming(self) -> None:
        """Tool execution errors are captured correctly with incremental streaming."""
        tools = ToolRegistry()

        async def failing_tool() -> str:
            raise RuntimeError("Tool broke")

        tools.register(
            "failing", "A failing tool",
            {"type": "object", "properties": {}},
            failing_tool,
        )

        tool_chunks = _tool_call_chunks(
            [{"id": "call_fail", "name": "failing", "arguments": "{}"}]
        )
        final_chunks = _text_chunks("The tool encountered an error.", chunk_size=10)

        client = _make_fake_client(tool_chunks, final_chunks)
        config = _make_config()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        collected: list[str] = []
        async for chunk in loop.run_turn("Try the tool"):
            collected.append(chunk)

        # Error is in conversation
        tool_msg = next(m for m in loop.conversation.messages if m["role"] == "tool")
        assert "error" in tool_msg["content"].lower()
        assert "Tool broke" in tool_msg["content"]

        # Final text still arrives
        assert "".join(collected) == "The tool encountered an error."


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestStreamingEdgeCases:
    """Edge cases for incremental streaming."""

    async def test_budget_exhausted_yields_message(self) -> None:
        """Budget exhaustion yields a message and stops."""
        config = _make_config()
        tools = ToolRegistry()
        # Client that would succeed but we never reach it
        chunks = _text_chunks("Should not see this")
        client = _make_fake_client(chunks)

        loop = AgentLoop(
            config=config,
            tools=tools,
            client=client,
            system_prompt="",
            budget_check=lambda: False,  # always exhausted
        )

        collected: list[str] = []
        async for chunk in loop.run_turn("Test"):
            collected.append(chunk)

        assert len(collected) == 1
        assert "Budget exhausted" in collected[0]

    async def test_max_turns_stops_with_streaming(self) -> None:
        """Max turns limit is enforced with incremental streaming."""
        tools = ToolRegistry()

        async def echo(text: str = "") -> str:
            return f"echo: {text}"

        tools.register(
            "echo", "Echo",
            {"type": "object", "properties": {"text": {"type": "string"}}},
            echo,
        )

        # Create tool-call responses that would exceed max_turns=2
        responses = []
        for i in range(5):
            responses.append(
                _tool_call_chunks(
                    [{"id": f"call_{i}", "name": "echo", "arguments": f'{{"text": "turn {i}"}}'}]
                )
            )

        client = _make_fake_client(*responses)
        config = _make_config(max_turns=2)

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        collected: list[str] = []
        async for chunk in loop.run_turn("Keep going"):
            collected.append(chunk)

        # Should have stopped after max_turns
        assert loop.usage.turns <= 2

    async def test_interrupt_during_stream(self) -> None:
        """Interrupting during streaming stops yielding text."""
        tools = ToolRegistry()
        # Long text to give us time to "interrupt"
        response_text = "A" * 100
        chunks = _text_chunks(response_text, chunk_size=1)
        client = _make_fake_client(chunks)
        config = _make_config()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        collected: list[str] = []
        count = 0
        async for chunk in loop.run_turn("Go"):
            collected.append(chunk)
            count += 1
            if count >= 5:
                loop.interrupt()

        # Should have stopped well before 100 characters
        full_text = "".join(collected)
        assert len(full_text) <= 10, f"Expected early stop, got {len(full_text)} chars"

    async def test_two_turn_conversation_with_streaming(self) -> None:
        """Two sequential user turns with incremental streaming maintain history."""
        response1 = _text_chunks("Answer one", chunk_size=3)
        response2 = _text_chunks("Answer two", chunk_size=3)

        client = _make_fake_client(response1, response2)
        config = _make_config()
        tools = ToolRegistry()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="System")

        # Turn 1
        chunks1: list[str] = []
        async for chunk in loop.run_turn("Q1"):
            chunks1.append(chunk)
        assert "".join(chunks1) == "Answer one"

        # Turn 2
        chunks2: list[str] = []
        async for chunk in loop.run_turn("Q2"):
            chunks2.append(chunk)
        assert "".join(chunks2) == "Answer two"

        # Verify conversation
        msgs = loop.conversation.messages
        roles = [m["role"] for m in msgs]
        assert roles == ["system", "user", "assistant", "user", "assistant"]
        assert msgs[2]["content"] == "Answer one"
        assert msgs[4]["content"] == "Answer two"
