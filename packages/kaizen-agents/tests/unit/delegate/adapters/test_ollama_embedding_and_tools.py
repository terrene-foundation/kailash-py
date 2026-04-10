# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
# isort: skip_file
"""Unit tests for OllamaEmbeddingAdapter (#365) and tool-capable model allowlist (#366)."""

from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen_agents.delegate.adapters.ollama_adapter import (
    OLLAMA_TOOL_CAPABLE_FAMILIES,
    OllamaEmbeddingAdapter,
    OllamaStreamAdapter,
    model_supports_tools,
)

# ===========================================================================
# #366 — Tool-capable model allowlist
# ===========================================================================


class TestOllamaToolCapableFamilies:
    """Verify the OLLAMA_TOOL_CAPABLE_FAMILIES frozenset contents."""

    def test_is_frozenset(self) -> None:
        assert isinstance(OLLAMA_TOOL_CAPABLE_FAMILIES, frozenset)

    def test_contains_all_required_families(self) -> None:
        expected = {
            "llama3.1",
            "llama3.2",
            "qwen2.5",
            "qwen3",
            "qwq",
            "mistral-nemo",
            "mistral-small",
            "command-r",
            "command-r-plus",
            "firefunction-v2",
            "nemotron",
        }
        assert expected == OLLAMA_TOOL_CAPABLE_FAMILIES

    def test_immutable(self) -> None:
        with pytest.raises(AttributeError):
            OLLAMA_TOOL_CAPABLE_FAMILIES.add("new-model")  # type: ignore[attr-defined]


class TestModelSupportsTools:
    """Verify model_supports_tools() family extraction and lookup."""

    @pytest.mark.parametrize(
        "model_name",
        [
            "llama3.1:8b-instruct-q8_0",
            "llama3.1:latest",
            "llama3.1",
            "llama3.2:3b",
            "qwen2.5:14b",
            "qwen2.5:72b-instruct",
            "qwen3:8b",
            "qwq:32b",
            "mistral-nemo:12b",
            "mistral-small:latest",
            "command-r:35b",
            "command-r-plus:latest",
            "firefunction-v2:latest",
            "nemotron:70b",
        ],
    )
    def test_tool_capable_models_return_true(self, model_name: str) -> None:
        assert model_supports_tools(model_name) is True

    @pytest.mark.parametrize(
        "model_name",
        [
            "llama3:8b",
            "phi3:14b",
            "codellama:7b",
            "deepseek-coder:6.7b",
            "mixtral:8x7b",
            "gemma:7b",
            "vicuna:13b",
            "nomic-embed-text",
            "mxbai-embed-large",
        ],
    )
    def test_non_tool_capable_models_return_false(self, model_name: str) -> None:
        assert model_supports_tools(model_name) is False

    def test_case_insensitive(self) -> None:
        assert model_supports_tools("Qwen2.5:14B") is True
        assert model_supports_tools("LLAMA3.1:8B") is True

    def test_empty_string(self) -> None:
        assert model_supports_tools("") is False

    def test_no_colon_separator(self) -> None:
        assert model_supports_tools("llama3.1") is True
        assert model_supports_tools("phi3") is False


class TestToolStrippingInStreamChat:
    """Verify that tools are stripped with a WARN log for non-capable models."""

    @pytest.mark.asyncio
    async def test_tools_stripped_for_non_capable_model(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        adapter = OllamaStreamAdapter(
            base_url="http://localhost:11434",
            default_model="phi3:14b",
        )

        # Since tools are stripped, the request will go through the streaming
        # path (stream=True).  We mock the streaming path.
        class FakeStreamResponse:
            status_code = 200

            async def aiter_lines(self):
                yield json.dumps(
                    {
                        "message": {"content": "Hello without tools"},
                        "model": "phi3:14b",
                        "done": True,
                        "prompt_eval_count": 10,
                        "eval_count": 5,
                    }
                )

            async def aread(self):
                return b""

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        captured_kwargs: dict[str, Any] = {}

        def fake_stream(method: str, url: str, **kwargs: Any):
            captured_kwargs.update(kwargs)
            return FakeStreamResponse()

        mock_client = AsyncMock()
        mock_client.stream = fake_stream
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        tools = [
            {"type": "function", "function": {"name": "get_weather", "parameters": {}}}
        ]

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            caplog.at_level(logging.WARNING),
        ):
            events = []
            async for event in adapter.stream_chat(
                [{"role": "user", "content": "hi"}],
                tools=tools,
            ):
                events.append(event)

        # Tools should have been stripped -- the request should NOT have tools
        request_body = captured_kwargs["json"]
        assert "tools" not in request_body
        # stream=True because tools were stripped
        assert request_body["stream"] is True

        # WARN log should have been emitted
        assert any("ollama.tools_stripped" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_tools_kept_for_capable_model(self) -> None:
        adapter = OllamaStreamAdapter(
            base_url="http://localhost:11434",
            default_model="llama3.1:8b-instruct-q8_0",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "llama3.1:8b-instruct-q8_0",
            "message": {"role": "assistant", "content": "I can use tools"},
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

        tools = [
            {"type": "function", "function": {"name": "get_weather", "parameters": {}}}
        ]

        with patch("httpx.AsyncClient", return_value=mock_client):
            events = []
            async for event in adapter.stream_chat(
                [{"role": "user", "content": "hi"}],
                tools=tools,
            ):
                events.append(event)

        # Tools should be present in the request
        request_body = captured_kwargs["json"]
        assert "tools" in request_body
        assert len(request_body["tools"]) == 1
        # stream=False because tools are present
        assert request_body["stream"] is False

    @pytest.mark.asyncio
    async def test_no_tools_no_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """When no tools are provided, no stripping or warning should occur."""
        adapter = OllamaStreamAdapter(
            base_url="http://localhost:11434",
            default_model="phi3:14b",
        )

        class FakeStreamResponse:
            status_code = 200

            async def aiter_lines(self):
                yield json.dumps(
                    {
                        "message": {"content": "Hello"},
                        "model": "phi3:14b",
                        "done": True,
                        "prompt_eval_count": 5,
                        "eval_count": 3,
                    }
                )

            async def aread(self):
                return b""

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        mock_client = AsyncMock()
        mock_client.stream = lambda method, url, **kw: FakeStreamResponse()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            caplog.at_level(logging.WARNING),
        ):
            events = []
            async for event in adapter.stream_chat(
                [{"role": "user", "content": "hi"}],
                tools=None,
            ):
                events.append(event)

        assert not any("ollama.tools_stripped" in r.message for r in caplog.records)


# ===========================================================================
# #365 — OllamaEmbeddingAdapter
# ===========================================================================


class TestOllamaEmbeddingAdapterConstruction:
    """Verify constructor defaults and overrides."""

    def test_default_base_url(self) -> None:
        adapter = OllamaEmbeddingAdapter()
        assert adapter._base_url == "http://localhost:11434"

    def test_custom_base_url(self) -> None:
        adapter = OllamaEmbeddingAdapter(base_url="http://gpu-host:11434")
        assert adapter._base_url == "http://gpu-host:11434"

    def test_base_url_strips_trailing_slash(self) -> None:
        adapter = OllamaEmbeddingAdapter(base_url="http://gpu-host:11434/")
        assert adapter._base_url == "http://gpu-host:11434"

    def test_default_model(self) -> None:
        adapter = OllamaEmbeddingAdapter()
        assert adapter._default_model == "mxbai-embed-large"

    def test_custom_model(self) -> None:
        adapter = OllamaEmbeddingAdapter(default_model="nomic-embed-text")
        assert adapter._default_model == "nomic-embed-text"

    def test_base_url_from_env(self) -> None:
        with patch.dict("os.environ", {"OLLAMA_BASE_URL": "http://env-host:11434"}):
            adapter = OllamaEmbeddingAdapter()
            assert adapter._base_url == "http://env-host:11434"


class TestOllamaEmbeddingAdapterEmbed:
    """Verify the embed() method against mocked HTTP responses."""

    @pytest.mark.asyncio
    async def test_single_input(self) -> None:
        adapter = OllamaEmbeddingAdapter(base_url="http://localhost:11434")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "mxbai-embed-large",
            "embeddings": [[0.1, 0.2, 0.3, 0.4]],
        }

        captured_kwargs: dict[str, Any] = {}

        async def mock_post(url: str, **kwargs: Any) -> MagicMock:
            captured_kwargs["url"] = url
            captured_kwargs.update(kwargs)
            return mock_response

        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.embed(["Hello world"])

        assert result == [[0.1, 0.2, 0.3, 0.4]]
        assert captured_kwargs["url"] == "http://localhost:11434/api/embed"
        request_body = captured_kwargs["json"]
        assert request_body["model"] == "mxbai-embed-large"
        assert request_body["input"] == ["Hello world"]

    @pytest.mark.asyncio
    async def test_batch_inputs(self) -> None:
        adapter = OllamaEmbeddingAdapter(base_url="http://localhost:11434")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "mxbai-embed-large",
            "embeddings": [
                [0.1, 0.2, 0.3],
                [0.4, 0.5, 0.6],
                [0.7, 0.8, 0.9],
            ],
        }

        async def mock_post(url: str, **kwargs: Any) -> MagicMock:
            return mock_response

        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.embed(["text1", "text2", "text3"])

        assert len(result) == 3
        assert result[0] == [0.1, 0.2, 0.3]
        assert result[1] == [0.4, 0.5, 0.6]
        assert result[2] == [0.7, 0.8, 0.9]

    @pytest.mark.asyncio
    async def test_model_override(self) -> None:
        adapter = OllamaEmbeddingAdapter(base_url="http://localhost:11434")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "nomic-embed-text",
            "embeddings": [[1.0, 2.0]],
        }

        captured_kwargs: dict[str, Any] = {}

        async def mock_post(url: str, **kwargs: Any) -> MagicMock:
            captured_kwargs.update(kwargs)
            return mock_response

        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.embed(["test"], model="nomic-embed-text")

        assert captured_kwargs["json"]["model"] == "nomic-embed-text"
        assert result == [[1.0, 2.0]]

    @pytest.mark.asyncio
    async def test_http_error_raises_connection_error(self) -> None:
        adapter = OllamaEmbeddingAdapter(base_url="http://localhost:11434")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        async def mock_post(url: str, **kwargs: Any) -> MagicMock:
            return mock_response

        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            pytest.raises(ConnectionError, match="status 500"),
        ):
            await adapter.embed(["test"])

    @pytest.mark.asyncio
    async def test_missing_embeddings_key_raises_value_error(self) -> None:
        adapter = OllamaEmbeddingAdapter(base_url="http://localhost:11434")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"model": "mxbai-embed-large"}

        async def mock_post(url: str, **kwargs: Any) -> MagicMock:
            return mock_response

        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            pytest.raises(ValueError, match="missing 'embeddings' key"),
        ):
            await adapter.embed(["test"])

    @pytest.mark.asyncio
    async def test_count_mismatch_raises_value_error(self) -> None:
        adapter = OllamaEmbeddingAdapter(base_url="http://localhost:11434")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "mxbai-embed-large",
            "embeddings": [[0.1, 0.2]],  # 1 embedding for 2 inputs
        }

        async def mock_post(url: str, **kwargs: Any) -> MagicMock:
            return mock_response

        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            pytest.raises(ValueError, match="1 embeddings for 2 inputs"),
        ):
            await adapter.embed(["text1", "text2"])

    @pytest.mark.asyncio
    async def test_empty_input_list(self) -> None:
        adapter = OllamaEmbeddingAdapter(base_url="http://localhost:11434")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "mxbai-embed-large",
            "embeddings": [],
        }

        async def mock_post(url: str, **kwargs: Any) -> MagicMock:
            return mock_response

        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await adapter.embed([])

        assert result == []


# ===========================================================================
# Registry — get_embedding_adapter
# ===========================================================================


class TestGetEmbeddingAdapter:
    """Verify the registry's get_embedding_adapter function."""

    def test_ollama_returns_embedding_adapter(self) -> None:
        from kaizen_agents.delegate.adapters.registry import get_embedding_adapter

        adapter = get_embedding_adapter("ollama")
        assert isinstance(adapter, OllamaEmbeddingAdapter)
        assert adapter._default_model == "mxbai-embed-large"

    def test_ollama_with_custom_model(self) -> None:
        from kaizen_agents.delegate.adapters.registry import get_embedding_adapter

        adapter = get_embedding_adapter("ollama", model="nomic-embed-text")
        assert isinstance(adapter, OllamaEmbeddingAdapter)
        assert adapter._default_model == "nomic-embed-text"

    def test_ollama_with_custom_base_url(self) -> None:
        from kaizen_agents.delegate.adapters.registry import get_embedding_adapter

        adapter = get_embedding_adapter("ollama", base_url="http://remote:11434")
        assert isinstance(adapter, OllamaEmbeddingAdapter)
        assert adapter._base_url == "http://remote:11434"

    def test_unknown_provider_raises(self) -> None:
        from kaizen_agents.delegate.adapters.registry import get_embedding_adapter

        with pytest.raises(ValueError, match="Unknown embedding provider"):
            get_embedding_adapter("nonexistent")

    def test_case_insensitive(self) -> None:
        from kaizen_agents.delegate.adapters.registry import get_embedding_adapter

        adapter = get_embedding_adapter("Ollama")
        assert isinstance(adapter, OllamaEmbeddingAdapter)
