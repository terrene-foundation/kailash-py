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

import hashlib
import logging
import re
from typing import Any, Callable, Dict, Optional

from kaizen.llm.auth.aws import AwsBearerToken
from kaizen.llm.auth.bearer import ApiKey, ApiKeyBearer, ApiKeyHeaderKind, StaticNone
from kaizen.llm.auth.gcp import GcpOauth
from kaizen.llm.deployment import Endpoint, LlmDeployment, WireProtocol
from kaizen.llm.errors import ModelRequired
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
    ``format_record_id_for_event``)."""
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:8]


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


def get_preset(name: str) -> Callable[..., LlmDeployment]:
    """Retrieve a preset factory by name. Validates the name first."""
    validated = _validate_preset_name(name)
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
    )


register_preset("openai", openai_preset)


# ---------------------------------------------------------------------------
# Attach presets as classmethods on LlmDeployment
# ---------------------------------------------------------------------------


def _attach_openai_classmethod() -> None:
    """Wire `openai_preset` onto `LlmDeployment.openai`.

    The LlmDeployment class already declares stubs for every other preset
    (they raise NotImplementedError with the session marker). Session 1
    replaces the `openai` entry only; subsequent sessions add their own.
    """

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
    )


def cohere_preset(
    api_key: str,
    model: str,
    *,
    base_url: str = "https://api.cohere.com",
    path_prefix: str = "/v1",
) -> LlmDeployment:
    """Cohere Generate API.

    Wire:     `CohereGenerate`
    Endpoint: `https://api.cohere.com/v1`
    Auth:     `Authorization: Bearer <key>`
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
    )


def huggingface_preset(
    api_key: str,
    model: str,
    *,
    base_url: str = "https://api-inference.huggingface.co",
    path_prefix: str = "",
) -> LlmDeployment:
    """HuggingFace Inference API.

    Wire:     `HuggingFaceInference`
    Endpoint: `https://api-inference.huggingface.co`
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
    """Validate a GCP region against the strict allowlist regex."""
    if not isinstance(region, str) or not region:
        raise ValueError(
            "vertex preset requires a non-empty region string "
            "(e.g. 'us-central1', 'europe-west4')"
        )
    if not _REGION_RE.match(region):
        raise ValueError(
            "vertex region failed validation against "
            f"^[a-z]{{2,20}}-[a-z]+\\d{{1,2}}$ "
            f"(region_fingerprint={_fingerprint(region)})"
        )
    return region


def _build_vertex_deployment(
    *,
    preset_name: str,
    publisher: str,
    service_account_key: dict | str,
    project: str,
    region: str,
    model: str,
    env_hint: str,
    grammar: Any,
    wire: WireProtocol,
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
    endpoint_host = f"{validated_region}-aiplatform.googleapis.com"
    # The Vertex URL embeds the model in the path (`:rawPredict` for
    # Anthropic-on-Vertex, `:streamGenerateContent` for Gemini -- but
    # we use `:rawPredict` for Gemini too, since the Vertex Gemini
    # path matches the Rust SDK's choice and supports both raw + stream
    # via the same endpoint with a query flag). path_prefix carries the
    # full project/location/publisher/model path; the wire adapter
    # appends `:rawPredict` at completion time.
    path_prefix = (
        f"/v1/projects/{validated_project}/locations/{validated_region}"
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
    service_account_key: dict | str,
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
    )


def vertex_gemini_preset(
    service_account_key: dict | str,
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
    )
    deployment = LlmDeployment(
        wire=WireProtocol.OpenAiChat,
        endpoint=endpoint,
        auth=auth,
        default_model=resolved_deployment,
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
]
