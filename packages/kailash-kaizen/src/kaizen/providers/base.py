# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Base classes and capability protocols for AI providers (SPEC-02).

Two coexisting layers:

1. **Legacy ABC hierarchy** — ``BaseAIProvider``, ``LLMProvider``,
   ``EmbeddingProvider``, ``UnifiedAIProvider``. The concrete per-provider
   modules inherit from these. Kept for backward compatibility with the
   5K-line monolith migration and every downstream consumer that imported
   them. No existing call site changes.

2. **SPEC-02 capability protocols** — ``BaseProvider``, ``AsyncLLMProvider``,
   ``StreamingProvider``, ``ToolCallingProvider``, ``StructuredOutputProvider``,
   plus the ``ProviderCapability`` enum. These are ``typing.Protocol`` classes
   with ``@runtime_checkable`` so callers can do ``isinstance(provider,
   StreamingProvider)`` to discover which capabilities a provider actually
   implements. The new protocols are satisfied structurally — any concrete
   class that exposes the required methods satisfies them, no explicit
   inheritance needed.

The two layers coexist: concrete providers continue to inherit from the ABC
layer (for lazy-init + capability dict behaviour), while the Protocol layer
gives consumers a structural way to ask "does this thing do streaming?"
without caring which base class it used.

See ``workspaces/platform-architecture-convergence/01-analysis/03-specs/02-spec-provider-layer.md``.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, AsyncGenerator, List, Protocol, runtime_checkable

from kaizen.providers.types import ChatResponse, Message, StreamEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SPEC-02 capability taxonomy
# ---------------------------------------------------------------------------


class ProviderCapability(Enum):
    """Capability flags for provider feature discovery (SPEC-02 §2.1).

    A provider declares which capabilities it supports via its ``capabilities``
    attribute. Consumers use :meth:`BaseProvider.supports` or direct set
    membership to gate calls.
    """

    CHAT_SYNC = "chat_sync"
    CHAT_ASYNC = "chat_async"
    CHAT_STREAM = "chat_stream"
    TOOLS = "tools"
    STRUCTURED_OUTPUT = "structured_output"
    EMBEDDINGS = "embeddings"
    VISION = "vision"
    AUDIO = "audio"
    REASONING_MODELS = "reasoning_models"
    BYOK = "byok"


# ---------------------------------------------------------------------------
# SPEC-02 capability protocols (runtime-checkable)
# ---------------------------------------------------------------------------


@runtime_checkable
class BaseProvider(Protocol):
    """Minimal structural contract every provider satisfies (SPEC-02 §2.1).

    Concrete providers do NOT need to inherit from this — any class exposing
    ``name`` and ``capabilities`` satisfies the protocol structurally.
    """

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> set[ProviderCapability]: ...

    def supports(self, capability: ProviderCapability) -> bool:
        return capability in self.capabilities


@runtime_checkable
class AsyncLLMProvider(Protocol):
    """Protocol for providers that expose an async chat completion method.

    A provider satisfies this if it defines ``async def chat_async(messages,
    **kwargs)`` returning a chat response (dict or :class:`ChatResponse`).
    """

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> set[ProviderCapability]: ...

    async def chat_async(
        self, messages: List[Message], **kwargs: Any
    ) -> dict[str, Any] | ChatResponse: ...


@runtime_checkable
class StreamingProvider(Protocol):
    """Protocol for providers that expose token-by-token streaming.

    A provider satisfies this if it defines ``async def stream_chat(messages,
    **kwargs)`` that yields :class:`StreamEvent` instances as chunks arrive
    from the underlying SDK. Consumers rely on this protocol to build real
    streaming agents (e.g. ``StreamingAgent``) — a single synthesized yield
    does NOT satisfy the contract.
    """

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> set[ProviderCapability]: ...

    def stream_chat(
        self, messages: List[Message], **kwargs: Any
    ) -> AsyncGenerator[StreamEvent, None]: ...


@runtime_checkable
class ToolCallingProvider(Protocol):
    """Protocol for providers that support native function calling.

    A provider satisfies this by implementing ``chat_with_tools(messages,
    tools, **kwargs)``. The default implementation on every LLM provider in
    this repo delegates to ``chat(messages, tools=tools, **kwargs)`` — the
    provider's regular chat path already handles tools when they are passed
    through ``kwargs``.
    """

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> set[ProviderCapability]: ...

    def chat_with_tools(
        self,
        messages: List[Message],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any] | ChatResponse: ...


@runtime_checkable
class StructuredOutputProvider(Protocol):
    """Protocol for providers that support JSON-schema / structured outputs.

    A provider satisfies this by implementing ``chat_structured(messages,
    schema, **kwargs)``. Typically it translates the schema into the
    provider's native format (OpenAI's ``response_format=json_schema``,
    Gemini's ``response_json_schema``, Anthropic's JSON-mode prompt injection)
    and delegates to the standard chat path.
    """

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> set[ProviderCapability]: ...

    def chat_structured(
        self,
        messages: List[Message],
        schema: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any] | ChatResponse: ...


# ---------------------------------------------------------------------------
# Legacy ABC hierarchy — unchanged, still used by concrete providers
# ---------------------------------------------------------------------------


class BaseAIProvider(ABC):
    """Base class for all AI provider implementations.

    Establishes lazy initialisation, cached availability checks, and a
    capability dictionary that consumers query at runtime.
    """

    #: Default capability set for providers that do not override ``capabilities``.
    #: Subclasses override this or the ``capabilities`` property directly.
    _DEFAULT_CAPABILITIES: set[ProviderCapability] = set()

    def __init__(self) -> None:
        self._client: Any = None
        self._available: bool | None = None
        self._capabilities: dict[str, bool] = {"chat": False, "embeddings": False}

    @abstractmethod
    def is_available(self) -> bool:
        """Return True when the provider's prerequisites are satisfied."""

    # ------------------------------------------------------------------
    # SPEC-02 BaseProvider protocol compatibility
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Provider name derived from the class name.

        ``OpenAIProvider`` → ``"openai"``; ``GoogleGeminiProvider`` → ``"google"``.
        Concrete providers may override for explicit control.
        """
        class_name = self.__class__.__name__
        if class_name.endswith("Provider"):
            class_name = class_name[: -len("Provider")]
        # GoogleGeminiProvider -> google
        for known in (
            "google",
            "openai",
            "anthropic",
            "ollama",
            "azure",
            "docker",
            "perplexity",
            "cohere",
            "huggingface",
            "mock",
        ):
            if known in class_name.lower():
                return known
        return class_name.lower()

    @property
    def capabilities(self) -> set[ProviderCapability]:
        """Capability set derived from the legacy dict + subclass overrides.

        Default mapping: ``{"chat": True}`` → ``CHAT_SYNC`` + ``CHAT_ASYNC``;
        ``{"embeddings": True}`` → ``EMBEDDINGS``. Providers override for
        finer control (adding ``CHAT_STREAM``, ``TOOLS``, ``VISION`` etc.).
        """
        caps: set[ProviderCapability] = set(self._DEFAULT_CAPABILITIES)
        if self._capabilities.get("chat", False):
            caps.add(ProviderCapability.CHAT_SYNC)
            caps.add(ProviderCapability.CHAT_ASYNC)
        if self._capabilities.get("embeddings", False):
            caps.add(ProviderCapability.EMBEDDINGS)
        return caps

    def supports(self, capability: ProviderCapability) -> bool:
        """Return True when this provider declares the given capability."""
        return capability in self.capabilities

    # ------------------------------------------------------------------
    # Legacy capability dict API (preserved)
    # ------------------------------------------------------------------

    def get_capabilities(self) -> dict[str, bool]:
        return self._capabilities.copy()

    def supports_chat(self) -> bool:
        return self._capabilities.get("chat", False)

    def supports_embeddings(self) -> bool:
        return self._capabilities.get("embeddings", False)


class LLMProvider(BaseAIProvider):
    """Abstract base for providers that support LLM chat operations."""

    def __init__(self) -> None:
        super().__init__()
        self._capabilities["chat"] = True

    @abstractmethod
    def chat(self, messages: List[Message], **kwargs: Any) -> dict[str, Any]:
        """Generate a chat completion.

        Args:
            messages: Conversation in OpenAI message format.
            **kwargs: Provider-specific parameters (model, generation_config, etc.).

        Returns:
            Standardised response dict.
        """

    def chat_with_tools(
        self,
        messages: List[Message],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Default ToolCallingProvider implementation.

        Delegates to :meth:`chat` with ``tools`` passed through kwargs.
        Concrete providers with a custom tool pipeline may override.
        """
        return self.chat(messages, tools=tools, **kwargs)

    def chat_structured(
        self,
        messages: List[Message],
        schema: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Default StructuredOutputProvider implementation.

        Builds an OpenAI-style ``response_format`` from the schema and
        delegates to :meth:`chat`. Providers with a different native format
        (Gemini, Anthropic) override this method.
        """
        generation_config = dict(kwargs.pop("generation_config", {}) or {})
        generation_config["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema.get("title", "output"),
                "strict": True,
                "schema": schema,
            },
        }
        return self.chat(messages, generation_config=generation_config, **kwargs)


class EmbeddingProvider(BaseAIProvider):
    """Abstract base for providers that support embedding generation."""

    def __init__(self) -> None:
        super().__init__()
        self._capabilities["embeddings"] = True

    @abstractmethod
    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        """Generate embeddings for *texts*."""

    @abstractmethod
    def get_model_info(self, model: str) -> dict[str, Any]:
        """Return metadata about an embedding *model*."""


class UnifiedAIProvider(LLMProvider, EmbeddingProvider):
    """Base for providers supporting both chat and embeddings."""

    def __init__(self) -> None:
        super().__init__()
        self._capabilities = {"chat": True, "embeddings": True}
