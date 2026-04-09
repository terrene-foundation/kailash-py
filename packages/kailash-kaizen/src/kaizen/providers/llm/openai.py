# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""OpenAI provider for LLM chat and embedding operations.

Supports GPT-4o, o1, o3, o4-mini, GPT-5, and text-embedding-3-* models.
Handles reasoning model parameter filtering, BYOK multi-tenant client
caching, vision/audio content, and both sync/async operation.
"""

from __future__ import annotations

import logging
import re
from typing import Any, AsyncGenerator, List

from kaizen.nodes.ai.client_cache import BYOKClientCache
from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error
from kaizen.providers.base import ProviderCapability, UnifiedAIProvider
from kaizen.providers.types import Message, StreamEvent, TokenUsage

logger = logging.getLogger(__name__)

# Module-level BYOK client cache (shared across all OpenAI provider instances)
_byok_cache = BYOKClientCache(max_size=128, ttl_seconds=300)


class OpenAIProvider(UnifiedAIProvider):
    """OpenAI provider for both LLM and embedding operations.

    Prerequisites:
        * ``OPENAI_API_KEY`` environment variable
        * ``pip install openai``

    Supported LLM models:
        * o4-mini (latest, vision support, recommended)
        * o3 (reasoning model)

    Note: Uses ``max_completion_tokens`` parameter compatible with latest
    OpenAI models. Older models (gpt-4, gpt-3.5-turbo) are not supported.

    Supported embedding models:
        * text-embedding-3-large (3072 dimensions, configurable)
        * text-embedding-3-small (1536 dimensions, configurable)
        * text-embedding-ada-002 (1536 dimensions, legacy)
    """

    # Reasoning models that DON'T support temperature at all (o1, o3)
    _REASONING_MODEL_PATTERNS = [
        r"^o1",
        r"^o3",
    ]

    # Models that REQUIRE temperature=1.0 (GPT-5)
    _TEMPERATURE_1_ONLY_PATTERNS = [
        r"^gpt-?5",
    ]

    MODELS = [
        "o4-mini",
        "o3",
        "o3-mini",
        "o1",
        "o1-mini",
        "gpt-5",
        "gpt-4o",
        "gpt-4o-mini",
    ]

    def __init__(self, use_async: bool = False) -> None:
        super().__init__()
        self._use_async = use_async
        self._sync_client: Any = None
        self._async_client: Any = None

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        import os

        self._available = bool(os.getenv("OPENAI_API_KEY"))
        return self._available

    # ------------------------------------------------------------------
    # SPEC-02 capability declaration
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "openai"

    @property
    def capabilities(self) -> set[ProviderCapability]:
        return {
            ProviderCapability.CHAT_SYNC,
            ProviderCapability.CHAT_ASYNC,
            ProviderCapability.CHAT_STREAM,
            ProviderCapability.TOOLS,
            ProviderCapability.STRUCTURED_OUTPUT,
            ProviderCapability.EMBEDDINGS,
            ProviderCapability.VISION,
            ProviderCapability.AUDIO,
            ProviderCapability.REASONING_MODELS,
            ProviderCapability.BYOK,
        }

    # ------------------------------------------------------------------
    # Reasoning model helpers
    # ------------------------------------------------------------------

    def _is_reasoning_model(self, model: str) -> bool:
        if not model:
            return False
        model_lower = model.lower()
        for pattern in self._REASONING_MODEL_PATTERNS:
            if re.search(pattern, model_lower, re.IGNORECASE):
                return True
        return False

    def _requires_temperature_1(self, model: str) -> bool:
        if not model:
            return False
        model_lower = model.lower()
        for pattern in self._TEMPERATURE_1_ONLY_PATTERNS:
            if re.search(pattern, model_lower, re.IGNORECASE):
                return True
        return False

    def _filter_reasoning_model_params(
        self, model: str, generation_config: dict
    ) -> dict:
        if self._requires_temperature_1(model):
            filtered = generation_config.copy()
            unsupported = {"top_p", "frequency_penalty", "presence_penalty"}
            removed = []
            for key in unsupported:
                if key in filtered:
                    removed.append(f"{key}={filtered[key]}")
                    del filtered[key]
            if filtered.get("temperature") != 1.0:
                if "temperature" in filtered:
                    removed.append(
                        f"temperature={filtered['temperature']} (forced to 1.0)"
                    )
                filtered["temperature"] = 1.0
            if removed:
                logger.warning(
                    "Model %s requires temperature=1.0. Adjusted parameters: %s",
                    model,
                    ", ".join(removed),
                )
            return filtered

        if not self._is_reasoning_model(model):
            return generation_config

        filtered = generation_config.copy()
        unsupported = {"temperature", "top_p", "frequency_penalty", "presence_penalty"}
        removed = []
        for key in unsupported:
            if key in filtered:
                removed.append(f"{key}={filtered[key]}")
                del filtered[key]
        if removed:
            logger.warning(
                "Model %s is a reasoning model that doesn't support temperature. "
                "Removed unsupported parameters: %s",
                model,
                ", ".join(removed),
            )
        return filtered

    # ------------------------------------------------------------------
    # Chat (sync)
    # ------------------------------------------------------------------

    def chat(self, messages: List[Message], **kwargs: Any) -> dict[str, Any]:
        try:
            import openai

            model = kwargs.get("model", "o4-mini")
            generation_config = kwargs.get("generation_config", {})
            tools = kwargs.get("tools", [])

            per_request_api_key = kwargs.get("api_key")
            per_request_base_url = kwargs.get("base_url")

            if per_request_api_key or per_request_base_url:
                client_kwargs: dict[str, Any] = {}
                if per_request_api_key:
                    client_kwargs["api_key"] = per_request_api_key
                if per_request_base_url:
                    client_kwargs["base_url"] = per_request_base_url
                client = _byok_cache.get_or_create(
                    per_request_api_key,
                    per_request_base_url,
                    factory=lambda: openai.OpenAI(**client_kwargs),
                )
            else:
                if self._sync_client is None:
                    self._sync_client = openai.OpenAI()
                client = self._sync_client

            processed_messages = self._process_messages(messages)

            max_completion = generation_config.get(
                "max_completion_tokens"
            ) or generation_config.get("max_tokens")

            if (
                "max_tokens" in generation_config
                and "max_completion_tokens" not in generation_config
            ):
                import warnings

                warnings.warn(
                    "'max_tokens' is deprecated and will be removed in v0.5.0. "
                    "Please use 'max_completion_tokens' instead.",
                    DeprecationWarning,
                    stacklevel=3,
                )

            filtered_config = self._filter_reasoning_model_params(
                model, generation_config
            )

            request_params: dict[str, Any] = {
                "model": model,
                "messages": processed_messages,
                "max_completion_tokens": max_completion,
                "stop": filtered_config.get("stop"),
                "n": filtered_config.get("n", 1),
                "stream": kwargs.get("stream", False),
                "logit_bias": filtered_config.get("logit_bias"),
                "user": filtered_config.get("user"),
                "seed": filtered_config.get("seed"),
            }

            if not self._is_reasoning_model(model):
                request_params["temperature"] = filtered_config.get("temperature", 1.0)
                request_params["top_p"] = filtered_config.get("top_p", 1.0)
                request_params["frequency_penalty"] = filtered_config.get(
                    "frequency_penalty"
                )
                request_params["presence_penalty"] = filtered_config.get(
                    "presence_penalty"
                )

            response_format = filtered_config.get("response_format")
            if response_format and isinstance(response_format, dict):
                if "type" in response_format:
                    request_params["response_format"] = response_format

            request_params = {k: v for k, v in request_params.items() if v is not None}

            if tools:
                request_params["tools"] = tools
                default_choice = "required" if tools else "auto"
                request_params["tool_choice"] = generation_config.get(
                    "tool_choice", default_choice
                )
                logger.debug(
                    "OpenAI tools: %d tools, tool_choice=%s",
                    len(tools),
                    request_params.get("tool_choice"),
                )

            response = client.chat.completions.create(**request_params)

            choice = response.choices[0]
            return {
                "id": response.id,
                "content": choice.message.content,
                "role": choice.message.role,
                "model": response.model,
                "created": response.created,
                "tool_calls": (
                    choice.message.tool_calls
                    if hasattr(choice.message, "tool_calls")
                    else []
                ),
                "finish_reason": choice.finish_reason,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                "metadata": {},
            }

        except ImportError:
            raise RuntimeError(
                "OpenAI library not installed. Install with: pip install openai"
            )
        except openai.BadRequestError as e:
            logger.error("OpenAI BadRequestError: %s", e, exc_info=True)
            if "max_tokens" in str(e):
                raise RuntimeError(
                    "This OpenAI provider requires models that support max_completion_tokens. "
                    "Please use o4-mini, o3. "
                    "Older models like gpt-4o or gpt-3.5-turbo are not supported."
                )
            raise RuntimeError(sanitize_provider_error(e, "OpenAI"))
        except Exception as e:
            logger.error("OpenAI error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "OpenAI"))

    # ------------------------------------------------------------------
    # Chat (async)
    # ------------------------------------------------------------------

    async def chat_async(
        self, messages: List[Message], **kwargs: Any
    ) -> dict[str, Any]:
        try:
            import openai

            model = kwargs.get("model", "o4-mini")
            generation_config = kwargs.get("generation_config", {})
            tools = kwargs.get("tools", [])

            per_request_api_key = kwargs.get("api_key")
            per_request_base_url = kwargs.get("base_url")

            if per_request_api_key or per_request_base_url:
                from openai import AsyncOpenAI

                client_kwargs: dict[str, Any] = {}
                if per_request_api_key:
                    client_kwargs["api_key"] = per_request_api_key
                if per_request_base_url:
                    client_kwargs["base_url"] = per_request_base_url
                async_client = AsyncOpenAI(**client_kwargs)
            else:
                if self._async_client is None:
                    from openai import AsyncOpenAI

                    self._async_client = AsyncOpenAI()
                async_client = self._async_client

            processed_messages = self._process_messages(messages)

            max_completion = generation_config.get(
                "max_completion_tokens"
            ) or generation_config.get("max_tokens")

            if (
                "max_tokens" in generation_config
                and "max_completion_tokens" not in generation_config
            ):
                import warnings

                warnings.warn(
                    "'max_tokens' is deprecated and will be removed in v0.5.0. "
                    "Please use 'max_completion_tokens' instead.",
                    DeprecationWarning,
                    stacklevel=3,
                )

            filtered_config = self._filter_reasoning_model_params(
                model, generation_config
            )

            request_params: dict[str, Any] = {
                "model": model,
                "messages": processed_messages,
                "max_completion_tokens": max_completion,
                "stop": filtered_config.get("stop"),
                "n": filtered_config.get("n", 1),
                "stream": kwargs.get("stream", False),
                "logit_bias": filtered_config.get("logit_bias"),
                "user": filtered_config.get("user"),
                "seed": filtered_config.get("seed"),
            }

            if not self._is_reasoning_model(model):
                request_params["temperature"] = filtered_config.get("temperature", 1.0)
                request_params["top_p"] = filtered_config.get("top_p", 1.0)
                request_params["frequency_penalty"] = filtered_config.get(
                    "frequency_penalty"
                )
                request_params["presence_penalty"] = filtered_config.get(
                    "presence_penalty"
                )

            response_format = filtered_config.get("response_format")
            if response_format and isinstance(response_format, dict):
                if "type" in response_format:
                    request_params["response_format"] = response_format

            request_params = {k: v for k, v in request_params.items() if v is not None}

            if tools:
                request_params["tools"] = tools
                default_choice = "required" if tools else "auto"
                request_params["tool_choice"] = generation_config.get(
                    "tool_choice", default_choice
                )
                logger.debug(
                    "OpenAI async tools: %d tools, tool_choice=%s",
                    len(tools),
                    request_params.get("tool_choice"),
                )

            response = await async_client.chat.completions.create(**request_params)

            choice = response.choices[0]
            return {
                "id": response.id,
                "content": choice.message.content,
                "role": choice.message.role,
                "model": response.model,
                "created": response.created,
                "tool_calls": (
                    choice.message.tool_calls
                    if hasattr(choice.message, "tool_calls")
                    else []
                ),
                "finish_reason": choice.finish_reason,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                "metadata": {},
            }

        except ImportError:
            raise RuntimeError(
                "OpenAI library not installed. Install with: pip install openai"
            )
        except openai.BadRequestError as e:
            logger.error("OpenAI BadRequestError: %s", e, exc_info=True)
            if "max_tokens" in str(e):
                raise RuntimeError(
                    "This OpenAI provider requires models that support max_completion_tokens. "
                    "Please use o4-mini, o3. "
                    "Older models like gpt-4o or gpt-3.5-turbo are not supported."
                )
            raise RuntimeError(sanitize_provider_error(e, "OpenAI"))
        except Exception as e:
            logger.error("OpenAI error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "OpenAI"))

    # ------------------------------------------------------------------
    # Chat (streaming) — SPEC-02 StreamingProvider protocol
    # ------------------------------------------------------------------

    async def stream_chat(
        self, messages: List[Message], **kwargs: Any
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream tokens from OpenAI chat.completions.create(stream=True).

        Genuinely iterates the AsyncOpenAI streaming response — one
        :class:`StreamEvent` per incoming delta chunk, followed by a final
        ``"done"`` event carrying the accumulated text, finish reason, and
        usage (when ``stream_options={"include_usage": True}`` is supported).
        """
        # Import is unconditional — ModuleNotFoundError propagates as a
        # clear error. Wrapping in try/except here confuses static analysers
        # about whether ``openai`` is bound in the rest of the method.
        import openai

        model = kwargs.get("model", "o4-mini")
        generation_config = dict(kwargs.get("generation_config", {}) or {})
        tools = kwargs.get("tools", [])

        per_request_api_key = kwargs.get("api_key")
        per_request_base_url = kwargs.get("base_url")

        if per_request_api_key or per_request_base_url:
            client_kwargs: dict[str, Any] = {}
            if per_request_api_key:
                client_kwargs["api_key"] = per_request_api_key
            if per_request_base_url:
                client_kwargs["base_url"] = per_request_base_url
            async_client = openai.AsyncOpenAI(**client_kwargs)
        else:
            if self._async_client is None:
                self._async_client = openai.AsyncOpenAI()
            async_client = self._async_client

        processed_messages = self._process_messages(messages)

        max_completion = generation_config.get(
            "max_completion_tokens"
        ) or generation_config.get("max_tokens")

        filtered_config = self._filter_reasoning_model_params(model, generation_config)

        request_params: dict[str, Any] = {
            "model": model,
            "messages": processed_messages,
            "max_completion_tokens": max_completion,
            "stop": filtered_config.get("stop"),
            "n": filtered_config.get("n", 1),
            "stream": True,
            "stream_options": {"include_usage": True},
            "logit_bias": filtered_config.get("logit_bias"),
            "user": filtered_config.get("user"),
            "seed": filtered_config.get("seed"),
        }

        if not self._is_reasoning_model(model):
            request_params["temperature"] = filtered_config.get("temperature", 1.0)
            request_params["top_p"] = filtered_config.get("top_p", 1.0)
            request_params["frequency_penalty"] = filtered_config.get(
                "frequency_penalty"
            )
            request_params["presence_penalty"] = filtered_config.get("presence_penalty")

        response_format = filtered_config.get("response_format")
        if response_format and isinstance(response_format, dict):
            if "type" in response_format:
                request_params["response_format"] = response_format

        request_params = {k: v for k, v in request_params.items() if v is not None}

        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = generation_config.get("tool_choice", "auto")

        logger.debug(
            "openai.stream_chat.start model=%s tools=%d",
            model,
            len(tools) if tools else 0,
        )

        try:
            stream = await async_client.chat.completions.create(**request_params)

            accumulated_text = ""
            # Accumulate tool calls across chunks (OpenAI streams tool calls
            # in partial deltas keyed by index).
            tool_call_acc: dict[int, dict[str, Any]] = {}
            last_finish_reason: str | None = None
            last_usage: dict[str, int] = {}

            async for chunk in stream:
                if not chunk.choices:
                    # Final usage-only chunk (stream_options.include_usage).
                    if getattr(chunk, "usage", None) is not None:
                        last_usage = {
                            "prompt_tokens": chunk.usage.prompt_tokens,
                            "completion_tokens": chunk.usage.completion_tokens,
                            "total_tokens": chunk.usage.total_tokens,
                        }
                    continue

                choice = chunk.choices[0]
                delta = choice.delta

                if delta is None:
                    continue

                text_piece = getattr(delta, "content", None)
                if text_piece:
                    accumulated_text += text_piece
                    yield StreamEvent(
                        event_type="text_delta",
                        delta_text=text_piece,
                        content=accumulated_text,
                        model=model,
                    )

                delta_tool_calls = getattr(delta, "tool_calls", None) or []
                for tc_delta in delta_tool_calls:
                    idx = getattr(tc_delta, "index", 0) or 0
                    acc = tool_call_acc.setdefault(
                        idx,
                        {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        },
                    )
                    if getattr(tc_delta, "id", None):
                        acc["id"] = tc_delta.id
                    fn_delta = getattr(tc_delta, "function", None)
                    if fn_delta is not None:
                        name_piece = getattr(fn_delta, "name", None)
                        args_piece = getattr(fn_delta, "arguments", None)
                        if name_piece:
                            acc["function"]["name"] += name_piece
                        if args_piece:
                            acc["function"]["arguments"] += args_piece

                if choice.finish_reason:
                    last_finish_reason = choice.finish_reason

            logger.debug(
                "openai.stream_chat.done model=%s chars=%d finish=%s",
                model,
                len(accumulated_text),
                last_finish_reason,
            )

            final_tool_calls = [tool_call_acc[k] for k in sorted(tool_call_acc)]
            yield StreamEvent(
                event_type="done",
                content=accumulated_text,
                tool_calls=final_tool_calls,
                finish_reason=last_finish_reason or "stop",
                model=model,
                usage=last_usage,
            )
        except Exception as exc:  # pragma: no cover - re-raise sanitised
            logger.error("openai.stream_chat.error error=%s", exc, exc_info=True)
            raise RuntimeError(sanitize_provider_error(exc, "OpenAI"))

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        try:
            import openai

            model = kwargs.get("model", "text-embedding-3-small")
            dimensions = kwargs.get("dimensions")
            user = kwargs.get("user")

            if self._sync_client is None:
                self._sync_client = openai.OpenAI()

            request_params: dict[str, Any] = {"model": model, "input": texts}
            if dimensions and "embedding-3" in model:
                request_params["dimensions"] = dimensions
            if user:
                request_params["user"] = user

            response = self._sync_client.embeddings.create(**request_params)
            return [item.embedding for item in response.data]

        except ImportError:
            raise RuntimeError(
                "OpenAI library not installed. Install with: pip install openai"
            )
        except Exception as e:
            logger.error("OpenAI embedding error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "OpenAI"))

    async def embed_async(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        try:
            import openai

            model = kwargs.get("model", "text-embedding-3-small")
            dimensions = kwargs.get("dimensions")
            user = kwargs.get("user")

            if self._async_client is None:
                from openai import AsyncOpenAI

                self._async_client = AsyncOpenAI()

            request_params: dict[str, Any] = {"model": model, "input": texts}
            if dimensions and "embedding-3" in model:
                request_params["dimensions"] = dimensions
            if user:
                request_params["user"] = user

            response = await self._async_client.embeddings.create(**request_params)
            return [item.embedding for item in response.data]

        except ImportError:
            raise RuntimeError(
                "OpenAI library not installed. Install with: pip install openai"
            )
        except Exception as e:
            logger.error("OpenAI embedding error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "OpenAI"))

    def get_model_info(self, model: str) -> dict[str, Any]:
        models = {
            "text-embedding-3-large": {
                "dimensions": 3072,
                "max_tokens": 8191,
                "description": "Most capable embedding model, supports dimensions",
                "capabilities": {
                    "variable_dimensions": True,
                    "min_dimensions": 256,
                    "max_dimensions": 3072,
                },
            },
            "text-embedding-3-small": {
                "dimensions": 1536,
                "max_tokens": 8191,
                "description": "Efficient embedding model, supports dimensions",
                "capabilities": {
                    "variable_dimensions": True,
                    "min_dimensions": 256,
                    "max_dimensions": 1536,
                },
            },
            "text-embedding-ada-002": {
                "dimensions": 1536,
                "max_tokens": 8191,
                "description": "Legacy embedding model",
                "capabilities": {"variable_dimensions": False},
            },
        }
        return models.get(
            model,
            {
                "dimensions": 1536,
                "max_tokens": 8191,
                "description": f"OpenAI model: {model}",
                "capabilities": {},
            },
        )

    # ------------------------------------------------------------------
    # Message processing helper
    # ------------------------------------------------------------------

    def _process_messages(self, messages: List[Message]) -> list:
        """Process messages for vision/audio content."""
        processed_messages = []
        for msg in messages:
            if isinstance(msg.get("content"), list):
                processed_content = []
                for item in msg["content"]:
                    if item.get("type") == "text":
                        processed_content.append(
                            {"type": "text", "text": item.get("text", "")}
                        )
                    elif item.get("type") == "image":
                        from kaizen.nodes.ai.vision_utils import (
                            encode_image,
                            get_media_type,
                            validate_image_size,
                        )

                        if "path" in item:
                            is_valid, error_msg = validate_image_size(item["path"])
                            if not is_valid:
                                raise ValueError(
                                    f"Image validation failed: {error_msg}"
                                )
                            base64_image = encode_image(item["path"])
                            media_type = get_media_type(item["path"])
                        elif "base64" in item:
                            base64_image = item["base64"]
                            media_type = item.get("media_type", "image/jpeg")
                        else:
                            raise ValueError(
                                "Image item must have either 'path' or 'base64' field"
                            )

                        processed_content.append(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{media_type};base64,{base64_image}"
                                },
                            }
                        )
                    elif item.get("type") == "audio":
                        from kaizen.nodes.ai.audio_utils import (
                            encode_audio,
                            get_audio_media_type,
                            validate_audio_size,
                        )

                        if "path" in item:
                            is_valid, error_msg = validate_audio_size(item["path"])
                            if not is_valid:
                                raise ValueError(
                                    f"Audio validation failed: {error_msg}"
                                )
                            base64_audio = encode_audio(item["path"])
                            media_type = get_audio_media_type(item["path"])
                        elif "base64" in item:
                            base64_audio = item["base64"]
                            media_type = item.get("media_type", "audio/mpeg")
                        elif "bytes" in item:
                            import base64

                            base64_audio = base64.b64encode(item["bytes"]).decode(
                                "utf-8"
                            )
                            media_type = item.get("media_type", "audio/mpeg")
                        else:
                            raise ValueError(
                                "Audio item must have 'path', 'base64', or 'bytes' field"
                            )

                        audio_format = media_type.split("/")[-1]
                        if audio_format == "mpeg":
                            audio_format = "mp3"
                        elif audio_format == "mp4":
                            audio_format = "m4a"

                        processed_content.append(
                            {
                                "type": "input_audio",
                                "input_audio": {
                                    "data": base64_audio,
                                    "format": audio_format,
                                },
                            }
                        )
                    elif item.get("type") == "audio_url":
                        import base64 as b64_mod

                        url = item.get("url", "")
                        if url.startswith("data:audio"):
                            header, b64_data = url.split(",", 1)
                            media_type = header.replace("data:", "").split(";")[0]
                            audio_format = media_type.split("/")[-1]
                            if audio_format == "mpeg":
                                audio_format = "mp3"
                            elif audio_format == "mp4":
                                audio_format = "m4a"
                            processed_content.append(
                                {
                                    "type": "input_audio",
                                    "input_audio": {
                                        "data": b64_data,
                                        "format": audio_format,
                                    },
                                }
                            )
                    else:
                        content_type = item.get("type", "unknown")
                        if content_type not in ("text", "image", "audio", "audio_url"):
                            import warnings

                            warnings.warn(
                                f"Unhandled content type '{content_type}' in message. "
                                "This content will be skipped. Supported types: text, image, audio, audio_url.",
                                UserWarning,
                                stacklevel=2,
                            )

                processed_messages.append(
                    {"role": msg.get("role", "user"), "content": processed_content}
                )
            else:
                processed_messages.append(msg)
        return processed_messages
