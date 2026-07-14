# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""LlmClient.from_env() — URI > selector > legacy precedence chain.

Session 7 (S7) of #498. Implements the three-tier environment resolution
for `LlmClient.from_env()`:

1. **URI tier** (highest priority): `KAILASH_LLM_DEPLOYMENT` holds a
   deployment URI like `bedrock://us-east-1/claude-3-opus` or
   `vertex://my-project/us-central1/claude-3-opus` or
   `azure://my-resource/gpt-4o-prod?api-version=2024-06-01`. Parsed
   per-scheme with strict field regexes.

2. **Selector tier**: `KAILASH_LLM_PROVIDER` holds a preset name (e.g.
   `"bedrock_claude"`) resolved through the preset registry. Required
   env vars per preset; unknown selectors raise `NoKeysConfigured`.

3. **Legacy tier**: preserves today's `autoselect_provider()` ordering
   (OpenAI > Azure > Anthropic > Google) based on which API key env
   var is present.

If BOTH the deployment tier (URI or selector) AND legacy per-provider
keys are set, emits a `WARNING llm_client.migration.legacy_and_deployment_both_configured`
and the deployment path wins.

**Deprecation (#1721/#1720):** the legacy tier itself -- resolving with NO
`KAILASH_LLM_DEPLOYMENT` URI and NO `KAILASH_LLM_PROVIDER` selector present,
purely from a per-provider `*_API_KEY` -- is a backward-compat migration
layer preserving the old `autoselect_provider()` behavior. This is where the
cross-SDK key-list divergence lives (Python's 5 legacy keys incl. Azure vs.
the Rust SDK's 10, no Azure): the canonical URI/selector surface is already
cross-SDK-aligned, so the fix is to retire the legacy tier, not reconcile the
key lists. Resolving via the legacy tier ALONE now emits a `DeprecationWarning`
plus a `WARNING llm_client.migration.legacy_key_autodetect_deprecated` log
line naming the detected key and the canonical migration path
(`KAILASH_LLM_PROVIDER=<preset>` or a `KAILASH_LLM_DEPLOYMENT` URI). This is
the START of the deprecation cycle -- the legacy tier still resolves this
release; only removal is deferred (zero-tolerance.md Rule 6a).
"""

from __future__ import annotations

import logging
import os
import re
import warnings
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from kaizen.llm.deployment import LlmDeployment
from kaizen.llm.errors import (
    InvalidUri,
    LlmClientError,
    MissingCredential,
    NoKeysConfigured,
)

logger = logging.getLogger(__name__)


# Canonical env var names.
ENV_DEPLOYMENT_URI = "KAILASH_LLM_DEPLOYMENT"
ENV_SELECTOR = "KAILASH_LLM_PROVIDER"

# Legacy per-provider API key env vars, ordered by autoselect precedence.
# Order MUST match today's `autoselect_provider()`.
LEGACY_KEY_ORDER = [
    ("OPENAI_API_KEY", "openai"),
    ("AZURE_OPENAI_API_KEY", "azure_openai"),
    ("ANTHROPIC_API_KEY", "anthropic"),
    ("GOOGLE_API_KEY", "google"),
    # DeepSeek (OpenAI-compatible) — placed last so it never displaces an
    # existing provider's precedence; a bare DEEPSEEK_API_KEY (no URI/selector)
    # resolves to the deepseek preset. (#1609)
    ("DEEPSEEK_API_KEY", "deepseek"),
]

# Strict per-field regexes for URI parsing -- defense-in-depth before
# values are interpolated into URL paths / hosts inside presets.
# AWS region shape is `us-east-1`, `eu-central-1`, `ap-southeast-2`, etc.
# GCP region shape is `us-central1`, `europe-west4`, etc. (no trailing
# dash before the digit). The regex accepts both forms.
_AWS_REGION_RE = re.compile(r"^[a-z]{2,3}-[a-z]+(-[a-z]+)?-\d{1,2}$")
# GCP region shape is `us-central1`, `europe-west4`, etc. Vertex also
# accepts the multi-region / global endpoints `us`, `eu`, and `global`
# (NEW-B); these pass straight through (no `eu -> europe-west1` mapping).
_GCP_REGION_RE = re.compile(r"^(?:[a-z]{2,20}-[a-z]+\d{1,2}|us|eu|global)$")
_PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9\-]{4,28}[a-z0-9]$")
_AZURE_RESOURCE_RE = re.compile(r"^[a-z][a-z0-9-]{1,22}[a-z0-9]$")

SUPPORTED_SCHEMES = frozenset({"bedrock", "vertex", "azure", "openai-compat"})


def resolve_env_deployment() -> LlmDeployment:
    """Apply the three-tier precedence and return a built deployment.

    Raises `NoKeysConfigured` if every tier is empty.
    """
    uri = os.environ.get(ENV_DEPLOYMENT_URI, "").strip()
    selector = os.environ.get(ENV_SELECTOR, "").strip()
    legacy_key = _detect_legacy_key()

    # Migration-window isolation: warn if deployment-tier signals coexist
    # with legacy per-provider keys. Deployment path wins.
    if (uri or selector) and legacy_key is not None:
        logger.warning(
            "llm_client.migration.legacy_and_deployment_both_configured",
            extra={
                "legacy_env_var": legacy_key,
                "deployment_path": "uri" if uri else "selector",
            },
        )

    if uri:
        return _build_from_uri(uri)
    if selector:
        return _build_from_selector(selector)
    if legacy_key is not None:
        # Legacy tier resolving ALONE (no URI, no selector) -- this is the
        # deprecated backward-compat auto-detect path (#1721/#1720). Does
        # NOT change resolution behavior: the legacy tier still resolves
        # this release. See module docstring "Deprecation" section.
        message = _legacy_alone_deprecation_message(legacy_key)
        warnings.warn(message, DeprecationWarning, stacklevel=3)
        logger.warning(
            "llm_client.migration.legacy_key_autodetect_deprecated",
            extra={
                "legacy_env_var": legacy_key,
                "suggested_selector": _legacy_preset_name(legacy_key),
                "canonical_selector_var": ENV_SELECTOR,
                "canonical_uri_var": ENV_DEPLOYMENT_URI,
            },
        )
        return _build_from_legacy(legacy_key)

    _legacy_keys = ", ".join(env_var for env_var, _preset in LEGACY_KEY_ORDER)
    raise NoKeysConfigured(
        "No LLM deployment configured. Set one of: "
        f"{ENV_DEPLOYMENT_URI} (URI), {ENV_SELECTOR} (preset name), "
        f"or a legacy per-provider API key ({_legacy_keys})."
    )


def _detect_legacy_key() -> Optional[str]:
    """Return the env var name of the highest-priority legacy key set."""
    for env_var, _preset in LEGACY_KEY_ORDER:
        if os.environ.get(env_var, "").strip():
            return env_var
    return None


def _legacy_preset_name(legacy_key: str) -> Optional[str]:
    """Return the preset/selector name paired with a legacy env var."""
    for env_var, preset in LEGACY_KEY_ORDER:
        if env_var == legacy_key:
            return preset
    return None


def _legacy_alone_deprecation_message(legacy_key: str) -> str:
    """Build the deprecation message for legacy-tier-ALONE resolution.

    Fires only when `resolve_env_deployment()` resolves via the legacy tier
    with NO `KAILASH_LLM_DEPLOYMENT` URI and NO `KAILASH_LLM_PROVIDER`
    selector present (#1721/#1720). Names the detected legacy env var and
    points at the canonical migration path -- a preset selector when this
    key maps to one, else the general selector/URI guidance.
    """
    preset = _legacy_preset_name(legacy_key)
    migration_path = (
        f"set {ENV_SELECTOR}={preset!r}"
        if preset is not None
        else f"set {ENV_SELECTOR} to a registered preset name"
    )
    return (
        f"LlmClient.from_env(): resolved via the legacy per-provider-key "
        f"auto-detect tier ({legacy_key} is set; no {ENV_DEPLOYMENT_URI} or "
        f"{ENV_SELECTOR} configured). This legacy auto-detect path is "
        f"deprecated and will be removed in a future release -- "
        f"{migration_path} (or a {ENV_DEPLOYMENT_URI} URI) instead."
    )


def _build_from_uri(uri: str) -> LlmDeployment:
    """Parse a deployment URI and build the corresponding LlmDeployment."""
    parsed = urlparse(uri)
    scheme = parsed.scheme
    if scheme not in SUPPORTED_SCHEMES:
        raise InvalidUri(
            f"Unsupported scheme '{scheme}' in {ENV_DEPLOYMENT_URI}; "
            f"supported schemes: {sorted(SUPPORTED_SCHEMES)}"
        )

    if scheme == "bedrock":
        return _build_bedrock_from_uri(parsed)
    if scheme == "vertex":
        return _build_vertex_from_uri(parsed)
    if scheme == "azure":
        return _build_azure_from_uri(parsed)
    if scheme == "openai-compat":
        return _build_openai_compat_from_uri(parsed)
    # Closed enum
    raise InvalidUri(f"Unhandled scheme: {scheme}")


def _build_bedrock_from_uri(parsed: Any) -> LlmDeployment:
    """bedrock://{region}/{model}  — bearer-token deployment."""
    region = parsed.netloc
    model = parsed.path.lstrip("/")
    if not region or not _AWS_REGION_RE.match(region):
        raise InvalidUri(
            f"bedrock:// URI region failed regex validation "
            f"(region_length={len(region)})"
        )
    if not model:
        raise InvalidUri("bedrock:// URI missing model path component")
    token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
    if not token:
        raise MissingCredential(
            "AWS_BEARER_TOKEN_BEDROCK not set; required for bedrock:// URIs"
        )
    from kaizen.llm.presets import bedrock_claude_preset

    return bedrock_claude_preset(token, region=region, model=model)


def _build_vertex_from_uri(parsed: Any) -> LlmDeployment:
    """vertex://{project}/{region}/{model} — GCP Vertex deployment."""
    project = parsed.netloc
    # path = "/region/model" (or "/region/model-with-dashes")
    path_parts = parsed.path.lstrip("/").split("/", 1)
    if len(path_parts) != 2:
        raise InvalidUri(
            "vertex:// URI requires /region/model after project "
            "(e.g. vertex://my-project/us-central1/gemini-1.5-pro)"
        )
    region, model = path_parts
    if not project or not _PROJECT_ID_RE.match(project):
        raise InvalidUri("vertex:// URI project failed regex validation")
    if not region or not _GCP_REGION_RE.match(region):
        raise InvalidUri("vertex:// URI region failed regex validation")
    # `GOOGLE_APPLICATION_CREDENTIALS` is OPTIONAL for vertex:// URIs. When
    # set it points at either a service-account OR an external_account
    # (Workload Identity Federation) JSON file; GcpOauth dispatches on the
    # file's `type` at credential-build time. When UNSET, `None` flows to
    # GcpOauth's keyless Application Default Credentials chain (ADC / GCE
    # metadata server) rather than hard-failing -- so a Vertex deployment
    # on GCE / Cloud Run / GKE with an attached service account needs no
    # key file on disk.
    sa_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    sa_key = sa_path if sa_path else None
    # Dispatch by model family prefix. Anthropic goes through vertex_claude;
    # everything else goes through vertex_gemini.
    from kaizen.llm.presets import vertex_claude_preset, vertex_gemini_preset

    if model.startswith("claude-"):
        return vertex_claude_preset(sa_key, project=project, region=region, model=model)
    return vertex_gemini_preset(sa_key, project=project, region=region, model=model)


def _build_azure_from_uri(parsed: Any) -> LlmDeployment:
    """azure://{resource}/{deployment}?api-version=X"""
    resource = parsed.netloc
    deployment_name = parsed.path.lstrip("/")
    if not resource or not _AZURE_RESOURCE_RE.match(resource):
        raise InvalidUri("azure:// URI resource failed regex validation")
    if not deployment_name:
        raise InvalidUri("azure:// URI missing deployment name path component")
    api_version = None
    if parsed.query:
        qs = parse_qs(parsed.query)
        api_version = qs.get("api-version", [None])[0]
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    if not api_key:
        raise MissingCredential(
            "AZURE_OPENAI_API_KEY not set; required for azure:// URIs"
        )
    from kaizen.llm.auth.azure import AzureEntra
    from kaizen.llm.presets import azure_openai_preset

    auth = AzureEntra(api_key=api_key)
    return azure_openai_preset(resource, deployment_name, auth, api_version=api_version)


def _build_openai_compat_from_uri(parsed: Any) -> LlmDeployment:
    """openai-compat://{host}/{model} — OpenAI-compatible endpoint."""
    host = parsed.netloc
    model = parsed.path.lstrip("/")
    if not host or not model:
        raise InvalidUri("openai-compat:// URI requires host + model path")
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get(
        "OPENAI_COMPAT_API_KEY"
    )
    if not api_key:
        raise MissingCredential(
            "OPENAI_API_KEY or OPENAI_COMPAT_API_KEY not set; "
            "required for openai-compat:// URIs"
        )
    from kaizen.llm.presets import openai_preset

    return openai_preset(api_key, model=model, base_url=f"https://{host}")


def _build_from_selector(selector: str) -> LlmDeployment:
    """Build a deployment from a preset name + provider-specific env vars."""
    from kaizen.llm.presets import get_preset

    try:
        factory = get_preset(selector)
    except ValueError as exc:
        raise NoKeysConfigured(
            f"KAILASH_LLM_PROVIDER='{_fingerprint_selector(selector)}' "
            f"is not a registered preset name"
        ) from exc

    # Provider-specific env-var resolution. This is a simplified mapping;
    # most presets take (api_key, model=env['{PROVIDER}_MODEL']).
    return _call_preset_from_env(selector, factory)


def _call_preset_from_env(selector: str, factory: Any) -> LlmDeployment:
    """Resolve env vars for the selected preset and call the factory."""
    if selector == "openai":
        api_key = _require_env("OPENAI_API_KEY")
        model = _require_env("OPENAI_PROD_MODEL", "OPENAI_MODEL")
        return factory(api_key, model=model)
    if selector == "anthropic":
        api_key = _require_env("ANTHROPIC_API_KEY")
        model = _require_env("ANTHROPIC_MODEL")
        return factory(api_key, model=model)
    if selector == "google":
        api_key = _require_env("GOOGLE_API_KEY", "GEMINI_API_KEY")
        model = _require_env("GOOGLE_MODEL", "GEMINI_MODEL")
        return factory(api_key, model=model)
    if selector == "deepseek":
        # DeepSeek (OpenAI-compatible). The preset carries the DeepSeek
        # base_url intrinsically, so no base_url override is needed here
        # (#1609). Model env precedence matches `_FROM_ENV_PROVIDERS`.
        api_key = _require_env("DEEPSEEK_API_KEY")
        model = _require_env("DEEPSEEK_PROD_MODEL", "DEEPSEEK_MODEL")
        return factory(api_key, model=model)
    if selector == "bedrock_claude":
        token = _require_env("AWS_BEARER_TOKEN_BEDROCK")
        region = _require_env("AWS_REGION")
        model = _require_env("BEDROCK_CLAUDE_MODEL_ID", "BEDROCK_MODEL")
        return factory(token, region=region, model=model)
    if selector == "azure_openai":
        api_key = _require_env("AZURE_OPENAI_API_KEY")
        resource = _require_env("AZURE_OPENAI_RESOURCE")
        deployment = _require_env("AZURE_OPENAI_DEPLOYMENT")
        from kaizen.llm.auth.azure import AzureEntra

        auth = AzureEntra(api_key=api_key)
        return factory(resource, deployment, auth)
    if selector in ("vertex_claude", "vertex_gemini"):
        # Vertex-on-GCP without a full URI. project + region + model are
        # REQUIRED; the service-account key is OPTIONAL -- an unset
        # `GOOGLE_APPLICATION_CREDENTIALS` flows `None` to the preset's
        # GcpOauth, which resolves keyless Application Default Credentials
        # (ADC / GCE metadata server). A set value points at either a
        # service-account OR an external_account (WIF) file; GcpOauth
        # dispatches on the file's `type` at credential-build time.
        project = _require_env("GOOGLE_CLOUD_PROJECT")
        region = _require_env("VERTEX_LOCATION")
        if selector == "vertex_claude":
            model = _require_env("VERTEX_CLAUDE_MODEL_ID", "VERTEX_CLAUDE_MODEL")
        else:
            model = _require_env("VERTEX_GEMINI_MODEL_ID", "VERTEX_GEMINI_MODEL")
        creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        sa_key = creds if creds else None
        return factory(sa_key, project=project, region=region, model=model)
    # Fallback: unknown selector shape. Caller MUST set URI tier instead.
    raise NoKeysConfigured(
        f"Selector '{_fingerprint_selector(selector)}' is registered but "
        f"the from_env() shape for it is not supported in v0; "
        f"use {ENV_DEPLOYMENT_URI} URI form instead."
    )


def _build_from_legacy(legacy_key: str) -> LlmDeployment:
    """Legacy tier: build from the detected legacy per-provider key (one of LEGACY_KEY_ORDER)."""
    from kaizen.llm.presets import (
        anthropic_preset,
        azure_openai_preset,
        deepseek_preset,
        google_preset,
        openai_preset,
    )

    if legacy_key == "OPENAI_API_KEY":
        api_key = os.environ["OPENAI_API_KEY"]
        model = _require_env("OPENAI_PROD_MODEL", "OPENAI_MODEL")
        return openai_preset(api_key, model=model)
    if legacy_key == "AZURE_OPENAI_API_KEY":
        api_key = os.environ["AZURE_OPENAI_API_KEY"]
        resource = _require_env("AZURE_OPENAI_RESOURCE")
        deployment = _require_env("AZURE_OPENAI_DEPLOYMENT")
        from kaizen.llm.auth.azure import AzureEntra

        auth = AzureEntra(api_key=api_key)
        return azure_openai_preset(resource, deployment, auth)
    if legacy_key == "ANTHROPIC_API_KEY":
        api_key = os.environ["ANTHROPIC_API_KEY"]
        model = _require_env("ANTHROPIC_MODEL")
        return anthropic_preset(api_key, model=model)
    if legacy_key == "GOOGLE_API_KEY":
        api_key = os.environ["GOOGLE_API_KEY"]
        model = _require_env("GOOGLE_MODEL", "GEMINI_MODEL")
        return google_preset(api_key, model=model)
    if legacy_key == "DEEPSEEK_API_KEY":
        # DeepSeek (OpenAI-compatible) — the preset carries the DeepSeek
        # base_url; from_env selects it when only DEEPSEEK_API_KEY is set
        # (no URI / selector tier). (#1609)
        api_key = os.environ["DEEPSEEK_API_KEY"]
        model = _require_env("DEEPSEEK_PROD_MODEL", "DEEPSEEK_MODEL")
        return deepseek_preset(api_key, model=model)
    raise LlmClientError(f"Unhandled legacy key: {legacy_key}")


def _require_env(*candidates: str) -> str:
    """Read the first non-empty env var from candidates; raise if none."""
    for var in candidates:
        val = os.environ.get(var, "").strip()
        if val:
            return val
    raise MissingCredential(f"None of these env vars are set: {list(candidates)}")


def _fingerprint_selector(selector: str) -> str:
    """8-char fingerprint for log-injection-safe selector names.

    #617: migrated from SHA-256 → fingerprint_secret (BLAKE2b) to close
    CodeQL py/weak-sensitive-data-hashing consistently across kaizen/llm.
    """
    from kailash.utils.url_credentials import fingerprint_secret

    return fingerprint_secret(selector)


__all__ = [
    "ENV_DEPLOYMENT_URI",
    "ENV_SELECTOR",
    "LEGACY_KEY_ORDER",
    "SUPPORTED_SCHEMES",
    "resolve_env_deployment",
]
