# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Azure AI Foundry provider for LLM and embedding operations.

Supports models deployed on Azure AI Foundry including Azure OpenAI,
Meta Llama, Mistral, and Cohere models. Handles vision, structured output,
and both sync/async operation.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, List

from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error
from kaizen.providers.base import ProviderCapability, UnifiedAIProvider
from kaizen.providers.types import Message, StreamEvent

logger = logging.getLogger(__name__)


class AzureAIFoundryProvider(UnifiedAIProvider):
    """Azure AI Foundry provider for LLM and embedding operations.

    Prerequisites:
        * Azure subscription with AI Foundry resource
        * Deployed model endpoint
        * ``AZURE_AI_INFERENCE_ENDPOINT`` environment variable
        * ``AZURE_AI_INFERENCE_API_KEY`` environment variable
    """

    MODELS = ["gpt-4o", "gpt-4-turbo", "Llama-3.1-*", "Mistral-large"]

    def __init__(self, use_async: bool = False) -> None:
        super().__init__()
        self._use_async = use_async
        self._sync_chat_client: Any = None
        self._sync_embed_client: Any = None
        self._async_chat_client: Any = None
        self._async_embed_client: Any = None
        self._model_cache: dict[str, dict[str, Any]] = {}

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        import os

        endpoint = os.getenv("AZURE_AI_INFERENCE_ENDPOINT")
        api_key = os.getenv("AZURE_AI_INFERENCE_API_KEY")
        self._available = bool(endpoint and api_key)
        return self._available

    # ------------------------------------------------------------------
    # SPEC-02 capability declaration
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "azure"

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
            ProviderCapability.BYOK,
        }

    def _get_credential(self) -> Any:
        import os

        from azure.core.credentials import AzureKeyCredential

        api_key = os.getenv("AZURE_AI_INFERENCE_API_KEY")
        if api_key:
            return AzureKeyCredential(api_key)
        try:
            from azure.identity import DefaultAzureCredential

            return DefaultAzureCredential()
        except ImportError:
            raise RuntimeError(
                "No API key found and azure-identity not installed. "
                "Set AZURE_AI_INFERENCE_API_KEY or install azure-identity."
            )

    def _get_endpoint(self) -> str:
        import os

        endpoint = os.getenv("AZURE_AI_INFERENCE_ENDPOINT")
        if not endpoint:
            raise RuntimeError(
                "AZURE_AI_INFERENCE_ENDPOINT environment variable not set."
            )
        return endpoint

    def _convert_messages(self, messages: List[Message]) -> list:
        from azure.ai.inference.models import (
            AssistantMessage,
            SystemMessage,
            UserMessage,
        )

        azure_messages: list[Any] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if isinstance(content, list):
                try:
                    from azure.ai.inference.models import (
                        ImageContentItem,
                        ImageUrl,
                        TextContentItem,
                    )

                    content_items: list[Any] = []
                    for item in content:
                        if item.get("type") == "text":
                            content_items.append(
                                TextContentItem(text=item.get("text", ""))
                            )
                        elif item.get("type") == "image_url":
                            url = item.get("image_url", {}).get("url", "")
                            content_items.append(
                                ImageContentItem(image_url=ImageUrl(url=url))
                            )
                        elif item.get("type") == "image":
                            if "path" in item:
                                from kaizen.nodes.ai.vision_utils import (
                                    encode_image,
                                    get_media_type,
                                )

                                base64_data = encode_image(item["path"])
                                media_type = get_media_type(item["path"])
                                url = f"data:{media_type};base64,{base64_data}"
                            elif "base64" in item:
                                media_type = item.get("media_type", "image/jpeg")
                                url = f"data:{media_type};base64,{item['base64']}"
                            else:
                                continue
                            content_items.append(
                                ImageContentItem(image_url=ImageUrl(url=url))
                            )
                        else:
                            content_type = item.get("type", "unknown")
                            if content_type not in ("text", "image", "image_url"):
                                import warnings

                                warnings.warn(
                                    f"Unhandled content type '{content_type}' in AzureAIFoundryProvider. "
                                    "Only 'text', 'image', and 'image_url' are supported.",
                                    UserWarning,
                                    stacklevel=2,
                                )

                    if role == "user":
                        azure_messages.append(UserMessage(content=content_items))
                    else:
                        text_content = " ".join(
                            item.get("text", "")
                            for item in content
                            if item.get("type") == "text"
                        )
                        if role == "system":
                            azure_messages.append(SystemMessage(content=text_content))
                        elif role == "assistant":
                            azure_messages.append(
                                AssistantMessage(content=text_content)
                            )

                except ImportError:
                    text_parts = [
                        item.get("text", "")
                        for item in content
                        if item.get("type") == "text"
                    ]
                    text_content = " ".join(text_parts)
                    if role == "system":
                        azure_messages.append(SystemMessage(content=text_content))
                    elif role == "assistant":
                        azure_messages.append(AssistantMessage(content=text_content))
                    else:
                        azure_messages.append(UserMessage(content=text_content))
            else:
                if role == "system":
                    azure_messages.append(SystemMessage(content=content))
                elif role == "assistant":
                    azure_messages.append(AssistantMessage(content=content))
                else:
                    azure_messages.append(UserMessage(content=content))

        return azure_messages

    def _format_tool_calls(self, message: Any) -> list:
        if not hasattr(message, "tool_calls") or not message.tool_calls:
            return []
        return [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in message.tool_calls
        ]

    def _handle_response_format(
        self, generation_config: dict, request_params: dict
    ) -> None:
        response_format = generation_config.get("response_format")
        if response_format and isinstance(response_format, dict):
            response_type = response_format.get("type")
            try:
                from azure.ai.inference.models import JsonSchemaFormat

                if response_type == "json_schema":
                    json_schema = response_format.get("json_schema", {})
                    request_params["response_format"] = JsonSchemaFormat(
                        name=json_schema.get("name", "response"),
                        schema=json_schema.get("schema", {}),
                        strict=json_schema.get("strict", True),
                    )
                elif response_type == "json_object":
                    request_params["response_format"] = JsonSchemaFormat(
                        name="response",
                        schema={"type": "object"},
                        strict=False,
                    )
            except ImportError:
                pass

    def chat(self, messages: List[Message], **kwargs: Any) -> dict[str, Any]:
        try:
            from azure.ai.inference import ChatCompletionsClient
            from azure.core.credentials import AzureKeyCredential

            generation_config = kwargs.get("generation_config", {})
            model = kwargs.get("model")
            tools = kwargs.get("tools", [])

            per_request_api_key = kwargs.get("api_key")
            per_request_base_url = kwargs.get("base_url")

            if per_request_api_key or per_request_base_url:
                endpoint = per_request_base_url or self._get_endpoint()
                credential = (
                    AzureKeyCredential(per_request_api_key)
                    if per_request_api_key
                    else self._get_credential()
                )
                chat_client = ChatCompletionsClient(
                    endpoint=endpoint, credential=credential
                )
            else:
                if self._sync_chat_client is None:
                    self._sync_chat_client = ChatCompletionsClient(
                        endpoint=self._get_endpoint(),
                        credential=self._get_credential(),
                    )
                chat_client = self._sync_chat_client

            azure_messages = self._convert_messages(messages)

            request_params: dict[str, Any] = {
                "messages": azure_messages,
                "temperature": generation_config.get("temperature", 0.7),
                "max_tokens": generation_config.get("max_tokens"),
                "top_p": generation_config.get("top_p"),
                "stop": generation_config.get("stop"),
                "stream": kwargs.get("stream", False),
            }

            if model:
                request_params["model"] = model
            if tools:
                request_params["tools"] = tools
                request_params["tool_choice"] = generation_config.get(
                    "tool_choice", "auto"
                )

            self._handle_response_format(generation_config, request_params)
            request_params = {k: v for k, v in request_params.items() if v is not None}

            response = chat_client.complete(**request_params)
            choice = response.choices[0]

            return {
                "id": response.id,
                "content": choice.message.content,
                "role": "assistant",
                "model": response.model,
                "created": (
                    int(response.created.timestamp()) if response.created else None
                ),
                "tool_calls": self._format_tool_calls(choice.message),
                "finish_reason": choice.finish_reason,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                "metadata": {"provider": "azure_ai_foundry"},
            }

        except ImportError:
            raise RuntimeError(
                "Azure AI Inference library not installed. "
                "Install with: pip install azure-ai-inference azure-identity"
            )
        except Exception as e:
            logger.error("Azure AI Foundry error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Azure AI Foundry"))

    async def chat_async(
        self, messages: List[Message], **kwargs: Any
    ) -> dict[str, Any]:
        try:
            from azure.ai.inference.aio import ChatCompletionsClient
            from azure.core.credentials import AzureKeyCredential

            generation_config = kwargs.get("generation_config", {})
            model = kwargs.get("model")
            tools = kwargs.get("tools", [])

            per_request_api_key = kwargs.get("api_key")
            per_request_base_url = kwargs.get("base_url")

            if per_request_api_key or per_request_base_url:
                endpoint = per_request_base_url or self._get_endpoint()
                credential = (
                    AzureKeyCredential(per_request_api_key)
                    if per_request_api_key
                    else self._get_credential()
                )
                async_chat_client = ChatCompletionsClient(
                    endpoint=endpoint, credential=credential
                )
            else:
                if self._async_chat_client is None:
                    self._async_chat_client = ChatCompletionsClient(
                        endpoint=self._get_endpoint(),
                        credential=self._get_credential(),
                    )
                async_chat_client = self._async_chat_client

            azure_messages = self._convert_messages(messages)

            request_params: dict[str, Any] = {
                "messages": azure_messages,
                "temperature": generation_config.get("temperature", 0.7),
                "max_tokens": generation_config.get("max_tokens"),
                "top_p": generation_config.get("top_p"),
                "stop": generation_config.get("stop"),
                "stream": kwargs.get("stream", False),
            }

            if model:
                request_params["model"] = model
            if tools:
                request_params["tools"] = tools
                request_params["tool_choice"] = generation_config.get(
                    "tool_choice", "auto"
                )

            self._handle_response_format(generation_config, request_params)
            request_params = {k: v for k, v in request_params.items() if v is not None}

            response = await async_chat_client.complete(**request_params)
            choice = response.choices[0]

            return {
                "id": response.id,
                "content": choice.message.content,
                "role": "assistant",
                "model": response.model,
                "created": (
                    int(response.created.timestamp()) if response.created else None
                ),
                "tool_calls": self._format_tool_calls(choice.message),
                "finish_reason": choice.finish_reason,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                "metadata": {"provider": "azure_ai_foundry"},
            }

        except ImportError:
            raise RuntimeError(
                "Azure AI Inference library not installed. "
                "Install with: pip install azure-ai-inference azure-identity"
            )
        except Exception as e:
            logger.error("Azure AI Foundry async error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Azure AI Foundry"))

    # ------------------------------------------------------------------
    # Chat (streaming) — SPEC-02 StreamingProvider protocol
    # ------------------------------------------------------------------

    async def stream_chat(
        self, messages: List[Message], **kwargs: Any
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream tokens from Azure AI Inference ChatCompletionsClient.

        Iterates the real per-chunk ``StreamingChatCompletionsUpdate`` events
        via ``ChatCompletionsClient.complete(stream=True)``.
        """
        from azure.ai.inference.aio import ChatCompletionsClient

        model = kwargs.get("model")
        generation_config = dict(kwargs.get("generation_config", {}) or {})

        endpoint = self._get_endpoint()
        credential = self._get_credential()

        async_chat_client = ChatCompletionsClient(
            endpoint=endpoint, credential=credential
        )

        processed_messages = self._process_messages(messages)

        complete_kwargs: dict[str, Any] = {
            "messages": processed_messages,
            "model": model,
            "stream": True,
        }
        if generation_config.get("temperature") is not None:
            complete_kwargs["temperature"] = generation_config["temperature"]
        if generation_config.get("max_tokens") is not None:
            complete_kwargs["max_tokens"] = generation_config["max_tokens"]
        if generation_config.get("top_p") is not None:
            complete_kwargs["top_p"] = generation_config["top_p"]

        logger.debug("azure.stream_chat.start model=%s", model)

        accumulated_text = ""
        last_finish_reason: str | None = None
        last_usage: dict[str, int] = {}

        try:
            stream = await async_chat_client.complete(**complete_kwargs)
            async for update in stream:
                choices = getattr(update, "choices", None) or []
                if not choices:
                    usage_obj = getattr(update, "usage", None)
                    if usage_obj is not None:
                        last_usage = {
                            "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0),
                            "completion_tokens": getattr(
                                usage_obj, "completion_tokens", 0
                            ),
                            "total_tokens": getattr(usage_obj, "total_tokens", 0),
                        }
                    continue
                choice = choices[0]
                delta = getattr(choice, "delta", None)
                text_piece = getattr(delta, "content", None) if delta else None
                if text_piece:
                    accumulated_text += text_piece
                    yield StreamEvent(
                        event_type="text_delta",
                        delta_text=text_piece,
                        content=accumulated_text,
                        model=model or "",
                    )
                fr = getattr(choice, "finish_reason", None)
                if fr:
                    last_finish_reason = str(fr)

            logger.debug(
                "azure.stream_chat.done model=%s chars=%d finish=%s",
                model,
                len(accumulated_text),
                last_finish_reason,
            )

            yield StreamEvent(
                event_type="done",
                content=accumulated_text,
                finish_reason=last_finish_reason or "stop",
                model=model or "",
                usage=last_usage,
            )
        except Exception as exc:  # pragma: no cover
            logger.error("azure.stream_chat.error error=%s", exc, exc_info=True)
            raise RuntimeError(sanitize_provider_error(exc, "Azure AI Foundry"))
        finally:
            try:
                await async_chat_client.close()
            except Exception:
                pass  # cleanup path — carve-out per zero-tolerance.md Rule 3

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        try:
            from azure.ai.inference import EmbeddingsClient

            model = kwargs.get("model")
            if self._sync_embed_client is None:
                self._sync_embed_client = EmbeddingsClient(
                    endpoint=self._get_endpoint(),
                    credential=self._get_credential(),
                )
            request_params: dict[str, Any] = {"input": texts}
            if model:
                request_params["model"] = model
            response = self._sync_embed_client.embed(**request_params)
            return [item.embedding for item in response.data]

        except ImportError:
            raise RuntimeError(
                "Azure AI Inference library not installed. Install with: pip install azure-ai-inference"
            )
        except Exception as e:
            logger.error("Azure AI Foundry embedding error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Azure AI Foundry"))

    async def embed_async(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        try:
            from azure.ai.inference.aio import EmbeddingsClient

            model = kwargs.get("model")
            if self._async_embed_client is None:
                self._async_embed_client = EmbeddingsClient(
                    endpoint=self._get_endpoint(),
                    credential=self._get_credential(),
                )
            request_params: dict[str, Any] = {"input": texts}
            if model:
                request_params["model"] = model
            response = await self._async_embed_client.embed(**request_params)
            return [item.embedding for item in response.data]

        except ImportError:
            raise RuntimeError(
                "Azure AI Inference library not installed. Install with: pip install azure-ai-inference"
            )
        except Exception as e:
            logger.error("Azure AI Foundry async embedding error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Azure AI Foundry"))

    def get_model_info(self, model: str) -> dict[str, Any]:
        if model in self._model_cache:
            return self._model_cache[model]

        known_models = {
            "text-embedding-3-small": {
                "dimensions": 1536,
                "max_tokens": 8191,
                "description": "Azure OpenAI small embedding model",
                "capabilities": {"variable_dimensions": True},
            },
            "text-embedding-3-large": {
                "dimensions": 3072,
                "max_tokens": 8191,
                "description": "Azure OpenAI large embedding model",
                "capabilities": {"variable_dimensions": True},
            },
            "text-embedding-ada-002": {
                "dimensions": 1536,
                "max_tokens": 8191,
                "description": "Azure OpenAI ada embedding model",
                "capabilities": {"variable_dimensions": False},
            },
        }

        if model in known_models:
            self._model_cache[model] = known_models[model]
            return known_models[model]

        return {
            "dimensions": 1536,
            "max_tokens": 8191,
            "description": f"Azure AI Foundry model: {model}",
            "capabilities": {},
        }
