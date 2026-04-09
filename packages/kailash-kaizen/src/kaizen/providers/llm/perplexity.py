# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Perplexity AI provider for LLM operations with integrated web search.

Provides real-time web search capabilities integrated directly into the
language model, returning responses with citations and sources.
"""

from __future__ import annotations

import logging
from typing import Any, List

from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error
from kaizen.providers.base import LLMProvider
from kaizen.providers.types import Message

logger = logging.getLogger(__name__)


class PerplexityProvider(LLMProvider):
    """Perplexity AI provider for LLM operations with integrated web search.

    Prerequisites:
        * ``PERPLEXITY_API_KEY`` environment variable
        * ``pip install openai`` (uses OpenAI-compatible API)

    Supported models:
        * sonar (lightweight search)
        * sonar-pro (advanced search)
        * sonar-reasoning (chain-of-thought with search)
        * sonar-reasoning-pro (premier reasoning)
        * sonar-deep-research (exhaustive research)
    """

    BASE_URL = "https://api.perplexity.ai"
    DEFAULT_MODEL = "sonar"

    SUPPORTED_MODELS = {
        "sonar": {
            "description": "Lightweight search model",
            "supports_search": True,
            "supports_citations": True,
            "context_length": 128000,
        },
        "sonar-pro": {
            "description": "Advanced search capabilities",
            "supports_search": True,
            "supports_citations": True,
            "context_length": 200000,
        },
        "sonar-reasoning": {
            "description": "Reasoning with search",
            "supports_search": True,
            "supports_citations": True,
            "context_length": 128000,
        },
        "sonar-reasoning-pro": {
            "description": "Premier reasoning model",
            "supports_search": True,
            "supports_citations": True,
            "context_length": 128000,
        },
        "sonar-deep-research": {
            "description": "Exhaustive research with effort levels",
            "supports_search": True,
            "supports_citations": True,
            "supports_reasoning_effort": True,
            "context_length": 128000,
        },
    }

    MODELS = list(SUPPORTED_MODELS.keys())

    def __init__(self, use_async: bool = False) -> None:
        super().__init__()
        self._use_async = use_async
        self._sync_client: Any = None
        self._async_client: Any = None

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        import os

        self._available = bool(os.getenv("PERPLEXITY_API_KEY"))
        return self._available

    def _get_api_key(self) -> str:
        import os

        api_key = os.getenv("PERPLEXITY_API_KEY")
        if not api_key:
            raise RuntimeError(
                "PERPLEXITY_API_KEY not found. Set the environment variable to use Perplexity."
            )
        return api_key

    def _process_messages(self, messages: List[Message]) -> list:
        processed = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                processed_content: list[dict[str, Any]] = []
                for item in content:
                    if item.get("type") == "text":
                        processed_content.append(
                            {"type": "text", "text": item.get("text", "")}
                        )
                    elif item.get("type") == "image":
                        if "url" in item:
                            processed_content.append(
                                {"type": "image_url", "image_url": {"url": item["url"]}}
                            )
                        elif "path" in item:
                            from kaizen.nodes.ai.vision_utils import (
                                encode_image,
                                get_media_type,
                            )

                            base64_image = encode_image(item["path"])
                            media_type = get_media_type(item["path"])
                            processed_content.append(
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{media_type};base64,{base64_image}"
                                    },
                                }
                            )
                        elif "base64" in item:
                            media_type = item.get("media_type", "image/jpeg")
                            processed_content.append(
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{media_type};base64,{item['base64']}"
                                    },
                                }
                            )
                processed.append(
                    {"role": msg.get("role", "user"), "content": processed_content}
                )
            else:
                processed.append({"role": msg.get("role", "user"), "content": content})
        return processed

    def _build_request_params(
        self, messages: list, model: str, generation_config: dict, **kwargs: Any
    ) -> dict:
        params: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": generation_config.get("temperature", 0.2),
            "top_p": generation_config.get("top_p", 0.9),
        }

        if "max_tokens" in generation_config:
            params["max_tokens"] = generation_config["max_tokens"]
        if "presence_penalty" in generation_config:
            params["presence_penalty"] = generation_config["presence_penalty"]
        if "frequency_penalty" in generation_config:
            params["frequency_penalty"] = generation_config["frequency_penalty"]
        if "stop" in generation_config:
            params["stop"] = generation_config["stop"]
        if "response_format" in generation_config:
            params["response_format"] = generation_config["response_format"]
        if kwargs.get("stream", False):
            params["stream"] = True

        perplexity_config = kwargs.get("perplexity_config", {})
        extra_body: dict[str, Any] = {}

        if "return_related_questions" in perplexity_config:
            extra_body["return_related_questions"] = perplexity_config[
                "return_related_questions"
            ]
        if "return_images" in perplexity_config:
            extra_body["return_images"] = perplexity_config["return_images"]
        if "search_domain_filter" in perplexity_config:
            domains = perplexity_config["search_domain_filter"]
            if len(domains) > 20:
                raise ValueError("search_domain_filter supports maximum 20 domains")
            extra_body["search_domain_filter"] = domains
        if "search_recency_filter" in perplexity_config:
            valid_recency = ["month", "week", "day", "hour"]
            recency = perplexity_config["search_recency_filter"]
            if recency not in valid_recency:
                raise ValueError(
                    f"search_recency_filter must be one of: {valid_recency}"
                )
            extra_body["search_recency_filter"] = recency
        if "search_mode" in perplexity_config:
            valid_modes = ["web", "academic", "sec"]
            mode = perplexity_config["search_mode"]
            if mode not in valid_modes:
                raise ValueError(f"search_mode must be one of: {valid_modes}")
            extra_body["search_mode"] = mode
        if "reasoning_effort" in perplexity_config:
            if model == "sonar-deep-research":
                valid_efforts = ["low", "medium", "high"]
                effort = perplexity_config["reasoning_effort"]
                if effort not in valid_efforts:
                    raise ValueError(
                        f"reasoning_effort must be one of: {valid_efforts}"
                    )
                extra_body["reasoning_effort"] = effort
        if "language_preference" in perplexity_config:
            if model in ["sonar", "sonar-pro"]:
                extra_body["language_preference"] = perplexity_config[
                    "language_preference"
                ]
        if perplexity_config.get("disable_search", False):
            extra_body["disable_search"] = True

        for date_filter in [
            "search_after_date_filter",
            "search_before_date_filter",
            "last_updated_after_filter",
            "last_updated_before_filter",
        ]:
            if date_filter in perplexity_config:
                extra_body[date_filter] = perplexity_config[date_filter]

        if "web_search_options" in perplexity_config:
            extra_body["web_search_options"] = perplexity_config["web_search_options"]

        if extra_body:
            params["extra_body"] = extra_body

        return params

    def _format_response(self, response: Any, raw_response: dict | None = None) -> dict:
        choice = response.choices[0]
        metadata: dict[str, Any] = {}

        if hasattr(response, "citations") and response.citations:
            metadata["citations"] = response.citations
        elif raw_response and "citations" in raw_response:
            metadata["citations"] = raw_response["citations"]

        if hasattr(response, "search_results") and response.search_results:
            metadata["search_results"] = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "date": r.get("date", ""),
                }
                for r in response.search_results
            ]
        elif raw_response and "search_results" in raw_response:
            metadata["search_results"] = raw_response["search_results"]

        if hasattr(response, "related_questions") and response.related_questions:
            metadata["related_questions"] = response.related_questions
        elif raw_response and "related_questions" in raw_response:
            metadata["related_questions"] = raw_response["related_questions"]

        if hasattr(response, "images") and response.images:
            metadata["images"] = response.images
        elif raw_response and "images" in raw_response:
            metadata["images"] = raw_response["images"]

        usage: dict[str, Any] = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                "completion_tokens": getattr(response.usage, "completion_tokens", 0),
                "total_tokens": getattr(response.usage, "total_tokens", 0),
            }
            if hasattr(response.usage, "search_context_tokens"):
                usage["search_context_tokens"] = response.usage.search_context_tokens
            if hasattr(response.usage, "citation_tokens"):
                usage["citation_tokens"] = response.usage.citation_tokens

        return {
            "id": response.id if hasattr(response, "id") else "",
            "content": choice.message.content if choice.message.content else "",
            "role": "assistant",
            "model": response.model if hasattr(response, "model") else "",
            "created": response.created if hasattr(response, "created") else None,
            "tool_calls": [],
            "finish_reason": choice.finish_reason if choice.finish_reason else "stop",
            "usage": usage,
            "metadata": metadata,
        }

    def chat(self, messages: List[Message], **kwargs: Any) -> dict[str, Any]:
        try:
            import openai

            model = kwargs.pop("model", self.DEFAULT_MODEL)
            generation_config = kwargs.pop("generation_config", {})

            per_request_api_key = kwargs.pop("api_key", None)
            per_request_base_url = kwargs.pop("base_url", None)

            if per_request_api_key or per_request_base_url:
                client = openai.OpenAI(
                    api_key=per_request_api_key or self._get_api_key(),
                    base_url=per_request_base_url or self.BASE_URL,
                )
            else:
                if self._sync_client is None:
                    self._sync_client = openai.OpenAI(
                        api_key=self._get_api_key(), base_url=self.BASE_URL
                    )
                client = self._sync_client

            processed_messages = self._process_messages(messages)
            request_params = self._build_request_params(
                processed_messages, model, generation_config, **kwargs
            )
            response = client.chat.completions.create(**request_params)
            return self._format_response(response)

        except ImportError:
            raise RuntimeError(
                "OpenAI library not installed. Install with: pip install openai"
            )
        except Exception as e:
            logger.error("Perplexity error: %s", e, exc_info=True)
            if "api_key" in str(e).lower():
                raise RuntimeError(
                    "Perplexity API key invalid or not set. "
                    "Set PERPLEXITY_API_KEY environment variable."
                )
            raise RuntimeError(sanitize_provider_error(e, "Perplexity"))

    async def chat_async(
        self, messages: List[Message], **kwargs: Any
    ) -> dict[str, Any]:
        try:
            from openai import AsyncOpenAI

            model = kwargs.pop("model", self.DEFAULT_MODEL)
            generation_config = kwargs.pop("generation_config", {})

            per_request_api_key = kwargs.pop("api_key", None)
            per_request_base_url = kwargs.pop("base_url", None)

            if per_request_api_key or per_request_base_url:
                client = AsyncOpenAI(
                    api_key=per_request_api_key or self._get_api_key(),
                    base_url=per_request_base_url or self.BASE_URL,
                )
            else:
                if self._async_client is None:
                    self._async_client = AsyncOpenAI(
                        api_key=self._get_api_key(), base_url=self.BASE_URL
                    )
                client = self._async_client

            processed_messages = self._process_messages(messages)
            request_params = self._build_request_params(
                processed_messages, model, generation_config, **kwargs
            )
            response = await client.chat.completions.create(**request_params)
            return self._format_response(response)

        except ImportError:
            raise RuntimeError(
                "OpenAI library not installed. Install with: pip install openai"
            )
        except Exception as e:
            logger.error("Perplexity error: %s", e, exc_info=True)
            if "api_key" in str(e).lower():
                raise RuntimeError(
                    "Perplexity API key invalid or not set. "
                    "Set PERPLEXITY_API_KEY environment variable."
                )
            raise RuntimeError(sanitize_provider_error(e, "Perplexity"))

    def get_supported_models(self) -> dict:
        return self.SUPPORTED_MODELS.copy()
