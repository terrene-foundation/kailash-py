# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Preset registry + provider-specific deployment factories.

Every preset factory:

* Returns a fully-constructed `LlmDeployment` with the correct wire protocol,
  endpoint URL + path prefix, and auth strategy for its provider.
* Is registered in `_PRESETS` under a short snake_case name matching the
  allowlist regex `^[a-z][a-z0-9_]{0,31}$`.
* Is exposed as a classmethod on `LlmDeployment` via `_attach_preset_methods()`
  so both call styles work:
      LlmDeployment.openai(api_key, model=os.environ["OPENAI_PROD_MODEL"])
      from kaizen.llm.presets import openai_preset      # module-level form

Session 1 ships only the `openai` preset. Every subsequent session adds its
presets (anthropic, google, bedrock_*, azure_*, vertex_*) to this file.

Security invariants enforced here:

* `register_preset(name, factory)` validates `name` against the regex and
  rejects CRLF / spaces / unicode / null-byte / leading-digit / >32-char
  inputs. The error message MUST NOT echo the raw bad name — that's a
  log-injection vector. The caller sees a fingerprint instead.
* Every call site of `register_preset` in this file uses a literal snake_case
  name; the validation is defence-in-depth for any future code path that
  might register from a config file or environment variable.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable, Dict, Optional

from kailash.utils.url_credentials import fingerprint_secret

from kaizen.llm.auth.aws import AwsBearerToken
from kaizen.llm.auth.bearer import ApiKey, ApiKeyBearer, ApiKeyHeaderKind, StaticNone
from kaizen.llm.auth.gcp import GcpOauth
from kaizen.llm.deployment import (
    CompletionRouting,
    Endpoint,
    LlmDeployment,
    WireProtocol,
)
from kaizen.llm.errors import MissingCredential, ModelRequired
from kaizen.llm.grammar.bedrock import (
    BedrockClaudeGrammar,
    BedrockCohereGrammar,
    BedrockLlamaGrammar,
    BedrockMistralGrammar,
    BedrockTitanGrammar,
)
from kaizen.llm.grammar.vertex import VertexClaudeGrammar, VertexGeminiGrammar

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Name validation
# ---------------------------------------------------------------------------

# Allowlist regex: lowercase ASCII letter first, then up to 31 of [a-z0-9_].
# Deliberate: rejects CRLF, spaces, unicode confusables (Cyrillic 'а' etc),
# null bytes, leading digits, and anything > 32 chars.
_PRESET_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def _fingerprint(raw: str) -> str:
    """8-char non-reversible tag — matches the cross-SDK contract (see
    ``rules/event-payload-classification.md`` §2 and DataFlow's
    ``format_record_id_for_event``).

    #617: migrated from SHA-256 → fingerprint_secret (BLAKE2b) to close
    CodeQL py/weak-sensitive-data-hashing consistently across kaizen/llm.
    """
    return fingerprint_secret(raw)


def _validate_preset_name(name: Any) -> str:
    """Assert `name` matches the regex; raise ValueError if not.

    The error message MUST NOT contain `name` verbatim (log-injection
    defence — CRLF in a preset name would otherwise split log lines).
    Instead it carries a 4-char SHA-256 fingerprint so the audit trail can
    correlate without reproducing the payload.

    Emits a WARN log on the reject path carrying only the fingerprint —
    the raw name is deliberately NOT logged (that's the point). Round-1
    redteam MED-2.
    """
    if not isinstance(name, str):
        logger.warning(
            "preset.validation_rejected",
            extra={"reason": "non_string", "type": type(name).__name__},
        )
        raise ValueError(
            "preset name must be a string; rejected non-string input "
            f"(type_fingerprint={type(name).__name__})"
        )
    if not _PRESET_NAME_RE.match(name):
        logger.warning(
            "preset.validation_rejected",
            extra={"reason": "regex", "name_fingerprint": _fingerprint(name)},
        )
        raise ValueError(
            "preset name failed validation against "
            f"^[a-z][a-z0-9_]{{0,31}}$ (name_fingerprint={_fingerprint(name)})"
        )
    return name


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


_PRESETS: Dict[str, Callable[..., LlmDeployment]] = {}


def register_preset(name: str, factory: Callable[..., LlmDeployment]) -> None:
    """Register a preset factory under `name`.

    Validates `name` against `_PRESET_NAME_RE`. Rejects duplicate
    registrations with a typed error to prevent silent shadowing — if a
    refactor tries to re-register `openai`, the second call raises.

    Emits an INFO log on successful registration. The preset name is a
    public symbol (not a secret) so logging it verbatim is safe — this is
    a config-state transition per observability.md §4. Round-1 redteam
    MED-2.
    """
    validated = _validate_preset_name(name)
    if not callable(factory):
        raise TypeError("factory must be callable")
    if validated in _PRESETS:
        raise ValueError(
            f"preset already registered (name_fingerprint={_fingerprint(validated)})"
        )
    _PRESETS[validated] = factory
    logger.info("preset.registered", extra={"preset_name": validated})


# Provider-string aliases (NEW-C). Callers reaching the registry with a
# hyphenated / provider-style name resolve to the canonical snake_case
# preset. Consulted BEFORE `_validate_preset_name` because aliases may carry
# hyphens (which `_PRESET_NAME_RE` deliberately rejects), keeping the
# canonical registry keys clean while accepting the common external spellings.
#   * `vertex-anthropic` / `vertex_claude`  → `vertex_claude`
#   * `vertex-gemini` / `vertex-google`     → `vertex_gemini`
_PRESET_ALIASES: Dict[str, str] = {
    "vertex-anthropic": "vertex_claude",
    "vertex-claude": "vertex_claude",
    "vertex-gemini": "vertex_gemini",
    "vertex-google": "vertex_gemini",
}


def _normalize_preset_name(name: Any) -> Any:
    """Map a provider-string alias to its canonical preset name.

    Non-string / unknown inputs pass through unchanged so the downstream
    validator produces the canonical typed error.
    """
    if isinstance(name, str) and name in _PRESET_ALIASES:
        return _PRESET_ALIASES[name]
    return name


def get_preset(name: str) -> Callable[..., LlmDeployment]:
    """Retrieve a preset factory by name. Normalizes aliases, then validates."""
    normalized = _normalize_preset_name(name)
    validated = _validate_preset_name(normalized)
    try:
        return _PRESETS[validated]
    except KeyError:
        raise ValueError(
            f"preset not registered (name_fingerprint={_fingerprint(validated)})"
        )


def list_presets() -> list[str]:
    """Return the registered preset names in registration order."""
    return list(_PRESETS.keys())


# ---------------------------------------------------------------------------
# OpenAI preset (Session 2)
# ---------------------------------------------------------------------------


def openai_preset(
    api_key: str,
    model: str,
    *,
    base_url: str = "https://api.openai.com",
    path_prefix: str = "/v1",
) -> LlmDeployment:
    """Build a deployment for the public OpenAI API.

    Wire:        `OpenAiChat`
    Endpoint:    `https://api.openai.com/v1`
    Auth:        `ApiKeyBearer(Authorization_Bearer, ApiKey(api_key))`

    `api_key` and `model` are REQUIRED. Per `rules/env-models.md`, model
    names MUST come from `.env` / environment variables — no default is
    provided by the preset. Callers:

        model = os.environ["OPENAI_PROD_MODEL"]  # or DEFAULT_LLM_MODEL
        LlmDeployment.openai(api_key, model=model)

    `api_key` MUST be a non-empty string; we do not accept `None` on the
    grounds that "let the provider 401" produces opaque errors.
    """
    if not isinstance(api_key, str) or not api_key:
        raise ValueError("openai_preset requires a non-empty api_key string")
    if not isinstance(model, str) or not model:
        raise ValueError(
            "openai_preset requires a non-empty model string — read it from "
            "os.environ['OPENAI_PROD_MODEL'] per rules/env-models.md"
        )

    endpoint = Endpoint(
        base_url=base_url,
        path_prefix=path_prefix,
    )
    auth = ApiKeyBearer(
        kind=ApiKeyHeaderKind.Authorization_Bearer,
        key=ApiKey(api_key),
    )
    return LlmDeployment(
        wire=WireProtocol.OpenAiChat,
        endpoint=endpoint,
        auth=auth,
        default_model=model,
        preset_name="openai",
    )


register_preset("openai", openai_preset)


# ---------------------------------------------------------------------------
# Attach presets as classmethods on LlmDeployment
# ---------------------------------------------------------------------------


def _attach_openai_classmethod() -> None:
    """Wire `openai_preset` onto `LlmDeployment.openai`."""

    @classmethod  # type: ignore[misc]
    def openai(cls, api_key: str, model: str, **kwargs: Any) -> LlmDeployment:
        return openai_preset(api_key, model=model, **kwargs)

    LlmDeployment.openai = openai  # type: ignore[attr-defined]


_attach_openai_classmethod()


# ---------------------------------------------------------------------------
# Session 2 (S3) — Direct-provider presets (15 total)
# ---------------------------------------------------------------------------
#
# Contract for every preset in this section:
#
#   1. `api_key` (or equivalent credential) and `model` are REQUIRED
#      positional/keyword arguments with NO defaults.
#   2. `model` MUST come from `os.environ[<PROVIDER>_PROD_MODEL]` or
#      equivalent per `rules/env-models.md`. Hardcoded defaults are
#      BLOCKED.
#   3. Factory returns a fully-constructed `LlmDeployment` with the
#      correct wire protocol, endpoint, and auth strategy.
#   4. Preset name (snake_case) byte-matches the Rust SDK literal so the
#      S9 cross-SDK parity fixture passes without translation.
#   5. Every preset is registered with `register_preset(name, factory)`
#      AND attached as `LlmDeployment.<name>` via `_attach_classmethod()`.
#
# The OpenAI-compatible providers (groq, together, fireworks, openrouter,
# deepseek, docker_model_runner, lm_studio, llama_cpp, mistral) share the
# `WireProtocol.OpenAiChat` wire — their chat completion schema is
# byte-identical to OpenAI's. They differ only in endpoint URL and (for
# some) header shape.


def _validate_required_str(
    value: Any, *, name: str, env_hint: str | None = None
) -> str:
    """Shared validator for required non-empty string arguments.

    Raises `ValueError` with an actionable message pointing at the env
    variable the caller should read from. `env_hint` is the canonical env
    var per `rules/env-models.md`.
    """
    if not isinstance(value, str) or not value:
        hint = f" — read from os.environ['{env_hint}']" if env_hint else ""
        raise ValueError(f"{name} must be a non-empty string{hint}")
    return value


def anthropic_preset(
    api_key: str,
    model: str,
    *,
    base_url: str = "https://api.anthropic.com",
    path_prefix: str = "/v1",
    anthropic_version: str = "2023-06-01",
) -> LlmDeployment:
    """Anthropic Messages API (`POST /v1/messages`).

    Wire:     `AnthropicMessages`
    Endpoint: `https://api.anthropic.com/v1`
    Auth:     `X-Api-Key: <key>` via `ApiKeyBearer(X_Api_Key)`
    Headers:  `anthropic-version` goes on the Endpoint.required_headers.

    `api_key` is REQUIRED; `model` is REQUIRED and MUST come from
    `os.environ["ANTHROPIC_PROD_MODEL"]` per `rules/env-models.md`.
    """
    _validate_required_str(api_key, name="anthropic_preset.api_key")
    _validate_required_str(
        model, name="anthropic_preset.model", env_hint="ANTHROPIC_PROD_MODEL"
    )

    endpoint = Endpoint(
        base_url=base_url,
        path_prefix=path_prefix,
        required_headers={"anthropic-version": anthropic_version},
    )
    auth = ApiKeyBearer(kind=ApiKeyHeaderKind.X_Api_Key, key=ApiKey(api_key))
    return LlmDeployment(
        wire=WireProtocol.AnthropicMessages,
        endpoint=endpoint,
        auth=auth,
        default_model=model,
        preset_name="anthropic",
    )


def google_preset(
    api_key: str,
    model: str,
    *,
    base_url: str = "https://generativelanguage.googleapis.com",
    path_prefix: str = "/v1beta",
) -> LlmDeployment:
    """Google Gemini GenerateContent API.

    Wire:     `GoogleGenerateContent`
    Endpoint: `https://generativelanguage.googleapis.com/v1beta`
    Auth:     `X-Goog-Api-Key: <key>`

    Model names are `gemini-*` per `rules/env-models.md`; read from
    `os.environ["GOOGLE_PROD_MODEL"]` or `GEMINI_PROD_MODEL`.
    """
    _validate_required_str(api_key, name="google_preset.api_key")
    _validate_required_str(
        model, name="google_preset.model", env_hint="GOOGLE_PROD_MODEL"
    )

    endpoint = Endpoint(base_url=base_url, path_prefix=path_prefix)
    auth = ApiKeyBearer(kind=ApiKeyHeaderKind.X_Goog_Api_Key, key=ApiKey(api_key))
    return LlmDeployment(
        wire=WireProtocol.GoogleGenerateContent,
        endpoint=endpoint,
        auth=auth,
        default_model=model,
        preset_name="google",
    )


def cohere_preset(
    api_key: str,
    model: str,
    *,
    base_url: str = "https://api.cohere.ai",
    path_prefix: str = "/v2",
) -> LlmDeployment:
    """Cohere v2 Chat API.

    Wire:     `CohereGenerate`
    Endpoint: `https://api.cohere.ai/v2` (cross-SDK parity with kailash-rs
              ``LlmDeployment::cohere()`` at
              ``crates/kailash-kaizen/src/llm/deployment/presets.rs:386-396``).
    Auth:     `Authorization: Bearer <key>`

    Default endpoint advanced from the legacy ``https://api.cohere.com/v1``
    Generate API to the modern ``https://api.cohere.ai/v2`` Chat API in
    kaizen 2.18.0 (#794) for byte-equivalent cross-SDK parity per
    ``rules/cross-sdk-inspection.md`` § 3 (EATP D6: matching semantics).
    The on-wire request envelope at ``/v2`` is OpenAI-Chat-compatible;
    Rust delegates v2 through ``OpenAiAdapter`` (see ``presets.rs:378-380``)
    and Python preserves the same ``WireProtocol.CohereGenerate`` tag for
    adapter routing continuity.

    Migration: callers who require the legacy v1 Generate API (different
    on-wire request shape) MUST opt in explicitly via
    ``cohere_preset(api_key, model, base_url="https://api.cohere.com",
    path_prefix="/v1")``. Both Cohere endpoints currently coexist (v1 has
    no announced sunset date), but Cohere's published API reference now
    directs new integrations at v2.
    """
    _validate_required_str(api_key, name="cohere_preset.api_key")
    _validate_required_str(
        model, name="cohere_preset.model", env_hint="COHERE_PROD_MODEL"
    )

    endpoint = Endpoint(base_url=base_url, path_prefix=path_prefix)
    auth = ApiKeyBearer(kind=ApiKeyHeaderKind.Authorization_Bearer, key=ApiKey(api_key))
    return LlmDeployment(
        wire=WireProtocol.CohereGenerate,
        endpoint=endpoint,
        auth=auth,
        default_model=model,
        preset_name="cohere",
    )


def mistral_preset(
    api_key: str,
    model: str,
    *,
    base_url: str = "https://api.mistral.ai",
    path_prefix: str = "/v1",
) -> LlmDeployment:
    """Mistral Chat Completions API (OpenAI-compatible schema, distinct wire tag).

    Wire:     `MistralChat`
    Endpoint: `https://api.mistral.ai/v1`
    Auth:     `Authorization: Bearer <key>`

    The on-the-wire schema is OpenAI-compatible but kept under a distinct
    `MistralChat` tag so provider-specific quirks (tool call shape, system
    message handling) can diverge without changing the canonical OpenAI
    wire.
    """
    _validate_required_str(api_key, name="mistral_preset.api_key")
    _validate_required_str(
        model, name="mistral_preset.model", env_hint="MISTRAL_PROD_MODEL"
    )

    endpoint = Endpoint(base_url=base_url, path_prefix=path_prefix)
    auth = ApiKeyBearer(kind=ApiKeyHeaderKind.Authorization_Bearer, key=ApiKey(api_key))
    return LlmDeployment(
        wire=WireProtocol.MistralChat,
        endpoint=endpoint,
        auth=auth,
        default_model=model,
        preset_name="mistral",
    )


def perplexity_preset(
    api_key: str,
    model: str,
    *,
    base_url: str = "https://api.perplexity.ai",
    path_prefix: str = "",
) -> LlmDeployment:
    """Perplexity Sonar API (OpenAI-compatible chat completion schema).

    Wire:     `OpenAiChat` (Perplexity implements OpenAI's schema)
    Endpoint: `https://api.perplexity.ai`
    Auth:     `Authorization: Bearer <key>`

    Perplexity's `/chat/completions` endpoint is byte-compatible with
    OpenAI's schema, so it shares the OpenAI wire.
    """
    _validate_required_str(api_key, name="perplexity_preset.api_key")
    _validate_required_str(
        model, name="perplexity_preset.model", env_hint="PERPLEXITY_PROD_MODEL"
    )

    endpoint = Endpoint(base_url=base_url, path_prefix=path_prefix)
    auth = ApiKeyBearer(kind=ApiKeyHeaderKind.Authorization_Bearer, key=ApiKey(api_key))
    return LlmDeployment(
        wire=WireProtocol.OpenAiChat,
        endpoint=endpoint,
        auth=auth,
        default_model=model,
        preset_name="perplexity",
    )


def huggingface_preset(
    api_key: str,
    model: str,
    *,
    base_url: str = "https://router.huggingface.co",
    path_prefix: str = "/hf-inference",
) -> LlmDeployment:
    """HuggingFace Inference API (Inference Providers router).

    Wire:     `HuggingFaceInference`
    Endpoint: `https://router.huggingface.co/hf-inference` (the legacy
              `api-inference.huggingface.co` host was decommissioned and no
              longer resolves in DNS; the hf-inference provider on the
              router serves the same `/models/{model}` contract)
    Auth:     `Authorization: Bearer <key>`
    """
    _validate_required_str(api_key, name="huggingface_preset.api_key")
    _validate_required_str(
        model, name="huggingface_preset.model", env_hint="HUGGINGFACE_PROD_MODEL"
    )

    endpoint = Endpoint(base_url=base_url, path_prefix=path_prefix)
    auth = ApiKeyBearer(kind=ApiKeyHeaderKind.Authorization_Bearer, key=ApiKey(api_key))
    return LlmDeployment(
        wire=WireProtocol.HuggingFaceInference,
        endpoint=endpoint,
        auth=auth,
        default_model=model,
        preset_name="huggingface",
    )


def huggingface_chat_preset(
    api_key: str,
    model: str,
    *,
    base_url: str = "https://router.huggingface.co",
    path_prefix: str = "",
) -> LlmDeployment:
    """HuggingFace router — OpenAI-compatible chat-completions schema (#1720 F3).

    Wire:     `HuggingFaceInference`
    Endpoint: `https://router.huggingface.co/v1/chat/completions` (the HF
              Inference-Providers router's OpenAI-compatible chat endpoint;
              the model travels in the JSON BODY, not the URL path — unlike the
              classic `huggingface_preset`, whose `/models/{model}` endpoint
              carries the model in the path)
    Auth:     `Authorization: Bearer <key>`

    Unlike the classic `huggingface_preset` (text-generation
    `{inputs, parameters}` body, NO tool-calling surface), this preset sets
    `completion_routing.use_chat_schema=True` so `LlmClient.complete()` /
    `stream()` shape the OpenAI chat body (`model` + `messages` +
    `tools`/`tool_choice`). Use this preset for TGI / Inference-Endpoint chat
    servers that speak the OpenAI schema and honour tool calls; a caller who
    passes `tools=` to a classic `huggingface_preset` deployment reaches ONLY
    the tool-less classic path (the drop is logged at WARNING, never silent).

    `preset_name` is `"huggingface"` (same as the classic preset) so the
    provider capability-matrix row is shared — both presets describe the same
    HuggingFace provider; only the on-wire route + body schema differ.
    """
    _validate_required_str(api_key, name="huggingface_chat_preset.api_key")
    _validate_required_str(
        model,
        name="huggingface_chat_preset.model",
        env_hint="HUGGINGFACE_PROD_MODEL",
    )

    endpoint = Endpoint(base_url=base_url, path_prefix=path_prefix)
    auth = ApiKeyBearer(kind=ApiKeyHeaderKind.Authorization_Bearer, key=ApiKey(api_key))
    return LlmDeployment(
        wire=WireProtocol.HuggingFaceInference,
        endpoint=endpoint,
        auth=auth,
        default_model=model,
        preset_name="huggingface",
        completion_routing=CompletionRouting(
            path_template="/v1/chat/completions",
            streaming_path_template="/v1/chat/completions",
            use_chat_schema=True,
        ),
    )


def ollama_preset(
    base_url: str,
    model: str,
    *,
    path_prefix: str = "",
) -> LlmDeployment:
    """Ollama self-hosted LLM server (no auth — local by default).

    Wire:     `OllamaNative`
    Endpoint: caller-provided (typically `http://localhost:11434`)
    Auth:     `StaticNone` (no credential — caller is responsible for
              network ACLs around the Ollama server)

    `base_url` is REQUIRED because Ollama has no universal public default;
    the SSRF guard in `url_safety.check_url` still enforces that HTTP is
    only accepted for localhost / 127.0.0.1 / ::1.
    """
    _validate_required_str(base_url, name="ollama_preset.base_url")
    _validate_required_str(
        model, name="ollama_preset.model", env_hint="OLLAMA_PROD_MODEL"
    )

    endpoint = Endpoint(base_url=base_url, path_prefix=path_prefix)
    return LlmDeployment(
        wire=WireProtocol.OllamaNative,
        endpoint=endpoint,
        auth=StaticNone(),
        default_model=model,
        preset_name="ollama",
    )


def docker_model_runner_preset(
    base_url: str,
    model: str,
    *,
    path_prefix: str = "/engines/v1",
) -> LlmDeployment:
    """Docker Model Runner (OpenAI-compatible chat schema, local).

    Wire:     `OpenAiChat`
    Endpoint: caller-provided (typically `http://localhost:12434`)
    Auth:     `StaticNone` (no credential — local-only)

    Docker Model Runner exposes an OpenAI-compatible chat completion
    endpoint under `/engines/v1`. SSRF guard enforces localhost-only HTTP.
    """
    _validate_required_str(base_url, name="docker_model_runner_preset.base_url")
    _validate_required_str(
        model,
        name="docker_model_runner_preset.model",
        env_hint="DOCKER_MODEL_RUNNER_PROD_MODEL",
    )

    endpoint = Endpoint(base_url=base_url, path_prefix=path_prefix)
    return LlmDeployment(
        wire=WireProtocol.OpenAiChat,
        endpoint=endpoint,
        auth=StaticNone(),
        default_model=model,
        preset_name="docker_model_runner",
    )


def groq_preset(
    api_key: str,
    model: str,
    *,
    base_url: str = "https://api.groq.com",
    path_prefix: str = "/openai/v1",
) -> LlmDeployment:
    """Groq inference API (OpenAI-compatible).

    Wire:     `OpenAiChat`
    Endpoint: `https://api.groq.com/openai/v1`
    Auth:     `Authorization: Bearer <key>`
    """
    _validate_required_str(api_key, name="groq_preset.api_key")
    _validate_required_str(model, name="groq_preset.model", env_hint="GROQ_PROD_MODEL")

    endpoint = Endpoint(base_url=base_url, path_prefix=path_prefix)
    auth = ApiKeyBearer(kind=ApiKeyHeaderKind.Authorization_Bearer, key=ApiKey(api_key))
    return LlmDeployment(
        wire=WireProtocol.OpenAiChat,
        endpoint=endpoint,
        auth=auth,
        default_model=model,
        preset_name="groq",
    )


def together_preset(
    api_key: str,
    model: str,
    *,
    base_url: str = "https://api.together.xyz",
    path_prefix: str = "/v1",
) -> LlmDeployment:
    """Together AI inference API (OpenAI-compatible).

    Wire:     `OpenAiChat`
    Endpoint: `https://api.together.xyz/v1`
    Auth:     `Authorization: Bearer <key>`
    """
    _validate_required_str(api_key, name="together_preset.api_key")
    _validate_required_str(
        model, name="together_preset.model", env_hint="TOGETHER_PROD_MODEL"
    )

    endpoint = Endpoint(base_url=base_url, path_prefix=path_prefix)
    auth = ApiKeyBearer(kind=ApiKeyHeaderKind.Authorization_Bearer, key=ApiKey(api_key))
    return LlmDeployment(
        wire=WireProtocol.OpenAiChat,
        endpoint=endpoint,
        auth=auth,
        default_model=model,
        preset_name="together",
    )


def fireworks_preset(
    api_key: str,
    model: str,
    *,
    base_url: str = "https://api.fireworks.ai",
    path_prefix: str = "/inference/v1",
) -> LlmDeployment:
    """Fireworks AI inference API (OpenAI-compatible).

    Wire:     `OpenAiChat`
    Endpoint: `https://api.fireworks.ai/inference/v1`
    Auth:     `Authorization: Bearer <key>`
    """
    _validate_required_str(api_key, name="fireworks_preset.api_key")
    _validate_required_str(
        model, name="fireworks_preset.model", env_hint="FIREWORKS_PROD_MODEL"
    )

    endpoint = Endpoint(base_url=base_url, path_prefix=path_prefix)
    auth = ApiKeyBearer(kind=ApiKeyHeaderKind.Authorization_Bearer, key=ApiKey(api_key))
    return LlmDeployment(
        wire=WireProtocol.OpenAiChat,
        endpoint=endpoint,
        auth=auth,
        default_model=model,
        preset_name="fireworks",
    )


def openrouter_preset(
    api_key: str,
    model: str,
    *,
    base_url: str = "https://openrouter.ai",
    path_prefix: str = "/api/v1",
) -> LlmDeployment:
    """OpenRouter multi-provider aggregator (OpenAI-compatible).

    Wire:     `OpenAiChat`
    Endpoint: `https://openrouter.ai/api/v1`
    Auth:     `Authorization: Bearer <key>`
    """
    _validate_required_str(api_key, name="openrouter_preset.api_key")
    _validate_required_str(
        model, name="openrouter_preset.model", env_hint="OPENROUTER_PROD_MODEL"
    )

    endpoint = Endpoint(base_url=base_url, path_prefix=path_prefix)
    auth = ApiKeyBearer(kind=ApiKeyHeaderKind.Authorization_Bearer, key=ApiKey(api_key))
    return LlmDeployment(
        wire=WireProtocol.OpenAiChat,
        endpoint=endpoint,
        auth=auth,
        default_model=model,
        preset_name="openrouter",
    )


def deepseek_preset(
    api_key: str,
    model: str,
    *,
    base_url: str = "https://api.deepseek.com",
    path_prefix: str = "/v1",
) -> LlmDeployment:
    """DeepSeek inference API (OpenAI-compatible).

    Wire:     `OpenAiChat`
    Endpoint: `https://api.deepseek.com/v1`
    Auth:     `Authorization: Bearer <key>`
    """
    _validate_required_str(api_key, name="deepseek_preset.api_key")
    _validate_required_str(
        model, name="deepseek_preset.model", env_hint="DEEPSEEK_PROD_MODEL"
    )

    endpoint = Endpoint(base_url=base_url, path_prefix=path_prefix)
    auth = ApiKeyBearer(kind=ApiKeyHeaderKind.Authorization_Bearer, key=ApiKey(api_key))
    return LlmDeployment(
        wire=WireProtocol.OpenAiChat,
        endpoint=endpoint,
        auth=auth,
        default_model=model,
        preset_name="deepseek",
    )


def lm_studio_preset(
    base_url: str,
    model: str,
    *,
    path_prefix: str = "/v1",
) -> LlmDeployment:
    """LM Studio local inference server (OpenAI-compatible, no auth).

    Wire:     `OpenAiChat`
    Endpoint: caller-provided (typically `http://localhost:1234`)
    Auth:     `StaticNone` (local-only)
    """
    _validate_required_str(base_url, name="lm_studio_preset.base_url")
    _validate_required_str(
        model, name="lm_studio_preset.model", env_hint="LM_STUDIO_PROD_MODEL"
    )

    endpoint = Endpoint(base_url=base_url, path_prefix=path_prefix)
    return LlmDeployment(
        wire=WireProtocol.OpenAiChat,
        endpoint=endpoint,
        auth=StaticNone(),
        default_model=model,
        preset_name="lm_studio",
    )


def llama_cpp_preset(
    base_url: str,
    model: str,
    *,
    path_prefix: str = "/v1",
) -> LlmDeployment:
    """llama.cpp server (OpenAI-compatible, no auth).

    Wire:     `OpenAiChat`
    Endpoint: caller-provided (typically `http://localhost:8080`)
    Auth:     `StaticNone` (local-only)
    """
    _validate_required_str(base_url, name="llama_cpp_preset.base_url")
    _validate_required_str(
        model, name="llama_cpp_preset.model", env_hint="LLAMA_CPP_PROD_MODEL"
    )

    endpoint = Endpoint(base_url=base_url, path_prefix=path_prefix)
    return LlmDeployment(
        wire=WireProtocol.OpenAiChat,
        endpoint=endpoint,
        auth=StaticNone(),
        default_model=model,
        preset_name="llama_cpp",
    )


# ---------------------------------------------------------------------------
# Default-URL convenience presets (#787 — cross-SDK parity with kailash-rs
# `LlmDeployment::ollama_default()` / `lm_studio_default()` /
# `llama_cpp_default()` / `docker_model_runner()` zero-arg classmethods at
# `crates/kailash-kaizen/src/llm/deployment/presets.rs:509,1138,1170,527`).
# ---------------------------------------------------------------------------
#
# Cross-SDK contract: each `<provider>_default_preset(model)` factory is
# byte-equivalent to calling the parent factory with the canonical localhost
# default URL kailash-rs publishes. The returned `LlmDeployment` carries the
# PARENT preset literal (`"ollama"`, `"lm_studio"`, etc.) per Rust semantics
# (`ollama_default()` calls `Self::ollama(...)` which sets the internal name
# to `"ollama"`); the `_default` variant is purely a constructor convenience,
# not a distinct preset identity. Capability-matrix lookup therefore routes
# through the parent row automatically.
#
# Python idiom-difference vs Rust per EATP D6 (`rules/cross-sdk-inspection.md`
# § 3): `model` is REQUIRED (Python's `rules/env-models.md` mandates explicit
# model selection at construction; Rust accepts a truly zero-arg signature).
# Semantics match — both SDKs route requests to a local server with the
# canonical default URL — only the construction arity differs.


def ollama_default_preset(model: str) -> LlmDeployment:
    """Convenience: ollama_preset with the canonical localhost default URL.

    Cross-SDK parity with kailash-rs ``LlmDeployment::ollama_default()``
    (``crates/kailash-kaizen/src/llm/deployment/presets.rs:509``). Equivalent
    to ``ollama_preset("http://localhost:11434/v1", model)``. The deployment
    carries ``preset_name="ollama"`` (mirrors Rust's ``Self::ollama(...)``
    delegation), so capability-matrix lookups behave identically to the
    long-form constructor.

    `model` is REQUIRED per `rules/env-models.md` — Python presets enforce
    explicit model selection at construction time. The Rust SDK accepts a
    truly zero-arg signature; the Python idiom-difference is acceptable per
    EATP D6 (semantics match).
    """
    return ollama_preset("http://localhost:11434/v1", model)


def lm_studio_default_preset(model: str) -> LlmDeployment:
    """Convenience: lm_studio_preset with the canonical localhost default URL.

    Cross-SDK parity with kailash-rs ``LlmDeployment::lm_studio_default()``
    (``crates/kailash-kaizen/src/llm/deployment/presets.rs:1138``). Equivalent
    to ``lm_studio_preset("http://localhost:1234", model)``. The deployment
    carries ``preset_name="lm_studio"``.
    """
    return lm_studio_preset("http://localhost:1234", model)


def llama_cpp_default_preset(model: str) -> LlmDeployment:
    """Convenience: llama_cpp_preset with the canonical localhost default URL.

    Cross-SDK parity with kailash-rs ``LlmDeployment::llama_cpp_default()``
    (``crates/kailash-kaizen/src/llm/deployment/presets.rs:1170``). Equivalent
    to ``llama_cpp_preset("http://localhost:8080", model)``. The deployment
    carries ``preset_name="llama_cpp"``.
    """
    return llama_cpp_preset("http://localhost:8080", model)


def docker_model_runner_default_preset(model: str) -> LlmDeployment:
    """Convenience: docker_model_runner_preset with the canonical default URL.

    Cross-SDK parity with kailash-rs zero-arg ``LlmDeployment::
    docker_model_runner()`` (``crates/kailash-kaizen/src/llm/deployment/
    presets.rs:527``), which constructs ``http://localhost:12434/engines/
    llama.cpp/v1``. The deployment carries ``preset_name="docker_model_runner"``.

    Note: the `path_prefix` differs from `docker_model_runner_preset`'s default
    (``/engines/v1``) to match Rust's engine-specific path; both URLs are valid
    Docker Model Runner endpoints, but Rust's zero-arg shortcut targets the
    llama.cpp engine specifically.
    """
    return docker_model_runner_preset(
        "http://localhost:12434",
        model,
        path_prefix="/engines/llama.cpp/v1",
    )


# ---------------------------------------------------------------------------
# Registration + classmethod attachment (Session 2)
# ---------------------------------------------------------------------------


def _register_and_attach_session_2_presets() -> None:
    """Register all 15 S3 presets AND attach as `LlmDeployment.<name>`.

    Single point of truth: one table lists every (name, factory, is_byok)
    tuple. `is_byok` distinguishes `api_key`-first presets (anthropic,
    groq, ...) from `base_url`-first presets (ollama, lm_studio,
    llama_cpp, docker_model_runner) so the attached classmethod's
    signature matches the factory.

    Registration and attachment MUST happen atomically because downstream
    consumers may use either path:

      * `LlmDeployment.anthropic(key, model=...)`   # classmethod
      * `get_preset("anthropic")(key, model=...)`    # registry

    A preset that is registered but not attached (or vice versa) would be
    silently visible via only one surface.
    """
    byok_table = [
        ("anthropic", anthropic_preset),
        ("google", google_preset),
        ("cohere", cohere_preset),
        ("mistral", mistral_preset),
        ("perplexity", perplexity_preset),
        ("huggingface", huggingface_preset),
        ("huggingface_chat", huggingface_chat_preset),
        ("groq", groq_preset),
        ("together", together_preset),
        ("fireworks", fireworks_preset),
        ("openrouter", openrouter_preset),
        ("deepseek", deepseek_preset),
    ]
    url_first_table = [
        ("ollama", ollama_preset),
        ("docker_model_runner", docker_model_runner_preset),
        ("lm_studio", lm_studio_preset),
        ("llama_cpp", llama_cpp_preset),
    ]

    # Default-URL convenience presets (#787) — model-only signature; each
    # delegates to the parent factory with the canonical localhost URL.
    # Registry name is `<parent>_default`; deployment's `preset_name` is the
    # PARENT literal so capability-matrix lookup routes through the parent row.
    model_only_table = [
        ("ollama_default", ollama_default_preset),
        ("lm_studio_default", lm_studio_default_preset),
        ("llama_cpp_default", llama_cpp_default_preset),
        ("docker_model_runner_default", docker_model_runner_default_preset),
    ]

    for name, factory in byok_table:
        register_preset(name, factory)

        # Bind factory via a default-arg closure so each classmethod
        # captures its own factory reference (standard Python closure
        # pitfall workaround).
        def _byok_cm(
            cls, api_key: str, model: str, _factory=factory, **kwargs: Any
        ) -> LlmDeployment:
            return _factory(api_key, model=model, **kwargs)

        _byok_cm.__name__ = name
        _byok_cm.__qualname__ = f"LlmDeployment.{name}"
        setattr(LlmDeployment, name, classmethod(_byok_cm))

    for name, factory in url_first_table:
        register_preset(name, factory)

        def _url_cm(
            cls, base_url: str, model: str, _factory=factory, **kwargs: Any
        ) -> LlmDeployment:
            return _factory(base_url, model=model, **kwargs)

        _url_cm.__name__ = name
        _url_cm.__qualname__ = f"LlmDeployment.{name}"
        setattr(LlmDeployment, name, classmethod(_url_cm))

    for name, factory in model_only_table:
        register_preset(name, factory)

        def _model_only_cm(
            cls, model: str, _factory=factory, **kwargs: Any
        ) -> LlmDeployment:
            return _factory(model=model, **kwargs)

        _model_only_cm.__name__ = name
        _model_only_cm.__qualname__ = f"LlmDeployment.{name}"
        setattr(LlmDeployment, name, classmethod(_model_only_cm))


_register_and_attach_session_2_presets()


# ---------------------------------------------------------------------------
# Session 3 (S4a) -- Bedrock Claude preset
# ---------------------------------------------------------------------------
#
# Distinctive preset shape vs the S3 direct-provider presets:
#
#   * Takes `api_key` + `region` (bearer-token auth) rather than just key.
#   * Region is carried on the AwsBearerToken strategy AND is the source
#     of truth for the endpoint host (bedrock-runtime.{region}.amazonaws.com).
#   * Model is resolved via BedrockClaudeGrammar at caller time; the
#     factory stores the RAW caller-supplied model string (e.g.
#     "claude-sonnet-4-6") and the grammar is applied at completion time.
#   * `ModelRequired` is raised with deployment_preset="bedrock_claude" when
#     the model argument is absent or empty (per rules/env-models.md).


_GRAMMAR_BEDROCK_CLAUDE = BedrockClaudeGrammar()


def bedrock_claude_preset(
    api_key: str,
    region: str,
    model: str,
) -> LlmDeployment:
    """AWS Bedrock Claude deployment using a bearer-token credential.

    Wire:        `AnthropicMessages` (Bedrock speaks the same Messages
                 schema as Anthropic direct -- only the endpoint + auth
                 change).
    Endpoint:    `https://bedrock-runtime.{region}.amazonaws.com` --
                 derived from the validated region. The region is NEVER
                 taken from a URL fragment; only the allowlist-checked
                 value goes into the hostname, so there is no
                 grammar-injection path into the endpoint.
    Auth:        `AwsBearerToken(token, region)` applying
                 `Authorization: Bearer <token>`.
    Model:       Validated via `BedrockClaudeGrammar` at caller time and
                 stored on the deployment as the RAW caller alias. Wire
                 adapters translate to the on-wire id via the grammar.

    Required arguments:

    * `api_key` -- the Bedrock bearer token (e.g. `$AWS_BEARER_TOKEN_BEDROCK`)
    * `region` -- one of `BEDROCK_SUPPORTED_REGIONS` (typed error otherwise)
    * `model` -- a short alias (`claude-sonnet-4-6`), inference-profile
      id (`global.anthropic.claude-sonnet-4-6`), or native on-wire id.
      Missing / empty raises `ModelRequired(deployment_preset="bedrock_claude",
      env_hint="BEDROCK_MODEL_ID")`.

    Observability: emits `llm.deployment.bedrock_claude.constructed` at
    INFO with `deployment_preset`, `region`, `auth_strategy_kind`, and
    `endpoint_host` fields. All four values are non-sensitive constants
    (region strings are public AWS identifiers; auth_strategy_kind and
    deployment_preset are fixed literals), so logging them verbatim is
    injection-safe.

    Cross-SDK parity: the preset name `bedrock_claude` is byte-identical
    to the Rust literal in
    `kailash-rs/crates/kailash-kaizen/src/llm/deployment/presets.rs`.
    """
    # --- api_key validation --------------------------------------------------
    if not isinstance(api_key, str) or not api_key:
        raise ValueError(
            "bedrock_claude_preset requires a non-empty api_key string "
            "(typically os.environ['AWS_BEARER_TOKEN_BEDROCK'])"
        )
    # --- model validation (per env-models.md) ---------------------------------
    if not isinstance(model, str) or not model:
        raise ModelRequired(
            deployment_preset="bedrock_claude",
            env_hint="BEDROCK_MODEL_ID",
        )
    # Route through the grammar gate at preset-build time so the caller
    # sees the typed ModelGrammarInvalid immediately rather than at the
    # first completion call. The resolved on-wire id is also what ends up
    # on the deployment's `default_model` so wire adapters don't have to
    # re-resolve. We deliberately store the RESOLVED id so downstream
    # observability dashboards can group by the true on-wire model.
    resolved_model = _GRAMMAR_BEDROCK_CLAUDE.resolve(model)
    # --- auth + region -------------------------------------------------------
    # AwsBearerToken.__init__ validates the region against the allowlist.
    # If the region is bad we get a RegionNotAllowed raised from the
    # auth constructor -- no need for a duplicate validate call here.
    auth = AwsBearerToken(token=api_key, region=region)
    endpoint_host = f"bedrock-runtime.{region}.amazonaws.com"
    endpoint = Endpoint(
        base_url=f"https://{endpoint_host}",
        path_prefix="",
    )
    # Bedrock Claude speaks the same Messages wire as Anthropic direct;
    # only the endpoint host + auth strategy differ. Cross-SDK parity with
    # kailash-rs presets.rs:408.
    deployment = LlmDeployment(
        wire=WireProtocol.AnthropicMessages,
        endpoint=endpoint,
        auth=auth,
        default_model=resolved_model,
        completion_routing=CompletionRouting(
            # Bedrock carries the model in the URL path; path_prefix is empty
            # so the {model} substitution forms /model/{id}/invoke.
            path_template="/model/{model}/invoke",
            streaming_path_template="/model/{model}/invoke-with-response-stream",
            # Bedrock-hosted Anthropic strips `model` from the body and
            # injects this version literal.
            anthropic_version_body="bedrock-2023-05-31",
        ),
        preset_name="bedrock_claude",
    )
    logger.info(
        "llm.deployment.bedrock_claude.constructed",
        extra={
            "deployment_preset": "bedrock_claude",
            "region": region,
            "auth_strategy_kind": auth.auth_strategy_kind(),
            "endpoint_host": endpoint_host,
        },
    )
    return deployment


register_preset("bedrock_claude", bedrock_claude_preset)


def _attach_bedrock_claude_classmethod() -> None:
    """Replace `LlmDeployment.bedrock_claude`'s NotImplementedError stub.

    The stub in `deployment.py` raises until this runs; attaching here
    follows the same pattern as every other preset (classmethod + module
    function both legal).
    """

    @classmethod  # type: ignore[misc]
    def bedrock_claude(cls, api_key: str, region: str, model: str) -> LlmDeployment:
        return bedrock_claude_preset(api_key, region=region, model=model)

    LlmDeployment.bedrock_claude = bedrock_claude  # type: ignore[attr-defined]


_attach_bedrock_claude_classmethod()


# ---------------------------------------------------------------------------
# Session 4 (S4b-ii) -- Bedrock Llama / Titan / Mistral / Cohere presets
# ---------------------------------------------------------------------------
#
# Each of these four presets mirrors `bedrock_claude_preset` contractually:
#
#   * Required args: `api_key` (bearer token), `region` (Bedrock allowlist),
#     `model` (caller alias / inference-profile / native on-wire id).
#   * Auth: `AwsBearerToken` (bearer-token fast path). Callers with
#     assumed-role / workload-identity credentials use `AwsSigV4` via a
#     manually-constructed deployment -- the bearer preset is the 90% path.
#   * Endpoint: `bedrock-runtime.{region}.amazonaws.com` -- same host as
#     Bedrock-Claude. Bedrock routes all families through one runtime.
#   * Wire: `BedrockInvoke` for non-Anthropic families because Llama /
#     Titan / Mistral / Cohere on Bedrock speak the native Bedrock
#     `invoke-model` schema, not the Anthropic Messages schema that
#     Bedrock-Claude uses. This is a family-level shape difference, NOT
#     a Kaizen implementation choice.
#   * Observability: every construction emits a structured INFO log with
#     deployment_preset, region, auth_strategy_kind, endpoint_host. Same
#     log shape as bedrock_claude for forensic correlation.

_GRAMMAR_BEDROCK_LLAMA = BedrockLlamaGrammar()
_GRAMMAR_BEDROCK_TITAN = BedrockTitanGrammar()
_GRAMMAR_BEDROCK_MISTRAL = BedrockMistralGrammar()
_GRAMMAR_BEDROCK_COHERE = BedrockCohereGrammar()


def _build_bedrock_deployment(
    *,
    preset_name: str,
    api_key: str,
    region: str,
    model: str,
    env_hint: str,
    grammar: Any,
    wire: WireProtocol,
) -> LlmDeployment:
    """Shared constructor for the 4 non-Claude Bedrock presets.

    Consolidates validation, grammar resolution, auth construction, and
    observability so every family's preset is a thin one-liner wrapper.
    Rejecting drift between the 4 families is the reason this helper
    exists -- the failure mode for Session 3 was "one preset has the
    structured log, another forgets it".
    """
    if not isinstance(api_key, str) or not api_key:
        raise ValueError(
            f"{preset_name}_preset requires a non-empty api_key string "
            f"(typically os.environ['AWS_BEARER_TOKEN_BEDROCK'])"
        )
    if not isinstance(model, str) or not model:
        raise ModelRequired(deployment_preset=preset_name, env_hint=env_hint)
    resolved_model = grammar.resolve(model)
    auth = AwsBearerToken(token=api_key, region=region)
    endpoint_host = f"bedrock-runtime.{region}.amazonaws.com"
    endpoint = Endpoint(base_url=f"https://{endpoint_host}", path_prefix="")
    deployment = LlmDeployment(
        wire=wire,
        endpoint=endpoint,
        auth=auth,
        default_model=resolved_model,
        completion_routing=CompletionRouting(
            # Native Bedrock invoke path; model carried in the URL, empty
            # path_prefix so {model} forms /model/{id}/invoke.
            path_template="/model/{model}/invoke",
            streaming_path_template="/model/{model}/invoke-with-response-stream",
        ),
        preset_name=preset_name,
    )
    logger.info(
        f"llm.deployment.{preset_name}.constructed",
        extra={
            "deployment_preset": preset_name,
            "region": region,
            "auth_strategy_kind": auth.auth_strategy_kind(),
            "endpoint_host": endpoint_host,
        },
    )
    return deployment


def bedrock_llama_preset(
    api_key: str,
    region: str,
    model: str,
) -> LlmDeployment:
    """AWS Bedrock Meta Llama deployment (bearer-token auth).

    Wire: `BedrockInvoke` -- Llama on Bedrock speaks the native Bedrock
    invoke-model schema, not Anthropic Messages.
    Endpoint: `https://bedrock-runtime.{region}.amazonaws.com`
    Auth: `AwsBearerToken(token, region)`

    Short aliases: `llama-3-8b`, `llama-3-70b`, `llama-3.1-8b`,
    `llama-3.1-70b`, `llama-3.1-405b`, `llama-3.2-1b`, `llama-3.2-3b`,
    `llama-3.2-11b`, `llama-3.2-90b`, `llama-3.3-70b`.
    Also accepts `meta.*` on-wire ids and `{region}.meta.*` profiles.
    """
    return _build_bedrock_deployment(
        preset_name="bedrock_llama",
        api_key=api_key,
        region=region,
        model=model,
        env_hint="BEDROCK_LLAMA_MODEL_ID",
        grammar=_GRAMMAR_BEDROCK_LLAMA,
        wire=WireProtocol.BedrockInvoke,
    )


def bedrock_titan_preset(
    api_key: str,
    region: str,
    model: str,
) -> LlmDeployment:
    """AWS Bedrock Amazon Titan deployment (bearer-token auth).

    Wire: `BedrockInvoke`
    Endpoint: `https://bedrock-runtime.{region}.amazonaws.com`
    Auth: `AwsBearerToken(token, region)`

    Short aliases: `titan-text-lite`, `titan-text-express`,
    `titan-text-premier`, `titan-embed-text`, `titan-embed-text-v2`,
    `titan-embed-image`. Also accepts `amazon.*` on-wire ids.
    """
    return _build_bedrock_deployment(
        preset_name="bedrock_titan",
        api_key=api_key,
        region=region,
        model=model,
        env_hint="BEDROCK_TITAN_MODEL_ID",
        grammar=_GRAMMAR_BEDROCK_TITAN,
        wire=WireProtocol.BedrockInvoke,
    )


def bedrock_mistral_preset(
    api_key: str,
    region: str,
    model: str,
) -> LlmDeployment:
    """AWS Bedrock Mistral deployment (bearer-token auth).

    Wire: `BedrockInvoke`
    Endpoint: `https://bedrock-runtime.{region}.amazonaws.com`
    Auth: `AwsBearerToken(token, region)`

    Distinct from `mistral_preset` (Mistral-direct API). On-wire ids here
    are `mistral.*-v1:0`. Short aliases: `mistral-7b`, `mixtral-8x7b`,
    `mistral-small`, `mistral-large`, `mistral-large-2407`.
    """
    return _build_bedrock_deployment(
        preset_name="bedrock_mistral",
        api_key=api_key,
        region=region,
        model=model,
        env_hint="BEDROCK_MISTRAL_MODEL_ID",
        grammar=_GRAMMAR_BEDROCK_MISTRAL,
        wire=WireProtocol.BedrockInvoke,
    )


def bedrock_cohere_preset(
    api_key: str,
    region: str,
    model: str,
) -> LlmDeployment:
    """AWS Bedrock Cohere deployment (bearer-token auth).

    Wire: `BedrockInvoke`
    Endpoint: `https://bedrock-runtime.{region}.amazonaws.com`
    Auth: `AwsBearerToken(token, region)`

    Distinct from `cohere_preset` (Cohere-direct API). On-wire ids here
    are `cohere.*-v1:0`. Short aliases: `cohere-command`,
    `cohere-command-light`, `cohere-command-r`, `cohere-command-r-plus`,
    `cohere-embed-english`, `cohere-embed-multilingual`.
    """
    return _build_bedrock_deployment(
        preset_name="bedrock_cohere",
        api_key=api_key,
        region=region,
        model=model,
        env_hint="BEDROCK_COHERE_MODEL_ID",
        grammar=_GRAMMAR_BEDROCK_COHERE,
        wire=WireProtocol.BedrockInvoke,
    )


def _register_and_attach_session_4_presets() -> None:
    """Register the 4 S4b-ii Bedrock presets AND replace the
    NotImplementedError stubs on LlmDeployment.

    `bedrock_cohere` is added here as a NEW preset (not previously
    stubbed on LlmDeployment because the deployment.py stub list only
    contained `bedrock_llama` / `bedrock_titan` / `bedrock_mistral`); it
    is attached via `setattr` the same way the S3 presets are.
    """
    table = [
        ("bedrock_llama", bedrock_llama_preset),
        ("bedrock_titan", bedrock_titan_preset),
        ("bedrock_mistral", bedrock_mistral_preset),
        ("bedrock_cohere", bedrock_cohere_preset),
    ]
    for name, factory in table:
        register_preset(name, factory)

        def _bedrock_cm(
            cls,
            api_key: str,
            region: str,
            model: str,
            _factory=factory,
        ) -> LlmDeployment:
            return _factory(api_key, region=region, model=model)

        _bedrock_cm.__name__ = name
        _bedrock_cm.__qualname__ = f"LlmDeployment.{name}"
        setattr(LlmDeployment, name, classmethod(_bedrock_cm))


_register_and_attach_session_4_presets()


# ---------------------------------------------------------------------------
# Session 5 (S5) -- Vertex AI presets (Claude + Gemini)
# ---------------------------------------------------------------------------
#
# Distinctive preset shape vs Bedrock:
#
#   * Takes `service_account_key` (dict OR path) + `project` + `region` +
#     `model`. Auth is GcpOauth (single-flight OAuth2) rather than a static
#     bearer token.
#   * Endpoint host is region-specific:
#     `https://{region}-aiplatform.googleapis.com/v1/projects/{project}/
#     locations/{region}/publishers/{publisher}/models/{model}:rawPredict`
#     where publisher = "anthropic" for Claude, "google" for Gemini.
#   * Project + region are validated against strict regexes at preset
#     construction so a malicious value never reaches the URL builder
#     (defense in depth -- url_safety.check_url is the structural defense).
#   * Model is resolved via the family grammar; resolved id ends up in
#     both `default_model` AND the URL path.
#
# Cross-SDK parity: preset names `vertex_claude` and `vertex_gemini` are
# byte-identical to the Rust SDK literals
# (`kailash-rs/crates/kailash-kaizen/src/llm/deployment/presets.rs`).

_GRAMMAR_VERTEX_CLAUDE = VertexClaudeGrammar()
_GRAMMAR_VERTEX_GEMINI = VertexGeminiGrammar()


# Strict per-segment validation regexes. GCP project IDs are 6-30 chars,
# lowercase letters / digits / hyphen, must start with a letter. Region
# names follow the `<area>-<locality><digit>` shape (e.g. `us-central1`,
# `europe-west4`). The regexes are intentionally narrow because the
# values are interpolated into the URL host + path and a permissive
# match would be a host-control vector.
_PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9\-]{4,28}[a-z0-9]$")
_REGION_RE = re.compile(r"^[a-z]{2,20}-[a-z]+\d{1,2}$")

# NEW-B: Vertex multi-region + global location literals accepted in addition
# to concrete regions (`us-central1`, `europe-west4`). `us` / `eu` are
# multi-region location values that pass STRAIGHT THROUGH into the URL path
# (`locations/us`, `locations/eu`); the host still needs a concrete regional
# subdomain, so a concrete default is used for host derivation ONLY (eu →
# europe-west3, NOT europe-west1). `global` uses the region-less
# `aiplatform.googleapis.com` host with `locations/global`.
_VERTEX_MULTI_REGIONS: frozenset[str] = frozenset({"us", "eu", "global"})

# Concrete regional subdomain used to build the HOST for a multi-region
# location value. The path `locations/<region>` still carries the multi-region
# literal verbatim; only the `{host_region}-aiplatform.googleapis.com`
# subdomain needs a concrete region.
_VERTEX_MULTIREGION_HOST_DEFAULTS: Dict[str, str] = {
    "us": "us-central1",
    "eu": "europe-west3",
}


def _validate_vertex_project(project: Any) -> str:
    """Validate a GCP project id against the strict allowlist regex.

    Raises `ValueError` with a stable error code on failure. The raw
    project value is NOT echoed (log-injection defense -- same shape as
    the preset-name validator). A successful return yields the unchanged
    project id ready for URL interpolation.
    """
    if not isinstance(project, str) or not project:
        raise ValueError(
            "vertex preset requires a non-empty project string "
            "(e.g. 'my-gcp-project-1234')"
        )
    if not _PROJECT_ID_RE.match(project):
        raise ValueError(
            "vertex project id failed validation against "
            f"^[a-z][a-z0-9\\-]{{4,28}}[a-z0-9]$ "
            f"(project_fingerprint={_fingerprint(project)})"
        )
    return project


def _validate_vertex_region(region: Any) -> str:
    """Validate a GCP region against the strict allowlist regex.

    Accepts concrete regions (``us-central1``, ``europe-west4``) AND the
    multi-region / global location literals ``us`` / ``eu`` / ``global``
    (NEW-B). Everything else fails with a log-injection-safe fingerprint.
    """
    if not isinstance(region, str) or not region:
        raise ValueError(
            "vertex preset requires a non-empty region string "
            "(e.g. 'us-central1', 'europe-west4', 'us', 'eu', 'global')"
        )
    if region in _VERTEX_MULTI_REGIONS:
        return region
    if not _REGION_RE.match(region):
        raise ValueError(
            "vertex region failed validation against "
            f"^[a-z]{{2,20}}-[a-z]+\\d{{1,2}}$ (or one of us/eu/global) "
            f"(region_fingerprint={_fingerprint(region)})"
        )
    return region


def _derive_vertex_host_and_location(region: str) -> tuple[str, str]:
    """Return ``(endpoint_host, path_location)`` for a validated region.

    * ``global`` → region-less host ``aiplatform.googleapis.com``, location
      ``global``.
    * ``us`` / ``eu`` → host uses the concrete default subdomain
      (``us-central1`` / ``europe-west3``); the location passes THROUGH
      as the multi-region literal so the path is ``locations/us`` /
      ``locations/eu``.
    * concrete region (``us-central1``) → host + location are both the region.
    """
    if region == "global":
        return "aiplatform.googleapis.com", "global"
    if region in _VERTEX_MULTIREGION_HOST_DEFAULTS:
        host_region = _VERTEX_MULTIREGION_HOST_DEFAULTS[region]
        return f"{host_region}-aiplatform.googleapis.com", region
    return f"{region}-aiplatform.googleapis.com", region


def _build_vertex_deployment(
    *,
    preset_name: str,
    publisher: str,
    service_account_key: dict | str | None,
    project: str,
    region: str,
    model: str,
    env_hint: str,
    grammar: Any,
    wire: WireProtocol,
    routing: Optional[CompletionRouting] = None,
) -> LlmDeployment:
    """Shared constructor for the 2 Vertex presets.

    Consolidates project/region validation, grammar resolution, GcpOauth
    construction, endpoint assembly, and observability so each family's
    preset is a thin wrapper. Drift between vertex_claude and
    vertex_gemini -- specifically "one preset has the structured log,
    another forgets it" -- is structurally impossible by construction.
    """
    # --- model validation (per env-models.md) -------------------------------
    if not isinstance(model, str) or not model:
        raise ModelRequired(deployment_preset=preset_name, env_hint=env_hint)
    # --- project + region validation (defense in depth before URL build) ---
    validated_project = _validate_vertex_project(project)
    validated_region = _validate_vertex_region(region)
    # --- grammar resolution -------------------------------------------------
    resolved_model = grammar.resolve(model)
    # --- auth construction --------------------------------------------------
    # GcpOauth.__init__ validates the service-account key shape (dict or
    # path string) and rejects empties. Scopes default to the cloud-
    # platform scope per Vertex spec.
    auth = GcpOauth(service_account_key=service_account_key)
    # --- endpoint assembly --------------------------------------------------
    # Host + path-location derive from the region: `global` uses the
    # region-less host; `us` / `eu` multi-region literals pass through into
    # the path while the host uses a concrete default subdomain (NEW-B).
    endpoint_host, path_location = _derive_vertex_host_and_location(validated_region)
    # path_prefix carries the full project/location/publisher/model path; the
    # completion path appends the routing verb (`:rawPredict` for
    # Anthropic-on-Vertex, `:generateContent` for Gemini) at send time.
    path_prefix = (
        f"/v1/projects/{validated_project}/locations/{path_location}"
        f"/publishers/{publisher}/models/{resolved_model}"
    )
    endpoint = Endpoint(
        base_url=f"https://{endpoint_host}",
        path_prefix=path_prefix,
    )
    deployment = LlmDeployment(
        wire=wire,
        endpoint=endpoint,
        auth=auth,
        default_model=resolved_model,
        completion_routing=routing,
        preset_name=preset_name,
    )
    logger.info(
        f"llm.deployment.{preset_name}.constructed",
        extra={
            "deployment_preset": preset_name,
            "project": validated_project,
            "region": validated_region,
            "publisher": publisher,
            "auth_strategy_kind": auth.auth_strategy_kind(),
            "endpoint_host": endpoint_host,
        },
    )
    return deployment


def vertex_claude_preset(
    service_account_key: dict | str | None,
    project: str,
    region: str,
    model: str,
) -> LlmDeployment:
    """Anthropic Claude served via Google Vertex AI.

    Wire:        `AnthropicMessages` (Vertex-Claude speaks Anthropic's
                 Messages schema; only the endpoint + auth differ from
                 Anthropic-direct).
    Endpoint:    `https://{region}-aiplatform.googleapis.com/v1/projects/
                 {project}/locations/{region}/publishers/anthropic/models/
                 {resolved_model}` -- the wire adapter appends
                 `:rawPredict` at completion time.
    Auth:        `GcpOauth(service_account_key)` -- single-flight OAuth2
                 token via google-auth, scoped to cloud-platform.
    Model:       Validated via `VertexClaudeGrammar` at caller time and
                 stored on the deployment as the resolved on-wire id.

    Required arguments:

    * `service_account_key` -- dict (parsed JSON) OR path string
      (typically `os.environ["GOOGLE_APPLICATION_CREDENTIALS"]`)
    * `project` -- GCP project id matching `^[a-z][a-z0-9-]{4,28}[a-z0-9]$`
    * `region` -- Vertex region matching `^[a-z]{2,20}-[a-z]+\\d{1,2}$`
      (e.g. `us-central1`, `europe-west4`)
    * `model` -- short alias (`claude-3-opus`, `claude-sonnet-4-6`) or
      already-versioned id (`claude-3-opus@20240229`). Missing / empty
      raises `ModelRequired(deployment_preset="vertex_claude",
      env_hint="VERTEX_CLAUDE_MODEL_ID")`.

    Observability: emits `llm.deployment.vertex_claude.constructed` at
    INFO with `deployment_preset`, `project`, `region`, `publisher`,
    `auth_strategy_kind`, and `endpoint_host` -- all non-sensitive
    operational identifiers, injection-safe to log verbatim.

    Cross-SDK parity: the preset name `vertex_claude` is byte-identical
    to the Rust SDK literal. The token cache + single-flight refresh
    contract matches the Rust `GcpOauth` strategy.
    """
    return _build_vertex_deployment(
        preset_name="vertex_claude",
        publisher="anthropic",
        service_account_key=service_account_key,
        project=project,
        region=region,
        model=model,
        env_hint="VERTEX_CLAUDE_MODEL_ID",
        grammar=_GRAMMAR_VERTEX_CLAUDE,
        wire=WireProtocol.AnthropicMessages,
        routing=CompletionRouting(
            # model already lives in path_prefix (.../models/{model}); the
            # verb attaches directly (leading ':') at send time.
            path_template=":rawPredict",
            streaming_path_template=":streamRawPredict",
            # Vertex-hosted Anthropic strips `model` from the body and
            # injects this version literal.
            anthropic_version_body="vertex-2023-10-16",
        ),
    )


def vertex_gemini_preset(
    service_account_key: dict | str | None,
    project: str,
    region: str,
    model: str,
) -> LlmDeployment:
    """Google Gemini served via Vertex AI.

    Wire:        `VertexGenerateContent`
    Endpoint:    `https://{region}-aiplatform.googleapis.com/v1/projects/
                 {project}/locations/{region}/publishers/google/models/
                 {resolved_model}`
    Auth:        `GcpOauth(service_account_key)` -- same single-flight
                 OAuth2 strategy used by `vertex_claude_preset`.
    Model:       Validated via `VertexGeminiGrammar`. Short aliases
                 (`gemini-1.5-pro`, `gemini-2.0-flash`) and any
                 `gemini-*` model id are accepted.

    Required arguments mirror `vertex_claude_preset`. Missing / empty
    `model` raises `ModelRequired(deployment_preset="vertex_gemini",
    env_hint="VERTEX_GEMINI_MODEL_ID")`.

    Cross-SDK parity: byte-identical preset name + grammar mapping with
    the Rust SDK.
    """
    return _build_vertex_deployment(
        preset_name="vertex_gemini",
        publisher="google",
        service_account_key=service_account_key,
        project=project,
        region=region,
        model=model,
        env_hint="VERTEX_GEMINI_MODEL_ID",
        grammar=_GRAMMAR_VERTEX_GEMINI,
        wire=WireProtocol.VertexGenerateContent,
        routing=CompletionRouting(
            # model already in path_prefix; verb attaches directly.
            path_template=":generateContent",
            streaming_path_template=":streamGenerateContent",
        ),
    )


def _register_and_attach_session_5_presets() -> None:
    """Register the 2 S5 Vertex presets AND attach as `LlmDeployment.<name>`.

    Replaces the `LlmDeployment.vertex_gemini` NotImplementedError stub
    AND adds the previously-missing `LlmDeployment.vertex_claude`
    classmethod (no stub existed for vertex_claude in S1-S4 because the
    deferred-stub list only contained azure_* + vertex_gemini; the
    vertex_claude attachment is therefore a fresh `setattr`).
    """
    table = [
        ("vertex_claude", vertex_claude_preset),
        ("vertex_gemini", vertex_gemini_preset),
    ]
    for name, factory in table:
        register_preset(name, factory)

        def _vertex_cm(
            cls,
            service_account_key: dict | str,
            project: str,
            region: str,
            model: str,
            _factory=factory,
        ) -> LlmDeployment:
            return _factory(
                service_account_key,
                project=project,
                region=region,
                model=model,
            )

        _vertex_cm.__name__ = name
        _vertex_cm.__qualname__ = f"LlmDeployment.{name}"
        setattr(LlmDeployment, name, classmethod(_vertex_cm))


_register_and_attach_session_5_presets()


# ---------------------------------------------------------------------------
# Azure OpenAI preset (Session 6 -- S6)
# ---------------------------------------------------------------------------

from kaizen.llm.auth.azure import AzureEntra
from kaizen.llm.grammar.azure_openai import AzureOpenAIGrammar

# Default Azure OpenAI api-version. Pinned; matches the Rust SDK constant
# (`kailash-rs/crates/kailash-kaizen/src/llm/deployment/azure.rs::DEFAULT_API_VERSION`).
# Operators who need a different version pass `api_version=...` to the preset.
AZURE_OPENAI_DEFAULT_API_VERSION: str = "2024-06-01"

# Azure resource-name allowlist regex. Azure requires 3-24 alphanumeric +
# hyphen chars, must start with a letter. Narrow on purpose: the value
# is interpolated into the endpoint host (`{resource}.openai.azure.com`)
# and a permissive match is a host-control vector.
_AZURE_RESOURCE_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,22}[a-z0-9]$")

_GRAMMAR_AZURE_OPENAI = AzureOpenAIGrammar()


def _validate_azure_resource(resource_name: Any) -> str:
    """Validate an Azure OpenAI resource name against the strict allowlist."""
    if not isinstance(resource_name, str) or not resource_name:
        raise ValueError(
            "azure_openai preset requires a non-empty resource_name "
            "(e.g. 'my-openai-resource')"
        )
    if not _AZURE_RESOURCE_NAME_RE.match(resource_name):
        raise ValueError(
            "azure_openai resource_name failed validation against "
            f"^[a-z][a-z0-9-]{{1,22}}[a-z0-9]$ "
            f"(resource_fingerprint={_fingerprint(resource_name)})"
        )
    return resource_name


def azure_openai_preset(
    resource_name: str,
    deployment_name: str,
    auth: AzureEntra,
    *,
    api_version: Optional[str] = None,
) -> LlmDeployment:
    """Azure OpenAI deployment -- composed with an AzureEntra auth strategy.

    Wire:        `OpenAiChat` (Azure OpenAI speaks the same on-wire JSON
                 as OpenAI-direct; only the URL + auth differ).
    Endpoint:    `https://{resource}.openai.azure.com/openai/deployments/{deployment}`
                 with `?api-version={api_version}` appended by the wire
                 adapter at completion time.
    Auth:        any `AzureEntra` instance -- api-key, workload-identity,
                 or managed-identity variant.
    Model:       The `deployment_name` IS the model identifier on the
                 wire; Azure does not use upstream OpenAI model ids.

    Required arguments:

    * `resource_name` -- Azure resource name matching the strict regex.
    * `deployment_name` -- Caller-chosen Azure deployment name, 1-64
      chars of `[a-zA-Z0-9_-]`.
    * `auth` -- pre-constructed `AzureEntra` (callers own the variant).

    Optional:

    * `api_version` -- defaults to `AZURE_OPENAI_DEFAULT_API_VERSION`.

    Cross-SDK parity: preset name `azure_openai` + default api-version +
    endpoint path template are byte-identical to the Rust SDK.
    """
    validated_resource = _validate_azure_resource(resource_name)
    resolved_deployment = _GRAMMAR_AZURE_OPENAI.resolve(deployment_name)
    if api_version is None:
        api_version = AZURE_OPENAI_DEFAULT_API_VERSION
    if not isinstance(api_version, str) or not api_version:
        raise ValueError(
            "azure_openai api_version must be a non-empty string "
            f"(default is '{AZURE_OPENAI_DEFAULT_API_VERSION}')"
        )
    if not isinstance(auth, AzureEntra):
        raise TypeError(
            "azure_openai preset requires an AzureEntra auth instance; "
            f"got {type(auth).__name__}"
        )

    endpoint_host = f"{validated_resource}.openai.azure.com"
    path_prefix = f"/openai/deployments/{resolved_deployment}"
    endpoint = Endpoint(
        base_url=f"https://{endpoint_host}",
        path_prefix=path_prefix,
        # Azure REQUIRES ?api-version= on EVERY request URL — completion AND
        # embed. Wiring it into endpoint.query_params (rather than only the
        # completion adapter's docstring-promised append) means both
        # _build_completion_url and _build_embed_url emit it, since both now
        # append endpoint.query_params (#1720 Wave-1b embed-remainder). Without
        # this an azure embed() call hits /embeddings with no api-version -> 400.
        query_params={"api-version": api_version},
    )
    deployment = LlmDeployment(
        wire=WireProtocol.OpenAiChat,
        endpoint=endpoint,
        auth=auth,
        default_model=resolved_deployment,
        preset_name="azure_openai",
    )
    logger.info(
        "llm.deployment.azure_openai.constructed",
        extra={
            "deployment_preset": "azure_openai",
            "resource": validated_resource,
            "deployment_name": resolved_deployment,
            "auth_strategy_kind": auth.auth_strategy_kind(),
            "endpoint_host": endpoint_host,
            "api_version": api_version,
        },
    )
    return deployment


def _register_and_attach_session_6_presets() -> None:
    """Register azure_openai + azure_entra, attach classmethods.

    `azure_entra` is exposed as `LlmDeployment.azure_entra(api_key=..., ...)`
    returning a bare AzureEntra auth (for composition with azure_openai),
    rather than an LlmDeployment -- matching the Rust SDK's Azure shape
    where auth and deployment are constructed separately.

    Replaces the `LlmDeployment.azure_openai` + `LlmDeployment.azure_entra`
    NotImplementedError stubs.
    """
    register_preset("azure_openai", azure_openai_preset)

    @classmethod  # type: ignore[misc]
    def azure_openai_cm(
        cls,
        resource_name: str,
        deployment_name: str,
        auth: AzureEntra,
        *,
        api_version: Optional[str] = None,
    ) -> LlmDeployment:
        return azure_openai_preset(
            resource_name,
            deployment_name,
            auth,
            api_version=api_version,
        )

    @classmethod  # type: ignore[misc]
    def azure_entra_cm(
        cls,
        *,
        api_key: Optional[str] = None,
        workload_identity: bool = False,
        managed_identity_client_id: Optional[str] = None,
    ) -> AzureEntra:
        return AzureEntra(
            api_key=api_key,
            workload_identity=workload_identity,
            managed_identity_client_id=managed_identity_client_id,
        )

    LlmDeployment.azure_openai = azure_openai_cm  # type: ignore[attr-defined]
    LlmDeployment.azure_entra = azure_entra_cm  # type: ignore[attr-defined]


_register_and_attach_session_6_presets()


# ---------------------------------------------------------------------------
# Compatible-endpoint presets — wrap an arbitrary HTTPS endpoint with a
# canonical wire protocol. Cross-SDK parity with kailash-rs PR #722
# (openai_compatible) and PR #724 (anthropic_compatible).
#
# Use cases: vLLM, llama.cpp servers, LM Studio remotes, LiteLLM proxies,
# OpenRouter Anthropic mode, internal gateways, third-party OpenAI/Anthropic-
# compatible providers. SSRF guard runs on `Endpoint.base_url` via the
# field validator in `deployment.py:129` (mode="before"), so loopback /
# private / link-local / cloud-metadata URLs are rejected at construction.
#
# `preset_name()` returns the literal `"openai_compatible"` /
# `"anthropic_compatible"` (NOT the host) per spec § 6.M2 — this prevents
# log-aggregator label cardinality blow-up and credential enumeration via
# observability (`rules/observability.md` § 8).
# ---------------------------------------------------------------------------


def openai_compatible_preset(
    base_url: str,
    api_key: str,
    *,
    path_prefix: str = "/v1",
) -> LlmDeployment:
    """OpenAI-compatible endpoint at a caller-provided base URL.

    Wire:     `OpenAiChat`
    Endpoint: caller-provided (e.g. `https://vllm.example.com`)
    Auth:     `Authorization: Bearer <api_key>` via
              `ApiKeyBearer(Authorization_Bearer)`

    Both `base_url` and `api_key` are REQUIRED non-empty strings. SSRF
    guard runs on `base_url` automatically via the `Endpoint` field
    validator — loopback / private / link-local / cloud-metadata /
    non-HTTP(S) URLs raise the appropriate typed error.

    Cross-SDK parity with kailash-rs `LlmDeployment::openai_compatible`
    (PR #722). The preset name on the constructed deployment is the
    literal `"openai_compatible"` — never the caller-provided host.
    """
    _validate_required_str(base_url, name="openai_compatible_preset.base_url")
    _validate_required_str(
        api_key,
        name="openai_compatible_preset.api_key",
        env_hint="OPENAI_COMPATIBLE_API_KEY",
    )

    endpoint = Endpoint(base_url=base_url, path_prefix=path_prefix)
    auth = ApiKeyBearer(
        kind=ApiKeyHeaderKind.Authorization_Bearer,
        key=ApiKey(api_key),
    )
    return LlmDeployment(
        wire=WireProtocol.OpenAiChat,
        endpoint=endpoint,
        auth=auth,
        default_model=None,
        preset_name="openai_compatible",
    )


def anthropic_compatible_preset(
    base_url: str,
    api_key: str,
    *,
    path_prefix: str = "/v1",
    anthropic_version: str = "2023-06-01",
) -> LlmDeployment:
    """Anthropic-compatible endpoint at a caller-provided base URL.

    Wire:     `AnthropicMessages`
    Endpoint: caller-provided (e.g. `https://anthropic-proxy.example.com`)
    Auth:     `X-Api-Key: <api_key>` via `ApiKeyBearer(X_Api_Key)`
    Headers:  `anthropic-version` on `Endpoint.required_headers` (default
              `"2023-06-01"`, override for proxies pinned to a different
              wire version)

    Both `base_url` and `api_key` are REQUIRED non-empty strings. SSRF
    guard runs on `base_url` automatically via the `Endpoint` field
    validator.

    Cross-SDK parity with kailash-rs `LlmDeployment::anthropic_compatible`
    (PR #724). The preset name on the constructed deployment is the
    literal `"anthropic_compatible"` — never the caller-provided host.
    """
    _validate_required_str(base_url, name="anthropic_compatible_preset.base_url")
    _validate_required_str(
        api_key,
        name="anthropic_compatible_preset.api_key",
        env_hint="ANTHROPIC_COMPATIBLE_API_KEY",
    )

    endpoint = Endpoint(
        base_url=base_url,
        path_prefix=path_prefix,
        required_headers={"anthropic-version": anthropic_version},
    )
    auth = ApiKeyBearer(kind=ApiKeyHeaderKind.X_Api_Key, key=ApiKey(api_key))
    return LlmDeployment(
        wire=WireProtocol.AnthropicMessages,
        endpoint=endpoint,
        auth=auth,
        default_model=None,
        preset_name="anthropic_compatible",
    )


def _attach_compatible_classmethods() -> None:
    """Register `openai_compatible` / `anthropic_compatible` AND attach as
    `LlmDeployment.<name>` classmethods. Mirrors the
    `_register_and_attach_session_*` pattern.
    """
    register_preset("openai_compatible", openai_compatible_preset)
    register_preset("anthropic_compatible", anthropic_compatible_preset)

    @classmethod  # type: ignore[misc]
    def openai_compatible(
        cls, base_url: str, api_key: str, **kwargs: Any
    ) -> LlmDeployment:
        return openai_compatible_preset(base_url, api_key, **kwargs)

    @classmethod  # type: ignore[misc]
    def anthropic_compatible(
        cls, base_url: str, api_key: str, **kwargs: Any
    ) -> LlmDeployment:
        return anthropic_compatible_preset(base_url, api_key, **kwargs)

    LlmDeployment.openai_compatible = openai_compatible  # type: ignore[attr-defined]
    LlmDeployment.anthropic_compatible = anthropic_compatible  # type: ignore[attr-defined]


_attach_compatible_classmethods()


# ---------------------------------------------------------------------------
# Session 7 (#764) — Bedrock region runtime override
# ---------------------------------------------------------------------------


def _attach_bedrock_region_classmethod() -> None:
    """Attach `LlmDeployment.register_bedrock_region` (#764).

    Wires :func:`kaizen.llm.auth.aws.register_bedrock_region` onto
    :class:`LlmDeployment` as a classmethod so the public API surface
    matches kailash-rs's ``LlmDeployment::register_bedrock_region`` and
    callers reach it via the same canonical path:

        kailash.LlmDeployment.register_bedrock_region("xx-newregion-1")
    """
    from kaizen.llm.auth.aws import register_bedrock_region as _register

    @classmethod  # type: ignore[misc]
    def register_bedrock_region(cls, region: str) -> None:
        _register(region)

    LlmDeployment.register_bedrock_region = register_bedrock_region  # type: ignore[attr-defined]


_attach_bedrock_region_classmethod()


# ---------------------------------------------------------------------------
# `<provider>_from_env` convenience presets (#791 — cross-SDK parity with the
# 12 zero-arg `pub fn <provider>() -> Self` classmethods on kailash-rs
# `LlmDeployment` at `crates/kailash-kaizen/src/llm/deployment/presets.rs`
# lines 153, 249, 346, 386, 408, 430, 458, 928, 964, 1000, 1036, 1072.
# ---------------------------------------------------------------------------
#
# Cross-SDK contract per `rules/cross-sdk-inspection.md` § 3 (EATP D6):
# semantics MUST match; idioms MAY differ.
#
# Rust exposes a *zero-arg* `pub fn openai() -> Self` that constructs an
# auth-less deployment with the canonical hosted URL; callers chain
# `.with_api_key(...)` to populate credentials before use. The Python idiom
# (`rules/env-models.md`) mandates eager validation: an `LlmDeployment`
# without a real api_key + model raises at construction. Reconciling the two
# without compromising either:
#
# Each `<provider>_from_env_preset()` factory:
#   1. Reads `<PROVIDER>_API_KEY` from the environment (raises
#      `MissingCredential("<PROVIDER>_API_KEY")` if absent / empty).
#   2. Reads `<PROVIDER>_PROD_MODEL` (canonical), falling back to
#      `<PROVIDER>_MODEL` (legacy compatibility with `from_env.py`'s
#      precedence chain), raising `MissingCredential` if neither is set.
#   3. Delegates to the existing parent `<provider>_preset(api_key, model)`
#      factory — same wire / endpoint / auth shape as the long-form, with
#      eager validation preserved through the parent's own checks.
#
# A user porting Rust code that calls `LlmDeployment::openai()` zero-arg
# transcribes it to Python as `LlmDeployment.openai_from_env()`, with a
# clear contract: API key + model come from environment variables exactly
# as `rules/env-models.md` mandates, and missing env vars raise a typed
# `MissingCredential` error rather than failing later at the provider 401.
#
# Registry name pattern: `<provider>_from_env` (parent + suffix), parallel
# to the `<provider>_default` pattern from #787. Capability-matrix lookup
# routes through the parent row automatically because the deployment's
# `preset_name` is the PARENT literal (`"openai"`, not `"openai_from_env"`).

# Canonical model-env precedence: PROD first (per parent factory docstrings),
# legacy short-form fallback (per `from_env.py::_call_preset_from_env`).
_FROM_ENV_PROVIDERS: list[tuple[str, str, tuple[str, ...]]] = [
    # (preset_name, api_key_env, (model_env_candidates_in_precedence_order))
    ("openai", "OPENAI_API_KEY", ("OPENAI_PROD_MODEL", "OPENAI_MODEL")),
    ("anthropic", "ANTHROPIC_API_KEY", ("ANTHROPIC_PROD_MODEL", "ANTHROPIC_MODEL")),
    # GOOGLE / GEMINI key-and-model env vars are interchangeable per
    # `rules/env-models.md`; precedence prefers the canonical GOOGLE_* name.
    (
        "google",
        "GOOGLE_API_KEY",
        ("GOOGLE_PROD_MODEL", "GOOGLE_MODEL", "GEMINI_PROD_MODEL", "GEMINI_MODEL"),
    ),
    ("cohere", "COHERE_API_KEY", ("COHERE_PROD_MODEL", "COHERE_MODEL")),
    ("mistral", "MISTRAL_API_KEY", ("MISTRAL_PROD_MODEL", "MISTRAL_MODEL")),
    ("perplexity", "PERPLEXITY_API_KEY", ("PERPLEXITY_PROD_MODEL", "PERPLEXITY_MODEL")),
    (
        "huggingface",
        "HUGGINGFACE_API_KEY",
        ("HUGGINGFACE_PROD_MODEL", "HUGGINGFACE_MODEL"),
    ),
    ("groq", "GROQ_API_KEY", ("GROQ_PROD_MODEL", "GROQ_MODEL")),
    ("together", "TOGETHER_API_KEY", ("TOGETHER_PROD_MODEL", "TOGETHER_MODEL")),
    ("fireworks", "FIREWORKS_API_KEY", ("FIREWORKS_PROD_MODEL", "FIREWORKS_MODEL")),
    ("openrouter", "OPENROUTER_API_KEY", ("OPENROUTER_PROD_MODEL", "OPENROUTER_MODEL")),
    ("deepseek", "DEEPSEEK_API_KEY", ("DEEPSEEK_PROD_MODEL", "DEEPSEEK_MODEL")),
]


def _read_first_env(*candidates: str) -> Optional[str]:
    """Return the first non-empty env var in precedence order, or None."""
    for var in candidates:
        val = os.environ.get(var, "").strip()
        if val:
            return val
    return None


def _resolve_from_env_credentials(
    *,
    preset: str,
    api_key_var: str,
    model_vars: tuple[str, ...],
) -> tuple[str, str]:
    """Read api_key + model from env or raise typed `MissingCredential`.

    `MissingCredential.source_hint` is a constant chosen by the loader (not
    user input), so the env var name is safe to embed verbatim and gives
    operators an actionable error message. Order of checks is api_key first
    so the operator fixes the most common omission (no key set) before
    diagnosing model selection.
    """
    api_key = _read_first_env(api_key_var)
    if api_key is None:
        raise MissingCredential(api_key_var)
    model = _read_first_env(*model_vars)
    if model is None:
        # Compose source_hint from the candidate list so the message is
        # actionable: "checked envelope: OPENAI_PROD_MODEL or OPENAI_MODEL".
        joined = " or ".join(model_vars)
        raise MissingCredential(joined)
    return api_key, model


def _from_env_factory_for(preset: str) -> Callable[[], LlmDeployment]:
    """Build the parameter-less factory for one provider's `_from_env` form.

    Closure captures `preset` so the factory ID is stable in stack traces
    and matches the registry name byte-for-byte.
    """
    # Resolve the entry once (linear scan acceptable: 12 entries).
    spec = next((s for s in _FROM_ENV_PROVIDERS if s[0] == preset), None)
    if spec is None:
        raise ValueError(f"_from_env_factory_for: unknown preset {preset!r}")
    _name, api_key_var, model_vars = spec
    parent_factory = get_preset(preset)

    def _factory() -> LlmDeployment:
        api_key, model = _resolve_from_env_credentials(
            preset=preset, api_key_var=api_key_var, model_vars=model_vars
        )
        return parent_factory(api_key, model=model)

    _factory.__name__ = f"{preset}_from_env_preset"
    _factory.__qualname__ = f"{preset}_from_env_preset"
    _factory.__doc__ = (
        f"Construct `{preset}_preset` from environment variables.\n\n"
        f"Reads {api_key_var} and the first non-empty value of "
        f"{', '.join(model_vars)} from `os.environ`. Raises typed "
        f"`MissingCredential` if either is unset / empty.\n\n"
        f"Cross-SDK parity with kailash-rs `LlmDeployment::{preset}()` "
        f"(zero-arg auth-less constructor at "
        f"`crates/kailash-kaizen/src/llm/deployment/presets.rs`). Per EATP "
        f"D6, the Python idiom-difference is the explicit `_from_env` "
        f"naming + eager validation; semantics match (same endpoint, wire "
        f"protocol, and auth strategy as the long-form `{preset}_preset`)."
    )
    return _factory


# Module-level binding for each `<provider>_from_env_preset` so callers can
# import the symbol directly:
#
#     from kaizen.llm.presets import openai_from_env_preset
#     dep = openai_from_env_preset()
#
# (Mirrors `<provider>_preset` and `<provider>_default_preset` precedent.)
openai_from_env_preset = _from_env_factory_for("openai")
anthropic_from_env_preset = _from_env_factory_for("anthropic")
google_from_env_preset = _from_env_factory_for("google")
cohere_from_env_preset = _from_env_factory_for("cohere")
mistral_from_env_preset = _from_env_factory_for("mistral")
perplexity_from_env_preset = _from_env_factory_for("perplexity")
huggingface_from_env_preset = _from_env_factory_for("huggingface")
groq_from_env_preset = _from_env_factory_for("groq")
together_from_env_preset = _from_env_factory_for("together")
fireworks_from_env_preset = _from_env_factory_for("fireworks")
openrouter_from_env_preset = _from_env_factory_for("openrouter")
deepseek_from_env_preset = _from_env_factory_for("deepseek")


def _register_and_attach_from_env_presets() -> None:
    """Register all 12 `_from_env` factories AND attach as `LlmDeployment.<name>_from_env`.

    Registry name is `<parent>_from_env` (parallel to `<parent>_default`).
    The deployment's `preset_name` is the PARENT literal (`"openai"`, not
    `"openai_from_env"`) because the parent factory sets it; capability-
    matrix lookup therefore routes through the parent row.

    Both surfaces (registry round-trip + classmethod) MUST be installed
    atomically per the precedent in `_register_and_attach_session_2_presets`
    so a preset that is registered but not attached (or vice versa) is
    structurally impossible.
    """
    factory_table = [
        ("openai_from_env", openai_from_env_preset),
        ("anthropic_from_env", anthropic_from_env_preset),
        ("google_from_env", google_from_env_preset),
        ("cohere_from_env", cohere_from_env_preset),
        ("mistral_from_env", mistral_from_env_preset),
        ("perplexity_from_env", perplexity_from_env_preset),
        ("huggingface_from_env", huggingface_from_env_preset),
        ("groq_from_env", groq_from_env_preset),
        ("together_from_env", together_from_env_preset),
        ("fireworks_from_env", fireworks_from_env_preset),
        ("openrouter_from_env", openrouter_from_env_preset),
        ("deepseek_from_env", deepseek_from_env_preset),
    ]

    for name, factory in factory_table:
        register_preset(name, factory)

        # Bind factory via a default-arg closure so each classmethod
        # captures its own factory reference (standard Python closure
        # pitfall workaround — same shape as `_register_and_attach_session_2_presets`).
        def _from_env_cm(cls, _factory=factory) -> LlmDeployment:
            return _factory()

        _from_env_cm.__name__ = name
        _from_env_cm.__qualname__ = f"LlmDeployment.{name}"
        setattr(LlmDeployment, name, classmethod(_from_env_cm))


_register_and_attach_from_env_presets()


__all__ = [
    # S1
    "openai_preset",
    "register_preset",
    "get_preset",
    "list_presets",
    # S3 — direct providers
    "anthropic_preset",
    "google_preset",
    "cohere_preset",
    "mistral_preset",
    "perplexity_preset",
    "huggingface_preset",
    "huggingface_chat_preset",
    "ollama_preset",
    "docker_model_runner_preset",
    "groq_preset",
    "together_preset",
    "fireworks_preset",
    "openrouter_preset",
    "deepseek_preset",
    "lm_studio_preset",
    "llama_cpp_preset",
    # S4a -- Bedrock Claude
    "bedrock_claude_preset",
    # S4b-ii -- Bedrock non-Claude families
    "bedrock_llama_preset",
    "bedrock_titan_preset",
    "bedrock_mistral_preset",
    "bedrock_cohere_preset",
    # S5 -- Vertex AI presets
    "vertex_claude_preset",
    "vertex_gemini_preset",
    # S6 -- Azure OpenAI
    "azure_openai_preset",
    # S7 -- Compatible-endpoint presets (#761, #762)
    "openai_compatible_preset",
    "anthropic_compatible_preset",
    # S7b -- Default-URL convenience presets (#787, cross-SDK parity)
    "ollama_default_preset",
    "lm_studio_default_preset",
    "llama_cpp_default_preset",
    "docker_model_runner_default_preset",
    # S7c -- _from_env convenience presets (#791, cross-SDK parity with the
    # 12 zero-arg `pub fn <provider>() -> Self` constructors on kailash-rs
    # `LlmDeployment`).
    "openai_from_env_preset",
    "anthropic_from_env_preset",
    "google_from_env_preset",
    "cohere_from_env_preset",
    "mistral_from_env_preset",
    "perplexity_from_env_preset",
    "huggingface_from_env_preset",
    "groq_from_env_preset",
    "together_from_env_preset",
    "fireworks_from_env_preset",
    "openrouter_from_env_preset",
    "deepseek_from_env_preset",
]
