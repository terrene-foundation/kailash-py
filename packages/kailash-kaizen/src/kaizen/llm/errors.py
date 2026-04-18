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

import hashlib
from typing import Optional


def _fingerprint(raw: str | bytes, length: int = 4) -> str:
    """Produce a deterministic non-reversible tag for a sensitive value.

    4 hex chars (16 bits) = sufficient for forensic correlation across a
    single session's logs while too short for rainbow-table reversal of
    typical API keys.
    """
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:length]


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

    `body_snippet` MUST be truncated before construction (<= 256 chars) and
    MUST NOT echo Authorization / Set-Cookie headers or other secrets. The
    caller is responsible for redaction; this class performs a final defensive
    truncation.
    """

    _SNIPPET_LIMIT = 256

    def __init__(self, status: int, body_snippet: str = "") -> None:
        self.status = status
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
    "EndpointError",
    "InvalidEndpoint",
    "Unreachable",
    "ModelGrammarError",
    "ModelGrammarInvalid",
]
