# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shared provider-name -> four-axis ``LlmDeployment`` resolver (#1720 Wave-A).

Promoted from the module-private ``kaizen.nodes.ai.llm_agent::_shadow_deployment_for``
so that BOTH the Wave-2 dual-run shadow AND the Wave-B consumer cutover
(``embedding_generator``, the live ``llm_agent`` path) resolve a legacy
provider name to the matching four-axis preset through ONE surface, with
identical mapping. ``llm_agent`` keeps a thin ``_shadow_deployment_for``
wrapper that delegates here (no behavior change for the shadow).

The mapping is preserved byte-for-byte from the original shadow resolver:

* **api-key providers** (``openai`` / ``anthropic`` / ``google`` / ``gemini`` /
  ``cohere`` / ``huggingface`` / ``perplexity`` / ``pplx``): resolve the
  credential from the per-request ``api_key`` override, else the provider's
  own ``<PROVIDER>_API_KEY`` env var (``rules/env-models.md``); a missing
  credential returns ``None`` (skip).
* **base-url providers** (``ollama`` / ``docker``): require a ``base_url``;
  a missing one returns ``None`` (skip).
* **unmapped providers**: return ``None`` (skip).

(Azure providers and the known-but-unsupported ``azure_ai_foundry`` blocker
are added in #1720 Wave-A invariant #3, layered on this promotion.)

``resolve_deployment_for`` does NOT guarantee never-raises for the mapped
providers: the preset factories (``openai_preset`` etc.) and the Azure
deployment builder validate their own arguments and MAY raise (e.g.
``ValueError`` on an invalid model, ``InvalidEndpoint`` on a malformed
``base_url``). Shadow callers wrap the call in ``except BaseException`` to
stay non-load-bearing; live Wave-B callers surface the typed error.

Structural dispatch on the (typed, config-supplied) provider NAME is
permitted deterministic logic per ``rules/agent-reasoning.md`` -- it routes
on a deployment-level configuration value the caller chose, never on user
content.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# Providers whose four-axis preset is keyed on an API key + the env var the
# legacy provider itself reads. Preserved byte-for-byte from the original
# `_shadow_deployment_for` map.
def _api_key_preset_map() -> dict[str, tuple[Callable[..., Any], str]]:
    from kaizen.llm.presets import (
        anthropic_preset,
        cohere_preset,
        google_preset,
        huggingface_preset,
        openai_preset,
        perplexity_preset,
    )

    return {
        "openai": (openai_preset, "OPENAI_API_KEY"),
        "anthropic": (anthropic_preset, "ANTHROPIC_API_KEY"),
        "google": (google_preset, "GOOGLE_API_KEY"),
        "gemini": (google_preset, "GOOGLE_API_KEY"),
        "cohere": (cohere_preset, "COHERE_API_KEY"),
        "huggingface": (huggingface_preset, "HUGGINGFACE_API_KEY"),
        "perplexity": (perplexity_preset, "PERPLEXITY_API_KEY"),
        "pplx": (perplexity_preset, "PERPLEXITY_API_KEY"),
    }


# Providers whose four-axis preset is keyed on a base_url (local runtimes).
def _base_url_preset_map() -> dict[str, Callable[..., Any]]:
    from kaizen.llm.presets import docker_model_runner_preset, ollama_preset

    return {
        "ollama": ollama_preset,
        "docker": docker_model_runner_preset,
    }


def resolve_deployment_for(
    provider: str,
    model: str,
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
):
    """Resolve a four-axis ``LlmDeployment`` for a legacy ``provider`` name.

    Maps the legacy provider name (``kaizen.providers.registry.PROVIDERS``)
    onto the matching four-axis preset builder. Returns ``None`` when the
    provider has no four-axis mapping, or a required credential / base_url
    cannot be resolved -- callers treat ``None`` as "skip, already logged at
    DEBUG".

    ``api_key`` mirrors the legacy provider's own resolution: when the caller
    did not pass a per-request override, the same ``<PROVIDER>_API_KEY`` env
    var the legacy provider itself reads (``rules/env-models.md``) is tried
    before giving up.
    """
    provider_key = (provider or "").strip().lower()

    api_key_map = _api_key_preset_map()
    if provider_key in api_key_map:
        factory, env_var = api_key_map[provider_key]
        resolved_key = api_key or os.environ.get(env_var, "").strip() or None
        if not resolved_key:
            logger.debug(
                "llm.dual_run.shadow_skipped",
                extra={"provider": provider, "reason": "missing_api_key"},
            )
            return None
        kwargs: dict[str, Any] = {}
        if base_url:
            kwargs["base_url"] = base_url
        return factory(resolved_key, model, **kwargs)

    base_url_map = _base_url_preset_map()
    if provider_key in base_url_map:
        if not base_url:
            logger.debug(
                "llm.dual_run.shadow_skipped",
                extra={"provider": provider, "reason": "missing_base_url"},
            )
            return None
        factory = base_url_map[provider_key]
        return factory(base_url, model)

    logger.debug(
        "llm.dual_run.shadow_skipped",
        extra={"provider": provider, "reason": "unmapped_provider"},
    )
    return None


__all__ = ["resolve_deployment_for"]
