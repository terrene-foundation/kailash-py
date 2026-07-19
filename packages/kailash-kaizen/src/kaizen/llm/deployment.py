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
from typing import Any, ClassVar, Dict, Optional, Union
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from kaizen.llm.auth import AuthStrategy
from kaizen.llm.errors import InvalidEndpoint
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
    # Session 2 (S3) — direct providers with distinct wire schemas.
    # Member names byte-match the Rust `WireProtocol` variants; changing
    # them requires a coordinated cross-SDK edit + parity fixture update.
    CohereGenerate = "CohereGenerate"
    MistralChat = "MistralChat"
    OllamaNative = "OllamaNative"
    HuggingFaceInference = "HuggingFaceInference"


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

    @field_validator("base_url", mode="before")
    @classmethod
    def _validate_base_url(cls, v: Any) -> Any:
        """Route every `base_url` through the SSRF guard BEFORE Pydantic normalises.

        `mode="before"` means `check_url` sees the raw string the caller
        supplied, not Pydantic's `HttpUrl`-normalised form (which strips
        default paths, canonicalises IDN, and re-encodes percent sequences).
        A future Pydantic normalisation bug, or any urlparse divergence
        between the raw and normalised views, would otherwise leave an
        unaudited surface between `check_url`'s view and what the HTTP
        client actually sees. Round-1 redteam M2.

        Additionally rejects non-ASCII hostnames at the raw-string level to
        defeat IDN homograph attacks (e.g. Cyrillic `а` in "api.opеnai.com"):
        Pydantic would happily punycode-encode and pass the host to
        `check_url`, which sees only the ASCII punycode and has no way to
        detect the confusable. Rejecting at the raw layer is the only place
        the Unicode form is still visible.
        """
        if isinstance(v, str):
            # ASCII-host check runs FIRST so a non-resolving IDN reject comes
            # through as `malformed_url` (homograph-defense intent) rather
            # than `resolution_failed` (which looks like a transient error).
            try:
                parsed = urlparse(v)
            except Exception:
                raise InvalidEndpoint("malformed_url", raw_url=v)
            host = parsed.hostname or ""
            try:
                host.encode("ascii")
            except UnicodeEncodeError:
                raise InvalidEndpoint("malformed_url", raw_url=v)
            check_url(v)
        return v


# ---------------------------------------------------------------------------
# ResolvedModel
# ---------------------------------------------------------------------------


# Headers a caller MUST NOT install via `with_extra_header`. Case-insensitive;
# the caller's name is `.strip().lower()`-normalised before lookup so
# leading/trailing whitespace (" Authorization", "Authorization\t") cannot
# bypass the check. Source: ADR-0001 D1 + round-1 redteam H2.
_FORBIDDEN_EXTRA_HEADERS = frozenset(
    {
        # Auth / routing / version (original D1 set)
        "authorization",
        "host",
        "cookie",
        "x-amz-security-token",
        "x-api-key",
        "x-goog-api-key",
        "anthropic-version",
        # HTTP request-smuggling primitives. Transfer-Encoding + Content-Length
        # desync between the client and upstream proxy is the classical
        # request-smuggling vector; both must be controlled by the HTTP
        # library, not the caller.
        "transfer-encoding",
        "content-length",
        # Proxy-level auth. Proxy-Authorization installs a second credential
        # against an intermediate proxy; Proxy-Authenticate is its response
        # counterpart. Either in "extras" is an egress-integration risk.
        "proxy-authorization",
        "proxy-authenticate",
        # Upstream-trust / client-IP spoofing. If the provider or any
        # intermediate layer trusts these for tenant isolation or per-IP rate
        # limiting, the caller can forge the source IP and defeat both.
        "x-forwarded-for",
        "x-real-ip",
        "forwarded",
        # HTTP method override — lets a POST masquerade as DELETE against
        # Rails/Django-style providers that honour the header.
        "x-http-method-override",
        "x-http-method",
        "x-method-override",
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

        Rejects the forbidden header names case-insensitively AND
        whitespace-insensitively — `.strip().lower()` runs before the
        allowlist lookup so `" Authorization"`, `"Authorization\\t"`, and
        `"Authorization "` all reject. Downstream HTTP libraries
        (httpx, requests) may normalise header names but not all consumers
        do; normalising here is the only structural defense. Round-1
        redteam H2.

        The raw header name does NOT appear in the error message
        (log-injection defense); the caller receives a stable error code
        and must audit their code path.
        """
        if not isinstance(name, str) or not isinstance(value, str):
            raise TypeError("extra header name and value must both be str")
        # Whitespace-strip + case-fold before allowlist lookup. The ORIGINAL
        # user-supplied `name` is stored unmodified in extra_headers because
        # the HTTP layer may treat "X-Custom-Trace" and "x-custom-trace" as
        # distinct dict keys in non-normalising consumers.
        normalised = name.strip().lower()
        if not normalised:
            raise ValueError("extra header name must not be empty / whitespace-only")
        if normalised in _FORBIDDEN_EXTRA_HEADERS:
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
    # #1720 Wave-1a additive embed-parity fields (legacy providers/llm parity).
    # Cohere v3 embed REQUIRES an input_type; HuggingFace feature-extraction takes
    # a unit-normalization toggle. Both default None => byte-identical to today for
    # every embed wire that does not consume them.
    input_type: Optional[str] = None
    normalize: Optional[bool] = None


class CompletionRequest(BaseModel):
    """Minimal shared-shape completion request.

    The base field names mirror the Rust struct; concrete wire adapters
    translate to each provider's schema. The #1720 Wave-1a additive fields
    below are sourced from the legacy ``providers/llm/`` layer (Python-side)
    and are NOT asserted to already exist on the Rust struct — cross-SDK
    field-shape parity for them is a Wave-1b lockstep concern (tracked with
    the per-adapter emission), not a Wave-1a claim. Session 1 shipped the
    shape; the real chat completion send path landed in #1717 (OpenAI +
    platform-Anthropic +
    Bedrock/Vertex/Google/Cohere/Mistral/Ollama/HF).

    The #1720 Wave-1a additive fields below carry agent-facing capabilities
    (tool-calling, structured output, extended sampling) that the legacy
    ``providers/llm/`` layer already has. EVERY new field defaults to ``None``
    (or the pre-existing default) so a request that sets none of them shapes
    a payload BYTE-IDENTICAL to the pre-#1720 output for every wire — the
    additive-neutrality invariant the wave-1a pin tests enforce. The per-wire
    ``build_request_payload`` shapers (Wave 1b) translate a SET field into the
    provider's native shape; an UNSET field is never emitted.

    ``api_key`` is deliberately NOT a field here: the request model is the
    cross-SDK byte pre-image and must carry no per-call credential. Per-request
    BYOK threads through ``complete()``/``stream()`` into the auth headers
    (Wave 1b byok shard), never into this pre-image.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str
    # #1859 provider-API param-compatibility hint. The CANONICAL model FAMILY
    # this request targets — used ONLY for provider-side parameter compatibility
    # (reasoning-model sampling-param filtering + the
    # ``max_tokens``/``max_completion_tokens`` field selection), NEVER emitted on
    # the wire. Set when ``model`` is a routing ALIAS that does not name the
    # model family: the canonical case is an Azure OpenAI deployment whose name
    # is caller-chosen (e.g. ``"my-gpt5-deploy"`` for a gpt-5 deployment). Azure
    # requires the deployment NAME in the URL / wire ``model`` field, but
    # reasoning-model detection must key off the FAMILY (``"gpt-5"``) or the
    # reasoning-param strip is skipped and Azure returns 400 ``unsupported_value``.
    # ``None`` (the default) => detection falls back to ``model``, byte-identical
    # to pre-#1859 for every direct provider whose ``model`` already IS the family.
    canonical_model: Optional[str] = None
    messages: list[dict[str, Any]]
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    stop: Optional[list[str]] = None
    stream: bool = False
    user: Optional[str] = None
    # --- #1720 Wave-1a additive completion-parity fields (all default None) ---
    # Tool / function calling: OpenAI function-schema list, verbatim passthrough.
    tools: Optional[list[dict[str, Any]]] = None
    # 'auto' | 'required' | 'none' | provider forced-tool dict. Only emitted when
    # tools is set; wire shapers preserve legacy "required"-when-tools semantics.
    tool_choice: Optional[Union[str, dict[str, Any]]] = None
    # Structured output: OpenAI-native {"type": "json_object"} or
    # {"type": "json_schema", "json_schema": {...}}; wires translate per provider.
    response_format: Optional[dict[str, Any]] = None
    # Extended sampling (legacy openai.py parity).
    seed: Optional[int] = None
    logit_bias: Optional[dict[str, float]] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    n: Optional[int] = None
    # top_k: Anthropic/Google/Cohere/Mistral/Ollama families (not emitted by OpenAI).
    top_k: Optional[int] = None


class StreamingConfig(BaseModel):
    """Streaming behaviour per deployment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = True
    include_usage: bool = True


class CompletionRouting(BaseModel):
    """Per-deployment completion-path routing + platform body transform.

    Carries the wire-specific pieces that CANNOT be derived from the
    ``WireProtocol`` enum alone because SEVERAL presets share one wire but
    route differently. The canonical example: ``bedrock_claude``,
    ``vertex_claude`` and Anthropic-direct ALL use
    ``WireProtocol.AnthropicMessages`` yet each needs a different URL suffix
    (``/model/{model}/invoke`` vs ``:rawPredict`` vs ``/messages``) and a
    different body shape (Bedrock / Vertex strip ``model`` and inject an
    ``anthropic_version``; direct keeps ``model`` untouched).

    Fields:

    * ``path_template`` — non-streaming URL suffix appended after
      ``base_url`` + ``path_prefix``. ``{model}`` is substituted with the
      deployment's resolved model id. A template beginning with ``:`` (e.g.
      ``:rawPredict``) is appended WITHOUT a ``/`` separator so it attaches
      to a model-carrying ``path_prefix`` (``.../models/{model}`` +
      ``:rawPredict``); any other template is joined with a single ``/``.
    * ``streaming_path_template`` — the streaming variant (``:streamRawPredict``,
      ``/model/{model}/invoke-with-response-stream``). Falls back to
      ``path_template`` when ``None``.
    * ``anthropic_version_body`` — when set (``"vertex-2023-10-16"`` /
      ``"bedrock-2023-05-31"``), the completion path strips ``model`` from
      the Anthropic body and inserts ``anthropic_version``. Left ``None`` for
      Anthropic-direct so its body stays byte-identical to the pre-#1717
      output.
    * ``use_chat_schema`` — routing discriminator for wires that expose BOTH a
      classic text-generation schema AND an OpenAI-compatible chat schema on
      different URLs (HuggingFace: classic ``/models/{model}`` vs the router's
      ``/v1/chat/completions``). ``False`` (default) keeps the classic body
      shape; ``True`` selects the chat body (``model`` + ``messages`` +
      ``tools``/``tool_choice``) that TGI / Inference-Endpoint chat servers
      accept. Like ``anthropic_version_body``, this drives a per-deployment
      body transform from a typed config field the caller sets by choosing a
      preset (``huggingface_chat_preset``), NOT keyword-matching on user input
      (``rules/agent-reasoning.md``). The client passes it to the HuggingFace
      shaper's ``build_request_payload(..., use_chat_schema=...)``; it is a
      no-op for every other wire (whose shapers do not accept the kwarg).

    Cross-SDK parity: the routing pieces mirror the Rust adapter's per-preset
    URL + platform-body handling; a fixed deployment produces the same URL +
    body bytes on both SDKs.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    path_template: Optional[str] = None
    streaming_path_template: Optional[str] = None
    anthropic_version_body: Optional[str] = None
    use_chat_schema: bool = False


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
    canonical_model: Optional[str] = None
    """#1859 canonical model FAMILY for provider-API param compatibility.

    ``default_model`` is the value sent on the wire / interpolated into the URL;
    for Azure OpenAI that is the caller-chosen DEPLOYMENT NAME (a routing alias),
    NOT the model family. ``canonical_model`` carries the family
    (``"gpt-5"`` / ``"o1"`` / …) so the reasoning-model sampling-param filter and
    the ``max_tokens``/``max_completion_tokens`` field selection key off the
    family — a gpt-5 deployment named ``"my-gpt5-deploy"`` still gets its
    reasoning params stripped instead of taking a 400 ``unsupported_value``.
    ``None`` (the default, every direct provider whose ``default_model`` already
    IS the family) => detection falls back to ``default_model``/``request.model``,
    byte-identical to pre-#1859. Threaded onto the request as
    ``CompletionRequest.canonical_model`` by ``LlmClient._prepare_completion``.
    """
    streaming: StreamingConfig = Field(default_factory=StreamingConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    completion_routing: Optional[CompletionRouting] = None
    """Per-deployment completion URL + platform-body routing.

    ``None`` for presets whose completion path is fully determined by their
    ``wire`` (OpenAI, Anthropic-direct, Cohere, Mistral, Ollama, HF, Google-
    direct — the ``_COMPLETE_DISPATCH`` default templates cover them). Set by
    presets that share a wire with a differently-routed sibling
    (``vertex_claude`` / ``vertex_gemini`` / ``bedrock_*``): it disambiguates
    the URL suffix and, for platform-hosted Anthropic, drives the
    strip-``model`` / inject-``anthropic_version`` body transform.
    """
    preset_name: Optional[str] = None
    """Canonical preset literal (e.g. ``"openai"``, ``"openai_compatible"``).

    Set by every preset factory to the literal registered in ``_PRESETS``.
    Manual constructions leave it ``None``. The literal — NOT the host or
    any caller-supplied URL fragment — prevents log-aggregator label
    cardinality blow-up and credential enumeration via observability per
    ``rules/observability.md`` § 8 (schema-revealing field names) and
    cross-SDK parity with kailash-rs ``LlmDeployment::preset_name()``.
    Python idiom is field access (``dep.preset_name``) rather than the
    Rust method-style ``dep.preset_name()``.
    """

    # -------------------------------------------------------------
    # Preset classmethod STUBS — only `.openai` is implemented in S1+S2.
    # Every other preset raises NotImplementedError with the session
    # marker so `rules/zero-tolerance.md` Rule 2's "iterative TODOs"
    # clause applies (each stub references a named follow-up session).
    # -------------------------------------------------------------

    # Marker messages for each deferred preset; pinned so `grep
    # "Implemented in session"` surfaces the full list at audit time.
    # `bedrock_claude` moved out of this dict in Session 3 (S4a) and is
    # now wired via `presets.py` runtime attachment. `bedrock_llama`,
    # `bedrock_titan`, `bedrock_mistral`, `bedrock_cohere` follow the
    # same pattern in Session 4 (S4b-ii). `vertex_claude` and
    # `vertex_gemini` follow the same pattern in Session 5 (S5).
    _NOT_YET_IMPLEMENTED: ClassVar[Dict[str, str]] = {}

    # `openai` preset is defined in `presets.py` via runtime attachment
    # to avoid a circular import (presets depend on LlmDeployment).
    # Session 2 (S3) also attaches 15 direct-provider presets via
    # `presets.py` runtime attachment: anthropic, google, cohere,
    # mistral, perplexity, huggingface, ollama, docker_model_runner,
    # groq, together, fireworks, openrouter, deepseek, lm_studio,
    # llama_cpp. Session 3 (S4a) attaches bedrock_claude. Session 4
    # (S4b-ii) attaches bedrock_llama / bedrock_titan / bedrock_mistral
    # / bedrock_cohere.

    # azure_openai and azure_entra are attached by presets.py at import time
    # (Session 6). No stubs remain on LlmDeployment after S6.

    def supports(self) -> Dict[str, bool]:
        """Return the capability matrix for this deployment (#763).

        Returns a dict with five boolean keys: ``tools``, ``vision``,
        ``batch``, ``caching``, ``audio``. Per-preset values are derived
        from current provider documentation at release time. The matrix
        is coarse — it reports what the deployment's wire protocol +
        endpoint surface CAN carry, NOT what every model served by the
        preset will accept (per-model gating like ``gpt-4o`` supports
        vision but ``gpt-3.5-turbo`` does not is the caller's
        responsibility, typically wired through model registry metadata).

        .. warning::

           This matrix reports the **provider / wire-protocol** capability
           (for cross-SDK negotiation) — NOT necessarily what this SDK's
           four-axis ``LlmClient.complete()`` / ``stream()`` EMITS on a given
           wire. As of #1720 the ``CompletionRequest`` SHAPE carries the
           additive fields (``tools``, ``tool_choice``, ``response_format``,
           ``seed``, ``logit_bias``, ``frequency_penalty``, ``presence_penalty``,
           ``n``, ``top_k``), and per-wire EMISSION + tool_call PARSE is LIVE
           (Wave 1b) for OpenAI/Anthropic/Google/Mistral/Cohere/Ollama; each
           wire emits only the fields that provider supports (unsupported ones
           are omitted, never faked). Emission for the remaining wires
           (Bedrock-native families, HuggingFace) is a later Wave-1b shard. So
           ``supports()["tools"] is True`` means "the provider supports
           tool-calling", NOT necessarily "``complete()`` will send tools on
           THIS wire yet" — check the wire against the Wave-1b rollout.

        Fail-closed default (``rules/security.md`` § Fail-Closed Security
        Defaults): manual constructions whose ``preset_name`` is ``None``
        AND any unknown / future preset name return all-False. Adding a
        new preset constructor without wiring its capability row in
        :mod:`kaizen.llm.capabilities` leaves the deployment marked
        uncapable until the wiring lands.

        Returned dicts are independent copies — mutating one does not
        mutate the matrix table or any other call's result.

        Example::

            dep = LlmDeployment.openai(api_key, model=os.environ["OPENAI_PROD_MODEL"])
            caps = dep.supports()
            if caps["batch"]:
                ...  # caller can opt into the OpenAI Batch API

        Cross-SDK parity: rows are byte-identical to kailash-rs
        ``LlmDeployment::supports()`` per
        ``rules/cross-sdk-inspection.md`` § 3a.
        """
        # Local import: presets.py + capabilities.py both import deployment.py;
        # importing capabilities.py at module scope here would be fine (no
        # cycle), but a function-local import keeps deployment.py free of
        # additional import-time side effects per the existing structure
        # where preset wiring also happens via runtime attachment.
        from kaizen.llm.capabilities import for_preset

        return for_preset(self.preset_name)


__all__ = [
    "WireProtocol",
    "Endpoint",
    "ResolvedModel",
    "EmbedOptions",
    "CompletionRequest",
    "StreamingConfig",
    "RetryConfig",
    "CompletionRouting",
    "LlmDeployment",
]
