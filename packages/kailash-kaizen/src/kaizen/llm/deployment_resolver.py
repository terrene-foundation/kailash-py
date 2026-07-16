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
* **azure providers** (``azure`` / ``azure_openai``): resolve endpoint +
  api-key (+ api-version) from the per-request overrides else the canonical
  ``AZURE_*`` env vars, and build an ``OpenAiChat``-wire deployment with an
  ``AzureEntra`` api-key auth strategy (``api-key: <KEY>`` header) — Azure
  OpenAI speaks the same on-wire JSON as OpenAI-direct; only the URL + auth
  header differ. A missing endpoint or api-key returns ``None`` (skip).
* **known-but-unsupported providers** (``azure_ai_foundry``): raise
  :class:`UnsupportedDeploymentProvider` — a DOCUMENTED Wave-B blocker
  (no confirmed four-axis wire), NOT a silent ``None`` fallback
  (``rules/zero-tolerance.md`` Rule 3).
* **unmapped providers**: return ``None`` (skip) — a provider name this
  resolver has never heard of is a best-effort skip, distinct from a KNOWN
  provider we deliberately decline to map.

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


def legacy_tool_choice_default(tools: Any, explicit_choice: Any) -> Any:
    """Reproduce the legacy ``providers/llm`` chat ``tool_choice`` default.

    The legacy provider chat path (``providers/llm/openai.py``, also
    ``azure.py`` / ``docker.py``) sets ``default_choice = "required" if tools
    else "auto"`` and injects ``tool_choice="required"`` when tools are
    present AND the caller did not specify a choice. The four-axis
    ``LlmClient.complete`` defaults ``tool_choice=None`` (emits nothing ->
    the provider defaults to ``"auto"``), so a shadow / live four-axis call
    that does NOT reproduce this diverges from legacy on every tool-using
    agent — the Wave-2 dual-run shadow logged FALSE ``llm.dual_run.divergence``
    WARNs because of exactly this gap.

    Returns:

    * ``"required"`` — when ``tools`` are present AND no explicit choice was
      given (the legacy tools-present default);
    * the explicit choice — whenever the caller gave one (honored verbatim);
    * ``None`` — when no tools are present and no explicit choice was given
      (emit nothing, matching legacy, which skips the ``tool_choice`` block
      entirely when there are no tools).

    Shared home (this resolver module) so BOTH the Wave-2 dual-run shadow and
    the future Wave-B live-path migration import the SAME semantics rather
    than re-deriving them (which would let the two copies drift).
    """
    if tools and explicit_choice is None:
        return "required"
    return explicit_choice


class UnsupportedDeploymentProvider(ValueError):
    """A KNOWN provider has no confirmed four-axis ``LlmDeployment`` mapping.

    Raised by :func:`resolve_deployment_for` for a provider the resolver
    recognises but deliberately declines to map because it has no confirmed
    four-axis wire (currently ``azure_ai_foundry``). This is a DOCUMENTED
    blocker for the Wave-B cutover — surfacing it as a typed error rather
    than a silent ``None`` is the ``rules/zero-tolerance.md`` Rule 3
    (no silent fallbacks) disposition: a Wave-B implementer wiring this
    provider hits a clear signal instead of a shadow that silently never runs.
    """

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(
            f"provider {provider!r} has no confirmed four-axis LlmDeployment "
            "mapping (no confirmed wire); it cannot be resolved for the "
            "four-axis path. This is a DOCUMENTED Wave-B blocker, not a silent "
            "fallback (rules/zero-tolerance.md Rule 3) — add a confirmed wire "
            "mapping in kaizen.llm.deployment_resolver to enable it."
        )


# Legacy provider names that map onto an Azure-OpenAI four-axis deployment.
_AZURE_PROVIDERS = frozenset({"azure", "azure_openai"})

# KNOWN providers the resolver deliberately declines to map (no confirmed
# four-axis wire) — resolving one raises UnsupportedDeploymentProvider rather
# than silently returning None (rules/zero-tolerance.md Rule 3).
_UNSUPPORTED_PROVIDERS = frozenset({"azure_ai_foundry"})


def _resolve_azure_deployment(
    model: str, api_key: Optional[str], base_url: Optional[str]
):
    """Build an ``OpenAiChat``-wire Azure-OpenAI deployment (#1720 Wave-A #3).

    Azure OpenAI speaks the same on-wire JSON as OpenAI-direct; only the URL
    (``/openai/deployments/{deployment}/...?api-version=``) and the auth
    header (``api-key: <KEY>`` via ``AzureEntra`` api-key variant) differ —
    mirrors ``kaizen.llm.presets.azure_openai_preset``'s endpoint shape,
    sourcing the resource host from ``base_url`` and the deployment name from
    ``model`` instead of separate ``resource_name`` / ``deployment_name``
    args (the shadow/live callers only carry ``provider, model, api_key,
    base_url``).

    Credentials mirror the legacy Azure backend's own resolution
    (``kaizen.nodes.ai.azure_detection.resolve_azure_env``): the per-request
    override wins, else the canonical ``AZURE_*`` env vars (legacy
    ``AZURE_OPENAI_*`` names still resolve with a DeprecationWarning). A
    missing endpoint or api-key returns ``None`` (skip), matching the
    base-url family's missing-credential contract.
    """
    from kaizen.llm.auth.azure import AzureEntra
    from kaizen.llm.deployment import Endpoint, LlmDeployment, WireProtocol
    from kaizen.llm.grammar.azure_openai import AzureOpenAIGrammar
    from kaizen.llm.presets import AZURE_OPENAI_DEFAULT_API_VERSION
    from kaizen.nodes.ai.azure_detection import resolve_azure_env

    resolved_endpoint = base_url or resolve_azure_env(
        "AZURE_ENDPOINT", "AZURE_OPENAI_ENDPOINT"
    )
    if not resolved_endpoint:
        logger.debug(
            "llm.dual_run.shadow_skipped",
            extra={"provider": "azure", "reason": "missing_base_url"},
        )
        return None
    resolved_key = api_key or resolve_azure_env("AZURE_API_KEY", "AZURE_OPENAI_API_KEY")
    if not resolved_key:
        logger.debug(
            "llm.dual_run.shadow_skipped",
            extra={"provider": "azure", "reason": "missing_api_key"},
        )
        return None
    api_version = (
        resolve_azure_env("AZURE_API_VERSION", "AZURE_OPENAI_API_VERSION")
        or AZURE_OPENAI_DEFAULT_API_VERSION
    )

    # The deployment name is interpolated into the URL path; validate it
    # through the canonical Azure grammar (fail-closed on path-control chars)
    # BEFORE the f-string interpolation below — the same validator
    # azure_openai_preset uses.
    resolved_deployment = AzureOpenAIGrammar().resolve(model)

    endpoint = Endpoint(
        base_url=resolved_endpoint,
        path_prefix=f"/openai/deployments/{resolved_deployment}",
        # Azure REQUIRES ?api-version= on EVERY request URL; both
        # _build_completion_url and _build_embed_url append query_params.
        query_params={"api-version": api_version},
    )
    return LlmDeployment(
        wire=WireProtocol.OpenAiChat,
        endpoint=endpoint,
        auth=AzureEntra(api_key=resolved_key),
        default_model=resolved_deployment,
        preset_name="azure_openai",
    )


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
    DEBUG". Raises :class:`UnsupportedDeploymentProvider` for a KNOWN provider
    with no confirmed wire (``azure_ai_foundry``) — a documented Wave-B
    blocker, not a silent fallback.

    ``api_key`` mirrors the legacy provider's own resolution: when the caller
    did not pass a per-request override, the same ``<PROVIDER>_API_KEY`` env
    var the legacy provider itself reads (``rules/env-models.md``) is tried
    before giving up.
    """
    provider_key = (provider or "").strip().lower()

    if provider_key in _UNSUPPORTED_PROVIDERS:
        raise UnsupportedDeploymentProvider(provider_key)

    if provider_key in _AZURE_PROVIDERS:
        return _resolve_azure_deployment(model, api_key, base_url)

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


__all__ = [
    "resolve_deployment_for",
    "UnsupportedDeploymentProvider",
    "legacy_tool_choice_default",
]
