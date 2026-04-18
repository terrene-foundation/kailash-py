# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Four-axis LLM deployment abstraction — Pydantic v2 frozen models.

Implements ADR-0001 D1-D5 for Session 1: the foundation types. Presets for
specific providers live in `presets.py`; only `LlmDeployment.openai(...)` is
wired this session. Every other preset classmethod raises `NotImplementedError`
with "Implemented in session N (SK)" so orphan detection can grep them.

Cross-SDK parity rules:

* `WireProtocol` member names byte-match the Rust `WireProtocol` variants
  (string-compared in `tests/cross_sdk_parity/` once S9 lands).
* Field names on `ResolvedModel`, `Endpoint`, `CompletionRequest`,
  `StreamingConfig`, `RetryConfig`, `LlmDeployment` track the Rust structs
  in `kailash-rs/crates/kaizen/src/llm/deployment.rs`.

Invariants enforced at type level:

* `frozen=True` + `extra='forbid'` on every model — no field writes after
  construction, no silent acceptance of unknown fields.
* `Endpoint.base_url` routes through `url_safety.check_url()` before the
  model is finalized; validation failures raise `InvalidEndpoint` which is a
  typed `LlmClientError`.
* `ResolvedModel.with_extra_header(name, ...)` rejects the 7 forbidden header
  names case-insensitively — any of these would let the caller override the
  auth / routing layer installed by the deployment.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, ClassVar, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from kaizen.llm.auth import AuthStrategy
from kaizen.llm.url_safety import check_url

# `AuthStrategy` is a typing Protocol — Pydantic cannot validate a Protocol
# at the model level, so `LlmDeployment.auth` is typed as `Any` and the
# constraint is enforced by the preset classmethods.


# ---------------------------------------------------------------------------
# WireProtocol
# ---------------------------------------------------------------------------


class WireProtocol(str, Enum):
    """Selects the on-the-wire request/response schema for a deployment.

    Member names byte-match the Rust `WireProtocol` variants. Do NOT rename
    without a coordinated cross-SDK change — the parity test in S9 compares
    member name strings.
    """

    OpenAiChat = "OpenAiChat"
    OpenAiCompletions = "OpenAiCompletions"
    AnthropicMessages = "AnthropicMessages"
    GoogleGenerateContent = "GoogleGenerateContent"
    BedrockInvoke = "BedrockInvoke"
    VertexGenerateContent = "VertexGenerateContent"
    AzureOpenAi = "AzureOpenAi"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


class Endpoint(BaseModel):
    """Base URL + routing fragments for an LLM deployment."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    base_url: HttpUrl
    path_prefix: str = ""
    required_headers: Dict[str, str] = Field(default_factory=dict)
    query_params: Dict[str, str] = Field(default_factory=dict)

    @field_validator("base_url", mode="after")
    @classmethod
    def _validate_base_url(cls, v: HttpUrl) -> HttpUrl:
        """Route every `base_url` through the SSRF guard before accepting."""
        check_url(str(v))
        return v


# ---------------------------------------------------------------------------
# ResolvedModel
# ---------------------------------------------------------------------------


# Headers a caller MUST NOT install via `with_extra_header`. Case-insensitive.
# Source: ADR-0001 D1. These are precisely the headers that carry auth,
# routing, or API-version identity — letting a caller override them from the
# "extra" surface would silently defeat the deployment's contract.
_FORBIDDEN_EXTRA_HEADERS = frozenset(
    {
        "authorization",
        "host",
        "cookie",
        "x-amz-security-token",
        "x-api-key",
        "x-goog-api-key",
        "anthropic-version",
    }
)


class ResolvedModel(BaseModel):
    """Concrete model selection + per-request header / query overrides."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    name: str
    extra_headers: Dict[str, str] = Field(default_factory=dict)
    extra_query: Dict[str, str] = Field(default_factory=dict)

    def with_extra_header(self, name: str, value: str) -> "ResolvedModel":
        """Return a copy with one additional header.

        Rejects the 7 forbidden header names case-insensitively. The raw
        header name does NOT appear in the error message (log-injection
        defense); the caller receives a stable error code and must audit
        their code path.
        """
        if not isinstance(name, str) or not isinstance(value, str):
            raise TypeError("extra header name and value must both be str")
        lowered = name.lower()
        if lowered in _FORBIDDEN_EXTRA_HEADERS:
            raise ValueError(
                "header name is reserved by the deployment layer; "
                "refusing to accept it as an extra header"
            )
        new_headers = dict(self.extra_headers)
        new_headers[name] = value
        return ResolvedModel(
            name=self.name,
            extra_headers=new_headers,
            extra_query=self.extra_query,
        )


# ---------------------------------------------------------------------------
# Configuration fragments
# ---------------------------------------------------------------------------


class EmbedOptions(BaseModel):
    """Optional parameters for an embedding request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimensions: Optional[int] = None
    user: Optional[str] = None


class CompletionRequest(BaseModel):
    """Minimal shared-shape completion request.

    Field names mirror the Rust struct; concrete wire adapters translate to
    each provider's schema. Session 1 ships the shape; wiring to real chat
    completion lands in S2 (OpenAI) and subsequent sessions.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str
    messages: list[dict[str, Any]]
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    stop: Optional[list[str]] = None
    stream: bool = False
    user: Optional[str] = None


class StreamingConfig(BaseModel):
    """Streaming behaviour per deployment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = True
    include_usage: bool = True


class RetryConfig(BaseModel):
    """Retry policy per deployment (backoff + cap)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_attempts: int = 3
    initial_backoff_ms: int = 100
    max_backoff_ms: int = 10_000
    multiplier: float = 2.0


# ---------------------------------------------------------------------------
# LlmDeployment
# ---------------------------------------------------------------------------


class LlmDeployment(BaseModel):
    """Immutable four-axis description of an LLM deployment.

    Axes:
      1. `wire`       — WireProtocol enum
      2. `endpoint`   — Endpoint (base_url + path_prefix + ...)
      3. `auth`       — AuthStrategy (Protocol; typed `Any` for Pydantic)
      4. model axis   — `default_model` + per-request `ResolvedModel`s

    Plus two pieces of operational config (streaming, retry).

    Construction: prefer the preset classmethods (`.openai`, `.anthropic`,
    `.bedrock_claude`, etc.) over manual assembly — they wire the right
    defaults and the right auth strategy for each provider. Manual
    construction is permitted but is the power-user path.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    wire: WireProtocol
    endpoint: Endpoint
    auth: Any  # AuthStrategy Protocol; validated at preset construction
    default_model: Optional[str] = None
    streaming: StreamingConfig = Field(default_factory=StreamingConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)

    # -------------------------------------------------------------
    # Preset classmethod STUBS — only `.openai` is implemented in S1+S2.
    # Every other preset raises NotImplementedError with the session
    # marker so `rules/zero-tolerance.md` Rule 2's "iterative TODOs"
    # clause applies (each stub references a named follow-up session).
    # -------------------------------------------------------------

    # Marker messages for each deferred preset; pinned so `grep
    # "Implemented in session"` surfaces the full list at audit time.
    _NOT_YET_IMPLEMENTED: ClassVar[Dict[str, str]] = {
        "anthropic": "Implemented in session 2 (S3)",
        "google": "Implemented in session 2 (S3)",
        "bedrock_claude": "Implemented in session 3 (S4a)",
        "bedrock_llama": "Implemented in session 4 (S4b-ii)",
        "bedrock_titan": "Implemented in session 4 (S4b-ii)",
        "bedrock_mistral": "Implemented in session 4 (S4b-ii)",
        "azure_openai": "Implemented in session 5 (S5)",
        "azure_entra": "Implemented in session 6 (S6)",
        "vertex_gemini": "Implemented in session 6 (S6)",
    }

    # `openai` preset is defined in `presets.py` via runtime attachment
    # to avoid a circular import (presets depend on LlmDeployment).

    @classmethod
    def anthropic(cls, *args: Any, **kwargs: Any) -> "LlmDeployment":
        raise NotImplementedError(cls._NOT_YET_IMPLEMENTED["anthropic"])

    @classmethod
    def google(cls, *args: Any, **kwargs: Any) -> "LlmDeployment":
        raise NotImplementedError(cls._NOT_YET_IMPLEMENTED["google"])

    @classmethod
    def bedrock_claude(cls, *args: Any, **kwargs: Any) -> "LlmDeployment":
        raise NotImplementedError(cls._NOT_YET_IMPLEMENTED["bedrock_claude"])

    @classmethod
    def bedrock_llama(cls, *args: Any, **kwargs: Any) -> "LlmDeployment":
        raise NotImplementedError(cls._NOT_YET_IMPLEMENTED["bedrock_llama"])

    @classmethod
    def bedrock_titan(cls, *args: Any, **kwargs: Any) -> "LlmDeployment":
        raise NotImplementedError(cls._NOT_YET_IMPLEMENTED["bedrock_titan"])

    @classmethod
    def bedrock_mistral(cls, *args: Any, **kwargs: Any) -> "LlmDeployment":
        raise NotImplementedError(cls._NOT_YET_IMPLEMENTED["bedrock_mistral"])

    @classmethod
    def azure_openai(cls, *args: Any, **kwargs: Any) -> "LlmDeployment":
        raise NotImplementedError(cls._NOT_YET_IMPLEMENTED["azure_openai"])

    @classmethod
    def azure_entra(cls, *args: Any, **kwargs: Any) -> "LlmDeployment":
        raise NotImplementedError(cls._NOT_YET_IMPLEMENTED["azure_entra"])

    @classmethod
    def vertex_gemini(cls, *args: Any, **kwargs: Any) -> "LlmDeployment":
        raise NotImplementedError(cls._NOT_YET_IMPLEMENTED["vertex_gemini"])


__all__ = [
    "WireProtocol",
    "Endpoint",
    "ResolvedModel",
    "EmbedOptions",
    "CompletionRequest",
    "StreamingConfig",
    "RetryConfig",
    "LlmDeployment",
]
