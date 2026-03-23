"""Tests for the kz core agent loop.

Tests cover:
    - Single-turn text response (no tools)
    - Single-turn with tool call -> tool result -> final response
    - Multiple parallel tool calls in one response
    - Max turns limit enforcement
    - Conversation history management
    - Tool registry operations
    - Interrupt handling
    - Error handling in tool execution
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen_agents.delegate.loop import AgentLoop, Conversation, ToolRegistry, UsageTracker
from kaizen_agents.delegate.config.loader import KzConfig


# ---------------------------------------------------------------------------
# Helpers — fake OpenAI streaming responses
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
    model: str = "gpt-4o-test"
    usage: FakeUsage | None = None


def _text_chunks(text: str, chunk_size: int = 5) -> list[FakeChunk]:
    """Create a sequence of fake chunks that stream a text response."""
    chunks = []
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
        Optional text content before the tool calls.
    """
    chunks: list[FakeChunk] = []

    # Optional text content
    if text_before:
        chunks.append(FakeChunk(choices=[FakeChoice(delta=FakeDelta(content=text_before))]))

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


class FakeAsyncStream:
    """An async iterable that yields FakeChunk objects, mimicking AsyncStream."""

    def __init__(self, chunks: list[FakeChunk]) -> None:
        self._chunks = chunks

    def __aiter__(self) -> AsyncIterator[FakeChunk]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[FakeChunk]:
        for chunk in self._chunks:
            yield chunk


def _make_fake_client(*call_responses: list[FakeChunk]) -> AsyncMock:
    """Create a mock AsyncOpenAI client that returns the given chunk sequences.

    Each argument is a list of chunks for one call to chat.completions.create().
    """
    client = AsyncMock()
    side_effects = [FakeAsyncStream(chunks) for chunks in call_responses]
    client.chat.completions.create = AsyncMock(side_effect=side_effects)
    return client


def _make_config(**overrides: Any) -> KzConfig:
    """Create a KzConfig for testing."""
    defaults = {
        "model": "gpt-4o-test",
        "max_turns": 100,
        "temperature": 0.0,
        "max_tokens": 4096,
    }
    defaults.update(overrides)
    return KzConfig(**defaults)


# ---------------------------------------------------------------------------
# ToolRegistry tests
# ---------------------------------------------------------------------------


class TestToolRegistry:
    """Tests for the ToolRegistry."""

    def test_register_and_list(self) -> None:
        """Registering a tool makes it available in the registry."""
        registry = ToolRegistry()

        async def dummy(**kwargs: Any) -> str:
            return "ok"

        registry.register(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
            executor=dummy,
        )

        assert registry.has_tool("test_tool")
        assert "test_tool" in registry.tool_names
        assert not registry.has_tool("nonexistent")

    def test_openai_format(self) -> None:
        """Tools are exported in OpenAI function-calling format."""
        registry = ToolRegistry()

        async def dummy(**kwargs: Any) -> str:
            return "ok"

        registry.register(
            name="my_tool",
            description="Does things",
            parameters={"type": "object", "properties": {"x": {"type": "string"}}},
            executor=dummy,
        )

        tools = registry.get_openai_tools()
        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "my_tool"
        assert tools[0]["function"]["description"] == "Does things"

    async def test_execute_tool(self) -> None:
        """Executing a tool calls the registered executor."""
        registry = ToolRegistry()
        called_with: dict[str, Any] = {}

        async def my_tool(path: str = "", query: str = "") -> str:
            called_with["path"] = path
            called_with["query"] = query
            return "tool result"

        registry.register(
            name="my_tool",
            description="test",
            parameters={"type": "object", "properties": {}},
            executor=my_tool,
        )

        result = await registry.execute("my_tool", {"path": "/tmp", "query": "hello"})
        assert result == "tool result"
        assert called_with["path"] == "/tmp"
        assert called_with["query"] == "hello"

    async def test_execute_unknown_tool(self) -> None:
        """Executing an unknown tool raises KeyError."""
        registry = ToolRegistry()
        with pytest.raises(KeyError, match="Unknown tool"):
            await registry.execute("nonexistent", {})


# ---------------------------------------------------------------------------
# Conversation tests
# ---------------------------------------------------------------------------


class TestConversation:
    """Tests for conversation history management."""

    def test_system_message(self) -> None:
        """System message is set at the start of the conversation."""
        conv = Conversation()
        conv.add_system("You are helpful.")
        assert conv.messages[0] == {"role": "system", "content": "You are helpful."}

    def test_system_message_replacement(self) -> None:
        """Setting system message replaces the existing one."""
        conv = Conversation()
        conv.add_system("First")
        conv.add_system("Second")
        system_msgs = [m for m in conv.messages if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert system_msgs[0]["content"] == "Second"

    def test_user_message(self) -> None:
        """User messages are appended to the conversation."""
        conv = Conversation()
        conv.add_user("Hello")
        assert conv.messages[-1] == {"role": "user", "content": "Hello"}

    def test_assistant_message_text(self) -> None:
        """Assistant text messages are appended correctly."""
        conv = Conversation()
        conv.add_assistant("Hi there!")
        msg = conv.messages[-1]
        assert msg["role"] == "assistant"
        assert msg["content"] == "Hi there!"
        assert "tool_calls" not in msg

    def test_assistant_message_with_tool_calls(self) -> None:
        """Assistant messages with tool calls include both content and calls."""
        conv = Conversation()
        tool_calls = [
            {"id": "tc_1", "type": "function", "function": {"name": "test", "arguments": "{}"}}
        ]
        conv.add_assistant("Let me check.", tool_calls=tool_calls)
        msg = conv.messages[-1]
        assert msg["role"] == "assistant"
        assert msg["content"] == "Let me check."
        assert msg["tool_calls"] == tool_calls

    def test_tool_result(self) -> None:
        """Tool results are appended with the correct structure."""
        conv = Conversation()
        conv.add_tool_result("tc_1", "test_tool", "some result")
        msg = conv.messages[-1]
        assert msg["role"] == "tool"
        assert msg["tool_call_id"] == "tc_1"
        assert msg["name"] == "test_tool"
        assert msg["content"] == "some result"


# ---------------------------------------------------------------------------
# UsageTracker tests
# ---------------------------------------------------------------------------


class TestUsageTracker:
    """Tests for token usage tracking."""

    def test_add_usage(self) -> None:
        """Usage stats accumulate across multiple calls."""
        tracker = UsageTracker()
        tracker.add({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})
        tracker.add({"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30})
        assert tracker.prompt_tokens == 30
        assert tracker.completion_tokens == 15
        assert tracker.total_tokens == 45

    def test_increment_turn(self) -> None:
        """Turn counter increments correctly."""
        tracker = UsageTracker()
        tracker.increment_turn()
        tracker.increment_turn()
        assert tracker.turns == 2

    def test_empty_usage_dict(self) -> None:
        """Adding an empty dict does not change counters."""
        tracker = UsageTracker()
        tracker.add({})
        assert tracker.total_tokens == 0


# ---------------------------------------------------------------------------
# AgentLoop tests — text-only response
# ---------------------------------------------------------------------------


class TestAgentLoopTextResponse:
    """Test the agent loop with text-only (no tool calls) responses."""

    async def test_simple_text_response(self) -> None:
        """User message -> model text response -> text yielded."""
        response_text = "Hello! How can I help you?"
        chunks = _text_chunks(response_text)
        client = _make_fake_client(chunks)
        config = _make_config()
        tools = ToolRegistry()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="Test system")

        collected: list[str] = []
        async for chunk in loop.run_turn("Hi there"):
            collected.append(chunk)

        full_text = "".join(collected)
        assert full_text == response_text

    async def test_conversation_history_after_text_response(self) -> None:
        """After a text-only response, conversation has user + assistant messages."""
        chunks = _text_chunks("Response text")
        client = _make_fake_client(chunks)
        config = _make_config()
        tools = ToolRegistry()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="Sys")

        async for _ in loop.run_turn("User input"):
            pass

        msgs = loop.conversation.messages
        # System + user + assistant
        assert len(msgs) == 3
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert msgs[1]["content"] == "User input"
        assert msgs[2]["role"] == "assistant"
        assert msgs[2]["content"] == "Response text"

    async def test_usage_tracked(self) -> None:
        """Token usage is tracked after a response."""
        chunks = _text_chunks("Short")
        client = _make_fake_client(chunks)
        config = _make_config()
        tools = ToolRegistry()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        async for _ in loop.run_turn("Test"):
            pass

        assert loop.usage.turns == 1
        assert loop.usage.total_tokens == 15  # from FakeUsage defaults


# ---------------------------------------------------------------------------
# AgentLoop tests — tool call response
# ---------------------------------------------------------------------------


class TestAgentLoopToolCalls:
    """Test the agent loop with tool call responses."""

    async def test_single_tool_call(self) -> None:
        """User -> model tool call -> tool executed -> model final response."""
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

        # First call: model requests tool call
        tool_call_chunks = _tool_call_chunks(
            [
                {"id": "call_001", "name": "list_files", "arguments": '{"path": "."}'},
            ]
        )

        # Second call: model responds with text after seeing tool result
        final_text_chunks = _text_chunks("I found 2 files: file1.py and file2.py")

        client = _make_fake_client(tool_call_chunks, final_text_chunks)
        config = _make_config()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        collected: list[str] = []
        async for chunk in loop.run_turn("List files"):
            collected.append(chunk)

        full_text = "".join(collected)
        assert "file1.py" in full_text
        assert "file2.py" in full_text

        # Verify conversation history includes tool call + result
        msgs = loop.conversation.messages
        roles = [m["role"] for m in msgs]
        assert "tool" in roles
        tool_msg = next(m for m in msgs if m["role"] == "tool")
        assert tool_msg["name"] == "list_files"
        assert "file1.py" in tool_msg["content"]

    async def test_multiple_parallel_tool_calls(self) -> None:
        """Multiple tool calls in one response are executed in parallel."""
        tools = ToolRegistry()
        execution_order: list[str] = []

        async def tool_a(x: str = "") -> str:
            execution_order.append("a_start")
            await asyncio.sleep(0.01)
            execution_order.append("a_end")
            return f"result_a({x})"

        async def tool_b(y: str = "") -> str:
            execution_order.append("b_start")
            await asyncio.sleep(0.01)
            execution_order.append("b_end")
            return f"result_b({y})"

        tools.register(
            "tool_a", "Tool A", {"type": "object", "properties": {"x": {"type": "string"}}}, tool_a
        )
        tools.register(
            "tool_b", "Tool B", {"type": "object", "properties": {"y": {"type": "string"}}}, tool_b
        )

        # Model requests both tools in one response
        parallel_chunks = _tool_call_chunks(
            [
                {"id": "call_a", "name": "tool_a", "arguments": '{"x": "hello"}'},
                {"id": "call_b", "name": "tool_b", "arguments": '{"y": "world"}'},
            ]
        )

        final_chunks = _text_chunks("Both tools completed.")

        client = _make_fake_client(parallel_chunks, final_chunks)
        config = _make_config()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        collected: list[str] = []
        async for chunk in loop.run_turn("Run both"):
            collected.append(chunk)

        # Both tools should have been called (parallel via asyncio.gather)
        assert "a_start" in execution_order
        assert "b_start" in execution_order

        # Verify both tool results are in conversation
        tool_msgs = [m for m in loop.conversation.messages if m["role"] == "tool"]
        assert len(tool_msgs) == 2
        tool_names = {m["name"] for m in tool_msgs}
        assert tool_names == {"tool_a", "tool_b"}

    async def test_tool_execution_error_handled(self) -> None:
        """Tool execution errors are captured and sent back to the model."""
        tools = ToolRegistry()

        async def failing_tool() -> str:
            raise RuntimeError("Something went wrong")

        tools.register(
            "failing", "A failing tool", {"type": "object", "properties": {}}, failing_tool
        )

        tool_chunks = _tool_call_chunks(
            [
                {"id": "call_fail", "name": "failing", "arguments": "{}"},
            ]
        )

        final_chunks = _text_chunks("The tool encountered an error.")

        client = _make_fake_client(tool_chunks, final_chunks)
        config = _make_config()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        collected: list[str] = []
        async for chunk in loop.run_turn("Try the tool"):
            collected.append(chunk)

        # The error should be in the tool result message
        tool_msg = next(m for m in loop.conversation.messages if m["role"] == "tool")
        assert "error" in tool_msg["content"].lower()
        assert "Something went wrong" in tool_msg["content"]

    async def test_unknown_tool_handled(self) -> None:
        """Unknown tool names in model responses are handled gracefully."""
        tools = ToolRegistry()

        tool_chunks = _tool_call_chunks(
            [
                {"id": "call_unknown", "name": "nonexistent_tool", "arguments": "{}"},
            ]
        )

        final_chunks = _text_chunks("That tool does not exist.")

        client = _make_fake_client(tool_chunks, final_chunks)
        config = _make_config()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        collected: list[str] = []
        async for chunk in loop.run_turn("Use a fake tool"):
            collected.append(chunk)

        tool_msg = next(m for m in loop.conversation.messages if m["role"] == "tool")
        assert "Unknown tool" in tool_msg["content"]

    async def test_malformed_arguments_handled(self) -> None:
        """Malformed JSON in tool call arguments is handled gracefully."""
        tools = ToolRegistry()

        async def my_tool(**kwargs: Any) -> str:
            return "ok"

        tools.register("my_tool", "test", {"type": "object", "properties": {}}, my_tool)

        # Create chunks manually with bad JSON in arguments
        chunks: list[FakeChunk] = []
        chunks.append(
            FakeChunk(
                choices=[
                    FakeChoice(
                        delta=FakeDelta(
                            tool_calls=[
                                FakeToolCallDelta(
                                    index=0,
                                    id="call_bad",
                                    type="function",
                                    function=FakeFunctionCall(name="my_tool", arguments=""),
                                )
                            ]
                        )
                    )
                ]
            )
        )
        chunks.append(
            FakeChunk(
                choices=[
                    FakeChoice(
                        delta=FakeDelta(
                            tool_calls=[
                                FakeToolCallDelta(
                                    index=0,
                                    function=FakeFunctionCall(arguments="{not valid json"),
                                )
                            ]
                        )
                    )
                ]
            )
        )
        chunks.append(
            FakeChunk(choices=[FakeChoice(delta=FakeDelta(), finish_reason="tool_calls")])
        )
        chunks.append(FakeChunk(choices=[], usage=FakeUsage()))

        final_chunks = _text_chunks("Handled the error.")

        client = _make_fake_client(chunks, final_chunks)
        config = _make_config()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        collected: list[str] = []
        async for chunk in loop.run_turn("Bad args"):
            collected.append(chunk)

        # Should have a tool result with an error message
        tool_msg = next(m for m in loop.conversation.messages if m["role"] == "tool")
        assert "error" in tool_msg["content"].lower()


# ---------------------------------------------------------------------------
# AgentLoop tests — max turns limit
# ---------------------------------------------------------------------------


class TestAgentLoopMaxTurns:
    """Test max turns enforcement."""

    async def test_max_turns_stops_loop(self) -> None:
        """The loop stops after max_turns even if model keeps requesting tools."""
        tools = ToolRegistry()

        async def echo_tool(text: str = "") -> str:
            return f"echo: {text}"

        tools.register(
            "echo",
            "Echo text",
            {"type": "object", "properties": {"text": {"type": "string"}}},
            echo_tool,
        )

        # Create enough tool-call responses to exceed max_turns=3
        tool_responses = []
        for i in range(5):
            tool_responses.append(
                _tool_call_chunks(
                    [
                        {"id": f"call_{i}", "name": "echo", "arguments": f'{{"text": "turn {i}"}}'},
                    ]
                )
            )

        client = _make_fake_client(*tool_responses)
        config = _make_config(max_turns=3)

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        collected: list[str] = []
        async for chunk in loop.run_turn("Keep going"):
            collected.append(chunk)

        # Should have stopped after max_turns (3) API calls, not all 5
        assert loop.usage.turns <= 3

    async def test_max_turns_one_allows_single_response(self) -> None:
        """With max_turns=1, exactly one completion call is made."""
        chunks = _text_chunks("Single turn response")
        client = _make_fake_client(chunks)
        config = _make_config(max_turns=1)
        tools = ToolRegistry()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        collected: list[str] = []
        async for chunk in loop.run_turn("One shot"):
            collected.append(chunk)

        assert "".join(collected) == "Single turn response"
        assert loop.usage.turns == 1


# ---------------------------------------------------------------------------
# AgentLoop tests — interrupt handling
# ---------------------------------------------------------------------------


class TestAgentLoopInterrupt:
    """Test graceful interruption."""

    async def test_interrupt_stops_tool_loop(self) -> None:
        """Calling interrupt() during a tool-call loop stops further iterations.

        We set up a scenario where the model requests a tool call, and we
        interrupt after the tool executes. The loop should not make another
        API call after the interrupt.
        """
        tools = ToolRegistry()

        async def my_tool(x: str = "") -> str:
            return f"result({x})"

        tools.register(
            "my_tool", "test", {"type": "object", "properties": {"x": {"type": "string"}}}, my_tool
        )

        # First call: tool call. Second call would be a text response, but
        # we will interrupt before it happens.
        tool_chunks = _tool_call_chunks(
            [
                {"id": "call_1", "name": "my_tool", "arguments": '{"x": "test"}'},
            ]
        )
        text_chunks = _text_chunks("This should not appear")

        client = _make_fake_client(tool_chunks, text_chunks)
        config = _make_config()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        # Start the turn, then interrupt after the first API call + tool execution
        collected: list[str] = []
        turn_gen = loop.run_turn("Go")

        # Consume what is available from the first (tool-call) response:
        # run_turn yields nothing for a tool-call-only response, then loops
        # to the next API call. We need to interrupt between calls.
        # The simplest way: interrupt after the first API response is processed.
        # Since _stream_completion checks _interrupted, setting it after tool
        # execution will cause the next iteration's _stream_completion to
        # return an empty result and the loop to exit.

        # Patch _execute_tool_calls to interrupt after executing
        original_execute = loop._execute_tool_calls

        async def interrupt_after_execute(tc: list[dict[str, Any]]) -> None:
            await original_execute(tc)
            loop.interrupt()

        loop._execute_tool_calls = interrupt_after_execute  # type: ignore[assignment]

        async for chunk in turn_gen:
            collected.append(chunk)

        # The second API call should have been skipped due to interrupt.
        # The client was called once (tool call response), not twice.
        assert client.chat.completions.create.call_count == 1
        assert loop._interrupted is True


# ---------------------------------------------------------------------------
# AgentLoop tests — multi-turn conversation
# ---------------------------------------------------------------------------


class TestAgentLoopMultiTurn:
    """Test multi-turn conversations maintain proper history."""

    async def test_two_turn_conversation(self) -> None:
        """Two sequential user turns accumulate in conversation history."""
        response1_chunks = _text_chunks("Answer 1")
        response2_chunks = _text_chunks("Answer 2")

        client = _make_fake_client(response1_chunks, response2_chunks)
        config = _make_config()
        tools = ToolRegistry()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="System")

        # Turn 1
        async for _ in loop.run_turn("Question 1"):
            pass

        # Turn 2
        async for _ in loop.run_turn("Question 2"):
            pass

        msgs = loop.conversation.messages
        roles = [m["role"] for m in msgs]
        assert roles == ["system", "user", "assistant", "user", "assistant"]
        assert msgs[1]["content"] == "Question 1"
        assert msgs[2]["content"] == "Answer 1"
        assert msgs[3]["content"] == "Question 2"
        assert msgs[4]["content"] == "Answer 2"

    async def test_usage_accumulates_across_turns(self) -> None:
        """Token usage accumulates across multiple turns."""
        response1 = _text_chunks("A1")
        response2 = _text_chunks("A2")

        client = _make_fake_client(response1, response2)
        config = _make_config()
        tools = ToolRegistry()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        async for _ in loop.run_turn("Q1"):
            pass
        async for _ in loop.run_turn("Q2"):
            pass

        assert loop.usage.turns == 2
        assert loop.usage.total_tokens == 30  # 15 + 15 from FakeUsage


# ---------------------------------------------------------------------------
# AgentLoop tests — print mode
# ---------------------------------------------------------------------------


class TestAgentLoopPrintMode:
    """Test the non-interactive print mode."""

    async def test_run_print_returns_full_text(self) -> None:
        """run_print() returns the complete response text."""
        chunks = _text_chunks("The answer is 42.")
        client = _make_fake_client(chunks)
        config = _make_config()
        tools = ToolRegistry()

        loop = AgentLoop(config=config, tools=tools, client=client, system_prompt="")

        result = await loop.run_print("What is the answer?")
        assert result == "The answer is 42."
