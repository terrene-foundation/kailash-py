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

import logging
from typing import List, Optional

import httpx

from kaizen.llm.deployment import EmbedOptions, LlmDeployment, WireProtocol
from kaizen.llm.errors import (
    InvalidResponse,
    ProviderError,
    RateLimited,
    Timeout,
)
from kaizen.llm.http_client import LlmHttpClient
from kaizen.llm.redaction import redact_messages
from kaizen.llm.wire_protocols import ollama_embeddings, openai_embeddings

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
            raise TypeError(
                f"texts must be list[str]; got {type(texts).__name__}"
            )
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
        owns_client = http_client is None
        if owns_client:
            http_client = LlmHttpClient(
                deployment_preset=wire.name,
                timeout=60.0,
            )
        assert http_client is not None  # type narrower

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
                auth.auth_strategy_kind() if hasattr(auth, "auth_strategy_kind") else None
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


__all__ = ["LlmClient"]
