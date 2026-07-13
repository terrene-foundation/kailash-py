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
from types import TracebackType
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from kaizen.llm.deployment import (
    CompletionRequest,
    EmbedOptions,
    LlmDeployment,
    WireProtocol,
)
from kaizen.llm.errors import InvalidResponse, ProviderError, RateLimited, Timeout
from kaizen.llm.http_client import LlmHttpClient
from kaizen.llm.redaction import redact_messages
from kaizen.llm.wire_protocols import (
    anthropic_messages,
    bedrock_invoke,
    cohere_generate,
    google_generate_content,
    huggingface_inference,
    mistral_chat,
    ollama_embeddings,
    ollama_native,
    openai_chat,
    openai_embeddings,
)

logger = logging.getLogger(__name__)


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
    ) -> None:
        self._deployment = deployment
        self._classification_policy = classification_policy
        self._caller_clearance = caller_clearance
        # Opt-in pooled HTTP transport. Stays None for one-shot callers
        # (each embed() constructs + closes its own client). Set only on
        # the managed (async-context-manager) path, where it is the
        # persistent transport reused across embed() calls and closed at
        # aclose().
        self._http_client: Optional[LlmHttpClient] = None
        self._managed: bool = False
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

    @classmethod
    def from_deployment(
        cls,
        deployment: LlmDeployment,
        *,
        classification_policy: Optional[object] = None,
        caller_clearance: Optional[object] = None,
    ) -> "LlmClient":
        """Construct a client for the given deployment."""
        if not isinstance(deployment, LlmDeployment):
            raise TypeError(
                "LlmClient.from_deployment requires an LlmDeployment; "
                f"got {type(deployment).__name__}"
            )
        return cls(
            deployment=deployment,
            classification_policy=classification_policy,
            caller_clearance=caller_clearance,
        )

    @classmethod
    def from_env(
        cls,
        *,
        classification_policy: Optional[object] = None,
        caller_clearance: Optional[object] = None,
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
        )

    @classmethod
    def from_deployment_sync(
        cls,
        deployment: LlmDeployment,
        *,
        classification_policy: Optional[object] = None,
        caller_clearance: Optional[object] = None,
    ) -> "LlmClient":
        """Synchronous variant of `from_deployment` for non-async callers.

        Identical to `from_deployment` for the construction phase -- no
        async operations are performed at construction time. The distinct
        entry point exists for API symmetry with Rust's `LlmClient::
        from_deployment_sync` and to signal intent: this client will be
        used from sync code paths that call the sync wire-send methods.
        """
        return cls.from_deployment(
            deployment,
            classification_policy=classification_policy,
            caller_clearance=caller_clearance,
        )

    def with_deployment(self, deployment: LlmDeployment) -> "LlmClient":
        """Return a NEW client configured with the given deployment."""
        if not isinstance(deployment, LlmDeployment):
            raise TypeError(
                "with_deployment requires an LlmDeployment; "
                f"got {type(deployment).__name__}"
            )
        return LlmClient(
            deployment=deployment,
            classification_policy=self._classification_policy,
            caller_clearance=self._caller_clearance,
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
            options: Optional ``EmbedOptions`` (``dimensions`` / ``user``).
                Accepted for every wire; individual wires may ignore
                fields they do not support (Ollama ignores ``dimensions``
                per its documented contract).
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
                "Supported: OpenAiChat (openai, groq, etc.), OllamaNative. "
                "File an issue at terrene-foundation/kailash-py referencing "
                "#462 to request another provider."
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

        url = self._build_embed_url(path)

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

            resp = await http_client.post(
                url,
                headers=request["headers"],
                json=payload,
                auth_strategy_kind=auth_kind,
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
            parsed = shaper.parse_response(payload_json)
            vectors = parsed["vectors"]
            if not isinstance(vectors, list):
                raise InvalidResponse(
                    f"{wire.name.lower()}_embeddings: parse_response returned non-list vectors"
                )
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

    def _build_embed_url(self, suffix: str) -> str:
        """Join ``endpoint.base_url`` + ``endpoint.path_prefix`` + ``suffix``.

        Kept explicit (not ``urllib.parse.urljoin``) because ``urljoin``
        has surprising path-collapse behaviour that would drop the
        ``path_prefix`` when ``suffix`` starts with ``/``. We always
        concatenate with a single separator so the produced URL matches
        the deployment's declared shape.
        """
        assert self._deployment is not None
        endpoint = self._deployment.endpoint
        base = str(endpoint.base_url).rstrip("/")
        prefix = (endpoint.path_prefix or "").rstrip("/")
        suffix_norm = suffix if suffix.startswith("/") else "/" + suffix
        if prefix:
            prefix_norm = prefix if prefix.startswith("/") else "/" + prefix
            return f"{base}{prefix_norm}{suffix_norm}"
        return f"{base}{suffix_norm}"

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
    ) -> "CompletionRequest":
        """Redact messages, resolve the model, build the CompletionRequest."""
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
        return CompletionRequest(
            model=resolved_model,
            messages=redacted,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stop=stop,
            stream=stream,
            user=user,
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
        payload = shaper.build_request_payload(request)
        # Platform-Anthropic body transform (Vertex / Bedrock Claude). No-op
        # for every other wire and for Anthropic-direct.
        if wire is WireProtocol.AnthropicMessages:
            payload = self._apply_anthropic_platform_transform(payload)
        template = self._resolve_completion_route(dispatch, stream=stream)
        url = self._build_completion_url(template, request.model)
        return payload, url

    async def _prepare_auth_headers(
        self, url: str, body_bytes: bytes, *, stream: bool
    ) -> tuple[Dict[str, str], Optional[str]]:
        """Run the deployment auth strategy and return (headers, auth_kind).

        Prefers ``apply_async`` (GcpOauth's single-flight refresh) when the
        strategy exposes it; otherwise the sync ``apply``. The auth request
        carries ``method`` / ``url`` / ``body`` / ``streaming`` so richer
        strategies (AwsSigV4) that canonicalize over those fields work too.
        Endpoint ``required_headers`` (e.g. ``anthropic-version``) merge in
        via ``setdefault`` so auth never clobbers them.
        """
        assert self._deployment is not None
        request: dict = {
            "method": "POST",
            "url": url,
            "headers": {"Content-Type": "application/json"},
            "body": body_bytes,
            "streaming": stream,
        }
        auth = self._deployment.auth
        apply_async = getattr(auth, "apply_async", None)
        if callable(apply_async):
            await apply_async(request)
        else:
            auth.apply(request)
        for k, v in self._deployment.endpoint.required_headers.items():
            request["headers"].setdefault(k, v)
        auth_kind = (
            auth.auth_strategy_kind() if hasattr(auth, "auth_strategy_kind") else None
        )
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

        Raises:
            ValueError: ``messages`` empty of a resolvable model, or no
                deployment configured.
            TypeError: ``messages`` not a ``list[dict]``.
            ValueError: the deployment's ``wire`` is not supported.
            InvalidResponse / ProviderError / RateLimited / Timeout: wire
                failures with credential scrubbing.
            InvalidEndpoint: SSRF guard rejected the URL at DNS-resolve time.
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
        )
        payload, url = self._build_completion_payload_and_url(request, stream=False)
        body_bytes = json.dumps(payload).encode("utf-8")

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
                url, body_bytes, stream=False
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
        )
        payload, url = self._build_completion_payload_and_url(request, stream=True)
        body_bytes = json.dumps(payload).encode("utf-8")

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
                url, body_bytes, stream=True
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


__all__ = ["LlmClient"]
