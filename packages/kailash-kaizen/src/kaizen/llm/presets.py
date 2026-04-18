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
from typing import Any, Callable, Dict

from kaizen.llm.auth.aws import AwsBearerToken
from kaizen.llm.auth.bearer import ApiKey, ApiKeyBearer, ApiKeyHeaderKind, StaticNone
from kaizen.llm.deployment import Endpoint, LlmDeployment, WireProtocol
from kaizen.llm.errors import ModelRequired
from kaizen.llm.grammar.bedrock import (
    BedrockClaudeGrammar,
    BedrockCohereGrammar,
    BedrockLlamaGrammar,
    BedrockMistralGrammar,
    BedrockTitanGrammar,
)

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
]
