# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""LLM provider adapters for the Delegate.

Each adapter implements the :class:`StreamingChatAdapter` protocol, providing
model-agnostic streaming completions.  The Delegate does not know which LLM
provider is being used -- it calls the adapter through a uniform interface.

Adapters:
    protocol        -- StreamingChatAdapter protocol and StreamEvent dataclass
    openai_adapter  -- OpenAI / OpenAI-compatible endpoints
    anthropic_adapter -- Anthropic Claude models (native SDK)
    google_adapter  -- Google Gemini models (native SDK)
    ollama_adapter  -- Local Ollama models (httpx streaming)
    openai_stream   -- Low-level OpenAI SSE stream processor (internal)
"""

from kaizen_agents.delegate.adapters.protocol import StreamEvent, StreamingChatAdapter
from kaizen_agents.delegate.adapters.registry import (
    get_adapter,
    get_adapter_for_model,
    get_embedding_adapter,
)

__all__ = [
    "StreamEvent",
    "StreamingChatAdapter",
    "get_adapter",
    "get_adapter_for_model",
    "get_embedding_adapter",
]
