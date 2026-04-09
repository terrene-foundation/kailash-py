# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Anthropic provider for Claude LLM models.

Supports Claude 3.x family with vision, BYOK multi-tenant client caching,
and both sync/async operation.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, List

from kaizen.nodes.ai.client_cache import BYOKClientCache
from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error
from kaizen.providers.base import LLMProvider, ProviderCapability
from kaizen.providers.types import Message, StreamEvent

logger = logging.getLogger(__name__)

_byok_cache = BYOKClientCache(max_size=128, ttl_seconds=300)


class AnthropicProvider(LLMProvider):
    """Anthropic provider for Claude LLM models.

    Note: Anthropic currently only provides LLM capabilities, not embeddings.

    Prerequisites:
        * ``ANTHROPIC_API_KEY`` environment variable
        * ``pip install anthropic``

    Supported models:
        * claude-3-opus-20240229 (Most capable, slower)
        * claude-3-sonnet-20240229 (Balanced performance)
        * claude-3-haiku-20240307 (Fastest, most affordable)
    """

    MODELS = [
        "claude-3-opus-*",
        "claude-3-sonnet-*",
        "claude-3-haiku-*",
        "claude-3.5-*",
        "claude-sonnet-4-*",
        "claude-opus-4-*",
    ]

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        import os

        self._available = bool(os.getenv("ANTHROPIC_API_KEY"))
        return self._available

    # ------------------------------------------------------------------
    # SPEC-02 capability declaration
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def capabilities(self) -> set[ProviderCapability]:
        return {
            ProviderCapability.CHAT_SYNC,
            ProviderCapability.CHAT_ASYNC,
            ProviderCapability.CHAT_STREAM,
            ProviderCapability.TOOLS,
            ProviderCapability.STRUCTURED_OUTPUT,
            ProviderCapability.VISION,
            ProviderCapability.BYOK,
        }

    def _process_messages(self, messages: List[Message]) -> tuple[str | None, list]:
        """Convert messages to Anthropic format, extracting system message."""
        system_message = None
        user_messages: list[dict[str, Any]] = []

        for msg in messages:
            if msg["role"] == "system":
                system_message = (
                    msg["content"]
                    if isinstance(msg["content"], str)
                    else str(msg["content"])
                )
            else:
                if isinstance(msg.get("content"), list):
                    content_parts: list[dict[str, Any]] = []
                    for item in msg["content"]:
                        if item["type"] == "text":
                            content_parts.append({"type": "text", "text": item["text"]})
                        elif item["type"] == "image":
                            from kaizen.nodes.ai.vision_utils import (
                                encode_image,
                                get_media_type,
                            )

                            if "path" in item:
                                base64_image = encode_image(item["path"])
                                media_type = get_media_type(item["path"])
                            else:
                                base64_image = item.get("base64", "")
                                media_type = item.get("media_type", "image/jpeg")

                            content_parts.append(
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": base64_image,
                                    },
                                }
                            )
                        else:
                            content_type = item.get("type", "unknown")
                            if content_type not in ("text", "image"):
                                import warnings

                                warnings.warn(
                                    f"Unhandled content type '{content_type}' in AnthropicProvider. "
                                    "Only 'text' and 'image' are supported. This content will be skipped.",
                                    UserWarning,
                                    stacklevel=2,
                                )

                    user_messages.append(
                        {"role": msg["role"], "content": content_parts}
                    )
                else:
                    user_messages.append(msg)

        return system_message, user_messages

    def chat(self, messages: List[Message], **kwargs: Any) -> dict[str, Any]:
        try:
            import anthropic

            model = kwargs.get("model", "claude-3-sonnet-20240229")
            generation_config = kwargs.get("generation_config", {})

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
                    factory=lambda: anthropic.Anthropic(**client_kwargs),
                )
            else:
                if self._client is None:
                    self._client = anthropic.Anthropic()
                client = self._client

            system_message, user_messages = self._process_messages(messages)

            create_kwargs: dict[str, Any] = {
                "model": model,
                "messages": user_messages,
                "max_tokens": generation_config.get("max_tokens", 500),
                "temperature": generation_config.get("temperature", 0.7),
            }

            if system_message is not None:
                create_kwargs["system"] = system_message
            if generation_config.get("top_p") is not None:
                create_kwargs["top_p"] = generation_config["top_p"]
            if generation_config.get("top_k") is not None:
                create_kwargs["top_k"] = generation_config["top_k"]
            if generation_config.get("stop_sequences") is not None:
                create_kwargs["stop_sequences"] = generation_config["stop_sequences"]
            if generation_config.get("metadata") is not None:
                create_kwargs["metadata"] = generation_config["metadata"]

            response = client.messages.create(**create_kwargs)

            return {
                "id": response.id,
                "content": response.content[0].text,
                "role": "assistant",
                "model": response.model,
                "created": None,
                "tool_calls": [],
                "finish_reason": response.stop_reason,
                "usage": {
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens
                    + response.usage.output_tokens,
                },
                "metadata": {},
            }

        except ImportError:
            raise RuntimeError(
                "Anthropic library not installed. Install with: pip install anthropic"
            )
        except Exception as e:
            logger.error("Anthropic error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Anthropic"))

    async def chat_async(
        self, messages: List[Message], **kwargs: Any
    ) -> dict[str, Any]:
        try:
            import anthropic

            model = kwargs.get("model", "claude-3-sonnet-20240229")
            generation_config = kwargs.get("generation_config", {})

            per_request_api_key = kwargs.get("api_key")
            per_request_base_url = kwargs.get("base_url")

            if per_request_api_key or per_request_base_url:
                client_kwargs: dict[str, Any] = {}
                if per_request_api_key:
                    client_kwargs["api_key"] = per_request_api_key
                if per_request_base_url:
                    client_kwargs["base_url"] = per_request_base_url
                client = anthropic.AsyncAnthropic(**client_kwargs)
            else:
                client = anthropic.AsyncAnthropic()

            system_message, user_messages = self._process_messages(messages)

            create_kwargs: dict[str, Any] = {
                "model": model,
                "messages": user_messages,
                "max_tokens": generation_config.get("max_tokens", 500),
                "temperature": generation_config.get("temperature", 0.7),
            }

            if system_message is not None:
                create_kwargs["system"] = system_message
            if generation_config.get("top_p") is not None:
                create_kwargs["top_p"] = generation_config["top_p"]
            if generation_config.get("top_k") is not None:
                create_kwargs["top_k"] = generation_config["top_k"]
            if generation_config.get("stop_sequences") is not None:
                create_kwargs["stop_sequences"] = generation_config["stop_sequences"]

            response = await client.messages.create(**create_kwargs)

            return {
                "id": response.id,
                "content": response.content[0].text,
                "role": "assistant",
                "model": response.model,
                "created": None,
                "tool_calls": [],
                "finish_reason": response.stop_reason,
                "usage": {
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens
                    + response.usage.output_tokens,
                },
                "metadata": {},
            }

        except ImportError:
            raise RuntimeError(
                "Anthropic library not installed. Install with: pip install anthropic"
            )
        except Exception as e:
            logger.error("Anthropic async error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Anthropic"))

    # ------------------------------------------------------------------
    # Chat (streaming) — SPEC-02 StreamingProvider protocol
    # ------------------------------------------------------------------

    async def stream_chat(
        self, messages: List[Message], **kwargs: Any
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream tokens from Anthropic messages.stream().

        Genuinely iterates the AsyncAnthropic streaming context — one
        :class:`StreamEvent` per ``content_block_delta`` / ``text`` event,
        followed by a final ``"done"`` event with accumulated text, stop
        reason, and token usage.
        """
        # Unconditional import — ModuleNotFoundError propagates as a clear
        # error. Wrapping in try/except would leave ``anthropic`` possibly
        # unbound for the rest of the method (Pyright).
        import anthropic

        model = kwargs.get("model", "claude-3-sonnet-20240229")
        generation_config = dict(kwargs.get("generation_config", {}) or {})

        per_request_api_key = kwargs.get("api_key")
        per_request_base_url = kwargs.get("base_url")

        if per_request_api_key or per_request_base_url:
            client_kwargs: dict[str, Any] = {}
            if per_request_api_key:
                client_kwargs["api_key"] = per_request_api_key
            if per_request_base_url:
                client_kwargs["base_url"] = per_request_base_url
            async_client = anthropic.AsyncAnthropic(**client_kwargs)
        else:
            async_client = anthropic.AsyncAnthropic()

        system_message, user_messages = self._process_messages(messages)

        create_kwargs: dict[str, Any] = {
            "model": model,
            "messages": user_messages,
            "max_tokens": generation_config.get("max_tokens", 500),
            "temperature": generation_config.get("temperature", 0.7),
        }
        if system_message is not None:
            create_kwargs["system"] = system_message
        if generation_config.get("top_p") is not None:
            create_kwargs["top_p"] = generation_config["top_p"]
        if generation_config.get("top_k") is not None:
            create_kwargs["top_k"] = generation_config["top_k"]
        if generation_config.get("stop_sequences") is not None:
            create_kwargs["stop_sequences"] = generation_config["stop_sequences"]

        logger.debug("anthropic.stream_chat.start model=%s", model)

        accumulated_text = ""
        stop_reason: str | None = None
        usage: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        try:
            async with async_client.messages.stream(**create_kwargs) as stream:
                # The SDK emits ``text`` strings for streamed text chunks
                # and exposes the final message via ``get_final_message()``.
                async for text_piece in stream.text_stream:
                    if text_piece:
                        accumulated_text += text_piece
                        yield StreamEvent(
                            event_type="text_delta",
                            delta_text=text_piece,
                            content=accumulated_text,
                            model=model,
                        )

                final_message = await stream.get_final_message()
                if final_message is not None:
                    stop_reason = getattr(final_message, "stop_reason", None)
                    final_usage = getattr(final_message, "usage", None)
                    if final_usage is not None:
                        input_tokens = getattr(final_usage, "input_tokens", 0)
                        output_tokens = getattr(final_usage, "output_tokens", 0)
                        usage = {
                            "prompt_tokens": input_tokens,
                            "completion_tokens": output_tokens,
                            "total_tokens": input_tokens + output_tokens,
                        }

            logger.debug(
                "anthropic.stream_chat.done model=%s chars=%d stop=%s",
                model,
                len(accumulated_text),
                stop_reason,
            )

            yield StreamEvent(
                event_type="done",
                content=accumulated_text,
                finish_reason=stop_reason or "stop",
                model=model,
                usage=usage,
            )
        except Exception as exc:  # pragma: no cover - re-raise sanitised
            logger.error("anthropic.stream_chat.error error=%s", exc, exc_info=True)
            raise RuntimeError(sanitize_provider_error(exc, "Anthropic"))
