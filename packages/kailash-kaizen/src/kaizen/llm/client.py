# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""LlmClient — entry point for the four-axis deployment abstraction.

Additive API: introduces `LlmClient.from_deployment(...)` alongside the
existing `kaizen.providers.registry` surface. Registry consumers are
untouched (see the option-A decision journal in the #498 workspace).

Public API (post-S1-S8 + #462):

* `LlmClient.from_deployment(d)` — construct a client from an
  `LlmDeployment` (all 24 preset factories + the registry shim).
* `LlmClient.from_deployment_sync(d)` — synchronous variant for
  cross-SDK parity with Rust's `from_deployment_sync`.
* `LlmClient.from_env()` — three-tier precedence resolver (URI >
  selector > legacy) with migration-window isolation. See
  `from_env.py` for the grammar.
* `LlmClient()` (zero-arg) additive constructor — returns an empty
  client with `.with_deployment(d)` as the only path to a usable
  state.
* `LlmClient.embed(texts, *, model=None, options=None)` — issues a
  real HTTP embedding request through `LlmHttpClient` (SSRF-safe)
  and returns a `list[list[float]]`. First wire-send method on the
  client. Supports OpenAI (`WireProtocol.OpenAiChat` deployment) and
  Ollama (`WireProtocol.OllamaNative`).

The wire-layer `complete()` send-path is deliberately NOT exposed here
until every wire-protocol adapter (OpenAIChat, AnthropicMessages,
VertexGenerateContent, BedrockInvoke, etc.) has its dispatch function
landed and exercised by a Tier 2 end-to-end test. Shipping a public
`complete()` that raises `NotImplementedError` is BLOCKED per
`rules/zero-tolerance.md` Rule 2 and `rules/orphan-detection.md` Rule 3
(Removed = Deleted, Not Deprecated).
"""

from __future__ import annotations

import json
import logging
import re
from types import TracebackType
from typing import Any, AsyncIterator, Dict, List, Optional, Union

import httpx

from kaizen.llm.auth import ApiKey, ApiKeyBearer
from kaizen.llm.deployment import (
    CompletionRequest,
    EmbedOptions,
    LlmDeployment,
    WireProtocol,
)
from kaizen.llm.errors import (
    AuthError,
    InvalidResponse,
    ProviderError,
    RateLimited,
    Timeout,
    _fingerprint,
)
from kaizen.llm.http_client import LlmHttpClient
from kaizen.llm.redaction import redact_messages
from kaizen.llm.wire_protocols import (
    anthropic_messages,
    bedrock_invoke,
    cohere_embeddings,
    cohere_generate,
    google_generate_content,
    huggingface_embeddings,
    huggingface_inference,
    mistral_chat,
    ollama_embeddings,
    ollama_native,
    openai_chat,
    openai_embeddings,
)

logger = logging.getLogger(__name__)


class UnsupportedApiKeyOverride(AuthError):
    """Raised by ``complete()``/``stream()`` when a per-request ``api_key=``
    override (#1720 Wave-1b BYOK) is supplied but the deployment's auth
    strategy has no well-defined "install this raw string instead" semantics.

    Per-request BYOK is supported ONLY for ``ApiKeyBearer``-family
    deployments — the three header kinds ``Authorization: Bearer`` /
    ``X-Api-Key`` / ``X-Goog-Api-Key`` (``kaizen.llm.auth.bearer``). Every
    other auth strategy (``AwsSigV4`` request signing, ``GcpOauth`` /
    ``AzureEntra`` token refresh, ``AwsBearerToken``, ``StaticNone``,
    ``Custom``) is REJECTED rather than silently ignored or sent under the
    deployment's own credential — ``rules/zero-tolerance.md`` Rule 3 (no
    silent fallbacks): a caller who explicitly asked for a different
    credential and got the deployment's default instead is a security bug,
    not a convenience.
    """

    def __init__(self, auth_strategy_kind: str) -> None:
        self.auth_strategy_kind = auth_strategy_kind
        super().__init__(
            "per-request api_key= override is not supported for this "
            f"deployment's auth strategy (auth_strategy_kind={auth_strategy_kind!r}); "
            "only ApiKeyBearer-family deployments (Authorization: Bearer / "
            "X-Api-Key / X-Goog-Api-Key) accept a per-request BYOK override"
        )


class InvalidApiKeyOverride(AuthError):
    """Raised when a per-request ``api_key=`` override (#1720 Wave-1b BYOK)
    fails fail-closed validation BEFORE it is installed into a header.

    /redteam Round-1/2 (#1720 Wave-1b security finding): a per-request
    ``api_key`` containing a control character (``\\r`` / ``\\n`` / ``\\x00``
    / other C0 / DEL) or a non-ASCII character is a CRLF-header-injection /
    malformed-header surface -- :class:`kaizen.llm.auth.bearer.ApiKeyBearer`
    installs the raw string directly into an HTTP header value with no
    sanitization, and the offline ``MockLlmHttpClient`` test path never
    exercises real header parsing, so the injection was previously untested
    and unguarded. Mirrors ``_validate_completion_model``'s fail-closed
    shape: reject BEFORE the value reaches anything that could act on it.

    Co-located here (NOT in ``kaizen.llm.errors``) beside its sibling
    :class:`UnsupportedApiKeyOverride` — both are client-layer BYOK-override
    guards, not part of the cross-SDK-mirrored ``errors`` taxonomy. Only the
    fingerprint (never the raw key) appears in any human-visible field.
    """

    def __init__(self, raw_credential: str) -> None:
        self.fingerprint = _fingerprint(raw_credential)
        super().__init__(
            "per-request api_key= override rejected: contains a control "
            "character (\\r, \\n, \\x00, other C0, or DEL) or a non-ASCII "
            "character; refusing to install it into a request header "
            f"(fingerprint={self.fingerprint})"
        )


# Wire-protocol dispatch for embed(). Keyed by WireProtocol enum so a
# future wire (e.g. MistralChat embeddings, CohereGenerate embeddings)
# adds one entry and its shaper module — not a conditional branch. This
# is structural dispatch on a typed key, NOT keyword-matching on user
# input (rules/agent-reasoning.md), so it is permitted deterministic
# logic: it routes on a deployment-level configuration value the caller
# explicitly set by choosing a preset.
_EMBED_DISPATCH: dict = {
    WireProtocol.OpenAiChat: {
        "path": "/embeddings",
        "shaper": openai_embeddings,
        "env_model_hint": "OPENAI_EMBEDDING_MODEL",
    },
    WireProtocol.OllamaNative: {
        "path": "/api/embed",
        "shaper": ollama_embeddings,
        "env_model_hint": "OLLAMA_EMBEDDING_MODEL",
    },
    # #1720 Wave-1b EMBED-REMAINDER — Cohere speaks its own wire family
    # (WireProtocol.CohereGenerate) across both chat AND embeddings; the
    # embed path is a fixed suffix (model travels in the JSON body, not the
    # URL), same shape as OpenAiChat/OllamaNative above.
    WireProtocol.CohereGenerate: {
        "path": "/embed",
        "shaper": cohere_embeddings,
        "env_model_hint": "COHERE_EMBEDDING_MODEL",
    },
    # HuggingFace's feature-extraction endpoint carries the model in the URL
    # path, NOT the body (mirrors HuggingFaceInference's chat path_template
    # in _COMPLETE_DISPATCH below) -- `{model}` is substituted by
    # `_build_embed_url`.
    WireProtocol.HuggingFaceInference: {
        "path": "/models/{model}",
        "shaper": huggingface_embeddings,
        "env_model_hint": "HUGGINGFACE_EMBEDDING_MODEL",
    },
}


# Wire-protocol dispatch for complete() / stream(). Keyed by WireProtocol.
# Each entry names the chat shaper and the DEFAULT URL-suffix templates used
# when the deployment carries no `completion_routing` override (direct
# providers). Presets that share a wire but route differently
# (vertex_claude / vertex_gemini / bedrock_*) set `deployment.completion_routing`
# which OVERRIDES these defaults — that override is what disambiguates the
# three AnthropicMessages consumers (Anthropic-direct vs Vertex-Claude vs
# Bedrock-Claude). `{model}` in a template is substituted with the resolved
# model id; a template beginning with `:` attaches to a model-carrying
# path_prefix without a `/` separator. This is structural dispatch on a typed
# deployment-configuration value (rules/agent-reasoning.md permits it), not
# keyword-matching on user input.
_COMPLETE_DISPATCH: dict = {
    WireProtocol.OpenAiChat: {
        "shaper": openai_chat,
        "path_template": "/chat/completions",
        "streaming_path_template": "/chat/completions",
    },
    WireProtocol.AnthropicMessages: {
        "shaper": anthropic_messages,
        "path_template": "/messages",
        "streaming_path_template": "/messages",
    },
    WireProtocol.GoogleGenerateContent: {
        "shaper": google_generate_content,
        "path_template": "/models/{model}:generateContent",
        "streaming_path_template": "/models/{model}:streamGenerateContent",
    },
    WireProtocol.VertexGenerateContent: {
        "shaper": google_generate_content,
        "path_template": ":generateContent",
        "streaming_path_template": ":streamGenerateContent",
    },
    WireProtocol.BedrockInvoke: {
        "shaper": bedrock_invoke,
        "path_template": "/model/{model}/invoke",
        "streaming_path_template": "/model/{model}/invoke-with-response-stream",
    },
    WireProtocol.CohereGenerate: {
        "shaper": cohere_generate,
        "path_template": "/chat",
        "streaming_path_template": "/chat",
    },
    WireProtocol.MistralChat: {
        "shaper": mistral_chat,
        "path_template": "/chat/completions",
        "streaming_path_template": "/chat/completions",
    },
    WireProtocol.OllamaNative: {
        "shaper": ollama_native,
        "path_template": "/api/chat",
        "streaming_path_template": "/api/chat",
    },
    WireProtocol.HuggingFaceInference: {
        "shaper": huggingface_inference,
        "path_template": "/models/{model}",
        "streaming_path_template": "/models/{model}",
    },
}


# A caller-supplied ``model`` is interpolated into the URL path for the
# ``{model}``-template wires (GoogleGenerateContent, BedrockInvoke,
# HuggingFaceInference). Legitimate ids carry ``/`` (HuggingFace ``org/model``),
# ``@`` (version pins), ``:`` (Bedrock version suffix ``...v2:0``), ``.`` and
# ``-``. This shape allows those but is fail-closed against path traversal /
# URL-control injection: it must start alphanumeric (no leading slash/dot) and
# forbids ``%``/``?``/``#``/whitespace/control, and — checked separately — the
# ``..`` and ``//`` sequences that alone can change host or traverse. A ``:``
# inside a path segment cannot change the (SSRF-checked, fixed) host.
# `\Z` (end-of-string), NOT `$` — Python's `$` also matches immediately before a
# single trailing newline, which would let "model\n" slip a control char through.
_COMPLETION_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@/:-]{0,127}\Z")


def _validate_completion_model(model: str) -> str:
    """Fail-closed validation of a caller-controlled model before it reaches the
    URL path. Raises ``ValueError`` on any traversal / URL-control attempt so an
    app that routes untrusted input into ``model=`` cannot escape the provider
    path. Byte-preserving for valid ids (no encoding — the provider sees the
    exact id)."""
    if not _COMPLETION_MODEL_RE.match(model) or ".." in model or "//" in model:
        raise ValueError(
            "model contains characters not permitted in a request path segment "
            "(allowed: alphanumerics and _.@/:- , must start alphanumeric, no "
            "'..' or '//'); refusing to build the request URL"
        )
    return model


# A per-request ``api_key=`` BYOK override (#1720 Wave-1b) is installed
# directly into an HTTP header value via ``ApiKeyBearer.apply()`` with no
# further sanitization. Any C0 control character (``\r`` / ``\n`` / ``\x00``
# / 0x01-0x1F, excluding none) in that string is a CRLF-header-injection
# surface — a caller-controlled ``\r\nX-Injected: value`` could smuggle an
# extra header onto the outbound request. /redteam Round-1 (#1720 Wave-1b
# security finding): the offline ``MockLlmHttpClient`` test path never
# exercises real HTTP header parsing, so this was previously untested and
# unguarded.
# C0 controls (\x00-\x1f) AND \x7f (DEL) — all outside RFC 7230 field-vchar
# (VCHAR = 0x21-0x7e). \r/\n/\x00 are the CRLF-header-injection primitive; the
# rest are rejected for completeness so this guard is the strict superset of the
# transport's own header-grammar check (/redteam Round-2 completeness).
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")


def _validate_api_key_override(api_key: str) -> str:
    """Fail-closed validation of a per-request ``api_key=`` override before
    it is installed into a header. Raises :class:`InvalidApiKeyOverride` on
    any control character (C0 + DEL) OR any non-ASCII character. Mirrors
    ``_validate_completion_model``'s fail-closed shape. Byte-preserving for
    valid keys (no transformation — the provider sees the exact key).

    Non-ASCII is rejected here (rather than letting it fall through to an
    opaque ``UnicodeEncodeError`` when httpx ascii-encodes the header value)
    so EVERY malformed override surfaces as the SAME typed, fingerprint-only
    error — an HTTP header value MUST be ASCII, so a non-ASCII api_key can
    never be a valid credential (/redteam Round-2 completeness)."""
    if _CONTROL_CHAR_RE.search(api_key) or not api_key.isascii():
        raise InvalidApiKeyOverride(api_key)
    return api_key


def _parse_stream_line(line: str, shaper: Any) -> Optional[Dict[str, Any]]:
    """Parse one streaming line into a shaper chunk dict, or ``None`` to skip.

    Handles both SSE framing (``data: {json}`` — OpenAI / Anthropic /
    Vertex-Gemini) and bare JSONL objects (Ollama / Bedrock). Terminal SSE
    sentinels (``[DONE]``), empty keep-alive lines, and non-JSON control
    frames (``event:`` / ``:`` comments) are skipped by returning ``None``.
    """
    if not line:
        return None
    stripped = line.strip()
    if not stripped:
        return None
    if stripped.startswith("data:"):
        stripped = stripped[len("data:") :].strip()
    if not stripped or stripped == "[DONE]":
        return None
    if stripped[0] not in "{[":
        # SSE control frame (event:, id:, retry:, or a `:` comment).
        return None
    try:
        obj = json.loads(stripped)
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    return shaper.parse_response(obj)


def _l2_normalize_vector(vector: List[float]) -> List[float]:
    """Return a unit-L2-norm copy of ``vector`` (pure math).

    This is the SINGLE client-side unit-normalization implementation. It is
    applied UNIFORMLY across every embed wire by :meth:`LlmClient.embed` when
    ``EmbedOptions.normalize`` is True (#1720 Wave-B1b, the folded F2-MEDIUM):
    divide each component by the vector's L2 norm. A zero vector (norm == 0)
    is returned UNCHANGED so normalization never divides by zero. There is no
    per-shaper normalize copy — the HuggingFace shaper's former in-``parse_response``
    normalize was removed so this is the only place normalization happens
    (no double-normalize).
    """
    norm = sum(v * v for v in vector) ** 0.5
    if norm == 0.0:
        return list(vector)
    return [v / norm for v in vector]


class LlmClient:
    """Uniform client over an `LlmDeployment`.

    The client holds the deployment by reference; the deployment is frozen
    so the client cannot mutate its own configuration post-construction.

    Optionally carries a DataFlow-compatible classification policy so
    every outbound `CompletionRequest.messages` payload is routed
    through `redact_messages` before wire-layer serialization. The
    policy is duck-typed on
    `apply_masking_to_record(model_name, record, caller_clearance)` --
    any class exposing that method works, but the DataFlow
    `ClassificationPolicy` is the canonical producer. See
    `rules/observability.md` § 8 and the §6.5 security test at
    `tests/unit/llm/security/test_llmclient_redacts_classified_prompt_fields.py`.

    # Lifecycle

    `LlmClient` is usable as a one-shot object OR as an async context
    manager with an opt-in pooled HTTP transport:

        # One-shot (unmanaged): a fresh LlmHttpClient is constructed and
        # closed per embed() call. No lifecycle method needed; nothing
        # is held between calls, so nothing leaks.
        vectors = await LlmClient.from_deployment(d).embed(texts, model=m)

        # Managed (pooled): a single persistent LlmHttpClient is created
        # on context-entry and reused across every embed() in the scope,
        # then deterministically closed on exit. Reuse amortizes the
        # SSRF-resolver + connection-pool setup across calls.
        async with LlmClient.from_deployment(d) as client:
            a = await client.embed(["text a"], model=m)
            b = await client.embed(["text b"], model=m)  # same transport

    `aclose()` (idempotent) closes the pooled transport when one was
    created; a managed client MUST be closed via `await client.aclose()`
    or by exiting its `async with` block. The `__del__` finalizer emits
    `ResourceWarning` if a managed client created a transport and was
    never closed (per `rules/patterns.md` § "Async Resource Cleanup"); it
    does NOT call close from `__del__` -- that deadlocks on CPython's root
    logging lock when the finalizer fires during GC. There is deliberately
    NO sync `close()`: a sync wrapper would need `asyncio.run()` and break
    inside any active event loop (`rules/patterns.md` § "Paired Public
    Surface"). One-shot unmanaged callers hold no transport, so they emit
    no warning and need no close.
    """

    def __init__(
        self,
        deployment: Optional[LlmDeployment] = None,
        *,
        classification_policy: Optional[object] = None,
        caller_clearance: Optional[object] = None,
        ungoverned: bool = False,
    ) -> None:
        self._deployment = deployment
        self._classification_policy = classification_policy
        self._caller_clearance = caller_clearance
        self._ungoverned = ungoverned
        # Opt-in pooled HTTP transport. Stays None for one-shot callers
        # (each embed() constructs + closes its own client). Set only on
        # the managed (async-context-manager) path, where it is the
        # persistent transport reused across embed() calls and closed at
        # aclose(). MUST be assigned BEFORE the #1779 gate below can raise —
        # __del__ reads self._http_client, so a gate-refused partial
        # construction would otherwise AttributeError in the GC finalizer.
        self._http_client: Optional[LlmHttpClient] = None
        self._managed: bool = False
        # #1779 governance_required posture: refuse a bare un-governed client
        # that would make REAL egress, at CONSTRUCTION. A deployment-less client
        # cannot egress (complete/embed/stream need a deployment), so it is not
        # gated here; mock/deterministic deployments, ungoverned=True, and the
        # OFF posture are the ONLY exemptions (an installed interceptor does NOT
        # exempt — the four-axis client never routes through it; redteam
        # CRITICAL). See governance_gate. The lazy defense-in-depth re-check in
        # embed()/complete()/stream() closes the posture-flipped-after-
        # construction hole (and the inject-a-real-transport-at-call path).
        # Runs LAST so every instance attribute __del__ touches is already set.
        if deployment is not None:
            from kaizen.llm.governance_gate import (
                enforce_governance_posture,
                is_mock_deployment,
            )

            enforce_governance_posture(
                is_mock=is_mock_deployment(deployment),
                ungoverned=ungoverned,
                surface="LlmClient",
            )
        logger.debug(
            "llm_client.constructed",
            extra={
                "has_deployment": deployment is not None,
                "wire": str(deployment.wire) if deployment is not None else None,
                "has_classification_policy": classification_policy is not None,
            },
        )

    @property
    def deployment(self) -> Optional[LlmDeployment]:
        return self._deployment

    @property
    def classification_policy(self) -> Optional[object]:
        return self._classification_policy

    def redact_request_messages(
        self,
        messages,
        *,
        model_name: str = "LlmPromptMessage",
    ):
        """Apply the configured classification policy to outbound messages.

        Returns a NEW list; the input is not mutated. When no policy is
        installed this is a pure copy. Wire adapters (OpenAI / Bedrock /
        etc.) MUST call this helper before serializing the request
        payload so prompt PII is redacted at the boundary per §6.5.
        """
        return redact_messages(
            request_messages=messages,
            policy=self._classification_policy,
            model_name=model_name,
            caller_clearance=self._caller_clearance,
        )

    def _enforce_lazy_governance(self, http_client: Optional[LlmHttpClient]) -> None:
        """#1779 defense-in-depth: re-check the ``governance_required`` posture
        at real-transport binding time.

        The construction gate (``__init__``) fires when the posture is already
        ON at construction. This lazy check closes two remaining holes: (1) the
        posture is flipped ON *after* the client is constructed, and (2) a real
        transport is injected at call time on an otherwise-ungated client.

        Exempt when the caller injected a MOCK transport (duck-typed via the
        ``is_mock_transport`` class marker so production code never imports the
        test-only transport package). A ``None`` ``http_client`` means a real
        ``LlmHttpClient`` is about to be constructed, so it is NOT exempt here;
        mock/deterministic deployment, ``ungoverned=True``, and the OFF posture
        are handled inside the gate (an installed interceptor does NOT exempt —
        redteam CRITICAL).
        """
        if http_client is not None and getattr(http_client, "is_mock_transport", False):
            return
        from kaizen.llm.governance_gate import (
            enforce_governance_posture,
            is_mock_deployment,
        )

        enforce_governance_posture(
            is_mock=is_mock_deployment(self._deployment),
            ungoverned=self._ungoverned,
            surface="LlmClient",
        )

    @classmethod
    def from_deployment(
        cls,
        deployment: LlmDeployment,
        *,
        classification_policy: Optional[object] = None,
        caller_clearance: Optional[object] = None,
        ungoverned: bool = False,
    ) -> "LlmClient":
        """Construct a client for the given deployment.

        ``ungoverned=True`` is the #1779 explicit opt-out: it disables the
        ``governance_required`` posture gate for this client.
        """
        if not isinstance(deployment, LlmDeployment):
            raise TypeError(
                "LlmClient.from_deployment requires an LlmDeployment; "
                f"got {type(deployment).__name__}"
            )
        return cls(
            deployment=deployment,
            classification_policy=classification_policy,
            caller_clearance=caller_clearance,
            ungoverned=ungoverned,
        )

    @classmethod
    def from_env(
        cls,
        *,
        classification_policy: Optional[object] = None,
        caller_clearance: Optional[object] = None,
        ungoverned: bool = False,
    ) -> "LlmClient":
        """Construct a client from environment variables.

        Three-tier precedence (Session 7 / S7):

        1. **URI tier**: `KAILASH_LLM_DEPLOYMENT` holds a deployment URI
           (`bedrock://`, `vertex://`, `azure://`, `openai-compat://`).
        2. **Selector tier**: `KAILASH_LLM_PROVIDER` holds a preset name.
        3. **Legacy tier**: per-provider `*_API_KEY` fallback, OpenAI >
           Azure > Anthropic > Google (matches today's `autoselect_provider`).

        Emits a `WARNING` if deployment-tier signals coexist with legacy
        per-provider keys; deployment path wins. See `from_env.py` for
        the full precedence chain + URI grammar.
        """
        from kaizen.llm.from_env import resolve_env_deployment

        deployment = resolve_env_deployment()
        return cls.from_deployment(
            deployment,
            classification_policy=classification_policy,
            caller_clearance=caller_clearance,
            ungoverned=ungoverned,
        )

    @classmethod
    def from_deployment_sync(
        cls,
        deployment: LlmDeployment,
        *,
        classification_policy: Optional[object] = None,
        caller_clearance: Optional[object] = None,
        ungoverned: bool = False,
    ) -> "LlmClient":
        """Synchronous variant of `from_deployment` for non-async callers.

        Identical to `from_deployment` for the construction phase -- no
        async operations are performed at construction time. The distinct
        entry point exists for API symmetry with Rust's `LlmClient::
        from_deployment_sync` and to signal intent: this client will be
        used from sync code paths that call the sync wire-send methods.

        ``ungoverned=True`` is the #1779 explicit opt-out for the
        ``governance_required`` posture gate.
        """
        return cls.from_deployment(
            deployment,
            classification_policy=classification_policy,
            caller_clearance=caller_clearance,
            ungoverned=ungoverned,
        )

    def with_deployment(self, deployment: LlmDeployment) -> "LlmClient":
        """Return a NEW client configured with the given deployment.

        The new client inherits this client's ``ungoverned`` opt-out so the
        #1779 posture gate treats the re-deployed client consistently.
        """
        if not isinstance(deployment, LlmDeployment):
            raise TypeError(
                "with_deployment requires an LlmDeployment; "
                f"got {type(deployment).__name__}"
            )
        return LlmClient(
            deployment=deployment,
            classification_policy=self._classification_policy,
            caller_clearance=self._caller_clearance,
            ungoverned=self._ungoverned,
        )

    # -----------------------------------------------------------------
    # Lifecycle — async context manager + aclose() (#1388)
    # -----------------------------------------------------------------

    async def __aenter__(self) -> "LlmClient":
        """Enter managed mode and eagerly pool the persistent HTTP transport.

        Marks the client managed so subsequent ``embed()`` calls reuse one
        ``LlmHttpClient`` instead of constructing a fresh one per call. The
        transport is created HERE (before any concurrent ``embed()``) so two
        racing ``embed()`` calls cannot each construct a transport; ``embed()``
        retains a lazy fallback for managed clients that somehow reach it with
        no transport yet.
        """
        self._managed = True
        if self._deployment is not None and self._http_client is None:
            self._http_client = LlmHttpClient(
                deployment_preset=self._deployment.wire.name,
                timeout=60.0,
            )
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        """Close the pooled transport on context exit. Delegates to aclose()."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the pooled HTTP transport, if one was created. Idempotent.

        Closes and drops the persistent ``LlmHttpClient`` so a subsequent
        managed ``embed()`` re-pools a fresh transport and ``__del__`` sees
        ``None`` (no ResourceWarning). A no-op when no transport was created
        (one-shot callers, or a managed client closed twice).
        """
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    # -----------------------------------------------------------------
    # embed() — the first wire-send method on LlmClient (#462)
    # -----------------------------------------------------------------

    async def embed(
        self,
        texts: List[str],
        *,
        model: Optional[str] = None,
        options: Optional[EmbedOptions] = None,
        timeout: Optional[float] = None,
        http_client: Optional[LlmHttpClient] = None,
    ) -> List[List[float]]:
        """Generate embedding vectors for ``texts`` via the configured deployment.

        Returns a ``list[list[float]]`` — one vector per input text, in
        the same order. For OpenAI the default vector dimension is the
        model's default (1536 for ``text-embedding-3-small``, 3072 for
        ``text-embedding-3-large``, overridable via
        ``EmbedOptions.dimensions``). For Ollama the dimension is fixed
        at the model level.

        Args:
            texts: One or more strings to embed. Empty list rejected.
            model: Override the deployment's ``default_model``. When
                ``None``, the deployment's ``default_model`` is used;
                when BOTH are ``None``, raises ``ValueError``. Per
                ``rules/env-models.md`` callers SHOULD read the model
                from the environment (``OPENAI_EMBEDDING_MODEL``,
                ``OLLAMA_EMBEDDING_MODEL``) rather than hardcoding.
            options: Optional ``EmbedOptions`` (``dimensions`` / ``user`` /
                ``input_type`` / ``normalize``). Accepted for every wire;
                individual wires may ignore fields they do not support
                (Ollama ignores ``dimensions`` per its documented contract).
                ``normalize=True`` L2-unit-normalizes every returned vector
                UNIFORMLY, client-side, for EVERY wire (#1720 Wave-B1b); a
                zero vector is returned unchanged. ``normalize`` unset / False
                leaves the raw wire vectors byte-identical.
            timeout: Optional per-request wire-call timeout, in seconds. When
                set, it bounds THIS embedding request (threaded into the
                underlying ``LlmHttpClient`` request the same way ``complete()``
                bounds its send). When ``None`` (default), the transport's own
                client-level timeout applies — byte-identical to the
                pre-``timeout`` behavior.
            http_client: Optional pre-constructed ``LlmHttpClient`` — for
                tests / advanced callers who want to share an HTTP pool
                across multiple ``embed()`` calls. When ``None``, a
                fresh client is constructed and closed per call.

        Raises:
            ValueError: ``texts`` empty, or neither ``model`` nor
                ``default_model`` set.
            TypeError: ``texts`` not a ``list[str]``, or ``options`` not
                ``EmbedOptions``.
            NotImplementedError: deployment's ``wire`` is not in the
                supported-for-embed set. This is NOT a stub — every
                supported wire is fully implemented; unsupported wires
                raise a concrete typed error directing the caller to
                file an issue. See ``_EMBED_DISPATCH`` for the supported
                set.
            InvalidResponse / ProviderError / RateLimited / Timeout:
                wire-layer failures, with credential scrubbing applied
                to all body snippets per ``errors.py``.
            InvalidEndpoint: SSRF guard rejected the deployment's
                ``base_url`` at DNS-resolve time. Raised BEFORE the TCP
                SYN fires.

        Example::

            import os
            from kaizen.llm import LlmClient, LlmDeployment
            deployment = LlmDeployment.openai(
                api_key=os.environ["OPENAI_API_KEY"],
                model=os.environ.get("OPENAI_PROD_MODEL", "gpt-4o"),
            )
            client = LlmClient.from_deployment(deployment)
            # Use an embedding model, not a chat model, for embed():
            vectors = await client.embed(
                ["text a", "text b"],
                model=os.environ["OPENAI_EMBEDDING_MODEL"],
            )
            assert len(vectors) == 2
            assert len(vectors[0]) == 1536  # text-embedding-3-small default
        """
        if self._deployment is None:
            raise ValueError(
                "LlmClient.embed requires a deployment; construct via "
                "LlmClient.from_deployment(...) or LlmClient.from_env() first"
            )
        if not isinstance(texts, list):
            raise TypeError(f"texts must be list[str]; got {type(texts).__name__}")
        if options is not None and not isinstance(options, EmbedOptions):
            raise TypeError(
                f"options must be EmbedOptions; got {type(options).__name__}"
            )

        wire = self._deployment.wire
        dispatch = _EMBED_DISPATCH.get(wire)
        if dispatch is None:
            raise NotImplementedError(
                f"LlmClient.embed does not yet support wire={wire.name!r}. "
                "Supported: OpenAiChat (openai, groq, etc.), OllamaNative, "
                "CohereGenerate, HuggingFaceInference. File an issue at "
                "terrene-foundation/kailash-py referencing #462 to request "
                "another provider."
            )

        resolved_model = model or self._deployment.default_model
        if not resolved_model:
            raise ValueError(
                "embed() requires a model — pass model=..., or construct "
                "the deployment with a default_model. Per rules/env-models.md, "
                f"read from os.environ[{dispatch['env_model_hint']!r}]."
            )

        shaper = dispatch["shaper"]
        path = dispatch["path"]
        payload = shaper.build_request_payload(texts, resolved_model, options)

        url = self._build_embed_url(path, model=resolved_model)

        # LlmHttpClient owns SSRF (via SafeDnsResolver) + structured
        # logging. NEVER construct httpx.AsyncClient directly here.
        #
        # Transport acquisition, three cases:
        #   1. Caller injected http_client= → caller owns it; embed() never
        #      closes it (owns_client stays False).
        #   2. Managed client (async-context-manager) with no injection →
        #      reuse the INSTANCE-pooled transport, lazily creating it if the
        #      managed scope somehow reached embed() before __aenter__ pooled
        #      one. The INSTANCE owns it; embed() must NOT close it per-call
        #      (it is closed at aclose()), so owns_client is False.
        #   3. Unmanaged client with no injection → construct a fresh transport
        #      per call and close it in the error/finally paths below
        #      (owns_client stays True). UNCHANGED legacy one-shot behavior.
        self._enforce_lazy_governance(http_client)
        owns_client = http_client is None
        if owns_client and self._managed:
            if self._http_client is None:
                self._http_client = LlmHttpClient(
                    deployment_preset=wire.name,
                    timeout=60.0,
                )
            http_client = self._http_client
            owns_client = False  # instance owns it; closed at aclose(), not here
        elif owns_client:
            http_client = LlmHttpClient(
                deployment_preset=wire.name,
                timeout=60.0,
            )
        assert http_client is not None  # narrowing for type-checker

        try:
            # Build request, let auth strategy install its header.
            request: dict = {"headers": {"Content-Type": "application/json"}}
            auth = self._deployment.auth
            auth.apply(request)
            # Merge endpoint.required_headers (e.g. anthropic-version —
            # not used for embed today, but correct by construction).
            for k, v in self._deployment.endpoint.required_headers.items():
                request["headers"].setdefault(k, v)

            auth_kind = (
                auth.auth_strategy_kind()
                if hasattr(auth, "auth_strategy_kind")
                else None
            )
            logger.info(
                "llm.embed.start",
                extra={
                    "wire": wire.name,
                    "auth_strategy_kind": auth_kind,
                    "text_count": len(texts),
                    "model": resolved_model,
                    "source": "real",
                    "mode": "real",
                },
            )

            # #1720 Wave-B1b: a caller-supplied ``timeout`` bounds THIS wire
            # call (legacy embed passed ``timeout`` through to the provider);
            # thread it into the httpx request only when set so an unset
            # timeout is byte-identical to the transport's client-level default.
            post_kwargs: dict = {}
            if timeout is not None:
                post_kwargs["timeout"] = timeout
            resp = await http_client.post(
                url,
                headers=request["headers"],
                json=payload,
                auth_strategy_kind=auth_kind,
                **post_kwargs,
            )
        except httpx.TimeoutException as exc:
            logger.error(
                "llm.embed.error",
                extra={"wire": wire.name, "exception_class": type(exc).__name__},
            )
            if owns_client:
                await http_client.aclose()
            raise Timeout() from exc
        except httpx.HTTPError as exc:
            # Covers ConnectError, ReadError, NetworkError, ProtocolError —
            # everything httpx surfaces that isn't a plain response.
            logger.error(
                "llm.embed.error",
                extra={"wire": wire.name, "exception_class": type(exc).__name__},
            )
            if owns_client:
                await http_client.aclose()
            raise

        # Response handling — map HTTP status to typed errors.
        try:
            if resp.status_code == 429:
                retry_after_raw = resp.headers.get("retry-after")
                retry_after: Optional[float] = None
                if retry_after_raw:
                    try:
                        retry_after = float(retry_after_raw)
                    except (TypeError, ValueError):
                        retry_after = None
                raise RateLimited(retry_after=retry_after)
            if resp.status_code >= 400:
                # Credential scrub is applied by ProviderError itself.
                raise ProviderError(resp.status_code, body_snippet=resp.text or "")
            try:
                payload_json = resp.json()
            except ValueError as exc:
                raise InvalidResponse(
                    f"{wire.name.lower()}_embeddings: response was not valid JSON"
                ) from exc
            # ``options`` is threaded into every embed shaper for dispatch
            # symmetry; the shapers consume the REQUEST-shaping fields
            # (openai ``dimensions``/``user``, cohere ``input_type``) and
            # ignore the rest. ``EmbedOptions.normalize`` is NOT a per-shaper
            # concern anymore: it is applied UNIFORMLY below, client-side, for
            # EVERY wire (#1720 Wave-B1b, folded F2-MEDIUM) — the former
            # HuggingFace-only in-``parse_response`` normalize was removed so
            # there is ONE normalize implementation and no double-normalize.
            parsed = shaper.parse_response(payload_json, options)
            vectors = parsed["vectors"]
            if not isinstance(vectors, list):
                raise InvalidResponse(
                    f"{wire.name.lower()}_embeddings: parse_response returned non-list vectors"
                )
            # #1720 Wave-B1b: single, uniform, client-side L2 unit-normalization
            # for EVERY wire when ``normalize=True``. Pure math (divide each
            # vector by its L2 norm); a zero vector is returned unchanged.
            # ``normalize`` unset / False -> vectors are byte-identical to the
            # raw wire output (zero-tolerance Rule 3c: the documented kwarg is
            # consumed by this branch, never accepted-and-dropped).
            if options is not None and options.normalize:
                vectors = [_l2_normalize_vector(v) for v in vectors]
            logger.info(
                "llm.embed.ok",
                extra={
                    "wire": wire.name,
                    "text_count": len(texts),
                    "vector_count": len(vectors),
                    "status_code": resp.status_code,
                },
            )
            return vectors
        finally:
            if owns_client:
                await http_client.aclose()

    def _build_embed_url(self, suffix: str, model: Optional[str] = None) -> str:
        """Join ``endpoint.base_url`` + ``endpoint.path_prefix`` + ``suffix``.

        Kept explicit (not ``urllib.parse.urljoin``) because ``urljoin``
        has surprising path-collapse behaviour that would drop the
        ``path_prefix`` when ``suffix`` starts with ``/``. We always
        concatenate with a single separator so the produced URL matches
        the deployment's declared shape.

        ``{model}`` in ``suffix`` is substituted with a fail-closed-validated
        ``model`` (mirrors ``_build_completion_url``'s ``{model}``
        substitution + ``_validate_completion_model`` check) -- only
        HuggingFace's feature-extraction dispatch entry
        (``"/models/{model}"``) carries the placeholder today, so every
        other embed wire's ``suffix`` passes through unchanged (byte-
        identical to the pre-#1720-EMBED-REMAINDER output). Any
        ``endpoint.query_params`` are appended as a query string (Azure's
        ``?api-version=`` reaching the embed URL, matching
        ``_build_completion_url``'s existing behaviour).
        """
        assert self._deployment is not None
        endpoint = self._deployment.endpoint
        base = str(endpoint.base_url).rstrip("/")
        prefix = (endpoint.path_prefix or "").rstrip("/")
        suffix_resolved = suffix
        if "{model}" in suffix:
            suffix_resolved = suffix.replace(
                "{model}", _validate_completion_model(model or "")
            )
        suffix_norm = (
            suffix_resolved
            if suffix_resolved.startswith("/")
            else "/" + suffix_resolved
        )
        if prefix:
            prefix_norm = prefix if prefix.startswith("/") else "/" + prefix
            url = f"{base}{prefix_norm}{suffix_norm}"
        else:
            url = f"{base}{suffix_norm}"
        if endpoint.query_params:
            from urllib.parse import urlencode

            url = f"{url}?{urlencode(endpoint.query_params)}"
        return url

    # -----------------------------------------------------------------
    # complete() / stream() — chat-completion send-path (#1717)
    # -----------------------------------------------------------------

    def _build_completion_url(self, template: str, model: Optional[str]) -> str:
        """Join ``base_url`` + ``path_prefix`` + a completion ``template``.

        ``{model}`` in the template is substituted with ``model``. A template
        beginning with ``:`` (a Vertex verb like ``:rawPredict``) attaches
        directly to the model-carrying ``path_prefix`` with NO ``/``
        separator; any other template is joined with a single ``/``. Any
        ``endpoint.query_params`` are appended as a query string.
        """
        assert self._deployment is not None
        endpoint = self._deployment.endpoint
        base = str(endpoint.base_url).rstrip("/")
        prefix = (endpoint.path_prefix or "").rstrip("/")
        if prefix and not prefix.startswith("/"):
            prefix = "/" + prefix
        root = f"{base}{prefix}"
        suffix = template.replace("{model}", model or "")
        if suffix.startswith(":"):
            url = f"{root}{suffix}"
        else:
            if not suffix.startswith("/"):
                suffix = "/" + suffix
            url = f"{root}{suffix}"
        if endpoint.query_params:
            from urllib.parse import urlencode

            url = f"{url}?{urlencode(endpoint.query_params)}"
        return url

    def _resolve_completion_route(self, dispatch: dict, *, stream: bool) -> str:
        """Pick the URL template: deployment routing override, else default."""
        assert self._deployment is not None
        routing = self._deployment.completion_routing
        if stream:
            if routing is not None and routing.streaming_path_template is not None:
                return routing.streaming_path_template
            if routing is not None and routing.path_template is not None:
                return routing.path_template
            return dispatch["streaming_path_template"]
        if routing is not None and routing.path_template is not None:
            return routing.path_template
        return dispatch["path_template"]

    def _apply_anthropic_platform_transform(
        self, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Strip ``model`` + inject ``anthropic_version`` for platform Anthropic.

        Gated on ``deployment.completion_routing.anthropic_version_body``:
        Vertex-Claude (``"vertex-2023-10-16"``) and Bedrock-Claude
        (``"bedrock-2023-05-31"``) carry the model in the URL and require the
        ``anthropic_version`` body field. Anthropic-DIRECT leaves
        ``completion_routing`` (or its ``anthropic_version_body``) ``None``,
        so the body is returned UNCHANGED — keeping direct-Anthropic bytes
        identical to the pre-#1717 output. Returns a new dict; input not
        mutated.
        """
        assert self._deployment is not None
        routing = self._deployment.completion_routing
        version = routing.anthropic_version_body if routing is not None else None
        if version is None:
            return payload
        transformed = dict(payload)
        transformed.pop("model", None)
        transformed["anthropic_version"] = version
        return transformed

    def _build_completion_request(
        self,
        messages: List[Dict[str, Any]],
        *,
        model: Optional[str],
        temperature: Optional[float],
        top_p: Optional[float],
        max_tokens: Optional[int],
        stop: Optional[List[str]],
        user: Optional[str],
        stream: bool,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, Any]] = None,
        seed: Optional[int] = None,
        logit_bias: Optional[Dict[str, float]] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        n: Optional[int] = None,
        top_k: Optional[int] = None,
    ) -> "CompletionRequest":
        """Redact messages, resolve the model, build the CompletionRequest.

        The #1720 Wave-1a completion-shaping fields (``tools`` … ``top_k``) are
        threaded through UNCHANGED; each defaults to ``None`` so a call that
        sets none of them builds a CompletionRequest identical to the
        pre-#1720 shape (the additive-neutrality invariant).
        """
        assert self._deployment is not None
        if not isinstance(messages, list):
            raise TypeError(
                f"messages must be list[dict]; got {type(messages).__name__}"
            )
        # Redact PII at the boundary BEFORE the request is shaped for the wire
        # (rules/observability.md §8 / §6.5). No-op when no policy installed.
        redacted = self.redact_request_messages(messages)
        resolved_model = model or self._deployment.default_model
        if not resolved_model:
            raise ValueError(
                "complete() requires a model — pass model=..., or construct "
                "the deployment with a default_model."
            )
        # Fail-closed: a caller-controlled model is interpolated into the URL
        # path for the {model}-template wires; reject traversal / URL-control
        # injection before the request is built (security-reviewer #1717 MEDIUM).
        _validate_completion_model(resolved_model)
        return CompletionRequest(
            model=resolved_model,
            messages=redacted,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stop=stop,
            stream=stream,
            user=user,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
            seed=seed,
            logit_bias=logit_bias,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            n=n,
            top_k=top_k,
        )

    def _build_completion_payload_and_url(
        self, request: "CompletionRequest", *, stream: bool
    ) -> tuple[Dict[str, Any], str]:
        """Shape the request body + build the URL for the deployment's wire."""
        assert self._deployment is not None
        wire = self._deployment.wire
        dispatch = _COMPLETE_DISPATCH.get(wire)
        if dispatch is None:
            # Every wire a preset can construct is covered above; the only
            # uncovered WireProtocol members (OpenAiCompletions, AzureOpenAi)
            # are never emitted by a preset (Azure uses the OpenAiChat wire).
            # A deployment reaching here was hand-assembled with an
            # unsupported wire — a concrete configuration error, not a stub.
            raise ValueError(
                f"LlmClient.complete does not support wire={wire.name!r}. "
                "Supported wires: "
                f"{', '.join(w.name for w in _COMPLETE_DISPATCH)}. File an "
                "issue at terrene-foundation/kailash-py referencing #1717 to "
                "request another provider."
            )
        shaper = dispatch["shaper"]
        # HuggingFace is the only wire whose shaper exposes BOTH a classic
        # text-generation body AND an OpenAI chat body on different routes; the
        # deployment's `completion_routing.use_chat_schema` (set by
        # `huggingface_chat_preset`) selects the chat body so `tools`/
        # `tool_choice` reach the wire instead of being dropped on the classic
        # path (#1720 F3). Guard by the typed wire enum -- every other shaper's
        # `build_request_payload` does NOT accept `use_chat_schema`, so it is
        # NEVER passed universally. This is structural dispatch on a typed
        # deployment-config value (rules/agent-reasoning.md permits it), not
        # keyword-matching on user content. When routing is absent or
        # `use_chat_schema=False` (every classic HF deployment), the shaper
        # emits the byte-identical classic `{inputs, parameters}` body.
        if wire is WireProtocol.HuggingFaceInference:
            routing = self._deployment.completion_routing
            use_chat_schema = routing.use_chat_schema if routing is not None else False
            payload = shaper.build_request_payload(
                request, use_chat_schema=use_chat_schema
            )
        else:
            payload = shaper.build_request_payload(request)
        # Platform-Anthropic body transform (Vertex / Bedrock Claude). No-op
        # for every other wire and for Anthropic-direct.
        if wire is WireProtocol.AnthropicMessages:
            payload = self._apply_anthropic_platform_transform(payload)
        template = self._resolve_completion_route(dispatch, stream=stream)
        url = self._build_completion_url(template, request.model)
        return payload, url

    async def _prepare_auth_headers(
        self,
        url: str,
        body_bytes: bytes,
        *,
        stream: bool,
        api_key: Optional[str] = None,
    ) -> tuple[Dict[str, str], Optional[str]]:
        """Run the deployment auth strategy and return (headers, auth_kind).

        Prefers ``apply_async`` (GcpOauth's single-flight refresh) when the
        strategy exposes it; otherwise the sync ``apply``. The auth request
        carries ``method`` / ``url`` / ``body`` / ``streaming`` so richer
        strategies (AwsSigV4) that canonicalize over those fields work too.
        Endpoint ``required_headers`` (e.g. ``anthropic-version``) merge in
        via ``setdefault`` so auth never clobbers them.

        ``api_key`` (#1720 Wave-1b BYOK): an OPTIONAL per-request credential
        override. ``CompletionRequest`` deliberately carries no credential
        field (it is the cross-SDK byte pre-image); BYOK threads through
        here instead of through the request body. When set, the override is
        installed via ``ApiKeyBearer.apply()`` — the SAME header-injection
        mechanism the deployment's own static credential uses — for the
        deployment's OWN header kind (``Authorization: Bearer`` /
        ``X-Api-Key`` / ``X-Goog-Api-Key``), never a hand-rolled header name.
        The deployment's own auth object is never mutated; the override is
        per-call only. Deployments whose auth strategy is NOT
        ``ApiKeyBearer`` (``AwsSigV4``, ``GcpOauth``, ``AzureEntra``,
        ``AwsBearerToken``, ``StaticNone``, ``Custom``) raise
        :class:`UnsupportedApiKeyOverride` — checked BEFORE the deployment's
        own ``apply``/``apply_async`` runs, so a rejected override never
        triggers an unnecessary token refresh (e.g. a live GCP OAuth call)
        for a credential that would then be discarded. The raw key is never
        logged: it is threaded directly into ``ApiKeyBearer``/``ApiKey``,
        whose ``__repr__`` implementations expose only a fingerprint.

        /redteam Round-1 (#1720 Wave-1b security finding): before ANY of the
        above, ``api_key`` is fail-closed-validated for control characters
        (``\\r`` / ``\\n`` / ``\\x00`` / other C0 / DEL) or non-ASCII via
        :func:`_validate_api_key_override`, raising
        :class:`InvalidApiKeyOverride` on a match — closing a
        CRLF-header-injection surface that was previously untested on the
        offline ``MockLlmHttpClient`` path.
        """
        assert self._deployment is not None
        auth = self._deployment.auth
        auth_kind = (
            auth.auth_strategy_kind() if hasattr(auth, "auth_strategy_kind") else None
        )
        if api_key is not None:
            # /redteam Round-1 (#1720 Wave-1b security finding): fail-closed
            # control-char validation BEFORE anything else runs — a
            # CRLF-header-injection surface must be rejected before the
            # unnecessary-refresh-avoidance check below, and long before
            # ApiKeyBearer.apply() installs the raw string into a header.
            _validate_api_key_override(api_key)
        if api_key is not None and not isinstance(auth, ApiKeyBearer):
            raise UnsupportedApiKeyOverride(auth_kind or type(auth).__name__)

        request: dict = {
            "method": "POST",
            "url": url,
            "headers": {"Content-Type": "application/json"},
            "body": body_bytes,
            "streaming": stream,
        }
        if api_key is not None:
            # isinstance-checked above: `auth` is an ApiKeyBearer, so
            # `auth.kind` is a valid ApiKeyHeaderKind. Reuse
            # ApiKeyBearer.apply() — never write the header name directly.
            ApiKeyBearer(kind=auth.kind, key=ApiKey(api_key)).apply(request)
        else:
            apply_async = getattr(auth, "apply_async", None)
            if callable(apply_async):
                await apply_async(request)
            else:
                auth.apply(request)
        for k, v in self._deployment.endpoint.required_headers.items():
            request["headers"].setdefault(k, v)
        return request["headers"], auth_kind

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        user: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, Any]] = None,
        seed: Optional[int] = None,
        logit_bias: Optional[Dict[str, float]] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        n: Optional[int] = None,
        top_k: Optional[int] = None,
        api_key: Optional[str] = None,
        http_client: Optional[LlmHttpClient] = None,
    ) -> Dict[str, Any]:
        """Issue a chat completion through the configured deployment.

        Mirrors :meth:`embed`: redacts prompt PII at the boundary, shapes the
        body for the deployment's wire, dispatches through the SSRF-safe
        ``LlmHttpClient``, maps HTTP status to the typed error taxonomy, and
        returns the shaper's normalized dict
        ``{text, raw_blocks?, usage, stop_reason, model}``.

        Supports OpenAI (+ every OpenAI-compatible provider), Anthropic
        (direct, Vertex-Claude, Bedrock-Claude), Google Gemini (direct +
        Vertex), Bedrock native families, Cohere, Mistral, Ollama, and
        HuggingFace. The per-wire URL, the platform-Anthropic body transform,
        and the per-model temperature floor are all data-driven — no provider
        branch in the caller path.

        #1720 completion-shaping kwargs (``tools``, ``tool_choice``,
        ``response_format``, ``seed``, ``logit_bias``, ``frequency_penalty``,
        ``presence_penalty``, ``n``, ``top_k``): the request SHAPE carries them
        (Wave 1a) and per-wire EMISSION + tool_call PARSE is LIVE (Wave 1b) for
        OpenAI (+ OpenAI-compatible), Anthropic (direct / Vertex / Bedrock),
        Google Gemini (direct / Vertex), Mistral, Cohere, and Ollama. Each wire
        emits only the fields the provider supports (unsupported fields are
        omitted, never faked) and parses tool calls back into one canonical
        shape ``[{id, type:"function", function:{name, arguments}}]``. Emission
        for the remaining wires (Bedrock native families, HuggingFace) is a
        later Wave-1b shard; passing a field to a not-yet-wired provider is a
        no-op for that field.

        ``api_key`` (#1720 Wave-1b BYOK): an OPTIONAL per-request credential
        override, applied ONLY to this call — the deployment's own
        credential is untouched for every other call. It is NOT a
        ``CompletionRequest`` field (that model is the cross-SDK byte
        pre-image and must carry no secret); it threads straight into the
        auth-header step. See :meth:`_prepare_auth_headers` for the header-
        kind contract and the ``UnsupportedApiKeyOverride`` disposition.

        Raises:
            ValueError: ``messages`` empty of a resolvable model, or no
                deployment configured.
            TypeError: ``messages`` not a ``list[dict]``.
            ValueError: the deployment's ``wire`` is not supported.
            InvalidResponse / ProviderError / RateLimited / Timeout: wire
                failures with credential scrubbing.
            InvalidEndpoint: SSRF guard rejected the URL at DNS-resolve time.
            UnsupportedApiKeyOverride: ``api_key`` was set but the
                deployment's auth strategy is not ``ApiKeyBearer``.
        """
        if self._deployment is None:
            raise ValueError(
                "LlmClient.complete requires a deployment; construct via "
                "LlmClient.from_deployment(...) or LlmClient.from_env() first"
            )
        wire = self._deployment.wire
        request = self._build_completion_request(
            messages,
            model=model,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stop=stop,
            user=user,
            stream=False,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
            seed=seed,
            logit_bias=logit_bias,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            n=n,
            top_k=top_k,
        )
        payload, url = self._build_completion_payload_and_url(request, stream=False)
        body_bytes = json.dumps(payload).encode("utf-8")

        self._enforce_lazy_governance(http_client)
        owns_client = http_client is None
        if owns_client and self._managed:
            if self._http_client is None:
                self._http_client = LlmHttpClient(
                    deployment_preset=wire.name, timeout=60.0
                )
            http_client = self._http_client
            owns_client = False
        elif owns_client:
            http_client = LlmHttpClient(deployment_preset=wire.name, timeout=60.0)
        assert http_client is not None

        try:
            headers, auth_kind = await self._prepare_auth_headers(
                url, body_bytes, stream=False, api_key=api_key
            )
            logger.info(
                "llm.complete.start",
                extra={
                    "wire": wire.name,
                    "auth_strategy_kind": auth_kind,
                    "message_count": len(request.messages),
                    "model": request.model,
                    "source": "real",
                    "mode": "real",
                },
            )
            resp = await http_client.post(
                url,
                headers=headers,
                content=body_bytes,
                auth_strategy_kind=auth_kind,
            )
        except httpx.TimeoutException as exc:
            logger.error(
                "llm.complete.error",
                extra={"wire": wire.name, "exception_class": type(exc).__name__},
            )
            if owns_client:
                await http_client.aclose()
            raise Timeout() from exc
        except httpx.HTTPError as exc:
            logger.error(
                "llm.complete.error",
                extra={"wire": wire.name, "exception_class": type(exc).__name__},
            )
            if owns_client:
                await http_client.aclose()
            raise
        except BaseException:
            # A non-httpx send-phase failure — SSRF InvalidEndpoint from the
            # transport, or a GcpOauth token-refresh error from
            # _prepare_auth_headers — happens BEFORE `resp` exists, so it never
            # reaches the response-phase finally below. Close the owned client
            # here so a one-shot caller does not leak the transport (F1).
            if owns_client:
                await http_client.aclose()
            raise

        try:
            if resp.status_code == 429:
                retry_after_raw = resp.headers.get("retry-after")
                retry_after: Optional[float] = None
                if retry_after_raw:
                    try:
                        retry_after = float(retry_after_raw)
                    except (TypeError, ValueError):
                        retry_after = None
                raise RateLimited(retry_after=retry_after)
            if resp.status_code >= 400:
                raise ProviderError(resp.status_code, body_snippet=resp.text or "")
            try:
                payload_json = resp.json()
            except ValueError as exc:
                raise InvalidResponse(
                    f"{wire.name.lower()}_complete: response was not valid JSON"
                ) from exc
            dispatch = _COMPLETE_DISPATCH[wire]
            parsed = dispatch["shaper"].parse_response(payload_json)
            logger.info(
                "llm.complete.ok",
                extra={
                    "wire": wire.name,
                    "message_count": len(request.messages),
                    "status_code": resp.status_code,
                },
            )
            return parsed
        finally:
            if owns_client:
                await http_client.aclose()

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        user: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, Any]] = None,
        seed: Optional[int] = None,
        logit_bias: Optional[Dict[str, float]] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        n: Optional[int] = None,
        top_k: Optional[int] = None,
        api_key: Optional[str] = None,
        http_client: Optional[LlmHttpClient] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream a chat completion as an async iterator of parsed chunks.

        A REAL streaming send: routes through ``LlmHttpClient.stream_lines``
        (httpx ``client.stream`` on the SAME SSRF-safe transport — no second
        client, no buffering). Each yielded dict is the shaper's parse of one
        chunk, carrying at least ``{text}``; terminal / non-JSON SSE control
        lines (``[DONE]``, empty keep-alives) are skipped.

        Consumes the deployment's :class:`StreamingConfig` — when
        ``streaming.enabled`` is False the request is issued non-streaming and
        a single parsed chunk is yielded, so callers can always iterate.

        SSE wires (OpenAI / Anthropic / Vertex-Gemini) emit ``data: {json}``
        lines; JSONL wires (Ollama / Bedrock) emit bare JSON objects per line.
        Both are handled: a ``data:`` prefix is stripped when present.

        #1720 completion-shaping kwargs (``tools`` … ``top_k``): per-wire
        emission is LIVE (Wave 1b) for OpenAI/Anthropic/Google/Mistral/Cohere/
        Ollama (Bedrock-native + HuggingFace pending). They are forwarded
        unchanged on both the streaming path AND the ``streaming.enabled=False``
        buffered-``complete()`` fallback, so the two paths stay at parity.

        ``api_key`` (#1720 Wave-1b BYOK): same per-request credential
        override contract as :meth:`complete` — forwarded unchanged on BOTH
        the buffered fallback and the real streaming send path, so BYOK
        stays at parity across both.
        """
        if self._deployment is None:
            raise ValueError(
                "LlmClient.stream requires a deployment; construct via "
                "LlmClient.from_deployment(...) or LlmClient.from_env() first"
            )
        wire = self._deployment.wire

        # StreamingConfig opt-out: issue a buffered complete() and yield the
        # single parsed result so the caller's `async for` still works.
        if not self._deployment.streaming.enabled:
            result = await self.complete(
                messages,
                model=model,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                stop=stop,
                user=user,
                tools=tools,
                tool_choice=tool_choice,
                response_format=response_format,
                seed=seed,
                logit_bias=logit_bias,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                n=n,
                top_k=top_k,
                api_key=api_key,
                http_client=http_client,
            )
            yield result
            return

        request = self._build_completion_request(
            messages,
            model=model,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stop=stop,
            user=user,
            stream=True,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
            seed=seed,
            logit_bias=logit_bias,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            n=n,
            top_k=top_k,
        )
        payload, url = self._build_completion_payload_and_url(request, stream=True)
        body_bytes = json.dumps(payload).encode("utf-8")

        self._enforce_lazy_governance(http_client)
        owns_client = http_client is None
        if owns_client and self._managed:
            if self._http_client is None:
                self._http_client = LlmHttpClient(
                    deployment_preset=wire.name, timeout=60.0
                )
            http_client = self._http_client
            owns_client = False
        elif owns_client:
            http_client = LlmHttpClient(deployment_preset=wire.name, timeout=60.0)
        assert http_client is not None

        dispatch = _COMPLETE_DISPATCH[wire]
        shaper = dispatch["shaper"]
        try:
            headers, auth_kind = await self._prepare_auth_headers(
                url, body_bytes, stream=True, api_key=api_key
            )
            logger.info(
                "llm.stream.start",
                extra={
                    "wire": wire.name,
                    "auth_strategy_kind": auth_kind,
                    "message_count": len(request.messages),
                    "model": request.model,
                    "source": "real",
                    "mode": "real",
                },
            )
            async for line in http_client.stream_lines(
                "POST",
                url,
                headers=headers,
                content=body_bytes,
                auth_strategy_kind=auth_kind,
            ):
                chunk = _parse_stream_line(line, shaper)
                if chunk is not None:
                    yield chunk
        except httpx.TimeoutException as exc:
            logger.error(
                "llm.stream.error",
                extra={"wire": wire.name, "exception_class": type(exc).__name__},
            )
            raise Timeout() from exc
        except httpx.HTTPError as exc:
            # Client-layer log parity with complete(); the transport layer also
            # logs llm.http.stream.error, but keep the wire-scoped line here too.
            logger.error(
                "llm.stream.error",
                extra={"wire": wire.name, "exception_class": type(exc).__name__},
            )
            raise
        finally:
            if owns_client:
                await http_client.aclose()

    def __del__(self) -> None:
        # Emit ResourceWarning ONLY; never call aclose()/close() from the
        # finalizer. Mirrors LlmHttpClient.__del__ — async cleanup in __del__
        # deadlocks on CPython's root logging lock when the finalizer fires
        # during GC (see rules/patterns.md § "Async Resource Cleanup"). Only a
        # managed client that pooled a transport and was never closed holds a
        # non-None _http_client here; one-shot unmanaged callers hold None and
        # emit no warning (no false positives).
        if self._http_client is not None:
            import warnings

            warnings.warn(
                "LlmClient not closed; call await client.aclose() "
                "or use it as an async context manager",
                ResourceWarning,
                stacklevel=2,
            )


__all__ = ["LlmClient", "UnsupportedApiKeyOverride"]
