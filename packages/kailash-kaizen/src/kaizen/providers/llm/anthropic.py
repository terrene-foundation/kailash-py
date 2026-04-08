# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Anthropic provider for Claude LLM models.

Supports Claude 3.x family with vision, BYOK multi-tenant client caching,
and both sync/async operation.
"""

from __future__ import annotations

import logging
from typing import Any, List

from kaizen.nodes.ai.client_cache import BYOKClientCache
from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error
from kaizen.providers.base import LLMProvider
from kaizen.providers.types import Message

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
