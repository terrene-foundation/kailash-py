# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Adapter registry -- resolve a provider name or model name to an adapter.

This module provides the deterministic configuration-driven logic that maps
``config.provider`` or model-name prefixes to concrete adapter instances.
This is *configuration branching* (permitted by the agent-reasoning rules),
NOT agent decision-making.

Provider resolution order:
    1. Explicit ``config.provider`` setting (if set)
    2. Model-name prefix heuristic (``claude-*`` -> anthropic, etc.)
    3. Default: ``openai``
"""

from __future__ import annotations

import logging
from typing import Any

from kaizen_agents.delegate.adapters.protocol import StreamingChatAdapter

logger = logging.getLogger(__name__)

# Model-name prefix -> provider mapping.
# This is infrastructure configuration, not agent reasoning.
_MODEL_PREFIX_MAP: list[tuple[str, str]] = [
    ("claude-", "anthropic"),
    ("gemini-", "google"),
    # Ollama models don't have a standard prefix; detected via explicit config
]


def get_adapter(
    provider: str,
    *,
    model: str = "",
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.4,
    max_tokens: int = 16384,
    **kwargs: Any,
) -> StreamingChatAdapter:
    """Create a streaming adapter for the named provider.

    Parameters
    ----------
    provider:
        Provider identifier: ``"openai"``, ``"anthropic"``, ``"google"``,
        ``"ollama"``.
    model:
        Default model name for the adapter.
    api_key:
        API key override (otherwise read from environment).
    base_url:
        Base URL override (for proxies or local endpoints).
    temperature:
        Default sampling temperature.
    max_tokens:
        Default max tokens.
    **kwargs:
        Extra keyword arguments forwarded to the adapter constructor.

    Returns
    -------
    A :class:`StreamingChatAdapter` instance.

    Raises
    ------
    ValueError:
        If the provider name is not recognised.
    """
    provider = provider.lower().strip()

    if provider == "openai":
        from kaizen_agents.delegate.adapters.openai_adapter import OpenAIStreamAdapter

        return OpenAIStreamAdapter(
            api_key=api_key,
            base_url=base_url,
            default_model=model,
            default_temperature=temperature,
            default_max_tokens=max_tokens,
            **kwargs,
        )

    if provider == "anthropic":
        from kaizen_agents.delegate.adapters.anthropic_adapter import AnthropicStreamAdapter

        return AnthropicStreamAdapter(
            api_key=api_key,
            default_model=model,
            default_temperature=temperature,
            default_max_tokens=max_tokens,
            **kwargs,
        )

    if provider == "google":
        from kaizen_agents.delegate.adapters.google_adapter import GoogleStreamAdapter

        return GoogleStreamAdapter(
            api_key=api_key,
            default_model=model,
            default_temperature=temperature,
            default_max_tokens=max_tokens,
            **kwargs,
        )

    if provider == "ollama":
        from kaizen_agents.delegate.adapters.ollama_adapter import OllamaStreamAdapter

        return OllamaStreamAdapter(
            base_url=base_url,
            default_model=model,
            default_temperature=temperature,
            default_max_tokens=max_tokens,
            **kwargs,
        )

    raise ValueError(
        f"Unknown provider '{provider}'.  "
        f"Supported providers: openai, anthropic, google, ollama"
    )


def get_adapter_for_model(
    model: str,
    *,
    provider: str = "",
    **kwargs: Any,
) -> StreamingChatAdapter:
    """Auto-detect the provider from a model name and create an adapter.

    If ``provider`` is explicitly given and non-empty, it takes precedence
    over model-name heuristics.  Otherwise the model name prefix is
    checked against known provider patterns.

    Parameters
    ----------
    model:
        The model name (e.g., ``"claude-sonnet-4-6"``, ``"gemini-2.0-flash"``).
    provider:
        Optional explicit provider override.
    **kwargs:
        Forwarded to :func:`get_adapter`.

    Returns
    -------
    A :class:`StreamingChatAdapter` instance.
    """
    if provider:
        return get_adapter(provider, model=model, **kwargs)

    # Auto-detect from model name prefix
    for prefix, detected_provider in _MODEL_PREFIX_MAP:
        if model.startswith(prefix):
            logger.debug(
                "Auto-detected provider '%s' from model prefix '%s'",
                detected_provider, prefix,
            )
            return get_adapter(detected_provider, model=model, **kwargs)

    # Default to OpenAI
    return get_adapter("openai", model=model, **kwargs)
