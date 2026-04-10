# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 1 unit tests for SPEC-02 unified provider types.

Covers:
- ``TokenUsage`` dataclass and ``to_dict()``.
- ``ToolCall`` dataclass and ``to_dict()``.
- ``ChatResponse`` dataclass, defaults, and ``to_dict()``.
- ``StreamEvent`` dataclass and event type values.
- ``Message`` and ``MessageContent`` type aliases are usable.
"""

from __future__ import annotations

from kaizen.providers.types import (
    ChatResponse,
    Message,
    MessageContent,
    StreamEvent,
    TokenUsage,
    ToolCall,
)


class TestTokenUsage:
    """TokenUsage tracks prompt/completion/total tokens."""

    def test_defaults_are_zero(self):
        u = TokenUsage()
        assert u.prompt_tokens == 0
        assert u.completion_tokens == 0
        assert u.total_tokens == 0

    def test_to_dict(self):
        u = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        d = u.to_dict()
        assert d == {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        }

    def test_custom_values(self):
        u = TokenUsage(prompt_tokens=500, completion_tokens=200, total_tokens=700)
        assert u.prompt_tokens == 500
        assert u.completion_tokens == 200
        assert u.total_tokens == 700


class TestToolCall:
    """ToolCall represents a single function call emitted by the model."""

    def test_defaults(self):
        tc = ToolCall(id="call_123")
        assert tc.id == "call_123"
        assert tc.type == "function"
        assert tc.function_name == ""
        assert tc.function_arguments == "{}"

    def test_to_dict(self):
        tc = ToolCall(
            id="call_abc",
            type="function",
            function_name="get_weather",
            function_arguments='{"city": "London"}',
        )
        d = tc.to_dict()
        assert d["id"] == "call_abc"
        assert d["type"] == "function"
        assert d["function"]["name"] == "get_weather"
        assert d["function"]["arguments"] == '{"city": "London"}'


class TestChatResponse:
    """ChatResponse is the standardised response from any LLM provider."""

    def test_defaults(self):
        r = ChatResponse()
        assert r.id == ""
        assert r.content == ""
        assert r.role == "assistant"
        assert r.model == ""
        assert r.tool_calls == []
        assert r.finish_reason == "stop"
        assert r.usage == {}
        assert r.metadata == {}

    def test_to_dict_roundtrip(self):
        r = ChatResponse(
            id="resp_1",
            content="Hello!",
            role="assistant",
            model="gpt-4o",
            finish_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )
        d = r.to_dict()
        assert d["id"] == "resp_1"
        assert d["content"] == "Hello!"
        assert d["model"] == "gpt-4o"
        assert d["usage"]["total_tokens"] == 15

    def test_none_content_allowed(self):
        r = ChatResponse(content=None)
        assert r.content is None
        d = r.to_dict()
        assert d["content"] is None

    def test_tool_calls_list(self):
        r = ChatResponse(
            tool_calls=[{"id": "call_1", "type": "function"}],
            finish_reason="tool_calls",
        )
        assert len(r.tool_calls) == 1
        assert r.finish_reason == "tool_calls"


class TestStreamEvent:
    """StreamEvent represents a single event during streaming."""

    def test_text_delta_event(self):
        e = StreamEvent(
            event_type="text_delta",
            content="Hello",
            delta_text="Hello",
        )
        assert e.event_type == "text_delta"
        assert e.delta_text == "Hello"
        assert e.content == "Hello"

    def test_done_event(self):
        e = StreamEvent(
            event_type="done",
            content="Full text",
            finish_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
            model="gpt-4o",
        )
        assert e.event_type == "done"
        assert e.finish_reason == "stop"
        assert e.usage["prompt_tokens"] == 10
        assert e.model == "gpt-4o"

    def test_tool_call_events(self):
        e = StreamEvent(
            event_type="tool_call_start",
            tool_calls=[{"id": "call_1"}],
        )
        assert e.event_type == "tool_call_start"
        assert len(e.tool_calls) == 1

    def test_defaults(self):
        e = StreamEvent(event_type="text_delta")
        assert e.content == ""
        assert e.tool_calls == []
        assert e.finish_reason is None
        assert e.model == ""
        assert e.usage == {}
        assert e.delta_text == ""


class TestTypeAliases:
    """Message and MessageContent type aliases are usable."""

    def test_message_is_dict(self):
        msg: Message = {"role": "user", "content": "Hello"}
        assert msg["role"] == "user"

    def test_message_content_string(self):
        content: MessageContent = "plain text"
        assert isinstance(content, str)

    def test_message_content_list(self):
        content: MessageContent = [
            {"type": "text", "text": "Hello"},
            {"type": "image_url", "image_url": {"url": "data:..."}},
        ]
        assert isinstance(content, list)
        assert len(content) == 2
