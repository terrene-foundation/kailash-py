# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for S8: Multi-Provider LLM Adapter.

Tier 1 (unit) tests -- mocks are permitted.

Tests cover:
    - StreamEvent dataclass construction and fields
    - StreamingChatAdapter protocol structural conformance
    - Adapter registry: provider selection by name
    - Adapter registry: auto-detection from model name prefix
    - Adapter registry: default fallback to OpenAI
    - Tool definition conversion for Anthropic
    - Tool definition conversion for Google Gemini
    - Message conversion for Anthropic
    - Message conversion for Ollama
    - OpenAI adapter stream event mapping
    - Anthropic adapter stream event mapping
    - Config.provider wiring into AgentLoop
    - StructuredLLMAdapter protocol conformance
    - Structured adapter factory dispatch
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen_agents.delegate.adapters.protocol import StreamEvent, StreamingChatAdapter
from kaizen_agents.delegate.adapters.registry import get_adapter, get_adapter_for_model
from kaizen_agents.delegate.config.loader import KzConfig
from kaizen_agents.delegate.loop import AgentLoop, ToolRegistry


# ---------------------------------------------------------------------------
# S8-001: StreamEvent dataclass
# ---------------------------------------------------------------------------


class TestStreamEvent:
    """Test the StreamEvent dataclass."""

    def test_text_delta_event(self) -> None:
        """StreamEvent with text_delta carries content and delta_text."""
        event = StreamEvent(
            event_type="text_delta",
            content="Hello world",
            delta_text="world",
        )
        assert event.event_type == "text_delta"
        assert event.content == "Hello world"
        assert event.delta_text == "world"
        assert event.tool_calls == []
        assert event.usage == {}

    def test_tool_call_start_event(self) -> None:
        """StreamEvent with tool_call_start has correct type."""
        event = StreamEvent(event_type="tool_call_start")
        assert event.event_type == "tool_call_start"

    def test_done_event_with_usage(self) -> None:
        """Done event carries tool_calls, finish_reason, and usage."""
        event = StreamEvent(
            event_type="done",
            content="Final text",
            tool_calls=[{"id": "call_1", "type": "function", "function": {"name": "test", "arguments": "{}"}}],
            finish_reason="stop",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )
        assert event.event_type == "done"
        assert event.finish_reason == "stop"
        assert len(event.tool_calls) == 1
        assert event.usage["total_tokens"] == 15

    def test_all_event_types(self) -> None:
        """All five event types can be constructed."""
        types = ["text_delta", "tool_call_start", "tool_call_delta", "tool_call_end", "done"]
        for t in types:
            event = StreamEvent(event_type=t)
            assert event.event_type == t


# ---------------------------------------------------------------------------
# S8-001: StreamingChatAdapter protocol
# ---------------------------------------------------------------------------


class TestStreamingChatAdapterProtocol:
    """Test that the protocol is correctly defined as runtime_checkable."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """StreamingChatAdapter supports isinstance checks."""

        class FakeAdapter:
            async def stream_chat(
                self,
                messages: list[dict[str, Any]],
                tools: list[dict[str, Any]] | None = None,
                **kwargs: Any,
            ) -> AsyncGenerator[StreamEvent, None]:
                yield StreamEvent(event_type="done")

        adapter = FakeAdapter()
        assert isinstance(adapter, StreamingChatAdapter)

    def test_non_conforming_class_not_adapter(self) -> None:
        """A class without stream_chat is not a StreamingChatAdapter."""

        class NotAnAdapter:
            pass

        assert not isinstance(NotAnAdapter(), StreamingChatAdapter)


# ---------------------------------------------------------------------------
# S8-002 through S8-005: Adapter registry selection
# ---------------------------------------------------------------------------


class TestAdapterRegistry:
    """Test provider selection and auto-detection in the adapter registry."""

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_get_adapter_openai(self) -> None:
        """get_adapter('openai') creates an OpenAI adapter."""
        from kaizen_agents.delegate.adapters.openai_adapter import OpenAIStreamAdapter

        adapter = get_adapter("openai", model="test-model")
        assert isinstance(adapter, OpenAIStreamAdapter)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_get_adapter_openai_case_insensitive(self) -> None:
        """Provider names are case-insensitive."""
        from kaizen_agents.delegate.adapters.openai_adapter import OpenAIStreamAdapter

        adapter = get_adapter("OpenAI", model="test-model")
        assert isinstance(adapter, OpenAIStreamAdapter)

    def test_get_adapter_unknown_provider_raises(self) -> None:
        """Unknown provider name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown provider"):
            get_adapter("nonexistent", model="test")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_get_adapter_for_model_openai_default(self) -> None:
        """Model without known prefix defaults to OpenAI."""
        from kaizen_agents.delegate.adapters.openai_adapter import OpenAIStreamAdapter

        adapter = get_adapter_for_model("gpt-4o")
        assert isinstance(adapter, OpenAIStreamAdapter)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_get_adapter_for_model_claude_prefix(self) -> None:
        """Model starting with 'claude-' auto-detects Anthropic."""
        from kaizen_agents.delegate.adapters.anthropic_adapter import AnthropicStreamAdapter

        adapter = get_adapter_for_model("claude-sonnet-4-6")
        assert isinstance(adapter, AnthropicStreamAdapter)

    @patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"})
    def test_get_adapter_for_model_gemini_prefix(self) -> None:
        """Model starting with 'gemini-' auto-detects Google."""
        from kaizen_agents.delegate.adapters.google_adapter import GoogleStreamAdapter

        adapter = get_adapter_for_model("gemini-2.0-flash")
        assert isinstance(adapter, GoogleStreamAdapter)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_explicit_provider_overrides_model_prefix(self) -> None:
        """Explicit provider takes precedence over model name auto-detection."""
        from kaizen_agents.delegate.adapters.openai_adapter import OpenAIStreamAdapter

        # Model says "claude-" but explicit provider says "openai"
        adapter = get_adapter_for_model("claude-sonnet-4-6", provider="openai")
        assert isinstance(adapter, OpenAIStreamAdapter)

    def test_ollama_adapter_creation(self) -> None:
        """Ollama adapter can be created (no API key needed)."""
        from kaizen_agents.delegate.adapters.ollama_adapter import OllamaStreamAdapter

        adapter = get_adapter("ollama", model="llama3")
        assert isinstance(adapter, OllamaStreamAdapter)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_unknown_model_prefix_defaults_openai(self) -> None:
        """Model with no known prefix falls back to OpenAI."""
        from kaizen_agents.delegate.adapters.openai_adapter import OpenAIStreamAdapter

        adapter = get_adapter_for_model("custom-model-v2")
        assert isinstance(adapter, OpenAIStreamAdapter)


# ---------------------------------------------------------------------------
# S8-003: Anthropic message/tool conversion
# ---------------------------------------------------------------------------


class TestAnthropicConversion:
    """Test message and tool format conversion for Anthropic."""

    def test_convert_messages_separates_system(self) -> None:
        """System message is extracted from the message list."""
        from kaizen_agents.delegate.adapters.anthropic_adapter import _convert_messages_for_anthropic

        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        system, msgs = _convert_messages_for_anthropic(messages)
        assert system == "You are helpful."
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"

    def test_convert_messages_tool_results(self) -> None:
        """Tool result messages become user messages with tool_result blocks."""
        from kaizen_agents.delegate.adapters.anthropic_adapter import _convert_messages_for_anthropic

        messages = [
            {"role": "tool", "tool_call_id": "call_1", "name": "search", "content": "result data"},
        ]
        _, msgs = _convert_messages_for_anthropic(messages)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"][0]["type"] == "tool_result"
        assert msgs[0]["content"][0]["tool_use_id"] == "call_1"

    def test_convert_messages_assistant_with_tool_calls(self) -> None:
        """Assistant messages with tool_calls become content blocks."""
        from kaizen_agents.delegate.adapters.anthropic_adapter import _convert_messages_for_anthropic

        messages = [
            {
                "role": "assistant",
                "content": "Let me search",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "search", "arguments": '{"q": "test"}'},
                    }
                ],
            },
        ]
        _, msgs = _convert_messages_for_anthropic(messages)
        assert len(msgs) == 1
        blocks = msgs[0]["content"]
        assert blocks[0]["type"] == "text"
        assert blocks[1]["type"] == "tool_use"
        assert blocks[1]["name"] == "search"

    def test_convert_tools_format(self) -> None:
        """OpenAI tool defs are converted to Anthropic format."""
        from kaizen_agents.delegate.adapters.anthropic_adapter import _convert_tools_for_anthropic

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search the web",
                    "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
                },
            }
        ]
        result = _convert_tools_for_anthropic(tools)
        assert len(result) == 1
        assert result[0]["name"] == "search"
        assert result[0]["description"] == "Search the web"
        assert "input_schema" in result[0]

    def test_convert_tools_empty_returns_empty(self) -> None:
        """Empty or None tools returns empty list."""
        from kaizen_agents.delegate.adapters.anthropic_adapter import _convert_tools_for_anthropic

        assert _convert_tools_for_anthropic(None) == []
        assert _convert_tools_for_anthropic([]) == []


# ---------------------------------------------------------------------------
# S8-004: Google Gemini message/tool conversion
# ---------------------------------------------------------------------------


class TestGoogleConversion:
    """Test message and tool format conversion for Google Gemini."""

    def test_convert_messages_system_extraction(self) -> None:
        """System message is extracted for Gemini's system_instruction."""
        from kaizen_agents.delegate.adapters.google_adapter import _convert_messages_for_gemini

        messages = [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Hello"},
        ]
        system, contents = _convert_messages_for_gemini(messages)
        assert system == "Be concise."
        assert len(contents) == 1
        assert contents[0]["role"] == "user"

    def test_convert_messages_role_mapping(self) -> None:
        """Assistant role maps to 'model' role in Gemini."""
        from kaizen_agents.delegate.adapters.google_adapter import _convert_messages_for_gemini

        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        _, contents = _convert_messages_for_gemini(messages)
        assert contents[0]["role"] == "user"
        assert contents[1]["role"] == "model"

    def test_convert_messages_tool_results(self) -> None:
        """Tool results become function_response parts."""
        from kaizen_agents.delegate.adapters.google_adapter import _convert_messages_for_gemini

        messages = [
            {"role": "tool", "name": "search", "content": "results"},
        ]
        _, contents = _convert_messages_for_gemini(messages)
        assert contents[0]["parts"][0]["function_response"]["name"] == "search"

    def test_convert_tools_format(self) -> None:
        """OpenAI tool defs become Gemini function_declarations."""
        from kaizen_agents.delegate.adapters.google_adapter import _convert_tools_for_gemini

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "calc",
                    "description": "Calculator",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = _convert_tools_for_gemini(tools)
        assert result is not None
        assert len(result) == 1
        assert "function_declarations" in result[0]
        assert result[0]["function_declarations"][0]["name"] == "calc"

    def test_convert_tools_none_returns_none(self) -> None:
        """None tools returns None."""
        from kaizen_agents.delegate.adapters.google_adapter import _convert_tools_for_gemini

        assert _convert_tools_for_gemini(None) is None


# ---------------------------------------------------------------------------
# S8-005: Ollama message conversion
# ---------------------------------------------------------------------------


class TestOllamaConversion:
    """Test message conversion for Ollama."""

    def test_convert_messages_passes_through(self) -> None:
        """Standard messages pass through to Ollama format."""
        from kaizen_agents.delegate.adapters.ollama_adapter import _convert_messages_for_ollama

        messages = [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        result = _convert_messages_for_ollama(messages)
        assert len(result) == 3
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"
        assert result[2]["role"] == "assistant"

    def test_convert_messages_skips_unknown_roles(self) -> None:
        """Messages with unknown roles are skipped."""
        from kaizen_agents.delegate.adapters.ollama_adapter import _convert_messages_for_ollama

        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "unknown", "content": "skip me"},
        ]
        result = _convert_messages_for_ollama(messages)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# S8-002: OpenAI adapter streaming event mapping
# ---------------------------------------------------------------------------


class TestOpenAIAdapterStreaming:
    """Test that OpenAI adapter maps chunks to StreamEvent correctly."""

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    async def test_text_streaming_yields_text_delta_events(self) -> None:
        """Text chunks produce text_delta events with accumulated content."""
        from kaizen_agents.delegate.adapters.openai_adapter import OpenAIStreamAdapter

        adapter = OpenAIStreamAdapter(api_key="test-key", default_model="test-model")

        # Build fake chunks (reuse the patterns from test_streaming)
        @dataclass
        class FakeFunctionCall:
            name: str | None = None
            arguments: str | None = None

        @dataclass
        class FakeToolCallDelta:
            index: int
            id: str | None = None
            type: str | None = None
            function: FakeFunctionCall | None = None

        @dataclass
        class FakeDelta:
            content: str | None = None
            tool_calls: list[FakeToolCallDelta] | None = None

        @dataclass
        class FakeChoice:
            delta: FakeDelta
            finish_reason: str | None = None

        @dataclass
        class FakeUsage:
            prompt_tokens: int = 10
            completion_tokens: int = 5
            total_tokens: int = 15

        @dataclass
        class FakeChunk:
            choices: list[FakeChoice] = field(default_factory=list)
            model: str = "test-model"
            usage: FakeUsage | None = None

        chunks = [
            FakeChunk(choices=[FakeChoice(delta=FakeDelta(content="Hello"))]),
            FakeChunk(choices=[FakeChoice(delta=FakeDelta(content=" world"))]),
            FakeChunk(choices=[FakeChoice(delta=FakeDelta(), finish_reason="stop")]),
            FakeChunk(choices=[], usage=FakeUsage()),
        ]

        class FakeStream:
            def __init__(self, chunks: list) -> None:
                self._chunks = chunks

            def __aiter__(self):
                return self._iter()

            async def _iter(self):
                for c in self._chunks:
                    yield c

        adapter._client = AsyncMock()
        adapter._client.chat.completions.create = AsyncMock(return_value=FakeStream(chunks))

        events: list[StreamEvent] = []
        async for event in adapter.stream_chat(
            messages=[{"role": "user", "content": "Hi"}],
            model="test-model",
        ):
            events.append(event)

        # Should have text_delta events, then done
        text_events = [e for e in events if e.event_type == "text_delta"]
        assert len(text_events) == 2
        assert text_events[0].delta_text == "Hello"
        assert text_events[1].delta_text == " world"
        assert text_events[1].content == "Hello world"

        done_events = [e for e in events if e.event_type == "done"]
        assert len(done_events) == 1
        assert done_events[0].content == "Hello world"
        assert done_events[0].finish_reason == "stop"
        assert done_events[0].usage["total_tokens"] == 15

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    async def test_tool_call_streaming_events(self) -> None:
        """Tool call chunks produce tool_call_start, tool_call_delta, tool_call_end, done."""
        from kaizen_agents.delegate.adapters.openai_adapter import OpenAIStreamAdapter

        adapter = OpenAIStreamAdapter(api_key="test-key", default_model="test-model")

        @dataclass
        class FakeFunctionCall:
            name: str | None = None
            arguments: str | None = None

        @dataclass
        class FakeToolCallDelta:
            index: int
            id: str | None = None
            type: str | None = None
            function: FakeFunctionCall | None = None

        @dataclass
        class FakeDelta:
            content: str | None = None
            tool_calls: list[FakeToolCallDelta] | None = None

        @dataclass
        class FakeChoice:
            delta: FakeDelta
            finish_reason: str | None = None

        @dataclass
        class FakeUsage:
            prompt_tokens: int = 10
            completion_tokens: int = 5
            total_tokens: int = 15

        @dataclass
        class FakeChunk:
            choices: list[FakeChoice] = field(default_factory=list)
            model: str = "test-model"
            usage: FakeUsage | None = None

        chunks = [
            # Tool call start
            FakeChunk(choices=[FakeChoice(delta=FakeDelta(
                tool_calls=[FakeToolCallDelta(
                    index=0, id="call_1", type="function",
                    function=FakeFunctionCall(name="search", arguments=""),
                )]
            ))]),
            # Tool call delta (arguments)
            FakeChunk(choices=[FakeChoice(delta=FakeDelta(
                tool_calls=[FakeToolCallDelta(
                    index=0,
                    function=FakeFunctionCall(arguments='{"q": "test"}'),
                )]
            ))]),
            # Finish
            FakeChunk(choices=[FakeChoice(delta=FakeDelta(), finish_reason="tool_calls")]),
            FakeChunk(choices=[], usage=FakeUsage()),
        ]

        class FakeStream:
            def __init__(self, chunks: list) -> None:
                self._chunks = chunks

            def __aiter__(self):
                return self._iter()

            async def _iter(self):
                for c in self._chunks:
                    yield c

        adapter._client = AsyncMock()
        adapter._client.chat.completions.create = AsyncMock(return_value=FakeStream(chunks))

        events: list[StreamEvent] = []
        async for event in adapter.stream_chat(
            messages=[{"role": "user", "content": "search for test"}],
            tools=[{
                "type": "function",
                "function": {"name": "search", "description": "Search", "parameters": {}},
            }],
            model="test-model",
        ):
            events.append(event)

        types = [e.event_type for e in events]
        assert "tool_call_start" in types
        assert "tool_call_delta" in types
        assert "tool_call_end" in types
        assert "done" in types

        done = next(e for e in events if e.event_type == "done")
        assert len(done.tool_calls) == 1
        assert done.tool_calls[0]["function"]["name"] == "search"
        assert done.finish_reason == "tool_calls"


# ---------------------------------------------------------------------------
# S8-006: AgentLoop wiring with adapter
# ---------------------------------------------------------------------------


class TestAgentLoopAdapterWiring:
    """Test that AgentLoop can use a StreamingChatAdapter."""

    async def test_adapter_based_text_streaming(self) -> None:
        """AgentLoop uses adapter for streaming when provided."""

        class FakeAdapter:
            """A fake adapter that yields text events."""

            async def stream_chat(
                self,
                messages: list[dict[str, Any]],
                tools: list[dict[str, Any]] | None = None,
                **kwargs: Any,
            ) -> AsyncGenerator[StreamEvent, None]:
                yield StreamEvent(
                    event_type="text_delta",
                    content="Hello",
                    delta_text="Hello",
                )
                yield StreamEvent(
                    event_type="text_delta",
                    content="Hello world",
                    delta_text=" world",
                )
                yield StreamEvent(
                    event_type="done",
                    content="Hello world",
                    finish_reason="stop",
                    usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                )

        config = KzConfig(model="test-model", max_turns=10)
        tools = ToolRegistry()

        loop = AgentLoop(
            config=config,
            tools=tools,
            adapter=FakeAdapter(),
            system_prompt="Test",
        )

        collected: list[str] = []
        async for chunk in loop.run_turn("Hi"):
            collected.append(chunk)

        assert "".join(collected) == "Hello world"
        assert loop.usage.total_tokens == 15

    async def test_adapter_tool_call_round_trip(self) -> None:
        """AgentLoop executes tool calls from adapter events and loops."""
        call_count = 0

        class FakeAdapter:
            async def stream_chat(
                self,
                messages: list[dict[str, Any]],
                tools: list[dict[str, Any]] | None = None,
                **kwargs: Any,
            ) -> AsyncGenerator[StreamEvent, None]:
                nonlocal call_count
                call_count += 1

                if call_count == 1:
                    # First call: request a tool call
                    yield StreamEvent(
                        event_type="tool_call_start",
                        content="",
                    )
                    yield StreamEvent(
                        event_type="done",
                        content="",
                        tool_calls=[{
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "greet",
                                "arguments": '{"name": "Alice"}',
                            },
                        }],
                        finish_reason="tool_calls",
                        usage={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
                    )
                else:
                    # Second call: text response
                    yield StreamEvent(
                        event_type="text_delta",
                        content="Done!",
                        delta_text="Done!",
                    )
                    yield StreamEvent(
                        event_type="done",
                        content="Done!",
                        finish_reason="stop",
                        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    )

        config = KzConfig(model="test-model", max_turns=10)
        tools = ToolRegistry()

        async def greet(name: str = "") -> str:
            return f"Hello, {name}!"

        tools.register(
            "greet", "Greet someone",
            {"type": "object", "properties": {"name": {"type": "string"}}},
            greet,
        )

        loop = AgentLoop(
            config=config,
            tools=tools,
            adapter=FakeAdapter(),
            system_prompt="Test",
        )

        collected: list[str] = []
        async for chunk in loop.run_turn("Greet Alice"):
            collected.append(chunk)

        assert "".join(collected) == "Done!"
        assert call_count == 2

        # Verify tool result is in conversation
        tool_msgs = [m for m in loop.conversation.messages if m["role"] == "tool"]
        assert len(tool_msgs) == 1
        assert "Hello, Alice!" in tool_msgs[0]["content"]

    async def test_legacy_client_still_works(self) -> None:
        """AgentLoop still works with legacy AsyncOpenAI client param."""
        from kaizen_agents.delegate.adapters.openai_stream import StreamResult

        @dataclass
        class FakeDelta:
            content: str | None = None
            tool_calls: list | None = None

        @dataclass
        class FakeChoice:
            delta: FakeDelta
            finish_reason: str | None = None

        @dataclass
        class FakeUsage:
            prompt_tokens: int = 10
            completion_tokens: int = 5
            total_tokens: int = 15

        @dataclass
        class FakeChunk:
            choices: list[FakeChoice] = field(default_factory=list)
            model: str = "test-model"
            usage: FakeUsage | None = None

        chunks = [
            FakeChunk(choices=[FakeChoice(delta=FakeDelta(content="Legacy"))]),
            FakeChunk(choices=[FakeChoice(delta=FakeDelta(), finish_reason="stop")]),
            FakeChunk(choices=[], usage=FakeUsage()),
        ]

        class FakeStream:
            def __init__(self, chunks):
                self._chunks = chunks
            def __aiter__(self):
                return self._iter()
            async def _iter(self):
                for c in self._chunks:
                    yield c

        client = AsyncMock()
        client.chat.completions.create = AsyncMock(return_value=FakeStream(chunks))

        config = KzConfig(model="test-model", max_turns=10)
        tools = ToolRegistry()

        loop = AgentLoop(
            config=config,
            tools=tools,
            client=client,
            system_prompt="Test",
        )

        collected: list[str] = []
        async for chunk in loop.run_turn("Hi"):
            collected.append(chunk)

        assert "".join(collected) == "Legacy"

    async def test_adapter_takes_precedence_over_client(self) -> None:
        """When both adapter and client are given, adapter is used."""

        class FakeAdapter:
            async def stream_chat(self, messages, tools=None, **kwargs):
                yield StreamEvent(
                    event_type="text_delta",
                    content="From adapter",
                    delta_text="From adapter",
                )
                yield StreamEvent(
                    event_type="done",
                    content="From adapter",
                    finish_reason="stop",
                    usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                )

        client = AsyncMock()
        # If client were used, it would fail because no side_effect is set
        config = KzConfig(model="test-model", max_turns=10)
        tools = ToolRegistry()

        loop = AgentLoop(
            config=config,
            tools=tools,
            client=client,
            adapter=FakeAdapter(),
            system_prompt="Test",
        )

        collected: list[str] = []
        async for chunk in loop.run_turn("Test"):
            collected.append(chunk)

        assert "".join(collected) == "From adapter"


# ---------------------------------------------------------------------------
# S8-007: StructuredLLMAdapter protocol
# ---------------------------------------------------------------------------


class TestStructuredLLMAdapter:
    """Test the structured adapter protocol and factory."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """StructuredLLMAdapter supports isinstance checks."""
        from kaizen_agents.orchestration.adapters import StructuredLLMAdapter

        class FakeStructured:
            def complete(self, messages, **kwargs):
                from kaizen_agents.orchestration.adapters import StructuredResponse
                return StructuredResponse(content="test")

            def complete_structured(self, messages, schema, **kwargs):
                return {"result": "test"}

        assert isinstance(FakeStructured(), StructuredLLMAdapter)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_get_structured_adapter_openai(self) -> None:
        """Factory creates OpenAI structured adapter."""
        from kaizen_agents.orchestration.adapters import (
            OpenAIStructuredAdapter,
            get_structured_adapter,
        )

        adapter = get_structured_adapter("openai")
        assert isinstance(adapter, OpenAIStructuredAdapter)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_get_structured_adapter_default_openai(self) -> None:
        """Empty provider defaults to OpenAI."""
        from kaizen_agents.orchestration.adapters import (
            OpenAIStructuredAdapter,
            get_structured_adapter,
        )

        adapter = get_structured_adapter("")
        assert isinstance(adapter, OpenAIStructuredAdapter)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_get_structured_adapter_anthropic(self) -> None:
        """Factory creates Anthropic structured adapter."""
        from kaizen_agents.orchestration.adapters import (
            AnthropicStructuredAdapter,
            get_structured_adapter,
        )

        adapter = get_structured_adapter("anthropic")
        assert isinstance(adapter, AnthropicStructuredAdapter)

    def test_get_structured_adapter_unknown_raises(self) -> None:
        """Unknown provider raises ValueError."""
        from kaizen_agents.orchestration.adapters import get_structured_adapter

        with pytest.raises(ValueError, match="Unknown structured adapter"):
            get_structured_adapter("nonexistent")


# ---------------------------------------------------------------------------
# Edge cases and error handling
# ---------------------------------------------------------------------------


class TestAdapterEdgeCases:
    """Edge cases for adapter handling."""

    def test_openai_adapter_missing_key_raises(self) -> None:
        """OpenAI adapter raises when no API key is available."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove any existing OPENAI_API_KEY
            env = dict(os.environ)
            env.pop("OPENAI_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                from kaizen_agents.delegate.adapters.openai_adapter import OpenAIStreamAdapter

                with pytest.raises(ValueError, match="No OpenAI API key"):
                    OpenAIStreamAdapter()

    def test_anthropic_adapter_missing_key_raises(self) -> None:
        """Anthropic adapter raises when no API key is available."""
        with patch.dict(os.environ, {}, clear=True):
            env = dict(os.environ)
            env.pop("ANTHROPIC_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                from kaizen_agents.delegate.adapters.anthropic_adapter import AnthropicStreamAdapter

                with pytest.raises(ValueError, match="No Anthropic API key"):
                    AnthropicStreamAdapter()

    def test_google_adapter_missing_key_raises(self) -> None:
        """Google adapter raises when no API key is available."""
        with patch.dict(os.environ, {}, clear=True):
            env = dict(os.environ)
            env.pop("GOOGLE_API_KEY", None)
            env.pop("GEMINI_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                from kaizen_agents.delegate.adapters.google_adapter import GoogleStreamAdapter

                with pytest.raises(ValueError, match="No Google API key"):
                    GoogleStreamAdapter()

    def test_ollama_adapter_default_base_url(self) -> None:
        """Ollama adapter defaults to localhost:11434."""
        from kaizen_agents.delegate.adapters.ollama_adapter import OllamaStreamAdapter

        adapter = OllamaStreamAdapter(default_model="llama3")
        assert "localhost:11434" in adapter._base_url

    @patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://remote:11434"})
    def test_ollama_adapter_env_base_url(self) -> None:
        """Ollama adapter reads base URL from env."""
        from kaizen_agents.delegate.adapters.ollama_adapter import OllamaStreamAdapter

        adapter = OllamaStreamAdapter(default_model="llama3")
        assert "remote:11434" in adapter._base_url
