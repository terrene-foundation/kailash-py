"""Azure backend implementations for Unified Azure Provider.

This module provides concrete backend implementations for Azure services:
- AzureOpenAIBackend: Uses OpenAI SDK with Azure configuration
- AzureAIFoundryBackend: Uses Azure AI Inference SDK

Both backends implement the AzureBackend abstract interface for interoperability.
"""

import logging
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default API version for Azure OpenAI
DEFAULT_API_VERSION = "2024-10-21"

# Patterns for reasoning models that require special handling
REASONING_MODEL_PATTERNS = [
    r"^o1",  # o1, o1-preview, o1-mini
    r"^o3",  # o3, o3-mini
    r"^gpt-5",  # gpt-5, GPT-5-turbo
]


class AzureBackend(ABC):
    """
    Abstract base class for Azure service backends.

    Defines the common interface that all Azure backends must implement,
    enabling seamless switching between Azure OpenAI Service and Azure AI Foundry.
    """

    @abstractmethod
    def is_configured(self) -> bool:
        """
        Check if the backend has valid configuration.

        Returns:
            True if all required configuration is present, False otherwise.
        """
        pass

    @abstractmethod
    def get_backend_type(self) -> str:
        """
        Return the backend identifier.

        Returns:
            "azure_openai" or "azure_ai_foundry"
        """
        pass

    @abstractmethod
    def chat(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
        """
        Synchronous chat completion.

        Args:
            messages: List of messages in OpenAI format
            **kwargs: Additional parameters (model, generation_config, tools, etc.)

        Returns:
            Standardized response dictionary
        """
        pass

    @abstractmethod
    async def chat_async(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
        """
        Asynchronous chat completion.

        Args:
            messages: List of messages in OpenAI format
            **kwargs: Additional parameters

        Returns:
            Standardized response dictionary
        """
        pass

    @abstractmethod
    def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        """
        Generate embeddings for texts.

        Args:
            texts: List of texts to embed
            **kwargs: Additional parameters (model, dimensions, etc.)

        Returns:
            List of embedding vectors
        """
        pass


class AzureOpenAIBackend(AzureBackend):
    """
    Azure OpenAI Service backend using OpenAI SDK.

    Uses the official OpenAI Python SDK with Azure configuration for:
    - Chat completions
    - Embeddings
    - Structured outputs (json_schema)
    - Reasoning models (o1, o3, GPT-5) with automatic parameter filtering

    Environment Variables:
        AZURE_OPENAI_ENDPOINT: Azure OpenAI endpoint URL
        AZURE_OPENAI_API_KEY: API key
        AZURE_API_VERSION: API version (default: 2024-10-21)
        AZURE_DEPLOYMENT: Default deployment name

        Alternative unified variables:
        AZURE_ENDPOINT: Unified endpoint URL
        AZURE_API_KEY: Unified API key
    """

    def __init__(self):
        """Initialize Azure OpenAI backend."""
        self._client = None
        self._async_client = None
        self._endpoint = self._get_endpoint()
        self._api_key = self._get_api_key()
        self._api_version = os.getenv("AZURE_API_VERSION", DEFAULT_API_VERSION)
        self._deployment = os.getenv("AZURE_DEPLOYMENT")

    def _get_endpoint(self) -> Optional[str]:
        """Get endpoint from environment variables."""
        return os.getenv("AZURE_OPENAI_ENDPOINT") or os.getenv("AZURE_ENDPOINT")

    def _get_api_key(self) -> Optional[str]:
        """Get API key from environment variables."""
        return os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("AZURE_API_KEY")

    def is_configured(self) -> bool:
        """Check if Azure OpenAI is configured."""
        return bool(self._endpoint and self._api_key)

    def get_backend_type(self) -> str:
        """Return backend identifier."""
        return "azure_openai"

    def _is_reasoning_model(self, model: Optional[str]) -> bool:
        """Check if model is a reasoning model (o1, o3, GPT-5)."""
        if not model:
            return False
        model_lower = model.lower()
        for pattern in REASONING_MODEL_PATTERNS:
            if re.search(pattern, model_lower, re.IGNORECASE):
                return True
        return False

    def _filter_params_for_model(
        self, model: Optional[str], params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Filter parameters based on model requirements.

        Reasoning models (o1, o3, GPT-5) don't support:
        - temperature (must be 1.0)
        - top_p (must be 1.0)
        - presence_penalty
        - frequency_penalty

        They also use max_completion_tokens instead of max_tokens.
        """
        if not self._is_reasoning_model(model):
            return params.copy()

        filtered = {}
        # Parameters to remove for reasoning models
        unsupported = {"temperature", "top_p", "presence_penalty", "frequency_penalty"}

        for key, value in params.items():
            if key in unsupported:
                logger.debug(
                    f"Filtering '{key}' parameter for reasoning model '{model}'"
                )
                continue
            if key == "max_tokens":
                # Translate to max_completion_tokens
                filtered["max_completion_tokens"] = value
                logger.debug(
                    f"Translated max_tokens to max_completion_tokens for '{model}'"
                )
            else:
                filtered[key] = value

        return filtered

    def _get_client(self):
        """Get or create sync Azure OpenAI client."""
        if self._client is None:
            from openai import AzureOpenAI

            self._client = AzureOpenAI(
                azure_endpoint=self._endpoint,
                api_key=self._api_key,
                api_version=self._api_version,
            )
        return self._client

    def _get_async_client(self):
        """Get or create async Azure OpenAI client."""
        if self._async_client is None:
            from openai import AsyncAzureOpenAI

            self._async_client = AsyncAzureOpenAI(
                azure_endpoint=self._endpoint,
                api_key=self._api_key,
                api_version=self._api_version,
            )
        return self._async_client

    def _format_response(
        self, response, provider: str = "azure_openai"
    ) -> Dict[str, Any]:
        """Format OpenAI API response to standardized format."""
        choice = response.choices[0]

        # Extract tool calls if present
        tool_calls = []
        if hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in choice.message.tool_calls
            ]

        return {
            "id": response.id,
            "content": choice.message.content,
            "role": choice.message.role,
            "model": response.model,
            "created": response.created,
            "tool_calls": tool_calls,
            "finish_reason": choice.finish_reason,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            "metadata": {"provider": provider},
        }

    def chat(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
        """Generate chat completion using Azure OpenAI."""
        client = self._get_client()

        generation_config = kwargs.get("generation_config", {})
        model = kwargs.get("model") or self._deployment
        tools = kwargs.get("tools", [])

        # Build request parameters
        request_params = {
            "model": model,
            "messages": messages,
            "temperature": generation_config.get("temperature", 0.7),
            "max_tokens": generation_config.get("max_tokens"),
            "top_p": generation_config.get("top_p"),
            "stop": generation_config.get("stop"),
            "stream": kwargs.get("stream", False),
        }

        # Add tools if provided
        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = generation_config.get("tool_choice", "auto")

        # Add response_format for structured output
        response_format = generation_config.get("response_format")
        if response_format:
            request_params["response_format"] = response_format

        # Filter parameters for reasoning models
        request_params = self._filter_params_for_model(model, request_params)

        # Remove None values
        request_params = {k: v for k, v in request_params.items() if v is not None}

        try:
            response = client.chat.completions.create(**request_params)
            return self._format_response(response)
        except Exception as e:
            raise RuntimeError(f"Azure OpenAI error: {str(e)}")

    async def chat_async(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
        """Generate chat completion using Azure OpenAI (async)."""
        client = self._get_async_client()

        generation_config = kwargs.get("generation_config", {})
        model = kwargs.get("model") or self._deployment
        tools = kwargs.get("tools", [])

        # Build request parameters
        request_params = {
            "model": model,
            "messages": messages,
            "temperature": generation_config.get("temperature", 0.7),
            "max_tokens": generation_config.get("max_tokens"),
            "top_p": generation_config.get("top_p"),
            "stop": generation_config.get("stop"),
            "stream": kwargs.get("stream", False),
        }

        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = generation_config.get("tool_choice", "auto")

        response_format = generation_config.get("response_format")
        if response_format:
            request_params["response_format"] = response_format

        # Filter parameters for reasoning models
        request_params = self._filter_params_for_model(model, request_params)
        request_params = {k: v for k, v in request_params.items() if v is not None}

        try:
            response = await client.chat.completions.create(**request_params)
            return self._format_response(response)
        except Exception as e:
            raise RuntimeError(f"Azure OpenAI async error: {str(e)}")

    def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        """Generate embeddings using Azure OpenAI."""
        client = self._get_client()

        model = kwargs.get("model") or "text-embedding-3-small"
        dimensions = kwargs.get("dimensions")

        request_params = {"model": model, "input": texts}
        if dimensions:
            request_params["dimensions"] = dimensions

        try:
            response = client.embeddings.create(**request_params)
            return [item.embedding for item in response.data]
        except Exception as e:
            raise RuntimeError(f"Azure OpenAI embedding error: {str(e)}")


class AzureAIFoundryBackend(AzureBackend):
    """
    Azure AI Foundry backend using Azure AI Inference SDK.

    Uses the Azure AI Inference SDK for:
    - Chat completions with various models (OpenAI, Llama, Mistral, etc.)
    - Embeddings
    - Vision (model-dependent)

    Environment Variables:
        AZURE_AI_INFERENCE_ENDPOINT: AI Foundry endpoint URL
        AZURE_AI_INFERENCE_API_KEY: API key

        Alternative unified variables:
        AZURE_ENDPOINT: Unified endpoint URL
        AZURE_API_KEY: Unified API key
    """

    def __init__(self):
        """Initialize Azure AI Foundry backend."""
        self._sync_chat_client = None
        self._async_chat_client = None
        self._sync_embed_client = None
        self._async_embed_client = None
        self._endpoint = self._get_endpoint()
        self._api_key = self._get_api_key()

    def _get_endpoint(self) -> Optional[str]:
        """Get endpoint from environment variables."""
        return os.getenv("AZURE_AI_INFERENCE_ENDPOINT") or os.getenv("AZURE_ENDPOINT")

    def _get_api_key(self) -> Optional[str]:
        """Get API key from environment variables."""
        return os.getenv("AZURE_AI_INFERENCE_API_KEY") or os.getenv("AZURE_API_KEY")

    def is_configured(self) -> bool:
        """Check if Azure AI Foundry is configured."""
        return bool(self._endpoint and self._api_key)

    def get_backend_type(self) -> str:
        """Return backend identifier."""
        return "azure_ai_foundry"

    def _get_credential(self):
        """Get Azure credential."""
        from azure.core.credentials import AzureKeyCredential

        if self._api_key:
            return AzureKeyCredential(self._api_key)

        # Fall back to DefaultAzureCredential
        try:
            from azure.identity import DefaultAzureCredential

            return DefaultAzureCredential()
        except ImportError:
            raise RuntimeError(
                "No API key found and azure-identity not installed. "
                "Set AZURE_AI_INFERENCE_API_KEY or install azure-identity."
            )

    def _translate_response_format(self, response_format: Dict) -> Any:
        """
        Translate OpenAI response_format to Azure JsonSchemaFormat.

        Args:
            response_format: OpenAI-style response format dict

        Returns:
            Azure SDK format object or None
        """
        if not response_format:
            return None

        response_type = response_format.get("type")

        try:
            from azure.ai.inference.models import JsonSchemaFormat

            if response_type == "json_schema":
                # OpenAI strict mode -> Azure JSON Schema mode
                json_schema = response_format.get("json_schema", {})
                return JsonSchemaFormat(
                    name=json_schema.get("name", "response"),
                    schema=json_schema.get("schema", {}),
                    strict=json_schema.get("strict", True),
                )
            elif response_type == "json_object":
                # OpenAI legacy mode -> Azure JSON mode
                return JsonSchemaFormat(
                    name="response",
                    schema={"type": "object"},
                    strict=False,
                )
        except ImportError:
            logger.warning("JsonSchemaFormat not available, skipping response_format")
            return None

        return None

    def _convert_messages(self, messages: List[Dict]) -> List:
        """Convert messages to Azure format."""
        from azure.ai.inference.models import (
            AssistantMessage,
            SystemMessage,
            UserMessage,
        )

        azure_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            # Handle complex content (vision/multi-modal)
            if isinstance(content, list):
                try:
                    from azure.ai.inference.models import (
                        ImageContentItem,
                        ImageUrl,
                        TextContentItem,
                    )

                    content_items = []
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
                                from .vision_utils import encode_image, get_media_type

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
                # Simple string content
                if role == "system":
                    azure_messages.append(SystemMessage(content=content))
                elif role == "assistant":
                    azure_messages.append(AssistantMessage(content=content))
                else:
                    azure_messages.append(UserMessage(content=content))

        return azure_messages

    def _format_tool_calls(self, message) -> List:
        """Format tool calls from Azure response."""
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

    def _format_response(
        self, response, provider: str = "azure_ai_foundry"
    ) -> Dict[str, Any]:
        """Format Azure response to standardized format."""
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
            "metadata": {"provider": provider},
        }

    def chat(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
        """Generate chat completion using Azure AI Foundry."""
        from azure.ai.inference import ChatCompletionsClient

        generation_config = kwargs.get("generation_config", {})
        model = kwargs.get("model")
        tools = kwargs.get("tools", [])

        # Initialize client if needed
        if self._sync_chat_client is None:
            self._sync_chat_client = ChatCompletionsClient(
                endpoint=self._endpoint,
                credential=self._get_credential(),
            )

        # Convert messages
        azure_messages = self._convert_messages(messages)

        # Build request
        request_params = {
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
            request_params["tool_choice"] = generation_config.get("tool_choice", "auto")

        # Handle response_format
        response_format = generation_config.get("response_format")
        if response_format:
            translated = self._translate_response_format(response_format)
            if translated:
                request_params["response_format"] = translated

        request_params = {k: v for k, v in request_params.items() if v is not None}

        try:
            response = self._sync_chat_client.complete(**request_params)
            return self._format_response(response)
        except Exception as e:
            raise RuntimeError(f"Azure AI Foundry error: {str(e)}")

    async def chat_async(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
        """Generate chat completion using Azure AI Foundry (async)."""
        from azure.ai.inference.aio import ChatCompletionsClient

        generation_config = kwargs.get("generation_config", {})
        model = kwargs.get("model")
        tools = kwargs.get("tools", [])

        if self._async_chat_client is None:
            self._async_chat_client = ChatCompletionsClient(
                endpoint=self._endpoint,
                credential=self._get_credential(),
            )

        azure_messages = self._convert_messages(messages)

        request_params = {
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
            request_params["tool_choice"] = generation_config.get("tool_choice", "auto")

        response_format = generation_config.get("response_format")
        if response_format:
            translated = self._translate_response_format(response_format)
            if translated:
                request_params["response_format"] = translated

        request_params = {k: v for k, v in request_params.items() if v is not None}

        try:
            response = await self._async_chat_client.complete(**request_params)
            return self._format_response(response)
        except Exception as e:
            raise RuntimeError(f"Azure AI Foundry async error: {str(e)}")

    def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        """Generate embeddings using Azure AI Foundry."""
        from azure.ai.inference import EmbeddingsClient

        model = kwargs.get("model")

        if self._sync_embed_client is None:
            self._sync_embed_client = EmbeddingsClient(
                endpoint=self._endpoint,
                credential=self._get_credential(),
            )

        request_params = {"input": texts}
        if model:
            request_params["model"] = model

        try:
            response = self._sync_embed_client.embed(**request_params)
            return [item.embedding for item in response.data]
        except Exception as e:
            raise RuntimeError(f"Azure AI Foundry embedding error: {str(e)}")


# Re-export for convenience
ChatCompletionsClient = None  # Lazy import marker
