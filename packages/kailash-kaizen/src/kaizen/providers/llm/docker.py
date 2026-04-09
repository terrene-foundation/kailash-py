# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Docker Model Runner provider for local LLM and embedding operations.

Uses Docker Desktop's Model Runner with GPU acceleration. Provides an
OpenAI-compatible API running locally with no API keys required.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, List

from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error
from kaizen.providers.base import ProviderCapability, UnifiedAIProvider
from kaizen.providers.types import Message, StreamEvent

logger = logging.getLogger(__name__)


class DockerModelRunnerProvider(UnifiedAIProvider):
    """Docker Model Runner provider for local LLM and embedding operations.

    Prerequisites:
        * Docker Desktop 4.40+ with Model Runner enabled
        * Models pulled via: ``docker model pull ai/llama3.2``
        * TCP access enabled: ``docker desktop enable model-runner --tcp 12434``

    Supported LLM models:
        * ai/llama3.2 (default), ai/llama3.3
        * ai/gemma3, ai/gemma2
        * ai/mistral, ai/mixtral
        * ai/phi4, ai/qwen3

    Supported embedding models:
        * ai/mxbai-embed-large (1024 dimensions)
        * ai/nomic-embed-text (768 dimensions)
        * ai/all-minilm (384 dimensions)
    """

    DEFAULT_BASE_URL = "http://localhost:12434/engines/llama.cpp/v1"
    CONTAINER_BASE_URL = "http://model-runner.docker.internal/engines/llama.cpp/v1"

    TOOL_CAPABLE_MODELS = frozenset({"ai/qwen3", "ai/llama3.3", "ai/gemma3"})

    MODELS = ["ai/llama3.2", "ai/llama3.3", "ai/gemma3", "ai/mistral", "ai/qwen3"]

    def __init__(self, use_async: bool = False) -> None:
        super().__init__()
        self._use_async = use_async
        self._sync_client: Any = None
        self._async_client: Any = None
        self._model_cache: dict[str, dict[str, Any]] = {}

    def _get_base_url(self) -> str:
        import os

        return os.getenv("DOCKER_MODEL_RUNNER_URL", self.DEFAULT_BASE_URL)

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        import urllib.error
        import urllib.request

        try:
            url = f"{self._get_base_url()}/models"
            req = urllib.request.urlopen(url, timeout=2)
            self._available = req.status == 200
        except (urllib.error.URLError, TimeoutError, OSError):
            self._available = False
        except Exception:
            self._available = False
        return self._available

    # ------------------------------------------------------------------
    # SPEC-02 capability declaration
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "docker"

    @property
    def capabilities(self) -> set[ProviderCapability]:
        return {
            ProviderCapability.CHAT_SYNC,
            ProviderCapability.CHAT_ASYNC,
            ProviderCapability.CHAT_STREAM,
            ProviderCapability.EMBEDDINGS,
            ProviderCapability.TOOLS,
        }

    def supports_tools(self, model: str) -> bool:
        return any(model.startswith(prefix) for prefix in self.TOOL_CAPABLE_MODELS)

    def _process_messages(self, messages: List[Message]) -> list:
        processed = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = [
                    item.get("text", "")
                    for item in content
                    if item.get("type") == "text"
                ]
                content = " ".join(text_parts)
            processed.append({"role": msg.get("role", "user"), "content": content})
        return processed

    def chat(self, messages: List[Message], **kwargs: Any) -> dict[str, Any]:
        try:
            import openai

            generation_config = kwargs.get("generation_config", {})
            model = kwargs.get("model", "ai/llama3.2")
            tools = kwargs.get("tools", [])
            stream = kwargs.get("stream", False)

            if tools and not self.supports_tools(model):
                import warnings

                warnings.warn(
                    f"Model {model} may not support tool calling. "
                    f"Consider using: {', '.join(sorted(self.TOOL_CAPABLE_MODELS))}",
                    UserWarning,
                    stacklevel=2,
                )

            if tools and stream:
                stream = False

            per_request_base_url = kwargs.get("base_url")
            if per_request_base_url:
                client = openai.OpenAI(
                    api_key="docker-model-runner", base_url=per_request_base_url
                )
            else:
                if self._sync_client is None:
                    self._sync_client = openai.OpenAI(
                        api_key="docker-model-runner", base_url=self._get_base_url()
                    )
                client = self._sync_client

            request_params: dict[str, Any] = {
                "model": model,
                "messages": self._process_messages(messages),
                "temperature": generation_config.get("temperature", 0.7),
                "max_tokens": generation_config.get("max_tokens"),
                "top_p": generation_config.get("top_p"),
                "stop": generation_config.get("stop"),
                "stream": stream,
            }

            if tools:
                request_params["tools"] = tools
                request_params["tool_choice"] = generation_config.get(
                    "tool_choice", "auto"
                )

            request_params = {k: v for k, v in request_params.items() if v is not None}

            response = client.chat.completions.create(**request_params)
            choice = response.choices[0]
            usage = response.usage

            return {
                "id": response.id or f"docker_{hash(str(messages))}",
                "content": choice.message.content,
                "role": "assistant",
                "model": response.model,
                "created": response.created,
                "tool_calls": (
                    choice.message.tool_calls
                    if hasattr(choice.message, "tool_calls")
                    and choice.message.tool_calls
                    else []
                ),
                "finish_reason": choice.finish_reason or "stop",
                "usage": {
                    "prompt_tokens": usage.prompt_tokens if usage else 0,
                    "completion_tokens": usage.completion_tokens if usage else 0,
                    "total_tokens": usage.total_tokens if usage else 0,
                },
                "metadata": {
                    "provider": "docker_model_runner",
                    "supports_tools": self.supports_tools(model),
                },
            }

        except ImportError:
            raise RuntimeError(
                "OpenAI library not installed. Install with: pip install openai"
            )
        except Exception as e:
            logger.error("Docker Model Runner error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Docker Model Runner"))

    async def chat_async(
        self, messages: List[Message], **kwargs: Any
    ) -> dict[str, Any]:
        try:
            from openai import AsyncOpenAI

            generation_config = kwargs.get("generation_config", {})
            model = kwargs.get("model", "ai/llama3.2")
            tools = kwargs.get("tools", [])
            stream = kwargs.get("stream", False)

            if tools and not self.supports_tools(model):
                import warnings

                warnings.warn(
                    f"Model {model} may not support tool calling. "
                    f"Consider using: {', '.join(sorted(self.TOOL_CAPABLE_MODELS))}",
                    UserWarning,
                    stacklevel=2,
                )

            if tools and stream:
                stream = False

            per_request_base_url = kwargs.get("base_url")
            if per_request_base_url:
                async_client = AsyncOpenAI(
                    api_key="docker-model-runner", base_url=per_request_base_url
                )
            else:
                if self._async_client is None:
                    self._async_client = AsyncOpenAI(
                        api_key="docker-model-runner", base_url=self._get_base_url()
                    )
                async_client = self._async_client

            request_params: dict[str, Any] = {
                "model": model,
                "messages": self._process_messages(messages),
                "temperature": generation_config.get("temperature", 0.7),
                "max_tokens": generation_config.get("max_tokens"),
                "top_p": generation_config.get("top_p"),
                "stop": generation_config.get("stop"),
                "stream": stream,
            }

            if tools:
                request_params["tools"] = tools
                request_params["tool_choice"] = generation_config.get(
                    "tool_choice", "auto"
                )

            request_params = {k: v for k, v in request_params.items() if v is not None}

            response = await async_client.chat.completions.create(**request_params)
            choice = response.choices[0]
            usage = response.usage

            return {
                "id": response.id or f"docker_{hash(str(messages))}",
                "content": choice.message.content,
                "role": "assistant",
                "model": response.model,
                "created": response.created,
                "tool_calls": (
                    choice.message.tool_calls
                    if hasattr(choice.message, "tool_calls")
                    and choice.message.tool_calls
                    else []
                ),
                "finish_reason": choice.finish_reason or "stop",
                "usage": {
                    "prompt_tokens": usage.prompt_tokens if usage else 0,
                    "completion_tokens": usage.completion_tokens if usage else 0,
                    "total_tokens": usage.total_tokens if usage else 0,
                },
                "metadata": {
                    "provider": "docker_model_runner",
                    "supports_tools": self.supports_tools(model),
                },
            }

        except ImportError:
            raise RuntimeError(
                "OpenAI library not installed. Install with: pip install openai"
            )
        except Exception as e:
            logger.error("Docker Model Runner async error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Docker Model Runner"))

    # ------------------------------------------------------------------
    # Chat (streaming) — SPEC-02 StreamingProvider protocol
    # ------------------------------------------------------------------

    async def stream_chat(
        self, messages: List[Message], **kwargs: Any
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream tokens from Docker Model Runner (OpenAI-compatible API).

        Uses the AsyncOpenAI client pointed at the local Docker Model Runner
        endpoint and iterates the real per-chunk deltas.
        """
        from openai import AsyncOpenAI

        model = kwargs.get("model", "ai/llama3.2")
        generation_config = dict(kwargs.get("generation_config", {}) or {})
        tools = kwargs.get("tools") or []

        per_request_base_url = kwargs.get("base_url") or self._get_base_url()
        async_client = AsyncOpenAI(
            api_key="docker-model-runner", base_url=per_request_base_url
        )

        request_params: dict[str, Any] = {
            "model": model,
            "messages": self._process_messages(messages),
            "temperature": generation_config.get("temperature", 0.7),
            "max_tokens": generation_config.get("max_tokens"),
            "top_p": generation_config.get("top_p"),
            "stop": generation_config.get("stop"),
            "stream": True,
        }

        # Tools and streaming are mutually exclusive on Docker Model Runner;
        # the non-streaming chat path already disables stream when tools
        # are present. For stream_chat we simply drop tools rather than
        # silently degrade to a non-streaming response.
        if tools:
            logger.warning(
                "docker.stream_chat.tools_ignored model=%s reason=stream_tools_unsupported",
                model,
            )

        request_params = {k: v for k, v in request_params.items() if v is not None}

        logger.debug(
            "docker.stream_chat.start model=%s base_url=%s", model, per_request_base_url
        )

        accumulated_text = ""
        last_finish_reason: str | None = None
        last_usage: dict[str, int] = {}

        try:
            stream = await async_client.chat.completions.create(**request_params)
            async for chunk in stream:
                if not chunk.choices:
                    if getattr(chunk, "usage", None) is not None:
                        last_usage = {
                            "prompt_tokens": chunk.usage.prompt_tokens,
                            "completion_tokens": chunk.usage.completion_tokens,
                            "total_tokens": chunk.usage.total_tokens,
                        }
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                text_piece = getattr(delta, "content", None) if delta else None
                if text_piece:
                    accumulated_text += text_piece
                    yield StreamEvent(
                        event_type="text_delta",
                        delta_text=text_piece,
                        content=accumulated_text,
                        model=model,
                    )
                if choice.finish_reason:
                    last_finish_reason = choice.finish_reason

            logger.debug(
                "docker.stream_chat.done model=%s chars=%d finish=%s",
                model,
                len(accumulated_text),
                last_finish_reason,
            )

            yield StreamEvent(
                event_type="done",
                content=accumulated_text,
                finish_reason=last_finish_reason or "stop",
                model=model,
                usage=last_usage,
            )
        except Exception as exc:  # pragma: no cover
            logger.error("docker.stream_chat.error error=%s", exc, exc_info=True)
            raise RuntimeError(sanitize_provider_error(exc, "Docker Model Runner"))

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        try:
            import openai

            model = kwargs.get("model", "ai/mxbai-embed-large")
            if self._sync_client is None:
                self._sync_client = openai.OpenAI(
                    api_key="docker-model-runner", base_url=self._get_base_url()
                )
            response = self._sync_client.embeddings.create(model=model, input=texts)
            return [item.embedding for item in response.data]

        except ImportError:
            raise RuntimeError(
                "OpenAI library not installed. Install with: pip install openai"
            )
        except Exception as e:
            logger.error("Docker Model Runner embedding error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Docker Model Runner"))

    async def embed_async(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        try:
            from openai import AsyncOpenAI

            model = kwargs.get("model", "ai/mxbai-embed-large")
            if self._async_client is None:
                self._async_client = AsyncOpenAI(
                    api_key="docker-model-runner", base_url=self._get_base_url()
                )
            response = await self._async_client.embeddings.create(
                model=model, input=texts
            )
            return [item.embedding for item in response.data]

        except ImportError:
            raise RuntimeError(
                "OpenAI library not installed. Install with: pip install openai"
            )
        except Exception as e:
            logger.error(
                "Docker Model Runner async embedding error: %s", e, exc_info=True
            )
            raise RuntimeError(sanitize_provider_error(e, "Docker Model Runner"))

    def get_model_info(self, model: str) -> dict[str, Any]:
        if model in self._model_cache:
            return self._model_cache[model]

        known_models = {
            "ai/mxbai-embed-large": {
                "dimensions": 1024,
                "max_tokens": 512,
                "description": "mxbai-embed-large embedding model (Matryoshka support)",
                "capabilities": {
                    "batch_processing": True,
                    "matryoshka_dimensions": [1024, 512, 256, 128, 64],
                },
            },
            "ai/nomic-embed-text": {
                "dimensions": 768,
                "max_tokens": 8192,
                "description": "Nomic embedding model (Matryoshka support)",
                "capabilities": {
                    "batch_processing": True,
                    "matryoshka_dimensions": [768, 512, 256, 128, 64],
                },
            },
            "ai/all-minilm": {
                "dimensions": 384,
                "max_tokens": 512,
                "description": "all-MiniLM-L6-v2 lightweight embedding model",
                "capabilities": {"batch_processing": True},
            },
            "ai/qwen3-embedding": {
                "dimensions": 1024,
                "max_tokens": 8192,
                "description": "Qwen3 embedding model",
                "capabilities": {"batch_processing": True},
            },
        }

        if model in known_models:
            self._model_cache[model] = known_models[model]
            return known_models[model]

        return {
            "dimensions": 1024,
            "max_tokens": 4096,
            "description": f"Docker Model Runner model: {model}",
            "capabilities": {},
        }
