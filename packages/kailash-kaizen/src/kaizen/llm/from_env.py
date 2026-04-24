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
"""

from __future__ import annotations

import logging
import os
import re
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
]

# Strict per-field regexes for URI parsing -- defense-in-depth before
# values are interpolated into URL paths / hosts inside presets.
# AWS region shape is `us-east-1`, `eu-central-1`, `ap-southeast-2`, etc.
# GCP region shape is `us-central1`, `europe-west4`, etc. (no trailing
# dash before the digit). The regex accepts both forms.
_AWS_REGION_RE = re.compile(r"^[a-z]{2,3}-[a-z]+(-[a-z]+)?-\d{1,2}$")
_GCP_REGION_RE = re.compile(r"^[a-z]{2,20}-[a-z]+\d{1,2}$")
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
        return _build_from_legacy(legacy_key)

    raise NoKeysConfigured(
        "No LLM deployment configured. Set one of: "
        f"{ENV_DEPLOYMENT_URI} (URI), {ENV_SELECTOR} (preset name), "
        "or a legacy per-provider API key (OPENAI_API_KEY, "
        "ANTHROPIC_API_KEY, GOOGLE_API_KEY, AZURE_OPENAI_API_KEY)."
    )


def _detect_legacy_key() -> Optional[str]:
    """Return the env var name of the highest-priority legacy key set."""
    for env_var, _preset in LEGACY_KEY_ORDER:
        if os.environ.get(env_var, "").strip():
            return env_var
    return None


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
    sa_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not sa_path:
        raise MissingCredential(
            "GOOGLE_APPLICATION_CREDENTIALS not set; required for vertex:// URIs"
        )
    # Dispatch by model family prefix. Anthropic goes through vertex_claude;
    # everything else goes through vertex_gemini.
    from kaizen.llm.presets import vertex_claude_preset, vertex_gemini_preset

    if model.startswith("claude-"):
        return vertex_claude_preset(
            sa_path, project=project, region=region, model=model
        )
    return vertex_gemini_preset(sa_path, project=project, region=region, model=model)


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
    # Fallback: unknown selector shape. Caller MUST set URI tier instead.
    raise NoKeysConfigured(
        f"Selector '{_fingerprint_selector(selector)}' is registered but "
        f"the from_env() shape for it is not supported in v0; "
        f"use {ENV_DEPLOYMENT_URI} URI form instead."
    )


def _build_from_legacy(legacy_key: str) -> LlmDeployment:
    """Legacy tier: detect one of the 4 canonical keys and build."""
    from kaizen.llm.presets import (
        anthropic_preset,
        azure_openai_preset,
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
