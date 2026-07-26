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
* **keyless LOCAL providers** (``ollama`` / ``docker``): resolve WITHOUT any
  credential -- they are local runtimes with ``StaticNone()`` auth, so
  availability is an ENDPOINT question only. The endpoint comes from the
  per-request ``base_url`` override, else the provider-scoped endpoint env
  var (``OLLAMA_BASE_URL`` / ``DOCKER_MODEL_RUNNER_URL``), else the
  provider's own canonical loopback default. Because a canonical default
  always exists, these providers NEVER return ``None`` -- a local runtime
  that is simply not running surfaces as a real connection error from the
  wire layer at call time, which names the actual failure, rather than as a
  reasonless "provider is not available" at resolve time.
* **azure providers** (``azure`` / ``azure_openai``): resolve endpoint +
  api-key (+ api-version) from the per-request overrides else the canonical
  ``AZURE_*`` env vars, and build an ``OpenAiChat``-wire deployment with an
  ``AzureEntra`` api-key auth strategy (``api-key: <KEY>`` header) — Azure
  OpenAI speaks the same on-wire JSON as OpenAI-direct; only the URL + auth
  header differ. A missing endpoint or api-key returns ``None`` (skip).
* **azure_ai_foundry** (#1892): resolves endpoint + api-key + model
  (+ api-version) from the per-request overrides else the canonical
  ``AZURE_AI_FOUNDRY_*`` env vars, and builds an ``OpenAiChat``-wire
  deployment via :func:`kaizen.llm.presets.azure_ai_foundry_preset` — the
  unified, MODEL-AGNOSTIC Foundry model-inference endpoint
  (``/models/chat/completions``). A missing endpoint or api-key returns
  ``None`` (skip), matching the ``azure`` / ``azure_openai`` contract.
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


# The legacy tools-present ``tool_choice`` default is PROVIDER-SPECIFIC — the
# providers do NOT agree, so a provider-agnostic default is wrong. It is ALSO
# stream-specific for openai (see the ``stream`` kwarg on the function below):
#   * ``openai`` non-stream chat (``OpenAIProvider.chat``) ->
#     ``default_choice = "required" if tools else "auto"`` -> "required";
#     BUT ``openai`` STREAM (``OpenAIProvider.stream_chat``) -> literal "auto".
#     openai is the ONLY provider whose stream vs non-stream default differs,
#     so it is the ONLY provider the ``stream`` kwarg below adjusts.
#   * ``azure`` / ``azure_openai`` non-stream chat -> "auto"; their
#     ``stream_chat`` builds NO tools and sets NO ``tool_choice`` (streaming
#     tool-calling unsupported), so their streaming tool_choice is moot.
#   * ``docker`` non-stream chat -> "auto"; its ``stream_chat`` DROPS tools
#     (``docker.stream_chat.tools_ignored``) and sets NO ``tool_choice``, so
#     its streaming tool_choice is likewise moot.
#   * every other legacy provider (perplexity/pplx, ollama, google/gemini,
#     anthropic, cohere, huggingface) sets NO ``tool_choice`` at all -> None.
# A provider absent from this map emits no tool_choice (None), matching legacy.
# This map holds the NON-STREAM chat defaults; the ``stream`` kwarg only
# adjusts openai (azure/docker do not stream tools, so their entry is unchanged).
_LEGACY_TOOL_CHOICE_DEFAULTS = {
    "openai": "required",
    "azure": "auto",
    "azure_openai": "auto",
    "docker": "auto",
}


def legacy_tool_choice_default(
    provider: Any, tools: Any, explicit_choice: Any, *, stream: bool = False
) -> Any:
    """Reproduce the legacy ``providers/llm`` chat ``tool_choice`` default.

    The legacy default is PROVIDER-SPECIFIC (see ``_LEGACY_TOOL_CHOICE_DEFAULTS``)
    AND, for openai, STREAM-SPECIFIC: legacy ``OpenAIProvider.chat`` forces
    ``"required"`` when tools are present and unset, but ``stream_chat`` forces
    ``"auto"``. ``azure``/``azure_openai``/``docker`` default to ``"auto"`` on
    BOTH the streaming and non-streaming paths; every other legacy provider sets
    no ``tool_choice`` at all. The four-axis ``LlmClient.complete`` defaults
    ``tool_choice=None`` (emits nothing), so a shadow / live four-axis call that
    does not reproduce the PER-PROVIDER, PER-MODE legacy default diverges from
    legacy — the Wave-2 dual-run shadow logged FALSE ``llm.dual_run.divergence``
    WARNs on openai tool-using agents because of exactly this gap. (A
    provider-AGNOSTIC ``"required"`` default is equally wrong — it OVER-injects
    ``"required"`` for azure/docker, whose legacy path sends ``"auto"``; and a
    stream-BLIND ``"required"`` over-injects on openai streaming, whose legacy
    ``stream_chat`` path sends ``"auto"``.)

    Args:
        stream: whether the call is a STREAMING completion. Only affects openai
            (whose legacy ``stream_chat`` default is ``"auto"`` vs ``chat``'s
            ``"required"``); azure/azure_openai/docker are ``"auto"`` regardless.

    Returns:

    * the explicit choice — whenever the caller gave one (honored verbatim);
    * ``None`` — when no tools are present (legacy skips the ``tool_choice``
      block entirely when there are no tools), OR when the provider sets no
      legacy ``tool_choice`` default;
    * ``"auto"`` — for openai when ``stream=True`` (legacy ``stream_chat``);
    * the provider's non-stream legacy default (``"required"`` for openai,
      ``"auto"`` for azure/azure_openai/docker) — when tools are present, unset,
      and not the openai-stream case above.

    Shared home (this resolver module) so BOTH the Wave-2 dual-run shadow and
    the future Wave-B live-path migration import the SAME semantics rather
    than re-deriving them (which would let the two copies drift).
    """
    if not tools:
        return None
    if explicit_choice is not None:
        return explicit_choice
    key = (provider or "").strip().lower()
    # openai is the ONLY provider whose legacy STREAM default ("auto",
    # OpenAIProvider.stream_chat) differs from its non-stream chat default
    # ("required"). azure/azure_openai/docker send "auto" on both paths, so the
    # ``stream`` flag changes only the openai result.
    if stream and key == "openai":
        return "auto"
    return _LEGACY_TOOL_CHOICE_DEFAULTS.get(key)


class UnsupportedDeploymentProvider(ValueError):
    """A KNOWN provider has no confirmed four-axis ``LlmDeployment`` mapping.

    Raised by :func:`resolve_deployment_for` for a provider the resolver
    recognises but deliberately declines to map because it has no confirmed
    four-axis wire. This is a DOCUMENTED extensibility hook — surfacing a
    future such provider as a typed error rather than a silent ``None`` is
    the ``rules/zero-tolerance.md`` Rule 3 (no silent fallbacks) disposition:
    an implementer wiring that provider hits a clear signal instead of a
    shadow that silently never runs. As of #1892 (four-axis ``azure_ai_foundry``
    wire) ``_UNSUPPORTED_PROVIDERS`` is empty — every KNOWN provider name has
    a confirmed four-axis mapping; the mechanism is retained for the next
    provider that needs it.
    """

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(
            f"provider {provider!r} has no confirmed four-axis LlmDeployment "
            "mapping (no confirmed wire); it cannot be resolved for the "
            "four-axis path. This is a DOCUMENTED blocker, not a silent "
            "fallback (rules/zero-tolerance.md Rule 3) — add a confirmed wire "
            "mapping in kaizen.llm.deployment_resolver to enable it."
        )


# Legacy provider names that map onto an Azure-OpenAI four-axis deployment.
_AZURE_PROVIDERS = frozenset({"azure", "azure_openai"})

# Legacy provider name that maps onto the Azure AI Foundry four-axis
# deployment (#1892) -- the unified, model-agnostic model-inference wire.
_AZURE_AI_FOUNDRY_PROVIDERS = frozenset({"azure_ai_foundry"})

# KNOWN providers the resolver deliberately declines to map (no confirmed
# four-axis wire) — resolving one raises UnsupportedDeploymentProvider rather
# than silently returning None (rules/zero-tolerance.md Rule 3). Empty as of
# #1892 -- azure_ai_foundry (the last such provider) now has a confirmed wire.
_UNSUPPORTED_PROVIDERS: frozenset[str] = frozenset()


def _resolve_azure_deployment(
    model: str,
    api_key: Optional[str],
    base_url: Optional[str],
    *,
    deployment: Optional[str] = None,
    api_version: Optional[str] = None,
):
    """Build an ``OpenAiChat``-wire Azure-OpenAI deployment (#1720 Wave-A #3).

    Azure OpenAI speaks the same on-wire JSON as OpenAI-direct; only the URL
    (``/openai/deployments/{deployment}/...?api-version=``) and the auth
    header (``api-key: <KEY>`` via ``AzureEntra`` api-key variant) differ —
    mirrors ``kaizen.llm.presets.azure_openai_preset``'s endpoint shape,
    sourcing the resource host from ``base_url``.

    #1859 deployment-name vs model-family split. Azure's deployment name is
    caller-chosen and is what Azure requires in the URL / wire ``model`` field;
    the model FAMILY (``gpt-5`` / ``o1`` / …) is what reasoning-model detection
    must key off. Two caller shapes:

    * ``deployment`` given (``BaseAgentConfig(model="gpt-5",
      provider_config={"deployment": "my-gpt5-deploy"})``): ``deployment`` is the
      URL / wire deployment name, ``model`` is the canonical family. The built
      deployment carries ``default_model=<deployment name>`` (URL + wire) AND
      ``canonical_model=<family>`` so the reasoning-param strip fires off the
      family regardless of the deployment name.
    * ``deployment`` absent (legacy shape, ``model`` IS the deployment name):
      ``default_model`` and ``canonical_model`` both resolve to ``model`` —
      byte-identical to pre-#1859. (No family is available in this shape, so the
      strip still keys off the deployment name; callers with a non-canonical
      deployment name must pass ``model``=family + ``provider_config.deployment``.)

    Credentials mirror the canonical Azure env resolution
    (``kaizen.llm.azure_env.resolve_azure_env``): the per-request
    override wins, else the canonical ``AZURE_*`` env vars (legacy
    ``AZURE_OPENAI_*`` names still resolve with a DeprecationWarning). A
    missing endpoint or api-key returns ``None`` (skip), matching the
    base-url family's missing-credential contract. ``api_version`` from
    ``provider_config`` wins over the ``AZURE_*`` env vars when supplied.
    """
    from kaizen.llm.auth.azure import AzureEntra
    from kaizen.llm.azure_env import resolve_azure_env
    from kaizen.llm.deployment import Endpoint, LlmDeployment, WireProtocol
    from kaizen.llm.grammar.azure_openai import AzureOpenAIGrammar
    from kaizen.llm.presets import AZURE_OPENAI_DEFAULT_API_VERSION

    resolved_endpoint = base_url or resolve_azure_env(
        "AZURE_ENDPOINT", "AZURE_OPENAI_ENDPOINT"
    )
    resolved_key = api_key or resolve_azure_env("AZURE_API_KEY", "AZURE_OPENAI_API_KEY")
    # rules/observability.md Rule 3: an entirely UNCONFIGURED provider is a
    # normal, expected skip (DEBUG). A PARTIALLY configured one -- the
    # operator set one half and believes Azure is wired -- is a
    # misconfiguration the operator must see (WARN).
    if not resolved_endpoint or not resolved_key:
        partially_configured = bool(resolved_endpoint) or bool(resolved_key)
        logger.log(
            logging.WARNING if partially_configured else logging.DEBUG,
            "llm.dual_run.shadow_skipped",
            extra={
                "provider": "azure",
                "reason": (
                    "missing_base_url" if not resolved_endpoint else "missing_api_key"
                ),
                "partially_configured": partially_configured,
            },
        )
        return None
    resolved_api_version = (
        api_version
        or resolve_azure_env("AZURE_API_VERSION", "AZURE_OPENAI_API_VERSION")
        or AZURE_OPENAI_DEFAULT_API_VERSION
    )

    # #1859: the DEPLOYMENT NAME (from provider_config, else `model` for the
    # legacy single-arg shape) is interpolated into the URL path; validate it
    # through the canonical Azure grammar (fail-closed on path-control chars)
    # BEFORE the f-string interpolation below — the same validator
    # azure_openai_preset uses. `model` remains the canonical FAMILY.
    deployment_name = deployment or model
    resolved_deployment = AzureOpenAIGrammar().resolve(deployment_name)

    endpoint = Endpoint(
        base_url=resolved_endpoint,
        path_prefix=f"/openai/deployments/{resolved_deployment}",
        # Azure REQUIRES ?api-version= on EVERY request URL; both
        # _build_completion_url and _build_embed_url append query_params.
        query_params={"api-version": resolved_api_version},
    )
    return LlmDeployment(
        wire=WireProtocol.OpenAiChat,
        endpoint=endpoint,
        auth=AzureEntra(api_key=resolved_key),
        default_model=resolved_deployment,
        # #1859: reasoning-model detection keys off the canonical family, not the
        # deployment name. When no separate deployment was supplied `model` IS the
        # deployment name, so family == deployment name (byte-neutral).
        canonical_model=model,
        preset_name="azure_openai",
    )


def _resolve_azure_ai_foundry_deployment(
    model: str,
    api_key: Optional[str],
    base_url: Optional[str],
    *,
    deployment: Optional[str] = None,
    api_version: Optional[str] = None,
):
    """Build an ``OpenAiChat``-wire Azure AI Foundry deployment (#1892).

    Azure AI Foundry's unified model-inference endpoint is MODEL-AGNOSTIC —
    one fixed URL (``/models/chat/completions``) serves every model deployed
    to the Foundry project; the model id travels in the wire body's
    ``model`` field (never the URL), so there is no deployment-name-vs-family
    split the way ``azure``/``azure_openai`` needs (#1859) — the resolved
    model name IS both the wire identity and the canonical family.

    Credential / model resolution precedence mirrors
    ``_resolve_azure_deployment``'s contract:

    * ``base_url`` (per-request override) else ``AZURE_AI_FOUNDRY_ENDPOINT``.
    * ``api_key`` (per-request override) else ``AZURE_AI_FOUNDRY_API_KEY``.
    * ``deployment`` (per-request override, from ``provider_config``) else
      ``AZURE_AI_FOUNDRY_DEPLOYMENT`` else the caller's ``model`` argument —
      the actual deployed model name/id (``rules/env-models.md``: never
      hardcode; read from the environment).
    * ``api_version`` (per-request override) else ``AZURE_AI_FOUNDRY_API_VERSION``
      else the preset's pinned default (``AZURE_AI_FOUNDRY_DEFAULT_API_VERSION``).

    A missing endpoint or api-key returns ``None`` (skip), matching the
    ``azure`` / ``azure_openai`` missing-credential contract — a genuinely
    absent credential is a quiet skip, NOT a raised error (only a KNOWN-but-
    undeliverable provider name raises ``UnsupportedDeploymentProvider``).
    """
    from kaizen.llm.presets import azure_ai_foundry_preset

    resolved_endpoint = (
        base_url or os.environ.get("AZURE_AI_FOUNDRY_ENDPOINT", "").strip()
    )
    resolved_key = api_key or os.environ.get("AZURE_AI_FOUNDRY_API_KEY", "").strip()
    # rules/observability.md Rule 3 -- see _resolve_azure_deployment.
    if not resolved_endpoint or not resolved_key:
        partially_configured = bool(resolved_endpoint) or bool(resolved_key)
        logger.log(
            logging.WARNING if partially_configured else logging.DEBUG,
            "llm.dual_run.shadow_skipped",
            extra={
                "provider": "azure_ai_foundry",
                "reason": (
                    "missing_base_url" if not resolved_endpoint else "missing_api_key"
                ),
                "partially_configured": partially_configured,
            },
        )
        return None
    resolved_model = (
        deployment or os.environ.get("AZURE_AI_FOUNDRY_DEPLOYMENT", "").strip() or model
    )
    resolved_api_version = (
        api_version
        or os.environ.get("AZURE_AI_FOUNDRY_API_VERSION", "").strip()
        or None
    )
    return azure_ai_foundry_preset(
        resolved_endpoint,
        resolved_key,
        resolved_model,
        api_version=resolved_api_version,
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


# ---------------------------------------------------------------------------
# KEYLESS LOCAL providers — availability is an ENDPOINT question, never a
# credential question (#1720 forest-drain).
# ---------------------------------------------------------------------------
#
# ``ollama`` and ``docker`` are LOCAL runtimes reached over plain HTTP on a
# loopback port with NO credential of any kind -- both presets pin
# ``StaticNone()`` auth. A keyless provider therefore
# MUST NOT be gated on credential presence, and MUST NOT be gated on the
# caller happening to pass a ``base_url``: a local runtime publishes a
# canonical loopback endpoint, so "the caller named no endpoint" means "use
# the provider's own default", NOT "the provider is unavailable".
#
# Each keyless provider declares, DECLARATIVELY (no per-name ``if`` branch in
# the resolve path -- a new local runtime is one row here):
#
#   * ``factory``      -- the parametrised preset builder;
#   * ``env_var``      -- the provider-scoped endpoint env var. Reading the
#                         endpoint from the environment is the ``base_url``
#                         analogue of the api-key family's
#                         ``<PROVIDER>_API_KEY`` fallback and keeps the
#                         environment the single source of truth
#                         (``rules/env-models.md``);
#   * ``default_url``  -- the provider's OWN canonical loopback endpoint,
#                         used when neither the per-request override nor the
#                         env var supplies one.
#
# ``default_url`` is a documented module-level named constant, overridable via
# a provider-SCOPED env var, and NOT chained to any provider-agnostic default
# -- the three conditions of the ``rules/env-models.md`` § "Provider-Intrinsic
# Named-Constant Defaults" carve-out, applied to the ENDPOINT axis rather than
# the model axis. Both values mirror the endpoints ``kaizen.config.providers``
# already publishes for these runtimes (``get_ollama_config`` /
# ``get_docker_config``), so the four-axis resolver and the legacy config
# surface agree on one endpoint per provider instead of drifting.
#
# Endpoint semantics: ``env_var`` / ``default_url`` carry the COMPLETE
# endpoint base the wire appends its path to (hence ``path_prefix=""``) --
# matching how ``kaizen.config.providers`` probes them
# (``f"{base_url}/api/tags"``, ``f"{base_url}/models"``). A per-request
# ``base_url`` override keeps its PRE-EXISTING meaning (the preset's own
# default ``path_prefix`` still applies), so no caller that passes an explicit
# ``base_url`` today changes behaviour.
#
# Both defaults use the ``localhost`` HOSTNAME rather than a literal loopback
# IP: ``url_safety.check_url`` allowlists the localhost LABEL for http, but
# rejects a literal ``127.0.0.1`` / ``::1`` at ``Endpoint`` construction
# (reason=``loopback``). Verified empirically -- a literal-IP default would
# raise ``InvalidEndpoint`` before any request was ever built.
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_DOCKER_MODEL_RUNNER_BASE_URL = "http://localhost:12434/engines/llama.cpp/v1"


def _local_provider_map() -> dict[str, tuple[Callable[..., Any], str, str]]:
    """Keyless local runtimes -> (factory, endpoint env var, canonical URL)."""
    from kaizen.llm.presets import docker_model_runner_preset, ollama_preset

    return {
        "ollama": (
            ollama_preset,
            "OLLAMA_BASE_URL",
            DEFAULT_OLLAMA_BASE_URL,
        ),
        "docker": (
            docker_model_runner_preset,
            "DOCKER_MODEL_RUNNER_URL",
            DEFAULT_DOCKER_MODEL_RUNNER_BASE_URL,
        ),
    }


def requires_credential(provider: str) -> bool:
    """Whether ``provider`` needs a credential to resolve at all.

    The DECLARATIVE property callers should branch on instead of testing the
    provider name against a hardcoded ``"ollama"`` literal. ``False`` for the
    keyless local runtimes above (they resolve on endpoint configuration
    alone); ``True`` for every credentialed family and for unknown names
    (fail-closed: an unrecognised provider is not assumed keyless).
    """
    return (provider or "").strip().lower() not in _local_provider_map()


def resolve_deployment_for(
    provider: str,
    model: str,
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    deployment: Optional[str] = None,
    api_version: Optional[str] = None,
):
    """Resolve a four-axis ``LlmDeployment`` for a legacy ``provider`` name.

    Maps the legacy provider name (``kaizen.providers.registry.PROVIDERS``)
    onto the matching four-axis preset builder. Returns ``None`` when the
    provider has no four-axis mapping, or a required CREDENTIAL cannot be
    resolved -- callers treat ``None`` as "skip, already logged". Raises
    :class:`UnsupportedDeploymentProvider` for a KNOWN provider with no
    confirmed wire — a documented Wave-B blocker, not a silent fallback.

    **Availability means CONFIGURED, not REACHABLE.** This function performs
    NO network I/O: it is called per-request on the ``llm_agent`` hot path,
    so probing an endpoint here would add a round-trip and a second failure
    mode to every completion. A provider resolves when its configuration is
    resolvable; whether the far end answers is decided by the wire layer at
    call time, where a refused connection is reported as a refused connection
    (``kaizen.config.providers.check_*_available`` remains the explicit
    opt-in reachability probe for callers that want one up front).

    Consequently the keyless local runtimes (``ollama`` / ``docker``, see
    :func:`requires_credential`) ALWAYS resolve — they are configured by
    construction via their canonical loopback default.

    ``api_key`` mirrors the legacy provider's own resolution: when the caller
    did not pass a per-request override, the same ``<PROVIDER>_API_KEY`` env
    var the legacy provider itself reads (``rules/env-models.md``) is tried
    before giving up.

    ``deployment`` / ``api_version`` are Azure-only (#1859): they come from the
    caller's ``provider_config`` (``{"deployment": ..., "api_version": ...}``).
    When ``deployment`` is given, ``model`` is the canonical model FAMILY and
    ``deployment`` is the Azure deployment NAME (URL / wire ``model`` field), so
    reasoning-model detection keys off the family regardless of the deployment
    name. Both are ignored by every non-Azure provider.
    """
    provider_key = (provider or "").strip().lower()

    # #1720 Wave-A security parity (enforcement-surface parity,
    # rules/security.md § Enforcement-Surface Parity): a per-request BYOK
    # ``api_key`` supplied HERE is installed directly into an HTTP header via
    # ``ApiKeyBearer.apply`` (through the preset / azure builders below) with NO
    # further sanitization — the SAME CRLF/control-char header-injection surface
    # that ``LlmClient.complete(api_key=)`` guards at its own entry
    # (``_validate_api_key_override``). This is the sibling BYOK entry point, so
    # it MUST route the caller-supplied override through the SAME shared
    # restrictiveness function; without it a ``\r\n``-bearing key reaches a
    # header on this path while the complete() path rejects it (a fail-open
    # parity gap the fix itself would otherwise leave). Env-derived keys
    # (``api_key is None`` here) are resolved downstream and are NOT
    # caller-per-request overrides — matching complete()'s override-only
    # validation. Lazy import: ``client`` does not import this module, so there
    # is no cycle; the import runs only when a per-request key is present.
    if api_key is not None:
        from kaizen.llm.client import _validate_api_key_override

        api_key = _validate_api_key_override(api_key)

    if provider_key in _UNSUPPORTED_PROVIDERS:
        raise UnsupportedDeploymentProvider(provider_key)

    if provider_key in _AZURE_PROVIDERS:
        return _resolve_azure_deployment(
            model,
            api_key,
            base_url,
            deployment=deployment,
            api_version=api_version,
        )

    if provider_key in _AZURE_AI_FOUNDRY_PROVIDERS:
        return _resolve_azure_ai_foundry_deployment(
            model,
            api_key,
            base_url,
            deployment=deployment,
            api_version=api_version,
        )

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

    local_map = _local_provider_map()
    if provider_key in local_map:
        factory, env_var, default_url = local_map[provider_key]
        # A keyless LOCAL runtime is never "unavailable for want of an
        # endpoint" -- it publishes a canonical loopback one. Precedence
        # mirrors the api-key family exactly: per-request override, else the
        # provider-scoped env var, else the provider's own default.
        if base_url:
            # Pre-existing per-request semantics: the preset's own default
            # `path_prefix` still applies (unchanged for every current caller).
            return factory(base_url, model)
        env_url = os.environ.get(env_var, "").strip() or None
        resolved_url = env_url or default_url
        logger.debug(
            "llm.deployment_resolver.local_endpoint_resolved",
            extra={
                "provider": provider,
                "source": "env" if env_url else "provider_default",
                "env_var": env_var,
            },
        )
        # `env_var` / `default_url` carry the COMPLETE endpoint base (see the
        # `_local_provider_map` note), so the preset appends no engine path.
        return factory(resolved_url, model, path_prefix="")

    logger.debug(
        "llm.dual_run.shadow_skipped",
        extra={"provider": provider, "reason": "unmapped_provider"},
    )
    return None


def describe_unresolved_precondition(provider: str) -> str:
    """Name WHICH precondition made ``provider`` unresolvable.

    ``resolve_deployment_for`` returning ``None`` tells a caller only THAT
    resolution failed. Surfacing that to a user as a bare "provider is not
    available" is the ``rules/zero-tolerance.md`` Rule 3 failure mode: the
    caller cannot act, because the message names no failed precondition.
    This renders the missing precondition for the caller's error message.

    It RENDERS the same declarative tables the resolve path branches on
    (``_api_key_preset_map`` / ``_local_provider_map``) rather than restating
    the precedence rules, so the message cannot drift from the behaviour.
    """
    provider_key = (provider or "").strip().lower()

    if provider_key in _local_provider_map():
        # Unreachable in practice: keyless local providers always resolve.
        _, env_var, default_url = _local_provider_map()[provider_key]
        return (
            f"{provider_key} is a keyless local runtime and resolves without "
            f"credentials (endpoint: ${env_var}, default {default_url})"
        )

    api_key_map = _api_key_preset_map()
    if provider_key in api_key_map:
        _, env_var = api_key_map[provider_key]
        return (
            f"no API key for {provider_key}: ${env_var} is unset or empty in "
            f"the environment and no per-request api_key override was supplied"
        )

    if provider_key in _AZURE_PROVIDERS:
        return (
            "Azure endpoint or API key unresolved: set $AZURE_ENDPOINT and "
            "$AZURE_API_KEY (or pass base_url / api_key per request)"
        )

    if provider_key in _AZURE_AI_FOUNDRY_PROVIDERS:
        return (
            "Azure AI Foundry endpoint or API key unresolved: set "
            "$AZURE_AI_FOUNDRY_ENDPOINT and $AZURE_AI_FOUNDRY_API_KEY "
            "(or pass base_url / api_key per request)"
        )

    known = sorted({*api_key_map, *_local_provider_map(), *_AZURE_PROVIDERS})
    return (
        f"{provider_key!r} has no four-axis deployment mapping; known "
        f"providers: {', '.join(known)}"
    )


__all__ = [
    "resolve_deployment_for",
    "requires_credential",
    "describe_unresolved_precondition",
    "UnsupportedDeploymentProvider",
    "legacy_tool_choice_default",
]
