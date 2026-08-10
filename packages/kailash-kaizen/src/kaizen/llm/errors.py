# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Error taxonomy for the LLM deployment abstraction.

Mirrors the Rust `LlmClientError` enum at the semantic level while remaining
Pythonic. Every error class accepting user-controlled input MUST route it
through a fingerprint before any human-visible string (repr, str, args) is
produced. Raw keys, raw URLs, or raw hostnames MUST NEVER appear verbatim in
the error message.

Taxonomy (ADR-0001 D5):

    LlmClientError
    |-- LlmError
    |   |-- Timeout
    |   |-- RateLimited
    |   |-- ProviderError
    |   `-- InvalidResponse
    |-- AuthError
    |   |-- Invalid
    |   |-- Expired
    |   `-- MissingCredential
    |-- EndpointError
    |   |-- InvalidEndpoint
    |   `-- Unreachable
    `-- ModelGrammarError
        `-- Invalid

Cross-SDK parity: class names track `LlmClientError::*` variants in
kailash-rs/crates/kaizen/src/llm/errors.rs. Semantic match only — the Python
idiom favours subclassing over a single sum-type.
"""

from __future__ import annotations

from typing import Optional

from kailash.utils.url_credentials import fingerprint_secret

from kaizen.utils.credential_scrub import scrub_credentials


def _fingerprint(raw: str | bytes, length: int = 8) -> str:
    """Produce a deterministic non-reversible tag for a sensitive value.

    8 hex chars (32 bits) matches the cross-SDK contract in
    ``rules/event-payload-classification.md`` § 2 and DataFlow's
    ``format_record_id_for_event`` helper, so a fingerprint emitted by a
    Python service and one emitted by a Rust service can be joined in the
    same forensic query. At ~1000 unique tags, birthday collision is
    ~0.01%, vs the 35% collision rate of the prior 4-char form.
    """
    # #617: migrated from SHA-256 → BLAKE2b-based fingerprint_secret to
    # close the CodeQL py/weak-sensitive-data-hashing rule class consistently
    # across all kaizen/llm sites, keeping the 8-hex cross-SDK shape stable.
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    return fingerprint_secret(raw, length=length)


# Sentinel substituted for a redacted credential on THIS surface. Distinct from
# the node surface's `[REDACTED]` so a redaction in a log line can be attributed
# to the `LlmClient` wire path rather than to `LLMAgentNode`.
_CRED_PLACEHOLDER = "[REDACTED-CRED]"


def _scrub_credentials(text: str) -> str:
    """Replace known credential patterns with a sentinel.

    Applied defensively before any body truncation so a provider that echoes
    the submitted token in its 4xx error body does not leak the full token
    into `ProviderError.body_snippet` / `str(err)` / tracing spans.

    Delegates to `kaizen.utils.credential_scrub.scrub_credentials`, the single
    scrub implementation shared with
    `kaizen.nodes.ai.error_sanitizer.sanitize_provider_error`. This module
    holds NO pattern list of its own — deliberately.

    Until this delegation landed, this module carried a SECOND, independent
    pattern tuple whose docstring claimed it "mirrors" the node-side sanitizer.
    It did not, and the drift ran in BOTH directions: every #1974 / #1960
    hardening (Slack, GitHub PAT, Stripe, Perplexity, uppercase hex, AWS
    40-char secrets, and all three URL-embedded-DSN rules) was missing HERE,
    while this module's own AWS-STS (`ASIA`) and Azure-SAS (`sig=`) rules were
    missing THERE. A pattern list that must agree with another pattern list
    will always drift; one implementation cannot.
    """
    return scrub_credentials(text, placeholder=_CRED_PLACEHOLDER)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class LlmClientError(Exception):
    """Base class for every error raised from the LLM deployment layer."""


# ---------------------------------------------------------------------------
# LlmError — provider / wire errors
# ---------------------------------------------------------------------------


class LlmError(LlmClientError):
    """Provider-side LLM errors (timeouts, rate limits, bad responses)."""


class Timeout(LlmError):
    """The provider call exceeded the configured deadline."""

    def __init__(self, timeout_s: Optional[float] = None) -> None:
        self.timeout_s = timeout_s
        if timeout_s is not None:
            super().__init__(f"llm call timed out after {timeout_s:.2f}s")
        else:
            super().__init__("llm call timed out")


class RateLimited(LlmError):
    """The provider reported a rate limit. `retry_after` is seconds."""

    def __init__(self, retry_after: Optional[float] = None) -> None:
        self.retry_after = retry_after
        if retry_after is not None:
            super().__init__(f"rate limited; retry_after={retry_after:.2f}s")
        else:
            super().__init__("rate limited; no retry_after hint")


class ProviderError(LlmError):
    """The provider returned a non-2xx response.

    `body_snippet` is defensively scrubbed BEFORE truncation and truncated to
    256 chars afterwards.

    The scrub is `kaizen.utils.credential_scrub.scrub_credentials` — the SAME
    implementation `kaizen.nodes.ai.error_sanitizer.sanitize_provider_error`
    uses, so this surface and the node surface redact an identical set of
    shapes by construction rather than by two lists agreeing. That set is
    enumerated at the shared module and currently covers vendor-prefixed keys
    (OpenAI / Anthropic / Google / Perplexity / Slack / GitHub / Stripe), AWS
    access-key IDs, STS temporary credentials and 40-char secret keys, bare and
    `Bearer` JWTs, Azure SAS `sig=` tokens, bare 32+ char hex keys,
    URL-embedded DSN credentials (postgres / redis / mongodb / any RFC-3986
    scheme), Azure OpenAI resource names, and internal filesystem paths.

    This is a STRUCTURAL last line of defense, not the only one: callers are
    still expected to redact at the source. It matters because all three feed
    sites hand this constructor the FULL, unredacted provider response body —
    `kaizen/llm/client.py` (embeddings + completions, `resp.text`) and
    `kaizen/llm/http_client.py` (streaming, `body.decode(...)`) — so whatever
    the provider echoed back, including a submitted Authorization header,
    arrives here verbatim.
    """

    _SNIPPET_LIMIT = 256

    def __init__(self, status: int, body_snippet: str = "") -> None:
        self.status = status
        # Credential scrub MUST run before truncation — if the key straddles
        # the truncation boundary, `_scrub_credentials` on the truncated
        # substring would miss the partial match. Round-1 redteam M1.
        body_snippet = _scrub_credentials(body_snippet)
        if len(body_snippet) > self._SNIPPET_LIMIT:
            body_snippet = body_snippet[: self._SNIPPET_LIMIT] + "...[truncated]"
        self.body_snippet = body_snippet
        super().__init__(f"provider error: status={status} body={body_snippet!r}")


class InvalidResponse(LlmError):
    """The provider response did not match the expected schema."""

    def __init__(self, reason: str = "") -> None:
        self.reason = reason
        super().__init__(
            f"invalid response: {reason}" if reason else "invalid response"
        )


# ---------------------------------------------------------------------------
# AuthError — credential problems
# ---------------------------------------------------------------------------


class AuthError(LlmClientError):
    """Credential / authentication errors."""


class Invalid(AuthError):
    """A credential was rejected by the provider.

    The raw key MUST NOT appear in any human-visible field. We store ONLY the
    4-char fingerprint for forensic correlation with the rotation log.
    """

    def __init__(self, raw_credential: str) -> None:
        # Defensive: fingerprint at construction, drop the raw reference.
        self.fingerprint = _fingerprint(raw_credential)
        # Deliberately do not keep `raw_credential` as an attribute; a future
        # reviewer shouldn't find a back door to the credential via `err.args`.
        super().__init__(
            f"credential rejected by provider (fingerprint={self.fingerprint})"
        )


class Expired(AuthError):
    """A credential is past its expiry window (e.g. an Entra access token)."""

    def __init__(self) -> None:
        super().__init__("credential expired; refresh required")


class MissingCredential(AuthError):
    """No credential was discovered for the deployment.

    `source_hint` is a human-readable description of the envelope that was
    searched (e.g. "OPENAI_API_KEY" or "AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY").
    The hint MUST NOT be a user-supplied string — it is a constant chosen by
    the loader.
    """

    def __init__(self, source_hint: str) -> None:
        self.source_hint = source_hint
        super().__init__(f"no credential found; checked envelope: {source_hint}")


# ---------------------------------------------------------------------------
# EndpointError — URL / reachability problems
# ---------------------------------------------------------------------------


class EndpointError(LlmClientError):
    """Endpoint (base_url / host / network) errors."""


class InvalidEndpoint(EndpointError):
    """The supplied endpoint failed validation.

    `reason` is a short code from a fixed set ("scheme", "private_ip",
    "metadata_service", "malformed_url", ...). `reason` MUST NOT contain the
    user-supplied URL; the URL MAY appear in the exception's private
    `_fingerprint` attribute for log correlation.
    """

    _REASON_ALLOWLIST = {
        "scheme",
        "private_ipv4",
        "private_ipv6",
        "loopback",
        "link_local",
        "metadata_service",
        "metadata_host",
        "malformed_url",
        "resolution_failed",
        "ipv4_mapped",
        "encoded_ip_bypass",
    }

    def __init__(self, reason: str, raw_url: Optional[str] = None) -> None:
        if reason not in self._REASON_ALLOWLIST:
            # Defensive — a caller who passed a raw URL as `reason` by mistake
            # would otherwise leak the URL into str(err). Enforce the allowlist.
            reason = "malformed_url"
        self.reason = reason
        self._fingerprint = _fingerprint(raw_url) if raw_url else None
        if self._fingerprint is not None:
            super().__init__(
                f"invalid endpoint: reason={reason} url_fingerprint={self._fingerprint}"
            )
        else:
            super().__init__(f"invalid endpoint: reason={reason}")


class Unreachable(EndpointError):
    """The endpoint resolved but could not be reached."""

    def __init__(self, host_fingerprint: Optional[str] = None) -> None:
        self.host_fingerprint = host_fingerprint
        if host_fingerprint is not None:
            super().__init__(
                f"endpoint unreachable (host_fingerprint={host_fingerprint})"
            )
        else:
            super().__init__("endpoint unreachable")


# ---------------------------------------------------------------------------
# ModelGrammarError — bad model / deployment grammar
# ---------------------------------------------------------------------------


class ModelGrammarError(LlmClientError):
    """The model string or deployment grammar is malformed."""


class ModelGrammarInvalid(ModelGrammarError):
    """`reason` is a short, caller-controlled error code.

    The reason MUST NOT echo user-supplied model strings verbatim; callers who
    want to include the name should pass a fingerprint.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"invalid model grammar: {reason}")


class ModelRequired(ModelGrammarError):
    """A deployment preset was constructed without a required model string.

    Per `rules/env-models.md`, model names MUST come from the environment
    (e.g. `os.environ["BEDROCK_MODEL_ID"]` for bedrock_claude) -- no
    hardcoded defaults. When the env var is missing or empty at the preset
    entry point, `ModelRequired` is raised with the `deployment_preset`
    label so operators can grep logs for the precise preset that rejected.
    """

    def __init__(self, deployment_preset: str, env_hint: Optional[str] = None) -> None:
        self.deployment_preset = deployment_preset
        self.env_hint = env_hint
        if env_hint:
            super().__init__(
                f"model is required for deployment_preset={deployment_preset!r}; "
                f"read it from os.environ[{env_hint!r}] per rules/env-models.md"
            )
        else:
            super().__init__(
                f"model is required for deployment_preset={deployment_preset!r}"
            )


class ConfigError(LlmClientError):
    """Base for configuration / environment resolution errors (#498 S7)."""


class NoKeysConfigured(ConfigError):
    """No deployment env vars or legacy keys resolved to a valid config."""


class InvalidUri(ConfigError):
    """KAILASH_LLM_DEPLOYMENT URI failed per-scheme regex validation."""


class InvalidPresetName(ConfigError):
    """register_preset() name failed the regex gate (#498 S8)."""


__all__ = [
    "LlmClientError",
    "LlmError",
    "Timeout",
    "RateLimited",
    "ProviderError",
    "InvalidResponse",
    "AuthError",
    "Invalid",
    "Expired",
    "MissingCredential",
    "ConfigError",
    "NoKeysConfigured",
    "InvalidUri",
    "InvalidPresetName",
    "EndpointError",
    "InvalidEndpoint",
    "Unreachable",
    "ModelGrammarError",
    "ModelGrammarInvalid",
    "ModelRequired",
]
