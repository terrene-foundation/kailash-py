# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for Ollama adapter bug fixes (#361, #363, #364, #367a-c)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kaizen_agents.delegate.adapters.ollama_adapter import (
    OllamaStreamAdapter,
    _convert_messages_for_ollama,
)

# ---------------------------------------------------------------------------
# Fix 1 — #361: Tool-call args JSON string -> dict
# ---------------------------------------------------------------------------


class TestConvertMessagesDeserializesToolCallArgs:
    """Verify that JSON-string arguments in assistant tool_calls are
    deserialised back to dicts when converting for Ollama."""

    def test_json_string_args_become_dict(self) -> None:
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"city": "London", "units": "metric"}',
                        },
                    }
                ],
            }
        ]
        result = _convert_messages_for_ollama(messages)
        tc = result[0]["tool_calls"][0]
        assert isinstance(tc["function"]["arguments"], dict)
        assert tc["function"]["arguments"] == {"city": "London", "units": "metric"}

    def test_dict_args_stay_as_dict(self) -> None:
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": {"city": "Tokyo"},
                        },
                    }
                ],
            }
        ]
        result = _convert_messages_for_ollama(messages)
        tc = result[0]["tool_calls"][0]
        assert isinstance(tc["function"]["arguments"], dict)
        assert tc["function"]["arguments"] == {"city": "Tokyo"}

    def test_invalid_json_string_falls_back_to_empty_dict(self) -> None:
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "broken",
                            "arguments": "{not valid json",
                        },
                    }
                ],
            }
        ]
        result = _convert_messages_for_ollama(messages)
        tc = result[0]["tool_calls"][0]
        assert tc["function"]["arguments"] == {}


# ---------------------------------------------------------------------------
# Fix 2 — #363: Tool-role messages preserve tool_call_id and name
# ---------------------------------------------------------------------------


class TestConvertMessagesPreservesToolRoleFields:
    """Verify that tool-role messages retain tool_call_id and name."""

    def test_tool_call_id_and_name_preserved(self) -> None:
        messages = [
            {
                "role": "tool",
                "content": '{"temp": 22}',
                "tool_call_id": "call_abc123",
                "name": "get_weather",
            }
        ]
        result = _convert_messages_for_ollama(messages)
        assert result[0]["tool_call_id"] == "call_abc123"
        assert result[0]["name"] == "get_weather"

    def test_tool_message_without_optional_fields(self) -> None:
        messages = [
            {
                "role": "tool",
                "content": "result text",
            }
        ]
        result = _convert_messages_for_ollama(messages)
        assert "tool_call_id" not in result[0]
        assert "name" not in result[0]
        assert result[0]["content"] == "result text"


# ---------------------------------------------------------------------------
# Fix 3 — #364: stream=True + tools incompatible
# ---------------------------------------------------------------------------


class TestStreamDisablesWhenToolsPresent:
    """Verify that the request body has stream=False when tools are provided."""

    @pytest.mark.asyncio
    async def test_stream_false_with_tools(self) -> None:
        adapter = OllamaStreamAdapter(
            base_url="http://localhost:11434",
            default_model="llama3",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "llama3",
            "message": {"role": "assistant", "content": "Hello"},
            "done": True,
            "prompt_eval_count": 10,
            "eval_count": 5,
        }

        captured_kwargs: dict[str, Any] = {}

        async def mock_post(url: str, **kwargs: Any) -> MagicMock:
            captured_kwargs.update(kwargs)
            return mock_response

        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        tools = [{"type": "function", "function": {"name": "test", "parameters": {}}}]

        with patch("httpx.AsyncClient", return_value=mock_client):
            events = []
            async for event in adapter.stream_chat(
                [{"role": "user", "content": "hi"}],
                tools=tools,
            ):
                events.append(event)

        request_body = captured_kwargs["json"]
        assert request_body["stream"] is False

    @pytest.mark.asyncio
    async def test_stream_true_without_tools(self) -> None:
        adapter = OllamaStreamAdapter(
            base_url="http://localhost:11434",
            default_model="llama3",
        )

        # For the streaming path we need to mock the stream context manager.
        # We just need to verify the request_body has stream=True; we don't
        # need to fully run the streaming loop, so we raise after capture.
        captured_kwargs: dict[str, Any] = {}

        class FakeStreamResponse:
            status_code = 200

            async def aiter_lines(self):
                yield json.dumps(
                    {
                        "message": {"content": "hi"},
                        "model": "llama3",
                        "done": True,
                        "prompt_eval_count": 1,
                        "eval_count": 1,
                    }
                )

            async def aread(self):
                return b""

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        def fake_stream(method: str, url: str, **kwargs: Any):
            captured_kwargs.update(kwargs)
            return FakeStreamResponse()

        mock_client = AsyncMock()
        mock_client.stream = fake_stream
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            events = []
            async for event in adapter.stream_chat(
                [{"role": "user", "content": "hi"}],
                tools=None,
            ):
                events.append(event)

        request_body = captured_kwargs["json"]
        assert request_body["stream"] is True


# ---------------------------------------------------------------------------
# Fix 4 — #367a: Default max tokens
# ---------------------------------------------------------------------------


class TestDefaultMaxTokensIs4096:
    """Verify the default_max_tokens constructor default is 4096."""

    def test_default(self) -> None:
        adapter = OllamaStreamAdapter()
        assert adapter._default_max_tokens == 4096

    def test_override(self) -> None:
        adapter = OllamaStreamAdapter(default_max_tokens=8192)
        assert adapter._default_max_tokens == 8192


# ---------------------------------------------------------------------------
# Fix 5 — #367b: kwargs merges options instead of overwriting
# ---------------------------------------------------------------------------


class TestKwargsMergesOptions:
    """Verify that passing options={...} as kwargs merges into the existing
    options dict rather than replacing it."""

    @pytest.mark.asyncio
    async def test_options_merged_not_replaced(self) -> None:
        adapter = OllamaStreamAdapter(
            base_url="http://localhost:11434",
            default_model="llama3",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "llama3",
            "message": {"role": "assistant", "content": "ok"},
            "done": True,
            "prompt_eval_count": 5,
            "eval_count": 3,
        }

        captured_kwargs: dict[str, Any] = {}

        async def mock_post(url: str, **kwargs: Any) -> MagicMock:
            captured_kwargs.update(kwargs)
            return mock_response

        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        tools = [{"type": "function", "function": {"name": "t", "parameters": {}}}]

        with patch("httpx.AsyncClient", return_value=mock_client):
            events = []
            async for event in adapter.stream_chat(
                [{"role": "user", "content": "hi"}],
                tools=tools,
                options={"top_k": 40, "top_p": 0.9},
            ):
                events.append(event)

        request_body = captured_kwargs["json"]
        opts = request_body["options"]
        # Original options should still be present
        assert "temperature" in opts
        assert "num_predict" in opts
        # Caller-provided options should be merged in
        assert opts["top_k"] == 40
        assert opts["top_p"] == 0.9


# ---------------------------------------------------------------------------
# Fix 6 — #367c: Unique tool-call IDs (no index-based collisions)
# ---------------------------------------------------------------------------


class TestToolCallIdsUniqueAcrossTurns:
    """Verify that tool-call IDs are UUID-based and unique, not index-based."""

    @pytest.mark.asyncio
    async def test_ids_unique_across_multiple_tool_calls(self) -> None:
        adapter = OllamaStreamAdapter(
            base_url="http://localhost:11434",
            default_model="llama3",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "llama3",
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "func_a", "arguments": {"x": 1}}},
                    {"function": {"name": "func_b", "arguments": {"y": 2}}},
                    {"function": {"name": "func_c", "arguments": {"z": 3}}},
                ],
            },
            "done": True,
            "prompt_eval_count": 10,
            "eval_count": 5,
        }

        async def mock_post(url: str, **kwargs: Any) -> MagicMock:
            return mock_response

        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        tools = [{"type": "function", "function": {"name": "func_a", "parameters": {}}}]

        with patch("httpx.AsyncClient", return_value=mock_client):
            events = []
            async for event in adapter.stream_chat(
                [{"role": "user", "content": "hi"}],
                tools=tools,
            ):
                events.append(event)

        done_event = [e for e in events if e.event_type == "done"][0]
        ids = [tc["id"] for tc in done_event.tool_calls]
        # All IDs should be unique
        assert len(ids) == len(set(ids)) == 3
        # IDs should use uuid format, not index-based
        for tc_id in ids:
            assert tc_id.startswith("call_ollama_")
            suffix = tc_id[len("call_ollama_") :]
            # Should be 12-char hex, not a digit like "0", "1", "2"
            assert len(suffix) == 12
            # Verify it's valid hex
            int(suffix, 16)
